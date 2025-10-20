# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Conditional Controller Class for DExTer.-"""


import os
import time
from collections import defaultdict
from itertools import chain

from dex.debugger.DebuggerControllers.ControllerHelpers import (
    in_source_file,
)
from dex.debugger.DebuggerControllers.DebuggerControllerBase import (
    DebuggerControllerBase,
)
from dex.debugger.DebuggerBase import DebuggerBase
from dex.test_script.Nodes import Expect, Scope, Then
from dex.test_script.Script import DexterScript
from dex.utils.Exceptions import DebuggerException
from dex.utils.Timeout import Timeout
from dex.dextIR import LocIR

class BreakpointRange:
    """A range of breakpoints and a set of conditions.

    The leading breakpoint (on line `range_from`) is always active.

    When the leading breakpoint is hit the trailing range should be activated
    when `expression` evaluates to any value in `values`. If there are no
    conditions (`expression` is None) then the trailing breakpoint range should
    always be activated upon hitting the leading breakpoint.

    Args:
       expression: None for no conditions, or a str expression to compare
       against `values`.

       hit_count: None for no limit, or int to set the number of times the
                  leading breakpoint is triggered before it is removed.
    """

    def __init__(
        self,
        expression: str,
        path: str,
        range_from: int,
        range_to: int,
        values: list,
        hit_count: int,
        finish_on_remove: bool,
        is_continue: bool = False,
        function: str = None,
        addr: str = None,
    ):
        self.expression = expression
        self.path = path
        self.function = function
        self.range_from = range_from
        self.range_to = range_to
        self.conditional_values = values
        self.max_hit_count = hit_count
        self.current_hit_count = 0
        self.finish_on_remove = finish_on_remove
        self.is_continue = is_continue
        self.function = function
        self.addr = addr

    def __repr__(self) -> str:
        items = []
        if self.expression:
            items.append(f"expression={self.expression}")
        if self.path:
            items.append(f"path={self.path}")
        if self.function:
            items.append(f"function={self.function}")
        if self.range_from:
            items.append(f"range_from={self.range_from}")
        if self.range_to:
            items.append(f"range_to={self.range_to}")
        if self.conditional_values:
            items.append(f"conditional_values={self.conditional_values}")
        if self.max_hit_count:
            items.append(f"max_hit_count={self.max_hit_count}")
        if self.current_hit_count:
            items.append(f"current_hit_count={self.current_hit_count}")
        if self.finish_on_remove:
            items.append(f"finish_on_remove={self.finish_on_remove}")
        if self.is_continue:
            items.append(f"is_continue={self.is_continue}")
        if self.function:
            items.append(f"function={self.function}")
        if self.addr:
            items.append(f"addr={self.addr}")
        return f"BP({', '.join(items)})"

    def limit_steps(
        expression: str,
        path: str,
        range_from: int,
        range_to: int,
        values: list,
        hit_count: int,
    ):
        return BreakpointRange(
            expression,
            path,
            range_from,
            range_to,
            values,
            hit_count,
            False,
        )

    def finish_test(
        expression: str, path: str, on_line: int, values: list, hit_count: int
    ):
        return BreakpointRange(
            expression,
            path,
            on_line,
            on_line,
            values,
            hit_count,
            True,
        )

    def continue_from_to(
        expression: str,
        path: str,
        from_line: int,
        to_line: int,
        values: list,
        hit_count: int,
    ):
        return BreakpointRange(
            expression,
            path,
            from_line,
            to_line,
            values,
            hit_count,
            finish_on_remove=False,
            is_continue=True,
        )

    def step_function(function: str, path: str, hit_count: int):
        return BreakpointRange(
            None,
            path,
            None,
            None,
            None,
            hit_count,
            finish_on_remove=False,
            is_continue=False,
            function=function,
        )

    def has_conditions(self):
        return self.expression is not None

    def get_conditional_expression_list(self):
        conditional_list = []
        for value in self.conditional_values:
            # (<expression>) == (<value>)
            conditional_expression = "({}) == ({})".format(self.expression, value)
            conditional_list.append(conditional_expression)
        return conditional_list

    def add_hit(self):
        self.current_hit_count += 1

    def should_be_removed(self):
        if self.max_hit_count is None:
            return False
        return self.current_hit_count >= self.max_hit_count


class ConditionalController(DebuggerControllerBase):
    def __init__(self, context, step_collection):
        self._bp_ranges = None
        self._watches = set()
        self._scope_watches = set()
        self._step_index = 0
        self._pause_between_steps = context.options.pause_between_steps
        self._max_steps = context.options.max_steps
        # Map {id: BreakpointRange}
        self._leading_bp_handles = {}
        super(ConditionalController, self).__init__(context, step_collection)
        script: DexterScript = self.step_collection.script
        self._get_bp_ranges()

    def _get_bp_ranges(self):
        self._bp_ranges = []

        visited_expect_scopes = set()
        visited_finish_scopes = set()
        visited_continue_scopes = set()

        def add_expect_bp_locs(expect: Expect, value, scope: Scope):
            checked_scope = scope
            # FIXME: This is trying to get around the case where we have a !where{fn}, with !where{lines} children that
            # are used simply to scope variable expects, but we set breakpoints for those lines that may not be
            # appropriate. We probably need some kind of continuous traversal up the chain of parent scopes to find the
            # outermost scope that should be used for breakpoints.
            # What we're trying to figure out here is whether the current scope is *subsumed* by a parent scope; in the
            # long term this should allow for nested function breakpoints, but I've yet to work out the full logic for
            # that.
            if scope.fn and scope.lines and scope.parent_scope.fn and not scope.parent_scope.lines:
                checked_scope = scope.parent_scope
            if scope.as_tuple() in visited_expect_scopes:
                return
            visited_expect_scopes.add(scope.as_tuple())
            if checked_scope.fn and not checked_scope.lines:
                # FIXME: By our design it should be possible to use conditional breakpoints here, and conditional
                # function breakpoints are supported by (at least some) debuggers.
                self._bp_ranges.append(
                    BreakpointRange.step_function(checked_scope.fn, checked_scope.file, checked_scope.for_hit_count))
            else:
                self._bp_ranges.append(
                    BreakpointRange.limit_steps(None, checked_scope.file, checked_scope.get_lines()[0],
                                                checked_scope.get_lines()[-1], None, checked_scope.for_hit_count))
        def add_then_bp_locs(then: Then, scope: Scope):
            if then.command == "finish":
                if scope.as_tuple() in visited_finish_scopes:
                    return
                visited_finish_scopes.add(scope.as_tuple())
                self._bp_ranges.append(
                    BreakpointRange.finish_test(None, scope.file, scope.get_lines()[0], None, scope.for_hit_count))
            elif then.command == "continue":
                if scope.as_tuple() in visited_continue_scopes:
                    return
                visited_continue_scopes.add(scope.as_tuple())
                # Continue commands should allow a "to" argument that determines where they continue up to.
                self._bp_ranges.append(
                    BreakpointRange.continue_from_to(None, scope.file, scope.get_lines()[0], None,
                                                        None, scope.for_hit_count))
            else:
                raise Exception(f"Bad command value for Then: {then.command}")
        
        script: DexterScript = self.step_collection.script
        script.visit_script(visit_expect=add_expect_bp_locs, visit_then=add_then_bp_locs)

    def _set_leading_bps(self):
        # Set a leading breakpoint for each BreakpointRange, building a
        # map of {leading bp id: BreakpointRange}.
        for bpr in self._bp_ranges:
            if bpr.has_conditions():
                # Add a conditional breakpoint for each condition.
                for cond_expr in bpr.get_conditional_expression_list():
                    id = self.debugger.add_conditional_breakpoint(
                        bpr.path, bpr.range_from, cond_expr
                    )
                    self._leading_bp_handles[id] = bpr
            elif bpr.function is not None:
                id = self.debugger.add_function_breakpoint(bpr.function)
                self._leading_bp_handles[id] = bpr
            else:
                # Add an unconditional breakpoint.
                id = self.debugger.add_breakpoint(bpr.path, bpr.range_from)
                self._leading_bp_handles[id] = bpr

    def _run_debugger_custom(self, cmdline):
        # TODO: Add conditional and unconditional breakpoint support to dbgeng.
        if self.debugger.get_name() == "dbgeng":
            raise DebuggerException(
                "Conditional stepping not supported by dbgeng"
            )

        self.step_collection.clear_steps()

        script: DexterScript = self.step_collection.script
        self._watches.update(script.get_watches())
        self._scope_watches.update(script.get_scope_watches())
        self._set_leading_bps()

        self.debugger.launch(cmdline)
        time.sleep(self._pause_between_steps)

        exit_desired = False
        timed_out = False
        total_timeout = Timeout(self.context.options.timeout_total)

        step_function_backtraces: list[list[str]] = []
        self.instr_bp_ids = set()

        print("BPs:")
        for bp in self._bp_ranges:
            print(f"  {bp}")
        while not self.debugger.is_finished:
            breakpoint_timeout = Timeout(self.context.options.timeout_breakpoint)
            while self.debugger.is_running and not timed_out:
                # Check to see whether we've timed out while we're waiting.
                if total_timeout.timed_out():
                    self.context.logger.error(
                        "Debugger session has been "
                        f"running for {total_timeout.elapsed}s, timeout reached!"
                    )
                    timed_out = True
                if breakpoint_timeout.timed_out():
                    self.context.logger.error(
                        f"Debugger session has not "
                        f"hit a breakpoint for {breakpoint_timeout.elapsed}s, timeout "
                        "reached!"
                    )
                    timed_out = True

            if timed_out or self.debugger.is_finished:
                break

            step_info = self.debugger.get_step_info(self._watches, self._scope_watches, self._step_index)
            backtrace = None
            if step_info.current_frame:
                backtrace = [f.function for f in step_info.frames]

            record_step = False
            debugger_continue = False
            bp_to_delete = []
            for bp_id in self.debugger.get_triggered_breakpoint_ids():
                try:
                    # See if this is one of our leading breakpoints.
                    bpr = self._leading_bp_handles[bp_id]
                    record_step = True
                except KeyError:
                    # This is a trailing bp. Mark it for removal.
                    bp_to_delete.append(bp_id)
                    if bp_id in self.instr_bp_ids:
                        self.instr_bp_ids.remove(bp_id)
                    else:
                        record_step = True
                    continue

                bpr.add_hit()
                if bpr.should_be_removed():
                    if bpr.finish_on_remove:
                        exit_desired = True
                    bp_to_delete.append(bp_id)
                    del self._leading_bp_handles[bp_id]

                if bpr.function is not None:
                    if step_info.frames:
                        # Add this backtrace to the stack. While the current
                        # backtrace matches the top of the stack we'll step,
                        # and while there's a backtrace in the stack that
                        # is a subset of the current backtrace we'll step-out.
                        if (
                            len(step_function_backtraces) == 0
                            or backtrace != step_function_backtraces[-1]
                        ):
                            # FIXME: This is a quick temp fix, may need an improved solution later on.
                            # If the function breakpoint for a target function lands in a function inlined into that
                            # target function, should remove the inlined function(s) from the step_function_backtrace,
                            # and adjust the instruction breakpoint accordingly.
                            def expected_matches_frame_fn(expected_fn, frame_fn):
                                if '(' in expected_fn and not '(' in frame_fn:
                                    expected_fn = expected_fn.split('(')[0]
                                if '(' in frame_fn and not '(' in expected_fn:
                                    frame_fn = frame_fn.split('(')[0]
                                return expected_fn == frame_fn
                            target_frame_idx = 0
                            print(bpr.function)
                            print(backtrace[target_frame_idx])
                            while not expected_matches_frame_fn(bpr.function, backtrace[target_frame_idx]):
                                target_frame_idx += 1
                                print(backtrace[target_frame_idx])

                            step_function_backtraces.append(backtrace[target_frame_idx:])

                            # Add an address breakpoint so we don't fall out
                            # the end of nested DexStepFunctions with a DexContinue.
                            addr = self.debugger.get_pc(frame_idx=target_frame_idx+1)
                            instr_id = self.debugger.add_instruction_breakpoint(addr)
                            # Note the breakpoint so we don't log the source location
                            # it in the trace later.
                            self.instr_bp_ids.add(instr_id)

                elif bpr.is_continue:
                    print("debugger continue")
                    debugger_continue = True
                    if bpr.range_to is not None:
                        self.debugger.add_breakpoint(bpr.path, bpr.range_to)

                else:
                    # Add a range of trailing breakpoints covering the lines
                    # requested in the DexLimitSteps command. Ignore first line as
                    # that's covered by the leading bp we just hit and include the
                    # final line.
                    for line in range(bpr.range_from + 1, bpr.range_to + 1):
                        id = self.debugger.add_breakpoint(bpr.path, line)

            # Remove any trailing or expired leading breakpoints we just hit.
            self.debugger.delete_breakpoints(bp_to_delete)

            debugger_next = False
            debugger_out = False
            if not debugger_continue and step_info.current_frame and step_info.frames:
                while len(step_function_backtraces) > 0:
                    match_subtrace = False  # Backtrace contains a target trace.
                    match_trace = False  # Backtrace matches top of target stack.

                    # The top of the step_function_backtraces stack contains a
                    # backtrace that we want to step through. Check if the
                    # current backtrace ("backtrace") either matches that trace
                    # or otherwise contains it.
                    target_backtrace = step_function_backtraces[-1]
                    if len(backtrace) >= len(target_backtrace):
                        match_trace = len(backtrace) == len(target_backtrace)
                        # Check if backtrace contains target_backtrace, matching
                        # from the end (bottom of call stack) backwards.
                        match_subtrace = (
                            backtrace[-len(target_backtrace) :] == target_backtrace
                        )

                    if match_trace:
                        # We want to step through this function; do so and
                        # log the steps in the step trace.
                        debugger_next = True
                        record_step = True
                        break
                    elif match_subtrace:
                        # There's a function we care about buried in the
                        # current backtrace. Step-out until we get to it.
                        debugger_out = True
                        break
                    else:
                        # Drop backtraces that are not match_subtraces of the current
                        # backtrace; the functions we wanted to step through
                        # there are no longer reachable.
                        step_function_backtraces.pop()

            if record_step and step_info.current_frame:
                self._step_index += 1
                # Record the step.
                # FIXME: Figure out if this is necessary for the script-model.
                # update_step_watches(
                #     step_info, self._watches, self.step_collection.commands
                # )
                self.step_collection.new_step(self.context, step_info)

            print ("end of step:")
            if step_info.frames:
                print (f"  step={step_info.frames[0].loc.lineno}")
            print (f"  record_step={record_step}")
            print (f"  exit_desired={exit_desired}")
            print (f"  debugger_continue={debugger_continue}")
            print (f"  debugger_next={debugger_next}")
            print (f"  debugger_out={debugger_out}")
            if exit_desired:
                break
            elif debugger_next:
                self.debugger.step_next()
            elif debugger_out:
                self.debugger.step_out()
            else:
                self.debugger.go()
            time.sleep(self._pause_between_steps)
