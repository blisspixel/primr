"""Process-level contracts for the local MCP/A2A job supervisor."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from primr.mcp_server import job_process as job_process_mod
from primr.mcp_server.job_process import LocalJobSupervisor, worker_environment
from primr.mcp_server.job_store import ResearchJobState, SingleJobStore
from primr.mcp_server.types import ResearchStage

_WORKER_PREAMBLE = r"""
import json
import os
import pathlib
import signal
import sys
import time
from datetime import datetime, timezone

PROTOCOL = "primr.mcp.worker"
VERSION = 1

if sys.platform == "win32":
    job_object_name = os.environ.pop("PRIMR_WORKER_JOB_OBJECT", None)
    if job_object_name:
        from primr.mcp_server.windows_job import attach_current_process
        attach_current_process(job_object_name)

def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def emit(kind, seq, state=None, exit_reason=None):
    event = {
        "protocol": PROTOCOL,
        "version": VERSION,
        "kind": kind,
        "job_id": job_id,
        "seq": seq,
        "ts": now(),
    }
    if state is not None:
        event["state"] = state
    if exit_reason is not None:
        event["exit_reason"] = exit_reason
    print(json.dumps(event, separators=(",", ":")), flush=True)

def terminal_state(stage, *, error_type=None, error_message=None):
    state = dict(job)
    state["current_stage"] = stage
    state["stage_progress_percent"] = 100 if stage == "completed" else 0
    state["last_heartbeat_time"] = now()
    state["completion_time"] = now()
    state["error_type"] = error_type
    state["error_message"] = error_message
    return state

start = json.loads(sys.stdin.readline())
job = dict(start["job"])
job_id = start["job_id"]
"""


def _worker_script(body: str) -> str:
    return textwrap.dedent(_WORKER_PREAMBLE) + "\n" + textwrap.dedent(body)


def _store_and_job(tmp_path: Path) -> tuple[SingleJobStore, ResearchJobState]:
    store = SingleJobStore(journal_path=str(tmp_path / "journal.json"))
    return store, store.create("Acme Corp", "full", owner_client_id="client-1")


def _supervisor(
    store: SingleJobStore,
    tmp_path: Path,
    script: str,
    *,
    cooperative_timeout: float = 0.2,
    terminate_timeout: float = 0.2,
    kill_timeout: float = 2.0,
) -> LocalJobSupervisor:
    return LocalJobSupervisor(
        store,
        worker_command=(sys.executable, "-c", script),
        output_root=tmp_path / "workers",
        cooperative_timeout=cooperative_timeout,
        terminate_timeout=terminate_timeout,
        kill_timeout=kill_timeout,
    )


async def _wait_for_path(
    path: Path,
    timeout: float = 3.0,
    *,
    expected: str | None = None,
) -> str:
    """Wait until *path* exists, optionally until its text matches *expected*.

    On Windows, ``Path.write_text`` can make the path visible before the
    write is flushed. Callers that assert on content should pass *expected*
    so the waiter does not race the empty open window.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    last = ""
    while True:
        if path.exists():
            try:
                last = path.read_text(encoding="utf-8")
            except OSError:
                last = ""
            if expected is None or last == expected:
                return last
        if asyncio.get_running_loop().time() >= deadline:
            detail = f" (last content {last!r})" if path.exists() else ""
            raise AssertionError(
                f"Timed out waiting for child marker: {path.name}{detail}"
            )
        await asyncio.sleep(0.01)


async def _cleanup(supervisor: LocalJobSupervisor, monitor: asyncio.Task[None] | None) -> None:
    for job_id in supervisor.running_job_ids:
        await supervisor.cancel(
            job_id,
            cooperative_timeout=0.05,
            terminate_timeout=0.05,
            kill_timeout=2.0,
        )
    if monitor is not None and not monitor.done():
        await asyncio.wait_for(asyncio.shield(monitor), timeout=3.0)


def test_worker_environment_strips_controller_names_case_insensitively() -> None:
    environment = worker_environment(
        {
            "mcp_jwt_secret": "secret",
            "Primr_Control_Plane_Token": "secret",
            "OPENAI_API_KEY": "provider",
            "AWS_SECRET_ACCESS_KEY": "cloud-secret",
            "AZURE_CLIENT_SECRET": "cloud-secret",
            "GOOGLE_APPLICATION_CREDENTIALS": "cloud-secret.json",
            "GITHUB_TOKEN": "ci-secret",
            "NVIDIA_API_KEY": "unrelated-cloud-secret",
            "NVIDIA_VISIBLE_DEVICES": "all",
            "APPLICATIONINSIGHTS_CONNECTION_STRING": "telemetry-secret",
        }
    )

    assert "mcp_jwt_secret" not in environment
    assert "Primr_Control_Plane_Token" not in environment
    assert environment["OPENAI_API_KEY"] == "provider"
    assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert "AZURE_CLIENT_SECRET" not in environment
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in environment
    assert "GITHUB_TOKEN" not in environment
    assert "NVIDIA_API_KEY" not in environment
    assert environment["NVIDIA_VISIBLE_DEVICES"] == "all"
    assert "APPLICATIONINSIGHTS_CONNECTION_STRING" not in environment


@pytest.mark.asyncio
async def test_spawn_failure_closes_worker_log_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lexical stream owner exits its context on every spawn failure."""
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, _worker_script("raise SystemExit(1)"))
    stderr_context = MagicMock()
    stderr_stream = MagicMock()
    stderr_context.__enter__.return_value = stderr_stream

    async def failed_spawn(*_args, **_kwargs):
        raise OSError("spawn failed")

    monkeypatch.setattr(
        job_process_mod, "open", lambda *_args, **_kwargs: stderr_context, raising=False
    )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", failed_spawn)

    with pytest.raises(OSError, match="spawn failed"):
        await supervisor.start(job=job, company_url="https://example.com", mode="full")

    stderr_context.__exit__.assert_called_once()
    failed = store.get(job.job_id)
    assert failed is not None
    assert failed.error_type == "worker_spawn_failed"


@pytest.mark.asyncio
async def test_worker_output_directory_failure_closes_output_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, _worker_script(""))
    supervisor.mark_output_preflight_succeeded()
    worker_directory = supervisor.output_root / job.job_id
    original_mkdir = Path.mkdir

    def guarded_mkdir(path: Path, *args, **kwargs) -> None:
        if path == worker_directory:
            raise OSError("output unavailable")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)

    with pytest.raises(OSError, match="output unavailable"):
        await supervisor.start(job=job, company_url="https://example.com", mode="full")

    assert supervisor.output_persistence_healthy is False
    failed = store.get(job.job_id)
    assert failed is not None
    assert failed.error_type == "worker_spawn_failed"


def test_terminal_manifest_failure_closes_output_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing required terminal artifact makes output readiness fail closed."""
    store, job = _store_and_job(tmp_path)
    job.advance_stage(ResearchStage.FAILED)
    store.update(job)
    supervisor = _supervisor(store, tmp_path, _worker_script(""))
    supervisor.mark_output_preflight_succeeded()
    handle = MagicMock(
        job_id=job.job_id,
        company_url="https://example.test",
        mode="full",
        budget_usd=None,
        cancel_reason=None,
        termination_method=None,
    )
    monkeypatch.setattr(job_process_mod, "write_terminal_manifest", lambda **_kwargs: None)

    supervisor._write_terminal_manifest(handle, return_code=1)

    assert supervisor.output_persistence_healthy is False


def test_terminal_manifest_directory_failure_closes_output_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, job = _store_and_job(tmp_path)
    job.advance_stage(ResearchStage.FAILED)
    store.update(job)
    supervisor = _supervisor(store, tmp_path, _worker_script(""))
    supervisor.mark_output_preflight_succeeded()
    handle = MagicMock(
        job_id=job.job_id,
        company_url="https://example.test",
        mode="full",
        budget_usd=None,
        cancel_reason=None,
        termination_method=None,
    )

    def fail_mkdir(*_args, **_kwargs) -> None:
        raise OSError("manifest directory unavailable")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    supervisor._write_terminal_manifest(handle, return_code=1)

    assert supervisor.output_persistence_healthy is False


def test_terminal_manifest_exception_closes_output_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, job = _store_and_job(tmp_path)
    job.advance_stage(ResearchStage.FAILED)
    store.update(job)
    supervisor = _supervisor(store, tmp_path, _worker_script(""))
    supervisor.mark_output_preflight_succeeded()
    handle = MagicMock(
        job_id=job.job_id,
        company_url="https://example.test",
        mode="full",
        budget_usd=None,
        cancel_reason=None,
        termination_method=None,
    )
    monkeypatch.setattr(
        job_process_mod,
        "write_terminal_manifest",
        MagicMock(side_effect=OSError("cleanup failed")),
    )

    supervisor._write_terminal_manifest(handle, return_code=1)

    assert supervisor.output_persistence_healthy is False


@pytest.mark.asyncio
async def test_worker_stderr_remains_connected_after_parent_stream_closes(tmp_path: Path) -> None:
    """The child keeps its inherited stderr target after process creation returns."""
    script = _worker_script(
        r"""
        emit("ready", 1)
        print("worker diagnostic", file=sys.stderr, flush=True)
        emit("terminal", 2, terminal_state("completed"), "completed")
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script)

    monitor = await supervisor.start(job=job, company_url="https://example.com", mode="full")
    await asyncio.wait_for(monitor, timeout=3.0)

    log_path = tmp_path / "workers" / job.job_id / "_worker.log"
    assert log_path.read_text(encoding="utf-8") == "worker diagnostic\n"


@pytest.mark.asyncio
async def test_worker_environment_strips_controller_secrets_but_retains_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker gets provider/runtime configuration, not controller credentials."""
    monkeypatch.setenv("MCP_JWT_SECRET", "controller-only")
    monkeypatch.setenv("PRIMR_MCP_APPROVAL_TOKEN_SECRET", "controller-only")
    monkeypatch.setenv("PRIMR_CONTROL_PLANE_PRIVATE", "controller-only")
    monkeypatch.setenv("XAI_API_KEY", "provider-visible")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "cloud-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ci-secret")
    path_value = os.environ.get("PATH", "")

    script = _worker_script(
        r"""
        emit("ready", 1)
        observed = {
            "mcp_jwt": os.environ.get("MCP_JWT_SECRET"),
            "approval": os.environ.get("PRIMR_MCP_APPROVAL_TOKEN_SECRET"),
            "control_plane": os.environ.get("PRIMR_CONTROL_PLANE_PRIVATE"),
            "provider": os.environ.get("XAI_API_KEY"),
            "aws": os.environ.get("AWS_SECRET_ACCESS_KEY"),
            "github": os.environ.get("GITHUB_TOKEN"),
            "path": os.environ.get("PATH"),
        }
        state = terminal_state("completed")
        state["error_message"] = json.dumps(observed, sort_keys=True)
        emit("terminal", 2, state, "completed")
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script)

    monitor = await supervisor.start(job=job, company_url="https://example.com", mode="full")
    await asyncio.wait_for(monitor, timeout=3.0)

    completed = store.get(job.job_id)
    assert completed is not None
    assert completed.current_stage == ResearchStage.COMPLETED
    observed = json.loads(completed.error_message or "{}")
    assert observed == {
        "approval": None,
        "aws": None,
        "control_plane": None,
        "github": None,
        "mcp_jwt": None,
        "path": path_value,
        "provider": "provider-visible",
    }


@pytest.mark.asyncio
async def test_successful_terminal_snapshot_applies_only_after_worker_exit(tmp_path: Path) -> None:
    """A terminal event is provisional until the owned process has exited."""
    terminal_seen = tmp_path / "terminal-seen"
    release = tmp_path / "release-worker"
    script = _worker_script(
        r"""
        emit("ready", 1)
        emit("terminal", 2, terminal_state("completed"), "completed")
        root = pathlib.Path(start["destination"])
        (root / "terminal-seen").write_text("seen", encoding="utf-8")
        while not (root / "release-worker").exists():
            time.sleep(0.01)
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script)
    monitor = None

    try:
        monitor = await supervisor.start(
            job=job,
            company_url="https://example.com",
            mode="full",
            destination=str(tmp_path),
        )
        await _wait_for_path(terminal_seen, expected="seen")
        assert not monitor.done()
        assert not store.get(job.job_id).is_terminal()

        release.write_text("release", encoding="utf-8")
        await asyncio.wait_for(monitor, timeout=3.0)
        assert store.get(job.job_id).current_stage == ResearchStage.COMPLETED
    finally:
        release.touch(exist_ok=True)
        await _cleanup(supervisor, monitor)


@pytest.mark.asyncio
async def test_cooperative_cancellation_waits_for_exit_before_cancelled(tmp_path: Path) -> None:
    """A cooperative request remains nonterminal until the worker exits."""
    cancel_seen = tmp_path / "cancel-seen"
    release = tmp_path / "release-worker"
    script = _worker_script(
        r"""
        emit("ready", 1)
        cancel = json.loads(sys.stdin.readline())
        root = pathlib.Path(start["destination"])
        (root / "cancel-seen").write_text(cancel["reason"], encoding="utf-8")
        while not (root / "release-worker").exists():
            time.sleep(0.01)
        emit(
            "terminal",
            2,
            terminal_state(
                "cancelled",
                error_type="user_cancelled",
                error_message="Worker acknowledged cancellation",
            ),
            "user_cancelled",
        )
        raise SystemExit(130)
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script, cooperative_timeout=2.0)
    monitor = None

    try:
        monitor = await supervisor.start(
            job=job,
            company_url="https://example.com",
            mode="full",
            destination=str(tmp_path),
        )
        cancellation = asyncio.create_task(supervisor.cancel(job.job_id))
        assert await _wait_for_path(cancel_seen, expected="user_cancelled") == (
            "user_cancelled"
        )
        assert not cancellation.done()
        assert not store.get(job.job_id).is_terminal()

        release.write_text("release", encoding="utf-8")
        outcome = await asyncio.wait_for(cancellation, timeout=3.0)
        await asyncio.wait_for(monitor, timeout=3.0)

        assert outcome.status == "cancelled"
        assert outcome.worker_exit_confirmed is True
        assert outcome.termination_method == "cooperative"
        assert store.get(job.job_id).current_stage == ResearchStage.CANCELLED
        manifest_path = tmp_path / "workers" / job.job_id / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["execution"]["status"] == "cancelled"
        assert manifest["termination"] == {
            "worker_exit_confirmed": True,
            "worker_return_code": 130,
            "reason": "user_cancelled",
            "method": "cooperative",
            "remote_provider_status": "unknown",
        }
        assert str(manifest_path) in store.get(job.job_id).output_paths
    finally:
        release.touch(exist_ok=True)
        await _cleanup(supervisor, monitor)


@pytest.mark.asyncio
async def test_completion_wins_cancel_race_and_remains_completed(tmp_path: Path) -> None:
    """A worker success observed during cancellation is not rewritten as cancelled."""
    script = _worker_script(
        r"""
        emit("ready", 1)
        json.loads(sys.stdin.readline())
        emit("terminal", 2, terminal_state("completed"), "completed")
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script, cooperative_timeout=1.0)
    monitor = await supervisor.start(job=job, company_url="https://example.com", mode="full")

    outcome = await asyncio.wait_for(supervisor.cancel(job.job_id), timeout=3.0)
    await asyncio.wait_for(monitor, timeout=3.0)

    assert outcome.status == "completed"
    assert outcome.worker_exit_confirmed is True
    assert store.get(job.job_id).current_stage == ResearchStage.COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_event", ["malformed", "wrong_sequence"])
async def test_invalid_worker_event_fails_job_with_protocol_error(
    tmp_path: Path,
    bad_event: str,
) -> None:
    """Malformed and out-of-sequence JSONL both fail closed."""
    body = (
        'emit("ready", 1); sys.stdout.write("not-json\\n"); sys.stdout.flush()'
        if bad_event == "malformed"
        else 'emit("ready", 1); emit("state", 3, job)'
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, _worker_script(body))

    monitor = await supervisor.start(job=job, company_url="https://example.com", mode="full")
    await asyncio.wait_for(monitor, timeout=3.0)

    failed = store.get(job.job_id)
    assert failed is not None
    assert failed.current_stage == ResearchStage.FAILED
    assert failed.error_type == "worker_protocol_error"
    assert failed.error_message is not None
    assert "Invalid worker event" in failed.error_message


@pytest.mark.asyncio
async def test_forced_escalation_confirms_exit_before_cancellation(tmp_path: Path) -> None:
    """An uncooperative child is killed and reaped before CANCELLED is visible."""
    ready_marker = tmp_path / "ready"
    script = _worker_script(
        r"""
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, signal.SIG_IGN)
        emit("ready", 1)
        pathlib.Path(start["destination"]).write_text("ready", encoding="utf-8")
        while True:
            time.sleep(1)
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(
        store,
        tmp_path,
        script,
        cooperative_timeout=0.05,
        terminate_timeout=0.05,
        kill_timeout=2.0,
    )
    monitor = None

    try:
        monitor = await supervisor.start(
            job=job,
            company_url="https://example.com",
            mode="full",
            destination=str(ready_marker),
        )
        await _wait_for_path(ready_marker)
        outcome = await asyncio.wait_for(supervisor.cancel(job.job_id), timeout=4.0)
        await asyncio.wait_for(monitor, timeout=3.0)

        assert outcome.status == "cancelled"
        assert outcome.worker_exit_confirmed is True
        if os.name == "nt":
            assert outcome.termination_method == "terminate_job_object"
        else:
            assert outcome.termination_method == "sigkill_group"
        assert store.get(job.job_id).current_stage == ResearchStage.CANCELLED
        assert job.job_id not in supervisor.running_job_ids
    finally:
        await _cleanup(supervisor, monitor)


@pytest.mark.asyncio
async def test_shutdown_reaps_worker_and_records_server_shutdown(tmp_path: Path) -> None:
    """Server shutdown is a failure cause, not a user cancellation."""
    ready_marker = tmp_path / "ready"
    script = _worker_script(
        r"""
        emit("ready", 1)
        pathlib.Path(start["destination"]).write_text("ready", encoding="utf-8")
        json.loads(sys.stdin.readline())
        emit(
            "terminal",
            2,
            terminal_state("cancelled", error_type="user_cancelled"),
            "server_shutdown",
        )
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script)
    monitor = None

    try:
        monitor = await supervisor.start(
            job=job,
            company_url="https://example.com",
            mode="full",
            destination=str(ready_marker),
        )
        await _wait_for_path(ready_marker)
        shutdown_complete = await asyncio.wait_for(supervisor.shutdown(timeout=0.6), timeout=4.0)
        await asyncio.wait_for(monitor, timeout=3.0)

        failed = store.get(job.job_id)
        assert failed is not None
        assert failed.current_stage == ResearchStage.FAILED
        assert failed.error_type == "server_shutdown"
        assert shutdown_complete is True
        assert job.job_id not in supervisor.running_job_ids
    finally:
        await _cleanup(supervisor, monitor)


@pytest.mark.asyncio
async def test_duplicate_start_for_same_job_is_rejected(tmp_path: Path) -> None:
    """The registry owns at most one child process for a job id."""
    script = _worker_script(
        r"""
        emit("ready", 1)
        json.loads(sys.stdin.readline())
        emit(
            "terminal",
            2,
            terminal_state("cancelled", error_type="user_cancelled"),
            "user_cancelled",
        )
        raise SystemExit(130)
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script, cooperative_timeout=1.0)
    monitor = None

    try:
        monitor = await supervisor.start(job=job, company_url="https://example.com", mode="full")
        with pytest.raises(RuntimeError, match="Worker already exists"):
            await supervisor.start(job=job, company_url="https://example.com", mode="full")
        assert supervisor.running_job_ids == (job.job_id,)

        outcome = await asyncio.wait_for(supervisor.cancel(job.job_id), timeout=3.0)
        await asyncio.wait_for(monitor, timeout=3.0)
        assert outcome.status == "cancelled"
    finally:
        await _cleanup(supervisor, monitor)


@pytest.mark.asyncio
async def test_concurrent_duplicate_start_is_reserved_during_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second start cannot cross the first start's subprocess await."""
    script = _worker_script(
        r"""
        emit("ready", 1)
        json.loads(sys.stdin.readline())
        emit(
            "terminal",
            2,
            terminal_state("cancelled", error_type="user_cancelled"),
            "user_cancelled",
        )
        raise SystemExit(130)
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script, cooperative_timeout=1.0)
    real_spawn = asyncio.create_subprocess_exec
    spawn_entered = asyncio.Event()
    release_spawn = asyncio.Event()

    async def delayed_spawn(*args, **kwargs):
        spawn_entered.set()
        await release_spawn.wait()
        return await real_spawn(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    first = asyncio.create_task(
        supervisor.start(job=job, company_url="https://example.com", mode="full")
    )
    await asyncio.wait_for(spawn_entered.wait(), timeout=1.0)
    duplicate = asyncio.create_task(
        supervisor.start(job=job, company_url="https://example.com", mode="full")
    )
    release_spawn.set()
    monitor = await asyncio.wait_for(first, timeout=3.0)

    try:
        with pytest.raises(RuntimeError, match="Worker already exists"):
            await asyncio.wait_for(duplicate, timeout=1.0)
        assert supervisor.running_job_ids == (job.job_id,)
        outcome = await supervisor.cancel(job.job_id, cooperative_timeout=1.0)
        assert outcome.status == "cancelled"
        await monitor
    finally:
        await _cleanup(supervisor, monitor)


@pytest.mark.asyncio
async def test_shutdown_during_spawn_prevents_worker_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown waits for the spawn reservation and tears its child down."""
    script = _worker_script("time.sleep(30)")
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script)
    real_spawn = asyncio.create_subprocess_exec
    spawn_entered = asyncio.Event()
    release_spawn = asyncio.Event()

    async def delayed_spawn(*args, **kwargs):
        spawn_entered.set()
        await release_spawn.wait()
        return await real_spawn(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    start_task = asyncio.create_task(
        supervisor.start(job=job, company_url="https://example.com", mode="full")
    )
    await asyncio.wait_for(spawn_entered.wait(), timeout=1.0)
    shutdown_task = asyncio.create_task(supervisor.shutdown(timeout=2.0))
    await asyncio.sleep(0)
    release_spawn.set()

    with pytest.raises(RuntimeError, match="shutdown"):
        await asyncio.wait_for(start_task, timeout=3.0)
    await asyncio.wait_for(shutdown_task, timeout=3.0)
    failed = store.get(job.job_id)
    assert failed is not None
    assert failed.current_stage == ResearchStage.FAILED
    assert failed.error_type == "server_shutdown"
    assert supervisor.running_job_ids == ()


@pytest.mark.asyncio
async def test_cancel_during_spawn_waits_for_retained_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation cannot return not_running from the subprocess await gap."""
    script = _worker_script(
        r"""
        emit("ready", 1)
        json.loads(sys.stdin.readline())
        emit(
            "terminal",
            2,
            terminal_state("cancelled", error_type="user_cancelled"),
            "user_cancelled",
        )
        raise SystemExit(130)
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script, cooperative_timeout=1.0)
    real_spawn = asyncio.create_subprocess_exec
    spawn_entered = asyncio.Event()
    release_spawn = asyncio.Event()

    async def delayed_spawn(*args, **kwargs):
        spawn_entered.set()
        await release_spawn.wait()
        return await real_spawn(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    start_task = asyncio.create_task(
        supervisor.start(job=job, company_url="https://example.com", mode="full")
    )
    await asyncio.wait_for(spawn_entered.wait(), timeout=1.0)
    cancel_task = asyncio.create_task(supervisor.cancel(job.job_id))
    release_spawn.set()
    monitor = await asyncio.wait_for(start_task, timeout=3.0)

    try:
        outcome = await asyncio.wait_for(cancel_task, timeout=3.0)
        assert outcome.status == "cancelled"
        assert outcome.worker_exit_confirmed is True
        await monitor
    finally:
        await _cleanup(supervisor, monitor)


@pytest.mark.asyncio
async def test_cancelling_start_during_spawn_reaps_created_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shielded spawn ownership survives cancellation of its request task."""
    script = _worker_script("time.sleep(30)")
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script)
    real_spawn = asyncio.create_subprocess_exec
    spawn_entered = asyncio.Event()
    release_spawn = asyncio.Event()

    async def delayed_spawn(*args, **kwargs):
        spawn_entered.set()
        await release_spawn.wait()
        return await real_spawn(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    start_task = asyncio.create_task(
        supervisor.start(job=job, company_url="https://example.com", mode="full")
    )
    await asyncio.wait_for(spawn_entered.wait(), timeout=1.0)
    start_task.cancel()
    release_spawn.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(start_task, timeout=3.0)
    failed = store.get(job.job_id)
    assert failed is not None
    assert failed.current_stage == ResearchStage.FAILED
    assert failed.error_type == "worker_protocol_error"
    assert supervisor.running_job_ids == ()


@pytest.mark.asyncio
async def test_cancelling_start_while_waiting_for_ready_reaps_worker(tmp_path: Path) -> None:
    """Request cancellation during readiness cannot orphan a child."""
    marker = tmp_path / "start-seen"
    script = _worker_script(
        r"""
        pathlib.Path(start["destination"]).write_text("seen", encoding="utf-8")
        time.sleep(30)
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script, kill_timeout=2.0)
    start_task = asyncio.create_task(
        supervisor.start(
            job=job,
            company_url="https://example.com",
            mode="full",
            destination=str(marker),
        )
    )
    await _wait_for_path(marker)
    start_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(start_task, timeout=3.0)
    failed = store.get(job.job_id)
    assert failed is not None
    assert failed.current_stage == ResearchStage.FAILED
    assert failed.error_type == "worker_protocol_error"
    assert supervisor.running_job_ids == ()


@pytest.mark.asyncio
async def test_signal_failure_does_not_claim_worker_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed escalation remains nonterminal and can be retried."""
    script = _worker_script(
        r"""
        emit("ready", 1)
        json.loads(sys.stdin.readline())
        time.sleep(30)
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(
        store,
        tmp_path,
        script,
        cooperative_timeout=0.02,
        terminate_timeout=0.02,
        kill_timeout=0.02,
    )
    monitor = await supervisor.start(job=job, company_url="https://example.com", mode="full")
    original_signal = supervisor._signal_process_tree

    async def failed_signal(_handle, *, force):
        return "signal_failed"

    monkeypatch.setattr(supervisor, "_signal_process_tree", failed_signal)
    outcome = await supervisor.cancel(job.job_id)
    assert outcome.status == "cancellation_failed"
    assert outcome.worker_exit_confirmed is False
    assert not store.get(job.job_id).is_terminal()

    monkeypatch.setattr(supervisor, "_signal_process_tree", original_signal)
    try:
        retry = await supervisor.cancel(
            job.job_id,
            cooperative_timeout=0.01,
            terminate_timeout=0.01,
            kill_timeout=2.0,
        )
        assert retry.status == "cancelled"
        assert retry.worker_exit_confirmed is True
        await monitor
    finally:
        await _cleanup(supervisor, monitor)


@pytest.mark.asyncio
async def test_unsolicited_cancelled_terminal_is_protocol_failure(tmp_path: Path) -> None:
    """A worker cannot cancel itself without matching parent intent."""
    script = _worker_script(
        r"""
        emit("ready", 1)
        emit(
            "terminal",
            2,
            terminal_state("cancelled", error_type="user_cancelled"),
            "user_cancelled",
        )
        raise SystemExit(130)
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script)
    monitor = await supervisor.start(job=job, company_url="https://example.com", mode="full")
    await asyncio.wait_for(monitor, timeout=3.0)

    failed = store.get(job.job_id)
    assert failed is not None
    assert failed.current_stage == ResearchStage.FAILED
    assert failed.error_type == "worker_protocol_error"


@pytest.mark.asyncio
async def test_cleanup_failure_retains_ownership_until_retry_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parent exit alone cannot release a possibly live descendant tree."""
    script = _worker_script(
        r"""
        emit("ready", 1)
        emit("terminal", 2, terminal_state("completed"), "completed")
        """
    )
    store, job = _store_and_job(tmp_path)
    supervisor = _supervisor(store, tmp_path, script)
    cleanup_attempted = asyncio.Event()
    permit_cleanup = asyncio.Event()
    original_cleanup = job_process_mod.cleanup_process_tree

    async def controlled_cleanup(process, windows_job):
        cleanup_attempted.set()
        if not permit_cleanup.is_set():
            return windows_job, "Worker process-tree cleanup failed: retained for retry"
        return await original_cleanup(process, windows_job)

    monkeypatch.setattr(job_process_mod, "cleanup_process_tree", controlled_cleanup)
    monkeypatch.setattr(job_process_mod, "TREE_CLEANUP_RETRY_INTERVAL", 0.01)
    monitor = await supervisor.start(job=job, company_url="https://example.com", mode="full")
    await asyncio.wait_for(cleanup_attempted.wait(), timeout=3.0)
    await asyncio.sleep(0)

    assert supervisor.running_job_ids == (job.job_id,)
    assert not store.get(job.job_id).is_terminal()

    shutdown_complete = await supervisor.shutdown(timeout=0.03)
    assert shutdown_complete is False
    assert supervisor.running_job_ids == (job.job_id,)

    permit_cleanup.set()
    await asyncio.wait_for(monitor, timeout=3.0)
    failed = store.get(job.job_id)
    assert failed is not None
    assert failed.current_stage == ResearchStage.FAILED
    assert failed.error_type == "worker_protocol_error"
    assert "cleanup failed" in (failed.error_message or "")
    assert supervisor.running_job_ids == ()
