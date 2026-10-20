"""Canonical legacy pipeline keeps quality gates and compatibility boundaries."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from primr.core.legacy_research import LegacyServices, run_research


@pytest.mark.parametrize("captured", [{}, {"https://acme.example": "too thin"}])
def test_empty_or_insufficient_collection_stops_before_any_model_call(tmp_path, captured):
    model = MagicMock(side_effect=AssertionError("quality gate must stop synthesis"))
    services = replace(LegacyServices(), fetch=MagicMock(return_value=captured), model=model)
    assert (
        run_research(
            "ExampleCo", "https://acme.example", folder_path=str(tmp_path), services=services
        )
        is None
    )
    model.assert_not_called()


def test_explicit_folder_and_section_callbacks_survive_canonical_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "primr.output.working_brief.emit_after_structured_scrape", lambda *args: None
    )
    monkeypatch.setattr("primr.data.search_utils.search_web", lambda *args: [])
    corpus = {"https://acme.example/about": "Sourced context."}
    services = replace(
        LegacyServices(),
        fetch=MagicMock(return_value=corpus),
        folder=MagicMock(side_effect=AssertionError("explicit folder must be preserved")),
        external_queries=MagicMock(return_value=[]),
        summarize=MagicMock(return_value="Collected summary"),
        prompt=MagicMock(return_value="Industry prompt"),
        model=MagicMock(return_value="Industrial equipment"),
    )
    overview = MagicMock(return_value="Company overview")
    section = MagicMock(return_value="Source-grounded section")
    progress: list[str] = []
    result = run_research(
        "ExampleCo",
        "https://acme.example",
        on_progress=progress.append,
        fail_on_low_scrape=False,
        folder_path=str(tmp_path),
        services=services,
        overview_fn=overview,
        section_fn=section,
    )
    assert result is not None
    assert result["company_name"] == "Source-grounded section"
    services.summarize.assert_called_once_with(
        "ExampleCo", "https://acme.example", corpus, str(tmp_path)
    )
    overview.assert_called_once_with(
        "ExampleCo", "https://acme.example", "Industrial equipment", str(tmp_path)
    )
    assert section.call_count == 18
    assert section.call_args.args[-2:] == ("Company overview", "Collected summary")
    assert (tmp_path / "_scraped_urls.txt").is_file()
    assert any("15 report sections" in message for message in progress)


def test_leaf_import_and_legacy_exports_do_not_load_operational_cli():
    source = Path(__file__).resolve().parents[2] / "src"
    script = f"""
import sys
sys.path.insert(0, {str(source)!r})
import primr.core.legacy_research
assert 'primr.core.research_agent' not in sys.modules
assert 'primr.core.cli' not in sys.modules
import primr
from primr.core import research_agent
from primr.cli_entry import main
assert research_agent.main is main
assert primr.perform_research is research_agent.perform_research
assert 'primr.core.cli' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, timeout=30)
