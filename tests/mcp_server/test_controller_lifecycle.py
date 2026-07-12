"""Shared controller lifecycle contracts for MCP and A2A transports."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.types import ResearchStage


@pytest.fixture
def server(tmp_path):
    return create_mcp_server(
        journal_path=str(tmp_path / "journal.json"),
        audit_log_path=str(tmp_path / "audit.jsonl"),
        skip_background_tasks=True,
    )


@pytest.mark.asyncio
async def test_nested_controller_lifecycle_acquires_and_releases_once(server, monkeypatch):
    lease = MagicMock()
    monkeypatch.setattr(server, "_controller_lease", lease)
    reload_journal = MagicMock()
    monkeypatch.setattr(server.job_store, "reload_from_journal", reload_journal)
    reconcile = MagicMock(return_value=None)
    monkeypatch.setattr(server.job_store, "reconcile_interrupted_job", reconcile)
    shutdown = AsyncMock(return_value=True)
    monkeypatch.setattr(server, "_graceful_shutdown", shutdown)

    async with server.controller_lifecycle(), server.controller_lifecycle():
        assert server._controller_lifecycle_users == 2
        lease.acquire.assert_called_once_with()
        shutdown.assert_not_awaited()

    reload_journal.assert_called_once_with()
    reconcile.assert_called_once_with()
    shutdown.assert_awaited_once_with()
    lease.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_transport_failure_shuts_workers_before_lease_release(server, monkeypatch):
    order = []
    lease = MagicMock()
    lease.acquire.side_effect = lambda: order.append("acquire")
    lease.close.side_effect = lambda: order.append("close")
    monkeypatch.setattr(server, "_controller_lease", lease)
    monkeypatch.setattr(server.job_store, "reconcile_interrupted_job", MagicMock(return_value=None))

    async def fail_transport():
        order.append("transport")
        raise RuntimeError("transport failed")

    async def shutdown():
        order.append("shutdown")
        return True

    monkeypatch.setattr(server, "run_stdio", fail_transport)
    monkeypatch.setattr(server, "_graceful_shutdown", shutdown)

    with pytest.raises(RuntimeError, match="transport failed"):
        await server.run()
    assert order == ["acquire", "transport", "shutdown", "close"]


@pytest.mark.asyncio
async def test_unreaped_worker_retains_controller_lease(server, monkeypatch):
    lease = MagicMock()
    lease.acquired = False
    lease.acquire.side_effect = lambda: setattr(lease, "acquired", True)
    monkeypatch.setattr(server, "_controller_lease", lease)
    monkeypatch.setattr(server.job_store, "reconcile_interrupted_job", MagicMock(return_value=None))
    monkeypatch.setattr(server, "_graceful_shutdown", AsyncMock(return_value=False))
    monkeypatch.setattr(
        type(server.job_supervisor),
        "running_job_ids",
        property(lambda _self: ("job-unreaped",)),
    )

    with pytest.raises(RuntimeError, match="retaining the journal lease"):
        async with server.controller_lifecycle():
            pass
    lease.acquire.assert_called_once_with()
    lease.close.assert_not_called()

    with pytest.raises(RuntimeError, match="Prior controller shutdown is incomplete"):
        async with server.controller_lifecycle():
            pass


@pytest.mark.asyncio
async def test_controller_reloads_journal_after_acquiring_lease(tmp_path):
    """A waiting controller cannot reconcile a stale in-memory snapshot."""
    journal_path = str(tmp_path / "shared-journal.json")
    first = create_mcp_server(
        journal_path=journal_path,
        audit_log_path=str(tmp_path / "first-audit.jsonl"),
        skip_background_tasks=True,
    )

    async with first.controller_lifecycle():
        job = first.job_store.create("Fresh Corp", "full")
        second = create_mcp_server(
            journal_path=journal_path,
            audit_log_path=str(tmp_path / "second-audit.jsonl"),
            skip_background_tasks=True,
        )
        stale = second.job_store.get(job.job_id)
        assert stale is not None
        assert not stale.is_terminal()

        job.advance_stage(ResearchStage.COMPLETED)
        first.job_store.update(job)

    async with second.controller_lifecycle():
        current = second.job_store.get(job.job_id)
        assert current is not None
        assert current.current_stage == ResearchStage.COMPLETED
        assert current.error_type is None
