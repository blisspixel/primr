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


def _link(url: str) -> SimpleNamespace:
    return SimpleNamespace(
        url=url,
        anchor_text="",
        sitemap_priority=None,
        source="homepage",
    )


def test_selector_uses_heuristic_when_model_calls_disabled() -> None:
    from primr.utils.model_policy import disable_model_calls

    links = [
        _link("https://acme.example/privacy"),
        _link("https://acme.example/login"),
        _link("https://acme.example/legal"),
        _link("https://acme.example/about"),
        _link("https://acme.example/investors"),
        _link("https://acme.example/products"),
    ]
    model_call = MagicMock(return_value="https://acme.example/privacy")
    with disable_model_calls():
        selected = select_links_with_llm(
            links,
            "Acme Corp",
            "https://acme.example",
            max_links=3,
            model_call=model_call,
        )
    model_call.assert_not_called()
    assert "https://acme.example/about" in selected
    assert "https://acme.example/investors" in selected
    assert "https://acme.example/privacy" not in selected


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
