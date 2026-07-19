"""Truthful, body-safe MCP controller readiness contracts."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from primr.mcp_server.job_store import JobJournalError
from primr.mcp_server.readiness import PersistencePreflightError
from primr.mcp_server.server import create_mcp_server


def _server(tmp_path: Path):
    return create_mcp_server(
        transport="streamable-http",
        journal_path=str(tmp_path / "state" / "journal.json"),
        audit_log_path=str(tmp_path / "audit" / "events.jsonl"),
        skip_background_tasks=True,
    )


def test_controller_is_not_ready_before_lifecycle(tmp_path):
    server = _server(tmp_path)

    ready, payload = server.readiness_snapshot()

    assert ready is False
    assert payload == {
        "status": "not_ready",
        "checks": {
            "controller": "not_ready",
            "journal": "not_ready",
            "audit": "not_ready",
            "output": "not_ready",
        },
    }


@pytest.mark.asyncio
async def test_controller_is_ready_only_inside_healthy_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    server = _server(tmp_path)
    server._graceful_shutdown = AsyncMock(return_value=True)

    async with server.controller_lifecycle():
        ready, payload = server.readiness_snapshot()
        assert ready is True
        assert payload["status"] == "ready"
        assert set(payload["checks"].values()) == {"ready"}

    ready, payload = server.readiness_snapshot()
    assert ready is False
    assert payload["status"] == "not_ready"


@pytest.mark.asyncio
async def test_audit_degradation_and_shutdown_make_readiness_fail(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    server = _server(tmp_path)
    server._graceful_shutdown = AsyncMock(return_value=True)

    async with server.controller_lifecycle():
        with patch.object(server.audit_log, "health_snapshot", return_value={"status": "degraded"}):
            ready, payload = server.readiness_snapshot()
        assert ready is False
        assert payload["checks"]["audit"] == "not_ready"
        assert payload["checks"]["controller"] == "ready"

        server._shutdown_event.set()
        ready, payload = server.readiness_snapshot()
        assert ready is False
        assert payload["checks"]["controller"] == "not_ready"


@pytest.mark.asyncio
async def test_corrupt_journal_blocks_activation_without_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    server = _server(tmp_path)
    journal = server.job_store.journal_path
    journal.parent.mkdir(parents=True)
    journal.write_text("{not-json", encoding="utf-8")

    with pytest.raises(JobJournalError, match="corrupt"):
        async with server.controller_lifecycle():
            pytest.fail("corrupt state must not activate")

    assert journal.read_text(encoding="utf-8") == "{not-json"
    assert server._controller_lease.acquired is False
    assert server.readiness_snapshot()[0] is False


@pytest.mark.asyncio
async def test_journal_is_not_read_before_leased_persistence_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    journal = tmp_path / "state" / "journal.json"
    journal.mkdir(parents=True)

    server = _server(tmp_path)

    assert server.job_store.get_active() is None
    with pytest.raises(PersistencePreflightError, match="journal"):
        async with server.controller_lifecycle():
            pytest.fail("a nonregular journal must not activate")

    assert journal.is_dir()
    assert server._controller_lease.acquired is False
    assert server.readiness_snapshot()[0] is False


@pytest.mark.asyncio
async def test_hard_linked_journal_is_rejected_before_read(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    target = tmp_path / "external-journal.json"
    target.write_text("{}", encoding="utf-8")
    journal = tmp_path / "state" / "journal.json"
    journal.parent.mkdir(parents=True)
    try:
        journal.hardlink_to(target)
    except OSError:
        pytest.skip("hard links are unavailable")

    server = _server(tmp_path)

    assert server.job_store.get_active() is None
    with pytest.raises(PersistencePreflightError, match="journal"):
        async with server.controller_lifecycle():
            pytest.fail("a hard-linked journal must not activate")
    assert target.read_text(encoding="utf-8") == "{}"


@pytest.mark.asyncio
async def test_symlinked_journal_is_rejected_before_read(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    target = tmp_path / "external-journal.json"
    target.write_text("{}", encoding="utf-8")
    journal = tmp_path / "state" / "journal.json"
    journal.parent.mkdir(parents=True)
    try:
        journal.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks are unavailable")

    server = _server(tmp_path)

    assert server.job_store.get_active() is None
    with pytest.raises(PersistencePreflightError, match="journal"):
        async with server.controller_lifecycle():
            pytest.fail("a symlinked journal must not activate")
    assert target.read_text(encoding="utf-8") == "{}"


@pytest.mark.asyncio
async def test_linked_journal_parent_is_rejected_before_lease_acquisition(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    target = tmp_path / "external-state"
    target.mkdir()
    linked_parent = tmp_path / "state"
    try:
        linked_parent.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory links are unavailable")
    server = _server(tmp_path)

    with (
        patch.object(server._controller_lease, "acquire") as acquire,
        pytest.raises(PersistencePreflightError, match="journal"),
    ):
        async with server.controller_lifecycle():
            pytest.fail("a linked journal parent must not activate")

    acquire.assert_not_called()
    assert not (target / server._controller_lease.lock_path.name).exists()


@pytest.mark.asyncio
async def test_persistence_failure_blocks_activation_and_releases_new_lease(tmp_path):
    server = _server(tmp_path)

    with (
        patch(
            "primr.mcp_server.server.probe_local_persistence",
            side_effect=PersistencePreflightError("output"),
        ),
        pytest.raises(PersistencePreflightError, match="output"),
    ):
        async with server.controller_lifecycle():
            pytest.fail("failed persistence must not activate")

    assert server._controller_lease.acquired is False
    assert server.readiness_snapshot()[0] is False


@pytest.mark.asyncio
async def test_actual_audit_sink_failure_blocks_activation(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    server = _server(tmp_path)

    with (
        patch.object(server.audit_log, "preflight", return_value=False),
        pytest.raises(PersistencePreflightError, match="audit"),
    ):
        async with server.controller_lifecycle():
            pytest.fail("an unavailable audit sink must not activate")

    assert server._controller_lease.acquired is False
    assert server.readiness_snapshot()[0] is False


@pytest.mark.asyncio
async def test_runtime_journal_failure_rolls_back_and_closes_readiness(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    server = _server(tmp_path)
    server._graceful_shutdown = AsyncMock(return_value=True)

    async with server.controller_lifecycle():
        with (
            patch("primr.mcp_server.job_store.atomic_write_text", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            server.job_store.create("Example", "full")

        assert server.job_store.get_active() is None
        ready, payload = server.readiness_snapshot()
        assert ready is False
        assert payload["checks"]["journal"] == "not_ready"


@pytest.mark.asyncio
async def test_closed_worker_admission_closes_controller_readiness(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    server = _server(tmp_path)
    server._graceful_shutdown = AsyncMock(return_value=True)

    async with server.controller_lifecycle():
        server.job_supervisor._shutdown_started = True
        ready, payload = server.readiness_snapshot()

    assert ready is False
    assert payload["checks"]["controller"] == "not_ready"


@pytest.mark.asyncio
async def test_shut_down_server_instance_cannot_reenter_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    server = _server(tmp_path)

    async with server.controller_lifecycle():
        assert server.readiness_snapshot()[0] is True

    with pytest.raises(RuntimeError, match="already shut down"):
        async with server.controller_lifecycle():
            pytest.fail("a closed supervisor must not advertise readiness again")


def test_readiness_payload_never_exposes_local_diagnostics(tmp_path):
    sentinel = "sensitive-readyz-sentinel"
    server = create_mcp_server(
        journal_path=str(tmp_path / sentinel / "journal.json"),
        audit_log_path=str(tmp_path / sentinel / "audit.jsonl"),
        skip_background_tasks=True,
    )

    _ready, payload = server.readiness_snapshot()
    rendered = str(payload)

    assert sentinel not in rendered
    assert set(payload) == {"status", "checks"}
    assert set(payload["checks"]) == {"controller", "journal", "audit", "output"}
