
import yaml
from dex.dextIR.StepIR import StepIR
from dex.dextIR.ValueIR import ValueIR
from dex.test_script.DataTypes import Metric, ScalarMetric, FractionMetric
import difflib

class Where:
    """"One or more instances of this class define a range of steps in a debugging session. Any expects in the script
    within scope of a "Where" will only be evaluated for the steps where the Where applies.
    """
    def __init__(self, attributes: dict):
        self.file: str | None = attributes.get("file")
        self.function: list[str] | str | None = attributes.get("function")
        self.lines: int | tuple[int, int] | range | None = attributes.get("lines")
        self.after_hits: int | None = attributes.get("after_hits")
        self.conditions: dict = attributes.get("conditions")
        assert self.function or self.lines or not self.after_hits, "Can't have after_hits without also having lines or a function"

    def __repr__(self):
        elts = []
        if self.file:
            elts.append(f"file={self.file}")
        if self.function:
            elts.append(f"fn={self.function}")
        if self.lines:
            elts.append(f"lines={str(self.lines)}")
        if self.after_hits:
            elts.append(f"after_hits={str(self.after_hits)}")
        return "Where(" + ", ".join(elts) + ")"


    def constructor(loader, node):
        return Where(loader.construct_mapping(node))

    def representer(dumper: yaml.Dumper, data):
        mapping = {}
        if data.file:
            mapping["file"] = data.file
        if data.function:
            mapping["fn"] = data.function
        if data.lines:
            mapping["lines"] = data.lines
        if data.after_hits:
            mapping["after_hits"] = str(data.after_hits)
        return dumper.represent_mapping('!where', mapping, flow_style=True)

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

class Then:
    """Used to perform actions, such as finishing the test or running a command. Will trigger when it is first in-scope
    for a step, so a typical usage pattern is to map to it directly from a "Where", e.g.
    `!where {line: 4, after_hits: 2}: !then finish`.
    """
    def __init__(self, command: str):
        self.command = command

    def is_valid(self) -> bool:
        return self.command == "finish"

    def __repr__(self):
        return f"Then({self.command})"

    def constructor(loader, node):
        return Then(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar('!then', data.command)

    def register_yaml(loader):
        yaml.add_constructor("!then", Then.constructor, loader)
        yaml.add_representer(Then, Then.representer)

class Scope:
    def __init__(self, file: str, labels: dict, fn: str | None = None, lines: int | range | list | None = None,
                 conditions: dict | None = None, after_hits: int | None = None):
        self.file = file
        self.labels = labels
        self.fn = fn
        self.lines = lines
        self.conditions = conditions
        self.after_hits = after_hits

    def empty_scope():
        return Scope(None, dict())

    def as_tuple(self):
        return (
            self.file,
            self.fn,
            tuple(self.get_lines()),
            self.conditions,
            self.after_hits,
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
        scope_conditions = self.conditions
        scope_after_hits = self.after_hits
        if where.file:
            scope_file = where.file
            scope_fn = None
            scope_lines = None
            scope_after_hits = None
        if where.function:
            scope_fn = where.function
            scope_lines = None
            scope_after_hits = None
            scope_conditions = None
        if where.lines:
            scope_lines = where.lines
            scope_after_hits = None
            scope_conditions = None
        if where.conditions:
            scope_conditions = where.conditions
        if where.after_hits:
            scope_after_hits = where.after_hits
        return Scope(scope_file, scope_labels, scope_fn, scope_lines, scope_conditions, scope_after_hits)

    def as_where(self) -> Where:
        attributes = {
            "file": self.file,
            "function": self.fn,
            "lines": self.lines,
            "conditions": self.conditions,
            "after_hits": self.after_hits,
        }
        return Where({k: v for k, v in attributes if v is not None})

    def get_lines(self):
        # This should use self.labels to resolve "lines" to something concrete, when we have proper label support.
        if not self.lines:
            return []
        if isinstance(self.lines, int):
            return [self.lines]
        return self.lines
    
    def get_line_range(self):
        if not self.lines:
            return None
        if isinstance(self.lines, int):
            return range(self.lines, self.lines + 1)
        # FIXME: For non-contiguous ranges this is incorrect, as is returning a range here at all - fix it later.
        if isinstance(self.lines, list):
            return range(self.lines[0], self.lines[-1] + 1)
        assert isinstance(self.lines, range)
        return self.lines

    # Awkward design to match current Dexter interface.
    def get_single_condition(self):
        if not self.conditions or len(self.conditions) != 1:
            return (None, None)
        return (self.conditions.keys()[0], self.conditions.values()[0])

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


# An expectation of some debugger state that will be compared to actual observed debugger state and generate one or more
# metrics as a measurement of the difference.
# Expects are largely independent, but may have some limited cross-over in the case of metavariables (such as !addr).
class Expect:
    def __init__(self):
        pass

    # For a list of steps in which this expectation is in-scope, returns all the information required to evaluate it.
    def get_actual_value(self, steps: list[StepIR]):
        raise NotImplementedError()

    # Similar to `get_actual_value`, but returns a value suitable for serializing directly to YAML instead of being
    # usable for evaluation, for the purposes of substituting unknown values.
    def get_unknown_substitute_value(self, steps: list[StepIR]):
        raise NotImplementedError()

    def evaluate(self, expected, actual) -> dict[str, Metric]:
        raise NotImplementedError()

    def get_watched_exprs(self) -> list[str]:
        raise NotImplementedError()

class Result:
    def __init__(self, result: str, is_error: bool = False):
        self.result = result if not is_error else None
        self.error = result if is_error else None

    def __repr__(self):
        if self.result is not None:
            return str(self.result)
        return f"<{self.error}>"

    def __eq__(self, other):
        return (self.result, self.error) == (other.result, other.error)

    def from_value_ir(value: ValueIR):
        if value.error_string is not None:
            return Result(value.error_string, True)
        if value.value is not None:
            return Result(value.value)
        if not value.could_evaluate:
            return Result("could not evaluate", True)
        if value.is_irretrievable:
            return Result("could not retrieve", True)
        if value.is_optimized_away:
            return Result("optimized out", True)
        return Result("unknown error", True)

class Value(Expect):
    def __init__(self, variable_name: str):
        self.variable_name = variable_name

    def get_actual_value(self, steps: list[StepIR]) -> list[ValueIR]:
        values = []
        for step in steps:
            values.append(step.program_state.frames[0].watches[self.variable_name])
        return values

    def get_unknown_substitute_value(self, steps: list[StepIR]):
        # If we observed no values at all, something has gone wrong.
        if not steps:
            return None
        values = []
        for step in steps:
            step_result: ValueIR = step.program_state.frames[0].watches[self.variable_name]
            # If we could not evaluate this variable, we have failed to find a substitute.
            if not step_result.value:
                return None
            values.append(step_result.value)
        # Prefer a scalar result if possible!
        if len(values) == 1:
            values = values[0]
        return values

    def evaluate(self, expected, actual: list[ValueIR]) -> dict[str, Metric]:
        # Cannot get meaningful metrics from a wildcard input.
        if isinstance(expected, Unknown):
            return {}
        if not isinstance(expected, list):
            expected = [expected]
        expected = [str(e) for e in expected]

        correct_steps = len([a for a in actual if a.value in expected])
        incorrect_steps = len([a for a in actual if a.value not in expected])
        missing_value_steps = len([a for a in actual if not a.could_evaluate or a.is_irretrievable or a.is_optimized_away])
        unexpected_value_steps = len([a for a in actual if a.could_evaluate and a.value is not None and a.value not in expected])
        missing_values = len([e for e in expected if not any(a.value == e for a in actual)])
        return {
            # The number of steps. Though this is not a useful metric in itself, it may be useful to see in tandem with
            # other variables.
            "total_steps": ScalarMetric(len(actual)),
            # The number of steps where the expected value sequence was observed.
            "correct_steps": ScalarMetric(correct_steps),
            # The number of steps which did not match the expected value sequence.
            "incorrect_steps": ScalarMetric(incorrect_steps, improves_asc=False),
            # The number of steps where the watched variable/expression was not available in the debugger.
            "missing_value_steps": ScalarMetric(missing_value_steps, improves_asc=False),
            # The number of steps where the watched variable/expression had a value not in the set of expected values.
            "unexpected_value_steps": ScalarMetric(unexpected_value_steps, improves_asc=False),
            # The number of steps where the watched variable/expression had a value in the set of expected values, but
            # out-of-order with the expected sequence.
            "misordered_value_steps": ScalarMetric(0, improves_asc=False),
            # The % of steps where the expected value sequence was observed.
            "correct_step_coverage": FractionMetric(correct_steps, len(actual)),
            # The edit distance between the expected and observed value sequences.
            "difference_from_expected": ScalarMetric(0, improves_asc=False),
            # The number of expected values that were not observed.
            "missing_values": ScalarMetric(missing_values, improves_asc=False),
        }

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
    def __init__(self, index):
        self.index: str = str(index)
        self.found_values = None

    def set_actual_values(self, actual_values):
        self.found_values = actual_values

    def constructor(loader, node):
        return Unknown(loader.construct_scalar(node))

    def representer(dumper: yaml.Dumper, data):
        if data.found_values is not None:
            return dumper.represent_data(data.found_values)
        return dumper.represent_scalar('!unknown', data.index)

    def register_yaml(loader):
        yaml.add_constructor("!unknown", Unknown.constructor, loader)
        yaml.add_representer(Unknown, Unknown.representer)
