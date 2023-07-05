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

# Library
from readfish._cli_args import DEVICE_BASE_ARGS
from readfish._client import RUClient
from readfish._config import Action, Conf
from readfish._loggers import setup_debug_logger
from readfish._utils import get_device, send_message, ChunkTracker, Severity
from readfish.plugins.abc import AlignerABC, CallerABC
from readfish.plugins.utils import Decision


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
        "--chunk-log",
        "--debug-log",
        dict(
            help="Chunk log",
            default=None,
        ),
    ),
)

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
)


class Analysis:
    """
    Analysis class where the read until magic happens. Comprises of one run
    function that is run threaded in the run function at the base of this file.
    Arguments listed in the __init__ docs.

    :param client: An instance of the ReadUntilClient object
    :param conf: readfish._config.Conf
    :param logger: The command level logger for this module
    :param debug_logger: The debug logger that writes the chunks. If None no chunks are logged.
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
        debug_logger: logging.Logger | None,
        throttle: float = 0.1,
        unblock_duration: float = 0.5,
        dry_run: bool = False,
        toml: str = "a.toml",
    ):
        self.client = client
        self.conf = conf
        self.logger = logger
        self.debug_logger = debug_logger
        self.throttle = throttle
        self.unblock_duration = unblock_duration
        self.dry_run = dry_run
        self.toml = Path(f"{toml}_live").resolve()

        self.chunk_log = setup_debug_logger(
            "chunk_log",
            log_file=debug_logger,
            header="\t".join(CHUNK_LOG_FIELDS),
        )
        logger.info("Initialising Caller")
        self.caller: CallerABC = conf.caller_settings.load_object("Caller")
        logger.info("Caller initialised")
        logger.info("Initialising Aligner")
        self.mapper: AlignerABC = conf.mapper_settings.load_object(
            "Aligner", readfish_config=self.conf
        )
        self.logger.info("Aligner initialised")

        # count how often a read is seen
        self.chunk_tracker = ChunkTracker(self.client.channel_count)

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

        self.logger.info("Starting main loop")
        while self.client.is_running:
            t0 = timer()
            if not self.client.is_phase_sequencing:
                time.sleep(self.throttle)
                continue

            if not self.mapper.initialised:
                # TODO: Log when in this trap
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
                action = condition.get_action(result.decision)
                # TODO: Create a tracker for previous channel end action
                previous_action = "TODO!"

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

                    # TODO: Check previous read decision here

                if action is Action.stop_receiving:
                    stop_receiving_action_list.append(
                        (result.channel, result.read_number)
                    )
                elif action is Action.unblock:
                    unblock_batch_action_list.append(
                        (result.channel, result.read_number, result.read_id)
                    )

                self.chunk_log.debug(
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
                    f"{previous_action}\t"
                    f"{time.time()}"
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
    )

    # Load TOML configuration
    conf = Conf.from_file(args.toml, read_until_client.channel_count, logger=logger)

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
        debug_logger=args.chunk_log,
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
