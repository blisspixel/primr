"""Unit tests for authoring helpers (offline, no LLM)."""

from __future__ import annotations

from primr.skill_pack.authoring import _parse_bundled_files


def test_parse_bundled_files_preserves_backslash_n_in_scripts():
    """Regression: the double-escaped-\\n normalization must NOT run on .py
    (or .json) bundled content, where a literal backslash-n is meaningful
    (regex, Windows path) and rewriting it corrupts the file."""
    raw = [
        {"path": "scripts/calc.py", "content": "import re\\nre.split('\\\\n', text)"},
        {"path": "references/notes.md", "content": "line one\\nline two"},
    ]
    files = {bf.relpath: bf.content for bf in _parse_bundled_files(raw)}
    # Script: literal backslash-n sequences are preserved verbatim.
    assert "\\n" in files["scripts/calc.py"]
    # Markdown: double-escaped \n is normalized to a real newline.
    assert files["references/notes.md"] == "line one\nline two"


def test_parse_bundled_files_skips_malformed_entries():
    raw = ["not a dict", {"content": "no path"}, {"path": "references/x.md"}, 123]
    assert _parse_bundled_files(raw) == []


def test_parse_bundled_files_non_list_returns_empty():
    assert _parse_bundled_files(None) == []
    assert _parse_bundled_files("nope") == []
