
from dataclasses import dataclass
import re
from typing import Any
import yaml
from dex.dextIR.StepIR import StepIR
from dex.dextIR.ValueIR import ValueIR
from dex.test_script.DataTypes import Metric, ScalarMetric, FractionMetric


def setup_yaml_parser(loader):
    reg_classes = [
        Where,
        Then,
        Value,
        Type,
        Steps,
        Label,
        Unknown,
        DexRange,
        Address,
        ValueAll,
        TypeAll,
        Float,
    ]
    for c in reg_classes:
        c.register_yaml(loader)

class Float:
    """Used as part of an expect for float values that may have an approximate range."""
    def __init__(self, values, range=None):
        if not isinstance(values, list):
            values = [values]
        self.values = [float(v) for v in values]
        self.range = range

    def matches(self, value):
        try:
            value = float(value)
        except ValueError:
            return False
        if self.range is None:
            return value in self.values
        return any(abs(expected - value) <= self.range for expected in self.values)

    def constructor(loader, node):
        if isinstance(node, yaml.ScalarNode):
            return Float(loader.construct_scalar(node))
        if isinstance(node, yaml.SequenceNode):
            return Float(loader.construct_sequence(node))
        elif isinstance(node, yaml.MappingNode):
            return Float(**loader.construct_mapping(node, deep=True))
        raise Exception("Invalid args to !float")

    def representer(dumper: yaml.Dumper, data):
        values = data.values
        if data.range is None:
            return dumper.represent_sequence('!float', values, flow_style=True)
        mapping = {
            "values": values,
            "range": data.range,
        }
        return dumper.represent_mapping('!float', mapping, flow_style=True)

    def register_yaml(loader):
        yaml.add_constructor("!float", Float.constructor, loader)
        yaml.add_representer(Float, Float.representer)

class Where:
    """"One or more instances of this class define a range of steps in a debugging session. Any expects in the script
    within scope of a "Where" will only be evaluated for the steps where the Where applies.
    """
    def __init__(self, attributes: dict):
        self.file: str | None = attributes.get("file")
        self.function: list[str] | str | None = attributes.get("function")
        self.lines: int | tuple[int, int] | DexRange | None = attributes.get("lines")
        self.for_hit_count: int | None = attributes.get("for_hit_count")
        self.conditions: dict = attributes.get("conditions")
        assert self.function or self.lines or not self.for_hit_count, "Can't have for_hit_count without also having lines or a function"

    def __repr__(self):
        elts = []
        if self.file:
            elts.append(f"file={self.file}")
        if self.function:
            elts.append(f"fn={self.function}")
        if self.lines:
            elts.append(f"lines={str(self.lines)}")
        if self.for_hit_count:
            elts.append(f"for_hit_count={str(self.for_hit_count)}")
        if self.conditions:
            conds = [f"{var}={val}" for var, val in self.conditions.items()]
            elts.append(f"conditions={{{', '.join(conds)}}}")
        return "Where(" + ", ".join(elts) + ")"


    def constructor(loader, node):
        return Where(loader.construct_mapping(node))

    def representer(dumper: yaml.Dumper, data):
        mapping = {}
        if data.file:
            mapping["file"] = data.file
        if data.function:
            mapping["function"] = data.function
        if data.lines:
            mapping["lines"] = data.lines
        if data.for_hit_count:
            mapping["for_hit_count"] = str(data.for_hit_count)
        return dumper.represent_mapping('!where', mapping, flow_style=True)

    def register_yaml(loader):
        yaml.add_constructor("!where", Where.constructor, loader)
        yaml.add_representer(Where, Where.representer)

class Then:
    """Used to perform actions, such as finishing the test or running a command. Will trigger when it is first in-scope
    for a step, so a typical usage pattern is to map to it directly from a "Where", e.g.
    `!where {line: 4, for_hit_count: 2}: !then finish`.
    """
    def __init__(self, command: str, attrs: dict = {}):
        self.command = command
        # FIXME: should we use subclasses instead of keeping this dict?
        self.attrs = attrs

    def from_dict(attrs: dict):
        attrs = attrs.copy()
        command = attrs.pop("do")
        return Then(command, attrs)

    def to_dict(self) -> dict:
        attrs = self.attrs.copy()
        attrs["do"] = self.command
        return attrs

    def is_valid(self) -> bool:
        return self.command == "finish" or self.command == "continue"

    def __repr__(self):
        return f"Then({self.command})"

    def constructor(loader, node):
        if isinstance(node, yaml.ScalarNode):
            return Then(loader.construct_scalar(node))
        elif isinstance(node, yaml.MappingNode):
            return Then.from_dict(loader.construct_mapping(node))
        raise Exception("Invalid args to !then")

    def representer(dumper, data):
        if data.attrs:
            return dumper.represent_mapping('!then', data.to_dict())
        else:
            return dumper.represent_scalar('!then', data.command)

    def register_yaml(loader):
        yaml.add_constructor("!then", Then.constructor, loader)
        yaml.add_representer(Then, Then.representer)

class Scope:
    def __init__(self, file: str, labels: dict, fn: str | None = None, lines: int | range | list | None = None,
                 conditions: dict | None = None, for_hit_count: int | None = None, parent_scope = None):
        self.file = file
        self.labels = labels
        self.fn = fn
        self.lines = lines
        self.conditions = conditions
        self.for_hit_count = for_hit_count
        self.parent_scope = parent_scope

    def empty_scope():
        return Scope(None, dict())

    # FIXME: Figure out whether "parentScope" should be contained in this.
    def as_tuple(self):
        return (
            self.file,
            self.fn,
            tuple(self.get_lines()),
            self.conditions,
            self.for_hit_count,
        )

    # Returns a new Scope resulting from applying the new Where to this scope.
    # Note that the 'Where' does not need to be contained within the current scope; for example, if 'where' is in a
    # different file to this scope, we take that as the new file and invalidate any existing fn/line info since it no
    # longer applies to the new scope.
    def add_where(self, where: Where, per_file_labels: dict[str, int] = {}):
        scope_file = self.file
        scope_fn = self.fn
        scope_lines = self.lines
        scope_conditions = self.conditions
        scope_for_hit_count = self.for_hit_count
        if where.file:
            scope_file = where.file
            scope_fn = None
            scope_lines = None
            scope_for_hit_count = None
        if where.function:
            scope_fn = where.function
            scope_lines = None
            scope_for_hit_count = None
            scope_conditions = None
        if where.lines:
            scope_lines = where.lines
            scope_for_hit_count = None
            scope_conditions = None
        if where.conditions:
            scope_conditions = where.conditions
        if where.for_hit_count:
            scope_for_hit_count = where.for_hit_count
        scope_labels = per_file_labels.get(scope_file, {})
        return Scope(scope_file, scope_labels, scope_fn, scope_lines, scope_conditions, scope_for_hit_count, parent_scope=self)

    def as_where(self) -> Where:
        attributes = {
            "file": self.file,
            "function": self.fn,
            "lines": self.lines,
            "conditions": self.conditions,
            "for_hit_count": self.for_hit_count,
        }
        return Where({k: v for k, v in attributes.items() if v is not None})

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

# Class used for holding any context that applies across individual expects. Currently, this includes addresses, where
# instead of expecting exact values we expect matching or relative values across steps/variables, and labels, which may
# appear as expected values for expects that contain line numbers.
class EvaluationContext:
    def __init__(self):
        self.address_resolutions: dict[str, str] = {}
        self.labels: dict[str, int] = {}

# An expectation of some debugger state that will be compared to actual observed debugger state and generate one or more
# metrics as a measurement of the difference.
# Expects are largely independent, but may have some limited cross-over in the case of metavariables (such as !addr).
class Expect:
    def __init__(self):
        pass

    # For a list of steps in which this expectation is in-scope, returns all the information required to evaluate it.
    def get_actual_value(self, steps: list[StepIR]):
        raise NotImplementedError()

    # For a list of steps in which this expectation is in-scope, returns all the information required to evaluate it.
    def get_actual_value(self, steps: list[StepIR]):
        raise NotImplementedError()

    # Similar to `get_actual_value`, but returns a value suitable for serializing directly to YAML instead of being
    # usable for evaluation, for the purposes of substituting unknown values.
    def get_unknown_substitute_value(self, steps: list[StepIR]):
        raise NotImplementedError()

    def evaluate(
        self, expected, actual, context: EvaluationContext
    ) -> dict[str, Metric]:
        raise NotImplementedError()

    def get_watched_exprs(self) -> list[str]:
        raise NotImplementedError()

    def get_watched_scope(self) -> str:
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
        self.actual_values = None

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

    def evaluate(
        self, expected, actual: list[ValueIR], context: EvaluationContext
    ) -> dict[str, Metric]:
        assert not isinstance(
            expected, Unknown
        ), "Cannot evaluate against unknown expected value!"
        # FIXME: Support lists and offsets.
        if isinstance(expected, Address):
            if expected.name in context.address_resolutions:
                expected = context.address_resolutions[expected.name]
            else:
                resolved_addr = next(
                    (a.value for a in actual if a.value is not None), None
                )
                if resolved_addr is not None:
                    context.address_resolutions[expected.name] = resolved_addr
                    expected = resolved_addr
        if not isinstance(expected, list):
            expected = [expected]

        # Compare the expected value to the observed value, recursively traversing any subvalues.
        def expected_matches_observed(expected, observed: ValueIR):
            if isinstance(expected, dict):
                # We are looking for subvalues of this expected value.
                for subv_name, subv_expected in expected.items():
                    try:
                        subv_observed = next(v for v in observed.sub_values if v.expression == subv_name)
                    except StopIteration:
                        print(f"Missing {subv_name}")
                        # Missing observed value for this subvalue.
                        return False
                    if not expected_matches_observed(subv_expected, subv_observed):
                        return False
                return True
            # FIXME: Find some way to generalize this "matcher" logic at some point.
            if isinstance(expected, Float):
                return expected.matches(observed.value)
            return str(expected) == observed.value

        seen_value_idxs = set()
        step_matches = []
        correct_steps = 0
        incorrect_steps = 0
        missing_var_steps = 0
        unexpected_value_steps = 0
        for a_idx, a in enumerate(actual):
            if not a.could_evaluate:
                if a.is_irretrievable or a.is_optimized_away:
                    missing_var_steps += 1
                incorrect_steps += 1
                continue
            matching_expected_idxs = [idx for idx, e in enumerate(expected) if expected_matches_observed(e, a)]
            if matching_expected_idxs:
                correct_steps += 1
                for e_idx in matching_expected_idxs:
                    seen_value_idxs.add(e_idx)
                    step_matches.append((a_idx, e_idx))
            else:
                incorrect_steps += 1
                unexpected_value_steps += 1
        seen_values = len(seen_value_idxs)
        missing_values = len(expected) - len(seen_value_idxs)
        return {
            # The number of steps. Though this is not a useful metric in itself, it may be useful to see in tandem with
            # other variables.
            "total_watched_steps": ScalarMetric(len(actual)),
            # The number of steps where the expected value sequence was observed.
            "correct_steps": ScalarMetric(correct_steps),
            # The number of steps which did not match the expected value sequence.
            "incorrect_steps": ScalarMetric(incorrect_steps, improves_asc=False),
            # The number of steps where the watched variable/expression was not available in the debugger.
            "missing_var_steps": ScalarMetric(missing_var_steps, improves_asc=False),
            # The number of steps where the watched variable/expression had a value not in the set of expected values.
            "unexpected_value_steps": ScalarMetric(unexpected_value_steps, improves_asc=False),
            # The number of steps where the watched variable/expression had a value in the set of expected values, but
            # out-of-order with the expected sequence.
            "misordered_value_steps": ScalarMetric(0, improves_asc=False),
            # The % of steps where the expected value sequence was observed.
            "correct_step_coverage": FractionMetric(correct_steps, len(actual)),
            # The edit distance between the expected and observed value sequences.
            "difference_from_expected": ScalarMetric(0, improves_asc=False),
            # The number of expected values that were observed at least once.
            "seen_values": ScalarMetric(seen_values),
            # The number of expected values that were not observed.
            "missing_values": ScalarMetric(missing_values, improves_asc=False),
        }

    def get_watched_exprs(self) -> list[str]:
        return [self.variable_name]

    def get_watched_scope(self) -> str:
        return None

    def __repr__(self):
        return f"Value({self.variable_name})"

    def constructor(loader, node):
        return Value(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar('!value', data.variable_name)

    def register_yaml(loader):
        yaml.add_constructor("!value", Value.constructor, loader)
        yaml.add_representer(Value, Value.representer)

class All:
    def get_watched_scope(self) -> str:
        raise NotImplementedError()

    def get_observed_value(self, value: ValueIR):
        raise NotImplementedError()

    def get_var_expect(self, var_name):
        raise NotImplementedError()

    def get_scope_values(self, scope: Scope, relevant_steps: list[StepIR]):
        watched_scope = self.get_watched_scope()

        class ScopeVarValues:
            # FIXME: Figure out how to filter out uninitialized values.
            def __init__(self, val: ValueIR, line: int):
                self.values = [val]
                self.min = line
                self.max = line
                # FIXME: I'm pretty sure we'll need this later to figure out cases where we want all local
                # variables in a function, rather than between line ranges; checking the min/max lines won't
                # help us figure out whether a given variable is available for the whole function, so we'll need
                # to directly check whether there were any steps it wasn't in scope for.
                self.any_not_in_scope = False

            def add_step(self, val: ValueIR, line: int):
                self.values.append(val)
                self.min = min(self.min, line)
                self.max = max(self.max, line)

            def print(self):
                print(f"[{self.min} - {self.max}]:")
                for v in self.values:
                    print(f"  {str(v)}")

        # Find for each scope variable the the least Where containing valid evaluations of each scope variable.
        # FIXME: For simplicity's sake, we assume here that we never track the variables of the same name across
        # multiple functions. 95% of the time this will be the case, but we'll need to handle it in future
        # maybe.
        scope_var_ranges: dict[str, ScopeVarValues] = {}
        for step in relevant_steps:
            step_scope_vars: list[ValueIR] = step.program_state.frames[
                0
            ].scope_watches.get(watched_scope)
            for val in step_scope_vars:
                # FIXME: We ignore errors outright here because we're assuming there won't be any when we use
                # this at O0 to generate a test script; later on we'll have to actually think about this.
                if not val.could_evaluate or val.error_string:
                    continue
                var_name = val.expression
                if not var_name in scope_var_ranges:
                    scope_var_ranges[var_name] = ScopeVarValues(
                        val, step.frames[0].loc.lineno
                    )
                else:
                    scope_var_ranges[var_name].add_step(val, step.frames[0].loc.lineno)

        def map_value_range(vals: list[ValueIR]):
            # If we observed no values at all, something has gone wrong.
            if not vals:
                return None
            values = []
            for val in vals:
                # If we could not evaluate this variable, we have failed to find a substitute.
                if not val.value:
                    return None

                # For a given ValueIR, returns its value if it has no subvalues, or a dict containing its
                # mapped subvalues if it has any.
                def get_subvalue(value: ValueIR):
                    if not value.sub_values:
                        return self.get_observed_value(value)
                    return {
                        "_": self.get_observed_value(value),
                        **{
                            subv.expression: get_subvalue(subv)
                            for subv in value.sub_values
                        },
                    }

                # Where a and b are either strings, or dicts containing string keys and values that are similar
                # types.
                new_val = get_subvalue(val)
                if values and str(new_val) == str(values[-1]):
                    continue
                values.append(new_val)

            # Prefer a scalar result if possible!
            if len(values) == 1:
                values = values[0]
            return values

        scope_vars = {}
        for var, ranges in scope_var_ranges.items():
            print(var)
            scope_line_range = scope.get_line_range()
            if (
                scope_line_range is not None
                and ranges.min == scope_line_range.start
                and ranges.max + 1 == scope_line_range.stop
            ):
                lines = None
            else:
                lines = DexRange(ranges.min, ranges.max)
            scope_line_vars = scope_vars.setdefault(lines, {})
            scope_line_vars[self.get_var_expect(var)] = map_value_range(ranges.values)
        return scope_vars


# A special class that can be used in place of a variable/expression in an expect, to indicate that we wish to apply the
# expect to all vars that match the provided category.
class ValueAll(Expect, All):
    def __init__(self, category: str):
        self.category = category
        # The set resolved variables and their associated values, grouped by scopes, using an empty Where as the key for
        # any vars that don't need scope narrowing.
        self.scopes_and_vars: dict[DexRange, dict[str, Any]] = {}

    def __repr__(self):
        return f"ValueAll({self.category})"

    def get_var_expect(self, var_name):
        return Value(var_name)

    def get_observed_value(self, value: ValueIR):
        return value.value

    def get_watched_exprs(self) -> list[str]:
        return []

    def get_watched_scope(self) -> str:
        return self.get_scope()


    def get_actual_value(self, steps: list[StepIR]) -> list[ValueIR]:
        return []

    def get_unknown_substitute_value(self, steps: list[StepIR]):
        return []

    def evaluate(
        self, expected, actual: list[ValueIR], context: EvaluationContext
    ) -> dict[str, Metric]:
        return {}

    def get_scope(self):
        return "Locals"

    # Given a list of actual steps, returns a list containing lists of steps for each item that this ValueAll expands to.
    def expand(self, steps: list[StepIR]) -> list[list[StepIR]]:
        assert self.category == "locals"

    def constructor(loader, node):
        return ValueAll(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!value/all", data.category)

    def register_yaml(loader):
        yaml.add_constructor("!value/all", ValueAll.constructor, loader)
        yaml.add_representer(ValueAll, ValueAll.representer)


# A special class that can be used in place of a variable/expression in an expect, to indicate that we wish to apply the
# expect to all vars that match the provided category.
class TypeAll(Expect, All):
    def __init__(self, category: str):
        self.category = category
        # The set resolved variables and their associated values, grouped by scopes, using an empty Where as the key for
        # any vars that don't need scope narrowing.
        self.scopes_and_vars: dict[DexRange, dict[str, Any]] = {}

    def __repr__(self):
        return f"TypeAll({self.category})"

    def get_var_expect(self, var_name):
        return Type(var_name)

    def get_watched_exprs(self) -> list[str]:
        return []

    def get_watched_scope(self) -> str:
        return self.get_scope()

    def get_actual_value(self, steps: list[StepIR]) -> list[ValueIR]:
        return []

    def get_observed_value(self, value: ValueIR):
        return value.type_name

    def get_unknown_substitute_value(self, steps: list[StepIR]):
        return []

    def evaluate(
        self, expected, actual: list[ValueIR], context: EvaluationContext
    ) -> dict[str, Metric]:
        return {}

    def get_scope(self):
        return "Locals"

    # Given a list of actual steps, returns a list containing lists of steps for each item that this TypeAll expands to.
    def expand(self, steps: list[StepIR]) -> list[list[StepIR]]:
        assert self.category == "locals"

    def constructor(loader, node):
        return TypeAll(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!type/all", data.category)

    def register_yaml(loader):
        yaml.add_constructor("!type/all", TypeAll.constructor, loader)
        yaml.add_representer(TypeAll, TypeAll.representer)

class Type(Expect):
    def __init__(self, variable_name: str):
        self.variable_name = variable_name

    # For a list of steps in which this expectation is in-scope, returns all the information required to evaluate it.
    def get_actual_value(self, steps: list[StepIR]):
        values = []
        for step in steps:
            values.append(step.program_state.frames[0].watches[self.variable_name])
        return values

    # Similar to `get_actual_value`, but returns a value suitable for serializing directly to YAML instead of being
    # usable for evaluation, for the purposes of substituting unknown values.
    def get_unknown_substitute_value(self, steps: list[StepIR]) -> str | list[str]:
        # If we observed no values at all, something has gone wrong.
        if not steps:
            return None
        values = []
        for step in steps:
            step_result: ValueIR = step.program_state.frames[0].watches[self.variable_name]
            # If we could not evaluate this variable, we have failed to find a substitute.
            if not step_result.type_name:
                return None
            values.append(step_result.type_name)
        # Prefer a scalar result if possible!
        if len(values) == 1:
            values = values[0]
        return values

    def evaluate(
        self, expected, actual: list[ValueIR], context: EvaluationContext
    ) -> dict[str, Metric]:
        assert not isinstance(
            expected, Unknown
        ), "Cannot evaluate against unknown expected value!"
        if not isinstance(expected, list):
            expected = [expected]
        expected = [str(e) for e in expected]

        correct_steps = len([a for a in actual if a.type_name in expected])
        incorrect_steps = len([a for a in actual if a.type_name not in expected])
        missing_var_steps = len([a for a in actual if not a.could_evaluate or a.is_irretrievable or a.is_optimized_away])
        unexpected_type_steps = len([a for a in actual if a.could_evaluate and a.type_name is not None and a.type_name not in expected])
        seen_types = len([e for e in expected if any(a.type_name == e for a in actual)])
        missing_types = len([e for e in expected if not any(a.type_name == e for a in actual)])
        return {
            # The number of steps. Though this is not a useful metric in itself, it may be useful to see in tandem with
            # other variables.
            "total_watched_steps": ScalarMetric(len(actual)),
            # The number of steps where the expected types were observed.
            "correct_steps": ScalarMetric(correct_steps),
            # The number of steps where the expected types were not observed.
            "incorrect_steps": ScalarMetric(incorrect_steps, improves_asc=False),
            # The number of steps where the watched variable/expression was not available in the debugger.
            "missing_var_steps": ScalarMetric(missing_var_steps, improves_asc=False),
            # The number of steps where the watched variable/expression had a value not in the set of expected values.
            "unexpected_type_steps": ScalarMetric(unexpected_type_steps, improves_asc=False),
            # The fraction of steps where the expected types were observed.
            "correct_step_coverage": FractionMetric(correct_steps, len(actual)),
            # The number of expected types that observed at least once.
            "seen_types": ScalarMetric(seen_types, improves_asc=False),
            # The number of expected types that were not observed at all.
            "missing_types": ScalarMetric(missing_types, improves_asc=False),
        }

    def get_watched_exprs(self) -> list[str]:
        if self.variable_name is ValueAll:
            return []
        return [self.variable_name]

    def get_watched_scope(self) -> str:
        return None

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
    def __init__(self, kind: str):
        assert kind == "order" or kind == "never"
        self.kind = kind

    # For a list of steps in which this expectation is in-scope, returns all the information required to evaluate it.
    def get_actual_value(self, steps: list[StepIR]):
        return [step.frames[0].loc.lineno for step in steps]

    # Similar to `get_actual_value`, but returns a value suitable for serializing directly to YAML instead of being
    # usable for evaluation, for the purposes of substituting unknown values.
    def get_unknown_substitute_value(self, steps: list[StepIR]):
        return [step.frames[0].loc.lineno for step in steps]

    def evaluate(
        self, expected, actual, context: EvaluationContext
    ) -> dict[str, Metric]:
        if not isinstance(expected, list):
            expected = [expected]
        expected = [l.to_line(context.labels) if isinstance(l, Label) else int(l) for l in expected]
        if self.kind == "order":
            return {
                "correct_line_steps": len([a for a in actual if a in expected]),
                "missing_expected_lines": len([e for e in expected if e not in actual]),
                "unexpected_line_steps": len([a for a in actual if a not in expected]),
            }
        else:
            return {
                "unseen_undesired_lines": len([e for e in expected if e not in actual]),
                "seen_undesired_lines": len([e for e in expected if e in actual]),
                "undesired_line_steps": len([a for a in actual if a in expected]),
            }

    def get_watched_exprs(self) -> list[str]:
        return []

    def get_watched_scope(self) -> str:
        return None

    def __repr__(self):
        return f"Step({self.kind})"

    def constructor(loader, node):
        return Steps(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar('!steps', data.kind)

    def register_yaml(loader):
        yaml.add_constructor("!steps", Steps.constructor, loader)
        yaml.add_representer(Steps, Steps.representer)

@dataclass(frozen=True)
class Label:
    name: str

    def to_line(self, labels: dict[str, int]) -> int:
        # Labels may contain offsets, which is accounted for here.
        raw_label = self.name.strip()
        if match := re.match(r'^([a-zA-Z_]\w*)\s*([+-])\s*(\d+)$', raw_label):
            identifier, sign, number = match.groups()
            value = int(number) if sign == '+' else -int(number)
            return labels[identifier] + value
        return labels[raw_label]

    def __repr__(self):
        return f"Label({self.name})"

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

@dataclass(frozen=True)
class DexRange:
    start: int | Label
    stop: int | Label

    def __repr__(self) -> str:
        return f"[{self.start} - {self.stop}]"

    # We use an inclusive range in Dexter scripts, while python ranges are exclusive.
    def to_range(self, labels: dict[str, int]) -> range:
        start = self.start if isinstance(self.start, int) else self.start.to_line(labels)
        stop = self.stop if isinstance(self.stop, int) else self.stop.to_line(labels)
        return range(start, stop + 1)

    def constructor(loader, node):
        range_seq = loader.construct_sequence(node)
        if len(range_seq) != 2 or not all(
            [isinstance(elt, (int, Label)) for elt in range_seq]
        ):
            raise Exception(
                range_seq, "!range must have exactly 2 int or !label elements"
            )
        return DexRange(range_seq[0], range_seq[1])

    def representer(dumper, data: range):
        return dumper.represent_sequence("!range", [data.start, data.stop])

    def register_yaml(loader):
        yaml.add_constructor("!range", DexRange.constructor, loader)
        yaml.add_representer(DexRange, DexRange.representer)


class Address:
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"Address({self.name})"

    def constructor(loader, node):
        return Address(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!address", data.name)

    def register_yaml(loader):
        yaml.add_constructor("!address", Address.constructor, loader)
        yaml.add_representer(Address, Address.representer)
