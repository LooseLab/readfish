"""_filter.py
"""
from __future__ import annotations
import operator
import re
from functools import partial
from typing import Any

from readfish._utils import nested_get

_OPS = {
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
    "in": lambda a, b: operator.contains(b, a),
}
# TODO: Link to regex101 here
_SPEC = [
    # Capture strings in quotes
    r"(?P<Q>[\"'])(?P<STRING>[\w\.]+)(?P=Q)",
    # Numbers
    r"(?P<NUMBER>-?\d+(\.\d*)?)",
    # Operators
    rf"(?P<OP>{'|'.join(_OPS.keys())})",
    # Attributes and keys, unquoted
    r"(?P<ATTR>[\w\.]+)",
]
_TOKEN_REGEX = re.compile("|".join(_SPEC))


def tokenize(rule: str) -> dict[str, Any]:
    def _parse(rule: str):
        for match in _TOKEN_REGEX.finditer(rule):
            kind = match.lastgroup
            if kind is None:
                continue
            value = match.group(kind)
            if kind == "NUMBER":
                value = float(value)
                kind = "VALUE"
            elif kind == "STRING":
                kind = "VALUE"
            elif kind == "OP":
                value = _OPS.get(value)
            elif kind == "ATTR":
                value = value
            yield kind, value

    return dict(_parse(rule))


class Filter:
    def __init__(self, rule):
        self.rule = rule
        self._parts = tokenize(self.rule)
        self.get_fn = partial(nested_get, key=self._parts["ATTR"])
        self.static = None
        if len(self._parts) == 1:
            self.cmp = lambda a, _: bool(a)
        elif len(self._parts) == 3:
            if not callable(self._parts["OP"]):
                raise ValueError(f"Rule {rule!r} does not have a valid operation")
            self.cmp = self._parts["OP"]
            self.static = self._parts["VALUE"]
        else:
            raise ValueError(f"Cannot parse {self.rule!r}")

    def __repr__(self):
        return f"fn({self.rule!r})"

    def __call__(self, obj):
        return self.cmp(self.get_fn(obj), self.static)


class Filters:
    def __init__(self, rules):
        self.rules = rules
        self.funcs = [Filter(rule) for rule in self.rules]

    def __repr__(self):
        return str(self.funcs)

    def __call__(self, obj):
        return all(rule(obj) for rule in self.funcs)
