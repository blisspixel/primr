"""
Coverage-focused tests for primr.core.strategy_generation.

Covers the YAML prompt builder across optional config blocks, plus the
``generate_generic_strategy`` orchestration path with all external I/O
(Deep Research client, DOCX conversion, settings) mocked.
"""

from __future__ import annotations

import builtins
import io
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.ai.deep_research import ResearchStatus
from primr.core.strategy_generation import (
    build_strategy_prompt_from_yaml,
    generate_generic_strategy,
)

if TYPE_CHECKING:
    from pathlib import Path

_REAL_OPEN = builtins.open


def _yaml_read_open(*args, **kwargs):
    """open() shim: real open for write modes, a dummy reader otherwise.

    The strategy YAML is read once at the top of generate_generic_strategy;
    yaml.safe_load is separately patched so the returned content is ignored.
    All subsequent writes (md/txt) must hit the real filesystem.
    """
    mode = ""
    if len(args) > 1:
        mode = args[1]
    mode = kwargs.get("mode", mode)
    if "w" in mode or "a" in mode:
        return _REAL_OPEN(*args, **kwargs)
    return io.StringIO("placeholder: true")


# ---------------------------------------------------------------------------
# build_strategy_prompt_from_yaml
# ---------------------------------------------------------------------------


def test_prompt_minimal_config():
    prompt = build_strategy_prompt_from_yaml({}, "Acme Corp")
    assert "Strategy Document for Acme Corp" in prompt
    assert "FINAL INSTRUCTIONS" in prompt
    assert "Begin the document now." in prompt


def test_prompt_uses_meta_name():
    cfg = {"meta": {"name": "Security Strategy"}}
    prompt = build_strategy_prompt_from_yaml(cfg, "Acme Corp")
    assert "Security Strategy for Acme Corp" in prompt
    assert "Generate a comprehensive Security Strategy for Acme Corp." in prompt


def test_prompt_includes_optional_text_blocks():
    cfg = {
        "document_purpose": "PURPOSE_TEXT",
        "context_instructions": "CONTEXT_TEXT",
        "writing_standards": "STANDARDS_TEXT",
    }
    prompt = build_strategy_prompt_from_yaml(cfg, "Acme")
    assert "YOUR ROLE AND TASK" in prompt
    assert "PURPOSE_TEXT" in prompt
    assert "HOW TO USE CONTEXT" in prompt
    assert "CONTEXT_TEXT" in prompt
    assert "WRITING QUALITY STANDARDS" in prompt
    assert "STANDARDS_TEXT" in prompt


def test_prompt_includes_epistemic_rules():
    cfg = {"epistemic_rules": {"hypothesis_framing": "Frame as hypotheses."}}
    prompt = build_strategy_prompt_from_yaml(cfg, "Acme")
    assert "EPISTEMIC RULES (CRITICAL)" in prompt
    assert "Hypothesis Framing" in prompt
    assert "Frame as hypotheses." in prompt


def test_prompt_includes_discovery_notes():
    prompt = build_strategy_prompt_from_yaml({}, "Acme", discovery_notes_content="Internal note A")
    assert "DISCOVERY NOTES (INTERNAL INSIGHTS)" in prompt
    assert "Internal note A" in prompt


def test_prompt_renders_sections_subsections_and_covers():
    cfg = {
        "sections": [
            {
                "name": "Overview",
                "purpose": "Set context",
                "depth": "Be thorough",
                "covers": ["Market", "Competition"],
                "subsections": [
                    {"name": "Sub A", "covers": ["Detail 1"]},
                ],
            }
        ]
    }
    prompt = build_strategy_prompt_from_yaml(cfg, "Acme")
    assert "DOCUMENT STRUCTURE" in prompt
    assert "### Overview" in prompt
    assert "**Purpose**: Set context" in prompt
    assert "- Market" in prompt
    assert "#### Sub A" in prompt
    assert "- Detail 1" in prompt
    assert "**Depth Guidance**: Be thorough" in prompt


def test_prompt_section_defaults_when_fields_missing():
    cfg = {"sections": [{}]}
    prompt = build_strategy_prompt_from_yaml(cfg, "Acme")
    assert "### Untitled Section" in prompt


# ---------------------------------------------------------------------------
# generate_generic_strategy
# ---------------------------------------------------------------------------


def test_missing_yaml_returns_none():
    result = generate_generic_strategy(
        strategy_name="custom",
        strategy_yaml="definitely-not-a-real-strategy-name",
        company_name="Acme",
    )
    assert result is None


def test_preflight_empty_company_returns_none(tmp_path: Path):
    with (
        patch("primr.core.strategy_generation.Path.exists", return_value=True),
        patch("builtins.open", side_effect=_yaml_read_open),
        patch(
            "primr.core.strategy_generation.yaml.safe_load",
            return_value={"meta": {"name": "Custom"}},
        ),
        patch("primr.core.strategy_generation.get_settings") as mock_settings,
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        result = generate_generic_strategy(
            strategy_name="custom",
            strategy_yaml="custom",
            company_name="   ",
        )
    assert result is None


def test_preflight_missing_api_key_returns_none(tmp_path: Path):
    with (
        patch("primr.core.strategy_generation.Path.exists", return_value=True),
        patch("builtins.open", side_effect=_yaml_read_open),
        patch(
            "primr.core.strategy_generation.yaml.safe_load",
            return_value={"meta": {"name": "Custom"}},
        ),
        patch("primr.core.strategy_generation.get_settings") as mock_settings,
    ):
        mock_settings.return_value.api.gemini_key = None
        result = generate_generic_strategy(
            strategy_name="custom",
            strategy_yaml="custom",
            company_name="Acme",
        )
    assert result is None


def test_research_failure_returns_none(tmp_path: Path):
    fake_result = MagicMock()
    fake_result.status = ResearchStatus.FAILED
    fake_result.content = ""

    client = MagicMock()
    client.research = AsyncMock(return_value=fake_result)

    with (
        patch("primr.core.strategy_generation.Path.exists", return_value=True),
        patch("builtins.open", side_effect=_yaml_read_open),
        patch(
            "primr.core.strategy_generation.yaml.safe_load",
            return_value={"meta": {"name": "Custom"}},
        ),
        patch("primr.core.strategy_generation.get_settings") as mock_settings,
        patch(
            "primr.core.strategy_generation.get_deep_research_client",
            return_value=client,
        ),
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        result = generate_generic_strategy(
            strategy_name="custom",
            strategy_yaml="custom",
            company_name="Acme",
        )
    assert result is None


def test_successful_generation_writes_outputs(tmp_path: Path):
    fake_result = MagicMock()
    fake_result.status = ResearchStatus.COMPLETED
    fake_result.content = "# Strategy\n\nBody content."

    client = MagicMock()
    client.research = AsyncMock(return_value=fake_result)

    out_dir = tmp_path / "out"

    with (
        patch("primr.core.strategy_generation.Path.exists", return_value=True),
        patch(
            "primr.core.strategy_generation.yaml.safe_load",
            return_value={
                "meta": {"name": "Custom", "output_filename": "{company_name}_Custom"},
            },
        ),
        patch("primr.core.strategy_generation.get_settings") as mock_settings,
        patch(
            "primr.core.strategy_generation.get_deep_research_client",
            return_value=client,
        ),
        patch("primr.core.strategy_generation.markdown_to_docx") as mock_docx,
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        with patch("builtins.open", side_effect=_yaml_read_open):
            result = generate_generic_strategy(
                strategy_name="custom",
                strategy_yaml="custom",
                company_name="Acme",
                output_dir=out_dir,
                write_txt=True,
            )

    assert result is not None
    assert result.endswith(".docx")
    assert mock_docx.called
    # md + txt written
    md_files = list(out_dir.glob("*.md"))
    txt_files = list(out_dir.glob("*.txt"))
    assert md_files
    assert txt_files


def test_docx_permission_error_retries_with_timestamp(tmp_path: Path):
    fake_result = MagicMock()
    fake_result.status = ResearchStatus.COMPLETED
    fake_result.content = "# Strategy body"

    client = MagicMock()
    client.research = AsyncMock(return_value=fake_result)

    out_dir = tmp_path / "out"
    calls = {"n": 0}

    def docx_side_effect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("locked")
        return None

    with (
        patch("primr.core.strategy_generation.Path.exists", return_value=True),
        patch("builtins.open", side_effect=_yaml_read_open),
        patch(
            "primr.core.strategy_generation.yaml.safe_load",
            return_value={"meta": {"name": "Custom"}},
        ),
        patch("primr.core.strategy_generation.get_settings") as mock_settings,
        patch(
            "primr.core.strategy_generation.get_deep_research_client",
            return_value=client,
        ),
        patch(
            "primr.core.strategy_generation.markdown_to_docx",
            side_effect=docx_side_effect,
        ),
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        result = generate_generic_strategy(
            strategy_name="custom",
            strategy_yaml="custom",
            company_name="Acme",
            output_dir=out_dir,
        )

    assert result is not None
    assert calls["n"] == 2


def test_docx_generic_error_falls_back_to_md(tmp_path: Path):
    fake_result = MagicMock()
    fake_result.status = ResearchStatus.COMPLETED
    fake_result.content = "# Strategy body"

    client = MagicMock()
    client.research = AsyncMock(return_value=fake_result)

    out_dir = tmp_path / "out"

    with (
        patch("primr.core.strategy_generation.Path.exists", return_value=True),
        patch("builtins.open", side_effect=_yaml_read_open),
        patch(
            "primr.core.strategy_generation.yaml.safe_load",
            return_value={"meta": {"name": "Custom"}},
        ),
        patch("primr.core.strategy_generation.get_settings") as mock_settings,
        patch(
            "primr.core.strategy_generation.get_deep_research_client",
            return_value=client,
        ),
        patch(
            "primr.core.strategy_generation.markdown_to_docx",
            side_effect=RuntimeError("boom"),
        ),
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        result = generate_generic_strategy(
            strategy_name="custom",
            strategy_yaml="custom",
            company_name="Acme",
            output_dir=out_dir,
        )

    # Falls back to md path on DOCX conversion failure
    assert result is not None
    assert result.endswith(".md")


@pytest.mark.parametrize("write_txt", [True, False])
def test_write_txt_flag(tmp_path: Path, write_txt: bool):
    fake_result = MagicMock()
    fake_result.status = ResearchStatus.COMPLETED
    fake_result.content = "# Body"

    client = MagicMock()
    client.research = AsyncMock(return_value=fake_result)
    out_dir = tmp_path / "out"

    with (
        patch("primr.core.strategy_generation.Path.exists", return_value=True),
        patch("builtins.open", side_effect=_yaml_read_open),
        patch(
            "primr.core.strategy_generation.yaml.safe_load",
            return_value={"meta": {"name": "Custom"}},
        ),
        patch("primr.core.strategy_generation.get_settings") as mock_settings,
        patch(
            "primr.core.strategy_generation.get_deep_research_client",
            return_value=client,
        ),
        patch("primr.core.strategy_generation.markdown_to_docx"),
    ):
        mock_settings.return_value.api.gemini_key = "fake"
        generate_generic_strategy(
            strategy_name="custom",
            strategy_yaml="custom",
            company_name="Acme",
            output_dir=out_dir,
            write_txt=write_txt,
        )

    txt_files = list(out_dir.glob("*.txt"))
    if write_txt:
        assert txt_files
    else:
        assert not txt_files
