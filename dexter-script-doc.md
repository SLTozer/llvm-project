# Dexter Scripts

Dexter scripts are a means of describing the state that a debugger will observe while running a program. Scripts are written in [YAML](https://yaml.org/), using a collection of data types defined by Dexter to describe different kinds of debugger state. We use nested maps with tagged complex keys to structure the test script:

```yaml
# Simple example script:
!where {file: main.cpp, function: foo}:
  !where {lines: !range [10, 12]}:
    !value x: 0
  !value y: [1, 2]
  !where {lines: 13}: !then continue
  ? !value z
```

- We consider the script to have a "tree" like structure, where we have a key which maps to a nested map; we treat the key as a "parent", and the entries in the nested map as the corresponding "children".
- The `!where` type is the main building block of test scripts, and is used to describe where and when Dexter checks debugger state and performs actions. The `file`, `function`, and `line` arguments all declare the source locations where the children of this `where` apply, meaning that any child of `!where { lines: 13 }` will only apply on line 13.
- The `!value` type is an "expect", meaning it describes state that we want Dexter to observe in the debugger and measure by comparing against a known result. Specifically, `!value` tests the value of a variable: `!value x: 0` means that we expect the value of the variable "x" to be 0. `!value y: [1, 2]` means that we expect value of the variable "y" to be first 1, and then 2.
- The `!then` type defines a debugger action that will be taken whenever it is in scope - in this case, following the surrounding `!where` entries, the `!then` is in scope only when we are at the location `main.cpp:foo:13`, at which point the debugger will `continue`.
- The entry `? !value z` is an "abstract" expect, meaning that we have not declared what we expect the value of "z" to be - in YAML syntax, this means that `!value z` maps to nothing/a null value. When abstract expects are present, any observed value will match, and if given an output directory Dexter will write the test script out to a new file with the missing expect values filled in.
- The `!range` type is simply a way to express a range of lines; `lines: !range [10, 12]` in a `!where` means that it will match lines 10, 11, or 12.

These are the basic ideas needed to interpret a script: we use YAML maps to structure our scripts, using `!where` to define where Dexter performs its tests, `!then` to perform debugger actions, and `!value` or other expects to define what values we are testing.

## Matching Expects

Each expect appears as a key, which in itself declares the debugger state we want to test, and which maps to the value(s) we expect to see in the debugger. When Dexter has finished debugging and starts evaluating the debugger output, it matches observed values with expected values according to the following rules:

- If the expected values are a sequence, Dexter will try to match each element in that sequence against each observed value.
    NB: Currently the order of sequence elements is ignored, but in future the orders between observed and expected values will be expected to match, where each expected value matches against the observed values in one or more contiguous steps.
- Each expected value may be either a string literal, a map, or a matcher type. Each is matched against an observed value differently:
    - String literals are directly compared to the string output from the debugger; only exactly equal strings will match.
    - Maps are used to destructure the expected/observed value; for example, `!value pair: { x: 0, y: 2 }` means that we expect the variable `pair` to have a member `x` with the value 0 and a member `y` with the value 2. For this to work, the debugger has to be able to destructure the data - this will not match against the string literal "{ x: 0, y: 2 }" (if you *want* to match that string, use quotes so that YAML interprets the expected value as a string rather than a map). For DAP-based debuggers, the `variables` request is used for this destructuring. Nested maps can be used to further destructure results, e.g. `!value circle: { centre: { x: 0, y: 2 }, radius: 4 }`.
    - Matches are Dexter-defined data types that use custom matching logic, allowing them to match against something other than a single static value. For example, the `!float` matcher can match against any float value within a defined range.
    - These types can be mixed and matched; it is possible to have a sequence of maps, to have a sequence of complete destructured values to match against. Dexter also intends to allow maps of sequences, allowing individual members of a variable to be matched independently, so that we do not need to declare every complete state of a variable, and can avoid being sensitive to reordered assignments to members. Sequences and maps can also contain matchers, so that if one member of a struct variable is a float, we can use a float matcher (or sequence of matchers!) for just that member.

## Matching Nested Wheres

Every step in the debugger will be matched against `!where` entries in the script, according to the following rules:
- The children of a `!where` entry will be evaluated iff the `!where` matches the current step.
- The innermost `!where` must match the top stackframe - `!where { function: foo }` will only match when stepping through `foo`, not through a function called from `foo`.
- For nested `!where` entries, a child `!where` cannot match any stack frame above the frame that its parent `!where` matched. This means that the nested Wheres `!where {function: foo}: !where {function: bar}: ...` will only match when `foo` has called `bar`, either directly or via an intermediate function (TODO: we could make this match *only* when `foo` has directly called `bar`, no strong principled reason yet to go either way).

## Generating scripts

When an expect is not mapped to a value, Dexter can fill-in the blanks from a baseline test case. By default, if Dexter sees any abstract expects, observes any results for those abstract expects, and is given a `--results-directory` argument, it will create a copy of the file containing the test script in the given results directory, with the script text replaced by a version with the abstract expects filled in. Everything before and after the script is copied exactly as-is; the script is serialized to YAML from the modified script object, which means that any formatting in the original script may be lost. The expectation for these generated scripts is that if you generate new expected values from running Dexter on a target program, and then run Dexter with the generated script on the same program, the scores for all generated expects should be perfect, as the expected values should exactly match. This is not always the case however, as some values vary from run to run.

TBD We wish to fix this problem by allowing Dexter to run multiple times, and make a best-effort with optional human-intervention to modify its matches, avoiding steps where values are unpredictable (e.g. uninitialized) and using matchers where possible to capture the full range of possible values.

## Script Type Reference

### Control

- `!where { file: str, function: list, lines: int, for_hit_count: int, conditions: dict[str, str] }`
  Appears as the key for a map entry, and all its child entries will only be evaluated when the conditions of the `where` hold. The combination of `file:function:lines` sets the scope of source locations where the children of the `!where` apply. The `for_hit_count` and `conditions` field dynamically constrain the `!where` scope by limiting the number of times it will be applied, or only applying while one or more conditions are true, respectively.
- `!then continue`
  Appears as a single value mapped to by a `!where`, defining a debugger action that will be taken whenever that `where` is in scope.

### Expects

All expect types appear as the key for a map entry, and their corresponding value (if any) is the expected value from the debugger that the observed value will be compared against.

- `!value <variable>`
  Expects the value of `<variable>`, accepting either a scalar or sequence of strings, maps, or match types as observed values, which will be directly compared against.
- `!then <variable>`
  Expects the type of `<variable>`, accepting either a scalar or sequence of strings as observed values, which will be directly compared against.
- `!value/all <scope>`
  Expects the value of all variables within the given `<scope>`, as per the DAP `scopes` feature. This can only currently appear as an abstract expect.

### Matchers

Matcher types can appear as expected values, where instead performing a direct string comparison between them and the value reported by the debugger, they use some form of custom matching logic, allowing them to match against more than one literal value.

- `!float { value: float, range: float }`
  Matches any float value `f` where `value - range <= f <= value + range`.
- `!address { name: str, offset: int }`
  Matches any pointer type. If multiple addresses with the same name are present, they are expected to all agree, meaning the observed value, minus the optionally provided `offset` value, must be the same for all such addresses.

### Utilities

There are a few utility classes used to provide syntactic sugar for script-writing; they only ever appear as arguments to other types.

- `!label <name: str>`
  Can be used as a substitute for a line number anywhere that a line number could be present. The label `!label foo` will be replaced with a line number from one of the source files being tested by Dexter where the text string `dex_label foo` is present.
- `!range [low: int, high: int]`
  Used to represent a range of lines, rather than specifying each line individually in a list. Specifies an inclusive range, i.e. `!range [10, 12]` represents the lines 10, 11, and 12.

