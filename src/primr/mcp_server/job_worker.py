"""Child-process entry point for one supervised MCP research job."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import threading
from dataclasses import dataclass
from typing import Any, BinaryIO, TextIO, cast


def _isolate_standard_streams() -> tuple[object, object]:
    """Keep control/protocol pipes private from pipeline descendants.

    The controller gives the worker its protocol over standard input/output.
    Before importing pipeline code, duplicate those descriptors, mark the
    duplicates non-inheritable, replace fd 0 with ``DEVNULL``, and route fd 1
    to the worker log on fd 2. Python, native extensions, and subprocesses can
    then use ordinary stdin/stdout without reading control commands, corrupting
    JSONL, or keeping the controller's protocol pipe open after worker exit.
    """
    control_fd = os.dup(0)
    protocol_fd = os.dup(1)
    try:
        os.set_inheritable(control_fd, False)
        os.set_inheritable(protocol_fd, False)
        devnull_fd = os.open(os.devnull, os.O_RDWR)
        try:
            os.dup2(devnull_fd, 0)
        finally:
            os.close(devnull_fd)
        os.dup2(2, 1)
        if sys.platform == "win32":
            import ctypes
            import msvcrt

            windows_loader = getattr(ctypes, "WinDLL", None)
            if windows_loader is None:
                raise OSError("ctypes.WinDLL is unavailable")
            kernel32 = windows_loader("kernel32", use_last_error=True)
            set_standard_handle = kernel32.SetStdHandle
            set_standard_handle.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
            set_standard_handle.restype = ctypes.c_int
            for standard_id, descriptor in ((-10, 0), (-11, 1)):
                handle = msvcrt.get_osfhandle(descriptor)
                if not set_standard_handle(standard_id & 0xFFFFFFFF, handle):
                    raise OSError(ctypes.get_last_error(), "SetStdHandle failed")
        return (
            os.fdopen(control_fd, "rb", buffering=0),
            os.fdopen(protocol_fd, "wb", buffering=0),
        )
    except BaseException:
        os.close(control_fd)
        os.close(protocol_fd)
        raise


_SUPERVISED = os.environ.get("PRIMR_SUPERVISED_WORKER") == "1"
_EXPECTED_JOB_ID = os.environ.get("PRIMR_WORKER_JOB_ID")
_JOB_OBJECT_NAME = os.environ.get("PRIMR_WORKER_JOB_OBJECT")
_SUPERVISED_CONTROL_STREAM: object | None = None
_SUPERVISED_PROTOCOL_STREAM: object | None = None


def _set_linux_parent_death_signal(death_signal: int) -> None:
    """Set or clear Linux parent-death signaling for the bootstrap window."""
    if not sys.platform.startswith("linux"):
        return
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, death_signal, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        error_number = ctypes.get_errno()
        raise OSError(error_number, "prctl(PR_SET_PDEATHSIG) failed")


if _SUPERVISED:
    try:
        _SUPERVISED_CONTROL_STREAM, _SUPERVISED_PROTOCOL_STREAM = _isolate_standard_streams()
        if sys.platform == "win32":
            if not _JOB_OBJECT_NAME:
                raise OSError("Worker supervision setup is missing")
            from primr.mcp_server.windows_job import attach_current_process

            attach_current_process(_JOB_OBJECT_NAME)
        elif sys.platform.startswith("linux"):
            # Cover bootstrap before the control reader exists. No pipeline
            # work can run in this interval, so killing only the worker cannot
            # orphan pipeline descendants. The signal is cleared immediately
            # after the reader starts; parent loss then kills the whole group.
            parent_pid = os.getppid()
            _set_linux_parent_death_signal(signal.SIGKILL)
            if os.getppid() != parent_pid:
                os.kill(os.getpid(), signal.SIGKILL)
    except BaseException as exc:
        print(f"Worker supervision setup failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        raise SystemExit(1) from None

# Controller-only markers must not flow into pipeline descendants. They remain
# present through the early imports so Primr's .env loader can protect them.
os.environ.pop("PRIMR_WORKER_JOB_ID", None)
os.environ.pop("PRIMR_WORKER_JOB_OBJECT", None)

from primr.config.env import load_primr_env
from primr.mcp_server.job_store import ResearchJobState
from primr.mcp_server.pipeline_runner import PipelineRunner
from primr.mcp_server.types import ResearchStage
from primr.mcp_server.worker_protocol import (
    MAX_LINE_BYTES,
    WorkerProtocolError,
    decode_message,
    encode_message,
    make_event,
    read_message,
    validate_cancel_command,
    validate_start_command,
)
from primr.utils.async_utils import run_sync

# Capture and apply the supervised .env policy before removing the bootstrap
# marker. Later lazy configuration loads remain in supervised mode because the
# config module retains that trusted process-start state.
load_primr_env()
os.environ.pop("PRIMR_SUPERVISED_WORKER", None)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_PROTOCOL_ERROR = 2
EXIT_CANCELLED = 130
PARENT_DISCONNECT_GRACE_SECONDS = 10.0


class WorkerEventEmitter:
    """Serialize worker events to the protocol stream in sequence order."""

    def __init__(self, stream: BinaryIO, job_id: str) -> None:
        self._stream = stream
        self._job_id = job_id
        self._sequence = 0
        self._lock = threading.Lock()

    def emit(
        self,
        kind: str,
        *,
        state: dict[str, Any] | None = None,
        exit_reason: str | None = None,
    ) -> None:
        with self._lock:
            self._sequence += 1
            event = make_event(
                kind=kind,
                job_id=self._job_id,
                seq=self._sequence,
                state=state,
                exit_reason=exit_reason,
            )
            self._stream.write(encode_message(event))
            self._stream.flush()


class WorkerJobStore:
    """PipelineRunner store adapter that publishes existing job snapshots."""

    def __init__(self, emitter: WorkerEventEmitter) -> None:
        self._emitter = emitter
        self.latest_snapshot: dict[str, Any] | None = None

    def update(self, job: ResearchJobState) -> None:
        snapshot = job.to_journal_dict()
        self.latest_snapshot = snapshot
        # The parent owns terminal commitment and applies it only after it has
        # observed process exit. Publishing a terminal job as an ordinary
        # state event would either violate that rule or force the parent to
        # special-case a misleading progress event.
        if not job.is_terminal():
            self._emitter.emit("state", state=snapshot)


@dataclass
class WorkerServerContext:
    """Minimal PipelineRunner context for the child process."""

    job_store: WorkerJobStore


class CancellationController:
    """Bridge blocking stdin control messages into the worker event loop."""

    def __init__(
        self,
        *,
        job_id: str,
        loop: asyncio.AbstractEventLoop,
        runner: PipelineRunner,
        task: asyncio.Task[None],
        stderr: TextIO,
        parent_loss_hard_exit: bool,
    ) -> None:
        self.job_id = job_id
        self.loop = loop
        self.runner = runner
        self.task = task
        self.stderr = stderr
        self.parent_loss_hard_exit = parent_loss_hard_exit
        self.reason: str | None = None
        self._lock = threading.Lock()
        self._parent_loss_timer: threading.Timer | None = None

    def request(self, reason: str) -> None:
        """Schedule cooperative cancellation exactly once."""
        with self._lock:
            if self.reason is not None:
                return
            self.reason = reason
        with contextlib.suppress(RuntimeError):
            self.loop.call_soon_threadsafe(self._cancel_in_loop)
        if reason == "parent_disconnected" and self.parent_loss_hard_exit:
            timer = threading.Timer(
                PARENT_DISCONNECT_GRACE_SECONDS,
                _force_exit_after_parent_loss,
            )
            timer.daemon = True
            self._parent_loss_timer = timer
            timer.start()

    def _cancel_in_loop(self) -> None:
        self.runner.request_cancel()
        self.task.cancel()

    def close(self) -> None:
        """Cancel the parent-loss watchdog after normal worker settlement."""
        if self._parent_loss_timer is not None:
            self._parent_loss_timer.cancel()
            self._parent_loss_timer = None


def _force_exit_after_parent_loss() -> None:
    """Fail closed if cooperative cancellation stalls after controller loss."""
    if sys.platform == "win32":
        os._exit(EXIT_FAILURE)
    try:
        kill_group = getattr(os, "killpg")  # noqa: B009 - absent from Windows stubs
        kill_signal = getattr(signal, "SIGKILL")  # noqa: B009 - absent from Windows stubs
        kill_group(os.getpgrp(), kill_signal)
    except (AttributeError, ProcessLookupError):
        os._exit(EXIT_FAILURE)


def _control_reader(
    stream: BinaryIO,
    controller: CancellationController,
) -> None:
    """Read cancel commands until cancellation, EOF, or a protocol error."""
    while True:
        try:
            line = stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                controller.request("parent_disconnected")
                return
            command = decode_message(line)
            command = validate_cancel_command(command, expected_job_id=controller.job_id)
        except WorkerProtocolError as exc:
            print(f"Worker control protocol error: {exc}", file=controller.stderr, flush=True)
            controller.request("control_protocol_error")
            return
        controller.request(str(command["reason"]))
        return


async def run_worker(
    start: dict[str, Any],
    *,
    control_stream: BinaryIO,
    protocol_stream: BinaryIO,
    stderr: TextIO,
    parent_loss_hard_exit: bool = False,
) -> int:
    """Run one validated start command to a terminal worker event."""
    start = validate_start_command(start)
    job = ResearchJobState.from_journal_dict(start["job"])
    emitter = WorkerEventEmitter(protocol_stream, job.job_id)
    store = WorkerJobStore(emitter)
    context = WorkerServerContext(job_store=store)
    runner = PipelineRunner(context)  # type: ignore[arg-type]

    emitter.emit("ready")
    emitter.emit("state", state=job.to_journal_dict())

    research_task = asyncio.create_task(
        runner.run_research(
            job=job,
            company_url=start["company_url"],
            mode=start["mode"],
            platform=start["platform"],
            skip_qa=start["skip_qa"],
            verify=start["verify"],
            destination=start["destination"],
            budget_usd=start["budget_usd"],
        )
    )
    controller = CancellationController(
        job_id=job.job_id,
        loop=asyncio.get_running_loop(),
        runner=runner,
        task=research_task,
        stderr=stderr,
        parent_loss_hard_exit=parent_loss_hard_exit,
    )
    control_thread = threading.Thread(
        target=_control_reader,
        args=(control_stream, controller),
        name=f"primr-worker-control-{job.job_id[:8]}",
        daemon=True,
    )
    control_thread.start()
    if parent_loss_hard_exit:
        # The reader is now ready to observe controller-pipe EOF and kill the
        # complete process group. Retaining worker-only PDEATHSIG beyond this
        # point would kill the leader first and strand its descendants.
        _set_linux_parent_death_signal(0)

    try:
        # Pipeline and dependency console output must not corrupt protocol stdout.
        with contextlib.redirect_stdout(stderr):
            await research_task
    except asyncio.CancelledError:
        if not job.is_terminal():
            job.advance_stage(ResearchStage.CANCELLED)
            job.error_type = "user_cancelled"
            job.error_message = "Job was cancelled"
            store.update(job)
    except Exception as exc:
        print(
            f"Worker execution failed: {type(exc).__name__}",
            file=stderr,
            flush=True,
        )
        if not job.is_terminal():
            job.advance_stage(ResearchStage.FAILED)
            job.error_type = "worker_error"
            job.error_message = "Worker execution failed"
            store.update(job)

    if not job.is_terminal():
        job.advance_stage(ResearchStage.FAILED)
        job.error_type = "worker_incomplete"
        job.error_message = "Worker exited without a terminal job state"
        store.update(job)

    exit_reason = _terminal_reason(job, controller.reason)
    parent_disconnected = controller.reason == "parent_disconnected"
    try:
        emitter.emit("terminal", state=job.to_journal_dict(), exit_reason=exit_reason)
    finally:
        if parent_disconnected and parent_loss_hard_exit:
            _force_exit_after_parent_loss()
    controller.close()
    if job.current_stage == ResearchStage.COMPLETED:
        return EXIT_SUCCESS
    if job.current_stage == ResearchStage.CANCELLED:
        return EXIT_CANCELLED
    return EXIT_FAILURE


def _terminal_reason(job: ResearchJobState, cancellation_reason: str | None) -> str:
    if job.current_stage == ResearchStage.COMPLETED:
        return "completed"
    if job.current_stage == ResearchStage.CANCELLED:
        return cancellation_reason or job.error_type or "user_cancelled"
    return job.error_type or "failed"


def main(
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Read one start command, run it, and return a process exit code."""
    input_stream = stdin or cast("BinaryIO | None", _SUPERVISED_CONTROL_STREAM) or sys.stdin.buffer
    protocol_stream = (
        stdout or cast("BinaryIO | None", _SUPERVISED_PROTOCOL_STREAM) or sys.stdout.buffer
    )
    error_stream = stderr or sys.stderr

    try:
        start = validate_start_command(read_message(input_stream))
    except (WorkerProtocolError, KeyError, TypeError, ValueError) as exc:
        print(f"Worker start protocol error: {exc}", file=error_stream, flush=True)
        return EXIT_PROTOCOL_ERROR
    if _SUPERVISED and start["job_id"] != _EXPECTED_JOB_ID:
        print("Worker supervision job id mismatch", file=error_stream, flush=True)
        return EXIT_PROTOCOL_ERROR

    try:
        return run_sync(
            run_worker(
                start,
                control_stream=input_stream,
                protocol_stream=protocol_stream,
                stderr=error_stream,
                parent_loss_hard_exit=_SUPERVISED,
            )
        )
    except Exception as exc:
        print(
            f"Worker failed before completion: {type(exc).__name__}", file=error_stream, flush=True
        )
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
