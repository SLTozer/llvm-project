# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Diff tool."""

import os

import pickle
from typing import Any

import yaml
from dex.tools import ToolBase
from dex.utils.Exceptions import Error
from dex.utils.ReturnCode import ReturnCode
from dex.utils.PrettyOutputBase import Stream
from dex.dextIR import DextIR, StepIR
from dex.evaluate.ValueJoiner import join_scripts
from dex.evaluate.Evaluator import (
    DexEvaluator,
    DexVisualizer,
    diff_dexter_results,
    uniquify,
    EvaluationContext,
)
from dex.test_script.Nodes import All, Expect, Then, Where, setup_yaml_parser
from dex.test_script.Script import Scope, get_dexter_script

class Tool(ToolBase):
    """Given a pair of dextIR files, display a human-readable diff of the observed traces."""

    @property
    def name(self):
        return "DExTer diff"

    def add_tool_arguments(self, parser, defaults):
        parser.add_argument(
            "base",
            metavar="dextIR-file",
            type=str,
            default=None,
            help="dextIR file for the comparison base",
        )
        parser.add_argument(
            "diff",
            metavar="dextIR-file",
            nargs="+",
            type=str,
            default=None,
            help="dextIR file(s) to compare with the base",
        )
        parser.add_argument(
            "--script",
            metavar="dex-file",
            type=str,
            default=None,
            help="if provided, Dexter will use the provided dexter script as the base script for any operations",
        )
        parser.add_argument(
            "--prune",
            metavar="output-dextIR-file",
            type=str,
            default=None,
            help="if provided, Dexter will write a script file using the union of <base> and <diff>, such that both pass the resulting script",
        )
        parser.add_argument(
            "--join",
            metavar="output-dextIR-file",
            type=str,
            default=None,
            help="if provided, Dexter will join the <base> and <diff> wildcard scripts into the given file, such that both runs should pass the resulting script",
        )
        parser.description = Tool.__doc__

    def handle_options(self, defaults):
        options = self.context.options

        options.base = os.path.abspath(options.base)
        if not os.path.isfile(options.base):
            raise Error(
                '<d>could not find dextIR file</> <r>"{}"</>'.format(options.base)
            )
        options.diff = [os.path.abspath(diff) for diff in options.diff]
        for diff in options.diff:
            if not os.path.isfile(diff):
                raise Error(
                    '<d>could not find dextIR file</> <r>"{}"</>'.format(diff)
                )

    def _substitute_scripts(self, ir: DextIR):
        dex_eval = DexEvaluator(self.context, ir)
        if dex_eval.successful_wildcard_updates == 0 and dex_eval.unsuccessful_wildcard_updates == 0:
            return
        if dex_eval.unsuccessful_wildcard_updates > 0:
            self.context.logger.warning("Trying to diff script with missing wildcards, results may be wonky.")
        ir.script = ir.script.resolve_script(dex_eval.reified_map)

    def go(self) -> ReturnCode:
        options = self.context.options
        setup_yaml_parser(yaml.CLoader)

        with open(options.base, "rb") as fp:
            base_ir: DextIR = pickle.load(fp)
        diff_irs: list[DextIR] = []
        for diff in options.diff:
            with open(diff, "rb") as fp:
                diff_irs.append(pickle.load(fp))

        script = None
        if options.script is not None:
            script, src_files = get_dexter_script(self.context, [options.script], None)

        if options.join is not None:
            joined_script = join_scripts([base_ir] + diff_irs, script)
            output_text_path = options.join
            with open(output_text_path, "w") as fp:
                self.context.o.auto(
                    joined_script.write_script(),
                    stream=Stream(fp),
                )
            self.context.o.auto(f"Wrote output to {output_text_path}")
            return ReturnCode.OK


        self._substitute_scripts(base_ir)
        self._substitute_scripts(diff_ir)
        
        # FIXME: To make comparison easier; we're just assuming the scripts match here.
        diff_ir.script = base_ir.script

        base_steps = base_ir.steps
        diff_steps = diff_ir.steps

        if options.prune is not None:
            wheres_to_keep = set()
            new_expect_values = {}
            diff_eval = DexEvaluator(self.context, diff_ir)
            # For each expect, determines the set of its expected values that are common to both scripts.
            def visit_expect(expect: Expect, expected_value, scope: Scope):
                if expect not in diff_eval.actual_results:
                    return
                expect_actual_results = diff_eval.actual_results[expect]
                if len(expect_actual_results) == 0:
                    self.context.logger.error(f"Expect {expect} has no matches")
                    return
                matches = None
                if isinstance(expect_actual_results[-1], ListMatchResult):
                    # We don't try to filter these yet.
                    matches = expected_value
                else:
                    matches = []
                    for step, match, metrics in expect_actual_results:
                        assert isinstance(match, ComplexMatchResult)
                        def map_match(match_node: Submatch):
                            if match_node.match_type == MatchType.NONE:
                                return None
                            if match_node.is_leaf:
                                return match_node.leaf_value
                            return {
                                subm_name: mapped_value
                                for subm_name, subm_value in match_node.submatches.items()
                                if (mapped_value := map_match(subm_value)) is not None
                            }
                        mapped_value = map_match(match.match_tree)
                        if mapped_value is not None:
                            matches.append(mapped_value)
                    matches = uniquify(matches)
                    if len(matches) == 1:
                        matches = matches[0]
                if matches:
                    new_expect_values[expect] = matches
                    parent_scope = scope
                    while parent_scope.where is not None and parent_scope.where not in wheres_to_keep:
                        wheres_to_keep.add(parent_scope.where)
                        parent_scope = parent_scope.parent_scope
            def visit_then(then: Then, scope: Scope):
                parent_scope = scope
                while parent_scope.where is not None and parent_scope.where not in wheres_to_keep:
                    wheres_to_keep.add(parent_scope.where)
                    parent_scope = parent_scope.parent_scope
            # First, we figure out what values (and subsequently expects, and then wheres) we want to keep.
            diff_ir.script.visit_script(visit_expect=visit_expect, visit_then=visit_then)
            # Then, we use these recorded values to rewrite the script, excluding any bad values.
            def map_expect(expect: Expect, expected_value, scope: Scope):
                if expect not in new_expect_values:
                    return None
                return expect, new_expect_values[expect]
            def map_where(where: Where, scope: Scope):
                return where if where in wheres_to_keep else None
            new_script = diff_ir.script.map_script(map_expect=map_expect, map_where=map_where)
            output_text_path = options.prune
            with open(output_text_path, "w") as fp:
                self.context.o.auto(
                    new_script.write_script(),
                    stream=Stream(fp),
                )
            self.context.o.auto(f"Wrote output to {output_text_path}")
            return ReturnCode.OK

        self.context.o.auto(diff_dexter_results(self.context, base_ir, diff_ir))
        # if options.plot_steps:
        #     visualizer.graph_steps()
        return ReturnCode.OK
