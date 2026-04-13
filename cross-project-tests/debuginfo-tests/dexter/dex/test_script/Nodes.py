# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""This file defines all of the Nodes used to create Dexter scripts. All Nodes must be registered with the yaml
constructor/representer in `setup_yaml_parser` before loading or printing any script.
"""

from dataclasses import dataclass
import os
import re
import yaml
from dex.dextIR.ValueIR import ValueIR

def setup_yaml_parser(loader):
    reg_classes = [
        Where,
        Then,
        Value,
        Type,
        Steps,
        Label,
        DexRange,
        Address,
        ValueAll,
        TypeAll,
        Float,
        Self,
    ]
    for c in reg_classes:
        c.register_yaml(loader)


###################
## Structural Nodes: These are used as keys in the Script, and collectively define Dexter's actions when running a test:
##                   how it steps and navigates through the debuggee program, and what information it collects from the
##                   debugger.

class Where:
    """ "One or more instances of this class define a range of steps in a debugging session. Any expects in the script
    within scope of a "Where" will only be evaluated for the steps where the Where applies.
    """

    def __init__(self, attributes: dict, is_and: bool):
        self.file: str | None = attributes.get("file")
        self.function: list[str] | str | None = attributes.get("function")
        self.lines: int | Label | tuple[int, int] | DexRange | None = attributes.get("lines")
        self.after_hit_count: int | None = attributes.get("after_hit_count")
        self.for_hit_count: int | None = attributes.get("for_hit_count")
        self.conditions: dict = attributes.get("conditions")
        # Cached label resolutions for this Where.
        self._cached_labels: dict[str, int] = None
        self._cached_src_root_dir: str = None
        self.is_and: bool = is_and
        assert (
            self.function
            or self.lines
            or (not self.for_hit_count and not self.after_hit_count)
        ), "Can't have hit count checks without explicitly having either lines or a function"

    def __repr__(self):
        elts = []

        def append_if(name, item):
            if item:
                elts.append(f"{name}={item}")

        append_if("file", self.file)
        append_if("function", self.function)
        append_if("lines", self.lines)
        append_if("for_hit_count", self.for_hit_count)
        append_if("after_hit_count", self.after_hit_count)
        append_if("conditions", self.conditions)
        name = "And" if self.is_and else "Where"
        return f"{name}(" + ", ".join(elts) + ")"

    def get_constructor(is_and: bool):
        def constructor(loader, node):
            return Where(loader.construct_mapping(node), is_and)
        return constructor

    def representer(dumper: yaml.Dumper, data):
        data_entries = [
            ("file", data.file),
            ("function", data.function),
            ("lines", data.lines),
            ("for_hit_count", data.for_hit_count),
            ("after_hit_count", data.after_hit_count),
            ("conditions", data.conditions),
        ]
        mapping = {entry[0]: entry[1] for entry in data_entries if entry[1]}
        name = "!and" if data.is_and else "!where"
        return dumper.represent_mapping(name, mapping, flow_style=True)

    def register_yaml(loader):
        yaml.add_constructor("!where", Where.get_constructor(False), loader)
        yaml.add_constructor("!and", Where.get_constructor(True), loader)
        yaml.add_representer(Where, Where.representer)

    def get_file(self):
        """Returns the file pointed to by this Where, if any, converted to an absolute path using the source root
        directory."""
        if self.file is None:
            return None
        if os.path.isabs(self.file) or not self._cached_src_root_dir:
            return self.file
        return os.path.join(self._cached_src_root_dir, self.file)

    def get_lines(self, labels: dict = None) -> list[int] | range:
        """Returns the list or range of line numbers that this Where references, resolving any required labels, and
        returning an empty list if this Where does not refer to any lines."""
        labels = labels or self._cached_labels
        if not self.lines:
            return []
        if isinstance(self.lines, int):
            return [self.lines]
        if isinstance(self.lines, Label):
            return [labels[self.lines.name]]
        assert isinstance(self.lines, DexRange)
        return self.lines.to_range(labels)

    def cache_context(self, src_root_dir: str, labels: dict[str, int]):
        self._cached_src_root_dir = src_root_dir
        if not self.lines:
            return
        cached_labels = {}
        if isinstance(self.lines, Label):
            cached_labels[self.lines.name] = self.lines.to_line(labels)
        elif isinstance(self.lines, DexRange):
            if isinstance(self.lines.start, Label):
                cached_labels[self.lines.start.name] = self.lines.start.to_line(labels)
            if isinstance(self.lines.stop, Label):
                cached_labels[self.lines.stop.name] = self.lines.stop.to_line(labels)
        if cached_labels:
            self._cached_labels = cached_labels


class Then:
    """Used to perform actions, such as finishing the test or continuing. Will trigger when it is first in-scope
    for a Where in order to advance debugger state somehow, so the expected usage pattern is to map to it directly from
    a "Where", e.g. `!where {line: 4, for_hit_count: 2}: !then finish`.
    """

    def __init__(self, command: str, attrs: dict = {}):
        command_args = command.split()
        self.command = command_args[0]
        self.args = command_args[1:]
        # FIXME: should we use subclasses instead of keeping this dict?
        self.attrs = attrs

    def from_dict(attrs: dict):
        attrs = attrs.copy()
        command = attrs.pop("do")
        return Then(command, attrs)

    def to_dict(self) -> dict:
        attrs = self.attrs.copy()
        attrs["do"] = self.command
        return attrs

    def is_valid(self) -> bool:
        valid_commands = ["finish", "continue", "skip_to"]
        if self.command not in valid_commands:
            return False
        if self.command == "skip_to" and (
            len(self.args) != 1 or not self.args[0].isdigit()
        ):
            return False
        return True

    def __repr__(self):
        return f"Then({self.command})"

    def constructor(loader, node):
        if isinstance(node, yaml.ScalarNode):
            return Then(loader.construct_scalar(node))
        elif isinstance(node, yaml.MappingNode):
            return Then.from_dict(loader.construct_mapping(node))
        raise Exception("Invalid args to !then")

    def representer(dumper, data):
        if data.attrs:
            return dumper.represent_mapping("!then", data.to_dict())
        else:
            return dumper.represent_scalar("!then", data.command)

    def register_yaml(loader):
        yaml.add_constructor("!then", Then.constructor, loader)
        yaml.add_representer(Then, Then.representer)

# An expectation of some debugger state that will be compared to actual observed debugger state and generate one or more
# metrics as a measurement of the difference.
# Expects are largely evaluated independently, but may have some limited cross-over in the case of metavariables (such
# as !address).
class Expect:
    """An expectation of some debugger state that will be compared to actual observed debugger state and generate one
    or more metrics as a measurement of the difference.
    Expects are largely evaluated independently, but may have some limited cross-over in the case of metavariables (such
    as !address).
    """

    @staticmethod
    def get_variable_result(value: ValueIR) -> str | None:
        """For Expects that extract actual results from ValueIR, this method returns that result from the given value,
        excluding any subvalues (i.e. struct members), or None if there is no valid result for this ValueIR.
        """
        return NotImplementedError()

    def get_watched_expr(self) -> str:
        """Returns the list of expressions that this Expect wants to evaluate."""
        return None

    def get_watched_scope(self) -> str:
        """Returns the list of debugger scopes (e.g. Arguments, Locals) that this Expect wants to evaluate."""
        return None


class Value(Expect):
    def __init__(self, variable_name: str):
        self.variable_name = variable_name
        self.actual_values = None

    @staticmethod
    def get_variable_result(value: ValueIR) -> str:
        if value.could_evaluate and not (
            value.is_irretrievable or value.is_optimized_away
        ):
            return value.value
        return None

    def get_watched_expr(self) -> str:
        return self.variable_name

    def get_watched_scope(self) -> str:
        return None

    @property
    def uses_this(self) -> bool:
        return False

    @property
    def expand_arrays(self) -> bool:
        return True

    @property
    def exclude_uninitialized(self) -> bool:
        return True

    def __repr__(self):
        return f"Value({self.variable_name})"

    def constructor(loader, node):
        return Value(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!value", data.variable_name)

    def register_yaml(loader):
        yaml.add_constructor("!value", Value.constructor, loader)
        yaml.add_representer(Value, Value.representer)


class All(Expect):
    """A special variety of Expect which does not evaluate to any result, but is used to indicate that Dexter should
    collect all data that meet a given criterion; currently, this is just variables of a particular "scope" (as defined
    in the DAP protocol)."""

    def __init__(
        self,
        scope: str,
        uses_this: bool,
        expand_arrays: bool,
        exclude_uninitialized: bool,
    ):
        self.scope = scope
        self._uses_this = uses_this
        self._expand_arrays = expand_arrays
        self._exclude_uninitialized = exclude_uninitialized

    def get_watched_scope(self):
        return self.scope

    @staticmethod
    def get_variable_expect(var_name):
        """For a given variable name, returns the Expect that this All wants to generate for that variable."""
        raise NotImplementedError()

    @property
    def uses_this(self) -> bool:
        return self._uses_this

    @property
    def expand_arrays(self) -> bool:
        return self._expand_arrays

    @property
    def exclude_uninitialized(self) -> bool:
        return self._exclude_uninitialized

# A special class that can be used in place of a variable/expression in an expect, to indicate that we wish to apply the
# expect to all vars that match the provided category.
class ValueAll(All):
    def __init__(self, scope: str):
        super().__init__(
            scope, uses_this=False, expand_arrays=True, exclude_uninitialized=True
        )

    def __repr__(self):
        return f"ValueAll({self.scope})"

    @staticmethod
    def get_variable_expect(var_name):
        return Value(var_name)

    @staticmethod
    def get_variable_result(value: ValueIR) -> str:
        return Value.get_variable_result(value)

    def constructor(loader, node):
        return ValueAll(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!value/all", data.category)

    def register_yaml(loader):
        yaml.add_constructor("!value/all", ValueAll.constructor, loader)
        yaml.add_representer(ValueAll, ValueAll.representer)


class Type(Expect):
    def __init__(self, variable_name: str):
        self.variable_name = variable_name
        self._uses_this = True
        self._expand_arrays = False
        self._exclude_uninitialized = False

    @staticmethod
    def get_variable_result(value: ValueIR):
        if value.could_evaluate:
            return value.type_name
        return None

    def get_watched_expr(self) -> str:
        return self.variable_name

    @property
    def uses_this(self) -> bool:
        return True

    @property
    def expand_arrays(self) -> bool:
        return False

    @property
    def exclude_uninitialized(self) -> bool:
        return False

    def __repr__(self):
        return f"Type({self.variable_name})"

    def constructor(loader, node):
        return Type(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!type", data.variable_name)

    def register_yaml(loader):
        yaml.add_constructor("!type", Type.constructor, loader)
        yaml.add_representer(Type, Type.representer)


# A special class that can be used in place of a variable/expression in an expect, to indicate that we wish to apply the
# expect to all vars that match the provided category.
class TypeAll(All):
    def __init__(self, scope: str):
        super().__init__(
            scope, uses_this=True, expand_arrays=False, exclude_uninitialized=False
        )

    def __repr__(self):
        return f"TypeAll({self.scope})"

    @staticmethod
    def get_variable_result(value: ValueIR) -> str:
        return Type.get_variable_result(value)

    @staticmethod
    def get_variable_expect(var_name):
        return Type(var_name)

    def constructor(loader, node):
        return TypeAll(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!type/all", data.category)

    def register_yaml(loader):
        yaml.add_constructor("!type/all", TypeAll.constructor, loader)
        yaml.add_representer(TypeAll, TypeAll.representer)


class Steps(Expect):
    def __init__(self, kind: str):
        assert kind == "order" or kind == "never"
        self.kind = kind

    def __repr__(self):
        return f"Step({self.kind})"

    def constructor(loader, node):
        return Steps(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!steps", data.kind)

    def register_yaml(loader):
        yaml.add_constructor("!steps", Steps.constructor, loader)
        yaml.add_representer(Steps, Steps.representer)


##############
## Utility Nodes: Can be used anywhere in a script as a form of syntactic sugar.

@dataclass(frozen=True)
class Label:
    name: str

    def to_line(self, labels: dict[str, int]) -> int:
        # Labels may contain offsets, which is accounted for here.
        raw_label = self.name.strip()
        if match := re.match(r"^([a-zA-Z_]\w*)\s*([+-])\s*(\d+)$", raw_label):
            identifier, sign, number = match.groups()
            value = int(number) if sign == "+" else -int(number)
            return labels[identifier] + value
        return labels[raw_label]

    def __repr__(self):
        return f"Label({self.name})"

    def constructor(loader, node):
        return Label(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!label", data.name)

    def register_yaml(loader):
        yaml.add_constructor("!label", Label.constructor, loader)
        yaml.add_representer(Label, Label.representer)


@dataclass(frozen=True)
class DexRange:
    start: int | Label
    stop: int | Label

    def __repr__(self) -> str:
        return f"[{self.start} - {self.stop}]"

    # We use an inclusive range in Dexter scripts, while python ranges are exclusive.
    def to_range(self, labels: dict[str, int]) -> range:
        start = (
            self.start if isinstance(self.start, int) else self.start.to_line(labels)
        )
        stop = self.stop if isinstance(self.stop, int) else self.stop.to_line(labels)
        return range(start, stop + 1)

    def constructor(loader, node):
        range_seq = loader.construct_sequence(node)
        if len(range_seq) != 2 or not all(
            [isinstance(elt, (int, Label)) for elt in range_seq]
        ):
            raise Exception(
                range_seq, "!range must have exactly 2 int or !label elements"
            )
        return DexRange(range_seq[0], range_seq[1])

    def representer(dumper, data: range):
        return dumper.represent_sequence("!range", [data.start, data.stop])

    def register_yaml(loader):
        yaml.add_constructor("!range", DexRange.constructor, loader)
        yaml.add_representer(DexRange, DexRange.representer)


##############
## Value Nodes: Used as part of the expected value in a script.

class Address:
    """Named label for an address, which may resolve to different values across test runs but must always be consistent
    within a test run."""
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"Address({self.name})"

    def constructor(loader, node):
        return Address(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!address", data.name)

    def register_yaml(loader):
        yaml.add_constructor("!address", Address.constructor, loader)
        yaml.add_representer(Address, Address.representer)


class Float:
    """Used as part of an expect for float values that may have an approximate range."""

    def __init__(self, values, range=None):
        if not isinstance(values, list):
            values = [values]
        self.values = [float(v) for v in values]
        self.range = range

    def __repr__(self):
        if self.range:
            return f"Float(range={self.range}, values={self.values})"
        return f"Float(values={self.values})"
    

    def matches(self, value):
        try:
            value = float(value)
        except ValueError:
            return False
        if self.range is None:
            return value in self.values
        return any(abs(expected - value) <= self.range for expected in self.values)

    def constructor(loader, node):
        if isinstance(node, yaml.ScalarNode):
            return Float(loader.construct_scalar(node))
        if isinstance(node, yaml.SequenceNode):
            return Float(loader.construct_sequence(node))
        elif isinstance(node, yaml.MappingNode):
            return Float(**loader.construct_mapping(node, deep=True))
        raise Exception("Invalid args to !float")

    def representer(dumper: yaml.Dumper, data):
        values = data.values
        if data.range is None:
            return dumper.represent_sequence("!float", values, flow_style=True)
        mapping = {
            "values": values,
            "range": data.range,
        }
        return dumper.represent_mapping("!float", mapping, flow_style=True)

    def register_yaml(loader):
        yaml.add_constructor("!float", Float.constructor, loader)
        yaml.add_representer(Float, Float.representer)


# FIXME: `Self` is already a special type in Python, find some name for this that isn't!
class Self:
    """Used as part of aggregate expected values to refer to the current member, allowing us to test the members of a
    struct as well as the struct itself; for example, `!type p { x: int, y: int, !self : Point }`.
    """

    def __init__(self, v: str):
        self.v = v

    def __repr__(self):
        return f"Self()"

    def constructor(loader, node):
        return Self(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar("!self", " ")

    def register_yaml(loader):
        yaml.add_constructor("!self", Self.constructor, loader)
        yaml.add_representer(Self, Self.representer)
