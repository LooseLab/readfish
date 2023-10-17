"""
_filter.py

Provides functionality to filter alignments in the PAF format using a mini-language.
Users can define complex filtering conditions using this language, and the module
parses these conditions to filter PAF records accordingly.

Key Features:
- Tokenization of user-defined filter rules.
- Conversion of tokenized rules into callable filter functions.
- Support for various comparison operators like '<', '>', '==', etc.
- Ability to chain multiple filter rules together for compound filtering.

Example Usage:
    filter_rules = [
        "is_primary",
        "mapq > 40",
        "strand == -1",
    ]
    filters = Filters(filter_rules)
    for paf_record in paf_records:
        if filters(paf_record):
            process(paf_record)

Notes:
- This module is designed for extensibility, allowing for potential future enhancements
  such as adding logical operators, grouping conditions, and more.
- Users are encouraged to ensure their filter rules are correctly formatted to avoid
  potential parsing errors.
"""

# ... rest of the code ...

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
    """
    Tokenize the given filtering rule string into its constituent parts.

    :param rule: The filtering rule string to tokenize.
    :return: A dictionary containing the tokenized elements of the rule.

    :Example:

    .. doctest::

        >>> tokenize("is_primary")
        {'ATTR': 'is_primary'}
        >>> tokenize("mapq > 40")
        {'ATTR': 'mapq', 'OP': <built-in function gt>, 'VALUE': 40.0}
        >>> tokenize("strand == -1")
        {'ATTR': 'strand', 'OP': <built-in function eq>, 'VALUE': -1.0}
        >>> tokenize('"filename" in attr') # doctest: +ELLIPSIS
        {'VALUE': 'filename', 'OP': <function <lambda> at ...>, 'ATTR': 'attr'}

    .. note::

        - The function can handle different types of rules, including those with
          comparison operators, attribute checks, and checks for membership (using "in").
        - The function recognizes and tokenizes attributes, comparison operators,
          numbers, and quoted strings.
    """

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
    """
    Represents a single filter condition parsed from a rule string.

    This class tokenizes a rule, interprets its meaning, and provides a callable
    interface to evaluate the rule against given objects.

    :param rule: The filtering rule string to parse and interpret.

    :Example:

    .. doctest::

        >>> filter1 = Filter("is_primary")
        >>> filter1({"is_primary": True, "mapq": 20, "strand": -1})
        True
        >>> filter2 = Filter("mapq > 40")
        >>> filter2({"is_primary": True, "mapq": 50, "strand": -1})
        True
        >>> filter2({"is_primary": True, "mapq": 30, "strand": -1})
        False
        >>> filter3 = Filter("strand == -1")
        >>> filter3({"is_primary": True, "mapq": 50, "strand": -1})
        True

    .. note::

        - The `Filter` class can handle different types of rules, including attribute checks,
          comparison operations, and membership checks.
        - The class provides a callable interface, allowing it to be used as a function
          to evaluate objects based on the rule.
    """

    def __init__(self, rule: str):
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
    """
    Represents a collection of filter conditions parsed from a list of rule strings.

    This class aggregates multiple `Filter` objects and provides a unified interface
    to evaluate a set of filter conditions against given objects. It evaluates whether
    an object satisfies *all* the provided conditions.

    :param rules: A list of filtering rule strings to parse and interpret.
    :type rules: List[str]

    :Example:

    .. doctest::

        >>> rules = ["is_primary", "mapq > 40", "strand == -1"]
        >>> filters = Filters(rules)
        >>> obj1 = {"is_primary": True, "mapq": 50, "strand": -1}
        >>> obj2 = {"is_primary": False, "mapq": 50, "strand": -1}
        >>> obj3 = {"is_primary": True, "mapq": 30, "strand": -1}
        >>> filters(obj1)
        True
        >>> filters(obj2)
        False
        >>> filters(obj3)
        False

    .. note::

        - The `Filters` class aggregates multiple individual `Filter` objects.
        - The class provides a callable interface, allowing it to be used as a function
          to evaluate whether objects satisfy all the filtering conditions.
        - If any rule is not satisfied, the `Filters` callable returns `False`.
    """

    def __init__(self, rules):
        self.rules = rules
        self.funcs = [Filter(rule) for rule in self.rules]

    def __repr__(self):
        return str(self.funcs)

    def __call__(self, obj):
        return all(rule(obj) for rule in self.funcs)
