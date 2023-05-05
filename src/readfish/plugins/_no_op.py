"""A no operation plugin module, used for pass through behaviour.

"""
from __future__ import annotations
from typing import Iterable

from readfish.plugins.abc import AlignerABC, CallerABC
from readfish.plugins.utils import Result


class Aligner(AlignerABC):
    def __init__(self, *args, **kwargs) -> None:
        return

    def initialised(self) -> bool:
        return True

    def map_reads(self, basecall_results: Iterable[Result]) -> Iterable[Result]:
        return basecall_results

    def disconnect(self) -> None:
        return


class Caller(CallerABC):
    def __init__(self, *args, **kwargs) -> None:
        pass

    def basecall(
        self,
        chunks: list[tuple[int, "data_pb2.GetLiveReadsResponse.ReadData"]],  # type: ignore
        *args,
        **kwargs,
    ) -> Iterable[Result]:
        """
        Basecall live data from the Read Until API.

        :param chunks: Raw data wrapper from the MinKNOW RPC
        :param signal_dtype: The NumPy :func:`numpy.dtype` for the raw signal bytes.
        :param daq_values: Mapping of channel number to it's ``CALIBRATION`` values.

        :returns: Yields ``Result`` classes with the ``Result.channel``, ``Result.read_number``, ``Result.read_id``, and ``Result.seq`` fields set.
        """
        for channel, read in chunks:
            yield Result(
                channel=channel,
                read_number=read.number,
                read_id=read.id,
                seq="",
            )

    def disconnect(self) -> None:
        return
