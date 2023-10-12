"""

This module contains the ReadfishStatistics class, which is designed to
track and manage statistics pertaining to a single Readfish run. The ReadfishStatistics
class is able to update and query various statistics and counters regarding the
performance, decisions, actions, and conditions of Readfish runs.

The ReadfishStatistics class has the ability to compute and return averages
related to chunks per second, batch time, and batch size, and it maintains
various counters to keep track of the number of chunks processed, actions taken,
decisions made, and conditions met. The class also facilitates the addition of
new performance and read records to the existing statistics.


:Example:

    >>> from readfish._statistics import ReadfishStatistics, DEBUG_STATS_LOG_FIELDS
    >>> stats = ReadfishStatistics(None)
    >>> stats.add_batch_performance(1,1)
    >>> stats.log_read(**dict(zip(DEBUG_STATS_LOG_FIELDS, (1, 2, "test_read_id", 7, 1, 100, 3,\
 "single_on", "stop_receiving", "exp_region", None, None, False, 0.0))), region_name="naff",\
 overridden_action_name=None)
    >>> print(stats.get_batch_performance())
    0001R/1.0000s; Avg: 0001R/1.0000s; Seq:1; Unb:0; Pro:0; Slow batches (>1.00s): 0/1
    >>> print(stats.decisions)
    Counter({'single_on': 1})

"""
from __future__ import annotations
from collections import Counter
import logging
import attrs
from readfish._loggers import setup_logger
from threading import RLock

DEBUG_STATS_LOG_FIELDS = (
    "client_iteration",
    "read_in_loop",
    "read_id",
    "channel",
    "read_number",
    "seq_len",
    "counter",
    "mode",
    "decision",
    "condition",
    "barcode",
    "previous_action",
    "action_override",
    "timestamp",
)


@attrs.define
class ReadfishStatistics:
    """
    A class for tracking and managing statistics for individual Readfish runs.

    The ReadfishStatistics class is designed to manage and present
    statistics from individual Readfish runs, providing insights into performance,
    decisions, actions, and conditions encountered during the runs.

    :ivar break_reads_seconds: The number of seconds between each collection of chunk signal. Default 1.0.
    :ivar log_file: The name of the log file to write to. If None, no file is output.
    :ivar total_chunks: The total number of chunks processed.
    :ivar actions: A counter tracking the number of :class:`Actions <readfish.plugins.utils.Action>` sent.
    :ivar conditions: A counter tracking the number of reads seen for each :class:`Condition <readfish._config>_Condition>`.
    :ivar actions_conditions: A counter tracking number of condition/action/decision combinations.
    :ivar decisions: A counter tracking the number of decisions made, globally.
    :ivar first_read_overrides: A counter tracking whether the first read was sequences readfish was started during sequencing or unblocked if it was not.
    :ivar batch_statistics: A counter tracking performance metrics such as summed batch times, total chunks in batches, and number of batches seen.

    Example:

    >>> stats = ReadfishStatistics(None)
    >>> stats.add_batch_performance(1, 1)
    >>> stats.log_read(**dict(zip(DEBUG_STATS_LOG_FIELDS, (1, 2, "test_read_id",\
7, 1, 100, 3, "single_on", "stop_receiving", "exp_region", None, None,\
False, 0.0))), region_name="naff", overridden_action_name=None)
    >>> print(stats.get_batch_performance())
    0001R/1.0000s; Avg: 0001R/1.0000s; Seq:1; Unb:0; Pro:0; Slow batches (>1.00s): 0/1
    >>> print(stats.decisions)
    Counter({'single_on': 1})

    Example with log file

    >>> import tempfile
    >>> import os
    >>> import time
    >>> from pprint import pformat
    >>> from readfish._statistics import ReadfishStatistics, DEBUG_STATS_LOG_FIELDS
    >>> with tempfile.TemporaryDirectory() as tmpdir:
    ...     # Change the current working directory to the temporary directory
    ...     os.chdir(tmpdir)
    ...     # Use the current directory for the log file
    ...     log_file_name = "readfish.log"
    ...     # Create an instance of ReadfishStatistics with the log file in the temporary directory
    ...     stats = ReadfishStatistics(log_file=log_file_name)
    ...     # Use the log_read method to log a sample read
    ...     stats.log_read(**dict(zip(DEBUG_STATS_LOG_FIELDS,\
(1, 2, "test_read_id", 7, 1, 100, 3, "single_on", "stop_receiving", "exp_region",\
None, None, False, 0.0))), region_name="naff", overridden_action_name=None)
    ...     # in this test, we need a small amount of time to allow the logger to write the file
    ...     time.sleep(0.1)
    ...     # Read the content of the file
    ...     with open(log_file_name, 'r') as log_file:
    ...         content = log_file.read()
    ...     # Prepare the expected content
    ...     header = " ".join(DEBUG_STATS_LOG_FIELDS)
    ...     expected_line = " ".join(map(str, (1, 2, "test_read_id", 7, 1, 100, 3, "single_on",\
"stop_receiving", "exp_region", None, None, False, 0.0)))
    ...     expected = f"{header}\\n{expected_line}"
    ...     # Check that the content matches, don't ask about the replaces, it was the only way
    ...     expected.replace("\t", " ") == content.replace("\\t", " ").strip()
    True
    """

    log_file: str | None
    break_reads_seconds: float = attrs.field(default=1.0)
    total_chunks: int = attrs.field(repr=False, default=0)
    actions: Counter = attrs.field(repr=False, factory=Counter)
    conditions: Counter = attrs.field(repr=False, factory=Counter)
    actions_conditions: Counter = attrs.field(repr=False, factory=Counter)
    decisions: Counter = attrs.field(repr=False, factory=Counter)
    first_read_overrides: Counter = attrs.field(repr=False, factory=Counter)
    batch_statistics: Counter = attrs.field(repr=False, factory=Counter)
    debug_logger: logging.Logger = attrs.field(init=False)
    _lock: RLock = attrs.field(repr=False, factory=RLock)

    def __attrs_post_init__(self):
        # NOTE if there is no log file specified this returns a NullHandler logger
        self.debug_logger = setup_logger(
            name="chunk_debug_stats",
            header="\t".join(DEBUG_STATS_LOG_FIELDS),
            log_file=self.log_file,
        )

    @property
    def average_chunks_per_second(self) -> float:
        """
        Calculate and return the average number of chunks processed per second.

        :return: Average number of chunks processed per second.

        Given:
        batch_statistics = {"batch_count": 2, "batch_size": 100, "batch_time": 50}

        >>> stats = ReadfishStatistics(None)
        >>> stats.add_batch_performance(number_of_reads=10, batch_time=5)
        >>> stats.average_chunks_per_second
        2.0

        More complex example:

        >>> stats = ReadfishStatistics(None)
        >>> stats.add_batch_performance(number_of_reads=10, batch_time=5)
        >>> stats.add_batch_performance(number_of_reads=10, batch_time=5)
        >>> stats.add_batch_performance(number_of_reads=40, batch_time=5)
        >>> stats.average_chunks_per_second
        4.0

        When batch_count is 0, the result will be 0.

        >>> stats.batch_statistics["batch_count"] = 0
        >>> stats.average_chunks_per_second
        0
        """
        with self._lock:
            if self.batch_statistics["batch_count"] == 0:
                return 0
            return (
                self.batch_statistics["cumulative_batch_size"]
                / self.batch_statistics["cumulative_batch_time"]
            )

    @property
    def average_batch_time(self) -> float:
        """
        Calculate and return the average time taken per batch.

        Examples:

        Given:
        batch_statistics = {"batch_count": 3, "cumulative_batch_size": 150, "cumulative_batch_time": 60}

        >>> stats = ReadfishStatistics(None)
        >>> stats.batch_statistics = {"batch_count": 3, "cumulative_batch_size": 150, "cumulative_batch_time": 60}
        >>> stats.average_batch_time
        20.0

        When batch_count is 0, the result should be 0.

        >>> stats.batch_statistics["batch_count"] = 0
        >>> stats.average_batch_time
        0
        """
        with self._lock:
            if self.batch_statistics["batch_count"] == 0:
                return 0
            return (
                self.batch_statistics["cumulative_batch_time"]
                / self.batch_statistics["batch_count"]
            )

    @property
    def average_batch_size(self) -> float:
        """
        Calculate and return the average size of processed batches.

        The method computes the average batch size by dividing the total number
        of chunks processed by the number of batches seen. If no batches have been
        processed, the method returns 0.

        :return: Average number of reads processed per batch.

        Example:

        >>> stats = ReadfishStatistics(None)
        >>> stats.average_batch_size
        0
        >>> stats.add_batch_performance(50, 20.0)
        >>> stats.add_batch_performance(100, 20.0)
        >>> stats.average_batch_size
        75.0
        """
        with self._lock:
            if self.batch_statistics["batch_count"] == 0:
                return 0
            return (
                self.batch_statistics["cumulative_batch_size"]
                / self.batch_statistics["batch_count"]
            )

    def get_batch_performance(self) -> str:
        """
        Generate and return a formatted string representing batch performance.

        If no batches have been processed, a placeholder message is returned.

        :return: String summary of the current performance metrics.

        Examples:

        When no batches have been processed:

        >>> stats = ReadfishStatistics(None)
        >>> stats.batch_statistics = {"batch_count": 0, "cumulative_batch_size": 0, \
            "cumulative_batch_time": 0, "batch_size": 0, "batch_time": 0}
        >>> stats.get_batch_performance()
        'No performance data yet'

        When 100 chunks is processed in 10 seconds and it has been lagging for 6 consecutive batches:

        >>> stats = ReadfishStatistics(None)
        >>> stats.batch_statistics.update({"batch_count": 6, "cumulative_batch_size": 100, \
            "cumulative_batch_time": 10, "batch_size": 10, "batch_time": 10,\
            "cumulative_lagging_batches": 6, "consecutive_lagging_batches": 6})
        >>> stats.get_batch_performance()
        '0010R/10.0000s; Avg: 0016R/1.6667s; Seq:0; Unb:0; Pro:0; Slow batches (>1.00s): 6/6'

        When three batches of total 300 chunks are processed in a total of 45 seconds:

        >>> stats = ReadfishStatistics(None)
        >>> stats.batch_statistics.update({"batch_count": 3, "cumulative_batch_size": 300, \
            "cumulative_batch_time": 45, "batch_size": 300, "batch_time": 45})
        >>> stats.get_batch_performance()
        '0300R/45.0000s; Avg: 0100R/15.0000s; Seq:0; Unb:0; Pro:0; Slow batches (>1.00s): 0/3'

        When five batches of total 500 chunks are processed in a total of 120 seconds:

        >>> stats = ReadfishStatistics(None)
        >>> stats.batch_statistics.update({"batch_count": 5, "cumulative_batch_size": 500,\
             "cumulative_batch_time": 120,  "batch_size": 500, "batch_time": 120})
        >>> stats.get_batch_performance()
        '0500R/120.0000s; Avg: 0100R/24.0000s; Seq:0; Unb:0; Pro:0; Slow batches (>1.00s): 0/5'
        """
        with self._lock:
            if self.batch_statistics["batch_count"] == 0:
                return "No performance data yet"
            return (
                f"{int(self.batch_statistics['batch_size']):0>4}R"
                f"/{self.batch_statistics['batch_time']:.4f}s; "
                f"Avg: {int(self.average_batch_size):0>4}R"
                f"/{self.average_batch_time:.4f}s; "
                f"Seq:{self.actions['stop_receiving']:,}; "
                f"Unb:{self.actions['unblock']:,}; "
                f"Pro:{self.actions['proceed']:,}; "
                f"Slow batches (>{self.break_reads_seconds:.2f}s): "
                f"{self.batch_statistics['cumulative_lagging_batches']}"
                f"/{self.batch_statistics['batch_count']}"
            )

    def add_batch_performance(self, number_of_reads: int, batch_time: float) -> None:
        """
        Update the collected statistics with new batch performance data.

        This method integrates a new set of chunk batch performance metrics into
        the class's statistics, specifically updating the batch size, batch time,
        and batch count based on the provided number of reads and the time taken.

        :param number_of_reads: The number of reads processed in the current batch.
        :param batch_time: The time taken to process the current batch in seconds.

        Example:

        >>> stats = ReadfishStatistics(None)
        >>> stats.add_batch_performance(100, 10.5)
        >>> stats.batch_statistics
        Counter({'cumulative_batch_size': 100, 'batch_size': 100, 'cumulative_batch_time':\
 10.5, 'batch_time': 10.5, 'batch_count': 1, 'cumulative_lagging_batches': 1,\
 'consecutive_lagging_batches': 1})
        >>> stats.add_batch_performance(100, 10.5)
        >>> stats.batch_statistics
        Counter({'cumulative_batch_size': 200, 'batch_size': 100, 'cumulative_batch_time':\
 21.0, 'batch_time': 10.5, 'batch_count': 2, 'cumulative_lagging_batches': 2,\
 'consecutive_lagging_batches': 2})
        """
        with self._lock:
            self.batch_statistics["cumulative_batch_size"] += number_of_reads
            self.batch_statistics["cumulative_batch_time"] += batch_time
            self.batch_statistics["batch_count"] += 1
            self.batch_statistics["batch_size"] = number_of_reads
            self.batch_statistics["batch_time"] = batch_time
            # Check for lagging batches
            if batch_time > self.break_reads_seconds:
                self.batch_statistics["cumulative_lagging_batches"] += 1
                self.batch_statistics["consecutive_lagging_batches"] += 1
            else:
                self.batch_statistics["consecutive_lagging_batches"] = 0

    def log_read(
        self, region_name: str, overridden_action_name: str | None, **kwargs
    ) -> None:
        """
        Add a new read chunk record into the collected statistics,
        and log it to the debug logger.

        The following terms are used in this function:
        decision is expected to be one of Unblock, stop_receiving etc.
        mode is expected to be one of single_on, single_off, multi_on etc.

        The term "action" is used to describe what the sequencer actually did.
        #ToDo: see and address issue #298
        :param region_name: The name of the region on the flow cell.
        :param overridden_action_name: Optional, if the originally determined action
        was overridden, the name of the NEW action.
        """

        with self._lock:
            self.total_chunks += 1
            action_overridden = kwargs.get("action_overridden")
            # Use the overridden action name for readfish stats counters
            decision_name = (
                kwargs.get("decision")
                if not action_overridden
                else overridden_action_name
            )

            # Increment total actions count, Unblock, stop_receiving etc.
            self.actions[decision_name] += 1
            # Increment total hits for this condition and condition.action.mode
            condition_name = kwargs.get("condition")
            self._update_condition_counter(
                condition_name,
                region_name,
                decision_name,
                kwargs.get("mode"),
            )
            # increment count for this decision - single_off, single_on etc.
            self.decisions[kwargs.get("mode")] += 1
            # Count if read was skipped because it was mid translocation
            first_read_key = f"{'first_read_skipped' if not kwargs.get('previous_action') and action_overridden else 'read_analysed'}"
            self.first_read_overrides[first_read_key] += 1
            # Log the read to the debug logger
            debug_log_record = "\t".join(map(str, kwargs.values()))
            self.debug_logger.debug(debug_log_record)

    def _update_condition_counter(
        self,
        condition_name: str,
        region_name: str,
        decision_name: str,
        mode_name: str,
    ) -> None:
        """
        Update the condition and action condition counters with the provided parameters.

        This private method is responsible for incrementing the condition counter.
        If the ``condition_name`` differs from the ``region_name``, this method also increments
        the condition counter for the ``region_name`` and the action condition counter with the
        corresponding ``decision_name`` and ``action_name``.


        :param condition_name: The name of the condition being updated.
        :param region_name: The name of the region related to the condition.
        :param decision_name: The name of the decision made in relation to the condition. unblock, proceed, etc..
        :param mode_name: The name of the action taken in relation to the condition. single_off, single on, etc...

        Examples:

        Condition and region being different i.e a barcoded experiment:

        >>> stats = ReadfishStatistics(None)
        >>> stats._update_condition_counter("barcode_a", "region_a", "unblock", "action_a")
        >>> stats.conditions
        Counter({'barcode_a': 1, 'region_a': 1})
        >>> stats.actions_conditions
        Counter({('region_a', 'unblock', 'action_a'): 1, ('barcode_a', 'unblock', 'action_a'): 1})

        Condition and region being the same i.e not a barcoded experiment:

        >>> stats._update_condition_counter("barcode_a", "barcode_a", "decision_b", "action_b")
        >>> stats.conditions
        Counter({'barcode_a': 2, 'region_a': 1})
        >>> stats.actions_conditions
        Counter({('region_a', 'unblock', 'action_a'): 1, ('barcode_a', 'unblock', 'action_a'): 1, ('barcode_a', 'decision_b', 'action_b'): 1})

        With action overridden:

        >>> stats._update_condition_counter("barcode_b", "region_b", "decision_c", "action_c")
        >>> stats.conditions
        Counter({'barcode_a': 2, 'region_a': 1, 'barcode_b': 1, 'region_b': 1})
        >>> stats.actions_conditions
        Counter({('region_a', 'unblock', 'action_a'): 1, ('barcode_a', 'unblock', 'action_a'): 1,\
 ('barcode_a', 'decision_b', 'action_b'): 1, ('region_b', 'decision_c', 'action_c'): 1, ('barcode_b',\
 'decision_c', 'action_c'): 1})
        """
        with self._lock:
            self.conditions[condition_name] += 1
            # We have a region for this barcoded read, increment the count for the region
            if condition_name != region_name:
                self.conditions[region_name] += 1
                self.actions_conditions[(region_name, decision_name, mode_name)] += 1
            self.actions_conditions[(condition_name, decision_name, mode_name)] += 1
