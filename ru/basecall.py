"""basecall.py

Extension of pyguppy Caller that maintains a connection to the basecaller

"""
import logging
import time
from collections import namedtuple

import mappy as mp
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
            read_id = f"RU-{read.id}" #we do not modify read.id itself as this can result in persistence after this function finishes
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

            for r in results:
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

    def basecall_minknow(self, *args, **kwargs):
        """basecall data from minknow

        Parameters are identical to GuppyCaller._basecall.

                Yields
        ------
        read_info : tuple
            (channel, read_number)
        read_id : str
        sequence : str
        sequence_length : int
        quality : str
        """
        for read_info, data in self._basecall(*args, **kwargs):
            yield (
                read_info,
                data["metadata"]["read_id"],
                data["datasets"]["sequence"],
                data["metadata"]["sequence_length"],
                data["datasets"]["qstring"],
            )


class Mapper:
    def __init__(self, index):
        self.index = index
        if self.index:
            self.mapper = mp.Aligner(self.index, preset="map-ont")
            self.initialised = True
        else:
            self.mapper = None
            self.initialised = False

    def map_read(self, seq):
        return self.mapper.map(seq)

    def map_reads(self, calls):
        for read_id, seq in calls:
            yield read_id, list(self.mapper.map(seq))

    def map_reads_2(self, calls):
        """Align reads against a reference

        Parameters
        ----------
        calls : iterable [tuple,  str, str, int, str]
            An iterable of called reads from PerpetualCaller.basecall_minknow

        Yields
        ------
        read_info : tuple
            Tuple of read info (channel, read_number)
        read_id : str
        sequence : str
        sequence_length : int
        mapping_results : list
        """
        for read_info, read_id, seq, seq_len, quality in calls:
            yield read_info, read_id, seq_len, list(self.mapper.map(seq))
