"""Focused tests for the supervised MCP child entry point."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from primr.mcp_server import job_worker
from primr.mcp_server.job_store import ResearchJobState
from primr.mcp_server.types import ResearchStage
from primr.mcp_server.worker_protocol import (
    build_cancel_command,
    build_start_command,
    decode_message,
    encode_message,
    validate_event,
)


class QueueControlStream:
    """Blocking binary stream that tests can feed without closing stdin early."""

    def __init__(self) -> None:
        self._lines: queue.Queue[bytes] = queue.Queue()

    def readline(self, _size: int = -1) -> bytes:
        return self._lines.get(timeout=5)

    def feed(self, line: bytes) -> None:
        self._lines.put(line)


def _start_command() -> dict:
    job = ResearchJobState(
        job_id="job-worker-123",
        company_name="Acme Corp",
        mode="full",
        start_time=datetime(2026, 7, 11, tzinfo=timezone.utc),
        owner_client_id="stdio",
        current_stage=ResearchStage.ACCEPTED,
    )
    return build_start_command(
        job=job.to_journal_dict(),
        company_url="https://acme.example",
        mode="full",
        platform="aws",
        skip_qa=True,
        verify=True,
        destination="output/acme",
        budget_usd=3.0,
    )


def _events(stream: io.BytesIO) -> list[dict]:
    events = [decode_message(line) for line in stream.getvalue().splitlines(keepends=True)]
    for expected_seq, event in enumerate(events, start=1):
        validate_event(event, "job-worker-123", expected_seq)
    return events


@pytest.mark.asyncio
async def test_worker_emits_ready_state_terminal_and_redirects_stdout(monkeypatch):
    seen: dict = {}

    class SuccessRunner:
        def __init__(self, mcp_server):
            self.mcp_server = mcp_server

        async def run_research(self, **kwargs):
            seen.update(kwargs)
            print("pipeline console chatter")
            job = kwargs["job"]
            job.output_paths = ["output/acme/report.md"]
            job.advance_stage(ResearchStage.COMPLETED)
            self.mcp_server.job_store.update(job)

        def request_cancel(self):
            raise AssertionError("successful worker should not be cancelled")

    monkeypatch.setattr(job_worker, "PipelineRunner", SuccessRunner)
    control = QueueControlStream()
    protocol = io.BytesIO()
    stderr = io.StringIO()

    result = await job_worker.run_worker(
        _start_command(),
        control_stream=control,  # type: ignore[arg-type]
        protocol_stream=protocol,
        stderr=stderr,
    )
    control.feed(b"")

    assert result == job_worker.EXIT_SUCCESS
    events = _events(protocol)
    assert [event["kind"] for event in events] == ["ready", "state", "terminal"]
    assert events[-1]["state"]["current_stage"] == "completed"
    assert events[-1]["exit_reason"] == "completed"
    assert "pipeline console chatter" in stderr.getvalue()
    assert b"pipeline console chatter" not in protocol.getvalue()
    assert seen["company_url"] == "https://acme.example"
    assert seen["mode"] == "full"
    assert seen["platform"] == "aws"
    assert seen["skip_qa"] is True
    assert seen["verify"] is True
    assert seen["destination"] == "output/acme"
    assert seen["budget_usd"] == 3.0


def test_store_adapter_never_publishes_terminal_job_as_progress():
    protocol = io.BytesIO()
    emitter = job_worker.WorkerEventEmitter(protocol, "job-worker-123")
    store = job_worker.WorkerJobStore(emitter)
    job = ResearchJobState.from_journal_dict(_start_command()["job"])
    job.advance_stage(ResearchStage.COMPLETED)

    store.update(job)

    assert protocol.getvalue() == b""
    assert store.latest_snapshot is not None
    assert store.latest_snapshot["current_stage"] == "completed"


@pytest.mark.asyncio
async def test_worker_preserves_pipeline_failure_state(monkeypatch):
    class FailedRunner:
        def __init__(self, mcp_server):
            self.mcp_server = mcp_server

        async def run_research(self, **kwargs):
            job = kwargs["job"]
            job.advance_stage(ResearchStage.FAILED)
            job.error_type = "research_failed"
            job.error_message = "Research failed"
            self.mcp_server.job_store.update(job)

        def request_cancel(self):
            return None

    monkeypatch.setattr(job_worker, "PipelineRunner", FailedRunner)
    control = QueueControlStream()
    protocol = io.BytesIO()

    result = await job_worker.run_worker(
        _start_command(),
        control_stream=control,  # type: ignore[arg-type]
        protocol_stream=protocol,
        stderr=io.StringIO(),
    )
    control.feed(b"")

    assert result == job_worker.EXIT_FAILURE
    terminal = _events(protocol)[-1]
    assert terminal["state"]["current_stage"] == "failed"
    assert terminal["exit_reason"] == "research_failed"


@pytest.mark.asyncio
async def test_unhandled_worker_error_is_generic_and_terminal(monkeypatch):
    class ExplodingRunner:
        def __init__(self, _mcp_server):
            pass

        async def run_research(self, **_kwargs):
            raise RuntimeError("provider-key-should-not-cross-protocol")

        def request_cancel(self):
            return None

    monkeypatch.setattr(job_worker, "PipelineRunner", ExplodingRunner)
    control = QueueControlStream()
    protocol = io.BytesIO()
    stderr = io.StringIO()

    result = await job_worker.run_worker(
        _start_command(),
        control_stream=control,  # type: ignore[arg-type]
        protocol_stream=protocol,
        stderr=stderr,
    )
    control.feed(b"")

    assert result == job_worker.EXIT_FAILURE
    terminal = _events(protocol)[-1]
    assert terminal["state"]["error_type"] == "worker_error"
    assert terminal["state"]["error_message"] == "Worker execution failed"
    assert "provider-key-should-not-cross-protocol" not in protocol.getvalue().decode()
    assert "provider-key-should-not-cross-protocol" not in stderr.getvalue()


@pytest.mark.asyncio
async def test_cancel_command_calls_runner_and_cancels_task_on_loop_thread(monkeypatch):
    loop_thread_id = threading.get_ident()
    cancel_thread_ids: list[int] = []

    class BlockingRunner:
        def __init__(self, _mcp_server):
            pass

        async def run_research(self, **_kwargs):
            await asyncio.Event().wait()

        def request_cancel(self):
            cancel_thread_ids.append(threading.get_ident())

    monkeypatch.setattr(job_worker, "PipelineRunner", BlockingRunner)
    control = QueueControlStream()
    control.feed(encode_message(build_cancel_command("job-worker-123")))
    protocol = io.BytesIO()

    result = await asyncio.wait_for(
        job_worker.run_worker(
            _start_command(),
            control_stream=control,  # type: ignore[arg-type]
            protocol_stream=protocol,
            stderr=io.StringIO(),
        ),
        timeout=2,
    )

    assert result == job_worker.EXIT_CANCELLED
    assert cancel_thread_ids == [loop_thread_id]
    terminal = _events(protocol)[-1]
    assert terminal["state"]["current_stage"] == "cancelled"
    assert terminal["exit_reason"] == "user_cancelled"


@pytest.mark.asyncio
async def test_parent_disconnect_is_a_cancellation_reason(monkeypatch):
    class BlockingRunner:
        def __init__(self, _mcp_server):
            pass

        async def run_research(self, **_kwargs):
            await asyncio.Event().wait()

        def request_cancel(self):
            return None

    monkeypatch.setattr(job_worker, "PipelineRunner", BlockingRunner)
    control = QueueControlStream()
    control.feed(b"")
    protocol = io.BytesIO()

    result = await asyncio.wait_for(
        job_worker.run_worker(
            _start_command(),
            control_stream=control,  # type: ignore[arg-type]
            protocol_stream=protocol,
            stderr=io.StringIO(),
        ),
        timeout=2,
    )

    assert result == job_worker.EXIT_CANCELLED
    assert _events(protocol)[-1]["exit_reason"] == "parent_disconnected"


@pytest.mark.asyncio
async def test_invalid_control_message_fails_closed_to_cancellation(monkeypatch):
    class BlockingRunner:
        def __init__(self, _mcp_server):
            pass

        async def run_research(self, **_kwargs):
            await asyncio.Event().wait()

        def request_cancel(self):
            return None

    monkeypatch.setattr(job_worker, "PipelineRunner", BlockingRunner)
    control = QueueControlStream()
    control.feed(b"not-json\n")
    protocol = io.BytesIO()
    stderr = io.StringIO()

    result = await asyncio.wait_for(
        job_worker.run_worker(
            _start_command(),
            control_stream=control,  # type: ignore[arg-type]
            protocol_stream=protocol,
            stderr=stderr,
        ),
        timeout=2,
    )

    assert result == job_worker.EXIT_CANCELLED
    assert _events(protocol)[-1]["exit_reason"] == "control_protocol_error"
    assert "control protocol error" in stderr.getvalue()


@pytest.mark.parametrize("line", [b"", b"not-json\n", b"{}\n"])
def test_main_rejects_invalid_start_without_emitting_protocol(line):
    stdout = io.BytesIO()
    stderr = io.StringIO()

    result = job_worker.main(stdin=io.BytesIO(line), stdout=stdout, stderr=stderr)

    assert result == job_worker.EXIT_PROTOCOL_ERROR
    assert stdout.getvalue() == b""
    assert "start protocol error" in stderr.getvalue()


def test_protocol_descriptor_is_private_from_native_writes_and_descendants():
    script = r"""
import os
import subprocess
import sys

from primr.mcp_server.job_worker import _isolate_standard_streams

_control, protocol = _isolate_standard_streams()
os.write(1, b"native worker chatter\n")
subprocess.Popen(
    [
        sys.executable,
        "-c",
        "import os,time;os.write(1,b'descendant chatter\\n');time.sleep(1.5)",
    ],
)
protocol.write(b"protocol-only\n")
protocol.flush()
protocol.close()
os._exit(0)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None

    assert process.stdout.readline() == b"protocol-only\n"
    remaining: queue.Queue[bytes] = queue.Queue()
    reader = threading.Thread(target=lambda: remaining.put(process.stdout.read()), daemon=True)
    reader.start()
    reader.join(timeout=0.75)

    assert not reader.is_alive(), "descendant retained the private protocol descriptor"
    assert remaining.get_nowait() == b""
    process.wait(timeout=1.0)

    # The descendant deliberately remains alive for 1.5 seconds. EOF on the
    # protocol pipe must arrive with the worker, not with that descendant.
    if process.stdin is not None:
        process.stdin.close()
    if process.stderr is not None:
        process.stderr.close()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows workers require a live Job Object")
def test_supervised_worker_lazy_config_cannot_restore_controller_secrets(tmp_path):
    config_dir = tmp_path / "config"
    project_dir = tmp_path / "project"
    config_dir.mkdir()
    project_dir.mkdir()
    (config_dir / ".env").write_text(
        "XAI_API_KEY=provider-key\n"
        "MCP_ADMIN_TOKENS=controller-secret\n"
        "AWS_SECRET_ACCESS_KEY=unrelated-cloud-secret\n",
        encoding="utf-8",
    )
    (project_dir / ".env").write_text(
        "MCP_JWT_SECRET=controller-secret\n"
        "PRIMR_MCP_APPROVAL_TOKEN_SECRET=controller-secret\n"
        "PRIMR_WORKER_JOB_OBJECT=forged-object\n"
        "GITHUB_TOKEN=unrelated-ci-secret\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment.update(
        {
            "PRIMR_CONFIG_DIR": str(config_dir),
            "PRIMR_SUPERVISED_WORKER": "1",
            "PRIMR_WORKER_JOB_ID": "env-isolation-test",
        }
    )
    for name in (
        "XAI_API_KEY",
        "MCP_ADMIN_TOKENS",
        "MCP_JWT_SECRET",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
    ):
        environment.pop(name, None)
    environment.pop("PRIMR_MCP_APPROVAL_TOKEN_SECRET", None)
    script = r"""
import json
import os

import primr.mcp_server.job_worker

payload = {
    "provider": os.environ.get("XAI_API_KEY"),
    "admin": os.environ.get("MCP_ADMIN_TOKENS"),
    "jwt": os.environ.get("MCP_JWT_SECRET"),
    "approval": os.environ.get("PRIMR_MCP_APPROVAL_TOKEN_SECRET"),
    "job_object": os.environ.get("PRIMR_WORKER_JOB_OBJECT"),
    "supervised": os.environ.get("PRIMR_SUPERVISED_WORKER"),
    "aws": os.environ.get("AWS_SECRET_ACCESS_KEY"),
    "github": os.environ.get("GITHUB_TOKEN"),
}
os.write(2, (json.dumps(payload, sort_keys=True) + "\n").encode())
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_dir,
        env=environment,
        capture_output=True,
        check=True,
        timeout=10,
    )

    assert json.loads(completed.stderr) == {
        "admin": None,
        "approval": None,
        "aws": None,
        "github": None,
        "job_object": None,
        "jwt": None,
        "provider": "provider-key",
        "supervised": None,
    }


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux process-group contract")
def test_controller_crash_kills_worker_descendant_group(tmp_path):
    worker_marker = tmp_path / "worker.pid"
    descendant_marker = tmp_path / "descendant.pid"
    worker_code = r"""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from primr.mcp_server import job_worker

class BlockingRunner:
    def __init__(self, _server):
        pass

    async def run_research(self, **_kwargs):
        descendant = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
        Path(os.environ["DESCENDANT_MARKER"]).write_text(str(descendant.pid), encoding="utf-8")
        await asyncio.Event().wait()

    def request_cancel(self):
        return None

job_worker.PipelineRunner = BlockingRunner
raise SystemExit(job_worker.main())
"""
    controller_code = f"""
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from primr.mcp_server.job_store import ResearchJobState
from primr.mcp_server.types import ResearchStage
from primr.mcp_server.worker_protocol import build_start_command, encode_message

job_id = "controller-crash-test"
environment = dict(os.environ)
environment.update({{
    "PRIMR_SUPERVISED_WORKER": "1",
    "PRIMR_WORKER_JOB_ID": job_id,
    "DESCENDANT_MARKER": {str(descendant_marker)!r},
}})
worker = subprocess.Popen(
    [sys.executable, "-c", {worker_code!r}],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    env=environment,
    start_new_session=True,
)
Path({str(worker_marker)!r}).write_text(str(worker.pid), encoding="utf-8")
job = ResearchJobState(
    job_id=job_id,
    company_name="Acme Corp",
    mode="full",
    start_time=datetime.now(timezone.utc),
    owner_client_id="client-1",
    current_stage=ResearchStage.ACCEPTED,
)
command = build_start_command(
    job=job.to_journal_dict(),
    company_url="https://acme.example",
    mode="full",
)
worker.stdin.write(encode_message(command))
worker.stdin.flush()
deadline = time.monotonic() + 10
while not Path({str(descendant_marker)!r}).exists():
    if worker.poll() is not None or time.monotonic() >= deadline:
        raise SystemExit(2)
    time.sleep(0.02)
os._exit(0)
"""
    controller = subprocess.Popen(
        [sys.executable, "-c", controller_code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    controller.wait(timeout=15)
    assert controller.returncode == 0
    worker_pid = int(worker_marker.read_text(encoding="utf-8"))
    descendant_pid = int(descendant_marker.read_text(encoding="utf-8"))

    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (
            _linux_pid_running(worker_pid) or _linux_pid_running(descendant_pid)
        ):
            time.sleep(0.05)

        assert not _linux_pid_running(worker_pid)
        assert not _linux_pid_running(descendant_pid)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(worker_pid, signal.SIGKILL)


def _linux_pid_running(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        fields = stat_path.read_text(encoding="utf-8").split()
    except OSError:
        return False
    return len(fields) > 2 and fields[2] != "Z"
