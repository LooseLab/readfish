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

In the new **experimental** Duplex mode, it is possible to override a decision for a read based on the action taken for a previous read.
This is done by passing `--chemistry` and setting either duplex, or duplex simple.
`duplex_simple` accepts a read if the previous channels read was stop receiving, `duplex` checks that the previous reads alignment was on the same contig and opposite strand.
The default chemistry is simplex.

Running this should result in a very short (<1kb, ideally 400-600 bases) unblock peak at the start of a read length histogram and longer sequenced reads.

Example run command::

   readfish targets --device X3 \\
           --experiment-name "test" \\
           --toml my_exp.toml \\
           --log-file rf.log \\
           --debug-log chunks.tsv

Example experimental duplex command::

    readfish targets --device X3 \\
           --experiment-name "test" \\
           --toml my_exp.toml \\
           --log-file rf.log \\
           --debug-log chunks.tsv
           --chemistry duplex

In the debug_log chunks.tsv file, if this argument is passed, each line represents detailed information about a batch of
read signal that has been processed in an iteration.

The format of each line is as follows:
loop_counter  number_reads  read_id  channel  read_number  seq_length  seen_count
decision  action  condition  barcode  previous_action  timestamp  action_overridden

+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| Parameter         | Type        | Description                                                                                                   |
+===================+=============+===============================================================================================================+
| loop_counter      | int         | The iteration number for the loop.                                                                            |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| number_reads      | int         | The number of reads processed in this iteration.                                                              |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| read_id           | str         | UUID4 string representing the reads unique read_id.                                                           |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| channel           | int         | Channel number the read is being sequenced on.                                                                |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| read_number       | int         | The number this read is in the sequencing run as a whole.                                                     |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| seq_length        | int         | Length of the base-called signal chunk (includes any previous chunks).                                        |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| seen_count        | int         | Number of times this read has been seen in previous iterations.                                               |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| decision          | str         | The name of the Decision variant taken for this read, see :ref:`regions-sub-tables` for values.               |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| action            | str         | The name of the Action variant sent to the sequencer for this read, see :ref:`regions-sub-tables` for values. |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| condition         | str         | Name of the Condition that the read has been addressed with.                                                  |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| barcode           | str or None | The name of the Barcode for this read if present, otherwise None.                                             |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| previous_action   | str or None | Name of the last Action taken for a read sequenced by this channel or None if first read on a chann           |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| action_overridden | bool        | Indicates if the action has been overridden. Currently, actions are always overridden to be `stop_receiving`. |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+
| timestamp         | float       | Current time as given by the time module in seconds.                                                          |
+-------------------+-------------+---------------------------------------------------------------------------------------------------------------+

Actions being overridden occurs when the readfish run is a dry run and the action is unblock, or when the read is the first read seen for a channel by readfish.
This prevents trying to unblock reads of unknown length.


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
from readfish.read_until.read_cache import AccumulatingCache
from readfish.read_until import ReadUntilClient
from minknow_api import protocol_service

# Library
from readfish._cli_args import DEVICE_BASE_ARGS, Chemistry
from readfish._read_until_client import RUClient
from readfish._config import Action, Conf, make_decision, _Condition
from readfish._statistics import ReadfishStatistics
from readfish._utils import (
    get_device,
    send_message,
    ChunkTracker,
    Severity,
)
from readfish.plugins.abc import AlignerABC, CallerABC
from readfish.plugins.utils import (
    Decision,
    PreviouslySentActionTracker,
    Result,
    DuplexTracker,
    Strand,
)


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
        "--no-debug-log",
        dict(
            help="Disable debug output of information about chunks seen into a .tsv formatted log. Default enabled.",
            action="store_false",
            dest="debug_log",
        ),
    ),
    (
        "--padding",
        dict(
            help="Number of bases to pad the target sequences with",
            default=0,
            type=int,
            metavar="PADDING",
        ),
    ),
)
# When sequencing in duplex mode, overriding a decided `Action` on a currently sequenced molecule
# is not allowed if the previous molecules decision was one of these.
DISALLOWED_DUPLEX_DECISIONS = {Decision.first_read_override, Decision.duplex_override}


class Analysis:
    """
    Analysis class where the read until magic happens. Comprises of one run
    function that is run threaded in the run function at the base of this file.
    Arguments listed in the __init__ docs.

    :param client: An instance of the ReadUntilClient object.
    :param conf: An instance of the Conf object.
    :param logger: The command level logger for this module.
    :param debug_log: Whether to output the Debug Log. log Name is generated.
    :param throttle: The time interval (seconds) between requests to the ReadUntilClient.
    :param unblock_duration: Time, in seconds, to apply unblock voltage.
    :param dry_run: If True unblocks are replaced with `stop_receiving` commands.
    :param toml: The path to the toml file containing experiment conf. Used as the path for checking if the TOML needs reloading.
    :param chemistry: Instance of Chemistry Enum, representing the chemistry of the run (Simplex/Duplex). Used for
        decision making on strands that may be part of a duplex pair.
    """

    def __init__(
        self,
        client: ReadUntilClient,
        conf: Conf,
        logger: logging.Logger,
        debug_log: bool,
        throttle: float,
        unblock_duration: float,
        dry_run: bool,
        toml: str,
        chemistry: Chemistry,
    ):
        self.client = client
        self.conf = conf
        self.logger = logger
        self.debug_log = debug_log
        self.throttle = throttle
        self.unblock_duration = unblock_duration
        self.dry_run = dry_run
        self.live_toml = Path(f"{toml}_live").resolve()
        self.run_information = self.client.connection.protocol.get_run_info()
        self.chemistry = chemistry
        # Generate a run specific read log
        read_log_name = (
            f"{self.run_information.run_id}_readfish.tsv" if debug_log else None
        )

        self.logger.info("Fetching Run Configuration")
        self.break_reads_after_seconds = (
            self.client.connection.analysis_configuration.get_analysis_configuration().read_detection.break_reads_after_seconds.value
        )
        self.logger.info("Run Configuration Received")
        self.logger.info(f"run_id={self.run_information.run_id}")
        self.logger.info(f"break_reads_after_seconds={self.break_reads_after_seconds}")
        # Create our statistics tracker
        self.loop_statistics = ReadfishStatistics(
            read_log_name, self.break_reads_after_seconds
        )
        logger.info("Initialising Caller")
        self.caller: CallerABC = self.conf.caller_settings.load_object(
            "Caller", run_information=self.run_information
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
        # Keep track of previous alignments
        self.duplex_tracker = DuplexTracker()

        # We assume that sequencing is already running.
        # If the run is not in sequencing phase when the read until loop starts will
        # be set to false and the first read seen can be unblocked.
        self.readfish_started_during_sequencing = True

        # This is a flag to prevent repeated logging of the same message
        self.log_once_in_loop = True

    @property
    def wait_for_sequencing(self) -> bool:
        """
        Wait for minKNOW to report PHASE_SEQUENCING before starting readfish tight loop.
        The check occurs in out RUClient wrapper.

        :return: True if we are waiting for PHASE_SEQUENCING, False otherwise

        """
        if self.client.wait_for_sequencing_to_start:
            if self.log_once_in_loop:
                self.logger.info(
                    f"MinKNOW is reporting {protocol_service.ProtocolPhase.Name(self.client.current_protocol_phase)}, waiting for PHASE_SEQUENCING to begin."
                )
                self.log_once_in_loop = not self.log_once_in_loop
            self.readfish_started_during_sequencing = False  # We are not in sequencing phase, so we can unblock the first read we see as we will be sequencing it from the start
            return True
        return False

    def reload_toml(self, last_toml_mtime: float) -> float:
        """
        Reload the toml to refresh the conf with any updates.
        Reloading is determined by checking the modified time of the toml file.
        If it is more recent, reload the conf.

        :param last_live_mtime: The last modified time for the toml file.

        :return: The last modified time for the toml file, updated if changed.
        """
        if (
            self.live_toml.is_file()
            and self.live_toml.stat().st_mtime > last_toml_mtime
        ):
            try:
                self.conf = Conf.from_file(
                    self.live_toml, self.client.channel_count, self.logger
                )
            # FIXME: Broad exception
            except Exception:
                pass
            last_toml_mtime = self.live_toml.stat().st_mtime
        return last_toml_mtime

    def check_override_action(
        self,
        control: bool,
        action: Action,
        result: Result,
        seen_count: int,
        condition: _Condition,
        stop_receiving_action_list: list[tuple[int, int]],
        unblock_batch_action_list: list[tuple[int, int]],
    ) -> tuple[Action, bool, str | None]:
        """
        Check the chosen Action and amend it based on conditional checks.
        The action lists are appended to in place, so no return is required.

        Checks include:
            1. If the read is in a control region, the action is always stop_receiving.
            1. If the read is below the minimum chunks, use value in toml or default to proceed
            1. If the read is above the maximum chunks, use value in toml or default unblock--throttle
            1. First read seen for channel and readfish started during sequencing, override to stop_receiving
            1. If action is unblock and we are dry-running, override to stop_receiving
            1. If we are running in duplex chemistry, check the previous reads final decision and Action, and potentially sequence
                the current read, instead of unblocking it.

        :param control: Indicates read from a channel in a control region
        :param action: What action was decided for this read before any meddling
        :param result: Information about the current read.
        :param seen_count: Number of times other chunks from the read have been observed.
        :param condition: The set of conditions for deciding the action.
        :param stop_receiving_action_list: List to append channels and read numbers for which 'stop receiving' action is decided.
        :param unblock_batch_action_list: List to append channels, read numbers, and read IDs for which 'unblock' action is decided.

        :return: A tuple containing the previous action taken for this read,
          boolean indicating if the action was overridden, and the name of the action overridden too.

        """

        # Easy dub
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
        previous_action = self.previous_action_tracker.get_action(result.channel)
        action_overridden = False
        # If --duplex flag override decisions made based on the strand and contig alignment of the previous read.
        # Unfinished bruv
        if (
            self.chemistry is Chemistry.DUPLEX
            # Easy checks first, so wdon't do more complex processing unless we have to
            and action == Action.unblock
            and previous_action is Action.stop_receiving
        ):
            # Check if we think this read is possibly duplex
            possible_duplex = any(
                self.duplex_tracker.possible_duplex(
                    result.channel, result.read_id, al.ctg, al.strand
                )
                for al in result.alignment_data
            )
            # Check the previous decision for this channel was not already an override
            previous_decision_allowed = (
                self.duplex_tracker.get_previous_decision(result.channel)
                not in DISALLOWED_DUPLEX_DECISIONS
            )
            if possible_duplex and previous_decision_allowed:
                self.logger.debug(
                    f"Overriding read {result.read_id} as it is possibly second half of a duplex"
                    f"- previous read action {previous_action}, current_action: {action},"
                    f" previous_decision: {self.duplex_tracker.get_previous_decision(result.channel)}"
                )
                action_overridden = True
                result.decision = Decision.duplex_override
                action = Action.stop_receiving
        # Duplex
        elif (
            self.chemistry is Chemistry.DUPLEX_SIMPLE
            and previous_action is Action.stop_receiving
            and action is Action.unblock
        ):
            previous_decision_allowed = (
                self.duplex_tracker.get_previous_decision(result.channel)
                not in DISALLOWED_DUPLEX_DECISIONS
            )
            if previous_decision_allowed:
                self.logger.debug(
                    f"Overriding to duplex - previous read action {previous_action}, current_action: {action},"
                    f" previous_decision: {self.duplex_tracker.get_previous_decision(result.channel)}"
                )
                action = Action.stop_receiving
                action_overridden = True
                result.decision = Decision.duplex_override

        # Override to stop receiving if this is the first read ona channel and we started mid sequencing
        if previous_action is None and self.readfish_started_during_sequencing:
            self.logger.debug(
                f"This is the first suitable read chunk from channel {result.channel}. Translocated read length unknown, sequencing."
            )
            action_overridden = True
            result.decision = Decision.first_read_override
            action = Action.stop_receiving

        if action is Action.stop_receiving:
            stop_receiving_action_list.append((result.channel, result.read_number))

        elif action is Action.unblock:
            if self.dry_run:
                # Log an 'unblock' action to previous action, but send a 'stop receiving' to prevent further read processing.
                action_overridden = True
                stop_receiving_action_list.append((result.channel, result.read_number))
            else:
                unblock_batch_action_list.append(
                    (result.channel, result.read_number, result.read_id)
                )

        # If we have made a final decision for this read and we shouldn't see it again!
        if action is Action.unblock or action is Action.stop_receiving:
            # Add decided Action
            self.previous_action_tracker.add_action(result.channel, action)
            # Add duplex based tracking if we are in duplex mode
            if self.chemistry is Chemistry.DUPLEX_SIMPLE:
                self.duplex_tracker.set_decision(result.channel, result.decision)
            elif self.chemistry is Chemistry.DUPLEX:
                self.duplex_tracker.set_decision(result.channel, result.decision)
                self.duplex_tracker.set_alignments(
                    result.channel,
                    [(al.ctg, Strand(al.strand)) for al in result.alignment_data],
                )

        return (
            previous_action,
            action_overridden,
            action.name if action_overridden else None,
        )

    def run(self):
        """Run the read until loop, in one continuous while loop."""

        # TODO: Swap this for a CSV record later
        self.conf.write_channels_toml(self.client.mk_run_dir)

        # TODO: This could still be passed through to the basecaller to prevent
        #       rebasecalling data that is already being unblocked or sequenced
        loop_counter = 0

        last_live_toml_mtime = 0
        self.logger.info("Starting main loop")
        mapper_description = self.mapper.describe(self.conf.regions, self.conf.barcodes)
        self.logger.info(mapper_description)
        send_message(self.client.connection, mapper_description, Severity.INFO)

        while self.client.is_sequencing:
            t0 = timer()
            # Check if we have started readfish before PHASE_SEQUENCING,
            if self.wait_for_sequencing:
                time.sleep(self.throttle)
                continue
            # Set back to true for when we re-enter a non sequencing phase
            self.log_once_in_loop = True

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

            last_live_toml_mtime = self.reload_toml(last_live_toml_mtime)
            ########### Main Loop ###########
            loop_counter += 1
            number_reads = 0
            unblock_batch_action_list = []
            stop_receiving_action_list = []

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
                result.decision = make_decision(self.conf, result)
                action = condition.get_action(result.decision)
                seen_count = self.chunk_tracker.seen(result.channel, result.read_number)
                #  Check if there any conditions that override the action chose, exceed_max_chunks etc...
                (
                    previous_action,
                    action_overridden,
                    overridden_action_name,
                ) = self.check_override_action(
                    control,
                    action,
                    result,
                    seen_count,
                    condition,
                    stop_receiving_action_list,
                    unblock_batch_action_list,
                )
                self.loop_statistics.log_read(
                    client_iteration=loop_counter,
                    read_in_loop=number_reads,
                    read_id=result.read_id,
                    channel=result.channel,
                    read_number=result.read_number,
                    seq_len=len(result.seq),
                    counter=seen_count,
                    mode=result.decision.name,
                    decision=action.name,
                    condition=condition.name,
                    barcode=result.barcode,
                    previous_action=(
                        previous_action.name
                        if previous_action is not None
                        else previous_action
                    ),
                    action_overridden=action_overridden,
                    timestamp=time.time(),
                    # Anything below here is not included in the Debug log
                    region_name=(
                        _region.name
                        if (_region := self.conf.get_region(result.channel))
                        else "flowcell"
                    ),
                    overridden_action_name=overridden_action_name,
                )

            #######################################################################
            # Compile actions to be sent
            self.client.unblock_read_batch(
                unblock_batch_action_list, duration=self.unblock_duration
            )
            self.client.stop_receiving_batch(stop_receiving_action_list)

            t1 = timer()
            if number_reads > 0:
                self.loop_statistics.add_batch_performance(
                    number_of_reads=number_reads, batch_time=t1 - t0
                )
                self.logger.info(self.loop_statistics.get_batch_performance())

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

    # Set the padding if it is specified.
    if padding := getattr(args, "padding", None):
        for region in conf.regions:
            region.targets.padding = padding
        for barcode in conf.barcodes:
            conf.barcodes[barcode].targets.padding = padding
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
        debug_log=args.debug_log,
        unblock_duration=args.unblock_duration,
        throttle=args.throttle,
        dry_run=args.dry_run,
        toml=args.toml,
        chemistry=Chemistry(args.chemistry),
    )

    # begin readfish function
    try:
        worker.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, stopping readfish.")
        pass
    finally:
        read_until_client.reset()

    send_message(
        read_until_client.connection,
        "Readfish disconnected from this device. Sequencing will proceed normally.",
        Severity.WARN,
    )
    return 0
