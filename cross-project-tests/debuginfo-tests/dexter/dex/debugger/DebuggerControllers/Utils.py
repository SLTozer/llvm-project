# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Utilities for the DebuggerController that encapsulate some of the complex state-tracking problems."""

from dex.dextIR import StepIR


class SkipLoopFrame:
    """One frame of the virtual 'stack' maintained by SkipLoopState, tracking the number of times each instruction has
    been stepped on, and the corresponding source line for each."""

    def __init__(self, frame_depth: int, function: str):
        self.frame_depth = frame_depth
        self.function = function
        # address -> (source_line, hit_count)
        self.instr_steps: dict[str, tuple[int, int]] = {}

    def add_step(self, step_ir: StepIR) -> int:
        """Records the current step, and returns the number of times this instruction has been stepped on."""
        current_frame = step_ir.current_frame
        current_addr = current_frame.instruction_addr
        if current_addr is None:
            return 0
        current_line = step_ir.current_location.lineno
        if entry := self.instr_steps.get(current_addr):
            line, hit_count = entry
            current_hit_count = hit_count + 1
            # NB: This could actually happen if the compiler and debugger are using "location views", but we don't
            # expect to see those here - if this triggers because of that, we'll need to account for them!
            assert (
                line == current_line
            ), "Debugger has reported different lines for the same instruction address?"
            self.instr_steps[current_addr] = (current_line, current_hit_count)
        else:
            current_hit_count = 1
            self.instr_steps[current_addr] = (current_line, current_hit_count)
        return current_hit_count

    def next_line_after_loop(self, loop_count: int) -> int:
        """For the given loop_count, returns the line immediately after the last line in this frame at which we have
        stepped on the same instruction address loop_count times."""
        max_line = max(
            line
            for line, hit_count in self.instr_steps.values()
            if hit_count >= loop_count
        )
        return max_line + 1


class SkipLoopState:
    """Maintains a virtual 'stack' that tracks, for each stack frame in a debugger session, how many times each
    instruction has been stepped on, and recommends source locations to "skip forward" to in order to avoid any long
    loops."""

    def __init__(self, skip_loops_after: int):
        self.skip_loops_after = skip_loops_after
        self.skip_loop_frames: list[SkipLoopFrame] = []

    def update_state_for_current_step(self, step_ir: StepIR) -> tuple[str, int] | None:
        """Updates using the provided step, pushing/popping frames as necessary to match the current stack frame, and
        recording the current stepped instruction address+line. If we have hit the threshold to skip a loop in the
        current frame, returns the recommended breakpoint location (path + line) to skip to.
        """
        frame_size = step_ir.num_frames
        # Find the first SkipLoopFrame that does not match the current stack trace, and remove all frames from that
        # point upwards.
        pop_idx = None
        for idx, skip_loop_frame in enumerate(self.skip_loop_frames):
            frame_depth = skip_loop_frame.frame_depth
            function = skip_loop_frame.function
            if (
                frame_depth > frame_size
                or step_ir.frames[-frame_depth].function != function
            ):
                pop_idx = idx
                break
        if pop_idx is not None:
            self.skip_loop_frames = self.skip_loop_frames[:pop_idx]
        # Now we've sliced off invalid frames, add a new state for the current frame if needed:
        # FIXME: This approach assumes that when we step out of a function, we don't immediately step into it
        # again without an intermediate step. We may be able to circumvent this by checking the stop_reason, however.
        if (
            not self.skip_loop_frames
            or self.skip_loop_frames[-1].frame_depth < frame_size
        ):
            self.skip_loop_frames.append(
                SkipLoopFrame(frame_size, step_ir.current_function)
            )
        # And finally, we now actually record the current step in skip_loop_state, and skip out of the current
        # loop if required.
        # FIXME: This approach is fundamentally quite limited at the moment as it mixes instruction addresses
        # and line counts, and thus can be thrown off by some forms of scheduling. What we want in principle is
        # to "continue" until we exit the range of instruction addresses that have hit the skip_loop_after
        # count; unfortunately, we don't know the lines or addresses that the loop may exit to, and repeatedly
        # stepping would take too long for loops that run for thousands or millions of iterations, so for now
        # our best guess is to jump to the source line *after* the last source line that's seen in the loop.
        # There are various ways this can go wrong, so this will need more work later.
        current_skip_loop_state = self.skip_loop_frames[-1]
        hit_count = current_skip_loop_state.add_step(step_ir)
        if hit_count > self.skip_loops_after:
            bp_line = current_skip_loop_state.next_line_after_loop(
                self.skip_loops_after
            )
            bp_path = step_ir.current_location.path
            return (bp_path, bp_line)
