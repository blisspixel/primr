"""
Additional coverage-focused tests for primr.core.ai_strategy.

Targets branches not exercised by test_ai_strategy.py or
test_ai_strategy_internals_coverage.py:

- generate_ai_strategy with an already-resolved Platform enum (skips
  the str->enum conversion) plus usage-tracking failure tolerance.
- _validate_preflight output-directory-not-writable branch.
- _gather_context vendor-research generation branches (force-refresh,
  get-or-generate, agnostic fallback file).
- _poll_for_completion completed / failed / still-running outcomes.
- _execute_strategy_research polling fallback + interaction-id capture.
- _process_citations no-url citation line.
- _save_strategy_outputs failure tolerance (md write blows up).

All external I/O (deep research client, vendor research, DOCX, usage
tracker, registry) is mocked. No network or real API calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.core.ai_strategy import (
    AIStrategyConfig,
    Platform,
    _gather_context,
    _poll_for_completion,
    _process_citations,
    _save_strategy_outputs,
    _validate_preflight,
    generate_ai_strategy,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# generate_ai_strategy: enum platform path + usage tracking tolerance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_with_enum_platform_skips_conversion(tmp_path: Path, monkeypatch):
    """Passing a Platform enum (not str) takes the no-conversion branch (line 241)."""
    monkeypatch.setattr("primr.core.ai_strategy.OUTPUT_DIR", str(tmp_path))

    with (
        patch("primr.core.ai_strategy._validate_preflight", return_value=[]),
        patch(
            "primr.core.ai_strategy._gather_context",
            new=AsyncMock(return_value=([], [])),
        ),
        patch("primr.core.ai_strategy.build_ai_strategy_prompt", return_value="P"),
        patch(
            "primr.core.ai_strategy._execute_strategy_research",
            new=AsyncMock(return_value="# content"),
        ),
        patch(
            "primr.core.ai_strategy._save_strategy_outputs",
            return_value={"docx": str(tmp_path / "s.docx"), "md": None, "txt": None},
        ),
    ):
        # Pass the enum directly, not a string.
        result = await generate_ai_strategy(company_name="Acme", platform=Platform.PRIVATE)

    assert result.success is True


@pytest.mark.asyncio
async def test_generate_tolerates_usage_tracking_failure(tmp_path: Path, monkeypatch):
    """A raising usage tracker must not fail the strategy run (lines 319-321)."""
    monkeypatch.setattr("primr.core.ai_strategy.OUTPUT_DIR", str(tmp_path))

    fake_tracker_mod = MagicMock()
    fake_tracker_mod.get_usage_tracker.side_effect = RuntimeError("tracker down")

    with (
        patch("primr.core.ai_strategy._validate_preflight", return_value=[]),
        patch(
            "primr.core.ai_strategy._gather_context",
            new=AsyncMock(return_value=([], [])),
        ),
        patch("primr.core.ai_strategy.build_ai_strategy_prompt", return_value="P"),
        patch(
            "primr.core.ai_strategy._execute_strategy_research",
            new=AsyncMock(return_value="# content"),
        ),
        patch(
            "primr.core.ai_strategy._save_strategy_outputs",
            return_value={"docx": str(tmp_path / "s.docx"), "md": None, "txt": None},
        ),
        patch.dict("sys.modules", {"primr.utils.usage_tracker": fake_tracker_mod}),
    ):
        result = await generate_ai_strategy(company_name="Acme", platform="azure")

    assert result.success is True


@pytest.mark.asyncio
async def test_generate_records_usage_on_success(tmp_path: Path, monkeypatch):
    """Successful run records usage via the tracker (covers happy tracking path)."""
    monkeypatch.setattr("primr.core.ai_strategy.OUTPUT_DIR", str(tmp_path))

    tracker = MagicMock()
    fake_tracker_mod = MagicMock()
    fake_tracker_mod.get_usage_tracker.return_value = tracker

    with (
        patch("primr.core.ai_strategy._validate_preflight", return_value=[]),
        patch(
            "primr.core.ai_strategy._gather_context",
            new=AsyncMock(return_value=([], [])),
        ),
        patch("primr.core.ai_strategy.build_ai_strategy_prompt", return_value="P"),
        patch(
            "primr.core.ai_strategy._execute_strategy_research",
            new=AsyncMock(return_value="# content"),
        ),
        patch(
            "primr.core.ai_strategy._save_strategy_outputs",
            return_value={"docx": str(tmp_path / "s.docx"), "md": None, "txt": None},
        ),
        patch.dict("sys.modules", {"primr.utils.usage_tracker": fake_tracker_mod}),
    ):
        result = await generate_ai_strategy(company_name="Acme", platform="aws")

    assert result.success is True
    assert tracker.record_usage.called
    kwargs = tracker.record_usage.call_args.kwargs
    assert kwargs["mode"] == "standalone_ai_strategy_aws"
    assert kwargs["company"] == "Acme"
    from primr.config.models import DEEP_RESEARCH_COST

    assert kwargs["deep_research_cost"] == DEEP_RESEARCH_COST.standard_task_cost
    tracker.save.assert_called_once_with()


# ---------------------------------------------------------------------------
# _validate_preflight: output dir not writable
# ---------------------------------------------------------------------------


def test_preflight_output_dir_not_writable(monkeypatch):
    """An unwritable output dir surfaces as a preflight error (lines 377-378)."""
    fake_settings = MagicMock()
    fake_settings.api.gemini_key = "fake"
    fake_settings_mod = MagicMock()
    fake_settings_mod.get_settings.return_value = fake_settings

    config = AIStrategyConfig(company_name="Acme", platform=Platform.AZURE)

    with (
        patch.dict("sys.modules", {"primr.config.settings": fake_settings_mod}),
        patch("pathlib.Path.mkdir", side_effect=OSError("read-only fs")),
    ):
        errors = _validate_preflight(config)

    assert any("not writable" in e for e in errors)


def test_preflight_passes_with_key_and_writable(tmp_path, monkeypatch):
    """All preconditions met -> no errors."""
    monkeypatch.setattr("primr.core.ai_strategy.OUTPUT_DIR", str(tmp_path))
    fake_settings = MagicMock()
    fake_settings.api.gemini_key = "fake"
    fake_settings_mod = MagicMock()
    fake_settings_mod.get_settings.return_value = fake_settings

    config = AIStrategyConfig(company_name="Acme", platform=Platform.AZURE)
    with patch.dict("sys.modules", {"primr.config.settings": fake_settings_mod}):
        errors = _validate_preflight(config)

    assert errors == []


# ---------------------------------------------------------------------------
# _gather_context: vendor-research generation branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gather_context_force_refresh_vendor(tmp_path: Path):
    """--refresh-vendor-research is freshness-aware: it reuses a fresh cache and
    regenerates only stale/missing docs, so it never forces a paid task."""
    generated = tmp_path / "azure.txt"
    generated.write_text("vendor", encoding="utf-8")

    registry = MagicMock()
    registry.get_context_files.return_value = []
    fake_registry_mod = MagicMock()
    fake_registry_mod.get_registry.return_value = registry

    result = MagicMock()
    result.paths = [generated]
    fake_vendor_mod = MagicMock()
    fake_vendor_mod.generate_vendor_research = AsyncMock()
    fake_vendor_mod.get_or_generate_vendor_research = AsyncMock(return_value=result)
    fake_vendor_mod.get_vendor_research_path.return_value = tmp_path / "missing-agnostic.txt"

    config = AIStrategyConfig(
        company_name="Acme",
        platform=Platform.AZURE,
        force_refresh_vendor=True,
    )

    with patch.dict(
        "sys.modules",
        {
            "primr.prompts.registry": fake_registry_mod,
            "primr.core.vendor_research": fake_vendor_mod,
        },
    ):
        context_files, vendor_paths = await _gather_context(config)

    assert str(generated) not in context_files
    assert str(generated) in vendor_paths
    # Freshness-aware path, not an unconditional force-generate.
    assert not fake_vendor_mod.generate_vendor_research.called
    assert fake_vendor_mod.get_or_generate_vendor_research.called
    call = fake_vendor_mod.get_or_generate_vendor_research.call_args
    assert call.kwargs["force_refresh"] is False
    assert call.kwargs["allow_auto_refresh"] is True


@pytest.mark.asyncio
async def test_gather_context_get_or_generate_vendor(tmp_path: Path):
    """Non-force path uses get_or_generate_vendor_research (lines 433-445)."""
    vendor_file = tmp_path / "aws.txt"
    vendor_file.write_text("vendor", encoding="utf-8")

    registry = MagicMock()
    registry.get_context_files.return_value = []
    fake_registry_mod = MagicMock()
    fake_registry_mod.get_registry.return_value = registry

    research_result = MagicMock()
    research_result.paths = [vendor_file]

    fake_vendor_mod = MagicMock()
    fake_vendor_mod.get_or_generate_vendor_research = AsyncMock(return_value=research_result)

    config = AIStrategyConfig(company_name="Acme", platform=Platform.AWS)

    with patch.dict(
        "sys.modules",
        {
            "primr.prompts.registry": fake_registry_mod,
            "primr.core.vendor_research": fake_vendor_mod,
        },
    ):
        context_files, vendor_paths = await _gather_context(config)

    assert str(vendor_file) not in context_files
    assert str(vendor_file) in vendor_paths
    fake_vendor_mod.get_or_generate_vendor_research.assert_awaited_once_with(
        "aws",
        force_refresh=False,
        on_progress=None,
        allow_auto_refresh=None,
    )


@pytest.mark.asyncio
async def test_gather_context_agnostic_appends_agnostic_file(tmp_path: Path):
    """AGNOSTIC platform appends the canonical cached research file."""
    agnostic_file = tmp_path / "vendor-research-agnostic.txt"
    agnostic_file.write_text("agnostic body", encoding="utf-8")

    registry = MagicMock()
    registry.get_context_files.return_value = []
    fake_registry_mod = MagicMock()
    fake_registry_mod.get_registry.return_value = registry

    # AGNOSTIC skips vendor generation entirely.
    fake_vendor_mod = MagicMock()
    fake_vendor_mod.get_vendor_research_path.return_value = agnostic_file

    config = AIStrategyConfig(company_name="Acme", platform=Platform.AGNOSTIC)

    with patch.dict(
        "sys.modules",
        {
            "primr.prompts.registry": fake_registry_mod,
            "primr.core.vendor_research": fake_vendor_mod,
        },
    ):
        context_files, vendor_paths = await _gather_context(config)

    assert str(agnostic_file) not in context_files
    assert str(agnostic_file) in vendor_paths
    fake_vendor_mod.get_vendor_research_path.assert_called_once_with("agnostic")


# ---------------------------------------------------------------------------
# _poll_for_completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_for_completion_completed():
    fake_dr = MagicMock()
    client = MagicMock()
    client.check_job.return_value = {"status": "completed", "content": "DONE"}
    on_recovery_ready = MagicMock()

    with (
        patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr}),
        patch("primr.core.ai_strategy.asyncio.sleep", new=AsyncMock()),
    ):
        out = await _poll_for_completion(
            client,
            "iid-1",
            "prompt",
            poll_interval=0,
            on_recovery_ready=on_recovery_ready,
        )

    assert out == "DONE"
    assert fake_dr.save_pending_job.called
    on_recovery_ready.assert_called_once_with("iid-1")


@pytest.mark.asyncio
async def test_poll_for_completion_completed_no_content():
    fake_dr = MagicMock()
    client = MagicMock()
    client.check_job.return_value = {"status": "completed", "content": ""}

    with (
        patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr}),
        patch("primr.core.ai_strategy.asyncio.sleep", new=AsyncMock()),
    ):
        out = await _poll_for_completion(client, "iid-1", "prompt", poll_interval=0)

    assert out is None


@pytest.mark.asyncio
async def test_poll_for_completion_failed():
    fake_dr = MagicMock()
    client = MagicMock()
    client.check_job.return_value = {"status": "failed", "error": "boom"}

    with (
        patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr}),
        patch("primr.core.ai_strategy.asyncio.sleep", new=AsyncMock()),
    ):
        out = await _poll_for_completion(client, "iid-1", "prompt", poll_interval=0)

    assert out is None


@pytest.mark.asyncio
async def test_poll_for_completion_times_out():
    """Unknown status loops until max_poll_time then returns None (lines 491-496)."""
    fake_dr = MagicMock()
    client = MagicMock()
    client.check_job.return_value = {"status": "weird"}

    # Drive a controllable clock so the while-loop exits deterministically.
    times = iter([0.0, 0.0, 100.0, 100.0, 100.0])

    class _Loop:
        def time(self):
            return next(times)

    with (
        patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr}),
        patch("primr.core.ai_strategy.asyncio.sleep", new=AsyncMock()),
        patch("primr.core.ai_strategy.asyncio.get_running_loop", return_value=_Loop()),
    ):
        out = await _poll_for_completion(
            client, "iid-1", "prompt", max_poll_time=10, poll_interval=0
        )

    assert out is None


# ---------------------------------------------------------------------------
# _execute_strategy_research: polling fallback paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_research_falls_back_to_polling():
    """Non-completed result with interaction_id triggers _poll_for_completion."""
    from primr.core import ai_strategy as mod

    class _Status:
        COMPLETED = "completed"

    incomplete = MagicMock()
    incomplete.status = "in_progress"
    incomplete.content = ""
    incomplete.interaction_id = "iid-99"

    client = MagicMock()
    client.research = AsyncMock(return_value=incomplete)

    fake_dr = MagicMock()
    fake_dr.get_deep_research_client.return_value = client
    fake_dr.ResearchStatus = _Status

    with (
        patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr}),
        patch.object(
            mod, "_poll_for_completion", new=AsyncMock(return_value="POLLED")
        ) as mock_poll,
    ):
        out = await mod._execute_strategy_research(prompt="P", context_files=[], timeout=10)

    assert out == "POLLED"
    assert mock_poll.await_args.args[1] == "iid-99"


@pytest.mark.asyncio
async def test_execute_research_no_interaction_id_returns_none():
    """Failure with no interaction id logs error and returns None (lines 540-542)."""
    from primr.core import ai_strategy as mod

    class _Status:
        COMPLETED = "completed"

    failed = MagicMock()
    failed.status = "failed"
    failed.content = ""
    failed.interaction_id = None
    failed.error = "no good"

    client = MagicMock()
    client.research = AsyncMock(return_value=failed)

    fake_dr = MagicMock()
    fake_dr.get_deep_research_client.return_value = client
    fake_dr.ResearchStatus = _Status

    with patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr}):
        out = await mod._execute_strategy_research(prompt="P", context_files=[], timeout=10)

    assert out is None


@pytest.mark.asyncio
async def test_execute_research_exception_saves_pending_job():
    """Exception with captured interaction_id saves a pending job (lines 547-549)."""
    from primr.core import ai_strategy as mod

    class _Status:
        COMPLETED = "completed"

    class _Progress:
        message = "working"
        interaction_id = "iid-from-progress"

    async def research(*args, **kwargs):
        # Fire the progress callback so interaction_id gets captured, then raise.
        kwargs["on_progress"](_Progress())
        raise RuntimeError("explode")

    client = MagicMock()
    client.research = research

    fake_dr = MagicMock()
    fake_dr.get_deep_research_client.return_value = client
    fake_dr.ResearchStatus = _Status

    captured = {}

    def save_pending_job(iid, kind, snippet):
        captured["iid"] = iid

    fake_dr.save_pending_job = save_pending_job

    with patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr}):
        out = await mod._execute_strategy_research(prompt="P", context_files=[], timeout=10)

    assert out is None
    assert captured["iid"] == "iid-from-progress"


# ---------------------------------------------------------------------------
# _process_citations: citation with title but no URL
# ---------------------------------------------------------------------------


def test_process_citations_title_only_line():
    """A sources entry that resolves to no URL keeps the title only (lines 609-610)."""
    import primr.ai.deep_research as dr_mod

    content = "Body [cite: 1].\n\n**Sources:**\n1. [Some Title](https://example.com/page)\n"

    def fake_resolve(citations):
        # Strip the URL so the title-only branch runs.
        for c in citations:
            c["url"] = ""
        return citations

    with patch.object(dr_mod, "resolve_citation_urls_sync", side_effect=fake_resolve):
        out = _process_citations(content)

    assert "Some Title" in out
    assert "https://example.com/page" not in out


# ---------------------------------------------------------------------------
# _save_strategy_outputs: write failure tolerance
# ---------------------------------------------------------------------------


def test_save_strategy_outputs_write_failure(tmp_path, monkeypatch):
    """An exception while writing outputs is swallowed (lines 675-677)."""
    monkeypatch.setattr("primr.core.ai_strategy.OUTPUT_DIR", str(tmp_path))

    with (
        patch("primr.core.ai_strategy._process_citations", side_effect=lambda c: c),
        patch("pathlib.Path.open", side_effect=OSError("disk full")),
    ):
        outputs = _save_strategy_outputs("# Body", "Acme", Platform.AZURE)

    # Nothing was written; function returned gracefully.
    assert outputs["md"] is None
    assert outputs["docx"] is None
