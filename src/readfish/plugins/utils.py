from __future__ import annotations
from enum import Enum, unique
from typing import Any, Dict, List, Union, Optional, Tuple
from collections import defaultdict
from pathlib import Path
from io import StringIO
import csv
import os

import attrs

def could_be_a_path(string):
    # check if the string could be a valid path
    return os.path.isabs(string) or string.startswith('.') or string.startswith('~')    


@unique
class Decision(Enum):
    single_on = "single_on"
    single_off = "single_off"
    multi_on = "multi_on"
    multi_off = "multi_off"
    no_map = "no_map"
    no_seq = "no_seq"
    above_max_chunks = "above_max_chunks"
    below_min_chunks = "below_min_chunks"


@unique
class Action(Enum):
    unblock = "unblock"
    stop_receiving = "stop_receiving"
    proceed = "proceed"


@attrs.define
class Result:
    """Result holder

    This should be progressively filled with data from the basecaller,
    barcoder, and then the aligner.
    """

    channel: int
    read_number: int
    read_id: str
    seq: str
    decision: Decision = attrs.field(default=Decision.no_seq)
    barcode: Optional[str] = attrs.field(default=None)
    basecall_data: Optional[Any] = attrs.field(default=None)
    alignment_data: Optional[Any] = attrs.field(default=None)


@unique
class Strand(Enum):
    forward = "+"
    reverse = "-"


@attrs.define
class Targets:
    value: Union[List[str], Path] = attrs.field(default=attrs.Factory(list))
    _targets: Dict[Strand, Dict[str, List[Tuple[float, float]]]] = attrs.field(
        repr=False, alias="_targets", init=False
    )

    @classmethod
    def from_str(cls, str_: str | Path) -> Targets:
        if isinstance(str_, list):
            return cls(str_)
        elif Path(str_).is_file():
            return cls(Path(str_))
        else:
            """It is possible that the user has supplied a path that does not exist, in this case we need to raise an exception."""
            if could_be_a_path(str_):
                raise RuntimeError(f"Could not find file {str_}")
            return cls([])
        raise RuntimeError()

    def __attrs_post_init__(self):
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
        intervals: list[Tuple[float, float]]
    ) -> list[Tuple[float, float]]:
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
        """"""
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
