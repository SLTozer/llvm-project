# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Utilities used to compare multiple DextIRs with an abstract sript and devise a concrete script that will accept all
of them."""

from collections import defaultdict
import re
from typing import Any, Callable
from dex.dextIR import DextIR, StepIR, ValueIR
from dex.test_script.Nodes import Address, All, DexRange, Expect, Float, Self
from dex.test_script.Script import Scope
from dex.test_script.StepMatcher import MatchContext, StepMatchResult
from dex.test_script.ValueMatcher import get_expected_value_map
from dex.evaluate.Evaluator import EvaluationContext, uniquify

# The percent difference threshold for joining float values.
maximum_float_pct_diff_threshold = 0.01
# The absolute difference threshold for joining float values.
maximum_float_abs_diff_threshold = 0.01


class JoiningContext:
    """Context object used when joining the results of Dexter test runs."""

    def __init__(self, num_runs: int):
        self.num_runs = num_runs
        # Tracks the mappings between labels and specific addresses (i.e. 0x[0-9A-F]{16}) for each run.
        self.label_to_address: dict[str, list[str]] = {}
        self.address_to_label: list[dict[str, list[str]]] = [
            defaultdict(list) for _ in range(num_runs)
        ]
        # Tracks the variables that make use of a given address.
        self.label_to_var: dict[str, set[str]] = defaultdict(set)
        self.labels: dict[str, int] = {}

def get_best_value_match(var: str, values: list[str], context: JoiningContext) -> Any | None:
    """For the given pair of values, attempts to find the best match between each of them, or returns None if no
    reasonable match can be found."""
    if not values or any(not v for v in values):
        return None
    assert (
        len(values) == context.num_runs
    ), "Didn't get a Value for every run being joined?"
    if all(v == values[0] for v in values[1:]):
        return values[0]

    # TODO: Finish implementing the below.
    # Attempt to join floats...
    try:
        float_values = [float(v) for v in values]
        try:
            [int(v) for v in values]
            is_integer = True
        except ValueError:
            is_integer = False
        if not is_integer:
            large, small = max(float_values), min(float_values)
            if (
                large - small < maximum_float_abs_diff_threshold
                or large * (1 - maximum_float_pct_diff_threshold) < small
            ):
                average = (large + small) / 2
                range = large - small
                return Float(values=average, range=range)
    except (FloatingPointError, ValueError):
        pass

    # Attempt to join addresses...
    def get_address(value: str):
        # TODO: Make this proper, possibly need to use ValueIRs?
        match = re.match("(0x[a-fA-F0-9]{16})( <(NULL|Bad Ptr)>)?", value)
        return match.group(1) if match else None

    addresses = [get_address(v) for v in values]
    if all(addresses):
        # First, check if all of them match an existing label; they may match more than one.
        matching_labels = [
            context.address_to_label[idx].get(address, [])
            for idx, address in enumerate(addresses)
        ]
        # TODO: When we support Address offsets, we need to check whether all addresses have the same offset from any
        # label as well.
        # Find the first label that matches all of the addresses, if any:
        for matching_label in matching_labels[0]:
            if all(matching_label in other_labels for other_labels in matching_labels[1:]):
                context.label_to_var[matching_label].add(var)
                return Address(matching_label)

        # If some addresses are null and others are not, ignore this for now.
        if any(address == "0x0000000000000000" for address in addresses):
            return None
        # Even if some addresses already match labels, we should assume that this is a coincidence if they do not all
        # match the same label, and create a new label to represent them here.
        attempted_namings = 0
        # FIXME: Maybe a real naming schema would help, especially since we may see identical variable names across
        #        different functions.
        while f"{var}_{attempted_namings}" in context.label_to_address:
            attempted_namings += 1
        new_label_name = f"{var}_{attempted_namings}"
        context.label_to_address[new_label_name] = addresses
        context.label_to_var[new_label_name].add(var)
        for run_idx, address in enumerate(addresses):
            context.address_to_label[run_idx][address].append(new_label_name)
        
    return None

def value_irs_to_expected(
    values: list[ValueIR],
    context: JoiningContext,
    get_variable_result: Callable[[ValueIR], str | None],
    expand_arrays: bool = True,
    include_self: bool = False,
) -> Any | None:
    expr = values[0].expression
    # FIXME: What should we do if we have at least one result with no subvalues, and at least one with? Right now the
    #        "lowest common denominator" approach (ignore all subvalues) makes sense, but is it correct?
    # No subvalues is the simple case - we return the observed value if one is present.
    if any(not value.sub_values for value in values):
        if all(not value.sub_values for value in values):
            variable_results = [get_variable_result(value) for value in values]
            # FIXME: Heuristic hack to stop us from evaluating abbreviated structs
            if any('...' in result for result in variable_results if result is not None):
                return None
            return get_best_value_match(expr, variable_results, context)
        return None

    if any(value.is_irretrievable for value in values):
        return None

    # If all values have subvalues then we try and disaggregate them here. Any subvalues which are not present for at
    # least one incoming value must be None; all others, we try to join.

    result = {}
    for subv in values[0].sub_values:
        # If we don't care about every array element (e.g. we are looking at types), skip every array
        # subvalue except for [0].
        if (
            not expand_arrays
            and subv.expression.endswith("]")
            and not subv.expression.startswith("[0")
        ):
            continue
        # We only care about subvalues that are present in every value; all others must be ignored.
        matching_subvs = [next((matching_subv for matching_subv in value.sub_values if matching_subv.expression == subv.expression), None) for value in values[1:]]
        if any(matching_subv is None for matching_subv in matching_subvs):
            continue
        sub_result = value_irs_to_expected(
            [subv] + matching_subvs, context, get_variable_result, expand_arrays, include_self
        )
        # We only add valid results to the results dict.
        if sub_result is not None:
            result[subv.expression] = sub_result
    # If the result dict is empty, then there's nothing here to check - return now.
    if not result:
        # FIXME: If we have subvalues but still got nothing, then let's still record it for test purposes. We should
        # probably just return None though.
        return get_best_value_match(expr, [get_variable_result(value) for value in values], context)
    elif include_self:
    # Add a Self() entry if desired.
        result[Self(" ")] = get_best_value_match(expr, [get_variable_result(value) for value in values], context)
    return result

def get_scope_values(expect: All, scope: Scope, relevant_steps_per_run: list[list[StepIR]], context: JoiningContext):
    # TODO: We're just assuming step-matching here, at some point we need a more well-defined approach.
    assert all(len(relevant_steps) == len(relevant_steps_per_run[0]) for relevant_steps in relevant_steps_per_run)
    ## We want to fill out our expects, such that we get a result for each scope variable seen at any point in
    ## relevant_steps.
    # First we want, for each variable, a list of steps at which it has a partially valid value, along with the
    # associated ValueIRs for each run.
    var_to_step_values: dict[str, dict[StepIR, list[ValueIR]]] = defaultdict(dict)
    for step_idx in range(len(relevant_steps_per_run[0])):
        step_per_run = [steps[step_idx] for steps in relevant_steps_per_run]
        base_step = step_per_run[0]
        step_vars = base_step.current_frame.scopes.get(expect.get_watched_scope(), [])
        for var in step_vars:
            var_to_step_values[var][base_step] = [step.current_frame.values[var] for step in step_per_run]

    # Now we want, for each variable, an ordered uniqued list of the observed values, and the list of steps at which
    # that variable had a valid value observed.
    var_to_expected_values: dict[str, list[tuple[int, Any]]] = {}

    for var, step_values in var_to_step_values.items():
        expected_values: list[tuple[int, Any]] = []
        for step in relevant_steps_per_run[0]:
            step_line = step.current_location.lineno
            if step not in step_values:
                expected_values.append((step_line, None))
                continue
            values = step_values[step]
            expected_value = value_irs_to_expected(
                values,
                context,
                expect.get_variable_result,
                expect.expand_arrays,
                expect.uses_this,
            )
            # TODO: Everything past this point is identical to the non-joining version of this function; there should be
            # room for deduplication.
            expected_values.append((step.current_location.lineno, expected_value))
        if expected_values:
            var_to_expected_values[var] = expected_values

    # Finally we connect these maps, into a mapping of inclusive line ranges to the set of variables observed at those
    # ranges.
    return get_expected_value_map(expect, scope, var_to_expected_values)

def join_scripts(run_dext_irs: list[DextIR], extra_script=None):
    if not run_dext_irs:
        return
    # assert all(run_dext_ir.script == run_dext_irs[0].script for run_dext_ir in run_dext_irs[1:]), "Scripts must be identical!"
    script = extra_script or run_dext_irs[0].script
    expects_and_scopes: list[tuple[Expect, Any, Scope]] = []
    reified_map = {}
    context = JoiningContext(len(run_dext_irs))

    def accumulate_expects(expect: Expect, expected_value, scope: Scope):
        expects_and_scopes.append((expect, expected_value, scope))

    script.visit_script(visit_expect=accumulate_expects)

    step_match_results_per_run: list[list[StepMatchResult]] = []

    def check_condition(step: StepIR, frame_idx: int, condition: str):
        cond_value = step.frames[frame_idx].values[condition]
        result = cond_value.could_evaluate and cond_value.value == "true"
        return result

    for dext_ir in run_dext_irs:
        match_context = MatchContext(check_condition=check_condition)
        step_where_matches = [
            StepMatchResult(script, step, match_context) for step in dext_ir.steps
        ]
        step_match_results_per_run.append(step_where_matches)

    # TODO: Either allow, or formally disallow scripts with different steps.
    for run_idx, dext_ir in enumerate(run_dext_irs):
        if run_idx == 0:
            continue
        for step_idx, step in enumerate(dext_ir.steps):
            base_step = run_dext_irs[0].steps[step_idx]
            assert base_step.current_location == step.current_location, f"Mismatched step locations at run {run_idx} step {step_idx}"
            base_run_active_wheres = step_match_results_per_run[0][step_idx].active_wheres.keys()
            run_active_wheres = step_match_results_per_run[run_idx][step_idx].active_wheres.keys()
            if base_run_active_wheres != run_active_wheres:
                print(base_run_active_wheres)
                print(run_active_wheres)
            assert base_run_active_wheres == run_active_wheres, f"Mismatched active wheres at run {run_idx} step {step_idx}"

    # For now, we assume/assert that each run must have an identical stepping pattern, as we're aiming to see
    # consistency in everything but the non-deterministic values.
    for expect, expected_value, scope in expects_and_scopes:
        context.labels = scope.labels
        relevant_steps_per_run = [
            [
                step
                for step_idx, step in enumerate(dext_ir.steps)
                if scope.where
                and scope.where in step_match_results_per_run[run_idx][step_idx].active_wheres
            ]
            for run_idx, dext_ir in enumerate(run_dext_irs)
        ]
        if isinstance(expect, All):
            reified_map[expect] = get_scope_values(
                expect, scope, relevant_steps_per_run, context
            )
            continue

        # Updating wildcards is a separate matter...
        if expected_value is None:
            # FIXME: We can add a "joined" version of this too later.
            # reified_map[expect] = expect.get_unknown_substitute_value(
            #     relevant_steps
            # )
            continue

    return script.resolve_script(reified_map)
