"""basecall.py

Extension of pyguppy Caller that maintains a connection to the basecaller

"""
import logging
import os
from time import sleep

import mappy as mp
import numpy as np

# import deepnano2
from pyguppyclient.client import GuppyBasecallerClient as GuppyClient
from pyguppyclient.decode import ReadData as GuppyRead

__all__ = ["GPU", "CPU"]

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
    for read_id, channel, read_number, signal in _concat_signal(reads, signal_dtype, previous_signal):
        read_obj = GuppyRead(signal, read_id, 0, 1)
        previous_signal[channel].append((read_id, read_obj.signal))

        # # A little bit of a hack, but works with the deque
        # #  really should just replace tuples in the dict but :shrug:
        # #  or even have len of 2 on the deque ?
        # old_read_id, old_signal = previous_signal.get(channel, (("", np.empty(0, dtype=signal_dtype)),))[0]
        # if old_read_id == read.id:
        #     signal = np.concatenate((old_signal, np.frombuffer(read.raw_data, dtype=signal_dtype)))
        # else:
        #     signal = np.frombuffer(read.raw_data, dtype=signal_dtype)

        # read_obj.raw_read = signal
        # read_obj.daq_scaling = 1
        # read_obj.daq_offset = 0
        # read_obj.total_samples = len(read_obj.raw_read)
        yield channel, read_number, read_obj


def _concat_signal(reads, signal_dtype, previous_signal):
    for channel, read in reads:
        old_read_id, old_signal = previous_signal.get(channel, (("", np.empty(0, dtype=signal_dtype)),))[0]

        if old_read_id == read.id:
            signal = np.concatenate((old_signal, np.frombuffer(read.raw_data, dtype=signal_dtype)))
        else:
            signal = np.frombuffer(read.raw_data, dtype=signal_dtype)

        yield read.id, channel, read.number, signal


def _rescale_signal(signal):
    """Rescale signal for DeepNano"""
    signal = signal.astype(np.float32)
    med, mad = _med_mad(signal)
    signal -= med
    signal /= mad
    return signal


def _med_mad(x, factor=1.4826):
    """Calculate signal median and median absolute deviation"""
    med = np.median(x)
    mad = np.median(np.absolute(x - med)) * factor
    return med, mad


class _Caller:
    def basecall_minknow(self, *args, **kwargs):
        """Raise NotImplemented"""
        raise NotImplementedError("basecall_minknow needs to be overwritten")

    def disconnect(self):
        """Fallback disconnect"""
        pass


class CPU(_Caller):
    def __init__(self, **kwargs):
        import deepnano2
        network_type = "48"
        beam_size = 5
        beam_cut_threshold = 0.01
        weights = os.path.join(deepnano2.__path__[0], "weights", "rnn%s.txt" % network_type)
        self.caller = deepnano2.Caller(network_type, weights, beam_size, beam_cut_threshold)
        logger.info("CPU Caller Up")

    def basecall_minknow(self, reads, signal_dtype, prev_signal, decided_reads):
        hold = {}
        for read_id, channel, read_number, signal in _concat_signal(reads, signal_dtype, prev_signal):
            if read_id == decided_reads.get(channel, ""):
                continue

            signal = _rescale_signal(signal)

            hold[read_id] = (channel, read_number)
            seq = self.caller.call_raw_signal(signal)
            yield hold.pop(read_id), read_id, seq, len(seq), ""


class GPU(_Caller):
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
        # load_config(config, host, port)
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
        for channel, read_number, read in _create_guppy_read(reads, signal_dtype, prev_signal):
            if read.read_id == decided_reads.get(channel, ""):
                continue

            # while not self.client.can_accept_read():
            #     sleep(self.snooze)

            hold[read.read_id] = (channel, read_number)
            self.client.pass_read(read)
            read_counter += 1

        while done < read_counter:
            """
            res = self.client._get_called)_read() 
            # res is a tuple, (read, called)
            # called is the CalledReadData object
            """
            res = self.client._get_called_read()

            if res is not None:
                sleep(self.snooze)
                continue

            read, called = res
            # print(read, type(read), dir(read))
            # print(called, type(called), dir(called))
            yield hold.pop(read.read_id), read.read_id, called.seq, called.seqlen, called.qual
            #     done +=1
            #
            # for completed in range(completed_reads):
            #     try:
            #         read, meta, data = self.client._get_called_read()
            #         done += 1
            #         yield hold.pop(read.read_id), read.read_id, data.seq, len(data.seq), data.qual
            #     except TypeError:
            #         pass


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
