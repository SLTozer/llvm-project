
import pprint
from typing import Any
from dex.test_script.Nodes import (
    All,
    ValueAll,
    DexRange,
    Expect,
    Scope,
    Unknown,
    Value,
    Where,
)
from dex.dextIR.DextIR import DextIR, StepIR
from dex.dextIR.ValueIR import ValueIR
from dex.test_script.Nodes import EvaluationContext, Metric


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
        self.successful_wildcard_updates: int = 0
        self.unsuccessful_wildcard_updates: int = 0
        self.reified_map: dict = {}
        self.eval_context = EvaluationContext()
        self.evaluate()

    def evaluate(self):
        script = self.steps.script
        expects_and_scopes: list[tuple[Expect, Any, Scope]] = []

        def accumulate_expects(expect: Expect, expected_value, scope: Scope):
            expects_and_scopes.append((expect, expected_value, scope))
        script.visit_script(visit_expect=accumulate_expects)

        for expect, expected_value, scope in expects_and_scopes:
            self.eval_context.labels = scope.labels
            relevant_steps = [step for step in self.steps.steps if scope_matches_step(scope, step)]
            if isinstance(expect, All):
                self.reified_map[expect] = expect.get_scope_values(
                    scope, relevant_steps
                )
                if self.reified_map[expect]:
                    self.successful_wildcard_updates += 1
                else:
                    self.unsuccessful_wildcard_updates += 1
                continue

            # Updating wildcards is a separate matter...
            if expected_value is None:
                self.reified_map[expect] = expect.get_unknown_substitute_value(
                    relevant_steps
                )
                if self.reified_map[expect]:
                    self.successful_wildcard_updates += 1
                else:
                    self.unsuccessful_wildcard_updates += 1
                continue

            actual = expect.get_actual_value(relevant_steps)
            expect_metrics = expect.evaluate(expected_value, actual, self.eval_context)
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
