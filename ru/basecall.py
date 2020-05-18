"""basecall.py

Extension of pyguppy Caller that maintains a connection to the basecaller

"""
import logging

import mappy as mp
import numpy as np

from pyguppyclient.client import GuppyBasecallerClient
from pyguppyclient.decode import ReadData as GuppyRead


__all__ = ["GuppyCaller"]

logger = logging.getLogger("RU_basecaller")


def _create_guppy_read(reads, signal_dtype, previous_signal):
    """Convert a read from MinKNOW RPC to GuppyRead

    Parameters
    ----------
    reads : List[Tuple[int, minknow.rpc.read]]
        List of Tuple, containing (channel, read)
    signal_dtype : np.dtype
        A dtype that can be used by numpy to convert the raw data
    previous_signal : dict
        Dict containing previous signal segments

    Yields
    ------
    channel : int
    read_number : int
    GuppyRead
    """
    for read_id, channel, read_number, signal in _concat_signal(
        reads, signal_dtype, previous_signal
    ):
        read_obj = GuppyRead(signal, read_id, 0, 1)
        previous_signal[channel].append((read_id, read_obj.signal))
        yield channel, read_number, read_obj


def _concat_signal(reads, signal_dtype, previous_signal):
    for channel, read in reads:
        old_read_id, old_signal = previous_signal.get(
            channel, (("", np.empty(0, dtype=signal_dtype)),)
        )[0]

        if old_read_id == read.id:
            signal = np.concatenate(
                (old_signal, np.frombuffer(read.raw_data, dtype=signal_dtype))
            )
        else:
            signal = np.frombuffer(read.raw_data, dtype=signal_dtype)

        yield read.id, channel, read.number, signal


class GuppyCaller(GuppyBasecallerClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connect()

    def basecall_minknow(self, reads, signal_dtype, prev_signal, decided_reads):
        """Guppy basecaller wrapper for MinKNOW RPC reads

        Parameters
        ----------
        reads : iterable[Tuple[int, rpc.Read]]
            List or generator of tuples containing (channel, MinKNOW.rpc.Read)
        signal_dtype
            Numpy dtype of the raw data
        prev_signal : DefaultDict[int: collections.deque[Tuple[str, np.ndarray]]]
            Dictionary of previous signal fragment from a channel
        decided_reads : Dict[int: str]
            Dictionary of channels with the last read id a decision was made for

        Yields
        ------
        read_info : tuple
            Tuple of read info (channel, read_number)
        read_id : str
        sequence : str
        sequence_length : int
        quality : str
        """
        done = 0
        read_counter = 0

        hold = {}
        for channel, read_number, read in _create_guppy_read(
            reads, signal_dtype, prev_signal
        ):
            if read.read_id == decided_reads.get(channel, ""):
                continue

            hold[read.read_id] = (channel, read_number)
            try:
                self.pass_read(read)
            except Exception as e:
                logger.warning("Skipping read: {} due to {}".format(read.read_id, e))
                hold.pop(read.read_id)
                continue
            read_counter += 1

        while done < read_counter:
            res = self._get_called_read()

            if res is None:
                continue

            read, called = res

            yield hold.pop(
                read.read_id
            ), read.read_id, called.seq, called.seqlen, called.qual
            done += 1


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
