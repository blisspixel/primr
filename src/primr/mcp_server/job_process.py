"""Supervised local worker processes for long MCP and A2A research jobs.

The controller, not the child, owns canonical job state. A worker may publish
progress snapshots while it runs, but a terminal snapshot is committed only
after the controller has observed process exit. This makes cancellation
truthful even when the pipeline is executing blocking Python or native work.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import BinaryIO

from primr.mcp_server.job_process_types import (
    CancellationOutcome,
    CancellationReason,
    CancellationStatus,
    await_task_uninterruptibly,
)
from primr.mcp_server.job_process_types import (
    WorkerHandle as _WorkerHandle,
)
from primr.mcp_server.job_store import ResearchJobState, SingleJobStore
from primr.mcp_server.job_terminal_manifest import write_terminal_manifest
from primr.mcp_server.types import ResearchStage
from primr.mcp_server.windows_job import WindowsJobObject, create_worker_job
from primr.mcp_server.worker_environment import worker_environment
from primr.mcp_server.worker_process_control import cleanup_process_tree, signal_process_tree
from primr.mcp_server.worker_protocol import (
    MAX_LINE_BYTES,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    WorkerProtocolError,
    build_cancel_command,
    build_start_command,
    decode_message,
    encode_message,
    validate_event,
)
from primr.mcp_server.worker_terminal_policy import (
    is_cancel_return_code,
    terminal_event_is_compatible,
)
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)

WORKER_PROTOCOL = PROTOCOL_NAME
WORKER_PROTOCOL_VERSION = PROTOCOL_VERSION
MAX_WORKER_LINE_BYTES = MAX_LINE_BYTES
DEFAULT_COOPERATIVE_TIMEOUT = 10.0
DEFAULT_TERMINATE_TIMEOUT = 5.0
DEFAULT_KILL_TIMEOUT = 5.0
DEFAULT_READY_TIMEOUT = 10.0
TREE_CLEANUP_RETRY_INTERVAL = 0.25


class LocalJobSupervisor:
    """Own and supervise one local Python child process per research job."""

    def __init__(
        self,
        job_store: SingleJobStore,
        *,
        worker_command: tuple[str, ...] | None = None,
        output_root: str | Path | None = None,
        cooperative_timeout: float = DEFAULT_COOPERATIVE_TIMEOUT,
        terminate_timeout: float = DEFAULT_TERMINATE_TIMEOUT,
        kill_timeout: float = DEFAULT_KILL_TIMEOUT,
        ready_timeout: float = DEFAULT_READY_TIMEOUT,
    ) -> None:
        self._job_store = job_store
        self._worker_command = worker_command or (
            sys.executable,
            "-m",
            "primr.mcp_server.job_worker",
        )
        self._output_root = Path(output_root) if output_root is not None else None
        self._cooperative_timeout = cooperative_timeout
        self._terminate_timeout = terminate_timeout
        self._kill_timeout = kill_timeout
        self._ready_timeout = ready_timeout
        self._handles: dict[str, _WorkerHandle] = {}
        self._start_lock = asyncio.Lock()
        self._shutdown_started = False

    @property
    def running_job_ids(self) -> tuple[str, ...]:
        """Return the job ids whose child processes are still owned."""
        return tuple(self._handles)

    async def start(
        self,
        *,
        job: ResearchJobState,
        company_url: str,
        mode: str,
        platform: str | None = None,
        skip_qa: bool = False,
        verify: bool = False,
        destination: str | None = None,
        budget_usd: float | None = None,
    ) -> asyncio.Task[None]:
        """Spawn one worker and return the task that observes its lifecycle."""
        async with self._start_lock:
            if self._shutdown_started:
                self._commit_failure(
                    job.job_id,
                    "server_shutdown",
                    "Server shutdown before worker start",
                )
                raise RuntimeError("Cannot start a worker while the server is shutting down")
            if job.is_terminal():
                raise ValueError(f"Cannot start terminal job {job.job_id}")
            if job.job_id in self._handles:
                raise RuntimeError(f"Worker already exists for job {job.job_id}")

            stderr_file: BinaryIO | None = None
            windows_job: WindowsJobObject | None = None
            spawn_task: asyncio.Task[asyncio.subprocess.Process] | None = None
            handle: _WorkerHandle | None = None
            try:
                start_message = build_start_command(
                    job=job.to_journal_dict(),
                    company_url=company_url,
                    mode=mode,
                    platform=platform,
                    skip_qa=skip_qa,
                    verify=verify,
                    destination=destination,
                    budget_usd=budget_usd,
                )

                log_path = self._worker_log_path(job.job_id)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                # The handle owns this stream until its monitor observes exit.
                stderr_file = open(log_path, "ab", buffering=0)  # noqa: SIM115

                environment = worker_environment()
                environment["PRIMR_SUPERVISED_WORKER"] = "1"
                environment["PRIMR_WORKER_JOB_ID"] = job.job_id
                if os.name == "nt":
                    job_object_name = f"Local\\Primr-{uuid.uuid4()}"
                    windows_job = create_worker_job(job_object_name)
                    environment["PRIMR_WORKER_JOB_OBJECT"] = job_object_name
                    spawn_task = asyncio.create_task(
                        asyncio.create_subprocess_exec(
                            *self._worker_command,
                            stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=stderr_file,
                            env=environment,
                            limit=MAX_WORKER_LINE_BYTES,
                            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                        ),
                        name=f"primr-worker-spawn-{job.job_id}",
                    )
                else:
                    spawn_task = asyncio.create_task(
                        asyncio.create_subprocess_exec(
                            *self._worker_command,
                            stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=stderr_file,
                            env=environment,
                            limit=MAX_WORKER_LINE_BYTES,
                            start_new_session=True,
                        ),
                        name=f"primr-worker-spawn-{job.job_id}",
                    )

                # Shield process creation so cancellation cannot discard a
                # successfully created child before its handle is retained.
                process = await asyncio.shield(spawn_task)
                handle = self._register_worker(
                    job=job,
                    process=process,
                    stderr_file=stderr_file,
                    windows_job=windows_job,
                    company_url=company_url,
                    mode=mode,
                    budget_usd=budget_usd,
                )
                stderr_file = None
                windows_job = None
            except asyncio.CancelledError:
                if spawn_task is not None and handle is None:
                    try:
                        process = await await_task_uninterruptibly(spawn_task)
                    except BaseException:
                        process = None
                    if process is not None and stderr_file is not None:
                        handle = self._register_worker(
                            job=job,
                            process=process,
                            stderr_file=stderr_file,
                            windows_job=windows_job,
                            company_url=company_url,
                            mode=mode,
                            budget_usd=budget_usd,
                        )
                        stderr_file = None
                        windows_job = None
                if handle is not None:
                    handle.protocol_error = "Worker startup was cancelled"
                    await self._abort_startup_uninterruptibly(handle)
                else:
                    self._close_startup_resources(stderr_file, windows_job)
                    self._commit_failure(
                        job.job_id,
                        "worker_start_cancelled",
                        "Worker startup was cancelled",
                    )
                raise
            except BaseException:
                self._close_startup_resources(stderr_file, windows_job)
                self._commit_failure(
                    job.job_id,
                    "worker_spawn_failed",
                    "Worker process failed to start",
                )
                raise

            assert handle is not None
            monitor_task = handle.monitor_task
            assert monitor_task is not None
            if self._shutdown_started:
                handle.cancel_reason = "server_shutdown"
                await self._abort_startup_uninterruptibly(handle)
                raise RuntimeError("Server shutdown while worker was starting")

        try:
            await self._send(handle, start_message)
            await self._wait_for_ready(handle)
        except BaseException as exc:
            handle.protocol_error = f"Worker failed to become ready: {exc}"
            await self._abort_startup_uninterruptibly(handle)
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise RuntimeError(handle.protocol_error) from exc

        return monitor_task

    def _register_worker(
        self,
        *,
        job: ResearchJobState,
        process: asyncio.subprocess.Process,
        stderr_file: BinaryIO,
        windows_job: WindowsJobObject | None,
        company_url: str,
        mode: str,
        budget_usd: float | None,
    ) -> _WorkerHandle:
        """Retain a spawned process before any caller can lose ownership."""
        handle = _WorkerHandle(
            job_id=job.job_id,
            process=process,
            stderr_file=stderr_file,
            company_url=company_url,
            mode=mode,
            budget_usd=budget_usd,
            done=asyncio.Event(),
            ready_event=asyncio.Event(),
            windows_job=windows_job,
            finalization_lock=asyncio.Lock(),
        )
        self._handles[job.job_id] = handle
        monitor_task = asyncio.create_task(
            self._monitor_worker(handle),
            name=f"primr-worker-monitor-{job.job_id}",
        )
        handle.monitor_task = monitor_task
        return handle

    @staticmethod
    def _close_startup_resources(
        stderr_file: BinaryIO | None,
        windows_job: WindowsJobObject | None,
    ) -> None:
        """Close resources when startup fails before a process is retained."""
        if windows_job is not None:
            with contextlib.suppress(OSError):
                windows_job.close()
        if stderr_file is not None:
            stderr_file.close()

    async def _abort_startup_uninterruptibly(self, handle: _WorkerHandle) -> None:
        """Force a retained startup child down and wait until exit is observed."""
        cleanup_task = asyncio.create_task(
            self._abort_startup(handle),
            name=f"primr-worker-startup-abort-{handle.job_id}",
        )
        with contextlib.suppress(BaseException):
            await await_task_uninterruptibly(cleanup_task)

    async def _abort_startup(self, handle: _WorkerHandle) -> None:
        await self._force_stop(handle)
        if handle.monitor_task is not None:
            await asyncio.shield(handle.monitor_task)

    async def cancel(
        self,
        job_id: str,
        *,
        reason: CancellationReason = "user_cancelled",
        cooperative_timeout: float | None = None,
        terminate_timeout: float | None = None,
        kill_timeout: float | None = None,
    ) -> CancellationOutcome:
        """Request stop, escalate if needed, and wait for observed worker exit."""
        # A start holds this lock until a spawned process has a retained
        # handle, so cancellation cannot race through the spawn gap.
        async with self._start_lock:
            handle = self._handles.get(job_id)
        if handle is None:
            job = self._job_store.get(job_id)
            if job is not None and job.is_terminal():
                terminal_status: CancellationStatus
                if job.current_stage == ResearchStage.CANCELLED:
                    terminal_status = "cancelled"
                elif job.current_stage == ResearchStage.COMPLETED:
                    terminal_status = "completed"
                else:
                    terminal_status = "failed"
                return CancellationOutcome(
                    status=terminal_status,
                    worker_exit_confirmed=True,
                    termination_method="already_exited",
                    error_message=job.error_message,
                )
            return CancellationOutcome(status="not_running", worker_exit_confirmed=False)

        if handle.cancellation_task is not None and handle.cancellation_task.done():
            try:
                previous_outcome = handle.cancellation_task.result()
            except BaseException:
                previous_outcome = None
            if previous_outcome is None or previous_outcome.status == "cancellation_failed":
                handle.cancellation_task = None

        if handle.cancellation_task is None:
            handle.cancel_reason = reason
            handle.cancellation_task = asyncio.create_task(
                self._cancel_handle(
                    handle,
                    cooperative_timeout=(
                        self._cooperative_timeout
                        if cooperative_timeout is None
                        else cooperative_timeout
                    ),
                    terminate_timeout=(
                        self._terminate_timeout if terminate_timeout is None else terminate_timeout
                    ),
                    kill_timeout=self._kill_timeout if kill_timeout is None else kill_timeout,
                ),
                name=f"primr-worker-cancel-{job_id}",
            )
        return await asyncio.shield(handle.cancellation_task)

    async def shutdown(self, timeout: float = 5.0) -> bool:
        """Stop owned workers and report whether every process was reaped."""
        self._shutdown_started = True
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, timeout)

        # Wait only within the caller's shutdown budget for an in-flight spawn
        # to become retained. The start path observes _shutdown_started and
        # tears that child down before releasing this lock.
        remaining = max(0.0, deadline - loop.time())
        try:
            await asyncio.wait_for(self._start_lock.acquire(), timeout=remaining)
        except TimeoutError:
            logger.error("Timed out waiting for an in-flight worker start during shutdown")
            return False
        try:
            handles = list(self._handles.values())
        finally:
            self._start_lock.release()
        if not handles:
            return True

        shutdown_tasks = [
            asyncio.create_task(
                self._shutdown_handle(handle, deadline),
                name=f"primr-worker-shutdown-{handle.job_id}",
            )
            for handle in handles
        ]
        remaining = max(0.0, deadline - loop.time())
        done, pending = await asyncio.wait(shutdown_tasks, timeout=remaining)
        for task in done:
            try:
                task.result()
            except BaseException:
                logger.exception("Worker shutdown task failed")

        if pending:
            # Do not extend the shutdown deadline. Issue one last force signal;
            # terminal state remains non-cancelled until the monitor observes
            # an actual return code.
            for handle in handles:
                if not self._exit_confirmed(handle):
                    await self._signal_process_tree(handle, force=True)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            logger.error(
                "Shutdown deadline expired with %d worker(s) not yet reaped",
                sum(not self._exit_confirmed(handle) for handle in handles),
            )
        return not self._handles

    async def _shutdown_handle(self, handle: _WorkerHandle, deadline: float) -> None:
        """Accelerate any existing cancellation within one shutdown deadline."""
        handle.cancel_reason = "server_shutdown"
        process = handle.process
        if process.returncode is None:
            with contextlib.suppress(Exception):
                await self._send(
                    handle,
                    build_cancel_command(handle.job_id, reason="server_shutdown"),
                )

        for force in (None, False, True):
            remaining = max(0.0, deadline - asyncio.get_running_loop().time())
            if remaining <= 0 or self._exit_confirmed(handle):
                return
            phases_left = 3 if force is None else (2 if force is False else 1)
            if force is not None:
                handle.termination_method = await self._signal_process_tree(handle, force=force)
            if await self._wait_done(handle, remaining / phases_left):
                return

    async def _monitor_worker(self, handle: _WorkerHandle) -> None:
        """Consume worker events, observe exit, then commit one terminal state."""
        process = handle.process
        assert process.stdout is not None
        monitor_cancelled = False
        try:
            while True:
                try:
                    line = await process.stdout.readline()
                except (ValueError, asyncio.LimitOverrunError) as exc:
                    handle.protocol_error = f"Worker event exceeded protocol limit: {exc}"
                    await self._force_stop(handle)
                    break
                if not line:
                    break
                try:
                    event = self._validate_event(line, handle)
                    self._apply_event(event, handle)
                except (KeyError, TypeError, ValueError, WorkerProtocolError) as exc:
                    handle.protocol_error = f"Invalid worker event: {exc}"
                    await self._force_stop(handle)
                    break
        except asyncio.CancelledError:
            monitor_cancelled = True
            handle.protocol_error = "Worker monitor was cancelled before process exit"
        except BaseException as exc:
            handle.protocol_error = f"Worker monitor failed: {type(exc).__name__}"

        if process.returncode is None and handle.protocol_error is not None:
            await self._force_stop(handle)

        return_code: int | None = process.returncode
        if return_code is None:
            wait_task = asyncio.create_task(
                process.wait(),
                name=f"primr-worker-wait-{handle.job_id}",
            )
            try:
                return_code = await await_task_uninterruptibly(wait_task)
            except BaseException as exc:
                handle.protocol_error = f"Worker exit wait failed: {type(exc).__name__}"
                return_code = process.returncode

        handle.exit_observed = return_code is not None and process.returncode is not None
        if handle.exit_observed:
            assert return_code is not None
            while not await self._complete_observed_exit(handle, return_code):
                try:
                    await asyncio.sleep(TREE_CLEANUP_RETRY_INTERVAL)
                except asyncio.CancelledError:
                    monitor_cancelled = True
                    break
        else:
            logger.error("Worker %s could not be reaped; retaining its handle", handle.job_id)

        if monitor_cancelled:
            raise asyncio.CancelledError

    def _validate_event(self, line: bytes, handle: _WorkerHandle) -> dict:
        event = decode_message(line)
        event = validate_event(event, handle.job_id, handle.expected_sequence)
        handle.expected_sequence += 1
        return event

    def _apply_event(self, event: dict, handle: _WorkerHandle) -> None:
        kind = event["kind"]
        if kind == "ready":
            if handle.ready:
                raise ValueError("worker emitted more than one ready event")
            if handle.terminal_snapshot is not None:
                raise ValueError("worker emitted ready after a terminal event")
            handle.ready = True
            if handle.ready_event is not None:
                handle.ready_event.set()
            return

        if not handle.ready:
            raise ValueError(f"worker emitted {kind} before ready")
        if handle.terminal_snapshot is not None:
            raise ValueError(f"worker emitted {kind} after terminal")

        snapshot = event.get("state")
        if not isinstance(snapshot, dict):
            raise TypeError(f"{kind} event requires an object state")
        if kind == "state":
            if not self._job_store.apply_worker_snapshot(handle.job_id, snapshot):
                current = self._job_store.get(handle.job_id)
                if current is None or not current.is_terminal():
                    raise ValueError("worker progress snapshot was rejected")
            return

        terminal = ResearchJobState.from_journal_dict(snapshot)
        if not terminal.is_terminal():
            raise ValueError("terminal event state is not terminal")
        handle.terminal_snapshot = snapshot
        handle.terminal_exit_reason = str(event["exit_reason"])

    async def _cancel_handle(
        self,
        handle: _WorkerHandle,
        *,
        cooperative_timeout: float,
        terminate_timeout: float,
        kill_timeout: float,
    ) -> CancellationOutcome:
        process = handle.process
        if process.returncode is None:
            with contextlib.suppress(Exception):
                await self._send(
                    handle,
                    build_cancel_command(
                        handle.job_id,
                        reason=handle.cancel_reason or "user_cancelled",
                    ),
                )

        if not await self._wait_done(handle, cooperative_timeout):
            handle.termination_method = await self._signal_process_tree(handle, force=False)
        if not await self._wait_done(handle, terminate_timeout):
            handle.termination_method = await self._signal_process_tree(handle, force=True)
        if not await self._wait_done(handle, kill_timeout):
            return CancellationOutcome(
                status="cancellation_failed",
                worker_exit_confirmed=False,
                termination_method=handle.termination_method,
                error_message="Worker exit could not be confirmed",
            )

        job = self._job_store.get(handle.job_id)
        if job is None:
            return CancellationOutcome(
                status="failed",
                worker_exit_confirmed=True,
                termination_method=handle.termination_method,
                error_message="Job state disappeared while cancelling",
            )
        status = job.get_status().value
        normalized: CancellationStatus
        if status == "cancelled":
            normalized = "cancelled"
        elif status == "completed":
            normalized = "completed"
        else:
            normalized = "failed"
        return CancellationOutcome(
            status=normalized,
            worker_exit_confirmed=True,
            termination_method=handle.termination_method or "cooperative",
            error_message=job.error_message,
        )

    async def _wait_done(self, handle: _WorkerHandle, timeout: float) -> bool:
        assert handle.done is not None
        if self._exit_confirmed(handle):
            return True
        if handle.exit_observed and handle.process.returncode is not None:
            if await self._complete_observed_exit(handle, handle.process.returncode):
                return True
        try:
            await asyncio.wait_for(handle.done.wait(), timeout=max(0.0, timeout))
        except TimeoutError:
            return False
        return self._exit_confirmed(handle)

    @staticmethod
    def _exit_confirmed(handle: _WorkerHandle) -> bool:
        """Return true only after the monitor observed a concrete return code."""
        return bool(
            handle.exit_observed
            and handle.process.returncode is not None
            and handle.done is not None
            and handle.done.is_set()
        )

    async def _wait_for_ready(self, handle: _WorkerHandle) -> None:
        """Wait until the child joins its ownership boundary and emits ready."""
        assert handle.ready_event is not None
        assert handle.done is not None
        ready_wait = asyncio.create_task(handle.ready_event.wait())
        done_wait = asyncio.create_task(handle.done.wait())
        try:
            completed, _pending = await asyncio.wait(
                {ready_wait, done_wait},
                timeout=self._ready_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not completed:
                raise TimeoutError(
                    f"worker did not emit ready within {self._ready_timeout:.1f} seconds"
                )
            if handle.ready_event.is_set():
                return
            raise RuntimeError(handle.protocol_error or "worker exited before ready")
        finally:
            for task in (ready_wait, done_wait):
                if not task.done():
                    task.cancel()
            await asyncio.gather(ready_wait, done_wait, return_exceptions=True)

    async def _send(self, handle: _WorkerHandle, message: dict) -> None:
        stdin = handle.process.stdin
        if stdin is None or stdin.is_closing():
            raise BrokenPipeError("worker stdin is closed")
        encoded = encode_message(message)
        stdin.write(encoded)
        await stdin.drain()

    async def _force_stop(self, handle: _WorkerHandle) -> None:
        if handle.process.returncode is None:
            handle.termination_method = await self._signal_process_tree(handle, force=True)
        if not handle.ready and handle.process.returncode is None:
            with contextlib.suppress(ProcessLookupError, OSError):
                handle.process.kill()
                if handle.termination_method == "terminate_job_object":
                    handle.termination_method = "terminate_job_object_and_process"

    async def _cleanup_tree_after_worker_exit(self, handle: _WorkerHandle) -> bool:
        """Remove descendants before the parent commits a terminal job state."""
        if handle.tree_cleanup_confirmed:
            return True
        handle.windows_job, error = await cleanup_process_tree(
            handle.process,
            handle.windows_job,
        )
        if error is not None:
            if error != handle.tree_cleanup_error:
                logger.error("Worker %s cleanup remains unconfirmed: %s", handle.job_id, error)
            handle.tree_cleanup_error = error
            handle.protocol_error = error
            return False
        handle.tree_cleanup_confirmed = True
        return True

    async def _complete_observed_exit(
        self,
        handle: _WorkerHandle,
        return_code: int,
    ) -> bool:
        """Commit terminal state only after parent exit and tree cleanup."""
        assert handle.finalization_lock is not None
        assert handle.done is not None
        async with handle.finalization_lock:
            if handle.done.is_set():
                return True
            if not handle.exit_observed or handle.process.returncode is None:
                return False
            if not await self._cleanup_tree_after_worker_exit(handle):
                return False

            self._finalize_after_exit(handle, return_code)
            self._write_terminal_manifest(handle, return_code)
            if handle.process.stdin is not None:
                handle.process.stdin.close()
                with contextlib.suppress(Exception):
                    await handle.process.stdin.wait_closed()
            handle.stderr_file.close()
            if handle.windows_job is not None:
                with contextlib.suppress(OSError):
                    handle.windows_job.close()
            self._handles.pop(handle.job_id, None)
            handle.done.set()
            return True

    async def _signal_process_tree(self, handle: _WorkerHandle, *, force: bool) -> str:
        return await signal_process_tree(
            handle.process,
            handle.windows_job,
            current_method=handle.termination_method,
            force=force,
        )

    def _finalize_after_exit(self, handle: _WorkerHandle, return_code: int | None) -> None:
        job = self._job_store.get(handle.job_id)
        if job is None or job.is_terminal():
            return

        if handle.protocol_error is not None:
            self._commit_failure(handle.job_id, "worker_protocol_error", handle.protocol_error)
            return

        if handle.cancel_reason == "server_shutdown":
            self._commit_failure(
                handle.job_id,
                "server_shutdown",
                "Server shutdown while job was in progress",
            )
            return

        terminal_snapshot = handle.terminal_snapshot
        if terminal_snapshot is not None:
            proposed = ResearchJobState.from_journal_dict(terminal_snapshot)
            if terminal_event_is_compatible(
                proposed,
                exit_reason=handle.terminal_exit_reason,
                return_code=return_code,
                cancel_reason=handle.cancel_reason,
                termination_method=handle.termination_method,
            ) and self._job_store.apply_worker_snapshot(
                handle.job_id,
                terminal_snapshot,
                allow_terminal=True,
            ):
                return

            self._commit_failure(
                handle.job_id,
                "worker_protocol_error",
                "Worker terminal state, exit reason, and return code were inconsistent",
            )
            return

        if handle.cancel_reason == "user_cancelled" and is_cancel_return_code(
            return_code, handle.termination_method
        ):
            self._commit_cancelled(handle.job_id, handle.termination_method or "cooperative")
        elif handle.cancel_reason == "user_cancelled":
            self._commit_failure(
                handle.job_id,
                "worker_protocol_error",
                "Worker exited successfully without a compatible cancellation terminal event",
            )
        else:
            self._commit_failure(
                handle.job_id,
                "worker_exit",
                f"Worker exited with code {return_code} without a terminal event",
            )

    def _commit_cancelled(self, job_id: str, method: str) -> None:
        job = self._job_store.get(job_id)
        if job is None or job.is_terminal():
            return
        if job.advance_stage(ResearchStage.CANCELLED):
            job.error_type = "user_cancelled"
            job.error_message = f"Worker exited after cancellation ({method})"
            self._job_store.update(job)

    def _commit_failure(self, job_id: str, error_type: str, message: str) -> None:
        job = self._job_store.get(job_id)
        if job is None or job.is_terminal():
            return
        if job.advance_stage(ResearchStage.FAILED):
            job.error_type = error_type
            job.error_message = message
            self._job_store.update(job)

    def _write_terminal_manifest(
        self,
        handle: _WorkerHandle,
        return_code: int | None,
    ) -> None:
        """Persist a compact audit manifest for failed and cancelled workers."""
        job = self._job_store.get(handle.job_id)
        if job is None or not job.is_terminal() or job.current_stage == ResearchStage.COMPLETED:
            return
        manifest_value = write_terminal_manifest(
            job=job,
            output_dir=self._worker_log_path(handle.job_id).parent,
            company_url=handle.company_url,
            mode=handle.mode,
            budget_usd=handle.budget_usd,
            return_code=return_code,
            cancel_reason=handle.cancel_reason,
            termination_method=handle.termination_method,
        )
        if manifest_value is None:
            return
        if manifest_value not in job.output_paths:
            job.output_paths.append(manifest_value)
            self._job_store.update(job)

    def _worker_log_path(self, job_id: str) -> Path:
        if self._output_root is not None:
            return self._output_root / job_id / "_worker.log"
        from primr.config.config import OUTPUT_DIR

        return Path(OUTPUT_DIR) / job_id / "_worker.log"


__all__ = [
    "MAX_WORKER_LINE_BYTES",
    "WORKER_PROTOCOL",
    "WORKER_PROTOCOL_VERSION",
    "CancellationOutcome",
    "LocalJobSupervisor",
    "worker_environment",
]
