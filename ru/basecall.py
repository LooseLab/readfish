"""basecall.py

Extension of pyguppy Caller that maintains a connection to the basecaller

"""
from time import sleep

import mappy as mp
import numpy as np
import logging

import deepnano2
import os

from pyguppy.io import GuppyRead
from pyguppy.client import GuppyClient, load_config


logger = logging.getLogger("RU_basecaller")


def _parse_minknow_read(reads, signal_dtype, previous_signal):
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
    for channel, read in reads:
        read_obj = GuppyRead(read.id)

        # A little bit of a hack, but works with the deque
        #  really should just replace tuples in the dict but :shrug:
        #  or even have len of 2 on the deque ?
        old_read_id, old_signal = previous_signal.get(channel, (("", np.empty(0, dtype=signal_dtype)),))[0]
        if old_read_id == read.id:
            signal = np.concatenate((old_signal, np.frombuffer(read.raw_data, dtype=signal_dtype)))
        else:
            signal = np.frombuffer(read.raw_data, dtype=signal_dtype)

        read_obj.raw_read = signal

        previous_signal[channel].append((read.id, read_obj.raw_read))

        read_obj.daq_scaling = 1
        read_obj.daq_offset = 0
        read_obj.total_samples = len(read_obj.raw_read)
        yield channel, read.number, read_obj

def med_mad(x, factor=1.4826):
    """
    Calculate signal median and median absolute deviation
    """
    med = np.median(x)
    mad = np.median(np.absolute(x - med)) * factor
    return med, mad

def rescale_signal(signal):
    signal = signal.astype(np.float32)
    med, mad = med_mad(signal)
    signal -= med
    signal /= mad
    return signal


class CPUPerpetualCaller:
    def __init__(
            self,
            config,
            host=None,
            port=None,
            snooze=None,
            inflight=None,
            procs=1
    ):
        network_type = "96"
        beam_size = 20
        beam_cut_threshold = 0.01
        weights = os.path.join(deepnano2.__path__[0], "weights", "rnn%s.txt" % network_type)
        self.caller = deepnano2.Caller(network_type, weights, beam_size, beam_cut_threshold)
        logging.info("CPU Caller Up")

    def basecall_minknow(self, reads, signal_dtype, prev_signal, decided_reads):
        hold = {}
        for channel, read_number, read in _parse_minknow_read(reads, signal_dtype, prev_signal):
            if read.read_id == decided_reads.get(channel, ""):
                continue

            #if len(read.raw_read) > 16000:
            #    continue

            signal = rescale_signal(read.raw_read)

            hold[read.read_id] = (channel, read_number)
            sequence = self.caller.call_raw_signal(signal)
            lenseq = len(sequence)
            yield hold.pop(read.read_id), read.read_id, sequence, lenseq, ""

class PerpetualCaller:
    def __init__(
            self,
            config,
            host='127.0.0.1',
            port=5555,
            snooze=1e-4,
            inflight=512,
            procs=4,
    ):
        self.host = host
        self.port = port
        self.procs = procs
        self.config = config
        self.snooze = snooze
        self.inflight = inflight
        load_config(config, host, port)
        self.client = GuppyClient(self.config, host=self.host, port=self.port)
        self.client.connect()

    def disconnect(self):
        self.client.disconnect()

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
        for channel, read_number, read in _parse_minknow_read(reads, signal_dtype, prev_signal):
            if read.read_id == decided_reads.get(channel, ""):
                continue

            while not self.client.can_accept_read():
                sleep(self.snooze)

            hold[read.read_id] = (channel, read_number)
            self.client.pass_read(read)
            read_counter += 1

        while done < read_counter:
            completed_reads = self.client.num_reads_done()

            if not completed_reads:
                sleep(self.snooze)
                continue

            for completed in range(completed_reads):
                try:
                    read, meta, data = self.client.get_called_read(events=False)
                    done += 1
                    yield hold.pop(read.read_id), read.read_id, data.seq, meta.seqlen, data.qual
                except TypeError:
                    pass

    def basecall_read_until(self, reads):
        """

        Parameters
        ----------
        reads : iterable
            Iterable of GuppyRead objects

        Returns
        -------
        List
            List of Tuple, (read_id, read_seq)
        """
        done = 0
        basecalls = []

        read_counter = 0
        for read in reads:
            # Sleep if client cannot accept reads
            while not self.client.can_accept_read():
                sleep(self.snooze)

            self.client.pass_read(read)
            read_counter += 1

        while done < read_counter:
            completed_reads = self.client.num_reads_done()

            if not completed_reads:
                sleep(self.snooze)
                continue
            # logger.info("completed_reads: {}".format(completed_reads))
            for completed in range(completed_reads):
                try:
                    read, meta, data = self.client.get_called_read(events=False)
                    basecalls.append((read.read_id, data.seq))
                    done += 1
                except Exception as e:
                    # TODO: Specify what exception are we expecting here
                    logger.debug("PerpetualCaller got exception: {}".format(e))
                    pass

        return basecalls


class Mapper:
    def __init__(self, index):
        self.mapper = mp.Aligner(index, preset='map-ont')

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
