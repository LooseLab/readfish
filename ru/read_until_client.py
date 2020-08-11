import time
from collections import OrderedDict
from collections.abc import MutableMapping
from threading import RLock

from ru.utils import setup_logger

from minknow_api.data import get_numpy_types
from minknow_api.acquisition_pb2 import MinknowStatus
from read_until import ReadUntilClient


class RUClient(ReadUntilClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Override ONT Cache
        self.CacheType = AccumulatingReadCache
        # Override signal_dtype
        self.signal_dtype = get_numpy_types(self.connection).uncalibrated_signal

        self.unblock_logger = setup_logger("unblocks", log_file="unblocked_read_ids.txt")

        while self.connection.acquisition.current_status().status != MinknowStatus.PROCESSING:
            time.sleep(1)

        self.logger.info("Processing")

    def unblock_read(self, read_channel, read_number, duration=0.1, read_id=None):
        super().unblock_read(
            read_channel=read_channel, read_number=read_number, duration=duration,
        )
        if read_id is not None:
            self.unblock_logger.debug(read_id)

        # Log read id of unblocked read


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
