
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


from collections import OrderedDict, namedtuple
import difflib
from itertools import chain
from pathlib import PurePath
import pprint
import os
from typing import Any
import yaml
from enum import Enum

from dex.test_script.Rules import Expect, Label, Scope, ScriptKeyword, Steps, Then, Type, Unknown, Value, Where
from dex.test_script.DataTypes import StepExpectInfo

from dex.dextIR.StepIR import StepIR
from dex.dextIR.LocIR import LocIR
from dex.dextIR.FrameIR import FrameIR
from dex.utils.Exceptions import DebuggerException
from dex.utils.Timer import Timer

# We use an inclusive range in Dexter scripts, while python ranges are exclusive.
def range_constructor(loader, node):
    range_seq = loader.construct_sequence(node)
    if len(range_seq) != 2 or not all([isinstance(elt, int) for elt in range_seq]):
        raise DexterScriptError(range_seq, "!range must have exactly 2 int elements")
    return range(range_seq[0], range_seq[1] + 1)

def range_representer(dumper, data: range):
    return dumper.represent_sequence('!range', data.start, data.stop - 1)

class DexterScriptError(Exception):
    pass

class DexterScript:
    def __init__(self, script_obj, scope: Scope):
        self.script_obj = script_obj
        self.root_scope = scope
        self.has_unknowns = False
        self.opening_line = None
        self.closing_line = None

    # Verifies that the contents of the script are valid.
    def validate(self):
        if not isinstance(self.script_obj, list) and not isinstance(self.script_obj, dict):
            raise DexterScriptError(self.script_obj)
        if isinstance(self.script_obj, dict):
            labels = self.script_obj.get("labels")
            if labels is not None:
                if not isinstance(labels, list):
                    raise DexterScriptError(labels)
                for label in labels:
                    if not isinstance(label, Label):
                        raise DexterScriptError(label)
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
                    new_scope = scope.add_where(key)
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

def setup_yaml_parser(loader):
    reg_classes = [
        Where,
        Then,
        Value,
        Type,
        Steps,
        Label,
        Unknown,
        ScriptKeyword,
    ]
    for c in reg_classes:
        c.register_yaml(loader)
    yaml.add_constructor("!range", range_constructor, loader)
    yaml.add_representer(range, range_representer)

def get_scripts(file, loader) -> list[DexterScript]:
    with open(file, 'r') as r:
        lines = r.readlines()
    assert lines, "Read no valid lines?"
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
            if line.startswith('...'):
                new_script = DexterScript(yaml.load('\n'.join(curr_yaml_doc), loader), Scope(scope_file, []))
                new_script.opening_line = start_line
                new_script.closing_line = idx + 1
                scripts.append(new_script)
                curr_yaml_doc = []
    if curr_yaml_doc:
        new_script = DexterScript(yaml.load('\n'.join(curr_yaml_doc), loader), Scope(scope_file, []))
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
