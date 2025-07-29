
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



class TraceStep:
    def __init__(self):
        self.file: str | None = None
        self.function: list[str] | str | None = None
        self.line: int | None = None
        self.conditions: dict = {}
        self.watches: Watch = None

class State:
    pass

# A single set of declared attributes.
class Attributes:
    def __init__(self):
        # Attributes ordered from least to most specific, i.e. we try to evaluate each present attribute from top to
        # bottom.
        self.file: str | None = None
        self.function: list[str] | str | None = None
        self.lines: int | tuple[int, int] | range[int] | None = None
        self.conditions: dict = {}

class VariableWatch:
    def __init__(self):
        pass

class StepWatch:
    def __init__(self):
        self.steps = list[int | range[int]]

# Defines a set of expected variable values and stepping behaviour; there is no cross-ordering between variables, or
# between variables and steps; a set of steps is unordered ("we just expect to see all of these"), a list is ordered.
class Watch:
    def __init__(self):
        self.variables: set[VariableWatch] = []
        self.steps: list[int] | set[int] = []

class Command:
    def __init__(self, type: str):
        self.type: str = type

class TriggerInputCommand(Command):
    def __init__(self, input):
        self.input = input
        super().__init__("TriggerInput")

class ScriptPattern:
    def __init__(self):
        self.attributes: Attributes = Attributes()
        # Contains either subpatterns, or just watches - cannot contain both at once.
        # A list of watches requests that they appear in order, while a set has no ordering.
        self.subpatterns: list[ScriptPattern] | set[ScriptPattern] | None = None
        self.watches: list[Watch] | None = None

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