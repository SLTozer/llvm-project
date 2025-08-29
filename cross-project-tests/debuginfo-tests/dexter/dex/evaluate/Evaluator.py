
from typing import Any
from dex.test_script.Rules import Expect, Scope, Unknown, Where
from dex.dextIR.DextIR import DextIR, StepIR
from dex.test_script.Rules import EvaluationContext, Metric


class EvaluationState(object):
    def __init__(self, relevant_expects: list[Expect], prev_state, step: StepIR):
        self.prev_state = prev_state
        self.step = step
        self.command_state: dict[int, object] = {}

def scope_matches_step(scope: Scope, step: StepIR):
    if scope.file is not None and scope.file != step.frames[0].loc.path:
        return False
    if scope.fn is not None and scope.fn != step.frames[0].function:
        return False
    return step.frames[0].loc.lineno in scope.get_lines()

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
            relevant_steps = [step for step in self.steps.steps if scope_matches_step(scope, step)]
            # Updating wildcards is a separate matter...
            if isinstance(value, Unknown):
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
