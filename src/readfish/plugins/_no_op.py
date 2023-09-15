"""A no operation plugin module, used for pass through behaviour.

This module implements a basic Aligner and Caller that do nothing and the minimum required behaviours respectively.
They are here for when readfish expects an action that may not be required.
For example if using a signal based alignment approach that module can replace the ``Caller`` and completely remove the extra alignment step.

To achieve this the ``_no_op.Caller`` will only iterate the raw data from the Read Until API and ``yield`` the minimal ``Result`` structs for the ``targets`` script to use:

.. code-block:: python

    Result(
        channel=<channel number>,
        read_number=<read_number>,
        read_id=<read_id>,
        seq="",
    )

The ``seq`` field will always be empty.
This is of little (essentially no) use outside of an unblock all or something completely random where you don't want or need any sequence.

In addition the ``_no_op.Aligner`` will pass through the iterable from the caller module without modifying/adding anything.
This behaviour can be useful if a plugin can complete it's entire decision in a single step.
"""
from __future__ import annotations
from typing import Iterable, TYPE_CHECKING

from readfish.plugins.abc import AlignerABC, CallerABC
from readfish.plugins.utils import Result

if TYPE_CHECKING:
    import minknow_api


class Aligner(AlignerABC):
    def __init__(self, *args, **kwargs) -> None:
        """No state is created, anything can be passed at initialisation
        it will all be ignored."""
        return

    def validate(self) -> None:
        """
        Validate the "Aligner" - will always return None, as there is no Aligner

        :return: None, always
        """
        return None

    def initialised(self) -> bool:
        """Will always return ``True``"""
        return True

    def map_reads(self, basecall_results: Iterable[Result]) -> Iterable[Result]:
        """Pass through the ``basecall_results`` iterable that is supplied."""
        return basecall_results

    def describe(self, *args, **kwargs) -> str:
        """
        Describe the no_op Aligner instance

        :return: _description_
        """
        return "Using the `no_op` Aligner. No alignments will be performed, and all Results will be passed through."

    def disconnect(self) -> None:
        """Will always return ``None``, does nothing."""
        return


class Caller(CallerABC):
    def __init__(self, *args, **kwargs) -> None:
        """No state is created, anything can be passed at initialisation
        it will all be ignored."""
        pass

    def validate(self) -> None:
        """
        Validate the "Caller" - will always return None, as there is no Caller

        :return: None, always
        """
        return None

    def basecall(
        self,
        chunks: list[tuple[int, minknow_api.data_pb2.GetLiveReadsResponse.ReadData]],
        *args,
        **kwargs,
    ) -> Iterable[Result]:
        """
        Create a minimal ``Result`` instance from live data from the Read Until API.

        This will use the actual channel, read number, and read ID but will set an empty string for the ``seq`` field.

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

    def describe(self) -> str:
        """
        Describe the `no_op` Caller.

        :return: A description string for the `no_op` Caller instance.
        """
        return "Using the `no_op` Caller. No base-calling will be performed, and minimum viable results will be yielded back for each read provided."

    def disconnect(self) -> None:
        """Will always return ``None``, does nothing."""
        return
