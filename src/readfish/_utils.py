"""utils.py
functions and utilities used internally.
"""
import sys
import logging
from collections import Counter
from functools import reduce
from operator import itemgetter
from enum import IntEnum
import re
import base64
import zlib

import numpy as np
from minknow_api.manager import Manager

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
    INFO = 1
    WARN = 2
    ERROR = 3


def nested_get(obj, key, default=None, *, delim="."):
    """Get a value from a nested structure

    Examples
    --------
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
    """

    def _get(o, k):
        if isinstance(o, dict):
            return o.get(k, default)
        else:
            return getattr(o, k, default)

    return reduce(_get, key.split(delim), obj)


def compress_and_encode_string(original_str):
    """Compresses a string, encodes it in base-64, and returns an ASCII string representation of the compressed blob.

    Parameters
    ----------
    original_str : str
        The string to be compressed and encoded.

    Returns
    -------
    str
        An ASCII string representation of the compressed and base-64 encoded blob.

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


def decode_and_decompress_string(encoded_str):
    """Decodes an ASCII string representation of a compressed blob, decompresses it, and returns the original string.
    This is the reverse of `compress_and_encode_string`.

    Parameters
    ----------
    encoded_str : str
        An ASCII string representation of the compressed and base-64 encoded blob.

    Returns
    -------
    str
        The original string that was compressed and encoded.

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


def escape_message_to_minknow(message, chars):
    r"""Escape characters in the chars list if they are in message

    Parameters
    ----------
    message : str
        The message that is being sent
    chars : list[str], str
        The characters to escape

    Returns
    -------
    message : str

    Examples
    --------
    >>> escape_message_to_minknow("20%", ["%"])
    '20\\%'
    >>> escape_message_to_minknow("20\\%", ["%"])
    '20\\%'
    >>> escape_message_to_minknow("20", ["%"])
    '20'
    """
    for char in chars:
        message = re.sub(rf"(?<!\\){char}", rf"\\{char}", message)
    return message


def send_message(rpc_connection, message, severity):
    """Send a message to MinKNOW

    Parameters
    ----------
    rpc_connection
        An instance of the rpc.Connection
    message : str
        The message to send
    severity : int
        The severity to use for the message: 1=info, 2=warning, 3=error

    Returns
    -------
    None
    """
    message = escape_message_to_minknow(message, "%")
    rpc_connection.log.send_user_message(severity=severity, user_message=message)


def nice_join(seq, sep=", ", conjunction="or"):
    """Join lists nicely"""
    seq = [str(x) for x in seq]

    if len(seq) <= 1 or conjunction is None:
        return sep.join(seq)
    else:
        return f"{sep.join(seq[:-1])} {conjunction} {seq[-1]}"


def get_coords(channel, flowcell_size):
    """Return a channel's coordinates given a flowcell size

    Parameters
    ----------
    channel : int
        The channel to retrieve the coordinates for
    flowcell_size : int
        The flowcell size, this is used to determine the flowcell layout

    Returns
    -------
    tuple
        Tuple of int: (column, row)

    Raises
    ------
    ValueError
        Raised if channel outside of bounds (0, flowcell_size)
        Raised if flowcell_size not one of [128, 512, 3000]
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


def get_flowcell_array(flowcell_size):
    """Return a numpy.ndarray in the shape of a flowcell

    Parameters
    ----------
    flowcell_size : int
        The total number of channels on the flowcell; 126 for Flongle, 512
        for MinION, and 3000 for PromethION

    Returns
    -------
    np.ndarray
        An N-dimensional array representation of the flowcell

    Examples
    --------
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


def generate_flowcell(flowcell_size, split=1, axis=1, odd_even=False):
    """Return an list of lists with channels to use in conditions

    Representations generated by this method are evenly split based on the physical
    layout of the flowcell. Each sub-list is the same size. Axis determines whether
    the flowcell divisions will go left-right (0) or top-bottom (1); as flongle has
    a shape of (10, 13) the top-bottom axis cannot be split evenly.

    Parameters
    ----------
    flowcell_size : int
        The total number of channels on the flowcell; 126 for Flongle, 512 for MinION,
        and 3000 for PromethION
    split : int
        The number of sections to split the flowcell into, must be a positive factor
        of the flowcell dimension
    axis : int, optional
        The axis along which to split,
        see: https://docs.scipy.org/doc/numpy/glossary.html?highlight=axis
    odd_even : bool
        Return a list of two lists split into odd-even channels,
        ignores `split` and `axis`

    Returns
    -------
    list
        A list of lists with channels divided equally

    Raises
    ------
    ValueError
        Raised when split is not a positive integer
        Raised when the value for split is not a factor on the axis provided

    Examples
    --------
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


def iter_exception_group(exc, level=0):
    r"""Traverses an exception tree, yielding formatted strings for each exception encountered

    Parameters
    ----------
    exc : BaseExceptionGroup
        The exception group to traverse
    level : int
        The current indentation level, defaults to 0

    Yields
    ------
    str
        Formatted (and indented) string representation of each exception encountered in the tree.

    Examples
    --------
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


# TODO: Rewrite to use the new Conf class, maybe make a method on the Conf?
def describe_experiment(conditions, mapper):
    """

    Parameters
    ----------
    conditions : List[NamedTuple, ...]
        List of named tuples, should be conditions from get_run_info
    mapper : mappy.mapper
        Instance of mappy.mapper initialised with the reference passed from
        get_run_info

    Yields
    ------
    str
        Message string
    severity : Severity
        One of Severity.INFO, Severity.WARN or Severity.ERROR

    """
    # TODO: conditional 's' here
    yield "This experiment has {} region{} on the flowcell".format(
        len(conditions), {1: ""}.get(len(conditions), "s")
    ), Severity.INFO

    if mapper.initialised:
        yield f"Using reference: {mapper.index}", Severity.INFO
        seq_names = set(mapper.seq_names)

        # Get total seq length of the reference.
        ref_len = 0
        for seq_name in seq_names:
            ref_len += len(mapper.seq(seq_name))

        # Convert to double stranded
        ref_len = 2 * ref_len

        for region in conditions:
            conds = {
                "unblock": [],
                "stop_receiving": [],
                "proceed": [],
            }
            for m in (
                "single_on",
                "single_off",
                "multi_on",
                "multi_off",
                "no_map",
                "no_seq",
            ):
                conds[getattr(region, m)].append(m)
            conds = {k: nice_join(v) for k, v in conds.items()}

            target_total = 0
            target_count = 0
            for strand in ["+", "-"]:
                for chromosome in region.coords[strand]:
                    total = 0
                    for s, f in region.coords[strand][chromosome]:
                        region_len = abs(f - s)
                        if np.isinf(region_len):
                            region_len = len(mapper.seq(chromosome))
                        total += region_len
                        target_count += 1
                    target_total += total

            s = (
                "Region '{}' (control={}) has {} contig{} of which {} are in the reference. "
                "There are {} targets (including +/- strand) representing {}% of the reference. "
                "Reads will be unblocked when classed as {unblock}; sequenced when classed as "
                "{stop_receiving}; and polled for more data when classed as {proceed}.".format(
                    region.name,
                    region.control,
                    len(region.targets),
                    {1: ""}.get(len(region.targets), "s"),
                    len(region.targets & seq_names),
                    target_count,
                    round(target_total / ref_len * 100, 2),
                    **conds,
                )
            )
            yield s, Severity.INFO
    else:
        yield "No reference file provided", Severity.WARN
        for region in conditions:
            conds = {
                "unblock": [],
                "stop_receiving": [],
                "proceed": [],
            }
            for m in (
                "single_on",
                "single_off",
                "multi_on",
                "multi_off",
                "no_map",
                "no_seq",
            ):
                conds[getattr(region, m)].append(m)
            conds = {k: nice_join(v) for k, v in conds.items()}
            s = (
                "Region '{}' (control={}) has {} contig{}. "
                "Reads will be unblocked when classed as {unblock}; sequenced when classed as "
                "{stop_receiving}; and polled for more data when classed as {proceed}.".format(
                    region.name,
                    region.control,
                    len(region.targets),
                    {1: ""}.get(len(region.targets), "s"),
                    **conds,
                )
            )

            yield s, Severity.WARN


def get_device(device, host="127.0.0.1", port=None):
    """Get an RPC connection from a device"""
    manager = Manager(host=host, port=port)
    for position in manager.flow_cell_positions():
        if position.name == device:
            return position
    raise ValueError(f"Could not find device {device!r}")


if __name__ == "__main__":
    import doctest

    doctest.testmod()
