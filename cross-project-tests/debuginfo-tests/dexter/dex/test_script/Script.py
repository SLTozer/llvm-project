
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


from itertools import chain
from pathlib import PurePath
import os
import re
import yaml

from dex.test_script.Rules import Expect, Scope, Then, Where, setup_yaml_parser
from dex.test_script.DataTypes import StepExpectInfo

from dex.utils.Exceptions import DebuggerException
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
    with open(file, "r") as r:
        lines = r.readlines()
    return get_labels_from_lines(lines)

class DexterScript:
    def __init__(self, script_obj, scope: Scope):
        self.script_obj = script_obj
        self.root_scope = scope
        self.has_unknowns = False
        self.opening_line = None
        self.closing_line = None
        self.per_file_labels = {}
        if scope.file and scope.labels:
            self.per_file_labels[scope.file] = scope.labels
        self.validate()
        self.gather_labels()

    # Verifies that the contents of the script are valid, and performs some initialization.
    def validate(self):
        if not isinstance(self.script_obj, list) and not isinstance(self.script_obj, dict):
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
                    if not isinstance(value, (dict, list, Then)):
                        raise DexterScriptError(script)
                    validate_subscript(value)
                elif isinstance(key, Expect):
                    # TODO: Fully verify the contents of the expect.
                    if isinstance(value, dict):
                        raise DexterScriptError(script)
                else:
                    raise DexterScriptError(key)

    def _visit_script(self, script, scope: Scope, visit_where=None, visit_expect=None, visit_then=None):
        if isinstance(script, list):
            for item in script:
                self._visit_script(item, scope, visit_where, visit_expect, visit_then)
        elif isinstance(script, dict):
            for key, value in script.items():
                if isinstance(key, Where):
                    if visit_where:
                        visit_where(key, scope)
                    new_scope = scope.add_where(key, self.per_file_labels)
                    self._visit_script(value, new_scope, visit_where, visit_expect, visit_then)
                elif isinstance(key, Expect):
                    if visit_expect:
                        visit_expect(key, value, scope)
                else:
                    # If we have `where {...}: {scalar: value}`, it's not clear what that should mean, but we visit
                    # 'value' here as a default since we'll probably use that at some point.
                    self._visit_script(value, scope, visit_where, visit_expect, visit_then)
        elif isinstance(script, Then):
            # `Then` is a special case in that it is a scalar node that may be directly mapped to by a !where, since
            # !then does not need any mapped arguments.
            if visit_then:
                visit_then(script, scope)

    def visit_script(self, visit_where=None, visit_expect=None, visit_then=None):
        self._visit_script(self.script_obj, self.root_scope, visit_where, visit_expect, visit_then)

    def gather_labels(self):
        def add_where_file_labels(where: Where, scope: Scope):
            if not where.file:
                return
            if where.file in self.per_file_labels:
                return
            # FIXME: We'll eventually need to use source_root_dir here.
            if not os.path.isfile(where.file):
                return
            self.per_file_labels[where.file] = get_labels_from_file(where.file)

        self.visit_script(visit_where=add_where_file_labels)

    # FIXME: Represent DexCommandLine in the new script format.
    def get_cmd_line_directives(self):
        return []

    def get_watches(self) -> list[StepExpectInfo]:
        watches = []
        def get_expect_watches(expect: Expect, values, scope: Scope):
            exprs = expect.get_watched_exprs()
            for expr in exprs:
                watches.append(StepExpectInfo(expr, scope.file, 0, scope.get_line_range()))
        self.visit_script(visit_expect=get_expect_watches)
        return watches

    def print(self):
        # Don't print trailing newlines.
        def print_subscript(script: list | dict, depth: int):
            result = ""
            indent = "  " * depth
            if isinstance(script, list):
                result += f"{indent}[\n"
                for s in script:
                    s_str = print_subscript(s, depth + 1)
                    result += s_str + ",\n"
                result += f"{indent}]\n"
            elif isinstance(script, dict):
                item_results = []
                for key, value in script.items():
                    item_result = indent + "  " + str(key) + ": "
                    if isinstance(key, Where):
                        item_result += "\n" + print_subscript(value, depth + 1)
                    else:
                        item_result += str(value)
                    item_results.append(item_result)
                result = ",\n".join(item_results)
            elif isinstance(script, Then):
                result = indent + "  " + str(script)
            return result
        print(print_subscript(self.script_obj, 0))

    def write_script(self, whole_file: bool = True) -> str:
        script = yaml.dump(self.script_obj)
        if not whole_file:
            return script
        assert self.opening_line is not None and self.closing_line is not None, "Can't print the full test file without knowing where the script is contained inside it"
        script_lines = ['---'] + script.splitlines() + ['...']
        # FIXME: Is this always correct, or do we need to trakc this better? We should probably do away with the current
        # logic for merging scripts too, each one will need to write itself out individually.
        original_file = self.root_scope.file
        with open(original_file, 'r') as r:
            original_file_lines = r.read().splitlines()
        assert original_file_lines, "Read no valid lines?"
        original_file_lines[self.opening_line:self.closing_line] = script_lines
        return '\n'.join(original_file_lines)

def merge_scripts(scripts: list[DexterScript]) -> DexterScript:
    assert len(scripts) > 0, "Need actual scripts to merge"
    if len(scripts) == 1:
        return scripts[0]
    new_script_obj = {s.root_scope.as_where(): s.script_obj for s in scripts}
    return DexterScript(new_script_obj, Scope.empty_scope())


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


def get_scripts(file, loader) -> list[DexterScript]:
    with open(file, 'r') as r:
        lines = r.readlines()
    assert lines, "Read no valid lines?"
    labels = get_labels_from_lines(lines)
    scope_file = str(file)
    scripts = []
    curr_yaml_doc = []
    start_line = None
    for idx, line in enumerate(lines):
        line = line.rstrip()
        if False: # Toggle for debugging
            print(f"{str(idx).rjust(3)}: {line}")
        if line == '---':
            curr_yaml_doc.append(line)
            start_line = idx
        elif curr_yaml_doc:
            curr_yaml_doc.append(line)
            # We expect yaml docs to end with '...'
            if line.startswith("..."):
                new_script = DexterScript(
                    try_load_yaml("\n".join(curr_yaml_doc), loader, start_line),
                    Scope(scope_file, labels),
                )
                new_script.opening_line = start_line
                new_script.closing_line = idx + 1
                scripts.append(new_script)
                curr_yaml_doc = []
    if curr_yaml_doc:
        new_script = DexterScript(
            try_load_yaml("\n".join(curr_yaml_doc), loader, start_line),
            Scope(scope_file, labels),
        )
        new_script.opening_line = start_line
        new_script.closing_line = len(lines)
        scripts.append(new_script)
    return scripts

def get_dexter_script(test_files, source_root_dir):
    setup_yaml_parser(yaml.CLoader)
    with Timer("parsing script"):
        try:
            scripts: list[DexterScript] = list(chain.from_iterable(get_scripts(file, yaml.CLoader) for file in test_files))
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
                            else os.path.dirname(script.root_scope)
                        )
                        declared_path = os.path.join(source_dir, declared_path)
                    source_files.add(str(PurePath(declared_path)))
                script.visit_script(visit_where=check_explicit_files)
            single_script = merge_scripts(scripts)
            return single_script, source_files
        except DexterScriptError as e:
            msg = f"parser error: {e}\n"
            raise DebuggerException(msg)
