"""Tests for the scraper-owned link-selection boundary."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import primr.data.scrape as scrape_module
from primr.data.link_selection import select_links_with_llm


def test_selector_uses_injected_model_call() -> None:
    links = [SimpleNamespace(url=f"https://acme.example/{index}") for index in range(60)]
    model_call = MagicMock(return_value="https://acme.example/4\nhttps://acme.example/2")

    selected = select_links_with_llm(
        links,
        "Acme Corp",
        "https://acme.example",
        max_links=20,
        model_call=model_call,
    )

    assert selected == ["https://acme.example/4", "https://acme.example/2"]
    model_call.assert_called_once()


def test_scraper_does_not_import_research_orchestration() -> None:
    """Keep data collection independent from the orchestration hub."""

    source_path = Path(inspect.getsourcefile(scrape_module) or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "primr.core.research_agent" not in imported_modules
