from __future__ import annotations
from enum import Enum, unique
from functools import partial
from itertools import filterfalse
from typing import Any, Iterator, List, Dict, Tuple, Optional, Union, Protocol
from collections import defaultdict, namedtuple, Counter
from collections.abc import Container
from pathlib import Path
from io import StringIO
import csv
import sys

if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup

import attrs
import numpy as np


TARGET_INTERVAL = namedtuple("TargetInterval", "chromosome start end strand")
STRAND_VALUES = {"+", "-", "."}


@unique
class Strand(Enum):
    """Enum representing the forward and reverse strand of DNA for alignments"""

    #: Forward strand
    forward = "+"
    #: Reverse strand
    reverse = "-"

    def __invert__(self):
        """Flip the strand, using bitwise NOT (~)

        >>> ~Strand.forward
        <Strand.reverse: '-'>
        >>> ~Strand.reverse
        <Strand.forward: '+'>
        """
        return Strand.forward if self is Strand.reverse else Strand.reverse


STRANDS = {
    1: Strand.forward,
    "+": Strand.forward,
    Strand.forward: Strand.forward,
    -1: Strand.reverse,
    "-": Strand.reverse,
    Strand.reverse: Strand.reverse,
}


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
            (
                count_dict_elements(v)
                if isinstance(v, dict)
                # If v is a list, tuple, sequence, dict etc., return the length of the container filtering out any empty sun elements,
                else (
                    len(list(filterfalse(partial(is_empty), v)))
                    if isinstance(v, Container)
                    else 1
                )
            )
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


def coord_validator(row: dict[str, str]) -> tuple[dict, list[str]]:
    """
    Validates and converts the 'start' and 'end' fields in the given row
    dictionary to integers. If conversion is not possible, or if 'start'
    is greater than 'end', appends appropriate error messages to a list
    and returns the list along with the row dictionary. The error
    messages as intended to be collected and converted to a ValueError
    as part of a BaseExceptionGroup.

    :param row: A dictionary containing 'start' and 'end' fields,
                presumably as strings.
    :return: A tuple containing the possibly modified row dictionary
             and a list of error messages.

    :Example:

    >>> row = {'start': '10', 'end': '5'}
    >>> coord_validator(row)
    ({'start': 10, 'end': 5}, ['{target_specification_format} {line_number} start > end (10 > 5)'])

    >>> row = {'start': 'a', 'end': '20'}
    >>> coord_validator(row)
    ({'start': 'a', 'end': 20}, ["{target_specification_format} {line_number} start coordinate \'a\' could not be converted to an integer"])

    >>> row = {'start': '10', 'end': '20'}
    >>> coord_validator(row)
    ({'start': 10, 'end': 20}, [])
    """
    errors = []
    int_error = False
    for f in ("start", "end"):
        try:
            row[f] = int(row[f])
        except ValueError:
            errors.append(
                f"{{target_specification_format}} {{line_number}} {f} coordinate {row[f]!r} could not be converted to an integer"
            )
            int_error = True
    if not int_error and row["start"] > row["end"]:
        errors.append(
            f"{{target_specification_format}} {{line_number}} start > end ({row['start']} > {row['end']})"
        )
    return row, errors


def strand_validator(row: dict[str, str]) -> tuple[dict, list[str]]:
    """
    Validates the 'strand' field in the given row dictionary to be either '+',
    '-', or '.'. If the 'strand' field is '.', it is converted to '+-'. If the
    'strand' field is not one of the mentioned valid values, an error message
    is added to a list of errors, and the list of error messages along with the modified
    row dictionary are returned.

    :param row: A dictionary containing a 'strand' field.
    :return: A tuple containing the possibly modified row dictionary and a
             list of error messages.

    :Example:

    >>> row = {'strand': '.'}
    >>> strand_validator(row)
    ({'strand': '+-'}, [])

    >>> row = {'strand': 'x'}
    >>> strand_validator(row)
    ({'strand': 'x'}, ["{target_specification_format} {line_number} strand 'x' not one of ['+', '-', '.']"])
    >>> row = {'strand': '+'}
    >>> strand_validator(row)
    ({'strand': '+'}, [])

    Refer to http://genome.ucsc.edu/FAQ/FAQformat#format1 for more details on
    the strand field in BED format.
    """
    errors = []
    if row["strand"] is None or row["strand"] not in STRAND_VALUES:
        errors.append(
            f"{{target_specification_format}} {{line_number}} strand {row['strand']!r} not one of {sorted(STRAND_VALUES)!r}"
        )
    # If strand is . (No strand in the bed format), set to +-, see http://genome.ucsc.edu/FAQ/FAQformat#format1 for more details
    #  Done here so we can allow CSV to use it as well
    if row["strand"] == ".":
        row["strand"] = "+-"
    return row, errors


def row_checker(
    row: dict[str, str], mode: Optional[str] = "csv"
) -> tuple[dict, list[str]]:
    """
    Validates the given row dictionary based on the mode and returns
    the row along with any errors found during the validation.

    The mode alters the behaviour. If the mode is 'csv', the row is
    allowed to only contain the contig. If it is "bed", the first 6
    columns of the BED format are required.

    Refer to http://genome.ucsc.edu/FAQ/FAQformat#format1 for more details on
    the strand field in BED format.

    :param row: A dictionary containing the row data.
    :param mode: A string indicating the target specification type, either 'csv' or 'bed'.
    :return: A tuple containing the validated (and possibly corrected) row
             and a list of error messages encountered during validation.

    >>> row = {'chrom': 'chr1', 'start': '1000', 'end': '2000', 'strand': '+'}
    >>> row_checker(row, mode='csv')  # No errors, valid row
    ({'chrom': 'chr1', 'start': 1000, 'end': 2000, 'strand': '+'}, [])

    >>> row = {'chrom': 'chr1', 'start': '2000', 'end': '1000', 'strand': '+'}
    >>> # Coord validator will report an error due to start > end
    >>> row_checker(row, mode='csv')
    ({'chrom': 'chr1', 'start': 2000, 'end': 1000, 'strand': '+'}, ['{target_specification_format} {line_number} start > end (2000 > 1000)'])

    >>> row = {'chrom': None, 'start': '1000', 'end': '2000', 'strand': '+'}
    >>> # Chromosome value is missing, an error will be reported
    >>> row_checker(row, mode='csv')
    ({'chrom': None, 'start': 1000, 'end': 2000, 'strand': '+'}, ['{target_specification_format} {line_number} has no chromosome value'])

    >>> row = ["chr1", 0, 1000, "+"]
    >>> # Chromosome value is missing, an error will be reported
    >>> row_checker(row, mode='csv')
    (['chr1', 0, 1000, '+'], ['Input row is not a valid dictionary'])

    :raises ValueError: If the mode is neither 'csv' nor 'bed'.
    """
    errors = []
    if row is None or not isinstance(row, dict):
        return row, ["Input row is not a valid dictionary"]

    if mode not in ["csv", "bed"]:
        return row, [f"Invalid mode {mode!r}, expected 'csv' or 'bed'"]
    # Check for the chromosome value
    if not row.get("chrom"):
        errors.append(
            "{target_specification_format} {line_number} has no chromosome value"
        )
    # if contig but no start stop, set targets as whole contig for both strands
    if mode == "csv" and all(row[f] is None for f in ("start", "end", "strand")):
        row["start"] = 0
        row["end"] = float("inf")
        row["strand"] = "+-"
        return row, errors
    elif mode == "bed" and any(
        row[f] is None for f in ("chrom", "start", "end", "name", "score", "strand")
    ):
        errors.append(
            "{target_specification_format} {line_number} is an improperly formatted BED record"
        )
    row, coord_errors = coord_validator(row)
    row, strand_error = strand_validator(row)
    return row, errors + coord_errors + strand_error


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
    #: Potential second half of a duplex read
    duplex_override = "duplex_override"
    #: Read sequenced as translocated portion was of unknown length at start of readfish
    first_read_override = "first_read_override"


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


@attrs.define
class Targets:
    """
    Class representation of target regions of a genome.

    This class is responsible for parsing and managing target regions specified either
    through a TOML file or provided as a list of strings.

    :ivar Union[List[str], Path] value: The raw value from the TOML file, either a list of strings or a path.
    :ivar Dict[Strand, Dict[str, List[Tuple[float, float]]]] _targets: A nested dictionary containing parsed target
        information. This is not intended to be a part of the public API.

    .. note::
        Example:

        - Using a list of targets:

            >>> targets = Targets.from_parsed_toml(["chr1,100,200,+"])

        - Using a .bed file:

            targets = Targets.from_parsed_toml("/path/to/targets.bed")
    """

    value: Union[List[str], Path] = attrs.field(default=attrs.Factory(list))
    _targets: Dict[Strand, Dict[str, Counter]] = attrs.field(
        repr=False, alias="_targets", init=False
    )
    padding: int = attrs.field(default=0)

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
        """
        Post-initialisation hook for the Targets class.

        This method is executed immediately after the instance is created.
        It's responsible for parsing the targets either from a list or a file
        and initializing the private _targets attribute.

        :raises ValueError: If a bed file record has too many columns.
        :raises BaseExceptionGroup: If validation for target intervals fails.
        """
        self._targets = defaultdict(lambda: defaultdict(Counter))

        if isinstance(self.value, Path):
            delim = "\t" if ".bed" in [s.lower() for s in self.value.suffixes] else ","
            target_specification_format = f"{self.value} line"
            with self.value.open() as fh:
                values = StringIO(fh.read(), newline="")
        else:
            delim = ","
            target_specification_format = "TOML targets number"
            values = StringIO("\n".join(self.value), newline="")
        bed_file = delim == "\t"
        fields = ["chrom", "start", "end"]
        if bed_file:
            fields += ["name", "score", "strand"]
        else:
            fields += ["strand"]
        all_errors: List[ValueError] = []

        for line_number, row in enumerate(
            csv.DictReader(values, fieldnames=fields, restkey="extra", delimiter=delim),
            start=1,
        ):
            row, errors = row_checker(row, "bed" if bed_file else "csv")
            if errors:
                all_errors.extend(
                    [
                        ValueError(
                            e.format(
                                target_specification_format=target_specification_format,
                                line_number=line_number,
                            )
                        )
                        for e in errors
                    ]
                )
                continue
            for strand in row["strand"]:
                self._targets[Strand(strand)][row["chrom"]][
                    (row["start"], row["end"])
                ] = 0
        if all_errors:
            raise BaseExceptionGroup("Target intervals validation failure", all_errors)
        for strand, inner in self._targets.items():
            for ctg, intervals in inner.items():
                self._targets[strand][ctg] = self._merge_intervals(intervals)

    @staticmethod
    def _merge_intervals(
        intervals: Counter[Tuple[float, float], int]
    ) -> Counter[Tuple[float, float], int]:
        """
        Merges overlapping intervals and returns a Counter object with the merged intervals as keys
        and the sum of the counts of the merged intervals as values.

        The method will compare each interval with the next one in the sorted order and merge them if they overlap.
        If an interval does not overlap with any other, it remains unchanged in the output Counter object.

        :param intervals: A Counter object where keys are tuples representing intervals (start, end) and
                          values are the counts associated with each interval.

        :return: A Counter object with keys as the merged intervals and values as the aggregated count
                 of the original intervals that were merged.

        :raises ValueError: If the input intervals are not properly formatted.

        :Examples:

        >>> from collections import Counter
        >>> intervals = Counter({(1.0, 2.0): 1, (2.0, 3.0): 1, (3.0, 4.0): 1})
        >>> Targets._merge_intervals(intervals)
        Counter({(1.0, 4.0): 3})

        >>> intervals = Counter({(1.0, 2.0): 1, (3.0, 4.0): 1})
        >>> Targets._merge_intervals(intervals)
        Counter({(1.0, 2.0): 1, (3.0, 4.0): 1})

        :Notes:
        - The intervals are assumed to be half-open intervals [start, end), meaning that start is inclusive and end is exclusive.
        """
        if len(intervals) < 2:
            return intervals

        collapsed_intervals = Counter()
        intervals_items = sorted(intervals.items())
        (curr_start, curr_end), curr_count = intervals_items[0]

        for (start, end), count in intervals_items[1:]:
            if start > curr_end:  # We have a new non-overlapping start
                collapsed_intervals[(curr_start, curr_end)] = curr_count
                curr_start, curr_end, curr_count = start, end, count
            else:  # Start is within the current range
                curr_end = max(curr_end, end)
                curr_count += count

        collapsed_intervals[(curr_start, curr_end)] = curr_count
        return collapsed_intervals

    def check_coord(self, contig: str, strand: Strand | int | str, coord: int) -> bool:
        """Check to see if a coordinate is within any of the target regions
        :param contig: The target contig name
        :param strand: The strand that the alignment is to
        :param coord: The coordinate to be checked
        :raises ValueError: If the strand passed is not recognised
        :return: Boolean representing whether the coordinate is within a target region or not

        >>> targets = Targets(["chr1,10,20,+", "chr1,15,30,+"])
        >>> targets.check_coord('chr1', "+", 15)
        True
        >>> targets.check_coord('chr1', "+", 5)
        False
        >>> targets.check_coord('chr1', "-", 15)
        False
        >>> targets.check_coord('chr1', "+", 31)  # Example where coord (31) is in reversed target interval (+ve strand) Should fail
        False
        >>> targets.check_coord('chr1', "-", 41)  # Example where coord (41) is in reversed target interval (-ve strand) Should fail
        False
        >>> targets.check_coord('chr1', "unknown_strand", 15)
        Traceback (most recent call last):
        ...
        ValueError: Unexpected strand unknown_strand
        """
        strand_ = STRANDS.get(strand, None)
        if strand_ is None:
            message = f"Unexpected strand {strand}"
            raise ValueError(message)

        intervals = self._targets[strand_][contig]
        # TODO: Binary search intervals when intervals > 30? -> pytest parameterise and benchmark
        start_offset, end_offset = self.get_offset(strand_)
        for start, end in intervals:
            if (start + start_offset) <= coord <= (end + end_offset):
                intervals[(start, end)] += 1
                return True
        return False

    def get_offset(self, strand: Strand):
        """
        Get the start and end padding offsets for a given strand.

        :param strand_: The strand for which to get the offsets.

        :return: A tuple containing the start and end offsets.

        :Examples:

        >>> targets = Targets(["chr1,10,20,+", "chr1,15,30,+"], padding=10)
        >>> targets.get_offset(Strand.forward)
        (-10, 0)
        >>> targets.get_offset(Strand.reverse)
        (0, 10)

        """
        start_offset, end_offset = -self.padding, 0
        if strand == Strand.reverse:
            start_offset, end_offset = end_offset, -start_offset
        return start_offset, end_offset

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
        TargetInterval(chromosome='chr1', start=10, end=30, strand=<Strand.forward: '+'>)

        >>> targets = Targets(["chr1,10,20,+", "chr2,5,15,-"])
        >>> for target in targets.iter_targets():
        ...     print((target.chromosome, target.start, target.end, target.strand))
        ('chr1', 10, 20, <Strand.forward: '+'>)
        ('chr2', 5, 15, <Strand.reverse: '-'>)

        >>> targets = Targets(["chr1,10,20,+", "chr2,5,15,-", "chr1,25,35,-"])
        >>> for target in targets.iter_targets():
        ...     print(target.chromosome, target.start, target.end, target.strand)
        chr1 10 20 Strand.forward
        chr2 5 15 Strand.reverse
        chr1 25 35 Strand.reverse
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


@attrs.define
class DuplexTracker:
    """
    Wrapper class to keep track the alignment location of the latest read seen on a channel,
    and previous decision made, tracking whether we made a duplex override on the last read
    Specifically, we store a list of tuples of any target contig names and strands that were aligned to,
    keyed to channel number and the previous decision for a read made on that channel.
    The decision should only be updated when a read has been finalised and should not be seen again,
    i.e a Stop receiving or Unblock has been sent to MinKNOW
    No maps are specified as (*, *)
    """

    # Note - `readfish.src.plugins.utils.Alignment` could be used here, instead of tuple[str, Strand]
    # We could then use the results of the ALignment directly, if we ever wanted to do something more complex
    # for duplex
    previous_alignments: Dict[int, list[tuple[str, Strand]]] = attrs.Factory(dict)
    previous_decision: Dict[int, Decision] = attrs.Factory(dict)

    def get_previous_decision(self, channel: int) -> Decision:
        """
        Get the previous decision seen on this channel.

        :param channel: The channel number.
        :return: Previously seen decision
        >>> dt = DuplexTracker()
        >>> dt.get_previous_decision(1) is None
        True
        >>> dt.set_decision(1, Decision.duplex_override)
        >>> dt.get_previous_decision(1)
        <Decision.duplex_override: 'duplex_override'>
        """
        return self.previous_decision.get(channel, None)

    def set_decision(self, channel: int, decision: Decision) -> None:
        """
        Set the previous decision for a given channel number.

        :param channel: The channel number.
        :param decision: The decision taken. Should be the final decision,
        i.e we won't see the read again.
        >>> dt = DuplexTracker()
        >>> dt.set_decision(1, Decision.no_map)
        >>> dt.previous_decision[1]
        <Decision.no_map: 'no_map'>
        """
        self.previous_decision[channel] = decision

    def get_previous_alignments(self, channel: int) -> list[tuple[str, Strand]]:
        """
        Retrieves last alignments, including no maps seen on the given channel.

        :param channel: The channel number to lookup the previous action for
        :param read_id: Read of ID of the current alignment
        :return: Returns a tuple of (contig_name, strand), for the last alignment seen on this channel

        >>> dt = DuplexTracker()
        >>> dt.get_previous_alignments(1) is None
        True
        >>> dt.set_alignments(1, [("contig1", Strand.forward), ("contig2", Strand.reverse)])
        >>> dt.get_previous_alignments(1)
        [('contig1', <Strand.forward: '+'>), ('contig2', <Strand.reverse: '-'>)]
        """
        return self.previous_alignments.get(channel, None)

    def set_alignments(
        self, channel: int, alignments: list[tuple[str, Strand]]
    ) -> None:
        """
        Add an alignment that has been seen for a channel.

        :param channel: The channel number to set the alignment for.
        :param target_name: The name of the target contig aligned to
        :param strand: The strand we have aligned to.

        >>> dt = DuplexTracker()
        >>> dt.set_alignments(1, [("contig3", Strand.forward), ("contig4", Strand.reverse)])
        >>> dt.previous_alignments[1]
        [('contig3', <Strand.forward: '+'>), ('contig4', <Strand.reverse: '-'>)]
        """
        self.previous_alignments[channel] = alignments

    def possible_duplex(
        self, channel: int, target_name: str, strand: Strand | str | int
    ) -> bool:
        """
        Compare the current alignment target_name and strand for a given channel
        with the previous alignment target_name and strand.

        If the strand is opposite and the target is the same, return True, else False.
        :param channel: Channel number to fetch alignment for
        :param target_name: The name of the target contig for the current alignment
        :param strand: The strand of the current alignment
        :return: True if the strand is opposite and target contig the same

        >>> dt = DuplexTracker()
        >>> dt.set_alignments(1, [("contig5", Strand.forward)])
        >>> dt.possible_duplex(1, "contig5", Strand.reverse)
        True
        >>> dt.possible_duplex(1, "contig6", Strand.reverse)
        False
        """
        strand = Strand(strand)
        return any(
            prev_alignment == (target_name, ~strand)
            for prev_alignment in self.get_previous_alignments(channel)
        )
