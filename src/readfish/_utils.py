"""utils.py
functions and utilities used internally.
"""
from __future__ import annotations
import sys
import logging
from collections import Counter
from functools import reduce
from operator import itemgetter
from enum import IntEnum
import re
import base64
from typing import Any, Mapping, Sequence
import zlib

import numpy as np
import numpy.typing as npt
from minknow_api.manager import Manager, FlowCellPosition
from minknow_api import Connection

if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup

from readfish._channels import FLONGLE_CHANNELS, MINION_CHANNELS


MODULE_LOGGER = logging.getLogger(__name__)


class ChunkTracker:
    def __init__(self, channels):
        # https://wiki.python.org/moin/TimeComplexity
        # self.tracker = defaultdict(Counter)
        self.tracker = [Counter() for _ in range(channels + 1)]

    def seen(self, channel, read_number):
        if read_number not in self.tracker[channel]:
            self.tracker[channel].clear()
        self.tracker[channel][read_number] += 1
        return self.tracker[channel][read_number]


class Severity(IntEnum):
    """Severity states for messaging to MinKNOW

    :param INFO: Info level
    :param WARN: Warn level
    :param ERROR: Error level
    """

    INFO = 1
    WARN = 2
    ERROR = 3


def format_bases(num: int, factor: int = 1000, suffix: str = "B") -> str:
    """Return a human readable string of a large number using SI unit prefixes

    :pararm num: A number to convert to decimal form
    :param factor: The SI factor, use 1000 for SI units and 1024 for binary multiples
    :param suffix: The suffix to place after the SI prefix, for example use B for SI units and iB for binary multiples
    :return: The input number formatted to two decimal places with the SI unit and suffix

    :Example:

    >>> format_bases(1_000)
    '1.00 kB'
    >>> format_bases(1_000_000)
    '1.00 MB'
    >>> format_bases(1_630_000)
    '1.63 MB'
    >>> format_bases(1_000_000_000)
    '1.00 GB'
    """
    for unit in ["", "k", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < factor:
            return f"{num:3.2f} {unit}{suffix}"
        num /= factor
    return f"{num:3.2f} Y{suffix}"


def nested_get(obj: Mapping, key: Any, default: Any = None, *, delim: str = ".") -> Any:
    """Get a value from a nested structure

    >>> class C:
    ...     def __init__(self, x=None):
    ...         self.x = x
    ...     def __repr__(self): return f"C(x={self.x!r})"
    >>> data = {"a": {"b": {"c": "d", "e": C(999)}}}
    >>> cls = C(C(data))
    >>> nested_get(data, "a.b.c")
    'd'
    >>> nested_get(data, "a.b.c", 0)
    'd'
    >>> nested_get(data, "a.b.c.d.e", 0)
    0
    >>> nested_get(cls, "x.x")
    {'a': {'b': {'c': 'd', 'e': C(x=999)}}}
    >>> nested_get(cls, "x.x.a.b.e.x")
    999
    >>> nested_get(cls, "missing", "MISSING")
    'MISSING'

    :param obj: Any with a __get_item__ method
    :param key: The key to get from the Mapping
    :param default: The default value to return if the key is not present, defaults to None
    :param delim: Split a string by given the delimiter, to access the Mapping using each key in turn, defaults to "."
    """

    def _get(o, k):
        if isinstance(o, dict):
            return o.get(k, default)
        else:
            return getattr(o, k, default)

    return reduce(_get, key.split(delim), obj)


def compress_and_encode_string(original_str: str) -> str:
    """Compresses a string, encodes it in base-64, and returns an ASCII string representation of the compressed blob.

    :param original_str: The string to be compressed and encoded.
    :return: An ASCII string representation of the compressed and base-64 encoded blob.
    """
    # Convert the string to bytes
    bytes_str = original_str.encode()
    # Compress the bytes
    compressed = zlib.compress(bytes_str)
    # Encode the compressed bytes in base-64
    b64_encoded = base64.b64encode(compressed)
    # Convert the base-64 encoded bytes to an ASCII string
    ascii_str = b64_encoded.decode("ascii")
    return ascii_str


def decode_and_decompress_string(encoded_str: str) -> str:
    """Decodes an ASCII string representation of a compressed blob, decompresses it, and returns the original string.
    This is the reverse of `compress_and_encode_string`.

    :param encoded_str: An ASCII string representation of the compressed and base-64 encoded blob.
    :return: The original string that was compressed and encoded.
    """
    # Convert the ASCII string to base-64 encoded bytes
    b64_encoded = encoded_str.encode("ascii")
    # Decode the base-64 encoded bytes to compressed bytes
    compressed = base64.b64decode(b64_encoded)
    # Decompress the compressed bytes to get the original bytes
    bytes_str = zlib.decompress(compressed)
    # Convert the bytes to a string
    original_str = bytes_str.decode()
    return original_str


def escape_message_to_minknow(message: str, chars: list[str] | str) -> str:
    r"""Escape characters in the chars list if they are in message

    >>> escape_message_to_minknow("20%", ["%"])
    '20\\%'
    >>> escape_message_to_minknow("20\\%", ["%"])
    '20\\%'
    >>> escape_message_to_minknow("20", ["%"])
    '20'

    :param message: The message that is being sent
    :param chars:  The characters to escape
    :return: message that has been escaped
    """
    for char in chars:
        message = re.sub(rf"(?<!\\){char}", rf"\\{char}", message)
    return message


def send_message(rpc_connection: Connection, message: str, severity: int) -> None:
    """Send a message to MinKNOW

    :param rpc_connection: An instance of the rpc.Connection
    :param message: The message to send
    :param severity: The severity to use for the message: 1=info, 2=warning, 3=error
    """
    message = escape_message_to_minknow(message, "%")
    rpc_connection.log.send_user_message(severity=severity, user_message=message)


def nice_join(seq: Sequence[Any], sep: str = ", ", conjunction: str = "or") -> str:
    """Join lists nicely

    :param seq: A sequence of objects that have a __str__ method.
    :param sep: The separator for the join, defaults to ", "
    :param conjunction: A conjunction between the joined list and the last element, defaults to "or"
    :return: The nicely joined string
    """
    seq = [str(x) for x in seq]

    if len(seq) <= 1 or conjunction is None:
        return sep.join(seq)
    else:
        return f"{sep.join(seq[:-1])} {conjunction} {seq[-1]}"


def get_coords(channel: int, flowcell_size: int) -> tuple[int, int]:
    """Return a channel's coordinates given a flowcell size

    :param channel: The channel to retrieve the coordinates for
    :param flowcell_size: The flowcell size, this is used to determine the flowcell layout
    :return: The column and row of a channel number in the flowcell
    :raises ValueError: channel cannot be below 0 or above flowcell_size
    :raises ValueError: Raised if flowcell_size not one of [128, 512, 3000]
    """
    if channel <= 0 or channel > flowcell_size:
        raise ValueError("channel cannot be below 0 or above flowcell_size")

    if flowcell_size == 3000:
        # find which block of 12 we are in:
        block = (channel - 1) // 250
        remainder = (channel - 1) % 250
        row = remainder // 10
        column = remainder % 10 + block * 10
        return column, row
    elif flowcell_size == 126:
        return FLONGLE_CHANNELS[channel]
    elif flowcell_size == 512:
        return MINION_CHANNELS[channel]
    else:
        raise ValueError("flowcell_size is not recognised")


def get_flowcell_array(flowcell_size: int) -> npt.ArrayLike:
    """Return a numpy.ndarray in the shape of a flowcell

    :param flowcell_size: The total number of channels on the flowcell; 126 for Flongle, 512 for MinION, and 3000 for PromethION
    :return: An N-dimensional array representation of the flowcell

    >>> get_flowcell_array(126).shape
    (10, 13)
    >>> get_flowcell_array(512).shape
    (16, 32)
    >>> get_flowcell_array(3000).shape
    (25, 120)
    >>> get_flowcell_array(128)
    Traceback (most recent call last):
        ...
    ValueError: flowcell_size is not recognised
    >>> get_flowcell_array(126)[9][-1]
    0
    >>> get_flowcell_array(512)[15][-1]
    1

    """
    # Make a list of tuples of (column, row, channel)
    coords = [(*get_coords(x, flowcell_size), x) for x in range(1, flowcell_size + 1)]

    # Initialise a nd array using the max row and column from coords
    b = np.zeros(
        (
            max(coords, key=itemgetter(1))[1] + 1,
            max(coords, key=itemgetter(0))[0] + 1,
        ),
        dtype=int,
    )

    # Mimic flowcell layout in an array
    for col, row, chan in coords:
        b[row][col] += chan

    # return the reversed array, to get the right orientation
    return b[::-1]


def stringify_grid(grid: list[list[str]]) -> str:
    """
    Convert a nested list of characters into a 2d grid.

    :param grid: The grid to convert. Represents the flowcell array.
    :return: String representation of the flowcell in ASCII art
    """
    x = []
    for row in grid:
        x.append("".join(row))
    return "\n".join(x)


def draw_flowcell_split(
    flowcell_size: int, split: int = 1, axis: int = 1, index: int = 0
) -> str:
    """
    Draw unicode representation of the flowcell. If the flowcell is split more than once, and index is passed, the region of the
    flowcell represented by the index is highlighted solid, whilst the rest is filled with Xs

    Rather than representing all the possible channels, we draw a 32 column wide flowcell for gridion and 120 for promethion and divide
    accordingly

    Example

    draw_flowcell_split(512)

    XXXX
    XXXX

    draw_flowcell_split(512, split = 2)
    XX00
    XX00

    draw_flowcell_split(512, split = 2, index = 1)
    00XX
    00XX

    :param flowcell_size: Number of channels on the flow cell
    :param split: The number of regions to split into, defaults to 1
    :param index: The index of the region to highlight, defaults to 0
    :return: String representation of the flowcell in ASCII art
    """
    depth, width = get_flowcell_array(flowcell_size).shape
    depth = round((depth / 2) + 0.5)
    cells = []
    for _h in range(depth):
        row = [
            "    ",
        ]
        for _w in range(width):
            row.append(".")
        cells.append(row)
    cells = np.array(cells)
    region = generate_flowcell(flowcell_size, split, axis)[index]
    for pos in region:
        row, col = get_coords(pos, flowcell_size)
        cells[(col // 2), row + 1] = "#"
    return f"\n{stringify_grid(cells)}\n"


def generate_flowcell(
    flowcell_size: int, split: int = 1, axis: int = 1, odd_even: bool = False
) -> list[list[int]]:
    """Return an list of lists with channels to use in conditions

    Representations generated by this method are evenly split based on the physical layout of the flowcell.
    Each sub-list is the same size. Axis determines whether the flowcell divisions will go left-right (0) or top-bottom (1).
    As flongle has a shape of (10, 13) the top-bottom axis cannot be split evenly.


    :param flowcell_size: The total number of channels on the flowcell; 126 for Flongle, 512 for MinION, and 3000 for PromethION
    :param split: The number of sections to split the flowcell into, must be a positive factor of the flowcell dimension, defaults to 1
    :param axis: The axis along which to split, see: https://docs.scipy.org/doc/numpy/glossary.html?highlight=axis, defaults to 1
    :param odd_even: Return a list of two lists split into odd-even channels, ignores `split` and `axis`, defaults to False
    :raises ValueError: Raised when split is not a positive integer
    :raises ValueError: Raised when the value for split is not a factor on the axis provided
    :return: A list of lists with channels divided equally

    >>> len(generate_flowcell(512))
    1
    >>> len(generate_flowcell(512)[0])
    512
    >>> len(generate_flowcell(512, split=4))
    4
    >>> for x in generate_flowcell(512, split=4):
    ...     print(len(x))
    128
    128
    128
    128
    >>> generate_flowcell(512, split=5)
    Traceback (most recent call last):
        ...
    ValueError: The flowcell cannot be split evenly
    """
    if odd_even:
        return [
            list(range(1, flowcell_size + 1, 2)),
            list(range(2, flowcell_size + 1, 2)),
        ]

    arr = get_flowcell_array(flowcell_size)

    if split <= 0:
        raise ValueError("split must be a positive integer")

    try:
        arr = np.array(np.split(arr, split, axis=axis))
    except ValueError:
        # The number of targets cannot be split evenly over the flowcell.
        #   For MinION flowcells the number of targets must be a factor of 16 or
        #   32 for axis 0 or 1 respectively; for PromethION flowcells the number
        #   of targets must be a factor of 25 or 120 for axis 0 or 1 respectively.
        raise ValueError("The flowcell cannot be split evenly")

    arr.shape = (arr.shape[0], arr.shape[1] * arr.shape[2])
    return [x for x in arr.tolist()]


def iter_exception_group(exc: BaseExceptionGroup, level: int = 0) -> str:
    r"""Traverses an exception tree, yielding formatted strings for each exception encountered

    :param exc: The exception group to traverse
    :param level: The current indentation level, defaults to 0, defaults to 0
    :yield: Formatted (and indented) string representation of each exception encountered in the tree.

    >>> exc = BaseExceptionGroup(
    ...     "level 1.0",
    ...     [
    ...         BaseExceptionGroup(
    ...             "level 2.0",
    ...             [
    ...                 BaseExceptionGroup(
    ...                     "level 3.0",
    ...                     [
    ...                         ValueError("abc"),
    ...                         KeyError("99"),
    ...                         BaseExceptionGroup("level 4.0", [TabError("nu uh")]),
    ...                     ],
    ...                 )
    ...             ],
    ...         ),
    ...         BaseExceptionGroup("level 2.1", [ValueError("345")]),
    ...     ],
    ... )
    >>> print("\n".join(iter_exception_group(exc)))
    level 1.0 (2 sub-exceptions):
     level 2.0 (1 sub-exception):
      level 3.0 (3 sub-exceptions):
       - ValueError('abc')
       - KeyError('99')
       level 4.0 (1 sub-exception):
        - TabError('nu uh')
     level 2.1 (1 sub-exception):
      - ValueError('345')
    """
    indent = " " * level
    if isinstance(exc, BaseExceptionGroup):
        yield f"{indent}{exc!s}:"
        for e in exc.exceptions:
            yield from iter_exception_group(e, level + 1)
    else:
        yield f"{indent}- {exc!r}"


def get_device(
    device: str, host: str = "127.0.0.1", port: int = None
) -> FlowCellPosition:
    """Get a position for a specific device over the minknow API

    :param device: The device name - example X1 or MS00000
    :param host: The host the RPC is listening on, defaults to "127.0.0.1"
    :param port: The port the RPC is listening on, defaults to None
    :raises ValueError: If their is no match on any of the positions for the given device name
    :return: The position representation from the MinkKNOW API
    """
    manager = Manager(host=host, port=port)
    for position in manager.flow_cell_positions():
        if position.name == device:
            return position
    raise ValueError(f"Could not find device {device!r}")


if __name__ == "__main__":
    import doctest

    doctest.testmod()
