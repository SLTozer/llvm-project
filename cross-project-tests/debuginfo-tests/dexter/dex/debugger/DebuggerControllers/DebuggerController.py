# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Debugger Controller Class for DExTer, responsible for driving a debugger session, invoking debugger actions and
recording debugger output."""


from enum import Enum
import time
from collections import defaultdict
from itertools import chain

from dex.debugger.DebuggerControllers.Utils import SkipLoopState
from dex.debugger.DebuggerBase import DebuggerBase, ScopeStepExpectInfo, StepExpectInfo
from dex.test_script.StepMatcher import MatchContext, StepMatchResult
from dex.test_script.Nodes import Where
from dex.test_script.Script import DexterScript, Scope
from dex.utils.Timeout import Timeout
from dex.dextIR import StepIR


class DebuggerAction(Enum):
    STEP = 0
    STEP_OUT = 1
    CONTINUE = 2
    EXIT = 3


class WhereBreakpointIDs:
    """Stores the Entry and Return breakpoint IDs for a given Where."""

    def __init__(self):
        self.entry_bp: int | None = None
        self.return_bp: int | None = None


class DebuggerController:
    def __init__(self, context, step_collection):
        self.context = context
        self.step_collection = step_collection
        # Maps Wheres to the IDs of their associated breakpoints.
        # First breakpoint is used for entering the Where (i.e. a function breakpoint), the second breakpoint is used
        # for returning to that Where from a higher stackframe.
        self._where_bps: dict[Where, WhereBreakpointIDs] = {}
        # Reverse dict of the above.
        self._bp_to_where: dict[int, Where] = {}
        # Tracks oneshot BPs, along with their associated path+line/address, allowing us to remove them when they are
        # hit (even if the debugger does not report the breakpoint as hit).
        self._oneshot_loc_bps: dict[int, tuple[str, int]] = {}
        self._oneshot_instr_bps: dict[int, str] = {}
        self._watches = set()
        self._scope_watches = set()
        self._step_index = 0
        self._record_steps_without_expects = (
            context.options.record_steps_without_expects
        )
        self._record_all_steps = context.options.record_all_steps
        self._pause_between_steps = context.options.pause_between_steps
        self._max_steps = context.options.max_steps

    def run_debugger(self, debugger):
        """Responsible for correctly launching and tearing down the debugger."""
        self.debugger: DebuggerBase = debugger

        # Fetch command line options, if any.
        the_cmdline = []
        cmd_lines = self.step_collection.script.get_cmd_line_directives()
        if cmd_lines:
            the_cmdline = list(chain.from_iterable(cmd_lines))

        with self.debugger:
            if not self.debugger.loading_error:
                self._run_debugger(the_cmdline)

        # We may need to pickle this debugger controller after running the
        # debugger. Debuggers are not picklable objects, so set to None.
        self.debugger = None

    def add_where_entry_bp(self, where: Where, scope: Scope) -> int:
        """Adds a breakpoint to catch when we enter the given Where.
        Tracks the new breakpoint in the relevant maps and returns its ID."""
        id = None
        file = where.get_file() or scope.get_file()
        if where.function:
            id = self.debugger.add_function_breakpoint(where.function)
        elif where.lines and not scope.fn:
            # If this Where covers some lines *and* it is not wrapped in a function (in which case we will naturally step to this Where anyway).
            assert file, "Cannot set line breakpoints without a valid file!"
            # FIXME: We actually need to set breakpoints for the whole range...
            id = self.debugger.add_breakpoint(file, where.get_lines()[0])
        if id != None:
            self._bp_to_where[id] = where
            self._where_bps[where].entry_bp = id
        return id

    def add_where_return_bp(self, where: Where, address: str) -> int:
        """Adds a breakpoint to catch when we return to the given Where from a function above it on the stack.
        Tracks the new breakpoint in the relevant maps and returns its ID."""
        assert (
            where.function
        ), "Return breakpoints are only relevant for function-level Wheres."
        id = self.debugger.add_instruction_breakpoint(address)
        self._bp_to_where[id] = where
        self._where_bps[where].return_bp = id
        self._oneshot_instr_bps[id] = address
        return id

    def _init_bps(self):
        self._where_bps = defaultdict(WhereBreakpointIDs)
        script: DexterScript = self.step_collection.script
        for node in script.script_obj:
            if not isinstance(node, Where):
                continue
            id = self.add_where_entry_bp(node, script.root_scope)
            if id is not None:
                self.context.logger.trace(f"Added Entry BP {id} for {node}")

    def _update_breakpoints(
        self,
        script: DexterScript,
        step_info: StepIR,
        step_match_result: StepMatchResult,
        match_context: MatchContext,
        triggered_breakpoints: list[int],
        will_continue: bool,
    ):
        ## Now we determine any breakpoints that we need to set or delete.
        bp_to_delete = []
        root_wheres = script.root_wheres
        # Remove old/expired Entry/Return BPs.
        for where, where_bps in self._where_bps.items():
            if where_bps.entry_bp is not None:
                if (
                    (where not in root_wheres or where in match_context.expired_wheres)
                    and where not in step_match_result.where_frame_matches
                    and all(where != av_where for av_where, _ in step_match_result.available_wheres)
                ):
                    self.context.logger.trace(
                        f"Removing Entry BP {where_bps.entry_bp} for {where}"
                    )
                    bp_to_delete.append(where_bps.entry_bp)
                    del self._bp_to_where[where_bps.entry_bp]
                    where_bps.entry_bp = None
            if where_bps.return_bp is not None:
                if where not in step_match_result.where_frame_matches:
                    assert (
                        where_bps.return_bp not in triggered_breakpoints
                    ), "Return BP for a Where triggered while that Where does not match any frame?"
                    self.context.logger.trace(
                        f"Removing Return BP {where_bps.return_bp} for {where}"
                    )
                    bp_to_delete.append(where_bps.return_bp)
                    del self._bp_to_where[where_bps.return_bp]
                    del self._oneshot_instr_bps[where_bps.return_bp]
                    where_bps.return_bp = None
        # Set new Entry BPs, unless we are are looking to continue past any available Wheres.
        if not will_continue:
            for where, scope in step_match_result.available_wheres:
                # We never set entry breakpoints for expired Wheres.
                if where in match_context.expired_wheres:
                    continue
                if self._where_bps[where].entry_bp is None:
                    id = self.add_where_entry_bp(where, scope)
                    if id is not None:
                        self.context.logger.trace(f"Added Entry BP {id} for {where}")
        else:
            for where, where_bps in self._where_bps.items():
                if where_bps.entry_bp is not None:
                    self.context.logger.trace(
                        f"Removing Entry BP {where_bps.entry_bp} for {where}"
                    )
                    bp_to_delete.append(where_bps.entry_bp)
                    del self._bp_to_where[where_bps.entry_bp]
                    where_bps.entry_bp = None


        # Set new Return BPs.
        # for where, frame_idx in step_match_result.where_frame_matches.items():
        #     if (
        #         frame_idx > 0
        #         and where.function
        #         and self._where_bps[where].return_bp is None
        #     ):
        #         # Get the instruction address at the Where's frame if necessary...
        #         if step_info.frames[frame_idx].instruction_addr is None:
        #             step_info.frames[frame_idx].instruction_addr = self.debugger.get_pc(
        #                 frame_idx
        #             )
        #         addr = step_info.frames[frame_idx].instruction_addr
        #         id = self.add_where_return_bp(where, addr)
        #         if id is not None:
        #             self.context.logger.trace(f"Added Return BP {id} for {where}")

        # Remove any oneshot breakpoints that have been hit.
        for bp_id in triggered_breakpoints:
            if (
                is_instr := bp_id in self._oneshot_instr_bps
            ) or bp_id in self._oneshot_loc_bps:
                bp_to_delete.append(bp_id)
                self.context.logger.trace(f"Removing triggered BP {bp_id}")
                if is_instr:
                    if bp_id in self._bp_to_where:
                        where = self._bp_to_where[bp_id]
                        self._where_bps[where].return_bp = None
                        del self._bp_to_where[bp_id]
                    del self._oneshot_instr_bps[bp_id]
                else:
                    del self._oneshot_loc_bps[bp_id]
                continue

        # Remove any trailing or expired leading breakpoints we just hit.
        self.debugger.delete_breakpoints(bp_to_delete)

    def _check_condition(self, step: StepIR, frame_idx: int, condition: str):
        """Evaluates the given condition at the given frame index. Requires the debugger session to be alive and the
        debuggee must be stopped."""
        cond_value = self.debugger.evaluate_expression(condition, frame_idx)
        step.frames[frame_idx].values[condition] = cond_value
        # FIXME: This is a language-specific test (albeit it covers all languages Dexter is currently used with).
        return cond_value.could_evaluate and cond_value.value == "true"

    def _run_debugger(self, cmdline):
        if self.debugger.get_name() == "dbgeng":
            self.context.logger.warning(
                "Using incomplete debugger implementation 'dbgeng', errors may occur."
            )

        self.step_collection.clear_steps()

        script: DexterScript = self.step_collection.script
        self._init_bps()

        self.debugger.launch(cmdline)
        time.sleep(self._pause_between_steps)

        timed_out = False
        total_timeout = Timeout(self.context.options.timeout_total)

        # Stack used to track state for instruction addresses in each call of each function, so that we can skip over
        # loops if desired.
        skip_loop_state = SkipLoopState(self.context.options.skip_loops_after)
        # Context object used for matching the DexterScript to each StepIR.
        step_info: StepIR = None
        match_context = MatchContext(check_condition=self._check_condition)
        while not self.debugger.is_finished:
            ## Check for timeouts.
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

            ## Fetch frame information and breakpoint information from the debugger.
            step_info: StepIR = self.debugger.get_stack_frames(self._step_index)

            triggered_breakpoints: list = self.debugger.get_triggered_breakpoint_ids()
            # In some cases, for some debuggers, we may have landed on a breakpoint but not have a "breakpoint"
            # stop_reason. In these cases, we manually check whether any of our oneshot breakpoints have been hit.
            if step_info.current_frame:
                for bp_id, bp_loc in self._oneshot_loc_bps.items():
                    path, line = bp_loc
                    if bp_id in triggered_breakpoints:
                        continue
                    if (
                        path == step_info.current_location.path
                        and line == step_info.current_location.lineno
                    ):
                        triggered_breakpoints.add(bp_id)
                if step_info.frames[0].instruction_addr is not None:
                    addr = step_info.frames[0].instruction_addr.upper()
                    for bp_id, bp_addr in self._oneshot_instr_bps.items():
                        if bp_addr.upper() == addr:
                            triggered_breakpoints.add(bp_id)

            step_info.hit_fn_bp = any(where for where, where_bps in self._where_bps.items() if where_bps.entry_bp in triggered_breakpoints)

            ## Use the acquired frame information to determine which Wheres are active.
            step_match_result = StepMatchResult(script, step_info, match_context)

            # should_record=True if we want to record the current step
            if self._record_steps_without_expects:
                should_record = any(step_match_result.active_wheres) or any(
                    step_match_result.early_wheres
                )
            elif len(step_match_result.active_wheres) > 0:
                # We record steps that have a "Then" even if there are no "Expects", since if we executed a Then
                # directive we'll want to see the step where that occurred in the output.
                should_record = (
                    any(step_match_result.active_expects)
                    or any(step_match_result.active_thens)
                    or any(step_match_result.early_wheres)
                )
            else:
                should_record = False
            next_action: DebuggerAction | None = None

            # If skip_loops_after has been set, check now to see whether we should be
            if self.context.options.skip_loops_after:
                skip_bp_loc = skip_loop_state.update_state_for_current_step(step_info)
                if skip_bp_loc is not None:
                    bp_path, bp_line = skip_bp_loc
                    should_record = False
                    next_action = DebuggerAction.CONTINUE
                    bp_id = self.debugger.add_breakpoint(bp_path, bp_line)
                    # Track the breakpoint in our oneshot list so that we can delete it when it's hit.
                    self._oneshot_loc_bps[bp_id] = (bp_path, bp_line)

            if self._record_all_steps:
                should_record = True

            # Our stepping behaviour is as follows:
            # - If we have hit an explicit control (e.g. !then continue), we follow that control.
            # - If we are in a function with a Where (whether that Where is active or not), we step with next().
            #   FIXME: Does the above really make sense? If all Wheres have breakpoints upon entry (either a function
            #   breakpoint or a set of line breakpoints) then we don't need to `next`, we can just continue/step out.
            # - If we are not in a function with a Where, but there is at least one stackframe that matches a Where, we step out.
            # - If there are no stackframes that match any Wheres but there are non-expired root Wheres, we continue.
            # - If all root Wheres are expired we exit.
            if should_record:
                for then, scope in step_match_result.active_thens:
                    if then.command == "continue":
                        next_action = DebuggerAction.STEP_OUT
                    elif then.command == "skip_to":
                        to_line = int(then.args[0])
                        bp_id = self.debugger.add_breakpoint(
                            step_info.current_location.path, to_line
                        )
                        # Add the breakpoint to the range so we can manually check if it gets hit.
                        self._oneshot_loc_bps[bp_id] = (
                            step_info.current_location.path,
                            to_line,
                        )
                        next_action = DebuggerAction.CONTINUE
                    elif then.command == "finish":
                        next_action = DebuggerAction.EXIT
                        # Stop processing `then` directives, they'll all be lower priority than exiting the program!
                        break

                watches = []
                scope_watches = []
                for expect, expected_result, scope in step_match_result.active_expects:
                    if watched_expr := expect.get_watched_expr():
                        watches.append(StepExpectInfo(watched_expr, scope.file, 0, scope.get_line_range()))
                    elif watched_scope := expect.get_watched_scope():
                        scope_watches.append(
                            ScopeStepExpectInfo(
                                watched_scope, scope.file, 0, scope.get_line_range()
                            )
                        )
                if watches or scope_watches:
                    self.debugger.collect_watches(step_info, watches, scope_watches)

            # Decide how we are going to step. If we've already set an action, then we continue. Otherwise:
            # - If there is an active Where, we step normally.
            # - If there is a Where matching a stackframe above 0, we step out.
            # - Otherwise, continue.
            if next_action is None:
                if step_match_result.active_wheres or step_match_result.almost_wheres:
                    next_action = DebuggerAction.STEP
                elif step_match_result.where_frame_matches:
                    next_action = DebuggerAction.STEP_OUT
                elif all(
                    where in match_context.expired_wheres
                    for where in script.root_wheres
                ):
                    next_action = DebuggerAction.EXIT
                else:
                    next_action = DebuggerAction.CONTINUE

            ## Now we determine any breakpoints that we need to set or delete.
            self._update_breakpoints(
                script,
                step_info,
                step_match_result,
                match_context,
                triggered_breakpoints,
                next_action == DebuggerAction.CONTINUE or next_action == DebuggerAction.STEP_OUT,
            )

            if should_record and step_info.current_frame:
                self._step_index += 1
                # Record the step in step_collection.
                self.step_collection.new_step(self.context, step_info)
                if self._step_index > self._max_steps:
                    next_action = DebuggerAction.EXIT

            # If we have --trace enabled, report a short overview of this step.
            self.context.logger.trace(
                f"Stopped at {step_info.current_function} {step_info.current_location.short_str()}, {len(step_match_result.active_wheres)} active !wheres, record_step={should_record}, next_action={next_action}"
            )

            if next_action == DebuggerAction.EXIT:
                break
            elif next_action == DebuggerAction.STEP:
                self.debugger.step_next()
            elif next_action == DebuggerAction.STEP_OUT:
                self.debugger.step_out()
            else:
                assert (
                    next_action == DebuggerAction.CONTINUE
                ), f"next_action has invalid value {next_action}"
                self.debugger.go()
            time.sleep(self._pause_between_steps)

