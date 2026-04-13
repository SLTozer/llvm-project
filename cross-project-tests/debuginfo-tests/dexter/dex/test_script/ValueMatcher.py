# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Contains the logic that unifies Dexter Scripts with DextIR, allowing us to match one to the other."""

# FIXME: should this file be in `evaluator` instead? It seems like the right place, but there needs to be a good
# interface between this and `Nodes`.

from collections import defaultdict
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Callable
from dex.evaluate.VisualDex import VisualDexNode, VisualDexNodeStatus, VisualDexResult
from dex.test_script.DataTypes import FractionMetric, ScalarMetric, Metric
from dex.test_script.Nodes import (
    Address,
    All,
    DexRange,
    Expect,
    Float,
    Self,
    Label,
    Steps,
    Then,
    Type,
    Value,
    Where,
)
from dex.test_script.Script import DexterScript, Scope
from dex.dextIR import ValueIR, StepIR
from dex.test_script.StepMatcher import MatchContext, StepMatchResult

def uniquify(l: list):
    """Takes the given list, whose elements may be non-hashable nested containers, and returns a new list containing all
    of its unique elements, in order of first appearance.
    Used for uniquing observed values when generating scripts."""

    def frozen(obj):
        # Converts non-hashable objects into hashable objects, for insertion into a set. As we use the result to check
        # for uniqueness, results must be consistent (i.e. dicts must be sorted).
        if isinstance(obj, dict):
            return tuple(sorted((str(k), frozen(v)) for k, v in obj.items()))
        if isinstance(obj, (list)):
            return tuple(frozen(x) for x in obj)
        if isinstance(obj, Float):
            return (tuple(obj.values), obj.range)
        if isinstance(obj, Address):
            return ("addr", obj.name)
        if isinstance(obj, ComplexMatchResult):
            return frozen(obj.match_tree)
        if isinstance(obj, Submatch):
            if obj.is_leaf:
                return obj.leaf_value
            return frozen(obj.submatches)
        return obj

    unique_set = set()
    result = []
    for item in l:
        frozen_item = frozen(item)
        if frozen_item not in unique_set:
            unique_set.add(frozen_item)
            result.append(item)
    return result


# Class used for holding any context that applies across individual expects. Currently, this includes addresses, where
# instead of expecting exact values we expect matching or relative values across steps/variables, and labels, which may
# appear as expected values for expects that contain line numbers.
class EvaluationContext:
    def __init__(self):
        self.address_resolutions: dict[str, str] = {}
        self.labels: dict[str, int] = {}


class MatchDistance:
    def __init__(self, d: int = 0):
        self.distances = [d]

    def is_zero(self) -> bool:
        return self.distances == [0]

    # Appends the digits of "other" to this distance; used in cases where "other" represents the distance of a child
    # Submatch and "self" represents the distance of its parent Submatch.
    def extend(self, other: "MatchDistance"):
        # If we're only adding 0, it's the same as adding nothing.
        if all(d == 0 for d in other.distances):
            return
        self.distances.extend(other.distances)

    # Adds together the distances of self and other pairwise, treating empty spaces as 0; used in cases where "self" and
    # "other" are sibling Submatches (i.e. they share a common parent) and their distances are being combined.
    def add(self, other: "MatchDistance"):
        if len(self.distances) < len(other.distances):
            self.distances.extend([0] * (len(other.distances) - len(self.distances)))
        for i, d in enumerate(other.distances):
            self.distances[i] += d

    # Returns <0 if self < other, >0 if self > other, and 0 if self == other.
    def cmp(self, other: "MatchDistance") -> int:
        for i in range(0, max(len(self.distances), len(other.distances))):
            self_d = self.distances[i] if i < len(self.distances) else 0
            other_d = other.distances[i] if i < len(other.distances) else 0
            diff = self_d - other_d
            if diff != 0:
                return diff
        return 0


class MatchType(Enum):
    NONE = 0
    PARTIAL = 1
    WHOLE = 2


class Submatch:
    def __init__(
        self,
        match_type: MatchType,
        leaf_value: str = None,
        submatches: dict[str | Self, "Submatch"] = None,
    ):
        # self.node_name = node_name
        assert (leaf_value is None) != (
            submatches is None
        ), "Must have exactly one of either submatches or a leaf value."
        self.leaf_value = leaf_value
        self.submatches = submatches
        self.match_type = match_type
        self.is_leaf = leaf_value is not None

    # Returns a measure of the "distance" of this match,
    def match_distance(self):
        if self.match_type != MatchType.PARTIAL:
            return MatchDistance(1 if self.match_type == MatchType.NONE else 0)
        assert (
            self.submatches is not None
        ), "Partial match for a Submatch without submatches?"
        match_dist = MatchDistance(0)
        # Accumulate the distances of all submatches, and add a "0".
        sub_match_dist = MatchDistance(0)
        for _, subm in self.submatches.items():
            sub_match_dist.add(subm.match_distance())
        match_dist.extend(sub_match_dist)
        return match_dist


class MatchResult:
    def __init__(self, step_index: int):
        self.step_index = step_index

    def format_for_display(self) -> str | list[str]:
        raise NotImplementedError()

    def get_match_type(self) -> MatchType:
        raise NotImplementedError()


# MatchResult for comparison of a list of simple values (integers only right now, for Step comparison).
# Does not perform complex matching of single results (as ComplexMatchResult does), but uses all previously matched
# values as part of its input, allowing us to check for ordering/repetition across multiple steps.
class ListMatchResult(MatchResult):
    def __init__(self, values: list[int], expected: list[int], step_index: int):
        super(ListMatchResult, self).__init__(step_index)
        self.values = values
        self.expected = expected
        self.value_matches = self.get_value_matches()

    def get_value_matches(self) -> list[MatchType]:
        matcher = SequenceMatcher(a=self.expected, b=self.values)
        matches = matcher.get_matching_blocks()
        matched_idx = 0
        value_matches = []
        for block_e, block_a, block_size in matches:
            if matched_idx < block_a:
                for v_idx in range(matched_idx, block_a):
                    if self.values[v_idx] in self.expected:
                        value_matches.append(MatchType.PARTIAL)
                    else:
                        value_matches.append(MatchType.NONE)
            value_matches += [MatchType.WHOLE] * block_size
            matched_idx = block_a + block_size
        return value_matches

    def format_for_display(self) -> list[str]:
        def format_value(value: int, match: MatchType) -> str:
            if match == MatchType.WHOLE:
                return f"<g>{value}</>"
            if match == MatchType.PARTIAL:
                return f"<y>{value}</>"
            return f"<r>{value}</>"

        return [
            format_value(value, match)
            for value, match in zip(self.values, self.value_matches)
        ]

    def get_match_type(self) -> MatchType:
        return MatchType.WHOLE if self.correct else MatchType.NONE


# Lil class representing the match state of an observed value to the list of expected values. For a given ValueIR, it
# contains a summary of:
#   - The overall result of the match (i.e. is the actual value correct)
#   - The complete structure of the attempted match, describing each value/subvalue that we attempted to match, and
#     whether those values/subvalues matched, did not match, or partially matched (i.e. some subvalues matched and
#     some didn't).
# It also contains a rough approximation of "match distance", meaning that for a set of ComplexMatchResults we can
# select which one was closest to being a correct match.
class ComplexMatchResult(MatchResult):
    def __init__(
        self,
        value: ValueIR,
        expected: Any,
        step_index: int,
        is_value: bool,
        context: EvaluationContext,
    ):
        super(ComplexMatchResult, self).__init__(step_index)
        self.root_value = value
        self.expected = expected
        self.is_value = is_value
        self.match_tree = self.get_match_tree(value, expected, context)
        self.match_distance = self.match_tree.match_distance()

    def get_match_type(self) -> MatchType:
        return self.match_tree.match_type

    def extract_result(self, value: ValueIR) -> str:
        if not value.could_evaluate:
            return "<Could not evaluate>"
        if value.is_irretrievable:
            return "<Value could not be retrieved>"
        if value.is_optimized_away:
            return "<Value optimized away>"
        return value.value if self.is_value else value.type_name

    def format_for_display(self):
        def format_submatch(submatch: Submatch):
            def get_match_color(match_type: MatchType) -> str:
                if match_type == MatchType.WHOLE:
                    return "<g>"
                elif match_type == MatchType.PARTIAL:
                    return "<y>"
                assert match_type == MatchType.NONE
                return "<r>"

            # Leaf values are always printed inline, i.e. we ignore any indenting. Also, as written this will only
            # be entered for the topmost item.
            if submatch.leaf_value is not None:
                color_tag = get_match_color(submatch.match_type)
                return f"{color_tag}{submatch.leaf_value}</>"
            result = {}
            for name, subm in submatch.submatches.items():
                color_tag = get_match_color(subm.match_type)
                if subm.leaf_value is not None:
                    result[f"{color_tag}{name}"] = f"{subm.leaf_value}</>"
                else:
                    res = format_submatch(subm)
                    assert res is not None
                    result[f"{color_tag}{name}</>"] = res
            return result

        return format_submatch(self.match_tree)

    def get_match_tree(
        self, observed: ValueIR, expected, context: EvaluationContext
    ) -> Submatch:
        if isinstance(expected, dict):
            # We are looking for subvalues of this expected value.
            submatches = {}
            for subv_name, subv_expected in expected.items():
                if isinstance(subv_name, Self):
                    assert not isinstance(
                        subv_expected, dict
                    ), "Should not use Self() to recurse"
                    subv_observed = self.extract_result(observed)
                    match_type = (
                        MatchType.WHOLE
                        if str(subv_expected) == subv_observed
                        else MatchType.NONE
                    )
                    submatches[subv_name] = Submatch(
                        match_type, leaf_value=subv_observed
                    )
                    continue
                try:
                    subv_observed = next(
                        v for v in observed.sub_values if v.expression == subv_name
                    )
                except StopIteration:
                    submatches[subv_name] = Submatch(
                        MatchType.NONE, leaf_value="<Missing>"
                    )
                    continue
                submatch = self.get_match_tree(subv_observed, subv_expected, context)
                submatches[subv_name] = submatch
            any_match = any(
                subm.match_type != MatchType.NONE for subm in submatches.values()
            )
            any_non_match = any(
                subm.match_type != MatchType.WHOLE for subm in submatches.values()
            )
            if any_match and not any_non_match:
                match_type = MatchType.WHOLE
            elif not any_match:
                match_type = MatchType.NONE
            else:
                match_type = MatchType.PARTIAL
            return Submatch(match_type, submatches=submatches)
        observed_result = self.extract_result(observed)
        if isinstance(expected, Address):
            # FIXME: Support offsets.
            if expected.name in context.address_resolutions:
                resolved_addr = context.address_resolutions[expected.name]
            else:
                resolved_addr = observed_result
                context.address_resolutions[expected.name] = resolved_addr
            # TODO: We probably want to display resolved addresses somewhere else. For now though, the next best
            # thing (and probably useful regardless) is to determine whether the observed value matches the resolved
            # address, if any, or otherwise any other addresses, and include that in the output.
            if str(resolved_addr) == observed_result:
                result_str = f"{observed_result} (!address {expected.name})"
                return Submatch(MatchType.WHOLE, leaf_value=result_str)
            elif other_addr := next(
                (
                    (name, addr)
                    for (name, addr) in context.address_resolutions.items()
                    if str(addr) == observed_result
                ),
                None,
            ):
                other_name, _ = other_addr
                return Submatch(
                    MatchType.NONE,
                    leaf_value=f"{observed_result} (!address {other_name})",
                )
            else:
                return Submatch(MatchType.NONE, leaf_value=observed_result)
        # FIXME: Find some way to generalize this "matcher" logic at some point.
        if isinstance(expected, Float):
            matches = (
                MatchType.WHOLE if expected.matches(observed_result) else MatchType.NONE
            )
        else:
            matches = (
                MatchType.WHOLE if str(expected) == observed_result else MatchType.NONE
            )
        assert observed_result is not None
        return Submatch(matches, leaf_value=observed_result)


def evaluate_step_steps(
    expected, relevant_steps: list[StepIR], context: EvaluationContext
) -> list[tuple[int, MatchResult, dict[str, Metric]]]:
    if not isinstance(expected, list):
        expected = [expected]
    expected = [
        l.to_line(context.labels) if isinstance(l, Label) else int(l) for l in expected
    ]
    stepped_lines = []
    correct_lines = 0
    incorrect_lines = 0
    result = []
    for step in relevant_steps:
        stepped_lines.append(step.frames[0].loc.lineno)
        match_result = ListMatchResult(stepped_lines.copy(), expected, step.step_index)
        if match_result.value_matches[-1] != MatchType.NONE:
            correct_lines += 1
        else:
            incorrect_lines += 1
        metric = {
            "total_line_steps": ScalarMetric(len(stepped_lines)),
            "correct_line_steps": ScalarMetric(correct_lines),
            "unexpected_line_steps": ScalarMetric(incorrect_lines),
            "missing_expected_lines": ScalarMetric(
                len([e for e in expected if e not in stepped_lines])
            ),
        }
        result.append((step.step_index, match_result, metric))
    return result


# Returns a list of the results after every relevant step, including the step index, the match result for that
# step, and the results after that step. The final metric results will be in the last element of the list.
def evaluate_type_steps(
    variable_name: str,
    expected,
    relevant_steps: list[StepIR],
    context: EvaluationContext,
) -> list[tuple[int, MatchResult, dict[str, Metric]]]:
    if not isinstance(expected, list):
        expected = [expected]

    results = []
    seen_type_idxs = set()
    correct_steps = 0
    incorrect_steps = 0
    missing_var_steps = 0
    unexpected_type_steps = 0
    watched_steps = 0
    for step in relevant_steps:
        # First calculate matches...
        actual = step.frames[0].values[variable_name]
        best_match = None
        matched_idx = None
        for idx, e in enumerate(expected):
            match_result = ComplexMatchResult(
                actual, e, step.step_index, False, context
            )
            if match_result.match_distance.is_zero():
                best_match = match_result
                matched_idx = idx
                break
            if (
                best_match is None
                or match_result.match_distance.cmp(best_match.match_distance) < 0
            ):
                best_match = match_result

        # Then calculate metric variables...
        watched_steps += 1
        if matched_idx is not None:
            seen_type_idxs.add(matched_idx)
            correct_steps += 1
        else:
            incorrect_steps += 1
        if not actual.could_evaluate:
            if actual.is_irretrievable or actual.is_optimized_away:
                missing_var_steps += 1
        elif matched_idx is None:
            unexpected_type_steps += 1
        seen_types = len(seen_type_idxs)
        missing_types = len(expected) - len(seen_type_idxs)

        # And finally produce the metrics map and add the new result to the list.
        metrics = {
            # The number of steps. Though this is not a useful metric in itself, it may be useful to see in tandem with
            # other variables.
            "total_watched_steps": ScalarMetric(watched_steps),
            # The number of steps where the expected value sequence was observed.
            "correct_steps": ScalarMetric(correct_steps),
            # The number of steps which did not match the expected value sequence.
            "incorrect_steps": ScalarMetric(incorrect_steps, improves_asc=False),
            # The number of steps where the watched variable/expression was not available in the debugger.
            "missing_var_steps": ScalarMetric(missing_var_steps, improves_asc=False),
            # The number of steps where the watched variable/expression had a value not in the set of expected values.
            "unexpected_type_steps": ScalarMetric(
                unexpected_type_steps, improves_asc=False
            ),
            # The % of steps where the expected value sequence was observed.
            "correct_step_coverage": FractionMetric(correct_steps, watched_steps),
            # The number of expected values that were observed at least once.
            "seen_types": ScalarMetric(seen_types),
            # The number of expected values that were not observed.
            "missing_types": ScalarMetric(missing_types, improves_asc=False),
        }
        results.append((step.step_index, best_match, metrics))
    return results


# Returns a list of the results after every relevant step, including the step index, the match result for that
# step, and the results after that step. The final metric results will be in the last element of the list.
def evaluate_value_steps(
    variable_name: str,
    expected,
    relevant_steps: list[StepIR],
    context: EvaluationContext,
) -> list[tuple[int, MatchResult, dict[str, Metric]]]:
    if not isinstance(expected, list):
        expected = [expected]

    results = []
    seen_value_idxs = set()
    correct_steps = 0
    incorrect_steps = 0
    missing_var_steps = 0
    unexpected_value_steps = 0
    watched_steps = 0
    for step in relevant_steps:
        # First calculate matches...
        if variable_name not in step.frames[0].values:
            print(f"Missing variable {variable_name} at step {step.step_index}")
            continue
        actual = step.frames[0].values[variable_name]
        best_match = None
        matched_idx = None
        for idx, e in enumerate(expected):
            match_result = ComplexMatchResult(actual, e, step.step_index, True, context)
            if (
                best_match is None
                or match_result.match_distance.cmp(best_match.match_distance) < 0
            ):
                best_match = match_result
                matched_idx = idx
                if match_result.match_distance.is_zero():
                    break
        # Then calculate metric variables...
        watched_steps += 1
        if match_result.match_distance.is_zero():
            seen_value_idxs.add(matched_idx)
            correct_steps += 1
        else:
            incorrect_steps += 1
        if not actual.could_evaluate:
            if actual.is_irretrievable or actual.is_optimized_away:
                missing_var_steps += 1
        elif matched_idx is None:
            unexpected_value_steps += 1
        seen_values = len(seen_value_idxs)
        missing_values = len(expected) - len(seen_value_idxs)
        # And finally produce the metrics map and add the new result to the list.
        metrics = {
            # The number of steps. Though this is not a useful metric in itself, it may be useful to see in tandem with
            # other variables.
            "total_watched_steps": ScalarMetric(watched_steps),
            # The number of steps where the expected value sequence was observed.
            "correct_steps": ScalarMetric(correct_steps),
            # The number of steps which did not match the expected value sequence.
            "incorrect_steps": ScalarMetric(incorrect_steps, improves_asc=False),
            # The number of steps where the watched variable/expression was not available in the debugger.
            "missing_var_steps": ScalarMetric(missing_var_steps, improves_asc=False),
            # The number of steps where the watched variable/expression had a value not in the set of expected values.
            "unexpected_value_steps": ScalarMetric(
                unexpected_value_steps, improves_asc=False
            ),
            # The number of steps where the watched variable/expression had a value in the set of expected values, but
            # out-of-order with the expected sequence.
            "misordered_value_steps": ScalarMetric(0, improves_asc=False),
            # The % of steps where the expected value sequence was observed.
            "correct_step_coverage": FractionMetric(correct_steps, watched_steps),
            # The edit distance between the expected and observed value sequences.
            "difference_from_expected": ScalarMetric(0, improves_asc=False),
            # The number of expected values that were observed at least once.
            "seen_values": ScalarMetric(seen_values),
            # The number of expected values that were not observed.
            "missing_values": ScalarMetric(missing_values, improves_asc=False),
        }
        results.append((step.step_index, best_match, metrics))
    return results


def evaluate_steps(
    expect: Expect, expected, relevant_steps: list[StepIR], context: EvaluationContext
) -> list[tuple[int, MatchResult, dict[str, Metric]]]:
    """Takes the given Expect along with its expected value and relevant steps, and returns the list of results by step:
    (step_index, match_result, metrics)."""
    if isinstance(expect, Value):
        return evaluate_value_steps(
            expect.variable_name, expected, relevant_steps, context
        )
    if isinstance(expect, Type):
        return evaluate_type_steps(
            expect.variable_name, expected, relevant_steps, context
        )
    assert isinstance(expect, Steps)
    return evaluate_step_steps(expected, relevant_steps, context)


def value_ir_to_expected(
    value: ValueIR,
    get_variable_result: Callable[[ValueIR], str | None],
    expand_arrays: bool = True,
    include_self: bool = False,
) -> Any | None:
    # No subvalues is the simple case - we return the observed value if one is present.
    if not value.sub_values:
        return get_variable_result(value)
    # If this value has subvalues (i.e. it's an aggregate) then we try and disaggregate it here.
    if value.is_irretrievable:
        return None
    result = {}
    for subv in value.sub_values:
        # If we don't care about every array element (e.g. we are looking at types), skip every array
        # subvalue except for [0].
        if (
            not expand_arrays
            and subv.expression.endswith("]")
            and not subv.expression.startswith("[0")
        ):
            continue
        sub_result = value_ir_to_expected(
            subv, get_variable_result, expand_arrays, include_self
        )
        # We only add valid results to the results dict.
        if sub_result is not None:
            result[subv.expression] = sub_result
    # If the result dict is empty, then there's nothing here to check - return now.
    if not result:
        # FIXME: If we have subvalues but still got nothing, then let's still record it for test purposes. We should
        # probably just return None though.
        return get_variable_result(value)
    elif include_self:
        # Add a Self() entry if desired.
        result[Self(" ")] = get_variable_result(value)
    return result


def get_expected_value_map(expect: Expect, scope: Scope, var_to_expected_values: dict[str, list[tuple[int, Any]]]) -> dict:
    """Takes a dict that maps variables to their observed step+values, with a value of None where no valid value was
    present, and produces a dict that maps line ranges to expected values, with the mapping key None used for any
    expected value sets that apply to the full scope."""
    # Finally we connect these maps, into a mapping of inclusive line ranges to the set of variables observed at those
    # ranges.
    result: dict[int | DexRange | None, dict] = defaultdict(dict)
    # FIXME: Should we just move this out of the function?
    scope_lines = (
        (scope_line_range.start, scope_line_range.stop - 1)
        if (scope_line_range := scope.get_line_range()) is not None
        else None
    )
    for var, expected_values in var_to_expected_values.items():
        assert expected_values
        sorted_lines = sorted(((expected_value[0], expected_value[1] is not None) for expected_value in expected_values), key=lambda lines_entry: lines_entry[0])
        # Find the line ranges without any invalid entries contained.
        line_ranges: list[tuple[int, int]] = []
        needs_new_range = True
        for line, is_valid in sorted_lines:
            if not is_valid:
                needs_new_range = True
                continue
            if needs_new_range:
                line_ranges.append((line, line))
                needs_new_range = False
            else:
                line_ranges[-1] = (line_ranges[-1][0], line)
        for min_line, max_line in line_ranges:
            if (min_line, max_line) == scope_lines:
                line_range = None
            elif min_line == max_line:
                line_range = min_line
            else:
                line_range = DexRange(min_line, max_line)
            values = uniquify(expected_value[1] for expected_value in var_to_expected_values[var] if expected_value[0] in range(min_line, max_line + 1))
            # Prefer a single value if possible.
            if isinstance(values, list) and len(values) == 1:
                values = values[0]

            result[line_range][expect.get_variable_expect(var)] = values

    return result

def get_step_values(expect: Steps, scope: Scope, relevant_steps: list[StepIR]):
    return [step.current_location.lineno for step in relevant_steps]

def get_var_values(expect: Expect, scope: Scope, relevant_steps: list[StepIR]):
    step_values = [step.current_frame.values[expect.get_watched_expr()] for step in relevant_steps]
    expected_values = [
        expected for value in step_values
        if (expected := value_ir_to_expected(value, expect.get_variable_result, expect.expand_arrays, expect.uses_this)) is not None]
    return uniquify(expected_values)

def get_scope_values(expect: All, scope: Scope, relevant_steps: list[StepIR]):
    ## We want to fill out our expects, such that we get a result for each scope variable seen at any point in
    ## relevant_steps.
    # First we want, for each variable, a list of steps at which it has a partially valid value, along with the
    # associated ValueIR.

    var_to_step_values: dict[str, dict[StepIR, ValueIR]] = defaultdict(dict)
    for step in relevant_steps:
        step_vars = step.current_frame.scopes.get(expect.get_watched_scope(), [])
        for var in step_vars:
            var_to_step_values[var][step] = step.current_frame.values[var]

    # Now we want, for each variable, an ordered uniqued list of the observed values, and the list of steps at which
    # that variable had a valid value observed.
    var_to_expected_values: dict[str, list[tuple[int, Any]]] = {}

    for var, step_values in var_to_step_values.items():
        expected_values: list[tuple[int, Any]] = []
        for step in relevant_steps:
            step_line = step.current_location.lineno
            if step not in step_values:
                expected_values.append((step_line, None))
                continue
            value = step_values[step]
            expected_value = value_ir_to_expected(
                value,
                expect.get_variable_result,
                expect.expand_arrays,
                expect.uses_this,
            )
            expected_values.append((step.current_location.lineno, expected_value))
        if expected_values:
            var_to_expected_values[var] = expected_values

    return get_expected_value_map(expect, scope, var_to_expected_values)

class ValueMatcher:
    def __init__(self, context):
        self.context = context

class ScopeVarMatcher:
    """Used to gather observed values for all variables of a given scope within a given set of steps, and produce a
    mapping of line ranges to Expects that would check for the observed values."""
    def __init__(self, context):
        self.context = context

class FullContext:
    def __init__(self, check_condition: Callable[[StepIR, int, str], bool]):
        self.match_context = MatchContext(check_condition)
        self.evaluate_context = EvaluationContext()

class ScriptTraceMatch:
    """Contains the complete matching state between a Script and a Trace as-of a particular step. Contains all the
    information needed to compute results at that step; this necessarily includes results from prior steps, while also
    explicitly defining the results that came from the most recent step. The full result of a trace can then be computed
    from the last ScriptTraceMatch."""

    def __init__(self, script: DexterScript, step: StepIR, context: FullContext, last_script_trace_match: "ScriptTraceMatch | None" = None):
        self.step_match = StepMatchResult(script, step, context.match_context)
        self.new_expect_matches: dict[Expect, tuple[int, MatchResult]] = {}
        self.expect_matches: dict[Expect, list[tuple[int, ComplexMatchResult]] | ListMatchResult] = {}
        for expect, expected, scope in self.step_match.active_expects:
            if not expected:
                # TODO: Merge the unknown value logic into here.
                continue
            if isinstance(expect, (Value, Type)):
                actual = step.frames[0].values.get(expect.get_watched_expr(), None)
                if actual is None:
                    continue
                if not isinstance(expected, list):
                    self.new_expect_matches[expect] = (None, ComplexMatchResult(actual, expected, step.step_index, isinstance(expect, Value), context.evaluate_context))
                    continue
                best_match = None
                for idx, e in enumerate(expected):
                    match_result = ComplexMatchResult(actual, e, step.step_index, True, context.evaluate_context)
                    if (
                        match_result.get_match_type() != MatchType.NONE and
                        (best_match is None or match_result.match_distance.cmp(best_match.match_distance) < 0)
                    ):
                        best_match = match_result
                        if match_result.match_distance.is_zero():
                            break
                self.new_expect_matches[expect] = (idx, best_match)
            else:
                actual = step.frames[0].loc.lineno
                # TODO: Make this make sense.
                self.new_expect_matches[expect] = (None, ListMatchResult([actual], expected, step.step_index))
        
        self.expect_matches = {expect: [match] for expect, match in self.new_expect_matches.items()}
        if last_script_trace_match is not None:
            for expect, matches in last_script_trace_match.expect_matches.items():
                if expect not in self.expect_matches:
                    self.expect_matches[expect] = []
                self.expect_matches[expect].extend(matches)


    def seen_values(self, new_only: bool = False) -> list[tuple[Expect, MatchResult]]:
        """Returns all Expects which have had at least a partial match; filter results by
        `match.get_match_type() == MatchType.WHOLE` to see Expects ."""
        if new_only:
            return [(expect, match) for expect, match in self.new_expect_matches.items()]
        return [(expect, match) for expect, matches in self.expect_matches.items() for match in matches]

    def get_visual_trace(self, script: DexterScript):
        """Test fn to demonstrate how we can use this to print a script and a trace; we print them here one after the
        other to avoid irrelevant complexities."""
        node_to_visual_node: dict[Any, VisualDexNode] = {}
        root_nodes: list[VisualDexNode] = []
        def add_child(node: Any, child: VisualDexNode, scope: Scope):
            node_to_visual_node[node] = child
            node_list = node_to_visual_node[scope.where].children if scope.where else root_nodes
            node_list.append(child)
        def visual_where(where: Where, scope: Scope):
            if where in self.step_match.active_wheres:
                status = VisualDexNodeStatus(where=True, active=True)
            elif where in self.step_match.where_frame_matches:
                status = VisualDexNodeStatus(where=True, stack=True)
            else:
                status = VisualDexNodeStatus(where=True, inactive=True)
            expected_node = VisualDexNode.NodeValue(status, f"{where}:")
            actual_node = VisualDexNode.NodeValue(status, f"{where}:")
            assert where != scope.where
            add_child(where, VisualDexNode(tag=str(where), values={"expected": expected_node, "actual": actual_node}), scope)
        def visual_expect(expect: Expect, expected, scope: Scope):
            def get_status(is_good: bool, is_bad: bool, is_value: bool, is_subvalue: bool) -> VisualDexNodeStatus:
                if is_good and not is_bad:
                    return VisualDexNodeStatus(expect=True, correct=True, value=is_value, subvalue=is_subvalue)
                elif is_good:
                    return VisualDexNodeStatus(expect=True, partial=True, value=is_value, subvalue=is_subvalue)
                return VisualDexNodeStatus(expect=True, incorrect=True, value=is_value, subvalue=is_subvalue)

            def build_complex_expected_node_value(expected: dict, tag: str, matches: list[ComplexMatchResult], is_active: bool) -> tuple[VisualDexNode, bool, bool]:
                """Builds a visual dex node for a single complex expected value (not a list).
                
                The resulting node will have an "expected" NodeValue of None, and should be used in the following ways:
                - If this node is the only expected value for its Expect, then its "expected" NodeValue should be set to
                  the Expect's text; if it is one of many, then each of them should be added as children of a new node
                  for the Expect.
                - If there is at least one actual value matched to this expected value, then the first actual should
                  have its NodeValue merged into this node, and all subsequent matched actuals should be siblings of
                  this node.
                """
                seen_leaf_nodes = set()
                def get_seen_leaf_values_for_submatch(path: tuple, submatch: Submatch) -> bool:
                    if submatch.match_type == MatchType.NONE:
                        return
                    if submatch.is_leaf:
                        seen_leaf_nodes.add(path)
                    else:
                        for name, subm in submatch.submatches.items():
                            get_seen_leaf_values_for_submatch(path + (name,), subm)
                for match in matches:
                    get_seen_leaf_values_for_submatch((), match.match_tree)
                
                def get_match_for_expected(path: tuple, node_value: str | None, expected) -> tuple[VisualDexNode, bool, bool]:
                    """Recursively create visual nodes for each expected value/subvalue.
                    Returns (node, is_good, is_bad)."""
                    if not isinstance(expected, dict):
                        is_good = path in seen_leaf_nodes
                        status = get_status(is_good, not is_good, True, node_value is not None)
                        value_node = VisualDexNode("value", {
                            "expected": VisualDexNode.NodeValue(status, str(expected))
                        })
                        key_node = VisualDexNode(node_value, {
                            "expected": VisualDexNode.NodeValue(status, node_value)
                        }, [value_node], children_on_same_line=True)
                        return (key_node, is_good, not is_good)
                    any_match = False
                    any_nonmatch = False
                    children = []
                    for k, v in expected.items():
                        k_node, is_good, is_bad = get_match_for_expected(path + (k,), f"{k}:", v)
                        children.append(k_node)
                        any_match = any_match or is_good
                        any_nonmatch = any_nonmatch or is_bad
                    node = VisualDexNode(node_value, {
                        "expected": VisualDexNode.NodeValue(get_status(any_match, any_nonmatch, True, node_value is not None), node_value)
                    }, children)
                    return (node, any_match, any_nonmatch)
                result, any_match, any_nonmatch = get_match_for_expected((), None, expected)
                result.tag = tag # TODO Pass a tag into `get_match_for_expected` without setting the NodeValue.
                return result, any_match, any_nonmatch
                
            def build_complex_actual_node_values(match: ComplexMatchResult, tag: str, is_active: bool) -> tuple[VisualDexNode, bool, bool]:
                """Returns a visual node for the given complex match."""
                def get_node_for_submatch(name: str | None, submatch: Submatch) -> tuple[VisualDexNode, bool, bool]:
                    if submatch.is_leaf:
                        is_good = submatch.match_type == MatchType.WHOLE
                        status = get_status(is_good, not is_good, True, name is not None)
                        value_node = VisualDexNode(name, {
                            "actual": VisualDexNode.NodeValue(status, submatch.leaf_value)
                        })
                        key_node = VisualDexNode(name, {
                            "actual": VisualDexNode.NodeValue(status, name)
                        }, [value_node], children_on_same_line=True)
                        return (key_node, is_good, not is_good)
                    any_match = False
                    any_nonmatch = False
                    children = []
                    for subm_name, subm in submatch.submatches.items():
                        subm_node, is_good, is_bad = get_node_for_submatch(f"{subm_name}:", subm)
                        children.append(subm_node)
                        any_match = any_match or is_good
                        any_nonmatch = any_nonmatch or is_bad
                    node = VisualDexNode(name, {
                        "actual": VisualDexNode.NodeValue(get_status(any_match, any_nonmatch, True, name is not None), name)
                    }, children)
                    return (node, any_match, any_nonmatch)
                result, any_match, any_nonmatch = get_node_for_submatch(None, match.match_tree)
                result.tag = tag
                return result, any_match, any_nonmatch

            expect_matches = self.expect_matches.get(expect, [])
            current_expected_idx, current_actual = self.new_expect_matches.get(expect, (None, None))

            if isinstance(expect, Steps):
                raise NotImplementedError("Visual Nodes for !steps not yet implemented")

            expected_match, expected_nonmatch = False, False
            actual_match, actual_nonmatch = False, False
            expect_nodes: list[VisualDexNode] = []
            def add_nodes_for_expected(tag, expected_value, actuals, expected_is_active):
                nonlocal expected_match, expected_nonmatch, actual_match, actual_nonmatch
                expected_node, e_match, e_nonmatch = build_complex_expected_node_value(expected_value, tag + "_0", actuals, expected_is_active)
                expected_match = expected_match or e_match
                expected_nonmatch = expected_nonmatch or e_nonmatch
                actual_nodes: list[VisualDexNode] = []
                for idx, actual in enumerate(actuals):
                    actual_node, a_match, a_nonmatch = build_complex_actual_node_values(actual, tag + f"_{idx}", actual == current_actual)
                    actual_match = actual_match or a_match
                    actual_nonmatch = actual_nonmatch or a_nonmatch
                    actual_nodes.append(actual_node)
                if actual_nodes:
                    # If we have at least one actual node, merge the first actual node with the expected node.
                    first_actual, actual_nodes = actual_nodes[0], actual_nodes[1:]
                    expected_node.merge(first_actual)
                expect_nodes.extend([expected_node] + actual_nodes)

            if isinstance(expected, list):
                # TODO extract some common logic from this if/else.
                for idx, expected_value in enumerate(expected):
                    actuals = uniquify([match for matched_idx, match in expect_matches if matched_idx == idx])
                    add_nodes_for_expected(str(idx), expected_value, actuals, idx == current_expected_idx)
            else:
                actuals = uniquify([match for _, match in expect_matches])
                add_nodes_for_expected("0", expected, actuals, True)
            
            expected_node = VisualDexNode.NodeValue(get_status(expected_match, expected_nonmatch, False, False), f"{expect}:")
            actual_node = VisualDexNode.NodeValue(get_status(actual_match, actual_nonmatch, False, False), f"{expect}:")
            add_child(expect, VisualDexNode(str(expect), {"expected": expected_node, "actual": actual_node}, expect_nodes), scope)
        def visual_then(then: Then, scope: Scope):
            status = VisualDexNodeStatus(then=True, active=True) if scope.where in self.step_match.active_wheres else VisualDexNodeStatus(then=True, inactive=True)
            expected_node = VisualDexNode.NodeValue(status, str(then))
            actual_node = VisualDexNode.NodeValue(status, str(then))
            add_child(then, VisualDexNode(str(then), values={"expected": expected_node, "actual": actual_node}), scope)
        script.visit_script(visit_where=visual_where, visit_expect=visual_expect, visit_then=visual_then)

        return VisualDexResult(root_nodes)

