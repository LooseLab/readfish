"""A no operation plugin module, used for pass through behaviour.

This module implements a basic Aligner and Caller that do nothing and the 
minimum required behaviours respectively. They are here for when readfish
expects an action that may not be required; for example if using a signal
based alignment approach that module can replace the ``Caller`` and completely
remove the extra alignment step.

To achieve this the ``_no_op.Caller`` will only iterate the raw data from the 
Read Until API and ``yield`` the minimal ``Result`` structs for the ``targets`` 
script to use:

.. code-block:: python

    Result(
        channel=<channel number>,
        read_number=<read_number>,
        read_id=<read_id>,
        seq="",
    )

the ``seq`` field will always be empty. This is of little (essentially no) 
use outside of an unblock all or something completely random where you 
don't want or need any sequence.

In addition the ``_no_op.Aligner`` will pass through the iterable from the 
caller module without modifying/adding anything which is useful if a plugin
can complete it's entire decision in a single step.
"""
from __future__ import annotations
from typing import Iterable

from readfish.plugins.abc import AlignerABC, CallerABC
from readfish.plugins.utils import Result


class Aligner(AlignerABC):
    def __init__(self, *args, **kwargs) -> None:
        """No state is created, anything can be passed at initialisation
        it will all be ignored."""
        return

    def initialised(self) -> bool:
        """Will always return ``True``"""
        return True

    def map_reads(self, basecall_results: Iterable[Result]) -> Iterable[Result]:
        """Pass through the ``basecall_results`` iterable that is supplied."""
        return basecall_results

    def disconnect(self) -> None:
        """Will always return ``None``, does nothing."""
        return


class Caller(CallerABC):
    def __init__(self, *args, **kwargs) -> None:
        """No state is created, anything can be passed at initialisation
        it will all be ignored."""
        pass

    def basecall(
        self,
        chunks: list[tuple[int, "data_pb2.GetLiveReadsResponse.ReadData"]],  # type: ignore
        *args,
        **kwargs,
    ) -> Iterable[Result]:
        """
        Create a minimal ``Result`` instance from live data from the Read Until API.

        This will use the actual channel, read number, and read ID but will set an empty
        string for the ``seq`` field.

        :param chunks: Raw data wrapper from the MinKNOW RPC

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
        """Will always return ``None``, does nothing."""
        return
