# DExTer (Debugging Experience Tester)

## Introduction

DExTer is a suite of tools used to evaluate the "User Debugging Experience". DExTer drives an external debugger, running on small test programs, and collects information on the behavior at each debugger step to provide quantitative values that indicate the quality of the debugging experience.

## Supported Debuggers

DExTer currently supports LLDB via its DAP interface.

The following command evaluates your environment, listing the available and compatible debuggers:

    dexter.py list-debuggers

## Dependencies
See: pyproject.toml

### Python 3.6

DExTer requires python version 3.6 or greater.

### pywin32 python package

This is required to access the DTE interface for the Visual Studio debuggers.

    <python-executable> -m pip install pywin32

## Running a test case

The following commands build fibonacci.cpp from the tests/nostdlib directory and run it in LLDB, reporting the debug experience heuristic. The first pair of commands build with no optimizations (-O0) and score 1.0000.  The second pair of commands build with optimizations (-O2) and score 0.2832 which suggests a worse debugging experience.

    clang -O0 -g tests/nostdlib/fibonacci.cpp -o tests/nostdlib/fibonacci/test
    dexter.py test --binary tests/nostdlib/fibonacci/test --debugger lldb -- tests/nostdlib/fibonacci/test.cpp

    clang -O2 -g tests/nostdlib/fibonacci/test.cpp -o tests/nostdlib/fibonacci/test
    dexter.py test --binary tests/nostdlib/fibonacci/test --debugger lldb -- tests/nostdlib/fibonacci/test.cpp

## An example test case

The following is an example Dexter test case:

    1.  void Fibonacci(int terms, int& total)
    2.  {
    3.     int first = 0;
    4.     int second = 1;
    5.     for (int i = 0; i < terms; ++i)
    6.     {
    7.         int next = first + second; // !dex_label start
    8.         total += first;
    9.         first = second;
    10.         second = next;            // !dex_label end
    11.     }
    12. }
    13.
    14. int main()
    15. {
    16.     int total = 0;
    17.     Fibonacci(5, total);
    18.     return total;
    19. }
    20.
    21. /*
    22. ---
    23. !where {lines: !range[!label start, !label end]}:
    24.   !value first: [0, 1, 2, 3, 5]
    25.   !value second: [1, 2, 3, 5]
    26.   !value total: [0, 1, 2, 4, 7]
    27    !value next: [1, 2, 3, 5, 8]
    28. !where {lines: 25}:
    29.   !value total: 7
    30. ...
    31. */

The script is a declaration of what state we expect to see in the debugger, using various "nodes" to define the test:
- The `!where` lines declare steps that we want the debugger to record
- The `!value` lines declare state that we expect to see during these steps.
- The labels, given by `!dex_label <name>` in the source code, and `!label <name>` in the script; the former assigns a name to the source line it appears on, and the latter references that name from in the script.

The script follows a hierarchical structure: the `!value` lines from lines 24-27 are nested under the `!where` on line 23, which means that from lines 7-10 Dexter will record the values of the 4 variables and compare the recorded values to the expected values (e.g. 0, 1, 2, 3, and 5 for `first`).

## Writing new test cases

Each test can be either embedded within the source file using comments or included as a separate file with the .dex extension. Dexter does not include support for building test cases, although if a Visual Studio Solution (.sln) is used as the test file, VS will build the program as part of launching a debugger session if it has not already been built.

# Planned Changes to Dexter

## Script Format

The script format is changing from a list of python commands to a structured YAML script. In the old model, Dexter would take a file as input and search that file for strings beginning with `Dex`, and interpreting them as Dexter "commands", which are python classes defined in Dexter. All the commands are evaluated, and each of them define some combination of instructions to Dexter while running the debugger, and some state that Dexter will evaluate to produce its final heuristic score. For example, `DexExpectWatchValue(expr, *values [,**from_line=1][,**to_line=Max])` tells Dexter to evaluate the expression `expr` while in the line range `[from_line, to_line]`, and expects the result to be equal to `values`. There are also commands that exist only for control flow, for example `DexFinishTest([expr, *values], **on_line[, **hit_count=0])`, which causes Dexter to end the debug session when all the provided conditions are met.

The primary reason Dexter is abandoning this approach is to better enable it to generate scripts; for this, a simple machine-writeable format is ideal. Although it would not be impossible to have Dexter generate the text for a Python program that runs a test, the solution would be much more convoluted than a straightforwardly serializable data structure. As a secondary reason, existing hand-written test scripts become harder to read and understand as they approach lengths suitable for benchmarking; switching to a data structure that also encodes the structure of the test is a bonus in usability.

The format that Dexter now uses is YAML, with a set of custom types and heavy use of complex keys. The structure of the script is a nested dict/map type, where most keys are objects and most values are dicts. For example:

```cpp
1: int iinvsqrt(int x) {
2:     int y = x * x;
3:     return 1/y;
4: }
```
```yaml
!where {function: iinvsqrt}:
    !value x: 42
    !and {lines: 3}:
      !value y: 0
      !type y: int
```

The Dexter test above shows the basic structure of a test script. We have a single key in the outermost dict, `!where {...}`, which defines some state of the debuggee program - in this case, when the current function is `iinvsqrt`. This `!where` key maps to another dict with two items. The first of these, `!value x: 42`, is an "expect", describing a piece of debugger output and it's expected value: we expect the variable `x` to have the value "42". This will only be evaluated and checked when the containing `!where` is active, meaning when we are in the function `iinvsqrt`. The `!and` key is similar to the `!where`, but it combines its state with the containing `!where`, so it is active when the function is `iinvqrt` and the current line is 3. Finally, the `!value y` and `!type y` entries are similar to the prior `!value x` entry, checking the value and type of `y` when the function is `iinvsqrt` and the line is 3.

The decision to use YAML over other formats is largely to support this model of using typed objects as keys to create a tree structure; it is technically possible to achieve this structure in other formats (e.g. JSON), but YAML was the only format I found that made it possible to write without a lot of boilerplate/verbosity, and that is well-supported by pre-existing tooling. It is entirely possible for Dexter to support other formats, either instead of or concurrent with YAML - the internal script representation does not depend on it, and the surface area of YAML interfacing (via `PyYaml`) has been kept deliberately small.

### Script Definitions

Each script is a tree of various types of "nodes":

- Structural Nodes - `[!where, !and]`: These are also generally referred to as `where` nodes throughout Dexter and this document. These nodes define some debugger state which can be "matched" against a stack frame; most commonly, this is a file+line number or function name. These nodes are never leaf nodes and are the only allowed "root" nodes, though they may be children of another structural node. The purpose of these nodes is to match against a stack frame for some steps in the debuggee program, such that the children of these nodes will be evaluated by Dexter in that frame for those steps.
- Expect Nodes: Defines some debugger state that the script wants to record, e.g. the value or type of a variable, and an expected value for that state. Expect nodes are always "leaf nodes" in that they have no child nodes, but they may refer to a complex expected value, e.g. a list of expected values, each of which may comprise a dict mapping field names to values.
- Execution Nodes: Also referred to as `then` nodes throughout Dexter and this document. Defines some debugger action that the script requests Dexter to execute when the execution node is in scope, such as instructing the debugger to `continue`. These are always leaf nodes.

The `!where` node is core to the structure of Dexter tests. Dexter will use `!where` to set breakpoints, trying to ensure that the debugger only stops and steps through code at which some `!where` is active. At the most basic level, `!where` defines some simple state, for example `!where {function: foo}` will match any stack frame which is a call of `foo`. When such a frame is the current frame of the program, we call this an "active" `!where`. These nodes can be nested, in two different ways:
- An `!and` node nested under a `!where` applies its conditions *in addition to* the conditions of the `!where`. For example, in the test `!where {function: foo}: { !and {lines: 10}: ...}`, the `!and` will be active only when the function is `foo` and the line number is `10`.
- A `!where` node nested under another `!where` node can only match in the stack frame above its parent, i.e. it corresponds to a function called during the first `!where`. For example, in the test `!where {function: foo}: { !where {function: bar}: ...}`, the inner `!where` will only be active when we are in function "bar" which was called directly by function "foo".

When we match `!where` or `!and` nodes against the current stack, we always do so from the bottom-up, and a single node cannot match against multiple frames at a single step. This means that if the call stack looks something like `[foo, bar, foo, bar]` while we have `!where {function: foo}: { !where {function: bar}: ...}`, then the outer `!where` will only match against the first call of `foo`, the inner `!where` will only match against the first call of `bar`, and therefore Dexter will not evaluate anything for the recursive calls of `foo` and `bar` (and in practice it would not set breakpoints for or step into them).

Within the structural nodes, there are two other types of nodes: expect and execution nodes. For these node types, we refer to them as being active when their parent structural node is active. Execution nodes are simple: they define some debugger action (e.g. `continue`) which will be executed whenever they are active. These are practically useful for skipping loops or long-running code that we have no interest in testing, though often this can also be achieved with the use of structural nodes. Expect nodes define some debugger output that we wish to measure, e.g. the value or type of a variable, and some expected output to compare the actual output against.

The two main types of expect node are `!value` and `!type`, which test the value and type of a variable respectively. `!value x: 10` states that the value of the variable `x` should be 10; whenever this node is active, Dexter will fetch and store the value of `x` from the debugger, and during the evaluation phase Dexter will check at each applicable step that `x` was equal to 10. Some of the complexities to this matching process are:

- It is possible to test multiple values: `!value x: [10, 20]` will test that the value of `x` is 10 at some point and 20 at another; Dexter currently does *not* test the order of these values.
- For more complex values, Dexter can test aggregate values: `!value point { x: 10, y: 20 }` tests that the variable `point` has two members, `x = 10` and `y = 20`. This disaggregation of `point` comes from the Debugger - similarly, the Debugger may support inspecting pointer variables to see their pointee values, e.g. `!value pointer: { "*": 10 }` for `int *pointer = new int(10)`.
- Some special "matcher" nodes can be used for non-deterministic values: `!float`, which can match float values with an error tolerance range, and `!address`, which matches pointer addresses whose values vary across runs but are consistent between variables within a given run:
    ```yaml
    !value f: !float { values: 3.14, range: 0.001 } # Matches any value in the range 3.139-3.141
    !value p1: !address p # First seen instance of p1 will be considered a match, and the address will be used for subsequent matches.
    !value p2: !address p # Matches iff the value of p2 is the same as the value of p1.
    ```
- For disaggregated values, it is possible to use the `!dex self` node to test the value of the aggresgate at the same time as its fields; this is mainly useful for `!type` checks, where we may be interested in testing the types of the fields of a struct as well as its members:
    ```yaml
    !type point:
        x: int
        y: int
        !dex self: Point<int>
    ```

All of these can be put together, allowing a test such as:

```yaml
!value pointer: !address point  # The value of "pointer" is some non-null address 'point'.
!value trace:   # The value of "trace" will be one of two expected aggregate values:
# The first expected value:
- from: 0x0000000000000000                        # trace.from is a nullptr
  distance: !float { values: 42.0, range: 0.01 }  # trace.distance is a float value in 42.0+-0.01
# The second expected value:
- from:                                           # trace.from has a complex expected value.
    "*":                                          # This describes the value of *(trace.from), which is presented in the debugger as if `trace.from` had a member named "*"
      x: 10                                       # trace.from->x == 10
      y: 20                                       # trace.from->y == 20
    !dex self: !address point                     # The actual value of trace.from is the non-null address 'point', i.e. the same address as the variable "pointer"
  distance: !float { values: 42.0, range: 0.01 }  # trace.distance is a float value in 42.0+-0.01
```

### Script Generation

Part of Dexter's new design is enabling the generation of expects for scripts. Currently, Dexter cannot generate structural or execution nodes, only expect nodes. There are two different ways to request generated values:

- An expect can be generated for a single variable by omitting an expected value for that variable. In order for the YAML to parse correctly, keys without mapped values require a `?` prefix, e.g. `!where {function: foo}: { ? value x }`. It is also  possible to use `value x: null`, those this isn't the preferred style of Dexter.
- An expect can be generated for all variables in a debugger-defined scope by using the "all" variant of an expect: `!value/all Locals` fetches the values of all variables in the "Locals" scope. The available scope names may vary across debuggers, but debuggers support a common set ("Locals", "Arguments", "Globals")

## Data Structures

Since Dexter's complexity is increased by these changes, we are also attempting to improve maintanability, such that Dexter is ultimately easier to work with than before. The basic goal of the refactoring is to consolidate most of Dexter's behaviour into a set of well-defined, documented, and debug-printable data structures. Dexter's various features can be summarized by the following top-level functions:

```
get_script: Path -> DexterScript
run_debugger: DexterScript, Debugger, Executable -> DextIR
evaluate: DexterScript, DextIR -> ScriptTraceMatch
get_metrics: DexterScript, ScriptTraceMatch -> Metrics
visualize: DexterScript, ScriptTraceMatch[, ScriptTraceMatch] -> VisualDexResult
```

A more detailed description of the various data structures follows:

### DextIR

Defined in `dex.dextIR.DextIR`.

This is the core data structure in Dexter, containing all of the observed state of a debugger session. It primarily stores the debugger output as a list of `StepIR`, which contain information taken at each step; this includes how we arrived at the step (e.g. step instruction or breakpoint) and a list of `FrameIR`, each of which contain all the observed information associated with a stack frame: source location, function, instruction address, and variable information recorded as `ValueIR` objects (see below). The `DextIR` object also contains some context information for the Dexter test, such as the executable, the debugger name + version, the version of Dexter that produced it, and the `DexterScript` (see below) that was used to produce it.

`DextIR` objects are produced when Dexter runs a debug session, i.e. from a `dexter test` command; they can also be serialized/deserialized via pickling, and each `dexter test` command will produce a `.dextIR` file containing the pickled object. The `DextIR` itself does not contain any evaluation of debugger state (e.g. metrics), but it contains all of the information used to evaluate or visualize the result of a Dexter run.

#### ValueIR

This class holds all the information observed regarding a variable/watch expression at a single point in the debugger, and deserves a detailed explanation since it is core to how Dexter evaluates results. This class contains:
- `expression: str` - The name of the variable or watch expression string, always a valid string.
- `value: str` - The value produced by the debugger for the expression, which will always be a string (as the debugger is displaying text). This may be `None` if the variable couldn't be evaluated.
- `type_name: str` - Similar to `value`, but for the type information; this may be `None`, but depending on the debugger there may be times when `value` is `None` but `type_name` isn't (e.g. when a variable has a valid debug entry but is optimized out).
- `error_string: str` - The error string produced by the debugger in place of a `value`, if the debugger failed to evaluate the variable.
- `could_evaluate: bool` + `is_optimized_away: bool` + `is_irretrievable: bool` - These 3 boolean variables track whether and why a variable could not be successfully evaluated.
- `sub_values: list[ValueIR]` - In most debuggers, variable/expression values will not always be a single scalar/string value; for example, the value of C/C++ `struct`s may be viewable in terms of their fields instead of compressing their entire state into a single (often truncated) string, or a pointer variable may allow a user to see the underlying pointee value. If the debugger produces such output, all the "sub-values" for the variable will be stored in this field; a sub-value may itself have sub-values.

### DexterScript

The DexterScript class defines a test script for Dexter. In memory, a script is a tree of `Node`s, which have the following broad kinds:
- Structural Nodes: Also referred to as `where` nodes throughout Dexter and this document. Defines some debugger state which can be "matched" against a particular stack frame, e.g. a line number or function name. These nodes are never leaf nodes and are the only allowed "root" nodes, though they may be children of another structural node, and they define the stack frame against which any of their children will be evaluated by Dexter.
- Expect Nodes: Defines some debugger state that the script wants to record, e.g. the value or type of a variable, and an expected value for that state. Expect nodes are always "leaf nodes" in that they have no child nodes, but they may refer to a complex expected value, e.g. a list of expected values, each of which may comprise a dict mapping field names to values.
- Execution Nodes: Also referred to as `then` nodes throughout Dexter and this document. Defines some debugger action that the script requests Dexter to execute when the execution node is in scope, such as instructing the debugger to `continue`. These are always leaf nodes.

A DexterScript can be serialized/deserialized from YAML, a human-operable format; they may also be pickled/unpickled as part of a `DextIR` object. A DexterScript instance can be produced from a file containing a YAML script using `get_script()`, and can be written to a string (containing line breaks) with `dexter_script.write_script()`.

### StepMatchResult / DebuggerStateMatch

**`StepMatchResult(script: DexterScript, step: StepIR, match_context: MatchContext)`**

The `StepMatchResult` class represents the result of matching the structural nodes of a `DexterScript` against a stack frame. This is a fundamental part of driving debugger sessions and evaluating results: the structural nodes determine where debugger actions are performed and variables or other state are evaluated. The input to a `StepMatchResult` is a `DexterScript`, a `StepIR` containing step information (but no variable information), and a `MatchContext` object. The `MatchContext` class tracks information from previous steps that is needed to match future steps, for example: some `!where` nodes declare `for_hit_count=n`, meaning they will only match the first `n` times that their declared state matches. The `MatchContext` tracks all such cross-step info, and is updated each time we create a new `StepMatchResult`. Because of this context, valid results will not always be produced from matching a single step to a script - for a fully correct result, each preceding step must also be matched in-order (even if their results are not being used) with a shared `MatchContext`.

The match result contains a dict mapping `where` nodes to the frame index that they matched to if any. For the purposes of efficient debugger driving, it also contains two sets of `where` nodes: those that are "early", meaning they match the current frame except for their `for_hit_count`, and those that are "almost", meaning we expect them to match at some point during the current call but they do not match yet (e.g. they specify a line range or condition that has not yet been met). Finally, for convenience it also stores the set of expect/execution nodes belonging to any `where` that matches the current frame (frame index = 0), as these are the nodes that we will be measuring/executing at the current step.

Results are produced by `StepMatchResult(script: DexterScript, step: StepIR, match_context: MatchContext)` -> Produces 

### ExpectMatchResult / DebuggerOutputMatch

**`ComplexMatchResult(value: ValueIR, expected: Any, step_index: int, is_value: bool, context: EvaluationContext)`** / **VariableMatchResult**
**`ListMatchResult(values: list[int], expected: list[int], step_index: int)`** / **SteppingMatchResult** 

The `ExpectMatchResult` class represents the result of matching an expect node and its expected value(s) against a debugger step. This abstract class is actually comprised of two quite different classes:
- `ComplexMatchResult` is used for variable expects, and produces a potentially "complex" (non-scalar) result. In the simple case, this simply matches the expected string against the debugger-reported result; when the expect is complex however, e.g. we expect values for each of the fields of a `struct` variable, the `ComplexMatchResult` disaggregates the result into `Submatch`es (which may themselves contain `Submatch`es), and produces a final "match distance". For a result that matches exactly, distance=0; for a result that does not match at all, distance=1; for a result that matches some fields and not others, the distance is a float value equal to the average distance of its immediate children. 
- `ListMatchResult` is used for stepping expects, where it matches the list of all line numbers seen up to a given step with the list of expected steps. This differs from the `ComplexMatchResult`, in which each match is (mostly) independent from each other match; the order and repetition counts of lines are compared as well as the actual values.

Creating an `ExpectMatchResult` also requires a context object, the `ExpectMatchContext`. Although expect node matches are mostly independent, there can exist interdependencies via the `!address` type. In order to meaningfully test address values, scripts may specify abstract address names, which will be resolved to concrete addresses during evaluation.

The mapping of name->address is consistent across expects in a script, and thus requires context. The order of evaluation of these address labels is firstly step order (earlier steps will assign address values before later steps), then in top-to-bottom script order (within a single step, address names that appear earlier in the script text will be assigned first).

### ScriptTraceMatch / DebuggerStepMatch

**`ScriptTraceMatch(script: DexterScript, step: StepIR, context: TraceMatchContext)`**

The `ScriptTraceMatch` class matches a `DexterScript` and a `DextIR` trace as-of a particular step. This class contains a `StepMatchResult`, and just as with that class the match result for step `N` can only be obtained after getting the results for steps `1..N-1` using a shared context object of type `TraceMatchContext`. Similarly, this class contains `ExpectMatchResult`s for every expect node, including both the results found in the current step and results in all prior steps. From this, a `ScriptTraceMatch` can be used to visualize the result/output of a Dexter test, and to produce the metrics that Dexter outputs.

If you only care about the final output of a Dexter test, you can get it from:
```python
def get_result(dext_ir: DextIR):
    script = dext_ir.script
    context = TraceMatchContext()
    for step in dext_ir.steps:
        result = ScriptTraceMatch(script, step, context)
    return result
```

- `ScriptTraceMatch(script: DexterScript, step: StepIR, context: TraceMatchContext)`

### VisualDexResult (experimental, currently mid-update)

The `VisualDexResult` class is a data structure used for visualizing Dexter results in a UI by comparing the accumulated debugger output up-to a given step to the corresponding Dexter script. The structure has some number of named "columns", e.g. `["Expected", "Actual"]`, and a tree where each node (`VisualDexNode`) contains a tagged string for each column. The tags for each string are used for formatting the output; for example, strings with the "correct" tag are coloured green, those with the "incorrect" tag are coloured red, and those with both (e.g. a complex result which has some correct children and some incorrect children) are yellow. The children of a node are nodes that are "contained" under that node, e.g. the `Expect` nodes under a `Where` node, or the expected values of an `Expect` node. By default these correspond with indent levels, but they can also be used for filtering - for example, if displaying the `VisualDexResult` for a step, a user may want to not print script nodes that are not in-scope at the current step; this can be done by skipping the rendering of the children of `Where` nodes with the "inactive" tag.

There are also some nodes that contain no strings, but are used for structural purposes where a set of nodes are grouped together but do not have a heading; this happens for lists of aggregates. Typically, these won't be rendered normally, but may still be used either to filter nodes or to modify subsequent lines.

Most of the time, each node represents the same piece of information from each of its contexts; for example, `!expect foo: 2` as the expected value, and `!expect foo: 0` as the actual value. For complex expected values, multiple nodes will be used, for example we would use 4 nodes for the following:
```python
("!expect point:", "!expect point:")    # Expected + Actual
  (None, None)                          # Empty node used to group the fields for a single expected value/result.
    ("x: 5", "x: 5")                    # Expected + Actual result
    ("y: 10", "y: 0")                   # ^
```

But in some cases, there will be a mismatch between the number of items to display on each side, e.g. if we expect only a single value for a variable but see multiple different values while debugging. In these cases, we try to construct nodes such that "matching" nodes are aligned, mismatched nodes may overlap, and missing nodes are represented by `None` (not empty strings). For an example, suppose we have the following expected/actual values for the variable `point` across two different runs of a test:
```
Expected: [{x: 5, y: 10}, {x: 10, y: 20}]
Actual 1: [{x: 5, y: 0}, {x: 0, y: 5}, {x: 10, y: 20}]
Actual 2: [{x: 5, y: 0}, <Optimized out>, {x: 10, y: 20}]
```

If we wanted to visualize these, showing us how the script and the two expected results compare, then we would produce the following tree:
```python
("!expect point:", "!expect point:", "!expect point:") # Expected, Actual 1, Actual 2
  (None, None, None)                    # Empty node used to group the fields for a single expected value/result.
    ("x: 5", "x: 5", "x: 5")            # Expected + Actual 1 + Actual 2 results
    ("y: 10", "y: 0", "y: 0")           # ^
  (None, None, None)                    # Empty node used to group the fields for the next expected value/result.
    (None, "x: 0", "<Optimized out>")   # No expected result, mismatched actual results.
    (None, "y: 5", None)                # No expected result, no further output for Actual 2, remaining output for Actual 1.
  (None, None, None)                    # Empty node for next results.
    ("x: 10", "x: 10", "x: 10")         # Matching Expected + Actual 1 + Actual 2 results
    ("y: 20", "y: 20", "y: 20")         # ^
```

This could then be rendered in a terminal side-by-side as:
```
Expected          | Actual 1          | Actual 2
--------          | --------          | --------
!expect point:    | !expect point:    | !expect point:
  - x: 5          |   - x: 5          |   - x: 5
    y: 10         |     y: 0          |     y: 0
                  |   - x: 0          |   - <Optimized out>
                  |     y: 5          |
  - x: 10         |   - x: 10         |   - x: 10
    y: 20         |     y: 20         |     y: 20
```

