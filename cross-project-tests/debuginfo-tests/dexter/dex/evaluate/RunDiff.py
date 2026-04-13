# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Utilities used to compare/diff Dexter runs of the same script."""

from difflib import SequenceMatcher
import itertools
import math

from dex.tools.Main import Context
from dex.dextIR import DextIR, StepIR

def get_aligned_steps(runs: list[DextIR], overlap_differing_segments: bool) -> list[tuple]:
    """For the given list of runs, returns an ordering/alignment of steps from these runs.
    Each entry in the list is a tuple representing one or more simultaneous/aligned steps from across runs. The tuple
    contains, for each run in `runs`, the index of the step from that run that occurs at this point, or None if no step
    aligns at this point; the alignment logic is based on difflib."""
    assert len(runs) == 2, "Currently only supports aligning exactly 2 runs."
    base = runs[0]
    diff = runs[1]
    base_steps_sequence = [str(step.current_location) for step in base.steps]
    diff_steps_sequence = [str(step.current_location) for step in diff.steps]
    step_match_sequence = SequenceMatcher(a=base_steps_sequence, b=diff_steps_sequence, autojunk=False)
    last_base_step = 0
    last_diff_step = 0
    aligned_steps: list[tuple] = []
    
    for base_step, diff_step, match_len in step_match_sequence.get_matching_blocks():
        # TODO: Instead of always putting the `base` unmatching steps first when we have both `base` and `diff`
        # unmatched steps, we could try and pick a principled ordering - for example, if only one of them changes
        # file/function, we'd prefer to put that one first so that the resulting view is cleaner.
        extra_base_steps = []
        extra_diff_steps = []
        if base_step > last_base_step:
            extra_base_steps = list(range(last_base_step, base_step))
        if diff_step > last_diff_step:
            extra_diff_steps = list(range(last_diff_step, diff_step))
        if extra_base_steps or extra_diff_steps:
            if overlap_differing_segments:
                aligned_steps.extend(itertools.zip_longest(extra_base_steps, extra_diff_steps))
            else:
                aligned_steps.extend(itertools.chain(((base_step, None) for base_step in extra_base_steps), ((diff_step, None) for diff_step in extra_diff_steps)))

        aligned_steps.extend((base_step + step_num, diff_step + step_num) for step_num in range(match_len))
        last_base_step = base_step + match_len
        last_diff_step = diff_step + match_len
    if len(base.steps) > last_base_step:
        aligned_steps.extend((step_idx, None) for step_idx in range(last_base_step, len(base.steps)))
    if len(diff.steps) > last_diff_step:
        aligned_steps.extend((None, step_idx) for step_idx in range(last_diff_step, len(diff.steps)))
    return aligned_steps

def get_min_line_per_function_and_max_offset_line(runs: list[DextIR]) -> tuple[dict[str, int], int]:
    min_line_per_function: dict[str, int] = {}
    for run in runs:
        for step in run.steps:
            step_line = step.current_location.lineno
            if step.current_function not in min_line_per_function:
                min_line_per_function[step.current_function] = step_line
            else:
                min_line_per_function[step.current_function] = min(step_line, min_line_per_function[step.current_function])
    max_offset_line: int = 0
    for run in runs:
        for step in run.steps:
            step_line = step.current_location.lineno
            min_fn_line = min_line_per_function[step.current_function]
            max_offset_line = max(max_offset_line, step_line - min_fn_line)
    return (min_line_per_function, max_offset_line)


try:
    import matplotlib.pyplot as plt
    import numpy as np
except (ModuleNotFoundError, ImportError) as e:
    plt = e

def graph_steps(context: Context, runs: list[DextIR]):
    if isinstance(plt, (ModuleNotFoundError, ImportError)):
        context.logger.error(f"Failed to import matplotlib.pyplot: {plt}")
        return
    assert len(runs) == 2
    aligned_steps = get_aligned_steps(runs, True)
    base_steps = runs[0].steps
    diff_steps = runs[1].steps
    min_line_per_function, max_offset_line = get_min_line_per_function_and_max_offset_line(runs)

    base_step_x = list(range(len(aligned_steps)))
    diff_step_x = list(range(len(aligned_steps)))

    def get_offset_line(step_idx: int | None, steps_list: list[StepIR]):
        if step_idx is None:
            return np.nan
        step = steps_list[step_idx]
        min_fn_line = min_line_per_function[step.current_function]
        return step.current_location.lineno - min_fn_line
    base_step_y = []
    base_step_y = [get_offset_line(aligned_step[0], base_steps) for aligned_step in aligned_steps]
    diff_step_y = [get_offset_line(aligned_step[1], diff_steps) for aligned_step in aligned_steps]
    function_start_positions = {}
    for aligned_step_idx in reversed(range(1, len(aligned_steps))):
        aligned_step = aligned_steps[aligned_step_idx]
        base_step_idx: int = aligned_step[0]
        if base_step_idx:
            base_fn = base_steps[base_step_idx].current_function
            last_base_fn = base_steps[base_step_idx - 1].current_function
            if base_fn != last_base_fn:
                function_start_positions[base_fn] = aligned_step_idx
                base_step_y.insert(aligned_step_idx, np.nan)
                base_step_x.insert(aligned_step_idx, aligned_step_idx)
        diff_step_idx: int = aligned_step[1]
        if diff_step_idx:
            diff_fn = diff_steps[diff_step_idx].current_function
            last_diff_fn = diff_steps[diff_step_idx - 1].current_function
            if diff_fn != last_diff_fn:
                function_start_positions[diff_fn] = aligned_step_idx
                diff_step_y.insert(aligned_step_idx, np.nan)
                diff_step_x.insert(aligned_step_idx, aligned_step_idx)
    # We want to mark the start of the first function as well.
    function_start_positions[base_steps[0].current_function] = 0

    function_starts: list[tuple[str, int]] = list(function_start_positions.items())
    function_starts.sort(key=lambda fn_line: fn_line[1])

    base_graph_y = list(base_step_y[math.floor(n / 2)] for n in range(len(base_step_y) * 2 - 1))
    base_graph_y.append(base_graph_y[-1])
    base_graph_x = list(base_step_x[math.ceil(n / 2)] for n in range(len(base_step_x) * 2 - 1))
    base_graph_x.append(base_graph_x[-1] + 1)
    diff_graph_y = list(diff_step_y[math.floor(n / 2)] for n in range(len(diff_step_y) * 2 - 1))
    diff_graph_y.append(base_graph_y[-1])
    diff_graph_x = list(diff_step_x[math.ceil(n / 2)] for n in range(len(diff_step_x) * 2 - 1))
    diff_graph_x.append(diff_graph_x[-1] + 1)
    plt.plot(base_graph_x, base_graph_y, label="O0", linewidth=4, zorder=1)
    plt.plot(diff_graph_x, diff_graph_y, label="O2", linewidth=2, zorder=2)

    min_step = 0
    max_step = max_offset_line

    plt.xlabel("Step")
    plt.ylabel("Line Number")
    plt.title("Base vs Diff steps")
    plt.legend()

    plt.ylim(max_step + 1, min_step)

    function_colors = ['lightblue', 'lightgreen']
    function_ys = [max_step - 10, max_step - 20]
    function_starts.append((None, len(aligned_steps)))
    for fn_idx in range(len(function_starts) - 1):
        start = function_starts[fn_idx][1]
        end = function_starts[fn_idx+1][1]
        color = function_colors[fn_idx % len(function_colors)]
        plt.axvspan(start, end, color=color, alpha=0.3)
        middle = (start + end) / 2
        fn_y = function_ys[fn_idx % len(function_ys)]
        plt.text(middle, fn_y, function_starts[fn_idx][0], ha='center', va='top')

    plt.show()
