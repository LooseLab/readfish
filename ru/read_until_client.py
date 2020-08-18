import logging
import queue
import time
from collections import OrderedDict
from collections.abc import MutableMapping
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from threading import RLock

from minknow_api.acquisition_pb2 import MinknowStatus
from minknow_api.data import get_numpy_types
from read_until import ReadUntilClient


class RUClient(ReadUntilClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger.disabled = True

        # We always want one_chunk to be False
        self.one_chunk = False

        # Override signal_dtype
        self.signal_dtype = get_numpy_types(self.connection).uncalibrated_signal

        self.mk_run_dir = self.connection.protocol.get_current_protocol_run().output_path
        if self.mk_host not in ("localhost", "127.0.0.1"):
            # running remotely, output in cwd
            self.mk_run_dir = "."

        Path(self.mk_run_dir).mkdir(parents=True, exist_ok=True)

        self.log_queue = queue.Queue(-1)
        self.queue_handler = QueueHandler(self.log_queue)
        self.unblock_logger = logging.getLogger("unblocks")
        self.unblock_logger.setLevel(logging.DEBUG)
        self.unblock_logger.propagate = False
        self.unblock_logger.addHandler(self.queue_handler)
        fmt = logging.Formatter("%(message)s")
        self.file_handler = logging.FileHandler(
            str(Path(self.mk_run_dir).joinpath("unblocked_read_ids.txt"))
        )
        self.file_handler.setFormatter(fmt)
        self.listener = QueueListener(self.log_queue, self.file_handler)
        self.listener.start()

        while self.connection.acquisition.current_status().status != MinknowStatus.PROCESSING:
            time.sleep(1)

    def _runner(
        self,
        first_channel=1,
        last_channel=512,
        min_chunk_size=0,
        action_batch=1000,
        action_throttle=0.001,
    ):
        """Yield the stream initializer request followed by action requests
        placed into the action_queue.
        :param first_channel: lowest channel for which to receive raw data.
        :param last_channel: highest channel (inclusive) for which to receive data.
        :param min_chunk_size: minimum number of raw samples in a raw data chunk.
        :param action_batch: maximum number of actions to batch in a single response.
        """
        self.logger.info(
            "Sending init command, channels:{}-{}, min_chunk:{}".format(
                first_channel, last_channel, min_chunk_size
            )
        )
        yield self.msgs.GetLiveReadsRequest(
            setup=self.msgs.GetLiveReadsRequest.StreamSetup(
                first_channel=first_channel,
                last_channel=last_channel,
                raw_data_type=self.msgs.GetLiveReadsRequest.UNCALIBRATED,
                sample_minimum_chunk_size=min_chunk_size,
            )
        )

        t0 = time.time()
        while self.is_running:
            t0 = time.time()
            # get as many items as we can up to the maximum, without blocking
            actions = list()
            for _ in range(action_batch):
                try:
                    action = self.action_queue.get_nowait()
                except queue.Empty:
                    break
                else:
                    actions.append(action)

            n_actions = len(actions)
            if n_actions > 0:
                self.logger.debug("Sending {} actions.".format(n_actions))
                action_group = self.msgs.GetLiveReadsRequest(
                    actions=self.msgs.GetLiveReadsRequest.Actions(actions=actions)
                )
                yield action_group

            # limit response interval
            t1 = time.time()
            if t0 + action_throttle > t1:
                time.sleep(action_throttle + t0 - t1)
        else:
            self.logger.info("Reset signal received by action handler.")

    def unblock_read(self, read_channel, read_number, duration=0.1, read_id=None):
        super().unblock_read(
            read_channel=read_channel, read_number=read_number, duration=duration,
        )
        if read_id is not None:
            self.unblock_logger.debug(read_id)


class AccumulatingReadCache(MutableMapping):
    """A thread-safe dict-like container with a maximum size

    This ReadCache contains all the required methods for working as an ordered
    cache with a max size.

    When implementing a ReadCache, this can be subclassed and a __setitem__
    overridden, see examples.

    :ivar size: The maximum size of the ReadCache
    :vartype size: int
    :ivar missed: The number of items deleted from the cache (read chunks replaced
        by a chunk from a different read)
    :vartype missed: int
    :ivar replaced: The number of items replaced by a newer item (read chunks
        replaced by a chunk from the same read)
    :vartype replaced: int
    :ivar _dict: An instance of an OrderedDict that forms the read cache
    :vartype _dict: collections.OrderedDict
    :ivar lock: The instance of the lock used to make the cache thread-safe
    :vartype lock: threading.Rlock

    :Example:

    When inheriting from ReadCache only the ``__setitem__`` method needs to be
    overridden. The attribute `self._dict` is an instance of OrderedDict that
    forms the cache so this is the object that must be updated.

    >>> class DerivedCache(ReadCache):
    ...     def __setitem__(self, key, value):
    ...         # The lock is required to maintain thread-safety
    ...         with self.lock:
    ...             # Logic to apply when adding items to the cache
    ...             self._dict[key] = value

    .. note:: This example is not likely to be a good cache.

    .. note:: When a method "Delegates with lock." it is calling the same
        method on the ``_dict`` attribute.

    A thread-safe dict-like container with a maximum size

    This cache has an identical interface to ReadCache, however
    it accumulates raw_data chunks that belong to the same read
    and concatenates them until a new read is received. The only
    attribute of the ``ReadData`` object that is updated is the
    ``raw_data`` field

    .. warning::
    For compatibility with the ReadUntilClient, the attributes
    `missed` and `replaced` are used here. However, `replaced`
    is incremented whenever a new chunk is appended to a read
    currently in the cache. `missed` is incremented whenever a
    read is replaced with a new read, not seen in the cache.

    .. warning::
    To prevent reads from being ejected from this cache the
    size should be set to the same as the maximum number of
    channels on the sequencing device. e.g. 512 on MinION.
    """

    def __init__(self, size):
        """Initialise ReadCache

        :param size: The maximum size of the ReadCache, defaults to 100
        :type size: int, optional
        """
        if size < 1:
            raise ValueError("'size' must be >1.")
        self.size = size
        self._dict = OrderedDict()
        self.lock = RLock()
        self.missed = 0
        self.replaced = 0
        # ``self._keys`` is an lookup dictionary. It is used to track reads
        #   that have been updated.
        self._keys = OrderedDict()

    def __getitem__(self, key):
        """Delegate with lock."""
        with self.lock:
            return self._dict[key]

    def __delitem__(self, key):
        """Delegate with lock."""
        with self.lock:
            del self._keys[key]
            del self._dict[key]

    def __len__(self):
        """Delegate with lock."""
        with self.lock:
            return len(self._keys)

    def __iter__(self):
        """Delegate with lock."""
        with self.lock:
            yield from self._keys.__iter__()

    def keys(self):
        """Delegate with lock."""
        with self.lock:
            return self._keys.keys()

    def __setitem__(self, key, value):
        """Cache that accumulates read chunks as they are received

        :param key: Channel number for the read chunk
        :type key: int
        :param value: Live read data object from MinKNOW rpc. Requires
            attributes `number` and `raw_data`.
        :type value: minknow_api.data_pb2.GetLiveReadsResponse.ReadData

        :returns: None

        .. notes:: In this implementation attribute `replaced` counts reads where
            the `raw_data` is accumulated, not replaced.
        """
        with self.lock:
            if key not in self:
                # Key not in _dict
                self._dict[key] = value
            else:
                # Key exists
                if self[key].number == value.number:
                    # Same read, update raw_data
                    self[key].raw_data += value.raw_data
                    self.replaced += 1
                else:
                    # New read
                    self._dict[key] = value
                    self.missed += 1

            # Mark this channel as updated
            self._keys[key] = True

            if len(self) > self.size:
                self.popitem(last=False)

    def popitem(self, last=True):
        """Remove and return a (key, value) pair from the cache

        :param last: If True remove in LIFO order, if False remove in FIFO order
        :type last: bool

        :returns: key, value pair of (channel, ReadData)
        :rtype: tuple
        """
        ch, _ = self._keys.popitem(last=last)
        return ch, self._dict.pop(ch)

    def popitems(self, items=1, last=True):
        """Return a list of popped items from the cache.

        :param items: Maximum number of items to return
        :type items: int
        :param last: If True, return the newest entry (LIFO); else the oldest (FIFO).
        :type last: bool

        :returns: Output list of upto `items` (key, value) pairs from the cache
        :rtype: list
        """
        if items > self.size:
            items = self.size

        with self.lock:
            data = []
            if items >= len(self._keys):
                if last:
                    data = [(ch, self._dict[ch]) for ch in reversed(self._keys.keys())]
                else:
                    data = [(ch, self._dict[ch]) for ch in self._keys.keys()]
                self._keys.clear()
                return data

            while self._keys and len(data) != items:
                ch, _ = self._keys.popitem(last=last)
                data.append((ch, self._dict[ch]))

            return data
