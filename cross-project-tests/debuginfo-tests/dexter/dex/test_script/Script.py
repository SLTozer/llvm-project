# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""This file defines the DexterScript class. Using Nodes as building blocks, the DexterScript defines a complete Dexter
test, a structured definition of locations, values, and actions used to drive a debugging session and evaluate the
results.
"""


# Fundamentally scripts and traces have a two-way relationship. This is needed for iterative test writing, as the
# intended pattern is:
# Abstract test script -> Trace with collected info -> Complete test script -> Trace with test result
# A viable mapping is (Script + Dexter) -> Trace, collecting trace information according to the script, and
# (Script + Trace) -> Script, using the trace to fill in the blanks in the script.

# In terms of ordering, functions are the most granular unit that we can make total inferences about. Within a function,
# steps can happen in basically any order any number of times, so it's impossible to say in the general case where a
# particular script section occurred "before" the other. We can do some pattern matching, but we can't take stateful
# actions, e.g. enabling future breakpoints, or triggering input. In order to make this distinction, we may need to
# split apart function-level scoping from line-level scoping.


import copy
from functools import reduce
from itertools import chain
from pathlib import PurePath
import os
import re
from typing import Any, Callable, Iterable
import yaml

from dex.test_script.Nodes import (
    All,
    DexRange,
    Label,
    Expect,
    Then,
    Where,
    setup_yaml_parser,
)

from dex.utils.Exceptions import DebuggerException
from dex.utils.PrettyOutputBase import strip_color
from dex.utils.Timer import Timer


class DexterScriptError(Exception):
    pass

# Assumes no more than one label per line.
def get_labels_from_lines(lines: list[str]) -> dict[str, int]:
    dex_label_re = re.compile(r"!dex_label ([^\s!]+)")
    dex_labels = {}

    for idx, line in enumerate(lines):
        label_str_match = dex_label_re.search(line)
        if label_str_match:
            dex_labels[label_str_match.group(1)] = idx + 1

    return dex_labels


def get_labels_from_file(file: str) -> dict[str, int]:
    if not os.path.exists(file):
        return {}
    with open(file, "r", encoding="utf-8", errors="ignore") as r:
        lines = r.readlines()
    return get_labels_from_lines(lines)


class Scope:
    """Helper class used to simplify queries about the context of a Node in the Dexter Script. The context for a given
    Node consists of some base context information in the root of the script, and then all Where nodes in the parent
    chain of the current Node. Therefore each Script has a root Scope object, and each Node's context is given by a
    Scope chain built from the root Scope and every Where between the root and the given Node.
    Most queries are essentially advancing up the parent chain and finding the first matching Where; for example, if we
    want to know what `lines` a Node applies at, we may search for the nearest parent with `lines=<range>`. However, if
    we have the chain `!where {lines: 10}: { !where {function: foo}: ... }`, we want the context to be `lines=None`, as
    the `function` declaration overrides the parent `lines` and places us in a different stackframe.
    """

    def __init__(
        self,
        file: str,
        labels: dict,
        fn: str | None = None,
        lines: int | range | list | None = None,
        conditions: dict | None = None,
        after_hit_count: int | None = None,
        for_hit_count: int | None = None,
        parent_scope=None,
    ):
        self.file = file
        self.labels = labels
        self.fn = fn
        self.lines = lines
        self.conditions = conditions
        self.after_hit_count = after_hit_count
        self.for_hit_count = for_hit_count
        self.where: Where = None
        self.parent_scope: Scope | None = parent_scope

    def empty_scope():
        return Scope(None, dict())

    # Returns a new Scope resulting from applying the new Where to this scope.
    # Note that the 'Where' does not need to be contained within the current scope; for example, if 'where' is in a
    # different file to this scope, we take that as the new file and invalidate any existing fn/line info since it no
    # longer applies to the new scope.
    # TODO: As the logic for nested !wheres is changing, so that we evaluate every !where sequentially as move up the
    # stack, the prior logic
    def add_where(self, where: Where, per_file_labels: dict[str, int] = {}):
        scope_file = self.file
        scope_fn = self.fn
        scope_lines = self.lines
        scope_conditions = self.conditions
        scope_after_hit_count = self.after_hit_count
        scope_for_hit_count = self.for_hit_count
        if where.file:
            scope_file = where.file
            scope_fn = None
            scope_lines = None
            scope_for_hit_count = None
            scope_after_hit_count = None
        if where.function:
            # Hack to make function `where`s easier. This will be removed anyway when we fix up the logic.
            # if not where.file:
            #     scope_file = None
            scope_fn = where.function
            scope_lines = None
            scope_for_hit_count = None
            scope_after_hit_count = None
            scope_conditions = None
        if where.lines:
            scope_lines = where.lines
            scope_for_hit_count = None
            scope_after_hit_count = None
            scope_conditions = None
        if where.conditions:
            scope_conditions = where.conditions
        if where.for_hit_count:
            scope_for_hit_count = where.for_hit_count
        if where.after_hit_count:
            scope_after_hit_count = where.after_hit_count
        scope_labels = per_file_labels.get(scope_file, {})
        result = Scope(
            scope_file,
            scope_labels,
            fn=scope_fn,
            lines=scope_lines,
            conditions=scope_conditions,
            for_hit_count=scope_for_hit_count,
            after_hit_count=scope_after_hit_count,
            parent_scope=self,
        )
        result.where = where
        return result

    def as_where(self) -> Where:
        attributes = {
            "file": self.file,
            "function": self.fn,
            "lines": self.lines,
            "conditions": self.conditions,
            "after_hit_count": self.after_hit_count,
            "for_hit_count": self.for_hit_count,
        }
        return Where({k: v for k, v in attributes.items() if v is not None})

    def get_file(self):
        """Returns the file referenced by this scope, if any, converted to an absolute path using the source root
        directory."""
        return self.where.get_file() if self.where else self.file

    def get_lines(self):
        # This should use self.labels to resolve "lines" to something concrete, when we have proper label support.
        if not self.lines:
            return []
        if isinstance(self.lines, int):
            return [self.lines]
        if isinstance(self.lines, Label):
            return [self.labels[self.lines.name]]
        assert isinstance(self.lines, DexRange)
        return self.lines.to_range(self.labels)

    def get_line_range(self):
        if not self.lines:
            return None
        if isinstance(self.lines, int):
            return range(self.lines, self.lines + 1)
        if isinstance(self.lines, Label):
            label_line = self.labels[self.lines.name]
            return range(label_line, label_line + 1)
        # FIXME: For non-contiguous ranges this is incorrect, as is returning a range here at all - fix it later.
        if isinstance(self.lines, list):
            return range(self.lines[0], self.lines[-1] + 1)
        assert isinstance(self.lines, DexRange)
        return self.lines.to_range(self.labels)

    # Awkward design to match current Dexter interface.
    def get_single_condition(self):
        if not self.conditions or len(self.conditions) != 1:
            return (None, None)
        return (self.conditions.keys()[0], self.conditions.values()[0])


## Structure of a Dexter script:
# <root> ::= { <where-entry>* }
# <where-entry> ::= <where>: { ( <where-entry> | <expect-entry> | ? <then> )* }
# <where>: !where { args }
# <expect-entry> ::= <expect>: <expected-result>
# <expect>: !value | !type | !steps
# <expected-results>: list | dict | str

class DexterScript:
    def __init__(
        self,
        context,
        script_obj,
        scope: Scope,
        per_file_labels: dict = None,
        source_root_dir: str = None,
        opening_line: int = None,
        closing_line: int = None,
    ):
        self.context = context
        self.script_obj = script_obj
        self.root_scope = scope
        self.has_unknowns = False
        self.opening_line = opening_line
        self.closing_line = closing_line
        self.per_file_labels = {}
        if scope.file and scope.labels:
            self.per_file_labels[scope.file] = scope.labels
        self.validate()
        if per_file_labels is None:
            self.gather_labels(source_root_dir)

    # Verifies that the contents of the script are valid, and performs some initialization.
    def validate(self):
        if not isinstance(self.script_obj, (dict, list)):
            raise DexterScriptError(self.script_obj)

        # script is either a list of scripts, or a dict containing declarations.
        def validate_subscript(script):
            if isinstance(script, list):
                for s in script:
                    validate_subscript(s)
            if not isinstance(script, dict):
                raise DexterScriptError(script)
            for key, value in script.items():
                if isinstance(key, Where):
                    if not isinstance(value, (dict, Then)):
                        raise DexterScriptError(script)
                    if isinstance(value, dict):
                        validate_subscript(value)
                elif isinstance(key, Expect):
                    # TODO: Fully verify the contents of the expect.
                    pass
                else:
                    raise DexterScriptError(key)

        validate_subscript(self.script_obj)

    # If a truthy value is returned, abort further visiting and return that value..
    def _visit_script(
        self, script, scope: Scope, visit_where=None, visit_expect=None, visit_then=None
    ) -> Any:
        def do(visitor, *args):
            if visitor:
                return visitor(*args)
            return None

        if isinstance(script, list):
            for item in script:
                if result := self._visit_script(
                    item, scope, visit_where, visit_expect, visit_then
                ):
                    return result
        elif isinstance(script, dict):
            for key, value in script.items():
                if isinstance(key, Where):
                    if result := do(visit_where, key, scope):
                        return result
                    new_scope = scope.add_where(key, self.per_file_labels)
                    if result := self._visit_script(
                        value, new_scope, visit_where, visit_expect, visit_then
                    ):
                        return result
                elif isinstance(key, Expect):
                    if result := do(visit_expect, key, value, scope):
                        return result
                else:
                    # If we have `where {...}: {scalar: value}`, it's not clear what that should mean, but we visit
                    # 'value' here as a default since we'll probably use that at some point.
                    if result := self._visit_script(
                        value, scope, visit_where, visit_expect, visit_then
                    ):
                        return result
        elif isinstance(script, Then):
            # `Then` is a special case in that it is a scalar node that may be directly mapped to by a !where, since
            # !then does not need any mapped arguments.
            if result := do(visit_then, script, scope):
                return result

    # Any visitor function provided may return a truthy value to abort the visit and return that value.
    def visit_script(
        self,
        visit_where: Callable[[Where, Scope], Any] | None = None,
        visit_expect: Callable[[Expect, Any, Scope], Any] | None = None,
        visit_then: Callable[[Then, Scope], Any] | None = None,
    ) -> Any:
        return self._visit_script(
            self.script_obj, self.root_scope, visit_where, visit_expect, visit_then
        )

    def _map_script(
        self,
        script,
        scope: Scope,
        map_where: Callable[[Where, Scope], Where],
        map_expect: Callable[[Expect, Any, Scope], tuple[Expect, Any]],
        map_then: Callable[[Then, Scope], Then],
    ) -> Any:
        if isinstance(script, list):
            mapped_list = [
                mapped_item
                for item in script
                if (mapped_item := self._map_script(item, scope, map_where, map_expect, map_then)) is not None
            ]
            if not mapped_list:
                return None
            return mapped_list
        elif isinstance(script, dict):
            result = {}
            for key, value in script.items():
                if isinstance(key, Where):
                    new_where = map_where(key, scope)
                    if new_where is None:
                        continue
                    new_scope = scope.add_where(new_where, self.per_file_labels)
                    new_where_children = self._map_script(
                        value, new_scope, map_where, map_expect, map_then
                    )
                    if new_where_children is not None:
                        result[new_where] = new_where_children
                elif isinstance(key, Expect):
                    new_expect, new_expected = map_expect(key, value, scope)
                    if new_expect is None:
                        continue
                    result[new_expect] = new_expected
                else:
                    # If we have `where {...}: {scalar: value}`, it's not clear what that should mean, but we visit
                    # 'value' here as a default since we'll probably use that at some point.
                    result[key] = value
            if not result:
                return None
            return result
        elif isinstance(script, Then):
            # `Then` is a special case in that it is a scalar node that may be directly mapped to by a !where, since
            # !then does not need any mapped arguments.
            return map_then(script)
        raise f"Invalid element in script: {script}"

    # Remap the script object recursively, and return a substitute script. Each map function remaps a node, or in the
    # case of an Expect, its node + mapping.
    def map_script(
        self,
        map_where: Callable[[Where, Scope], Where] = lambda w, _: w,
        map_expect: Callable[
            [Expect, Any, Scope], tuple[Expect, Any]
        ] = lambda e, v, _: (e, v),
        map_then: Callable[[Then, Scope], Then] = lambda t: t,
    ) -> "DexterScript":
        new_script_obj = self._map_script(
            self.script_obj, self.root_scope, map_where, map_expect, map_then
        )
        return DexterScript(
            self.context,
            new_script_obj,
            self.root_scope,
            per_file_labels=self.per_file_labels,
        )

    def gather_labels(self, source_root_dir: str = None):
        def add_where_file_labels(where: Where, scope: Scope):
            if not where.file:
                return
            if where.file in self.per_file_labels:
                return
            # FIXME: We'll eventually need to use source_root_dir here.
            if not os.path.isabs(where.file) and source_root_dir is None:
                return
            file = (
                where.file
                if os.path.isabs(where.file)
                else os.path.join(source_root_dir, where.file)
            )
            if not os.path.isfile(file):
                return
            self.per_file_labels[where.file] = get_labels_from_file(file)

        self.visit_script(visit_where=add_where_file_labels)

        # Now save cached label values for each Where.
        def add_cached_where_labels(where: Where, scope: Scope):
            where.cache_context(
                source_root_dir, self.per_file_labels.get(where.file or scope.file, {})
            )

        self.visit_script(visit_where=add_cached_where_labels)

    # TODO: Represent DexCommandLine in the new script format.
    def get_cmd_line_directives(self):
        return []

    @property
    def root_wheres(self) -> set[Where]:
        return set(node for node in self.script_obj if isinstance(node, Where))

    def format(self, process_node: Callable[[Any, Scope], str] = None):
        def format_node(node: Any, scope: Scope) -> str:
            if process_node is not None:
                return process_node(node, scope)
            return str(node)

        # Don't print trailing newlines.
        def format_subscript(script: list | dict, indent: str, scope: Scope):
            result = ""
            if isinstance(script, list):
                result += f"{indent}[\n"
                for s in script:
                    s_str = format_subscript(s, indent + "  ", scope)
                    result += s_str + "\n"
                result += f"{indent}]\n"
            elif isinstance(script, dict):
                item_results = []
                alignment_width = max(len(strip_color(str(key))) for key in script) + 2
                for key, value in script.items():
                    formatted_key = format_node(key, scope) + ": "
                    if len(strip_color(formatted_key)) < alignment_width:
                        formatted_key += " " * (
                            alignment_width - len(strip_color(formatted_key))
                        )
                    item_result = indent + "  " + formatted_key
                    if isinstance(value, dict):
                        next_scope = (
                            scope.add_where(key, self.per_file_labels)
                            if isinstance(key, Where)
                            else scope
                        )
                        item_result += "\n" + format_subscript(
                            value, indent + "  ", next_scope
                        )
                    elif isinstance(value, list):
                        list_indent = " " * (len(indent) + alignment_width + 2)

                        if value:
                            # We keep list_indent but lstrip here, as the first line of this list item already has an
                            # "indent" as it is printed on the same line as its parent, but any subsequent lines will
                            # need to have the correct indentation.
                            item_result += format_subscript(
                                value[0], list_indent, scope
                            ).lstrip()
                        for v in value[1:]:
                            item_result += f"\n" + format_subscript(
                                v, list_indent, scope
                            )
                    else:
                        item_result += format_node(value, scope)
                    item_results.append(item_result)
                result = "\n".join(item_results)
            else:
                result = indent + format_node(script, scope)
            return result

        return format_subscript(self.script_obj, "", self.root_scope)

    def write_script(self, whole_file: bool = True) -> str:
        script = yaml.dump(self.script_obj)
        if not whole_file:
            return script
        script_lines = ["---"] + script.splitlines() + ["..."]
        if self.opening_line is None or self.closing_line is None:
            return "\n".join(script_lines)
        # FIXME: Is this always correct, or do we need to track this better? We should probably do away with the current
        # logic for merging scripts too, each one will need to write itself out individually.
        original_file = self.root_scope.file
        with open(original_file, "r") as r:
            original_file_lines = r.read().splitlines()
        assert original_file_lines, "Read no valid lines?"
        original_file_lines[self.opening_line : self.closing_line] = script_lines
        return "\n".join(original_file_lines)

    # Creates a copy of this script, with any wildcard elements resolved to concrete values. This requires a variation
    # of the existing visitor logic:
    # - A script comprises dicts, lists, objects, and scalars. For these nodes, a list cannot contain scalars unless it
    #   consists entirely of scalars and is the value of an object key in a dict, and in such cases the list is itself
    #   treated itself as a scalar.
    # - The root of the script is always a dict.
    # - A dict maps object keys to any other type, though most objects are restricted in what types they can map to.
    #   When we map a dict, we visit each (k, v) entry, and the visitor returns an iterable of entries that are inserted
    #   into the resolved dict.
    # - A list contains any combination of dicts, objects, and lists; we visit each individually, and accumulate the
    #   results into the list, so there is not a way to map one original entry into multiple new entries.
    # - Objects can either be visited as standalone, as when they are in a list or the value in a dict entry, or as keys
    #   in a dict.
    # - Scalars are not visited as standalone items, since they don't resolve to anything different.
    # - The only elements that currently need to be resolved are:
    #   - `Unknown` objects, when used as a value in a dict, will resolve to a scalar.
    #   - `All` objects, when used as a key in a dict, will resolve to one or more new entries in the resolved dict.
    def resolve_script(self, reified_map: dict):
        # Returns an iterable of (k, v).
        def resolve_dict_entry(k: object, v) -> Iterable[tuple]:
            # Possible resolutions:
            if isinstance(k, All):
                entries = []
                for lines, expects in reified_map.get(k, {}).items():
                    if lines is None:
                        for var, expected in expects.items():
                            entries.append((var, expected))
                    else:
                        where = Where({"lines": lines}, True)
                        new_expects = {}
                        for var, expected in expects.items():
                            new_expects[var] = expected
                        entries.append((where, new_expects))
                return entries
            if (isinstance(k, Expect)) and v is None and reified_map.get(k, None) is not None:
                return [(copy.deepcopy(k), copy.deepcopy(reified_map[k]))]
            # Otherwise, we only need to resolve recursively.
            return [(copy.deepcopy(k), resolve_obj(v))]

        def resolve_dict(d: dict) -> dict:
            return {
                new_k: new_v
                for k, v in d.items()
                for new_k, new_v in resolve_dict_entry(k, v)
            }

        def resolve_list(l: list) -> list:
            return [resolve_obj(item) for item in l]

        def resolve_obj(item):
            if isinstance(item, dict):
                return resolve_dict(item)
            if isinstance(item, list):
                return resolve_list(item)
            # Assume item is a node or scalar in a context that does not need resolving.
            return copy.deepcopy(item)

        new_script = DexterScript(
            self.context,
            resolve_obj(self.script_obj),
            self.root_scope,
            per_file_labels=self.per_file_labels,
        )
        new_script.opening_line = self.opening_line
        new_script.closing_line = self.closing_line
        return new_script


def merge_scripts(scripts: list[DexterScript]) -> DexterScript:
    assert len(scripts) > 0, "Need actual scripts to merge"
    if len(scripts) == 1:
        return scripts[0]
    new_script_obj = {s.root_scope.as_where(): s.script_obj for s in scripts}
    new_per_file_labels = reduce(
        lambda new_labels, script: new_labels | script.per_file_labels, scripts, {}
    )
    return DexterScript(
        scripts[0].context,
        new_script_obj,
        Scope.empty_scope(),
        per_file_labels=new_per_file_labels,
    )


# Helper function to apply a line offset to the errors reported by YAML while loading, to account for the YAML documents
# being embedded in part of a file.
def try_load_yaml(yaml_doc, loader, line_offset=0):
    try:
        return yaml.load(yaml_doc, loader)
    except yaml.MarkedYAMLError as e:
        # We can't modify `e.problem_mark.line` in-place, as Mark may be immutable, so we overwrite with a
        # new mark.
        def adjust_mark_loc(mark: yaml.Mark | None) -> yaml.Mark | None:
            if mark is None:
                return None
            return yaml.Mark(
                mark.name,
                mark.index,
                mark.line + line_offset,
                mark.column,
                mark.buffer,
                mark.pointer,
            )

        e.context_mark = adjust_mark_loc(e.context_mark)
        e.problem_mark = adjust_mark_loc(e.problem_mark)
        raise e


def get_scripts(context, file, loader, source_root_dir) -> list[DexterScript]:
    with open(file, "r") as r:
        lines = r.readlines()
    assert lines, "Read no valid lines?"
    labels = get_labels_from_lines(lines)
    scope_file = str(file)
    scripts = []
    curr_yaml_doc = []
    start_line = None
    for idx, line in enumerate(lines):
        line = line.rstrip()
        if line == "---":
            curr_yaml_doc.append(line)
            start_line = idx
        elif curr_yaml_doc:
            curr_yaml_doc.append(line)
            # We expect yaml docs to end with '...'
            if line.startswith("..."):
                new_script = DexterScript(
                    context,
                    try_load_yaml("\n".join(curr_yaml_doc), loader, start_line),
                    Scope(scope_file, labels),
                    source_root_dir=source_root_dir,
                )
                new_script.opening_line = start_line
                new_script.closing_line = idx + 1
                scripts.append(new_script)
                curr_yaml_doc = []
    if curr_yaml_doc:
        new_script = DexterScript(
            context,
            try_load_yaml("\n".join(curr_yaml_doc), loader, start_line),
            Scope(scope_file, labels),
            source_root_dir=source_root_dir,
        )
        new_script.opening_line = start_line
        new_script.closing_line = len(lines)
        scripts.append(new_script)
    elif start_line is None:
        # If we saw no '---', then assume the whole file is a document and try to parse it.
        new_script = DexterScript(
            context,
            try_load_yaml("\n".join(lines), loader, 0),
            Scope(scope_file, labels),
            source_root_dir=source_root_dir,
        )
        new_script.opening_line = 0
        new_script.closing_line = len(lines)
        scripts.append(new_script)
    return scripts


def get_dexter_script(context, test_files, source_root_dir):
    setup_yaml_parser(yaml.CLoader)
    with Timer("parsing script"):
        try:
            scripts: list[DexterScript] = list(
                chain.from_iterable(
                    get_scripts(context, file, yaml.CLoader, source_root_dir)
                    for file in test_files
                )
            )
            if not scripts:
                return None, None
            source_files = set()
            for script in scripts:
                def check_explicit_files(where: Where, scope: Scope):
                    if not where.file:
                        return
                    declared_path = where.file
                    if not os.path.isabs(declared_path):
                        source_dir = (
                            source_root_dir
                            if source_root_dir
                            else os.path.dirname(script.root_scope.file)
                        )
                        declared_path = os.path.join(source_dir, declared_path)
                    source_files.add(str(PurePath(declared_path)))

                script.visit_script(visit_where=check_explicit_files)
            single_script = merge_scripts(scripts)
            return single_script, source_files
        except DexterScriptError as e:
            raise DebuggerException(f"parser error: {e}\n")
