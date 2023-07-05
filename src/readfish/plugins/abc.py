"""Abstract Base Classes for readfish plugins

These classes define the expected structures and type information for readfish plugins.
These are expanded on in the :doc:`developers-guide`.

Validation is left to the author of any plugins that inherits from either the :class:`AlignerABC` or :class:`CallerABC`.
Things we suggest that are validated:

  - **required keys** - Keys that must be present in the TOML
  - **correctly typed values** - Values that have been passed in are correctly parsed
  - **available input files** - Check the existence of paths
  - **writable outputs** - Check permissions on output files
  - **sufficient space/RAM/resource** - Check Disk space at least
"""
from __future__ import annotations
import abc
from typing import Iterable, TYPE_CHECKING

import numpy as np
from read_until.base import CALIBRATION

from readfish._config import Conf
from readfish.plugins.utils import Result

if TYPE_CHECKING:
    import minknow_api


class AlignerABC(abc.ABC):
    """Aligner base class."""

    @abc.abstractmethod
    def __init__(self, readfish_config: Conf, debug_log: str | None, **kwargs) -> None:
        """
        :param readfish_config: Cannot be passed in using the TOML. This is for retrieving target regions.
        :param debug_log: Filename for the aligner debug log
        :param kwargs: Keyword arguments that are passed through to the Aligner
        """

    @property
    @abc.abstractmethod
    def initialised(self) -> bool:
        """Is this aligner instance initialised.

        This method should indicate whether the class is initialised and capable of aligning data.
        If it returns ``False`` readfish will be paused until it evaluates to ``True``
        """

    @abc.abstractmethod
    def map_reads(self, basecall_results: Iterable[Result]) -> Iterable[Result]:
        """Map and make a decision on an iterable of basecalled data.

        :param basecall_results: An iterable, ideally from a :term:`generator`, of ``Result`` classes

        :returns: Yields ``Result`` classes with the ``Result.decision`` field filled and, optionally, ``Result.alignment_data``
        """

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Aligner disconnection method, this will be called after readish's main loop finishes"""


class CallerABC(abc.ABC):
    """Caller base class."""

    @abc.abstractmethod
    def __init__(self, debug_log: str | None, **kwargs) -> None:
        """
        :param debug_log: Filename for the caller debug log
        :param kwargs: Keyword arguments that are passed through to the Caller
        """

    @abc.abstractmethod
    def basecall(
        self,
        chunks: list[tuple[int, minknow_api.data_pb2.GetLiveReadsResponse.ReadData]],
        signal_dtype: np.dtype,
        daq_values: dict[int, CALIBRATION],
    ) -> Iterable[Result]:
        """Basecall live data from the Read Until API.

        :param chunks: Raw data wrapper from the MinKNOW RPC
        :param signal_dtype: The NumPy :func:`numpy.dtype` for the raw signal bytes.
        :param daq_values: Mapping of channel number to it's ``CALIBRATION`` values.

        :returns: Yields ``Result`` classes with the ``Result.channel``, ``Result.read_number``, ``Result.read_id``, and ``Result.seq`` fields set.
        """

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Caller disconnection method, this will be called after readfish's main loop finishes"""
