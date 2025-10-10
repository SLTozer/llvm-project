
import pprint
from typing import Any
from dex.test_script.Rules import All, DexRange, Expect, Scope, Unknown, Value, Where
from dex.dextIR.DextIR import DextIR, StepIR
from dex.dextIR.ValueIR import ValueIR
from dex.test_script.Rules import EvaluationContext, Metric


class EvaluationState(object):
    def __init__(self, relevant_expects: list[Expect], prev_state, step: StepIR):
        self.prev_state = prev_state
        self.step = step
        self.command_state: dict[int, object] = {}

def scope_matches_step(scope: Scope, step: StepIR):
    if scope.file is not None and scope.file != step.frames[0].loc.path:
        return False
    # The recorded function name may be a full signature, which won't exactly equal the function name; remove the
    # arguments list if one exists for matching purposes.
    fn = step.frames[0].function
    if '(' in fn:
        fn = fn.split('(')[0]
    if scope.fn is not None and scope.fn != fn:
        return False
    if scope.lines is not None and step.frames[0].loc.lineno not in scope.get_lines():
        return False
    return True

class DexEvaluator(object):
    def __init__(self, context, steps: DextIR):
        self.context = context
        self.steps = steps
        self.expect_results = []
        self.metrics: dict[str, Metric] = {}
        self.wildcard_updates: dict[str, Any] = {}
        self.eval_context = EvaluationContext()
        self.evaluate()

    def evaluate(self):
        script = self.steps.script
        expects_and_scopes: list[tuple[Expect, Any, Scope]] = []
        def accumulate_expects(expect: Expect, value, scope: Scope):
            expects_and_scopes.append((expect, value, scope))
        script.visit_script(visit_expect=accumulate_expects)

        for expect, value, scope in expects_and_scopes:
            self.eval_context.labels = scope.labels
            relevant_steps = [step for step in self.steps.steps if scope_matches_step(scope, step)]
            if isinstance(expect, All):
                print(value)
                watched_scope = expect.get_watched_scope()
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
                    step_scope_vars: list[ValueIR] = step.program_state.frames[0].scope_watches.get(watched_scope)
                    for val in step_scope_vars:
                        # FIXME: We ignore errors outright here because we're assuming there won't be any when we use
                        # this at O0 to generate a test script; later on we'll have to actually think about this.
                        if not val.could_evaluate or val.error_string:
                            continue
                        var_name = val.expression
                        if not var_name in scope_var_ranges:
                            scope_var_ranges[var_name] = ScopeVarValues(val, step.frames[0].loc.lineno)
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
                                return value.value
                            return {subv.expression: get_subvalue(subv) for subv in value.sub_values}
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
                for var, ranges in scope_var_ranges.items():
                    scope_line_range = scope.get_line_range()
                    if scope_line_range is not None and ranges.min == scope_line_range.start and ranges.max + 1 == scope_line_range.stop:
                        lines = None
                    else:
                        lines = DexRange(ranges.min, ranges.max)
                    scope_vars = expect.scopes_and_vars.setdefault(lines, {})
                    scope_vars[var] = map_value_range(ranges.values)
                pprint.pp(expect.scopes_and_vars)
                self.wildcard_updates[value] = expect.scopes_and_vars
            # Updating wildcards is a separate matter...
            if value is None or isinstance(value, Unknown):
                substitute_value = expect.get_unknown_substitute_value(relevant_steps)
                self.wildcard_updates[value.index] = substitute_value
                value.set_actual_values(substitute_value)
                continue
            actual = expect.get_actual_value(relevant_steps)
            expect_metrics = expect.evaluate(value, actual, self.eval_context)
            for metric_type, metric in expect_metrics.items():
                if metric_type not in self.metrics:
                    self.metrics[metric_type] = metric
                else:
                    self.metrics[metric_type] = self.metrics[metric_type].aggregate(metric)

    def all_successful(self):
        return all(r[1] != False for r in self.expect_results)

    def get_verbose_output(self):
        lines = []
        for metric_type, metric in self.metrics.items():
            lines.append(f"{metric_type}: {metric}")
        return '\n'.join(lines) + '\n'
