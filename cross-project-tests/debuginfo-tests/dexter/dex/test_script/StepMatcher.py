# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Contains the logic to match a StepIR with the Wheres of a DexterScript, allowing us to identify the currently active
Wheres, and track any relevant state to this matching."""

from collections import defaultdict
from enum import Enum
from typing import Any, Callable
from dex.dextIR import FrameIR, StepIR, StopReason
from dex.test_script.Nodes import Expect, Then, Where
from dex.test_script.Script import DexterScript, Scope

import os


# Summarizes the children of a !where node, including all child nodes (but not their children) and the resulting scope.
class WhereChildren:
    def __init__(self, scope: Scope):
        self.scope: Scope = scope
        self.wheres: list[Where] = []
        # TODO: Do we need the expected value, or just the expect?
        self.expects: list[tuple[Expect, Any]] = []
        self.thens: list[Then] = []


def paths_differ(expected: str, actual: str):
    normalized_expected: str = os.path.normcase(os.path.normpath(expected))
    normalized_second: str = os.path.normcase(os.path.normpath(actual))
    return not normalized_second.endswith(normalized_expected)


class FrameMatchResult(Enum):
    FALSE = 0
    TRUE = 1
    # Frame matches except for after_hit_count; needed to ensure that we count hits for such cases.
    EARLY = 2
    # Frame does not match yet, but we expect it to match at some point in this frame.
    ALMOST = 3


# A very simple matcher, returns True iff `where` matches `frame`.
def match_where_to_frame(
    where: Where,
    frame: FrameIR,
    where_hit_counts: dict[Where, int],
    check_condition: Callable[[str], bool],
) -> FrameMatchResult:
    if where.file is not None and paths_differ(where.file, frame.loc.path):
        return FrameMatchResult.FALSE
    if where.function is not None:
        fn = frame.function
        if "(" in fn:
            fn = fn.split("(")[0]
        if where.function != fn:
            return FrameMatchResult.FALSE
    if where.lines is not None:
        line_fail_result = FrameMatchResult.ALMOST if where.function else FrameMatchResult.FALSE
        if isinstance(where.lines, int):
            if where.lines != frame.loc.lineno:
                return line_fail_result
        elif frame.loc.lineno not in where.get_lines():
            return line_fail_result
    if where.for_hit_count is not None:
        after_hit_count = where.after_hit_count or 0
        if where_hit_counts[where] > where.for_hit_count + after_hit_count:
            return FrameMatchResult.FALSE
    if where.conditions is not None:
        cond_fail_result = FrameMatchResult.ALMOST if where.function else FrameMatchResult.FALSE
        if not check_condition(where.conditions):
            return cond_fail_result
    # NB: after_hit_count must be checked last, because the caller needs to know whether this where would match if not
    # for the after_hit_count, so that we can tally this as a "hit" in that case - otherwise we would never record hits
    # and thus could never pass an after_hit_count condition.
    if where.after_hit_count is not None:
        if where_hit_counts[where] <= where.after_hit_count:
            return FrameMatchResult.EARLY
    return FrameMatchResult.TRUE


class MatchContext:
    """Context object storing information relevant to matches across a Dexter run. After each StepMatchResult, this
    should be updated using that StepMatchResult and used as an input for the next match.
    """

    def __init__(self, check_condition: Callable[[StepIR, int, str], bool]):
        self._check_condition = check_condition
        self._condition_cache = {}
        self._last_match_result: "StepMatchResult" = None
        self._last_step: StepIR = None
        self.where_hit_counts: dict[Where, int] = defaultdict(int)
        # Set of Wheres that have reached their `for_hit_count` limit, and should no longer be hit.
        self.expired_wheres: set[Where] = set()

    def check_condition(self, step: StepIR, frame_idx: int, condition: str) -> bool:
        """Returns the result of evaluating the condition at the given frame index in the current step.
        Implements caching over the originally-provided function."""
        if (frame_idx, condition) in self._condition_cache:
            return self._condition_cache[(frame_idx, condition)]
        result = self._check_condition(step, frame_idx, condition)
        self._condition_cache[(frame_idx, condition)] = result
        return result

    def try_increment_where_hit_count(self, step: StepIR, where: Where) -> bool:
        """For a Where that is currently Early/Active, increments the hit_count if it is correct to do so, i.e. we have
        just entered/re-entered the Where (but not when we are just lingering there).
        Returns True if the hit_count is incremented."""
        # Here we update the match_context hit counts according to the active Wheres recorded here. For function-Wheres,
        # we simply increment hit counts when the function breakpoint was hit. For line-Wheres, we count them as hit
        # when we enter them after having left that line range within the current frame, or when entering them from a
        # lower frame (i.e. we step immediately into that line range when we call the containing function).
        # TODO: Fully implement the above - we're taking a simplified approach to line-Wheres here right now as we don't
        # have any real use cases for multiline-Wheres right now.
        should_increment = False
        if where.function and not where.lines:
            # Function-Wheres:
            # TODO: This is incomplete, we need to check that the reason we stopped was hitting the Function-Where's
            # breakpoint, which may require additional context to be passed in here.
            if step.hit_fn_bp:
                should_increment = True
        elif len(where.get_lines()) == 1:
            # Single-line-Wheres:
            should_increment = True
        elif self._last_match_result is not None:
            if where not in self._last_match_result.active_wheres and where not in self._last_match_result.early_wheres:
                should_increment = True
        else:
            should_increment = True
        
        if should_increment:
            self.where_hit_counts[where] += 1
            new_hit_count = self.where_hit_counts[where]
            if where.for_hit_count and new_hit_count >= where.for_hit_count + (
                where.after_hit_count or 0
            ):
                self.expired_wheres.add(where)
        return should_increment


    def update_for_step(self, step: StepIR, new_match_result: "StepMatchResult"):
        """Updates this context for the next step."""
        # TODO: In general, we probably don't actually want to reevaluate conditions on frames below the current frame.
        # We could change this to only clear conditions checked at the current frame - but then we're in the awkward
        # position that Dexter's behaviour *relies* on this cache sometimes being invalid. That might not be a bad
        # thing, but it feels wrong for a so-called "cache".
        self._condition_cache = {}
        self._last_match_result = new_match_result
        self._last_step = step


class StepMatchResult:
    """Represents the result of matching the given DexterScript against the given StepIR, used both for running a
    debugger session and for evaluating the result of a test. Uses and also updates the provided MatchContext.
    """

    def __init__(self, script: DexterScript, step: StepIR, match_context: MatchContext):
        self.where_frame_matches: dict[Where, int] = {}
        self.active_wheres: dict[Where, WhereChildren] = {}
        # Wheres that would be hit but have not due to their `after_hit_count` field.
        self.early_wheres: set[Where] = set()
        # Wheres that may become active in the current frame but are not currently active.
        # TODO: This feels a bit special-case-y, is there a way it can be made less so?
        self.almost_wheres: set[Where] = set()
        self._evaluate(script, step, match_context)


    # FIXME: It may be that this function needs to merge into match_where_to_frame, or that the hit_count logic needs
    # some rethinking, but for now this is a suitable stopgap.
    def _update_and_recheck_hitcount(self, step: StepIR, old_result: FrameMatchResult, where: Where, match_context: MatchContext) -> FrameMatchResult:
        """After we have successfully matched a Where to a frame, this function updates the hit_count of the Where and
        checks the hit_counts again, potentially changing the result from Early to True, or True to False."""
        # Results other than Early or True cannot be changed.
        if old_result != FrameMatchResult.EARLY and old_result != FrameMatchResult.TRUE:
            return old_result
        # Wheres with no for/after hit count cannot be changed.
        if where.for_hit_count is None and where.after_hit_count is None:
            return old_result
        # Otherwise, we have an interest in updating the hit count, and it may change the match result.
        changed = match_context.try_increment_where_hit_count(step, where)
        if not changed:
            return old_result
        # Now check again to see if the result of matching this Where has changed.
        if where.for_hit_count is not None:
            after_hit_count = where.after_hit_count or 0
            if match_context.where_hit_counts[where] > where.for_hit_count + after_hit_count:
                return FrameMatchResult.FALSE

        if where.after_hit_count is not None:
            if match_context.where_hit_counts[where] <= where.after_hit_count:
                return FrameMatchResult.EARLY
        
        return FrameMatchResult.TRUE

    def _evaluate(
        self, script: DexterScript, step: StepIR, match_context: MatchContext
    ):
        """Performs the matching logic, storing the results in this object's members."""
        # Determines whether the given Where matches either its parent Where's frame or the frame below it, or if
        # parent_frame_idx=None then we find the first matching frame from the bottom of the stack to the top. If a match
        # is found, we accumulate the Where (and its children if it is active at frame 0) to the result dicts.
        def traverse(
            where: Where,
            children: dict | Then,
            scope: Scope,
            parent_frame_idx: int | None,
        ):
            # First, check whether this Where matches at all, either in its parent's frame or in the frame above it.
            if parent_frame_idx is None:
                matched_frame_idx = None
                for frame_idx in reversed(range(step.num_frames)):
                    match_result = match_where_to_frame(
                        where,
                        step.frames[frame_idx],
                        match_context.where_hit_counts,
                        check_condition=lambda cond: match_context.check_condition(step, frame_idx, cond),
                    )
                    if frame_idx == 0:
                        match_result = self._update_and_recheck_hitcount(step, match_result, where, match_context)
                    if match_result == FrameMatchResult.TRUE:
                        matched_frame_idx = frame_idx
                        break
                    elif match_result == FrameMatchResult.EARLY:
                        self.early_wheres.add(where)
                        return
                    elif match_result == FrameMatchResult.ALMOST:
                        self.almost_wheres.add(where)
                        return
                if matched_frame_idx is None:
                    return
            else:
                if where.is_and:
                    match_result = match_where_to_frame(
                        where,
                        step.frames[parent_frame_idx],
                        match_context.where_hit_counts,
                        check_condition=lambda cond: match_context.check_condition(step, parent_frame_idx, cond),
                    )
                    if parent_frame_idx == 0:
                        match_result = self._update_and_recheck_hitcount(step, match_result, where, match_context)
                    if match_result == FrameMatchResult.TRUE:
                        matched_frame_idx = parent_frame_idx
                elif parent_frame_idx > 0:
                    match_result = match_where_to_frame(
                        where,
                        step.frames[parent_frame_idx - 1],
                        match_context.where_hit_counts,
                        check_condition=lambda cond: match_context.check_condition(step, parent_frame_idx - 1, cond),
                    )
                    if parent_frame_idx - 1 == 0:
                        match_result = self._update_and_recheck_hitcount(step, match_result, where, match_context)
                    if match_result == FrameMatchResult.TRUE:
                        matched_frame_idx = parent_frame_idx - 1
                else:
                    match_result = FrameMatchResult.FALSE
                if match_result == FrameMatchResult.EARLY:
                    self.early_wheres.add(where)
                elif match_result == FrameMatchResult.ALMOST:
                    self.almost_wheres.add(where)
                if match_result != FrameMatchResult.TRUE:
                    return
            # We match - note it in the frame_matches dict.
            self.where_frame_matches[where] = matched_frame_idx
            # Now we traverse the children of this Where. If it is inactive, we only search for child Wheres; if it is
            # active, we also accumulate all Expects and Thens.
            is_active = matched_frame_idx == 0
            if is_active:
                where_children = WhereChildren(scope.add_where(where, script.per_file_labels))
                self.active_wheres[where] = where_children
            # Thens can appear as the direct children of Wheres, which is the only case where `children` is not a dict.
            if isinstance(children, Then):
                if is_active:
                    where_children.thens.append(children)
                return
            for child, grandchild in children.items():
                if isinstance(child, Where):
                    traverse(
                        child, grandchild, scope.add_where(where, script.per_file_labels), matched_frame_idx
                    )
                if not is_active:
                    continue
                if isinstance(child, Where):
                    where_children.wheres.append(child)
                elif isinstance(child, Expect):
                    where_children.expects.append((child, grandchild))
                else:
                    if not isinstance(child, Then):
                        print(child)
                    if isinstance(child, Then):
                        where_children.thens.append(child)

        for node, child in script.script_obj.items():
            if not isinstance(node, Where):
                continue
            traverse(node, child, script.root_scope, None)

        match_context.update_for_step(step, self)

    @property
    def active_thens(self) -> list[tuple[Then, Scope]]:
        """Returns the list of Thens that are active at this step, and should be executed."""
        return [
            (then, children.scope)
            for children in self.active_wheres.values()
            for then in children.thens
        ]

    @property
    def active_expects(self) -> list[tuple[Expect, Any, Scope]]:
        """Returns the list of Expects that are active at this step, and should have their observed values recorded."""
        return [
            (expect, expected_result, children.scope)
            for children in self.active_wheres.values()
            for expect, expected_result in children.expects
        ]

    @property
    def available_wheres(self) -> list[tuple[Where, Scope]]:
        """Returns the list of Wheres that are available at this step, meaning that their parent Where is active and
        therefore we may wish to set breakpoints for them."""
        return [
            (where, children.scope)
            for children in self.active_wheres.values()
            for where in children.wheres
        ]
