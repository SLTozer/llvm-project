
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


from collections import namedtuple
import pprint
import yaml
from enum import Enum

# from dex.dextIR.StepIR import StepIR
class StepIR:
    pass


class TraceStep:
    def __init__(self):
        self.file: str | None = None
        self.function: list[str] | str | None = None
        self.line: int | None = None
        self.conditions: dict = {}
        self.watches: Watch = None

class State:
    pass

## Directly YAML-related classes.

# One or more instances of this class define a range of steps in a debugging session. Any expects in the script within
# scope of a "Where" will only be evaluated for the steps where the Where applies.
class Where:
    def __init__(self, attributes: dict):
        self.file: str | None = attributes.get("file")
        self.function: list[str] | str | None = attributes.get("function")
        self.lines: int | tuple[int, int] | range | None = attributes.get("lines")
        self.conditions: dict = attributes.get("conditions")

    def __repr__(self):
        elts = []
        if self.file:
            elts.append(f"file={self.file}")
        if self.function:
            elts.append(f"fn={self.function}")
        if self.lines:
            elts.append(f"lines={str(self.lines)}")
        return "Where(" + ", ".join(elts) + ")"


    def constructor(loader, node):
        return Where(loader.construct_mapping(node))

    def representer(dumper, data):
        mapping = {}
        if data.file:
            mapping["file"] = data.file
        if data.function:
            mapping["fn"] = data.function
        if data.lines:
            mapping["lines"] = str(data.lines)
        return dumper.represent_scalar('!where', mapping)

    def register_yaml(loader):
        yaml.add_constructor("!where", Where.constructor, loader)
        yaml.add_representer(Where, Where.representer)

    def get_lines(self) -> list[int]:
        if not self.lines:
            return []
        if isinstance(self.lines, int):
            return [self.lines]
        lines = []
        for line in self.lines:
            lines.append(line)
        return lines

class Scope:
    def __init__(self, file: str, labels: dict, fn: str | None = None, lines: int | range | list | None = None):
        self.file = file
        self.labels = labels
        self.fn = fn
        self.lines = lines

    def as_tuple(self):
        return (
            self.file,
            self.fn,
            tuple(self.get_lines())
        )


    # Returns a new Scope resulting from applying the new Where to this scope.
    # Note that the 'Where' does not need to be contained within the current scope; for example, if 'where' is in a
    # different file to this scope, we take that as the new file and invalidate any existing fn/line info since it no
    # longer applies to the new scope.
    def add_where(self, where: Where):
        scope_file = self.file
        scope_labels = self.labels
        scope_fn = self.fn
        scope_lines = self.lines
        if where.file:
            scope_file = where.file
            scope_fn = None
            scope_lines = None
        if where.function:
            scope_fn = where.function
            scope_lines = None
        if where.lines:
            scope_lines = where.lines
        return Scope(scope_file, scope_labels, scope_fn, scope_lines)

    def get_lines(self):
        # This should use self.labels to resolve "lines" to something concrete, when we have proper label support.
        if not self.lines:
            return []
        if isinstance(self.lines, int):
            return [self.lines]
        return self.lines


# Represents generic macros in the YAML script format, which take no arguments and expand out to ; they are represented here by
# just their name, e.g. !locals -> ScriptKeyword("locals").
class ScriptKeyword:
    def __init__(self, keyword: str):
        self.keyword = keyword

    def keywords():
        return ["locals", "params"]

    def get_constructor(keyword: str):
        return lambda loader, node: ScriptKeyword(keyword)

    def representer(dumper, data):
        return dumper.represent_scalar(f'!{data.keyword}', None)

    def register_yaml(loader):
        for keyword in ScriptKeyword.keywords():
            yaml.add_constructor(f"!{keyword}", ScriptKeyword.get_constructor(keyword), loader)
        yaml.add_representer(ScriptKeyword, ScriptKeyword.representer)

StepExpectInfo = namedtuple("StepExpectInfo", "expression, path, frame_idx, line_range")

# An expectation of some debugger state that will be compared to actual observed debugger state and generate one or more
# metrics as a measurement of the difference.
# Expects are largely independent, but may have some limited cross-over in the case of metavariables (such as !addr).
class Expect:
    def __init__(self):
        pass

    # For a list of steps in which this expectation is in-scope, returns all the information required to evaluate it.
    def get_actual_value(self, steps: list[StepIR]):
        raise NotImplementedError()

    def evaluate(self, expected, actual):
        # Implemented per subclass.
        raise NotImplementedError()

    def get_watched_exprs(self) -> list[str]:
        raise NotImplementedError()

class Value(Expect):
    def __init__(self, variable_name: str):
        self.variable_name = variable_name

    def get_watched_exprs(self) -> list[str]:
        return [self.variable_name]

    def __repr__(self):
        return f"Value({self.variable_name})"

    def constructor(loader, node):
        return Value(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar('!value', data.variable_name)

    def register_yaml(loader):
        yaml.add_constructor("!value", Value.constructor, loader)
        yaml.add_representer(Value, Value.representer)

class Type(Expect):
    def __init__(self, variable_name: str):
        self.variable_name = variable_name

    def get_watched_exprs(self) -> list[str]:
        return [self.variable_name]

    def __repr__(self):
        return f"Type({self.variable_name})"

    def constructor(loader, node):
        return Type(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar('!type', data.variable_name)

    def register_yaml(loader):
        yaml.add_constructor("!type", Type.constructor, loader)
        yaml.add_representer(Type, Type.representer)

class Steps(Expect):
    def __init__(self):
        pass

    def get_watched_exprs(self) -> list[str]:
        return []

    def __repr__(self):
        return f"Steps"

    def constructor(loader, node):
        return Steps()

    def representer(dumper, data):
        return dumper.represent_scalar('!steps', None)

    def register_yaml(loader):
        yaml.add_constructor("!steps", Steps.constructor, loader)
        yaml.add_representer(Steps, Steps.representer)

class Label:
    def __init__(self, name: str):
        self.name = name

    def constructor(loader, node):
        return Label(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar('!label', data.name)

    def register_yaml(loader):
        yaml.add_constructor("!label", Label.constructor, loader)
        yaml.add_representer(Label, Label.representer)

class Unknown:
    def __init__(self):
        self.index = None

    def constructor(loader, node):
        return Unknown()

    def representer(dumper, data):
        return dumper.represent_scalar('!unknown', None)

    def register_yaml(loader):
        yaml.add_constructor("!unknown", Unknown.constructor, loader)
        yaml.add_representer(Unknown, Unknown.representer)

def range_constructor(loader, node):
    range_seq = loader.construct_sequence(node)
    if len(range_seq) != 2 or not all([isinstance(elt, int) for elt in range_seq]):
        raise DexterScriptError(range_seq, "!range must have exactly 2 int elements")
    return range(range_seq[0], range_seq[1])

def range_representer(dumper, data: range):
    return dumper.represent_sequence('!range', data.start, data.stop)

class DexterScriptError(Exception):
    pass

class DexterScript:
    def __init__(self, script_obj, scope: Scope):
        self.script_obj = script_obj
        self.root_scope = scope

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
                    if not isinstance(value, dict) and not isinstance(value, list):
                        raise DexterScriptError(script)
                    validate_subscript(value)
                elif isinstance(key, Expect):
                    # TODO: Fully verify the contents of the expect.
                    if isinstance(value, dict):
                        raise DexterScriptError(script)
                else:
                    raise DexterScriptError(key)

    def _visit_script(self, script, scope: Scope, visit_where=None, visit_expect=None):
        if isinstance(script, list):
            for item in script:
                self._visit_script(item, scope, visit_where, visit_expect)
        elif isinstance(script, dict):
            for key, value in script.items():
                if isinstance(key, Where):
                    if visit_where:
                        visit_where(key, scope)
                    new_scope = scope.add_where(key)
                    self._visit_script(value, new_scope, visit_where, visit_expect)
                elif isinstance(key, Expect):
                    if visit_expect:
                        visit_expect(key, value, scope)
                else:
                    # If we have `where {...}: {scalar: value}`, it's not clear what that should mean, but we visit
                    # 'value' here as a default since we'll probably use that at some point.
                    self._visit_script(value, scope, visit_where, visit_expect)
        else:
            # If we have `where {...}: scalar`, it's not clear what that should mean, but we visit
            # 'value' here as a default since we'll probably use that at some point.
            pass

    def visit_script(self, visit_where=None, visit_expect=None):
        self._visit_script(self.script_obj, self.root_scope, visit_where, visit_expect)

    def get_breakpoint_locations(self):
        bp_locs = []
        def add_bp_locs(where: Where, scope: Scope):
            scope = scope.add_where(where)
            # 'where' can set either:
            # - Source breakpoints over a set of lines.
            # - A single function breakpoint.
            # - No breakpoints at all, if it is only defining a file scope.
            if where.lines:
                assert scope.file, "Can't set line breakpoints without a file scope"
                for line in where.get_lines():
                    bp_locs.append(("source", scope.file, line))
            elif where.function:
                if scope.file:
                    bp_locs.append(("function", scope.file, scope.fn))
                else:
                    bp_locs.append(("function", scope.fn))

        self.visit_script(visit_where=add_bp_locs)
        return bp_locs

    # Alternative version of the above fn that only gets breakpoints directly required by expects.
    def get_breakpoint_locations2(self):
        visited_scopes = set()
        bp_locs = []
        def add_bp_locs(expect: Expect, value, scope: Scope):
            if scope.as_tuple() in visited_scopes:
                return
            visited_scopes.add(scope.as_tuple())
            # The current scope should set either:
            # - Source breakpoints over a set of lines.
            # - A single function breakpoint.
            if scope.lines:
                assert scope.file, "Can't set line breakpoints without a file scope"
                for line in scope.get_lines():
                    bp_locs.append(("source", scope.file, line))
            elif scope.fn:
                if scope.file:
                    bp_locs.append(("function", scope.file, scope.fn))
                else:
                    bp_locs.append(("function", scope.fn))
            else:
                raise DexterScriptError(expect, "Expect set without a valid function or line scope")

        self.visit_script(visit_expect=add_bp_locs)
        return bp_locs

    def get_watches(self):
        watches = []
        def get_expect_watches(expect: Expect, values, scope: Scope):
            exprs = expect.get_watched_exprs()
            for expr in exprs:
                watches.append(StepExpectInfo(expr, scope.file, 0, scope.lines))
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
            else:
                item_results = []
                for key, value in script.items():
                    item_result = indent + "  " + str(key) + ": "
                    if isinstance(key, Where):
                        item_result += "\n" + print_subscript(value, depth + 1)
                    else:
                        item_result += str(value)
                    item_results.append(item_result)
                result = ",\n".join(item_results)
            return result
        print(print_subscript(self.script_obj, 0))

    def print_info(self):
        try:
            self.validate()
            print("Script:")
            self.print()
            print("Breakpoints:")
            for bp in self.get_breakpoint_locations2():
                print(f"  {bp}")
            print("Watches:")
            for watch in self.get_watches():
                print(f"  {watch}")
        except DexterScriptError as e:
            print(f"Found script error: {e}")

class ScriptVisitor:
    def __init__(self, visit_where=None, visit_expect=None):
        self.visit_where = visit_where
        self.visit_expect = visit_expect

    def visit(self, script, where_scopes=None):
        if where_scopes is None:
            where_scopes = []

        if isinstance(script, list):
            for item in script:
                self.visit(item, where_scopes)
        elif isinstance(script, dict):
            for key, value in script.items():
                if isinstance(key, Where):
                    if self.visit_where:
                        self.visit_where(key, where_scopes)
                    new_parents = where_scopes + [key]
                    self.visit(value, new_parents)
                elif isinstance(key, Expect):
                    if self.visit_expect:
                        self.visit_expect(key, value, where_scopes)
                else:
                    self.visit(value, where_scopes)
        else:
            # Other macros may be present here, ignore them for now however.
            pass


# Takes as an argument a YAML document representing a dexter test, and returns the test script object resulting from
# parsing it.
def parse_test(contents: str) -> DexterScript:
    return DexterScript(yaml.load(contents, yaml.CLoader), Scope(__file__, []))

def setup_yaml_parser(loader):
    reg_classes = [
        Where,
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

old_test_script = """---
!where {file: "Bullet-2.76/Demos/Benchmarks/main.cpp", function: main}:
    !where {lines: 88}: {!value d: 0}
    !where {file: "Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp", function: btAlignedAllocInternal}:
        !where {lines: !range [165, 173]}:
            !value gNumAlignedAllocs: [0, 1, 2]
            !where {lines: 173}:
                !value alignment: 16
                !value size: 360
            !steps : [165, 166, 167, 168, 169, 170, 171, 172, 173]
"""
test_script = """---
!where {lines: !range [22, 23]}:
  !type m_member: [int, double]
!where {lines: !range [27, 29]}:
  !type to_double: [const int &, const double &]
!where {lines: !range [37, 44]}:
  !type myInt                   : Doubled<int>
  !type myDouble                : Doubled<double>
  !type staticallyDoubledInt    : int...
  !type staticallyDoubledDouble : double
...
"""

print_script_source_file = False

def get_scripts(file, loader) -> list[DexterScript]:
    with open(file, 'r') as r:
        lines = r.read().splitlines()
    assert lines, "Read no valid lines?"
    scope_file = str(file)
    scripts = []
    curr_yaml_doc = []
    for idx, line in enumerate(lines):
        if print_script_source_file:
            print(f"{str(idx).rjust(3)}: {line}")
        if line == '---':
            curr_yaml_doc.append(line)
        elif curr_yaml_doc:
            curr_yaml_doc.append(line)
            # We expect yaml docs to end with '...'
            if line == '...':
                scripts.append(DexterScript(yaml.load('\n'.join(curr_yaml_doc), loader), Scope(scope_file, [])))
                curr_yaml_doc = []
    if curr_yaml_doc:
        scripts.append(DexterScript(yaml.load('\n'.join(curr_yaml_doc), loader), Scope(scope_file, [])))
    return scripts

setup_yaml_parser(yaml.CLoader)
dex_scripts = get_scripts("/home/gbtozers/dev/upstream-llvm/cross-project-tests/debuginfo-tests/dexter/feature_tests/commands/perfect/expect_watch_value.cpp", yaml.CLoader)
for s in dex_scripts:
    s.print_info()

class TraceTimes:
    def __init__(self, min: int | None = 1, max: int | None = 1):
        self.min = min
        self.max = max

    def Once():
        return TraceTimes()

    def OnceOrMore():
        return TraceTimes(1, None)

    def __str__(self):
        if self.min == 1 and self.max == 1:
            return ""
        if self.min is None or self.min <= 0:
            if self.max is None:
                return "*"
            return "{0-" + self.max + "}"
        if self.max is None:
            return "{" + self.min + "+}"
        return "{" + self.min + "-" + self.max + "}"

class ReqTrace:
    pass

class ReqTraceStep(ReqTrace):
    def __init__(self, depth: int | None = None, file: str | None = None, function: str | None = None, line: int | None = None, times: TraceTimes = TraceTimes()):
        self.depth = depth
        self.file = file
        self.function = function
        self.line = line
        self.times = times

class ReqTraceSet(ReqTrace):
    def __init__(self, traces: set[ReqTrace] = {}):
        self.times = 1
        self.traces = traces

class ReqTraceList(ReqTrace):
    def __init__(self, traces: list[ReqTrace]):
        self.times = 1
        self.traces = traces

def get_req_trace_from_script(script: DexterScript):
    def traverse_script(subscript: list | dict):
        if isinstance(subscript, list):
            pass
        pass
    return traverse_script(script)

class RecordedTraceStep:
    def __init__(self, depth: int, file: str, function: str, line: int):
        self.depth = depth
        self.file = file
        self.function = function
        self.line = line

# ScriptPattern(Attributes(File: 'Bullet-2.76/Demos/Benchmarks/main.cpp'), Subpatterns = [
#     ScriptPattern(Attributes(Lines=88, Conditions={HitCount=1}), Watches(
#         Variables=[Variable(Name='d')]
#     )
#     ScriptPattern(Attributes(File: 'Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp'), Subpatterns = [
#         ScriptPattern(Attributes(Function='foo'), Watches=[
#             Variables=[Variable(Local=true)]])
#         ScriptPattern(Subpatterns = {
#             ScriptPattern(Attributes(Lines=165..173, Conditions={HitCount=3}), Watches = [
#                 Locals
#                 Params
#             ]),
#             ScriptPattern(Attributes(Lines=173), Watches = [
#                 Var 'alignment': 16
#                 Var 'size': 360
#             ])
#         })
#         ScriptPattern(Attributes('Bullet-2.76/src/LinearMath/btAlignedObjectArray.h', Lines=78, Conditions={HitCount=1}), Watches=[
#             Variables=[Variable(Expr='this->m_size', Values=[0])]
#     ])

#### Flattened state

# [
#   ('Bullet-2.76/Demos/Benchmarks/main.cpp:88', times=1, 'd'),
#   {
#     ('Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp:165', times=3, 'locals', 'params'),
#     ('Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp:166', times=3, 'locals', 'params'),
#     ('Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp:167', times=3, 'locals', 'params'),
#     ('Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp:168', times=3, 'locals', 'params'),
#     ('Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp:169', times=3, 'locals', 'params'),
#     ('Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp:170', times=3, 'locals', 'params'),
#     ('Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp:171', times=3, 'locals', 'params'),
#     ('Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp:172', times=3, 'locals', 'params'),
#     ('Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp:173', times=3, 'locals', 'params'),
#     ('Bullet-2.76/src/LinearMath/btAlignedAllocator.cpp:173', 'alignment', 'size'),
#   },
#   ('Bullet-2.76/src/LinearMath/btAlignedObjectArray.h:78', times=1),
# ]