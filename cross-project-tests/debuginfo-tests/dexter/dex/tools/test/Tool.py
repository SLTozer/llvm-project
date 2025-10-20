# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Test tool."""

import math
import os
import csv
import pickle
import shutil
import platform

from dex.debugger.Debuggers import run_debugger_subprocess
from dex.debugger.DebuggerControllers.DefaultController import DefaultController
from dex.debugger.DebuggerControllers.ConditionalController import ConditionalController
from dex.dextIR.DextIR import DextIR
from dex.evaluate.Evaluator import DexEvaluator
from dex.tools import TestToolBase
from dex.test_script.Nodes import Expect, Scope, Then, Where
from dex.test_script.Script import DexterScript, get_dexter_script
from dex.utils.Exceptions import DebuggerException
from dex.utils.Exceptions import BuildScriptException
from dex.utils.PrettyOutputBase import Stream
from dex.utils.ReturnCode import ReturnCode


class TestCase(object):
    def __init__(self, context, name, heuristic, error):
        self.context = context
        self.name = name
        self.heuristic = heuristic
        self.error = error

    @property
    def penalty(self):
        try:
            return self.heuristic.penalty
        except AttributeError:
            return float("nan")

    @property
    def max_penalty(self):
        try:
            return self.heuristic.max_penalty
        except AttributeError:
            return float("nan")

    @property
    def score(self):
        try:
            return self.heuristic.score
        except AttributeError:
            return float("nan")

    def __str__(self):
        if self.error and self.context.options.verbose:
            verbose_error = str(self.error)
        else:
            verbose_error = ""

        if self.error:
            script_error = (
                " : {}".format(self.error.script_error.splitlines()[0])
                if getattr(self.error, "script_error", None)
                else ""
            )

            error = " [{}{}]".format(str(self.error).splitlines()[0], script_error)
        else:
            error = ""

        try:
            summary = self.heuristic.summary_string
        except AttributeError:
            summary = "<r>nan/nan (nan)</>"
        return "{}: {}{}\n{}".format(self.name, summary, error, verbose_error)


class Tool(TestToolBase):
    """Run the specified DExTer test(s) with the specified compiler and linker
    options and produce a dextIR file as well as printing out the debugging
    experience score calculated by the DExTer heuristic.
    """

    def __init__(self, *args, **kwargs):
        super(Tool, self).__init__(*args, **kwargs)
        self._test_cases = []

    @property
    def name(self):
        return "DExTer test"

    def add_tool_arguments(self, parser, defaults):
        parser.add_argument(
            "--fail-lt",
            type=float,
            default=0.0,  # By default TEST always succeeds.
            help="exit with status FAIL(2) if the test result"
            " is less than this value.",
            metavar="<float>",
        )
        parser.add_argument(
            "--calculate-average",
            action="store_true",
            help="calculate the average score of every test run",
        )
        super(Tool, self).add_tool_arguments(parser, defaults)

    def _init_debugger_controller(self):
        step_collection = DextIR(
            executable_path=self.context.options.executable,
            source_paths=self.context.options.source_files,
            dexter_version=self.context.version,
        )

        step_collection.script, new_source_files = get_dexter_script(
            self.context.options.test_files, self.context.options.source_root_dir
        )

        self.context.options.source_files.extend(list(new_source_files))

        seen_files = set()
        # If we have a then/expect that checks for a whole function, or if we have multiple files, assume we need the
        # conditional controller.
        def check_nontrivial_stepping(scope: Scope) -> bool:
            seen_files.add(scope.file)
            if len(seen_files) > 1:
                return True
            return scope.fn and not scope.lines
        def check_nontrivial_expect(expect: Expect, value, scope: Scope) -> bool:
            return check_nontrivial_stepping(scope)
        # If we have a `!then continue`, we need the conditional controller.
        def check_nontrivial_then(then: Then, scope: Scope) -> bool:
            return check_nontrivial_stepping(scope) or then.command == "continue"
        has_nontrivial_stepping = step_collection.script.visit_script(
            visit_expect=check_nontrivial_expect,
            visit_then=check_nontrivial_then)
        if has_nontrivial_stepping:
            debugger_controller = ConditionalController(self.context, step_collection)
        else:
            debugger_controller = DefaultController(self.context, step_collection)

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

    def _record_steps(self, test_name, steps):
        """Write out the set of steps out to the test's .txt and .json
        results file if a results directory has been specified.
        """
        if self.context.options.results_directory:
            output_text_path = self._get_results_text_path(test_name)
            with open(output_text_path, "w") as fp:
                self.context.o.auto(str(steps), stream=Stream(fp))

            output_dextIR_path = self._get_results_pickle_path(test_name)
            with open(output_dextIR_path, "wb") as fp:
                pickle.dump(steps, fp, protocol=pickle.HIGHEST_PROTOCOL)

    def _record_score(self, test_name, heuristic):
        """Write out the test's heuristic score to the results .txt file
        if a results directory has been specified.
        """
        if self.context.options.results_directory:
            output_text_path = self._get_results_text_path(test_name)
            with open(output_text_path, "a") as fp:
                self.context.o.auto(heuristic.verbose_output, stream=Stream(fp))

    def _write_updated_script(self, test_name, script: DexterScript):
        """Write out the original script file, modified to replace any unknown expects with the actual observed values.
        """
        if self.context.options.results_directory:
            output_text_path = self._get_results_path(test_name)
            with open(output_text_path, "w") as fp:
                self.context.o.auto(script.resolve_script().write_script(), stream=Stream(fp))

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
        test_case = TestCase(self.context, test_name, None, exception)
        self._record_test_and_display(test_case)

    def _record_successful_test(self, test_name, steps, evaluator):
        """Instantiate a successful test run, store test for handling later.
        Display verbose output for test case if required.
        """
        test_case = TestCase(self.context, test_name, evaluator, None)
        self._record_test_and_display(test_case)
        if self.context.options.verbose:
            self.context.o.auto("\n{}\n".format(steps))
            self.context.o.auto(evaluator.get_verbose_output())

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
            self._record_steps(test_name, steps)
            evaluator = DexEvaluator(self.context, steps)
            if any(v is None for v in evaluator.wildcard_updates.values()):
                self.context.o.auto("\n<y>Failed to find values for one or more unknowns.</>\n")
            elif len(evaluator.wildcard_updates) > 0:
                self.context.o.auto("\n<g>Found values for all unknowns.</>\n")
                self._write_updated_script(test_name, steps.script)
        except (BuildScriptException, DebuggerException) as e:
            self._record_failed_test(test_name, e)
            return

        self._record_successful_test(test_name, steps, evaluator)
        return

    def _handle_results(self) -> ReturnCode:
        return_code = ReturnCode.OK
        options = self.context.options

        if not options.verbose:
            self.context.o.auto("\n")

        if options.calculate_average:
            # Calculate and print the average score
            score_sum = 0.0
            num_tests = 0
            for test_case in self._test_cases:
                score = test_case.score
                if not test_case.error and not math.isnan(score):
                    score_sum += test_case.score
                    num_tests += 1

            if num_tests != 0:
                print("@avg: ({:.4f})".format(score_sum / num_tests))

        has_failed = lambda test: test.score < options.fail_lt or test.error
        if any(map(has_failed, self._test_cases)):
            return_code = ReturnCode.FAIL

        if options.results_directory:
            summary_path = os.path.join(options.results_directory, "summary.csv")
            with open(summary_path, mode="w", newline="") as fp:
                writer = csv.writer(fp, delimiter=",")
                writer.writerow(["Test Case", "Score", "Error"])

                for test_case in self._test_cases:
                    writer.writerow(
                        [
                            test_case.name,
                            "{:.4f}".format(test_case.score),
                            test_case.error,
                        ]
                    )

        return return_code
