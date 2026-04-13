# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Test tool."""

import json
import math
import os
import csv
import pickle
import shutil
import platform

from dex.debugger.Debuggers import run_debugger_subprocess
from dex.debugger import DebuggerController
from dex.dextIR.DextIR import DextIR
from dex.evaluate.Evaluator import DexEvaluator, DexVisualizer
from dex.evaluate.ValueJoiner import join_scripts
from dex.tools import TestToolBase
from dex.test_script.Nodes import Expect, Then, Where
from dex.test_script.Script import DexterScript, get_dexter_script
from dex.utils.Exceptions import DebuggerException
from dex.utils.Exceptions import BuildScriptException
from dex.utils.PrettyOutputBase import Stream
from dex.utils.ReturnCode import ReturnCode


class Tool(TestToolBase):
    """Run the specified DExTer test(s) with the specified compiler and linker
    options and produce a dextIR file as well as printing out the debugging
    experience metrics as calculated by the DexEvaluator.
    """

    def __init__(self, *args, **kwargs):
        super(Tool, self).__init__(*args, **kwargs)
        self._test_cases = []

    @property
    def name(self):
        return "DExTer test"

    def add_tool_arguments(self, parser, defaults):
        super(Tool, self).add_tool_arguments(parser, defaults)

    def _init_debugger_controller(self):
        step_collection = DextIR(
            executable_path=self.context.options.executable,
            source_paths=self.context.options.source_files,
            dexter_version=self.context.version,
        )

        step_collection.script, new_source_files = get_dexter_script(
            self.context, self.context.options.test_files, self.context.options.source_root_dir
        )

        self.context.options.source_files.extend(list(new_source_files))

        debugger_controller = DebuggerController(self.context, step_collection)

        return debugger_controller

    def _get_steps(self):
        """Generate a list of debugger steps from a test case."""
        debugger_controller = self._init_debugger_controller()
        debugger_controller = run_debugger_subprocess(
            debugger_controller, self.context.working_directory.path
        )
        steps = debugger_controller.step_collection
        return steps

    def _get_results_basename(self, test_name):
        def splitall(x):
            while len(x) > 0:
                x, y = os.path.split(x)
                yield y

        all_components = reversed([x for x in splitall(test_name)])
        return "_".join(all_components)

    def _get_results_path(self, test_name):
        """Returns the path to the test results directory for the test denoted
        by test_name.
        """
        assert self.context.options.results_directory is not None
        return os.path.join(
            self.context.options.results_directory,
            self._get_results_basename(test_name),
        )

    def _get_results_text_path(self, test_name):
        """Returns path results .txt file for test denoted by test_name."""
        test_results_path = self._get_results_path(test_name)
        return "{}.txt".format(test_results_path)

    def _get_results_pickle_path(self, test_name):
        """Returns path results .dextIR file for test denoted by test_name."""
        test_results_path = self._get_results_path(test_name)
        return "{}.dextIR".format(test_results_path)

    def _record_steps(self, test_name, steps, evaluator: DexEvaluator):
        """Write out the set of steps out to the test's .txt and .json
        results file if a results directory has been specified.
        """
        if self.context.options.results_directory:
            output_text_path = self._get_results_text_path(test_name)
            with open(output_text_path, "w", encoding="utf-8") as fp:
                visualizer = DexVisualizer(self.context, steps, evaluator)
                self.context.o.auto(f"{steps}\n\n{visualizer.visualize_final_result()}\n\n{evaluator.get_output()}", stream=Stream(fp))

            metrics_results_path = self._get_results_path(test_name) + ".json"
            with open(metrics_results_path, "w", encoding="utf-8") as fp:
                json.dump(evaluator.get_json_output(), fp)

            output_dextIR_path = self._get_results_pickle_path(test_name)
            with open(output_dextIR_path, "wb") as fp:
                pickle.dump(steps, fp, protocol=pickle.HIGHEST_PROTOCOL)

    def _write_updated_script(
        self, test_name, evaluator: DexEvaluator, script: DexterScript
    ):
        """Write out the original script file, modified to replace any unknown expects with the actual observed values."""
        if self.context.options.results_directory:
            output_text_path = self._get_results_path(test_name)
            with open(output_text_path, "w", encoding="utf-8") as fp:
                self.context.o.auto(
                    script.resolve_script(evaluator.reified_map).write_script(),
                    stream=Stream(fp),
                )

    def _record_test_and_display(self, test_case):
        """Output test case to o stream and record test case internally for
        handling later.
        """
        self.context.o.auto(test_case)
        self._test_cases.append(test_case)

    def _record_failed_test(self, test_name, exception):
        """Instantiate a failed test case with failure exception and
        store internally.
        """
        script_error = (
            " : {}".format(exception.script_error.splitlines()[0])
            if getattr(exception, "script_error", None)
            else ""
        )
        error = f"{test_name}: {str(exception).splitlines()[0]}{script_error}\n"
        self.context.o.auto(error)
        if self.context.options.verbose:
            self.context.o.auto(str(exception))

    def _record_successful_test(self, test_name, steps, evaluator: DexEvaluator):
        """Instantiate a successful test run, store test for handling later.
        Display verbose output for test case if required.
        """
        if self.context.options.verbose:
            visualizer = DexVisualizer(self.context, steps, evaluator)
            self.context.o.auto(f"\n{steps}\n\n{visualizer.visualize_final_result()}\n")
        self.context.o.auto(f"\n{evaluator.get_output()}\n")

    def _run_test(self, test_name):
        """Attempt to run test files specified in options.source_files. Store
        result internally in self._test_cases.
        """
        try:
            if self.context.options.binary:
                if platform.system() == 'Darwin' and os.path.exists(self.context.options.binary + '.dSYM'):
                    # On Darwin, the debug info is in the .dSYM which might not be found by lldb, copy it into the tmp working directory
                    shutil.copytree(self.context.options.binary + '.dSYM', self.context.options.executable + '.dSYM')
                # Copy user's binary into the tmp working directory.
                shutil.copy(
                    self.context.options.binary, self.context.options.executable
                )
            steps = self._get_steps()
            evaluator = DexEvaluator(self.context, steps)
            self._record_steps(test_name, steps, evaluator)
            if evaluator.unsuccessful_wildcard_updates > 0:
                self.context.o.auto("\n<y>Failed to find values for one or more unknowns.</>\n")
                self._write_updated_script(test_name, evaluator, steps.script)
            elif evaluator.successful_wildcard_updates > 0:
                self.context.o.auto("\n<g>Found values for all unknowns.</>\n")
                self._write_updated_script(test_name, evaluator, steps.script)
        except (BuildScriptException, DebuggerException) as e:
            self._record_failed_test(test_name, e)
            return

        self._record_successful_test(test_name, steps, evaluator)
        return

    def _run_repeated_test(self, test_name, num_times):
        """Attempt to run test files specified in options.source_files. Store
        result internally in self._test_cases.
        """
        try:
            if self.context.options.binary:
                if platform.system() == 'Darwin' and os.path.exists(self.context.options.binary + '.dSYM'):
                    # On Darwin, the debug info is in the .dSYM which might not be found by lldb, copy it into the tmp working directory
                    shutil.copytree(self.context.options.binary + '.dSYM', self.context.options.executable + '.dSYM')
                # Copy user's binary into the tmp working directory.
                shutil.copy(
                    self.context.options.binary, self.context.options.executable
                )
                
            steps_per_run: list[DextIR] = []
            for i in range(num_times):
                self.context.logger.note(f"Running test {i + 1}/{num_times}")
                result_steps = self._get_steps()
                steps_per_run.append(result_steps)
                output_dextIR_path = self._get_results_pickle_path(f"{test_name}.{i}")
                with open(output_dextIR_path, "wb") as fp:
                    pickle.dump(result_steps, fp, protocol=pickle.HIGHEST_PROTOCOL)
        except (BuildScriptException, DebuggerException) as e:
            self._record_failed_test(test_name, e)
            return

        joined_script = join_scripts(steps_per_run)
        base_steps = steps_per_run[0]
        base_steps.script = joined_script
        evaluator = DexEvaluator(self.context, base_steps)
        self._record_steps(test_name, base_steps, evaluator)
        if evaluator.unsuccessful_wildcard_updates > 0 or evaluator.successful_wildcard_updates > 0:
            self.context.logger.error("Script should be fully resolved, but wildcards remain?")
        if self.context.options.results_directory:
            output_text_path = self._get_results_path(test_name)
            with open(output_text_path, "w", encoding="utf-8") as fp:
                self.context.o.auto(
                    joined_script.write_script(),
                    stream=Stream(fp),
                )

        self._record_successful_test(test_name, base_steps, evaluator)
        return
