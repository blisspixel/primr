"""
Coverage-focused tests for primr.core.ai_strategy_runtime.

Covers the legacy sync runtime: prompt builder, preflight branches, the
lite (Pro) generation path, the Deep Research path, and output writing.
All external I/O (llm, deep research client, vendor research, DOCX) mocked.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.core.ai_strategy_runtime import (
    build_ai_strategy_prompt,
    generate_ai_strategy_section,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# build_ai_strategy_prompt
# ---------------------------------------------------------------------------


def test_prompt_contains_company_and_date():
    prompt = build_ai_strategy_prompt("Acme Corp", "azure")
    assert "Acme Corp" in prompt
    from datetime import datetime

    assert datetime.now().strftime("%B %Y") in prompt


@pytest.mark.parametrize(
    ("platform", "needle"),
    [
        ("azure", "Microsoft ecosystem emphasis"),
        ("aws", "AWS ecosystem emphasis"),
        ("gcp", "Google ecosystem emphasis"),
        ("agnostic", "Vendor-neutral, multicloud, hybrid, and private evaluation"),
        ("private", "Private, on-premises, edge, and accelerated infrastructure emphasis"),
    ],
)
def test_prompt_vendor_guidance(platform, needle):
    prompt = build_ai_strategy_prompt("Acme", platform)
    assert needle in prompt


def test_prompt_unknown_vendor_falls_back_to_agnostic():
    prompt = build_ai_strategy_prompt("Acme", "weirdcloud")
    assert "Vendor-neutral, multicloud, hybrid, and private evaluation" in prompt


def test_prompt_includes_discovery_notes():
    prompt = build_ai_strategy_prompt("Acme", "azure", discovery_notes_content="Note X")
    assert "DISCOVERY INSIGHTS (FROM MEETINGS)" in prompt
    assert "Note X" in prompt


# ---------------------------------------------------------------------------
# generate_ai_strategy_section: preflight failures
# ---------------------------------------------------------------------------


def test_preflight_empty_company():
    with patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings:
        mock_settings.return_value.api.gemini_key = "fake"
        result = generate_ai_strategy_section(company_name="  ", platform="azure")
    assert result is None


def test_preflight_invalid_vendor():
    with patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings:
        mock_settings.return_value.api.gemini_key = "fake"
        result = generate_ai_strategy_section(company_name="Acme", platform="badcloud")
    assert result is None


def test_preflight_missing_api_key():
    with patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings:
        mock_settings.return_value.api.gemini_key = None
        result = generate_ai_strategy_section(company_name="Acme", platform="azure")
    assert result is None


def test_preflight_missing_research_file(tmp_path: Path):
    with patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings:
        mock_settings.return_value.api.gemini_key = "fake"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="azure",
            company_research_path=str(tmp_path / "nope.md"),
        )
    assert result is None


def test_preflight_empty_research_file(tmp_path: Path):
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    with patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings:
        mock_settings.return_value.api.gemini_key = "fake"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="azure",
            company_research_path=str(empty),
        )
    assert result is None


# ---------------------------------------------------------------------------
# lite_strategy (bounded reasoning-model path)
# ---------------------------------------------------------------------------


def test_lite_strategy_success(tmp_path: Path):
    research = tmp_path / "research.md"
    research.write_text("# Company research body", encoding="utf-8")
    out_dir = tmp_path / "out"

    with (
        patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings,
        patch("primr.core.ai_strategy_runtime.get_vendor_research_path") as mock_vpath,
        patch(
            "primr.core.ai_strategy_runtime.get_or_generate_vendor_research_sync",
            return_value=[],
        ),
        patch(
            "primr.core.ai_strategy_runtime.llm",
            return_value="# AI Strategy\n\nContent.",
        ) as mock_llm,
        patch("primr.core.ai_strategy_runtime.markdown_to_docx") as mock_docx,
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        mock_vpath.return_value = tmp_path / "no-agnostic.txt"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="azure",
            company_research_path=str(research),
            lite_strategy=True,
            output_dir=out_dir,
        )

    assert result is not None
    assert result.endswith(".docx")
    assert mock_llm.called
    from primr.ai.routing import Role, pick_model_for_role
    from primr.config.models import LITE_AI_STRATEGY_MAX_OUTPUT_TOKENS

    assert mock_llm.call_args.kwargs["model"] == pick_model_for_role(Role.REASONING)
    assert mock_llm.call_args.kwargs["max_tokens"] == LITE_AI_STRATEGY_MAX_OUTPUT_TOKENS
    assert mock_docx.called
    assert list(out_dir.glob("*.md"))


def test_lite_strategy_bounds_large_context_and_uses_estimated_model(tmp_path: Path):
    from primr.ai.routing import Role, pick_model_for_role
    from primr.config.models import LITE_AI_STRATEGY_MAX_INPUT_BYTES

    research = tmp_path / "large-research.md"
    research.write_text("company-context\n" + "x" * 1_000_000, encoding="utf-8")
    out_dir = tmp_path / "out"

    with (
        patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings,
        patch("primr.core.ai_strategy_runtime.get_vendor_research_path") as mock_vpath,
        patch(
            "primr.core.ai_strategy_runtime.get_or_generate_vendor_research_sync",
            return_value=[],
        ),
        patch(
            "primr.core.ai_strategy_runtime.llm",
            return_value="# AI Strategy\n\nContent.",
        ) as mock_llm,
        patch("primr.core.ai_strategy_runtime.markdown_to_docx"),
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        mock_vpath.return_value = tmp_path / "no-agnostic.txt"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="agnostic",
            company_research_path=str(research),
            lite_strategy=True,
            output_dir=out_dir,
        )

    prompt = mock_llm.call_args.args[0]
    assert result is not None
    assert prompt.index("company-context") < prompt.index("AI Strategy")
    assert len(prompt.encode()) <= LITE_AI_STRATEGY_MAX_INPUT_BYTES
    assert mock_llm.call_args.kwargs["model"] == pick_model_for_role(Role.REASONING)


def test_lite_context_logs_do_not_expose_input_paths(tmp_path: Path, caplog) -> None:
    from primr.core.strategy_context import build_bounded_lite_strategy_prompt

    sensitive_name = "private-customer-record.md"
    missing = tmp_path / sensitive_name
    with caplog.at_level(logging.WARNING):
        prompt = build_bounded_lite_strategy_prompt("Write the strategy", [str(missing)])

    assert prompt.endswith("Write the strategy")
    assert sensitive_name not in caplog.text
    assert str(tmp_path) not in caplog.text
    assert "FileNotFoundError" in caplog.text


def test_lite_context_limit_logs_do_not_expose_input_paths(
    tmp_path: Path, caplog, monkeypatch
) -> None:
    from primr.core import strategy_context

    first = tmp_path / "private-first-record.md"
    second = tmp_path / "private-second-record.md"
    first.write_text("brief context", encoding="utf-8")
    second.write_text("more context", encoding="utf-8")
    monkeypatch.setattr(strategy_context, "LITE_AI_STRATEGY_MAX_INPUT_BYTES", 150)

    with caplog.at_level(logging.INFO):
        prompt = strategy_context.build_bounded_lite_strategy_prompt(
            "Write the strategy", [str(first), str(second)]
        )

    assert prompt.endswith("Write the strategy")
    assert "private-first-record.md" not in caplog.text
    assert "private-second-record.md" not in caplog.text
    assert str(tmp_path) not in caplog.text
    assert "governed limit" in caplog.text or "remaining inputs" in caplog.text


def test_lite_strategy_empty_llm_returns_none(tmp_path: Path):
    out_dir = tmp_path / "out"
    with (
        patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings,
        patch("primr.core.ai_strategy_runtime.get_vendor_research_path") as mock_vpath,
        patch(
            "primr.core.ai_strategy_runtime.get_or_generate_vendor_research_sync",
            return_value=[],
        ),
        patch("primr.core.ai_strategy_runtime.llm", return_value="   "),
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        mock_vpath.return_value = tmp_path / "no-agnostic.txt"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="agnostic",
            lite_strategy=True,
            output_dir=out_dir,
        )
    assert result is None


def test_lite_strategy_force_refresh_vendor(tmp_path: Path):
    out_dir = tmp_path / "out"
    with (
        patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings,
        patch("primr.core.ai_strategy_runtime.get_vendor_research_path") as mock_vpath,
        patch(
            "primr.core.ai_strategy_runtime.generate_vendor_research_sync",
            return_value=None,
        ) as mock_gen,
        patch(
            "primr.core.ai_strategy_runtime.llm",
            return_value="# Strategy body",
        ),
        patch("primr.core.ai_strategy_runtime.markdown_to_docx"),
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        mock_vpath.return_value = tmp_path / "no-agnostic.txt"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="aws",
            lite_strategy=True,
            force_refresh_vendor=True,
            output_dir=out_dir,
        )
    assert result is not None
    assert mock_gen.called


# ---------------------------------------------------------------------------
# Deep Research (background) path
# ---------------------------------------------------------------------------


def test_deep_research_success(tmp_path: Path):
    out_dir = tmp_path / "out"

    fake_result = MagicMock()
    fake_result.content = "# Deep strategy body"
    fake_result.interaction_id = "interaction-123"

    client = MagicMock()
    client.research = AsyncMock(return_value=fake_result)

    fake_dr_module = MagicMock()
    fake_dr_module.get_deep_research_client.return_value = client

    class _Status:
        COMPLETED = "completed"

    fake_dr_module.ResearchStatus = _Status
    fake_result.status = _Status.COMPLETED

    with (
        patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings,
        patch("primr.core.ai_strategy_runtime.get_vendor_research_path") as mock_vpath,
        patch(
            "primr.core.ai_strategy_runtime.get_or_generate_vendor_research_sync",
            return_value=[],
        ),
        patch.dict(
            "sys.modules",
            {"primr.ai.deep_research": fake_dr_module},
        ),
        patch(
            "primr.core.ai_strategy_runtime.markdown_to_docx",
            side_effect=lambda output_path, **_kwargs: output_path.write_bytes(b"docx"),
        ),
        patch(
            "primr.ai.job_persistence.acknowledge_pending_job_after_outputs",
            return_value=True,
        ) as acknowledge_mock,
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        mock_vpath.return_value = tmp_path / "no-agnostic.txt"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="gcp",
            lite_strategy=False,
            output_dir=out_dir,
        )

    assert result is not None
    assert client.research.called
    acknowledge_mock.assert_called_once()
    assert len(acknowledge_mock.call_args.args[1]) == 3


def test_deep_research_docx_failure_retains_pending_job(tmp_path: Path):
    fake_result = MagicMock(
        content="# Deep strategy body",
        interaction_id="interaction-123",
        status="completed",
    )
    client = MagicMock(research=AsyncMock(return_value=fake_result))
    fake_dr_module = MagicMock()
    fake_dr_module.get_deep_research_client.return_value = client
    fake_dr_module.ResearchStatus.COMPLETED = "completed"
    with (
        patch("primr.core.ai_strategy_runtime.get_settings") as settings,
        patch(
            "primr.core.ai_strategy_runtime.get_or_generate_vendor_research_sync",
            return_value=[],
        ),
        patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr_module}),
        patch(
            "primr.core.ai_strategy_runtime.markdown_to_docx",
            side_effect=RuntimeError("render failed"),
        ),
        patch("primr.ai.job_persistence.acknowledge_pending_job_after_outputs") as acknowledge_mock,
    ):
        settings.return_value.api.gemini_key = "fake"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="gcp",
            lite_strategy=False,
            output_dir=tmp_path / "out",
        )

    assert result is not None
    assert result.endswith(".md")
    acknowledge_mock.assert_not_called()


def test_deep_research_failure_returns_none(tmp_path: Path):
    out_dir = tmp_path / "out"

    class _Status:
        COMPLETED = "completed"
        FAILED = "failed"

    fake_result = MagicMock()
    fake_result.status = _Status.FAILED
    fake_result.content = ""

    client = MagicMock()
    client.research = AsyncMock(return_value=fake_result)

    fake_dr_module = MagicMock()
    fake_dr_module.get_deep_research_client.return_value = client
    fake_dr_module.ResearchStatus = _Status

    with (
        patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings,
        patch("primr.core.ai_strategy_runtime.get_vendor_research_path") as mock_vpath,
        patch(
            "primr.core.ai_strategy_runtime.get_or_generate_vendor_research_sync",
            return_value=[],
        ),
        patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr_module}),
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        mock_vpath.return_value = tmp_path / "no-agnostic.txt"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="agnostic",
            lite_strategy=False,
            output_dir=out_dir,
        )

    assert result is None


def test_docx_permission_error_retries(tmp_path: Path):
    out_dir = tmp_path / "out"
    calls = {"n": 0}

    def docx_side_effect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("locked")
        return None

    with (
        patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings,
        patch("primr.core.ai_strategy_runtime.get_vendor_research_path") as mock_vpath,
        patch(
            "primr.core.ai_strategy_runtime.get_or_generate_vendor_research_sync",
            return_value=[],
        ),
        patch("primr.core.ai_strategy_runtime.llm", return_value="# Body"),
        patch(
            "primr.core.ai_strategy_runtime.markdown_to_docx",
            side_effect=docx_side_effect,
        ),
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        mock_vpath.return_value = tmp_path / "no-agnostic.txt"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="agnostic",
            lite_strategy=True,
            output_dir=out_dir,
        )

    assert result is not None
    assert calls["n"] == 2


def test_docx_generic_error_falls_back_to_md(tmp_path: Path):
    out_dir = tmp_path / "out"
    with (
        patch("primr.core.ai_strategy_runtime.get_settings") as mock_settings,
        patch("primr.core.ai_strategy_runtime.get_vendor_research_path") as mock_vpath,
        patch(
            "primr.core.ai_strategy_runtime.get_or_generate_vendor_research_sync",
            return_value=[],
        ),
        patch("primr.core.ai_strategy_runtime.llm", return_value="# Body"),
        patch(
            "primr.core.ai_strategy_runtime.markdown_to_docx",
            side_effect=RuntimeError("boom"),
        ),
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        mock_vpath.return_value = tmp_path / "no-agnostic.txt"
        result = generate_ai_strategy_section(
            company_name="Acme",
            platform="agnostic",
            lite_strategy=True,
            output_dir=out_dir,
        )

    assert result is not None
    assert result.endswith(".md")
