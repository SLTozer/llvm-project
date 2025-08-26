
import yaml
from dex.dextIR.StepIR import StepIR
import difflib

class Where:
    """"One or more instances of this class define a range of steps in a debugging session. Any expects in the script
    within scope of a "Where" will only be evaluated for the steps where the Where applies.
    """
    def __init__(self, attributes: dict):
        self.file: str | None = attributes.get("file")
        self.function: list[str] | str | None = attributes.get("function")
        self.lines: int | tuple[int, int] | range | None = attributes.get("lines")
        self.after_hits: int | None = attributes.get("after_hits")
        self.conditions: dict = attributes.get("conditions")
        assert self.function or self.lines or not self.after_hits, "Can't have after_hits without also having lines or a function"

    def __repr__(self):
        elts = []
        if self.file:
            elts.append(f"file={self.file}")
        if self.function:
            elts.append(f"fn={self.function}")
        if self.lines:
            elts.append(f"lines={str(self.lines)}")
        if self.after_hits:
            elts.append(f"after_hits={str(self.after_hits)}")
        return "Where(" + ", ".join(elts) + ")"


    def constructor(loader, node):
        return Where(loader.construct_mapping(node))

    def representer(dumper: yaml.Dumper, data):
        mapping = {}
        if data.file:
            mapping["file"] = data.file
        if data.function:
            mapping["fn"] = data.function
        if data.lines:
            mapping["lines"] = str(data.lines)
        if data.after_hits:
            mapping["after_hits"] = str(data.after_hits)
        return dumper.represent_mapping('!where', mapping, flow_style=True)

    def register_yaml(loader):
        yaml.add_constructor("!where", Where.constructor, loader)
        yaml.add_representer(Where, Where.representer)

    def get_lines(self) -> list[int]:
        if not self.lines:
            return []
        if isinstance(self.lines, int):
            return [self.lines]
        lines = []
        for line in self.lines:
            lines.append(line)
        return lines

class Then:
    """Used to perform actions, such as finishing the test or running a command. Will trigger when it is first in-scope
    for a step, so a typical usage pattern is to map to it directly from a "Where", e.g.
    `!where {line: 4, after_hits: 2}: !then finish`.
    """
    def __init__(self, command: str):
        self.command = command

    def is_valid(self) -> bool:
        return self.command == "finish"

    def __repr__(self):
        return f"Then({self.command})"

    def constructor(loader, node):
        return Then(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar('!then', data.command)

    def register_yaml(loader):
        yaml.add_constructor("!then", Then.constructor, loader)
        yaml.add_representer(Then, Then.representer)

class Scope:
    def __init__(self, file: str, labels: dict, fn: str | None = None, lines: int | range | list | None = None,
                 conditions: dict | None = None, after_hits: int | None = None):
        self.file = file
        self.labels = labels
        self.fn = fn
        self.lines = lines
        self.conditions = conditions
        self.after_hits = after_hits

    def empty_scope():
        return Scope(None, dict())

    def as_tuple(self):
        return (
            self.file,
            self.fn,
            tuple(self.get_lines()),
            self.conditions,
            self.after_hits,
        )

    # Returns a new Scope resulting from applying the new Where to this scope.
    # Note that the 'Where' does not need to be contained within the current scope; for example, if 'where' is in a
    # different file to this scope, we take that as the new file and invalidate any existing fn/line info since it no
    # longer applies to the new scope.
    def add_where(self, where: Where):
        scope_file = self.file
        scope_labels = self.labels
        scope_fn = self.fn
        scope_lines = self.lines
        scope_conditions = self.conditions
        scope_after_hits = self.after_hits
        if where.file:
            scope_file = where.file
            scope_fn = None
            scope_lines = None
            scope_after_hits = None
        if where.function:
            scope_fn = where.function
            scope_lines = None
            scope_after_hits = None
            scope_conditions = None
        if where.lines:
            scope_lines = where.lines
            scope_after_hits = None
            scope_conditions = None
        if where.conditions:
            scope_conditions = where.conditions
        if where.after_hits:
            scope_after_hits = where.after_hits
        return Scope(scope_file, scope_labels, scope_fn, scope_lines, scope_conditions, scope_after_hits)

    def as_where(self) -> Where:
        attributes = {
            "file": self.file,
            "function": self.fn,
            "lines": self.lines,
            "conditions": self.conditions,
            "after_hits": self.after_hits,
        }
        return Where({k: v for k, v in attributes if v is not None})

    def get_lines(self):
        # This should use self.labels to resolve "lines" to something concrete, when we have proper label support.
        if not self.lines:
            return []
        if isinstance(self.lines, int):
            return [self.lines]
        return self.lines
    
    def get_line_range(self):
        if not self.lines:
            return None
        if isinstance(self.lines, int):
            return range(self.lines, self.lines + 1)
        # FIXME: For non-contiguous ranges this is incorrect, as is returning a range here at all - fix it later.
        if isinstance(self.lines, list):
            return range(self.lines[0], self.lines[-1] + 1)
        assert isinstance(self.lines, range)
        return self.lines

    # Awkward design to match current Dexter interface.
    def get_single_condition(self):
        if not self.conditions or len(self.conditions) != 1:
            return (None, None)
        return (self.conditions.keys()[0], self.conditions.values()[0])

# Represents generic macros in the YAML script format, which take no arguments and expand out to ; they are represented here by
# just their name, e.g. !locals -> ScriptKeyword("locals").
class ScriptKeyword:
    def __init__(self, keyword: str):
        self.keyword = keyword

    def keywords():
        return ["locals", "params"]

    def get_constructor(keyword: str):
        return lambda loader, node: ScriptKeyword(keyword)

    def representer(dumper, data):
        return dumper.represent_scalar(f'!{data.keyword}', None)

    def register_yaml(loader):
        for keyword in ScriptKeyword.keywords():
            yaml.add_constructor(f"!{keyword}", ScriptKeyword.get_constructor(keyword), loader)
        yaml.add_representer(ScriptKeyword, ScriptKeyword.representer)


# An expectation of some debugger state that will be compared to actual observed debugger state and generate one or more
# metrics as a measurement of the difference.
# Expects are largely independent, but may have some limited cross-over in the case of metavariables (such as !addr).
class Expect:
    def __init__(self):
        pass

    # For a list of steps in which this expectation is in-scope, returns all the information required to evaluate it.
    def get_actual_value(self, steps: list[StepIR]):
        raise NotImplementedError()

    def evaluate(self, expected, actual):
        raise NotImplementedError()

    def get_watched_exprs(self) -> list[str]:
        raise NotImplementedError()
    
class Value(Expect):
    def __init__(self, variable_name: str):
        self.variable_name = variable_name

    def get_actual_value(self, steps: list[StepIR]):
        values = []
        for step in steps:
            step_value = step.watches[self.variable_name]
            if not values or values[-1] != step_value:
                values.append(step_value)
        return values

    def evaluate(self, expected, actual):
        if not isinstance(expected, list):
            expected = [expected]
        if not isinstance(actual, list):
            actual = [actual]
        return list(
            difflib.Differ().compare(list(actual), list(expected))
        )

    def get_watched_exprs(self) -> list[str]:
        return [self.variable_name]

    def __repr__(self):
        return f"Value({self.variable_name})"

    def constructor(loader, node):
        return Value(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar('!value', data.variable_name)

    def register_yaml(loader):
        yaml.add_constructor("!value", Value.constructor, loader)
        yaml.add_representer(Value, Value.representer)

class Type(Expect):
    def __init__(self, variable_name: str):
        self.variable_name = variable_name

    def get_watched_exprs(self) -> list[str]:
        return [self.variable_name]

    def __repr__(self):
        return f"Type({self.variable_name})"

    def constructor(loader, node):
        return Type(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar('!type', data.variable_name)

    def register_yaml(loader):
        yaml.add_constructor("!type", Type.constructor, loader)
        yaml.add_representer(Type, Type.representer)

class Steps(Expect):
    def __init__(self):
        pass

    def get_watched_exprs(self) -> list[str]:
        return []

    def __repr__(self):
        return f"Steps"

    def constructor(loader, node):
        return Steps()

    def representer(dumper, data):
        return dumper.represent_scalar('!steps', None)

    def register_yaml(loader):
        yaml.add_constructor("!steps", Steps.constructor, loader)
        yaml.add_representer(Steps, Steps.representer)

class Label:
    def __init__(self, name: str):
        self.name = name

    def constructor(loader, node):
        return Label(loader.construct_scalar(node))

    def representer(dumper, data):
        return dumper.represent_scalar('!label', data.name)

    def register_yaml(loader):
        yaml.add_constructor("!label", Label.constructor, loader)
        yaml.add_representer(Label, Label.representer)

class Unknown:
    def __init__(self, index):
        self.index = index
        self.found_values = None

    def set_actual_values(self, actual_values):
        self.found_values = actual_values

    def constructor(loader, node):
        return Unknown(loader.construct_scalar(node))

    def representer(dumper: yaml.Dumper, data):
        if data.found_values is not None:
            return dumper.represent_data(data.found_values)
        return dumper.represent_scalar('!unknown', data.index)

    def register_yaml(loader):
        yaml.add_constructor("!unknown", Unknown.constructor, loader)
        yaml.add_representer(Unknown, Unknown.representer)
