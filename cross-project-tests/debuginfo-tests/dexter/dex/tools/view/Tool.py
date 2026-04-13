# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""View tool."""

import os

import pickle
from typing import Callable
from dex.dextIR import DextIR, StepIR
from dex.evaluate.ValueDiffer import diff_scripts
from dex.evaluate.VisualDex import VisualDexNode, VisualDexNodeStatus
from dex.test_script.ValueMatcher import FullContext, ScriptTraceMatch
from dex.tools import ToolBase
from dex.utils.Exceptions import Error
from dex.utils.ReturnCode import ReturnCode
from dex.evaluate.Evaluator import DexEvaluator, DexVisualizer
from dex.evaluate.RunDiff import graph_steps

try:
    from dex.tools.view.Interactive import run_interactive
except (ModuleNotFoundError, ImportError) as e:
    run_interactive = e

import yaml

from dex.test_script.Nodes import setup_yaml_parser
from argparse import ArgumentParser
import pprint
import sys
import json

from difflib import SequenceMatcher

class Tool(ToolBase):
    """Given a dextIR file, display the information in a human-readable form."""

    @property
    def name(self):
        return "DExTer view"

    def add_tool_arguments(self, parser: ArgumentParser, defaults):
        parser.add_argument(
            "input_path",
            metavar="dextIR-file",
            type=str,
            default=None,
            help="dexter dextIR file to view",
        )
        parser.add_argument(
            "diff_path",
            metavar="dextIR-file",
            nargs='?',
            type=str,
            default=None,
            help="second dexter dextIR file to compare to the first",
        )
        parser.add_argument(
            "-i", "--interactive",
            action="store_true",
            default=None,
            help="view an interactive display of the file"
        )
        parser.add_argument(
            "--side-by-side",
            action="store_true",
            default=None,
            help="print side-by-side diff of the expected vs actual results"
        )
        parser.add_argument(
            "--filter",
            type=str,
            default=None,
            help="filter used for side-by-side diff"
        )
        parser.add_argument(
            "--at-step",
            type=int,
            default=None,
            help="step to print results at"
        )
        parser.add_argument(
            "--plot-steps",
            action="store_true",
            default=None,
            help="plot a graph of the steps observed by Dexter compared to the expected steps"
        )
        parser.add_argument(
            "--plot-step-diff",
            action="store_true",
            default=None,
            help="plot a graph comparing the steps of the base dextIR to the diff dextIR"
        )
        parser.description = Tool.__doc__

    def handle_options(self, defaults):
        options = self.context.options

        options.input_path = os.path.abspath(options.input_path)
        if not os.path.isfile(options.input_path):
            raise Error(
                '<d>could not find dextIR file</> <r>"{}"</>'.format(options.input_path)
            )
        if options.diff_path:
            options.diff_path = os.path.abspath(options.diff_path)
            if not os.path.isfile(options.diff_path):
                raise Error(
                    '<d>could not find dextIR file</> <r>"{}"</>'.format(options.diff_path)
                )

    def _substitute_scripts(self, ir):
        dex_eval = DexEvaluator(self.context, ir)
        if dex_eval.successful_wildcard_updates == 0 and dex_eval.unsuccessful_wildcard_updates == 0:
            return
        if dex_eval.unsuccessful_wildcard_updates > 0:
            self.context.logger.warning("Trying to diff script with missing wildcards, results may be wonky.")
        ir.script = ir.script.resolve_script(dex_eval.reified_map)

    def go(self) -> ReturnCode:
        options = self.context.options
        setup_yaml_parser(yaml.CLoader)

        with open(options.input_path, "rb") as fp:
            steps: DextIR = pickle.load(fp)
        
        if options.diff_path:
            with open(options.diff_path, "rb") as fp:
                diff_steps = pickle.load(fp)
        else:
            diff_steps = None

        self._substitute_scripts(steps)

        if options.plot_step_diff:
            if diff_steps is None:
                raise Error("Missing second DextIR to compare steps with.")
            graph_steps(self.context, [steps, diff_steps])
            return ReturnCode.OK

        if options.interactive:
            if isinstance(run_interactive, (ModuleNotFoundError, ImportError)):
                self.context.logger.error(f"Failed to launch interactive mode: {run_interactive}")
                return ReturnCode.FAIL
            return run_interactive(self.context, steps)
        
        if options.side_by_side:
            if diff_steps is not None:
                visual_result = diff_scripts(self.context, [steps, diff_steps])
                renderer = visual_result.get_stdout_renderer(self.context.o.auto, display_columns=["expected", "base", "diff"], column_width=70)
                visual_result.render(renderer)
                return ReturnCode.OK
            def check_condition(step: StepIR, frame_idx: int, condition: str):
                cond_value = step.frames[frame_idx].values[condition]
                result = cond_value.could_evaluate and cond_value.value == "true"
                return result
            match_context = FullContext(check_condition=check_condition)
            script_trace_matches: list[ScriptTraceMatch] = []
            last_match: ScriptTraceMatch | None = None
            steps_to_match = steps.steps[0:options.at_step] if options.at_step is not None else steps.steps
            for step in steps_to_match:
                next_match = ScriptTraceMatch(steps.script, step, match_context, last_match)
                last_match = next_match
                script_trace_matches.append(next_match)
            if script_trace_matches:
                visual_result = script_trace_matches[-1].get_visual_trace(steps.script)
                renderer = visual_result.get_stdout_renderer(self.context.o.auto, ["expected", "actual"])
                def get_filter(filter: str | None) -> Callable[[VisualDexNode], bool] | None:
                    if filter is None:
                        return None    
                    def do_filter(node: VisualDexNode) -> bool:
                        try:
                            expected_status = node.values["expected"].status
                        except:
                            expected_status = VisualDexNodeStatus()
                        try:
                            actual_status = node.values["actual"].status
                        except:
                            actual_status = VisualDexNodeStatus()
                        combined = {field: actual_status.__dict__[field] or expected_status.__dict__[field] for field in actual_status.__dict__}
                        return eval(filter, {'__builtins__': None}, {"expected": expected_status, "actual": actual_status, **combined})
                    return do_filter
                visual_result.render(renderer, get_filter(options.filter))
            return ReturnCode.OK

        evaluator = DexEvaluator(self.context, steps)
        self.context.o.auto("\n{}\n".format(steps))
        self.context.o.auto(evaluator.get_output())
        visualizer = DexVisualizer(self.context, steps)
        self.context.o.auto(visualizer.visualize_final_result())
        if options.plot_steps:
            visualizer.graph_steps()
        return ReturnCode.OK
