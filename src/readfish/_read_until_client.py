"""read_until_client.py
Subclasses ONTs read_until_api ReadUntilClient added extra function that logs unblocks read_ids.
"""
from __future__ import annotations
import logging
import time

from pathlib import Path

from minknow_api.acquisition_pb2 import AcquisitionState
from minknow_api import protocol_service, acquisition_service
from readfish.read_until.base import ReadUntilClient
from readfish._loggers import setup_logger
from grpc import RpcError

# Check against these states to determine if Minknow is under the impression
# The run has fully begun and readfish can be started
ACCEPTABLE_ACQUISITION_STATES = {
    AcquisitionState.ACQUISITION_RUNNING,
    AcquisitionState.ACQUISITION_STARTING,
}
# Any but these two states suggest the run has stopped
ACCEPTABLE_PROTOCOL_STATES = {
    protocol_service.PROTOCOL_RUNNING,
    protocol_service.PROTOCOL_WAITING_FOR_TEMPERATURE,
}
# We expect sequencing to begin again after these phases
LOOPABLE_PROTOCOL_PHASES = {
    protocol_service.PHASE_INITIALISING,
    protocol_service.PHASE_MUX_SCAN,
    protocol_service.PHASE_RESUMING,
    protocol_service.PHASE_PREPARING_FOR_MUX_SCAN,
    protocol_service.PHASE_PAUSING,
    protocol_service.PHASE_PAUSED,
}
#  Timeout in seconds for the run folder to appear
TIMEOUT = 120


class RUClient(ReadUntilClient):
    """Subclasses ONTs read_until_api ReadUntilClient adding extra function that logs unblocks read_ids."""

    def __init__(self, *args, **kwargs):
        #  Default to TIMEOUT in the event we are not starting from the CLI.
        # If started from CLI args.wait-for-ready is used - also defaults to 120s
        self.timeout = kwargs.pop("timeout", TIMEOUT)
        super().__init__(*args, **kwargs)
        # disable the read until client logger
        self.logger.disabled = True
        self.log = setup_logger(
            __name__,
            level=logging.INFO,
            log_format="%(asctime)s %(name)s %(message)s",
            propagate=True,
        )
        self.current_protocol_phase = None
        self.current_protocol_state = None

        self.current_acquisition_state = None
        self.phase_errors = 0
        self.current_protocol = 0
        self.max_phase_errors = 1
        self.set_protocol_info()

        # We always want one_chunk to be False
        self.one_chunk = False

        self.mk_run_dir = Path(
            self.connection.protocol.get_current_protocol_run().output_path
        )
        if self.mk_host not in ("localhost", "127.0.0.1"):
            # running remotely, output in cwd
            self.mk_run_dir = "."
        # Loop until the run folder exists or the run stops
        self.wait_for_minknow_folder(self.timeout)
        # Attempt to create `unblocked_read_ids.txt` if this fails set the run
        # directory as the PWD this will also affect where the channels.toml
        # file is written to
        try:
            ids_log = self.mk_run_dir.joinpath("unblocked_read_ids.txt")
            ids_log.touch(exist_ok=True)
        except (PermissionError, FileNotFoundError):
            # TODO: log message here that fallback output is in use
            self.mk_run_dir = Path(".")
            ids_log = self.mk_run_dir.joinpath("unblocked_read_ids.txt")
            ids_log.touch(exist_ok=True)
        self.unblock_logger = setup_logger(
            "unblock_logger",
            log_file=ids_log,
            log_format="%(message)s",
            queue_bound=-1,
        )

    def unblock_read_batch(
        self, reads: list[tuple[int, int, str]], duration: float = 0.1
    ) -> None:
        """Request for a bunch of reads be unblocked.

        ``reads`` is expected to be a list of (channel, ReadData.number)

        :param reads: List of (channel, read_number, read_id)
        :param duration: time in seconds to apply unblock voltage.
        """
        actions = list()
        for channel, read_number, *read_id in reads:
            actions.append(
                self._generate_action(
                    channel, read_number, "unblock", duration=duration
                )
            )
            if read_id:
                self.unblock_logger.debug(read_id[0])
        self.action_queue.put(actions)

    def unblock_read(
        self,
        read_channel: int,
        read_number: int,
        duration: float = 0.1,
        read_id: str | None = None,
    ):
        """Send an unblock for a read via the read until client and log the read_id to the unblocked_read_ids.txt

        :param read_channel: The channel number
        :param read_number: The read number
        :param duration: The duration to apply the unblock voltage, defaults to 0.1
        :param read_id: The string uuid of the read, defaults to None
        """
        super().unblock_read(
            read_channel=read_channel,
            read_number=read_number,
            duration=duration,
        )
        if read_id is not None:
            self.unblock_logger.debug(read_id)

    def set_protocol_info(self):
        """Set the protocol info on the class. Gets the state and phase over the API."""
        try:
            protocol_run = self.connection.protocol.get_current_protocol_run()  # type: ignore
            current_state = protocol_run.state
            current_phase = protocol_run.phase
        except RpcError as e:
            self.log.info(f"Got RPC exception\n{e}")
            self.log.error(
                f"{e.details()}, Run is currently not underway, Please check MinKNOW UI."
            )
            self.phase_errors += 1
            raise SystemExit(1)
        if current_phase != self.current_protocol_phase:
            self.current_protocol_phase = current_phase
            self.log.info(
                f"Protocol phase changed to {protocol_service.ProtocolPhase.Name(self.current_protocol_phase)}"
            )
        if current_state != self.current_protocol_state:
            self.current_protocol_state = current_state
            self.log.info(
                f"Protocol state changed to {protocol_service.ProtocolState.Name(self.current_protocol_state)}"
            )

    def set_acquisition_state(self):
        """Set the acquisition state on the class. Gets the state over the API."""
        try:
            self.current_acquisition_state = (
                self.connection.acquisition.get_acquisition_info().state
            )
        except RpcError as e:
            if self.phase_errors < self.max_phase_errors:
                self.log.info(f"Got RPC exception\n{e}")
                self.log.info("Run may have ended")
                self.phase_errors += 1
            else:
                raise SystemExit(1)

    def wait_for_minknow_folder(self, timeout: int):
        """
        Rather than messing about with permissions wait for MinKNOW to create the run
        folder. If the folder doesn't appear after timeout seconds then write to the
        current working directory instead.
        """
        seconds_waited = 0
        while (
            not self.mk_run_dir.exists()
            and self.current_protocol_state in ACCEPTABLE_PROTOCOL_STATES
        ):
            # Update self.current_protocol_state
            self.set_protocol_info()
            if seconds_waited > timeout:
                self.log.warn(
                    f"Run folder did not appear after {timeout} seconds."
                    f" Writing extra output to {Path.cwd()}"
                )
                break
            if seconds_waited % 20 == 0:
                self.log.info(
                    f"Waiting up to {timeout} seconds for run folder to appear at {self.mk_run_dir}..."
                )
            time.sleep(1)
            seconds_waited += 1

    @property
    def acquisition_running(self) -> bool:
        """
        Acquisition State is a state indicating we are running
        , i.e a top level indication that the run is going to be sequencing.
        """
        self.set_acquisition_state()
        return self.current_acquisition_state in ACCEPTABLE_ACQUISITION_STATES

    @property
    def is_sequencing(self) -> bool:
        """And Running running

        Check the current protocol state and determine if
        the run is in suitable protocol state for readfish to run on.
        This implies the run hasn't stopped.

        Updates the self.current_state and self.current_phase attributes.
        """
        self.set_protocol_info()
        is_running = (
            self.current_protocol_state in ACCEPTABLE_PROTOCOL_STATES
            and self.acquisition_running
            and self.is_running
        )
        if not is_running:
            self.log.error(
                f"Protocol state is {protocol_service.ProtocolState.Name(self.current_protocol_state)} is"
                f" {protocol_service.ProtocolState.Name(protocol_service.PROTOCOL_WAITING_FOR_ACQUISITION)} or"
                " MinKNOW is reporting non data acquiring state."
                " Acquisition State - "
                f"({acquisition_service.AcquisitionState.Name(self.current_acquisition_state)})."
                " readfish is disconnecting..."
            )
        return is_running

    @property
    def wait_for_sequencing_to_start(self) -> bool:
        """Check the current protocol phase to determine if the run is in a phase that precedes sequencing.
        Returns false if the run is in the sequencing phase."""
        return (
            self.current_protocol_phase in LOOPABLE_PROTOCOL_PHASES
            and self.current_protocol_phase != protocol_service.PHASE_SEQUENCING
        )
