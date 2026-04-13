# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Utilities used to compare/diff values of Dexter runs of the same script.
NB: This overlaps with RunDiff.py, but that file has a lot of step-related stuff so I'm just gonna separate them out for
now."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable
from dex.utils.PrettyOutputBase import ljust_color


@dataclass
class VisualDexNodeStatus:
    active: bool = False
    inactive: bool = False
    stack: bool = False
    where: bool = False
    then: bool = False
    expect: bool = False
    correct: bool = False
    partial: bool = False
    incorrect: bool = False
    value: bool = False
    subvalue: bool = False

def to_color(node_status: VisualDexNodeStatus) -> str | None:
    if (node_status.active and (node_status.where or node_status.then)) or node_status.correct:
        return "g"
    if (node_status.stack and node_status.where) or node_status.partial:
        return "y"
    if node_status.incorrect:
        return "r"
    if node_status.inactive:
        return "grey"
    return None
    

class VisualDexNode:
    """A single node in a Dexter script, which may have a range of parallel values (expected value, actual value, and
    actual values from any additional comparison runs), and a list of child nodes.
    
    As mentioned above, each node represents a single script or StepIR element, which is shared across all comparison
    objects. For example:
    [!where {lines: !range [10, 12]}:] Node 1
        [!where {lines: 11}:] Node 2 (parent=1)
            [!value a: 10] Node 3 (parent=2)
        [!value point:] Node 4 (parent=1)
        [-] [x: 4] Node 5 (parent=4), Node 6 (parent=5)
          [y:] Node 7 (parent=5)
            [low: 5] Node 8 (parent=7)
            [high: 6] Node 9 (parent=7)
        - x: 10
          y: 3
    
    The set of Nodes corresponding to script-defined elements is fixed, but additional nodes may be added for Actual
    values that do not align with an Expected value. Exactly how we decide to order/pair Actual values with Expected
    values is not yet well-defined; where possible, we prefer to order Actual values exactly in order/step alignment
    with each other.
    """

    class NodeStatus:
        """The status of a node value."""
        def __init__(self, is_active: bool, is_good: bool, is_bad: bool):
            self.is_active = is_active
            self.is_good = is_good
            self.is_bad = is_bad

    @dataclass
    class NodeValue:
        """Represents the value of this node in a particular comparison object."""
        status: VisualDexNodeStatus
        text: str

    def __init__(self, tag: str, values: dict[str, "VisualDexNode.NodeValue"], children: list["VisualDexNode"] = None, children_on_same_line: bool = False):
        # FIXME: For efficiency's sake this would be better as a list with some getter methods.
        # May map to None for a node which has no representation for one or more comparison objects.
        self.tag = tag
        self.values: dict[str, VisualDexNode.NodeValue] = values
        self.children: list[VisualDexNode] = children or []
        self.allow_children_on_same_line: bool = children_on_same_line
    
    def debug_str(self) -> str:
        return f"({self.values})"

    def merge(self, other: "VisualDexNode"):
        """Merges `other` into this visual node, such that they will align neatly side-by-side."""
        self.values.update(other.values)
        for idx, child in enumerate(self.children):
            if idx >= len(other.children):
                return
            child.merge(other.children[idx])
        if len(other.children) > len(self.children):
            self.children.extend(other.children[len(self.children):])

class VisualDexResult:
    """Class used to represent, as simply as possible, the information needed to represent the result of a single Dexter
    run, or the comparison of multiple Dexter runs."""

    def __init__(self, root_nodes: list[VisualDexNode]):
        self.root_nodes = root_nodes

    @staticmethod
    def get_stdout_renderer(printer: Callable[[str], None], display_columns: list[str] = None, column_width: int = 100) -> Callable[[int, VisualDexNode], int]:
        if display_columns is None:
            display_columns = ["expected", "actual"]
        def render(indent: int, node: VisualDexNode) -> int:
            def node_status_to_color(status: VisualDexNodeStatus) -> tuple[str, str]:
                """Returns the pair of open/close tags for the color according to this status, returning a pair of empty
                strings if no color is appropriate."""
                tag = to_color(status)
                if tag is None:
                    return "", ""
                return f"<{tag}>", "</>"
            def node_value_to_str(node_value: VisualDexNode.NodeValue) -> str:
                if node_value.text is None:
                    return None
                open_tag, close_tag = node_status_to_color(node_value.status)
                return open_tag + node_value.text + close_tag
            col_strs = []
            for col in display_columns:
                value = node.values.get(col, VisualDexNode.NodeValue(VisualDexNodeStatus(), None))
                col_strs.append(node_value_to_str(value))
            if any(c is not None for c in col_strs):
                line = " | ".join(ljust_color(" " * indent + (col_s or ""), column_width) for col_s in col_strs).rstrip()
                printer(f"{line}\n")
                return indent + 2
            return indent
        return render

    def render(self, renderer: Callable[[int, VisualDexNode], int], should_render: Callable[[VisualDexNode], bool] | None = None):
        def print_visual_dex_node(node: VisualDexNode, indent = 0):
            if should_render is not None and not should_render(node):
                return
            child_depth = renderer(indent, node)
            for child in node.children:
                assert child != node
                print_visual_dex_node(child, child_depth)
        
        for root_node in self.root_nodes:
            print_visual_dex_node(root_node)
