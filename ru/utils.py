import logging
from collections import namedtuple, defaultdict
from pathlib import Path
from random import random
import numpy as np
import toml
from operator import itemgetter
import json
import jsonschema
from enum import IntEnum

from ru.channels import MINION_CHANNELS, FLONGLE_CHANNELS


class Severity(IntEnum):
    INFO = 1
    WARN = 2
    ERROR = 3


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
    rpc_connection.log.send_user_message(severity=severity, user_message=message)


def dynamic_import(name):
    """Dynamically import modules and classes, used to get the ReadCache

    https://stackoverflow.com/a/547867/3279716
    https://docs.python.org/2.4/lib/built-in-funcs.html

    Parameters
    ----------
    name : str
        The module/class path. E.g: "read_until.read_cache.{}".format("ReadCache")

    Returns
    -------
    module
    """
    components = name.split('.')
    mod = __import__(components[0])
    for comp in components[1:]:
        mod = getattr(mod, comp)
    return mod


def named_tuple_generator(dictionary, name='Conditions',):
    """Generate named tuple from dictionary

    Parameters
    ----------
    dictionary : dict
        dict to turn into a named tuple
    name : str
        The name to give the named tuple

    Returns
    -------
    namedtuple
    """
    return namedtuple(name, dictionary.keys())(**dictionary)


def nice_join(seq, sep=", ", conjunction="or"):
    """Join lists nicely"""
    seq = [str(x) for x in seq]

    if len(seq) <= 1 or conjunction is None:
        return sep.join(seq)
    else:
        return "{} {} {}".format(sep.join(seq[:-1]), conjunction, seq[-1])


def get_log_level(s):
    """Get log level from logging"""
    return getattr(logging, s.upper())


def read_lines_to_list(f):
    """Read file to list and return the list"""
    with open(f) as fh:
        lines = [line.strip() for line in fh]
    return lines


def print_args(args, logger=None, exclude=None):
    """Print and format all arguments from the command line"""
    if exclude is None:
        exclude = []
    dirs = dir(args)
    m = max([len(a) for a in dirs if a[0] != '_'])
    for attr in dirs:
        if attr[0] != '_' and attr not in exclude and attr.lower() == attr:
            if logger is not None:
                logger.info("{a}={b}".format(a=attr, m=m, b=getattr(args, attr)))
            else:
                print('{a:<{m}}\t{b}'.format(a=attr, m=m, b=getattr(args, attr)))


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
            max(coords, key=itemgetter(0))[0] + 1
        ),
        dtype=int
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


def get_targets(targets):
    """

    Parameters
    ----------
    targets : str or List[str]

    Returns
    -------
    defaultdict of list
    {
        'strand':
            {
                'contig': [(int, int), ...]
            }
    }
    """
    t = defaultdict(lambda: defaultdict(list))
    if isinstance(targets, str):
        # Load from list
        if Path(targets).is_file():
            targets = read_lines_to_list(targets)
        # If targets is not a file, then raise error

    for item in targets:
        ctg, *coords = item.split(",")
        if coords:
            strand = coords.pop()
            t[strand][ctg].append(tuple(int(x) for x in coords))
        else:
            for strand in ["+", "-"]:
                t[strand][ctg].append((0, float("inf")))

    return t


def load_config_toml(filepath, validate=True):
    """Load a TOML file and check file paths

    Parameters
    ----------
    filepath : str
        Path to the TOML config file
    validate : bool
        If True, test TOML file against the JSON schema (./static/readfish_toml.schema.json)

    Returns
    -------
    dict
        Returns dict of TOML config
    """
    # Check that TOML config file exists
    p = Path(filepath)
    if not p.is_file():
        raise FileNotFoundError("TOML config file not found at '{}'".format(filepath))

    # Load TOML to dict
    toml_dict = toml.load(p)

    # Check reference path
    reference_text = toml_dict.get("conditions", {}).get("reference", "")
    reference_path = Path(reference_text)
    if not reference_path.is_file() and reference_text:
        raise FileNotFoundError("Reference file not found at '{}'".format(reference_path))

    # Get keys for all condition tables, allows safe updates
    conditions = [k for k, cond in toml_dict.get("conditions", {}).items() if isinstance(cond, dict)]

    # Load targets from a file
    for k in conditions:
        targets = toml_dict["conditions"][k].get("targets", [])
        if isinstance(targets, str):
            if not Path(targets).is_file():
                raise FileNotFoundError("Targets file not found at '{}'".format(targets))

            toml_dict["conditions"][k]["targets"] = read_lines_to_list(targets)

    # Validate our TOML file
    if validate:
        # Load json schema
        _f = Path(__file__).parent / "static/readfish_toml.schema.json"
        with _f.resolve().open() as fh:
            schema = json.load(fh)
        try:
            jsonschema.validate(toml_dict, schema)
        except jsonschema.exceptions.ValidationError as err:
            print("😾 this TOML file has failed validation. See below for details:")
            raise

    return toml_dict


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
        yield "Using reference: {}".format(mapper.index), Severity.INFO
        seq_names = set(mapper.mapper.seq_names)

        for region in conditions:
            conds = {
                "unblock": [],
                "stop_receiving": [],
                "proceed": [],
            }
            for m in ("single_on", "single_off", "multi_on", "multi_off", "no_map", "no_seq"):
                conds[getattr(region, m)].append(m)
            conds = {k: nice_join(v) for k, v in conds.items()}
            s = (
                "Region '{}' (control={}) has {} target{} of which {} are in the reference. "
                "Reads will be unblocked when classed as {unblock}; sequenced when classed as "
                "{stop_receiving}; and polled for more data when classed as {proceed}.".format(
                    region.name,
                    region.control,
                    len(region.targets),
                    {1: ""}.get(len(region.targets), "s"),
                    len(region.targets & seq_names),
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
            for m in ("single_on", "single_off", "multi_on", "multi_off", "no_map", "no_seq"):
                conds[getattr(region, m)].append(m)
            conds = {k: nice_join(v) for k, v in conds.items()}
            s = (
                "Region '{}' (control={}) has {} target{}. "
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


def get_run_info(toml_filepath, num_channels=512):
    """Convert a TOML representation of a ReadFish experiment to conditions that
    can be used used by the analysis function

    Parameters
    ----------
    toml_filepath : str
        Filepath to a configuration TOML file
    num_channels : int
        Total number of channels on the sequencer, expects 512 for MinION and 3000 for
        PromethION

    Returns
    -------
    run_info : dict
        dict with a key per channel, the value maps to an index in `split_conditions`
    split_conditions : list
        List of namedtuples with conditions specified in the TOML file
    reference : str
        The path to the reference MMI file
    caller_settings : dict
        kwargs to pass to the base caller. If not found in the TOML an empty dict
        is returned
    """
    toml_dict = load_config_toml(toml_filepath)

    # Get condition keys, these should be ascending integers
    conditions = [
        k for k in toml_dict["conditions"].keys()
        if isinstance(toml_dict["conditions"].get(k), dict)
    ]

    # If maintain_order, is True: condition keys are sorted -> [0, 1, 2, 3]
    #  else: sorted is used with random.random() to shuffle the keys -> [4, 1, 2, 3]
    #  this sort is applied during the creation of `split_conditions`
    #  If maintain_order is not provided, evaluates True -> sorted
    if toml_dict["conditions"].get("maintain_order", True):
        sort_func = lambda L: sorted(L)
    else:
        sort_func = lambda L: sorted(L, key=lambda k: random())

    # Generate the flowcell lists
    axis = toml_dict["conditions"].get("axis", 1)
    split_channels = generate_flowcell(num_channels, split=len(conditions), axis=axis)

    # convert targets to sets
    for k in conditions:
        cond = toml_dict["conditions"].get(k)
        if not isinstance(cond, dict):
            continue
        cond["coords"] = get_targets(cond["targets"])

        _t = []
        for _k in cond["coords"].keys():
            _t.extend(cond["coords"].get(_k).keys())

        cond["targets"] = set(_t)

    # Create a list of named tuples, these are the conditions
    split_conditions = [
        named_tuple_generator(toml_dict["conditions"].get(k))
        for k in sort_func(toml_dict["conditions"].keys())
        if isinstance(toml_dict["conditions"].get(k), dict)
    ]

    run_info = {
        channel: pos
        for pos, (channels, condition) in enumerate(
            zip(split_channels, split_conditions)
        )
        for channel in channels
    }

    reference = toml_dict["conditions"].get("reference")
    caller_settings = toml_dict.get("caller_settings", {})

    return run_info, split_conditions, reference, caller_settings


def between(pos, coords):
    """Return bool if position is between the coords

    Parameters
    ----------
    pos : int
        Position to check
    coords : tuple
        Region to check between

    Returns
    -------
    bool

    Examples
    --------

    Between can use any valid floats in the `coords` tuple

    >>> between(500, (0, float("inf")))
    True
    >>> between(5, (10, 100))
    False
    >>> any([between(5, (10, 100)), between(245000000, (0, float("inf"))), ])
    True
    >>> any([between(5, (10, 100)), between(-1, (0, float("inf"))), ])
    False

    """
    return min(coords) <= pos <= max(coords)


def setup_logger(name, log_format="%(message)s", log_file=None, level=logging.DEBUG):
    """Setup loggers

    Parameters
    ----------
    name : str
        Name to give the logger
    log_format : str
        logging format string using % formatting
    log_file : str
        File to record logs to, sys.stderr if not set
    level : logging.LEVEL
        Where logging.LEVEL is one of (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns
    -------
    logger
    """
    """Function setup as many loggers as you want"""
    formatter = logging.Formatter(log_format)
    if log_file is not None:
        handler = logging.FileHandler(log_file, mode="w")
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


if __name__ == "__main__":
    import doctest
    doctest.testmod()
