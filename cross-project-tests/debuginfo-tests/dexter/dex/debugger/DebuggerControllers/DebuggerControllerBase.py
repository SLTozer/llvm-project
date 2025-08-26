# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Abstract Base class for controlling debuggers."""

import abc
from itertools import chain


class DebuggerControllerBase(object, metaclass=abc.ABCMeta):
    def __init__(self, context, step_collection):
        self.context = context
        self.step_collection = step_collection

    @abc.abstractclassmethod
    def _run_debugger_custom(self):
        """Specify your own implementation of run_debugger_custom in your own
        controller.
        """
        pass

    def run_debugger(self, debugger):
        """Responsible for correctly launching and tearing down the debugger."""
        self.debugger = debugger

        # Fetch command line options, if any.
        the_cmdline = []
        cmd_lines = self.step_collection.script.get_cmd_line_directives()
        if cmd_lines:
            the_cmdline = list(chain.from_iterable(cmd_lines))

        with self.debugger:
            if not self.debugger.loading_error:
                self._run_debugger_custom(the_cmdline)

        # We may need to pickle this debugger controller after running the
        # debugger. Debuggers are not picklable objects, so set to None.
        self.debugger = None
