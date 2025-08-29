
from collections import OrderedDict, namedtuple
import os

StepExpectInfo = namedtuple("StepExpectInfo", "expression, path, frame_idx, line_range")
ScopeStepExpectInfo = namedtuple("ScopeStepExpectInfo", "scope, path, frame_idx, line_range")

# For each command, there is a set of metrics that can be generated. Metrics across multiple identical commands can be
# aggregated, and each individual metric can be expressed in a scalar form that is considered "better" as it either
# ascends or descends.

class Metric:
    def __init__(self, improves_asc = True):
        self.improves_asc = improves_asc

    def as_scalar(self) -> float:
        raise NotImplementedError()

    def aggregate(self, other):
        raise NotImplementedError()

    # Returns 1 if this metric is better than "other", -1 if it worse, and 0 if it is the same.
    def compare(self, other):
        a = self.as_scalar()
        b = other.as_scalar()
        if not self.improves_asc:
            a, b = b, a
        if a > b:
            return 1
        elif a < b:
            return -1
        else:
            return 0

class ScalarMetric(Metric):
    def __init__(self, value: int | float, improves_asc = True):
        self.value = value
        super().__init__(improves_asc)

    def as_scalar(self) -> float:
        return float(self.value)

    def aggregate(self, other):
        return ScalarMetric(self.value + other.value, self.improves_asc)

    def __repr__(self):
        return f"{self.value}"

class FractionMetric(Metric):
    def __init__(self, numerator: int, denominator: int, improves_asc = True):
        self.num = numerator
        self.dom = denominator
        super().__init__(improves_asc)

    def as_scalar(self) -> float:
        return float(self.num) / float(self.dom)

    def aggregate(self, other):
        return FractionMetric(self.num + other.num, self.dom + other.dom, self.improves_asc)

    def __repr__(self):
        return f"{self.num}/{self.dom}"
