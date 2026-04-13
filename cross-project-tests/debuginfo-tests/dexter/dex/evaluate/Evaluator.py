# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Evaluation tools used to compare a DextIR with a Script."""

import math
import os
from typing import Any, Optional
from dex.test_script.Nodes import (
    All,
    Steps,
    Expect,
    Where,
)
from dex.dextIR import DextIR, FrameIR, StepIR
from dex.test_script.DataTypes import Metric, serialize_metric_to_json
from dex.test_script.StepMatcher import MatchContext, StepMatchResult
from dex.test_script.Script import Scope
from dex.test_script.ValueMatcher import (
    evaluate_steps,
    get_scope_values,
    get_step_values,
    get_var_values,
    ListMatchResult,
    MatchResult,
    MatchType,
    uniquify,
    EvaluationContext,
)


class DexEvaluator(object):
    def __init__(self, context, dext_ir: DextIR):
        self.context = context
        self.dext_ir = dext_ir
        self.metrics: dict[str, Metric] = {}
        self.successful_wildcard_updates: int = 0
        self.unsuccessful_wildcard_updates: int = 0
        self.reified_map: dict = {}
        self.eval_context = EvaluationContext()
        # Cached evaluated info, useful for visualization.
        self.actual_results: dict[
            Expect, list[tuple[int, MatchResult, dict[str, Metric]]]
        ] = {}
        self.step_matches: list[StepMatchResult] = []
        self.evaluate()

    def evaluate(self):
        script = self.dext_ir.script
        expects_and_scopes: list[tuple[Expect, Any, Scope]] = []

        def check_condition(step: StepIR, frame_idx: int, condition: str):
            cond_value = step.frames[frame_idx].values[condition]
            result = cond_value.could_evaluate and cond_value.value == "true"
            return result

        match_context = MatchContext(check_condition=check_condition)
        for step in self.dext_ir.steps:
            self.step_matches.append(StepMatchResult(script, step, match_context))

        def accumulate_expects(expect: Expect, expected_value, scope: Scope):
            expects_and_scopes.append((expect, expected_value, scope))

        script.visit_script(visit_expect=accumulate_expects)

        for expect, expected_value, scope in expects_and_scopes:
            self.eval_context.labels = scope.labels
            # The format the Expect currently wants to see is a list[StepIR] of steps where it is active.
            relevant_steps = [
                step
                for idx, step in enumerate(self.dext_ir.steps)
                if scope.where and scope.where in self.step_matches[idx].active_wheres
            ]
            # If this is a Scope-level expect (watching all expressions at a given scope), we specifically want to get
            # our result from `get_scope_values`.
            # FIXME: We should be able to merge this method with the one below.
            if isinstance(expect, All):
                self.reified_map[expect] = get_scope_values(
                    expect, scope, relevant_steps
                )
                if self.reified_map[expect]:
                    self.successful_wildcard_updates += 1
                else:
                    self.unsuccessful_wildcard_updates += 1
                continue

            # If there is no expected_value, this is a wildcard that we need to find a substitute value for via
            # `get_unknown_substitute_value`.
            if expected_value is None:
                if isinstance(expect, Steps):
                    self.reified_map[expect] = get_step_values(expect, scope, relevant_steps)
                else:
                    self.reified_map[expect] = get_var_values(expect, scope, relevant_steps)
                continue

            if relevant_steps:
                result = evaluate_steps(
                    expect, expected_value, relevant_steps, self.eval_context
                )
                self.actual_results[expect] = result
                final_step, final_matches, final_metrics = result[-1]
                
                for metric_type, metric in final_metrics.items():
                    if metric_type not in self.metrics:
                        self.metrics[metric_type] = metric
                    else:
                        self.metrics[metric_type] = self.metrics[metric_type].aggregate(
                            metric
                        )

    def get_output(self):
        lines = []
        for metric_type, metric in self.metrics.items():
            lines.append(f"{metric_type}: {metric}")
        return "\n".join(lines) + "\n"

    def get_json_output(self):
        return {metric_type: serialize_metric_to_json(metric) for metric_type, metric in self.metrics.items()}

try:
    import matplotlib.pyplot as plt
except (ModuleNotFoundError, ImportError) as e:
    plt = e

# Class used to visualize results from Dexter.
class DexVisualizer(object):
    def __init__(self, context, steps: DextIR, evaluator: DexEvaluator = None):
        self.context = context
        self.dext_ir = steps
        self.evaluator = evaluator or DexEvaluator(context, steps)

    # Contains details summarizing a particular step.
    class StepDetails:
        def __init__(self, step: StepIR):
            frame = step.current_frame
            loc = step.current_location
            self.short_name = f"{frame.function} ({os.path.basename(loc.path):{loc.lineno}:{loc.column}})"
            self.active_expects = 0

    def get_step_details(self, step_index: int):
        step_ir = self.dext_ir.steps[step_index]
        active_wheres = self.evaluator.step_active_wheres[step_index]
        script = self.dext_ir.script
        active_expects = 0

    # Outputs the script object with colour highlighting according to the current step.
    def visualize_final_result(self):
        script = self.dext_ir.script
        evaluator = self.evaluator

        def remap_expect(
            expect: Expect, expected: Any, scope: Scope
        ) -> tuple[Expect, Any]:
            actual_with_steps = evaluator.actual_results.get(expect, [])
            # For a ListMatchResult, the final "actual" has the full result. For a ComplexMatchResult, each step appears
            # in a separate actual entry.
            if actual_with_steps and isinstance(
                actual_with_steps[-1][1], ListMatchResult
            ):
                last_actual = actual_with_steps[-1][1]
                any_match = any(
                    match != MatchType.NONE for match in last_actual.value_matches
                )
                any_nonmatch = any(
                    match != MatchType.WHOLE for match in last_actual.value_matches
                )
                valid_actuals = last_actual.format_for_display()
            else:
                any_match = any(
                    result.get_match_type() != MatchType.NONE
                    for _step, result, _metrics in actual_with_steps
                )
                any_nonmatch = any(
                    result.get_match_type() != MatchType.WHOLE
                    for _step, result, _metrics in actual_with_steps
                )
                valid_actuals = [
                    result.format_for_display()
                    for _step, result, _metrics in actual_with_steps
                ]
            if any_match:
                color_code = "<y>" if any_nonmatch else "<g>"
            else:
                color_code = "<r>" if any_nonmatch else "<grey>"
            if len(valid_actuals) == 1:
                valid_actuals = valid_actuals[0]
            return (
                expect,
                {"Expected": expected, f"{color_code}Actual</>": valid_actuals},
            )

        return script.map_script(map_expect=remap_expect).format() + "\n"

    # Outputs the script object with colour highlighting according to the current step.
    def visualize_step(self, step_idx: int):
        script = self.dext_ir.script
        evaluator = self.evaluator

        def remap_expect(
            expect: Expect, expected: Any, scope: Scope
        ) -> tuple[Expect, Any]:
            actual_with_steps = evaluator.actual_results.get(expect, [])
            # For a ListMatchResult, the final "actual" has the full result. For a ComplexMatchResult, each step appears
            # in a separate actual entry.
            if actual_with_steps and isinstance(
                actual_with_steps[-1][1], ListMatchResult
            ):
                valid_actuals = next(
                    result.format_for_display()
                    for step, result, metrics in reversed(actual_with_steps)
                    if step <= step_idx
                )
            else:
                valid_actuals = [
                    result.format_for_display()
                    for step, result, _metrics in actual_with_steps
                    if step <= step_idx
                ]
                valid_actuals = uniquify(valid_actuals)
            if len(valid_actuals) == 1:
                valid_actuals = valid_actuals[0]
            return (expect, {"Expected": expected, "Actual": valid_actuals})

        visual_script = script.map_script(map_expect=remap_expect)
        where_matches = evaluator.step_matches[step_idx].where_frame_matches
        active_wheres = evaluator.step_matches[step_idx].active_wheres

        def highlight_nodes(node: Any, scope: Scope):
            node_str = f"{node}"
            node_str = node_str.replace("<", "[")
            node_str = node_str.replace(">", "]")
            if isinstance(node, Where):
                if node in active_wheres:
                    return f"<g>{node_str}</>"
                if node in where_matches:
                    return f"<y>{node_str}</>"
            if scope.where and scope.where not in where_matches:
                return f"<grey>{node_str}</>"
            return str(node_str)

        return visual_script.format(process_node=highlight_nodes)

    def graph_steps(self) -> list[tuple[list[int], list[int]]]:
        if isinstance(plt, (ModuleNotFoundError, ImportError)):
            self.context.logger.error(f"Failed to import matplotlib.pyplot: {plt}")
            return
        script = self.dext_ir.script
        steps = self.dext_ir.steps
        step_where_matches = [
            step_match.where_frame_matches for step_match in self.evaluator.step_matches
        ]
        step_active_wheres = [
            step_match.active_wheres for step_match in self.evaluator.step_matches
        ]
        comparison_steps_collection = []

        def accumulate_steps(expect: Expect, values, scope: Scope):
            if isinstance(expect, Steps) and values is not None:
                if isinstance(values, list):
                    assert all(isinstance(v, int) for v in values)
                    expected_steps = values
                else:
                    assert isinstance(
                        values, int
                    ), "Invalid step order, should be list of ints or single int"
                    expected_steps = [values]
                relevant_steps = [
                    step
                    for idx, step in enumerate(steps)
                    if scope.where and scope.where in step_active_wheres[idx]
                ]
                actual_steps = [step.frames[0].loc.lineno for step in relevant_steps]
                comparison_steps_collection.append((expected_steps, actual_steps))

        script.visit_script(visit_expect=accumulate_steps)
        for expected, actual in comparison_steps_collection:

            # if expected == actual:
            #     expected_label = "Expected & Actual"
            expected_y = list(expected[math.floor(n / 2)] for n in range(len(expected) * 2 - 1))
            expected_x = list(math.ceil(n / 2) for n in range(len(expected) * 2 - 1))
            plt.plot(expected_x, expected_y, label="Expected")

            actual_y = list(actual[math.floor(n / 2)] for n in range(len(actual) * 2 - 1))
            actual_x = list(math.ceil(n / 2) for n in range(len(actual) * 2 - 1))
            plt.plot(actual_x, actual_y, label="Actual")

            min_step = min(min(expected), min(actual))
            max_step = max(max(expected), max(actual))

            # Add labels and title
            plt.xlabel("Step")
            plt.ylabel("Line Number")
            plt.title("Expected vs Actual steps")
            plt.legend()

            plt.ylim(max_step + 1, min_step - 1)

            # Display the plot in a GUI window
            plt.show()

        return comparison_steps_collection

# Finds the set of differences between the recorded information (according to `a`'s script) in a and b.
def diff_dexter_results(context, a: DextIR, b: DextIR, a_eval: DexEvaluator = None, b_eval: DexEvaluator = None) -> str:
        script = a.script
        if a_eval is None:
            a_eval = DexEvaluator(context, a)
        if b_eval is None:
            b_eval = DexEvaluator(context, b)

        def remap_expect(
            expect: Expect, expected: Any, scope: Scope
        ) -> tuple[Expect, Any]:
            a_actual_with_steps = a_eval.actual_results.get(expect, [])
            b_actual_with_steps = b_eval.actual_results.get(expect, [])
            # For a ListMatchResult, the final "actual" has the full result. For a ComplexMatchResult, each step appears
            # in a separate actual entry.
            if a_actual_with_steps and isinstance(
                a_actual_with_steps[-1][1], ListMatchResult
            ):
                last_a_actual = a_actual_with_steps[-1][1]
                last_b_actual = b_actual_with_steps[-1][1]
                assert isinstance(last_b_actual, ListMatchResult)
                any_a_match = any(
                    match != MatchType.NONE for match in last_a_actual.value_matches
                )
                any_a_nonmatch = any(
                    match != MatchType.WHOLE for match in last_a_actual.value_matches
                )
                valid_a_actuals = last_a_actual.format_for_display()
                any_b_match = any(
                    match != MatchType.NONE for match in last_b_actual.value_matches
                )
                any_b_nonmatch = any(
                    match != MatchType.WHOLE for match in last_b_actual.value_matches
                )
                valid_b_actuals = last_b_actual.format_for_display()
            else:
                any_a_match = any(
                    result.get_match_type() != MatchType.NONE
                    for _step, result, _metrics in a_actual_with_steps
                )
                any_a_nonmatch = any(
                    result.get_match_type() != MatchType.WHOLE
                    for _step, result, _metrics in a_actual_with_steps
                )
                valid_a_actuals = [
                    result.format_for_display()
                    for _step, result, _metrics in a_actual_with_steps
                ]
                any_b_match = any(
                    result.get_match_type() != MatchType.NONE
                    for _step, result, _metrics in b_actual_with_steps
                )
                any_b_nonmatch = any(
                    result.get_match_type() != MatchType.WHOLE
                    for _step, result, _metrics in b_actual_with_steps
                )
                valid_b_actuals = [
                    result.format_for_display()
                    for _step, result, _metrics in b_actual_with_steps
                ]
            if any_a_match:
                a_color_code = "<y>" if any_a_nonmatch else "<g>"
            else:
                a_color_code = "<r>" if any_a_nonmatch else "<grey>"
            if len(valid_a_actuals) == 1:
                valid_a_actuals = valid_a_actuals[0]
            if any_b_match:
                b_color_code = "<y>" if any_b_nonmatch else "<g>"
            else:
                b_color_code = "<r>" if any_b_nonmatch else "<grey>"
            if len(valid_b_actuals) == 1:
                valid_b_actuals = valid_b_actuals[0]
            return (
                expect,
                {"Expected": expected, f"{a_color_code}Base</>": valid_a_actuals, f"{b_color_code}Comp</>": valid_b_actuals},
            )

        return script.map_script(map_expect=remap_expect).format() + "\n"
