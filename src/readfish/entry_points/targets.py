"""Run a targeted sequencing experiment on a device.

When given a :doc:`TOML <toml>` experiment configuration ``readfish targets`` will:
    #. Initialise a connection to the sequencing device
    #. Load the experiment configuration
    #. Initialise a connection to the Read Until API
    #. Initialise a connection to your chosen basecaller
    #. Initialise the read aligner

Then, during sequencing the start of each read is sampled.
These chunks of raw data are processed by the basecaller to produce FASTA, which is then aligned against the chosen reference genome.
The result of the alignment is used, along with the targets provided in the :doc:`TOML <toml>` file, to make a decision on each read.


Running this should result in a very short (<1kb, ideally 400-600 bases) unblock peak at the start of a read length histogram and longer sequenced reads.

Example run command::

   readfish targets --device X3 \\
           --experiment-name "test" \\
           --toml my_exp.toml \\
           --log-file rf.log \\
           --debug-log chunks.tsv

In the debug_log chunks.tsv file, if this argument is passed, each line represents detailed information about a batch of
read signal that has been processed in an iteration.

The format of each line is as follows:
loop_counter  number_reads  read_id  channel  read_number  seq_length  seen_count
decision  action  condition  barcode  previous_action  timestamp  action_overridden

- loop_counter (int): The iteration number for the loop.
- number_reads (int): The number of reads processed in this iteration.
- read_id (str): UUID4 string representing the reads unique read_id.
- channel (int): Channel number the read is being sequenced on.
- read_number (int): The number this read is in the sequencing run as a whole.
- seq_length (int): Length of the base-called signal chunk (includes any previous chunks).
- seen_count (int): Number of times this read has been seen in previous iterations.
- decision (str): The name of the :class:`~readfish.plugins.utils.Decision` variant taken for this read, one of `single_on, single_off, multi_on, multi_off, no_map`, or `no_seq`.
- action (str): The name of the :class:`~readfish.plugins.utils.Action` variant sent to the sequencer for this read, one of `unblock, stop_receiving`, or `proceed`.
- condition (str): Name of the :class:`~readfish._config._Condition` that the read has been addressed with.
- barcode (str or None): :class: The name of the :class:`~readfish._config.Barcode` for this read if present, otherwise None.
- previous_action (str or None): Name of the last :class:`~readfish.plugins.utils.Action` taken for a read sequenced by this channel or None if this is the first read on a channel.
- timestamp (float): Current time as given by the time module in seconds.
- action_overridden (bool): Indicates if the action has been overridden. Currently actions are always overridden to be `stop_receiving`.

Actions being overridden occurs when the readfish run is a dry run and the action is unblock, or when the read is the first read seen for a channel by readfish.
This prevents trying to unblock reads of unknown length.

Example line in debug_log.tsv:

1   10   cde5271b-13c2-43af-88e1-4268ab88928e  2  15  2  5 single_on  unblock  Condition_A  None  None  1678768540.879  False


"""
# Core imports
from __future__ import annotations
import argparse
import logging
import time
from timeit import default_timer as timer
from pathlib import Path
from typing import Any

# Third party imports
import rtoml
from read_until.read_cache import AccumulatingCache
from read_until import ReadUntilClient
from minknow_api import protocol_service

# Library
from readfish._cli_args import DEVICE_BASE_ARGS
from readfish._read_until_client import RUClient
from readfish._config import Action, Conf, make_decision
from readfish._loggers import setup_debug_logger
from readfish._utils import (
    get_device,
    send_message,
    ChunkTracker,
    Severity,
)
from readfish.plugins.abc import AlignerABC, CallerABC
from readfish.plugins.utils import Decision, PreviouslySentActionTracker


_help = "Run targeted sequencing"
_cli = DEVICE_BASE_ARGS + (
    (
        "--toml",
        dict(
            metavar="TOML",
            required=True,
            help="TOML file specifying experimental parameters",
        ),
    ),
    (
        "--debug-log",
        dict(
            help="Chunk log",
            default=None,
        ),
    ),
)

# See module level docstring for an explanation of the fields in this log.
CHUNK_LOG_FIELDS = (
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
    "timestamp",
    "action_override",
)


class Analysis:
    """
    Analysis class where the read until magic happens. Comprises of one run
    function that is run threaded in the run function at the base of this file.
    Arguments listed in the __init__ docs.

    :param client: An instance of the ReadUntilClient object
    :param conf: readfish._config.Conf
    :param logger: The command level logger for this module
    :param debug_log_filename: The debug log filename for chunks. If None no chunks are logged.
    :param throttle: The number of seconds interval between requests to the ReadUntilClient, defaults to 0.1
    :param unblock_duration: Time, in seconds, to apply unblock voltage, defaults to 0.5
    :param dry_run: If True unblocks are replaced with `stop_receiving` commands, defaults to False
    :param toml: The path to the toml file containing experiment conf. Used for reloading, defaults to "a.toml"
    """

    def __init__(
        self,
        client: ReadUntilClient,
        conf: Conf,
        logger: logging.Logger,
        debug_log_filename: str | None,
        throttle: float = 0.1,
        unblock_duration: float = 0.5,
        dry_run: bool = False,
        toml: str = "a.toml",
    ):
        self.client = client
        self.conf = conf
        self.logger = logger
        self.debug_log_filename = debug_log_filename
        self.throttle = throttle
        self.unblock_duration = unblock_duration
        self.dry_run = dry_run
        self.toml = Path(f"{toml}_live").resolve()

        self.debug_log = setup_debug_logger(
            "debug_chunk_log",
            log_file=self.debug_log_filename,
            header="\t".join(CHUNK_LOG_FIELDS),
        )
        logger.info("Initialising Caller")
        self.caller: CallerABC = self.conf.caller_settings.load_object(
            "Caller", run_information=self.client.connection.protocol.get_run_info()
        )
        logger.info("Caller initialised")
        caller_description = self.caller.describe()
        self.logger.info(caller_description)
        send_message(self.client.connection, caller_description, Severity.INFO)
        logger.info("Initialising Aligner")
        self.mapper: AlignerABC = self.conf.mapper_settings.load_object("Aligner")
        self.logger.info("Aligner initialised")
        # count how often a read is seen
        self.chunk_tracker = ChunkTracker(self.client.channel_count)

        # This is an object to keep track of the last action sent to the client for each channel
        self.previous_action_tracker = PreviouslySentActionTracker()

        # Check status when we start the run.
        # We assume that sequencing is already running unless we are told otherwise.
        # It starts as True which will prevent the first
        # read seen from a channel being unblocked, overriding the action to a stop_receiving.
        # If the run is not in sequencing phase when the read until loop starts then will
        # be set to false and the first read seen may be unblocked.
        self.readfish_started_during_sequencing = True

    def run(self):
        """Run the read until loop, in one continuous while loop."""

        # TODO: Swap this for a CSV record later
        d = {"conditions": dict()}
        for idx, r in enumerate(self.conf.regions):
            g = d["conditions"].setdefault(str(idx), {})
            g["channels"] = [c for c, i in self.conf._channel_map.items() if i == idx]
            g["name"] = r.name
        channels_out = str(Path(self.client.mk_run_dir) / "channels.toml")
        with open(channels_out, "w") as fh:
            fh.write(
                "# This file is written as a record of the condition each channel is assigned.\n"
                "# It may be changed or overwritten if you restart readfish.\n"
                "# In the future this file may become a CSV file.\n"
            )
            rtoml.dump(d, fh)

        # TODO: This could still be passed through to the basecaller to prevent
        #       rebasecalling data that is already being unblocked or sequenced
        loop_counter = 0
        last_live_mtime = 0
        # IN order to prevent repeated logging in the below loop we only log each check
        # message once
        log_once_in_loop = True
        self.logger.info("Starting main loop")
        mapper_description = self.mapper.describe(self.conf.regions, self.conf.barcodes)
        self.logger.info(mapper_description)
        send_message(self.client.connection, mapper_description, Severity.INFO)

        while self.client.is_sequencing:
            t0 = timer()
            # Check of we have started readfish before PHASE_SEQUECING,
            # if so wait until we are in PHASE_SEQUENCING
            if self.client.wait_for_sequencing_to_start:
                if log_once_in_loop:
                    self.logger.info(
                        f"MinKNOW is reporting {protocol_service.ProtocolPhase.Name(self.client.current_protocol_phase)}, waiting for PHASE_SEQUENCING to begin."
                    )
                    log_once_in_loop = not log_once_in_loop
                self.readfish_started_during_sequencing = False  # We are not in sequencing phase, so we can unblock the first read we see as we will be sequencing it from the start
                time.sleep(self.throttle)
                continue
            # We've left the conditional so we want to log if we go back out of it
            log_once_in_loop = True
            if self.readfish_started_during_sequencing and loop_counter == 0:
                self.logger.info(
                    "readfish started in PHASE_SEQUENCING. Fully sequencing first read from each channel."
                )
            if not self.mapper.initialised:
                self.logger.warning(
                    "readfish main loop started but mapper is not initialised. Please check your aligners plugin documentation."
                    "If you are using mappy or mappy-rs this is definitely an error. Please open an issue here - "
                    "https://github.com/LooseLab/readfish/issues"
                )
                time.sleep(self.throttle)
                continue
            # TODO: Determine how to reload a reference and only do so if changed from previous config.
            # Specify that to load a new reference it must have a different name.
            if self.toml.is_file() and self.toml.stat().st_mtime > last_live_mtime:
                try:
                    self.conf = Conf.from_file(
                        self.toml, self.client.channel_count, self.logger
                    )
                # FIXME: Broad exception
                except Exception:
                    pass
                last_live_mtime = self.toml.stat().st_mtime

            loop_counter += 1
            number_reads = 0
            unblock_batch_action_list = []
            stop_receiving_action_list = []

            #######################################################################
            # New config
            #######################################################################
            # TODO: Filters Data flow
            #       chunks: list[tuple[channel, ReadData]]
            #       calls:  Iterable[readfish.plugins.utils.Result]
            #       maps:   Iterable[readfish.plugins.utils.Result]
            #       The filtering and partitions should be moved to the plugin module
            #       this streamlines this function, and makes them expected behaviour
            #       in the plugins that we provide, not enforced on third-party code.

            chunks = self.client.get_read_chunks(self.client.channel_count, last=True)
            calls = self.caller.basecall(
                chunks, self.client.signal_dtype, self.client.calibration_values
            )
            aligns = self.mapper.map_reads(calls)

            #######################################################################
            for result in aligns:
                number_reads += 1
                control, condition = self.conf.get_conditions(
                    result.channel, result.barcode
                )
                seen_count = self.chunk_tracker.seen(result.channel, result.read_number)
                result.decision = make_decision(self.conf, result)
                action = condition.get_action(result.decision)

                if control:
                    action = Action.stop_receiving
                else:
                    # TODO: Document the less than logic here
                    below_min_chunks = seen_count < condition.min_chunks
                    above_max_chunks = seen_count > condition.max_chunks

                    # TODO: This will also factor into the precedence and documentation
                    # If we have seen this read more than the max chunks and want to
                    #   evaluate it again (Action.proceed) then we will overrule that
                    #   action using the above_max_chunks_action, unblock by default
                    if above_max_chunks and action is Action.proceed:
                        action = condition.above_max_chunks
                        result.decision = Decision.above_max_chunks

                    # If we are below min chunks and we get an action that is not PROCEED
                    #   then we will overrule that action using the below_min_chunks_action
                    #   which by default is proceed.
                    if below_min_chunks and action is not Action.proceed:
                        action = condition.below_min_chunks
                        result.decision = Decision.below_min_chunks

                # previous_action will be None if the read has not been seen before.
                # otherwise previous_action will contain the last Action sent for a read on this channel.
                previous_action = self.previous_action_tracker.get_action(
                    result.channel
                )
                # Default is action has not been overridden
                action_overridden = False
                # Check if this is the first time a read has been seen from this channel, and we started mid sequencing run
                if previous_action is None and self.readfish_started_during_sequencing:
                    self.logger.debug(
                        f"This is the first suitable read chunk from channel {result.channel}. Translocated read length unknown, sequencing."
                    )
                    action_overridden = True
                    action = Action.stop_receiving

                if action is Action.stop_receiving:
                    stop_receiving_action_list.append(
                        (result.channel, result.read_number)
                    )
                    # We do this here so that we only update the previous read
                    # tracker with reads that have decisions made on them.
                    self.previous_action_tracker.add_action(
                        result.channel, action
                    )  # This populates the last seen tracker with the current result.
                elif action is Action.unblock:
                    if self.dry_run:
                        # We wish to log that a read would have been unblocked, so
                        # we log overriding the action, but we instead send a stop receiving.
                        # This ensures that the read is not unblocked and is not processed
                        # further but we still log that it would have been unblocked.
                        action_overridden = True
                        stop_receiving_action_list.append(
                            (result.channel, result.read_number)
                        )
                    else:
                        # We do this here so that we only update the previous read
                        # tracker with a seen and decided read.
                        unblock_batch_action_list.append(
                            (result.channel, result.read_number, result.read_id)
                        )
                    self.previous_action_tracker.add_action(
                        result.channel, action
                    )  # This populates the last seen tracker with the current result.

                self.debug_log.debug(
                    f"{loop_counter}\t"
                    f"{number_reads}\t"
                    f"{result.read_id}\t"
                    f"{result.channel}\t"
                    f"{result.read_number}\t"
                    f"{len(result.seq)}\t"
                    f"{seen_count}\t"
                    f"{result.decision.name}\t"
                    f"{action.name}\t"
                    f"{condition.name}\t"
                    f"{result.barcode}\t"
                    f"{previous_action.name if previous_action is not None else previous_action}\t"
                    f"{time.time()}\t"
                    f"{action_overridden}"
                )
            #######################################################################
            self.client.unblock_read_batch(
                unblock_batch_action_list, duration=self.unblock_duration
            )
            self.client.stop_receiving_batch(stop_receiving_action_list)

            t1 = timer()
            if number_reads > 0:
                self.logger.info(f"{number_reads}R/{t1 - t0:.5f}s")
            # limit the rate at which we make requests
            if t0 + self.throttle > t1:
                time.sleep(self.throttle + t0 - t1)
        else:
            send_message(
                self.client.connection,
                "Readfish client stopped.",
                Severity.WARN,
            )
            self.caller.disconnect()
            self.mapper.disconnect()
            self.logger.info("Finished analysis of reads as client stopped.")


def run(
    parser: argparse.ArgumentParser, args: argparse.ArgumentParser, extras: list[Any]
) -> int:
    """Run function for targets.py

    Imported in `_cli_base.py`.
    Sets up the read until client and starts the analysis thread above.

    :param parser: Argparse onject - unused but must be taken due as may be needed
    :param args: The arguments passed to ArgParse
    :param extras: Extra stuff, I guess

    :returns: An exit code integer, 0 for success
    """
    # Setup logger used in this entry point, this one should be passed through
    logger = logging.getLogger(f"readfish.{args.command}")

    # Fetch sequencing device
    position = get_device(args.device, host=args.host, port=args.port)

    # Create a read until client
    read_until_client = RUClient(
        mk_host=position.host,
        mk_port=position.description.rpc_ports.secure,
        filter_strands=True,
        cache_type=AccumulatingCache,
        timeout=args.wait_for_ready,
    )

    # Load TOML configuration
    conf = Conf.from_file(args.toml, read_until_client.channel_count, logger=logger)
    logger.info(conf.describe_experiment())

    send_message(
        read_until_client.connection,
        f"'readfish {args.command}' connected to this device.",
        Severity.WARN,
    )

    # start the client running
    read_until_client.run(
        # TODO: Set correct channel range
        # first_channel=186,
        # last_channel=187,
        first_channel=1,
        last_channel=read_until_client.channel_count,
        max_unblock_read_length_seconds=args.max_unblock_read_length_seconds,
    )

    worker = Analysis(
        read_until_client,
        conf=conf,
        logger=logger,
        debug_log_filename=args.debug_log,
        unblock_duration=args.unblock_duration,
        throttle=args.throttle,
        dry_run=args.dry_run,
        toml=args.toml,
    )

    # begin readfish function
    try:
        worker.run()
    except KeyboardInterrupt:
        pass
    finally:
        read_until_client.reset()

    send_message(
        read_until_client.connection,
        "Readfish disconnected from this device. Sequencing will proceed normally.",
        Severity.WARN,
    )
    return 0
