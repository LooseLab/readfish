"""basecall.py

Extension of pyguppy Caller that maintains a connection to the basecaller

"""
import logging
from pathlib import Path
import time
from typing import Any, Union, Iterable
from collections import namedtuple

import mappy_rs as mp
import numpy as np

from pyguppy_client_lib.pyclient import PyGuppyClient
from pyguppy_client_lib.helper_functions import package_read

__all__ = ["GuppyCaller"]

logger = logging.getLogger("RU_basecaller")
CALIBRATION = namedtuple("calibration", "scaling offset")


class DefaultDAQValues:
    """Provides default calibration values

    Mimics the read_until_api calibration dict value from
    https://github.com/nanoporetech/read_until_api/blob/2319bbe80889a17c4b38dc9cdb45b59558232a7e/read_until/base.py#L34
    all keys return scaling=1.0 and offset=0.0
    """

    calibration = CALIBRATION(1.0, 0.0)

    def __getitem__(self, _):
        return self.calibration


class GuppyCaller(PyGuppyClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Override default priority
        self.set_params({"priority": PyGuppyClient.high_priority})
        self.connect()

    def _basecall(self, reads, signal_dtype, decided_reads, daq_values=None):
        """Guppy basecaller wrapper for MinKNOW RPC reads

        Parameters
        ----------
        reads : iterable[Tuple[int, rpc.Read]]
            List or generator of tuples containing (channel, MinKNOW.rpc.Read)
        signal_dtype
            Numpy dtype of the raw data
        decided_reads : Dict[int: str]
            Dictionary of channels with the last read id a decision was made for
        daq_values : Dict[int: namedtuple]
            Dictionary of channels with namedtuples containing offset and scaling.
            If not provided default values of 1.0 and 0.0 are used

        Yields
        ------
        read_info : tuple
            Tuple of read info (channel, read_number)
        data : dict
            Dict of data returned from guppy server
        sequence : str
        sequence_length : int
        quality : str
        """
        hold = {}
        # FixMe: This is resolved in later versions of guppy.
        skipped = {}
        done = 0
        read_counter = 0

        if daq_values is None:
            daq_values = DefaultDAQValues()

        for channel, read in reads:
            read_id = f"RU-{read.id}"  # we do not modify read.id itself as this can result in persistence after this function finishes
            hold[read_id] = (channel, read.number)
            t0 = time.time()
            success = self.pass_read(
                package_read(
                    read_id=read_id,
                    raw_data=np.frombuffer(read.raw_data, signal_dtype),
                    daq_offset=daq_values[channel].offset,
                    daq_scaling=daq_values[channel].scaling,
                )
            )
            if not success:
                logging.warning("Skipped a read: {}".format(read_id))
                # FixMe: This is resolved in later versions of guppy.
                skipped[read_id] = hold.pop(read_id)
                continue
            else:
                read_counter += 1

            sleep_time = self.throttle - t0
            if sleep_time > 0:
                time.sleep(sleep_time)

        while done < read_counter:
            results = self.get_completed_reads()

            if not results:
                time.sleep(self.throttle)
                continue

            for r_ in results:
                for r in r_:
                    r_id = r["metadata"]["read_id"]
                    try:
                        i = hold.pop(r_id)
                    except KeyError:
                        # FixMe: This is resolved in later versions of guppy.
                        i = skipped.pop(r_id)
                        read_counter += 1
                    r["metadata"]["read_id"] = r_id[3:]
                    yield i, r
                    done += 1

    def get_all_data(self, *args, **kwargs):
        """basecall data from minknow

        Parameters are identical to GuppyCaller._basecall.

                Yields
        ------
        read_info : tuple
            (channel, read_number)
        data : dict
                        All data returned from guppy server, this will contain different
                        attributes depending on the client connection parameters
        """
        yield from self._basecall(*args, **kwargs)


class MappyRSMapper:
    """
    Thin wrapper around mappy_rs aligner. 
    
    Parameters
    ----------
    index: str or Path
        Path to the index file to be loaded into the mapper. Can be either FASTA or minimap2 index type files.
    n_threads: int
        The number of alignment threads to be given to the mapper. Default 6, cannot be 0.
    """
    def __init__(self, index, n_threads = 6) -> None:
        self.index = index
        self.n_threads = n_threads
        if self.index:
            self.mapper = mp.Aligner(self.n_threads, self.index)
            self.initialised = True
        else:
            self.mapper = None
            self.initialised = False

    def map_batch(self, iterable):
        """
        Consume an iterable sending it to mappy_rs aligner queue. 
        Then calls a mapping function, yielding all mappings from the queue

        Parameters
        ----------
        iterable: Iterable[tuple[tuple[int, int], dict[Any]]]
            An iterable of tuples. The first element is a tuple of (channel_number, read_number), second is a data dictionary returned from Guppy.

        Yields
        ------
        tuple[metdata: (channel_num, read_num), data: dict[Any], list[AlignmentResults]]
            Yields a tuple of a tuple of (channel_num, read_num), a dict of the data returned from guppy, and a list of mapping results from mappy rs 


        """
        cache = {}
        for cache_id, data in iterable:
            cache[cache_id] = data
            res = self.mapper.send_one(
                (cache_id, data.get("datasets", {}).get("sequence", "A"))
            )
            if res == mp.Status.Bad:
                logger.warning("Bad mapping status encountered...")

        for res in self.mapper.get_all_alignments():
            metadata = res.metadata.to_tuple()
            data = cache.pop(metadata)
            yield metadata, data, list(res)
