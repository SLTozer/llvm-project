# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Utilities used to compare/diff values of Dexter runs of the same script.
NB: This overlaps with RunDiff.py, but that file has a lot of step-related stuff so I'm just gonna separate them out for
now."""

from dataclasses import dataclass
from typing import Any
from dex.dextIR import DextIR, StepIR
from dex.evaluate.VisualDex import VisualDexNode, VisualDexNodeStatus, VisualDexResult
from dex.test_script.Nodes import Expect, Steps, Then, Where
from dex.test_script.Script import DexterScript, Scope
from dex.test_script.ValueMatcher import ComplexMatchResult, FullContext, MatchType, ScriptTraceMatch, Submatch, uniquify
from dex.tools.Main import Context


def get_visual_diff(script: DexterScript, base: ScriptTraceMatch, diff: ScriptTraceMatch) -> VisualDexResult:
    """Test fn to demonstrate how we can use this to print a script and a trace; we print them here one after the
    other to avoid irrelevant complexities."""
    node_to_visual_node: dict[Any, VisualDexNode] = {}
    root_nodes: list[VisualDexNode] = []
    def add_child(node: Any, child: VisualDexNode, scope: Scope):
        node_to_visual_node[node] = child
        node_list = node_to_visual_node[scope.where].children if scope.where else root_nodes
        node_list.append(child)
    def visual_where(where: Where, scope: Scope):
        def get_status(is_active: bool, is_stack: bool):
            if is_active:
                return VisualDexNodeStatus(where=True, active=True)
            elif is_stack:
                return VisualDexNodeStatus(where=True, stack=True)
            return VisualDexNodeStatus(where=True, inactive=True)
        
        base_status = get_status(where in base.step_match.active_wheres, where in base.step_match.where_frame_matches)
        diff_status = get_status(where in diff.step_match.active_wheres, where in diff.step_match.where_frame_matches)
        expected_status = get_status(base_status.active or diff_status.active, base_status.stack or diff_status.stack)
        expected_node = VisualDexNode.NodeValue(expected_status, f"{where}:")
        base_node = VisualDexNode.NodeValue(base_status, f"{where}:")
        diff_node = VisualDexNode.NodeValue(diff_status, f"{where}:")
        assert where != scope.where
        add_child(where, VisualDexNode(tag=str(where), values={"expected": expected_node, "base": base_node, "diff": diff_node}), scope)
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
            
        def build_complex_actual_node_values(value_name: str, match: ComplexMatchResult, tag: str, is_active: bool) -> tuple[VisualDexNode, bool, bool]:
            """Returns a visual node for the given complex match."""
            def get_node_for_submatch(name: str | None, submatch: Submatch) -> tuple[VisualDexNode, bool, bool]:
                if submatch.is_leaf:
                    is_good = submatch.match_type == MatchType.WHOLE
                    status = get_status(is_good, not is_good, True, name is not None)
                    value_node = VisualDexNode(name, {
                        value_name: VisualDexNode.NodeValue(status, submatch.leaf_value)
                    })
                    key_node = VisualDexNode(name, {
                        value_name: VisualDexNode.NodeValue(status, name)
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
                    value_name: VisualDexNode.NodeValue(get_status(any_match, any_nonmatch, True, name is not None), name)
                }, children)
                return (node, any_match, any_nonmatch)
            result, any_match, any_nonmatch = get_node_for_submatch(None, match.match_tree)
            result.tag = tag
            return result, any_match, any_nonmatch

        base_expect_matches = base.expect_matches.get(expect, [])
        base_current_expected_idx, current_base_actual = base.new_expect_matches.get(expect, (None, None))
        diff_expect_matches = diff.expect_matches.get(expect, [])
        diff_current_expected_idx, current_diff_actual = diff.new_expect_matches.get(expect, (None, None))

        if isinstance(expect, Steps):
            raise NotImplementedError("Visual Nodes for !steps not yet implemented")

        expected_match, expected_nonmatch = False, False
        base_actual_match, base_actual_nonmatch = False, False
        diff_actual_match, diff_actual_nonmatch = False, False
        expect_nodes: list[VisualDexNode] = []
        def add_nodes_for_expected(tag, expected_value, base_actuals, diff_actuals, expected_is_active):
            nonlocal expected_match, expected_nonmatch, base_actual_match, base_actual_nonmatch, diff_actual_match, diff_actual_nonmatch
            expected_node, e_match, e_nonmatch = build_complex_expected_node_value(expected_value, tag + "_0", base_actuals + diff_actuals, expected_is_active)
            expected_match = expected_match or e_match
            expected_nonmatch = expected_nonmatch or e_nonmatch
            base_actual_nodes: list[VisualDexNode] = []
            for idx, base_actual in enumerate(base_actuals):
                actual_node, a_match, a_nonmatch = build_complex_actual_node_values(
                    "base", base_actual, tag + f"_{idx}", base_actual == current_base_actual)
                base_actual_match = base_actual_match or a_match
                base_actual_nonmatch = base_actual_nonmatch or a_nonmatch
                base_actual_nodes.append(actual_node)
            if base_actual_nodes:
                # If we have at least one actual node, merge the first actual node with the expected node.
                first_base_actual, base_actual_nodes = base_actual_nodes[0], base_actual_nodes[1:]
                expected_node.merge(first_base_actual)
            diff_actual_nodes: list[VisualDexNode] = []
            for idx, diff_actual in enumerate(diff_actuals):
                diff_actual_node, a_match, a_nonmatch = build_complex_actual_node_values(
                    "diff", diff_actual, tag + f"_{idx}", diff_actual == current_diff_actual)
                diff_actual_match = diff_actual_match or a_match
                diff_actual_nonmatch = diff_actual_nonmatch or a_nonmatch
                diff_actual_nodes.append(diff_actual_node)
            if diff_actual_nodes:
                # If we have at least one diff_actual node, merge the first actual node with the expected node.
                first_diff_actual, diff_actual_nodes = diff_actual_nodes[0], diff_actual_nodes[1:]
                expected_node.merge(first_diff_actual)
            actual_nodes = []
            if base_actual_nodes and diff_actual_nodes:
                for idx, child in enumerate(base_actual_nodes):
                    if idx >= len(diff_actual_nodes):
                        break
                    child.merge(diff_actual_nodes[idx])
                if len(diff_actual_nodes) > len(base_actual_nodes):
                    base_actual_nodes.extend(diff_actual_nodes[len(base_actual_nodes):])
                actual_nodes = base_actual_nodes
            elif diff_actual_nodes:
                actual_nodes = diff_actual_nodes

            expect_nodes.extend([expected_node] + actual_nodes)

        if isinstance(expected, list):
            for idx, expected_value in enumerate(expected):
                base_actuals = uniquify([match for matched_idx, match in base_expect_matches if matched_idx == idx])
                diff_actuals = uniquify([match for matched_idx, match in diff_expect_matches if matched_idx == idx])
                add_nodes_for_expected(str(idx), expected_value, base_actuals, diff_actuals, idx == base_current_expected_idx or idx == diff_current_expected_idx)
        else:
            base_actuals = uniquify([match for _, match in base_expect_matches])
            diff_actuals = uniquify([match for _, match in diff_expect_matches])
            add_nodes_for_expected("0", expected, base_actuals, diff_actuals, current_base_actual is not None or current_diff_actual is not None)
        
        expected_node = VisualDexNode.NodeValue(get_status(expected_match, expected_nonmatch, False, False), f"{expect}:")
        base_node = VisualDexNode.NodeValue(get_status(base_actual_match, base_actual_nonmatch, False, False), f"{expect}:")
        diff_node = VisualDexNode.NodeValue(get_status(diff_actual_match, diff_actual_nonmatch, False, False), f"{expect}:")
        add_child(expect, VisualDexNode(str(expect), {"expected": expected_node, "base": base_node, "diff": diff_node}, expect_nodes), scope)
    def visual_then(then: Then, scope: Scope):
        def get_status(is_active: bool):
            return VisualDexNodeStatus(then=True, active=is_active, inactive=not is_active)
        base_status = get_status(scope.where in base.step_match.active_wheres)
        diff_status = get_status(scope.where in diff.step_match.active_wheres)
        expected_status = get_status(base_status.active or diff_status.active)
        expected_node = VisualDexNode.NodeValue(expected_status, str(then))
        base_node = VisualDexNode.NodeValue(base_status, str(then))
        diff_node = VisualDexNode.NodeValue(diff_status, str(then))
        add_child(then, VisualDexNode(str(then), values={"expected": expected_node, "base": base_node, "diff": diff_node}), scope)
    script.visit_script(visit_where=visual_where, visit_expect=visual_expect, visit_then=visual_then)

    return VisualDexResult(root_nodes)



def diff_scripts(context: Context, run_dext_irs: list[DextIR]) -> VisualDexResult:
    if not run_dext_irs:
        return
    assert len(run_dext_irs) == 2, "Just two scripts for now"
    def check_condition(step: StepIR, frame_idx: int, condition: str):
        cond_value = step.frames[frame_idx].values[condition]
        result = cond_value.could_evaluate and cond_value.value == "true"
        return result

    base = run_dext_irs[0]
    base_match_context = FullContext(check_condition=check_condition)
    base_trace_matches: list[ScriptTraceMatch] = []
    last_base_match = None
    for step in base.steps:
        next_match = ScriptTraceMatch(base.script, step, base_match_context, last_base_match)
        last_base_match = next_match
        base_trace_matches.append(next_match)

    diff = run_dext_irs[1]
    # TODO: See if this can be made unnecessary at some point, but for now it's necessary.
    diff.script = base.script
    diff_match_context = FullContext(check_condition=check_condition)
    diff_trace_matches: list[ScriptTraceMatch] = []
    last_diff_match = None
    for step in diff.steps:
        next_match = ScriptTraceMatch(diff.script, step, diff_match_context, last_diff_match)
        last_diff_match = next_match
        diff_trace_matches.append(next_match)
    
    base_match = base_trace_matches[-1]
    diff_match = diff_trace_matches[-1]
    return get_visual_diff(base.script, base_match, diff_match)
