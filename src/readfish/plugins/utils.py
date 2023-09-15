from __future__ import annotations
from enum import Enum, unique
from functools import partial
from itertools import filterfalse
from typing import Any, Iterator, List, Dict, Tuple, Optional, Union, Protocol
from collections import defaultdict, namedtuple
from collections.abc import Container
from pathlib import Path
from io import StringIO
import csv

import attrs
import numpy as np

TARGET_INTERVAL = namedtuple("TargetInterval", "chromosome start end strand")


def get_contig_lengths(al) -> dict[str, int]:
    """
    Get the lengths of all contigs in the reference genome provided by an Aligner instance.

    :param al: An Aligner instance representing the reference genome.
    :type al: AlignerABC
    :return: A dictionary mapping contig names to their respective lengths.
    """
    genome = {}
    for seq in al.seq_names:
        if seq in genome:
            raise RuntimeError(f"Duplicate sequence name {seq} in reference file")
        genome[seq] = len(al.seq(seq))
    return genome


def _summary_percent_reference_covered(
    ref_len: int, targets: Targets, genome: dict[str, int]
) -> float:
    """
    Calculate the percentage of the reference covered by target intervals. Not formatted (i.e is a decimal)

    This function takes the length of a reference sequence, The targets class for a given _Condition class,
    and a dictionary of contig names to contig lengths (used for getting contig lengths if we have entire contigs as targets).
    It calculates the total length covered by the target intervals
    and returns the percentage of the reference sequence that is covered by this length.

    :param ref_len: The length of the reference sequence.
    :param targets: The targets class for a given _Condition class
    :param genome: A dictionary of contig names to contig lengths. Used if a target is in the entire contig.

    :return: The percentage of the reference sequence covered by the target intervals.
    """
    num_bases_in_targets = sum_target_coverage(targets.iter_targets(), genome)
    percentage_ref_covered = num_bases_in_targets / ref_len
    return percentage_ref_covered


def is_empty(item: Any) -> bool:
    """
    Check if an item is empty.

    This function checks whether the given item is empty. An item is considered empty if it is an empty Container (Set, Tuple, Dict, List etc.).
    For primitive types (Float, Int, String etc.), this function considers them non-empty.
    considers them non-empty.

    :param item: The item to check for emptiness.

    :return: True if the item is empty, False otherwise.

    :Examples:

    >>> is_empty(42)
    False
    >>> is_empty("Hello, world!")
    False
    >>> is_empty([])
    True
    >>> is_empty({})
    True
    >>> is_empty([1, 2, 3])
    False
    >>> is_empty({"a": 1, "b": 2})
    False
    >>> is_empty([[], [], []])
    False
    >>> is_empty([{}, {}])
    False
    >>> is_empty(None)
    False
    """
    if isinstance(item, Container):
        return not bool(item)
    return False


def count_dict_elements(d: dict[Any]) -> int:
    """
    Recursively count all the bottom elements of an arbitrarily nested dictionary.
    If the bottom element v is a list, return the length of the list, else return 1 for each v at the bottom of the list.

    Note - This will break for nested lists, i.e will only count the list as one, ignoring the sublists - see the last doctest for an example.
    This is not a problem for the current use case, but may be in the future.

    :param d: Dictionary to count elements of, may or may not be nested
    :return: Count of elements at lowest point in tree

    >>> simple_dict = {"a": 1, "b": 2, "c": 3}
    >>> count_dict_elements(simple_dict)
    3

    >>> string_dict = {"a": 1, "b": {"x": ["10", "2000"]}, "c": {"y": {"z": [30, 40, 50]}}}
    >>> count_dict_elements(string_dict)
    6

    >>> nested_dict = {"a": 1, "b": {"x": [10, 20]}, "c": {"y": {"z": [30, 40, 50]}}}
    >>> count_dict_elements(nested_dict)
    6

    >>> empty_dict = {"a": {}, "b": {"x": {}}, "c": {"y": {"z": []}}}
    >>> count_dict_elements(empty_dict)
    0

    >>> mixed_dict = {"a": 1, "b": {"x": [10, 20]}, "c": {"y": {"z": [30, 40, 50], "w": 7.0}}}
    >>> count_dict_elements(mixed_dict)
    7

    >>> empty_list_dict = {"a": [], "b": [{}], "c": [[], [], []]}
    >>> count_dict_elements(empty_list_dict)
    0

    # Nested lists are not counted properly

    >>> nested_list_dict = {"a": [], "b": [{}], "c": [[1, 2, [1, 2]], [], []]}
    >>> count_dict_elements(nested_list_dict)
    1
    """
    return sum(
        (
            count_dict_elements(v) if isinstance(v, dict)
            # If v is a list, tuple, sequence, dict etc., return the length of the container filtering out any empty sun elements,
            else len(list(filterfalse(partial(is_empty), v)))
            if isinstance(v, Container)
            else 1
            for v in d.values()
        )
    )


def _calculate_length(target_interval: TARGET_INTERVAL, genomes: dict[str, int]) -> int:
    """
    Take in the value of a given target, either in the form of (target_start, target_stop),
    or 0, np.inf. If 0, inf, get the length of the contig out of the mappy index. If tuple, return the absolute distance
    covered by the target, calculated by target_stop - target start.

    :param v: The value of the target coordinates.
    :param k: The name of the reference contig this target is on"""
    target_interval_length = abs(target_interval.end - target_interval.start)
    # If inf, get the length of the contig out of the mappy index
    if np.isinf(target_interval_length):
        target_interval_length = genomes[target_interval.chromosome]
    return target_interval_length


def sum_target_coverage(
    targets: Iterator[TARGET_INTERVAL], genomes: dict[str, int]
) -> int:
    """
    Recursively find the coverage of the range of a set of Targets - ASSUMES bottoms elements are in the form
    dict[chromosome_name, tuple[float, float]] or tuple[int, int], i.e genomic coordinates

    If there are no targets, return 0.

    :param targets: An iterator of TARGET_INTERVAL objects. Obtained from the Targets.iter_targets() method.
    :param genomes: A dictionary of contig names to contig lengths. Used if a target is in the entire contig.
    :return: sum of distance covered by ranges of targets in `d`.
    """
    # Empty targets
    summed_coverage = None
    summed_coverage = sum(
        (_calculate_length(target_interval, genomes) for target_interval in targets)
    )
    return summed_coverage if summed_coverage is not None else 0


class _AlignmentAttribute(Protocol):
    ctg: str
    r_st: int
    r_en: int
    strand: Strand | int | str


class _AlignmentProperty(Protocol):
    """
    >>> from collections import namedtuple
    >>> from dataclasses import dataclass
    >>> from typing import NamedTuple
    >>> Example1 = namedtuple("Example1", "ctg r_st r_en strand")
    >>> @dataclass
    ... class Example2:
    ...     ctg: str
    ...     r_st: int
    ...     r_en: int
    ...     strand: int
    >>> Example3 = NamedTuple("Example3", [("ctg", str), ("r_st", int), ("r_en", int), ("strand", Strand)])
    >>> eg1 = Example1("chr1", 10, 100, "+")
    >>> eg2 = Example2("chr2", 20, 200, -1)
    >>> eg3 = Example3("chr3", 30, 300, Strand("+"))
    """

    # fmt: off
    @property
    def ctg(self) -> str: ...
    @property
    def r_st(self) -> int: ...
    @property
    def r_en(self) -> int: ...
    @property
    def strand(self) -> Strand | int | str: ...
    # fmt: on


# Use a `Union` here to allow both attributes and properties
Alignment = Union[_AlignmentAttribute, _AlignmentProperty]


@unique
class Decision(Enum):
    """Decision readfish has made about a read after Alignment"""

    #: The read aligned to a single location that is within a target region
    single_on: str = "single_on"
    #: The read aligned to a single location that is not in a target region
    single_off = "single_off"
    #: The read aligned to multiple locations, where at least one alignment is within a target region
    multi_on = "multi_on"
    #: The read aligned to multiple locations, none of which were in a target region
    multi_off = "multi_off"
    #: The read was basecalled but did not align
    no_map = "no_map"
    #: The read did not basecall
    no_seq = "no_seq"
    #: Too many signal chunks have been collected for this read
    above_max_chunks = "above_max_chunks"
    #: Fewer signal chunks for this read collected than required
    below_min_chunks = "below_min_chunks"


@unique
class Action(Enum):
    """
    Action to take for a read.

    This enum class represents different actions that can be taken for a read during sequencing.
    Each action has a corresponding string value used for logging.

    :cvar unblock: Send an unblock command to the sequencer.
    :cvar stop_receiving: Allow the read to finish sequencing.
    :cvar proceed: Sample another chunk of data.

    :Example:

    Define an Action:

    >>> action = Action.unblock

    Access the string value of an Action:

    >>> action.value
    'unblock'
    """

    #: Send an unblock command to the sequencer
    unblock = "unblock"
    #: Allow the read to finish sequencing
    stop_receiving = "stop_receiving"
    #: Sample another chunk of data
    proceed = "proceed"


@attrs.define
class Result:
    """Result holder

    This should be progressively filled with data from the basecaller,
    barcoder, and then the aligner.

    :param channel: The channel that this read is being sequenced on
    :param read_number: The read number value from the Read Until API
    :param read_id: The read ID assigned to this read by MinKNOW
    :param seq: The basecalled sequence for this read
    :param decision: The ``Decision`` that has been made, this will by used to determine the ``Action``
    :param barcode: The barcode that has been assigned to this read
    :param basecall_data: Any extra data that the basecaller may want to send to the aligner
    :param alignment_data: Any extra alignment data
    """

    channel: int
    read_number: int
    read_id: str
    seq: str
    decision: Decision = attrs.field(default=Decision.no_seq)
    barcode: Optional[str] = attrs.field(default=None)
    basecall_data: Optional[Any] = attrs.field(default=None)
    alignment_data: Optional[list[Alignment]] = attrs.field(default=None)


@unique
class Strand(Enum):
    """Enum representing the forward and reverse strand of DNA for alignments"""

    #: Forward strand
    forward = "+"
    #: Reverse strand
    reverse = "-"


@attrs.define
class Targets:
    """The targets for a given region

    :param value: The raw value from the TOML file
    :param _targets: The parsed targets. Strand -> Contig -> List of Coordinates list[(start, stop)]
    """

    value: Union[List[str], Path] = attrs.field(default=attrs.Factory(list))
    _targets: Dict[Strand, Dict[str, List[Tuple[float, float]]]] = attrs.field(
        repr=False, alias="_targets", init=False
    )

    @classmethod
    def from_parsed_toml(cls, targets: List[str] | str) -> Targets:
        """Create the target array from the targets that have been read from the provided TOML file

        :param targets: The targets array or a target file, containing a file per line
        :raises ValueError: Raised if the supplied target is a file that cannot be parsed
        :raises ValueError: If we fail to initialise class
        :return: Initialised targets class
        """
        if isinstance(targets, list):
            # Assumes all elements are also `str`
            return cls(targets)
        elif isinstance(targets, str):
            # Assumes that a `str` on it's own is a Path
            if Path(targets).is_file():
                return cls(Path(targets))
            else:
                raise ValueError(
                    f"Supplied value {targets!r} is not a readable file. "
                    "Ensure that an absolute path is supplied."
                )
        raise ValueError(f"Could not use value {targets!r} for targets.")

    def __attrs_post_init__(self):
        """Post initialisation

        Used to fully parse the targets as this requires reading the values from a file/array

        :raises ValueError: Too many columns in a bed file record
        """
        self._targets = defaultdict(lambda: defaultdict(list))
        bed_file = False
        if isinstance(self.value, Path):
            suffixes = [s.lower() for s in self.value.suffixes]
            if ".bed" in suffixes:
                delim = "\t"
                bed_file = True
            else:
                delim = ","
            with self.value.open() as fh:
                values = StringIO(fh.read(), newline="")
        else:
            delim = ","
            values = StringIO("\n".join(self.value), newline="")
        for line, row in enumerate(csv.reader(values, delimiter=delim), start=1):
            if bed_file and len(row) != 6:
                raise ValueError(f"Invalid bed record in {self.value!s} at line {line}")
            ctg, *coords = row
            if coords:
                st, en, *_, strand = coords
                self._targets[Strand(strand)][ctg].append((float(st), float(en)))
            else:
                self._targets[Strand("+")][ctg].append((0, float("inf")))
                self._targets[Strand("-")][ctg].append((0, float("inf")))

        for strand, inner in self._targets.items():
            for ctg, intervals in inner.items():
                self._targets[strand][ctg] = self._merge_intervals(intervals)

    @staticmethod
    def _merge_intervals(
        intervals: List[Tuple[float, float]]
    ) -> List[Tuple[float, float]]:
        """If target coordinates overlap, we merge them into a single target

        >>> targets = Targets(["chr1,10,20,+", "chr1,15,30,+"])
        >>> targets._targets[Strand("+")]["chr1"]
        [(10.0, 30.0)]

        :param intervals: The target start and stop coordinates
        :return: The target stop and start coordinates, with any overlapping coordinates merged into one encompassing coordinate
        """
        if len(intervals) < 2:
            return intervals
        intervals.sort()
        n_args = len(intervals)
        res = [intervals[0]]
        for next_idx, (curr_s, curr_e) in enumerate(intervals, start=1):
            if next_idx == n_args:
                # Last interval, set last end position
                res[-1] = res[-1][0], max(res[-1][1], curr_e)
                break

            next_s, next_e = intervals[next_idx]
            if curr_e >= next_s or res[-1][1] >= next_s:
                # current end and next start overlap OR
                #   previous end and next start overlap
                res[-1] = res[-1][0], max(curr_e, next_e, res[-1][1])
            else:
                res.append((next_s, next_e))
        return res

    def check_coord(self, contig: str, strand: Strand | int | str, coord: int) -> bool:
        """Check to see if a coordinate is within any of the target regions

        :param contig: The target contig name
        :param strand: The strand that the alignment is to
        :param coord: The coordinate to be checked
        :raises ValueError: If the strand passed is not recognised
        :return: Boolean representing whether the coordinate is within a target region or not
        """
        strand_ = {
            1: Strand.forward,
            "+": Strand.forward,
            Strand.forward: Strand.forward,
            -1: Strand.reverse,
            "-": Strand.reverse,
            Strand.reverse: Strand.reverse,
        }.get(strand, None)
        if strand_ is None:
            raise ValueError("Unexpected strand {strand}")
        intervals = self._targets[strand_][contig]
        # TODO: Binary search intervals when intervals > 30? -> pytest parameterise and benchmark
        return any(start <= coord <= end for start, end in intervals)

    def iter_targets(self):
        """
        Iterate over the intervals for a _Conditions target intervals, yielding TARGET_INTERVAL objects.

        This method iterates over the target intervals stored in the `Targets` object and yields
        `TARGET_INTERVAL` objects representing each target interval.

        :return: Generator that yields `TARGET_INTERVAL` objects.

        :Example:

        >>> targets = Targets(["chr1,10,20,+", "chr1,15,30,+"])
        >>> for target in targets.iter_targets():
        ...     print(target)
        TargetInterval(chromosome='chr1', start=10.0, end=30.0, strand=<Strand.forward: '+'>)

        >>> targets = Targets(["chr1,10,20,+", "chr2,5,15,-"])
        >>> for target in targets.iter_targets():
        ...     print((target.chromosome, target.start, target.end, target.strand))
        ('chr1', 10.0, 20.0, <Strand.forward: '+'>)
        ('chr2', 5.0, 15.0, <Strand.reverse: '-'>)

        >>> targets = Targets(["chr1,10,20,+", "chr2,5,15,-", "chr1,25,35,-"])
        >>> for target in targets.iter_targets():
        ...     print(target.chromosome, target.start, target.end, target.strand)
        chr1 10.0 20.0 Strand.forward
        chr2 5.0 15.0 Strand.reverse
        chr1 25.0 35.0 Strand.reverse
        """
        for strand, regions in self._targets.items():
            for chrom, coords_list in regions.items():
                for start, end in coords_list:
                    yield TARGET_INTERVAL(chrom, start, end, strand)


@attrs.define
class PreviouslySentActionTracker:
    """
    A class to keep track of the last action sent from a channel.

    This class provides methods to add and retrieve the last action sent for each channel.

    :param last_action: A dictionary mapping channel IDs to the last sent action for that channel.

    :Example:

    Initialize a PreviouslySentActionTracker:

    >>> tracker = PreviouslySentActionTracker()

    Add an action for channel number 1:

    >>> from readfish.plugins.utils import Action
    >>> action = Action.unblock
    >>> tracker.add_action(1, action)

    Retrieve the last action for a channel:

    >>> retrieved_action = tracker.get_action(1)
    >>> retrieved_action
    <Action.unblock: 'unblock'>

    Retrieve the last action for a channel that hasn't sent any actions:

    >>> no_action = tracker.get_action(2)
    >>> no_action is None
    True
    """

    last_actions: Dict[int, Action] = attrs.Factory(dict)

    def add_action(self, channel: int, action: Action) -> None:
        """
        This method adds an action to the last sent action tracker.

        :param channel: The channel to add the action to.
        :param action: The action to add to the channel.
        """
        self.last_actions[channel] = action

    def get_action(self, channel: int) -> Optional[Action]:
        """
        This method checks the last action sent for a channel, returning the action if it exists,
        otherwise returning None.

        :param channel: The channel to check the last action for.
        :return: The last action sent for the channel, or None if no action has been sent.
        """
        return self.last_actions.get(channel, None)
