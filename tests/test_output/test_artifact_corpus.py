"""Artifact regression corpus harness.

Runs realistic long-form report/strategy fixtures through the final shipping
pipeline so renderer/validator changes are tested against real-shaped output,
not toy strings. Fixtures + expected outcomes live in
``tests/fixtures/artifacts/`` (see that directory's README.md).

Roadmap: "Artifact Pipeline Hardening" — build a regression corpus from real
shipped/failed artifacts so renderer/validator changes are tested against
actual long-form outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from primr.output.artifact_validation import (
    _validate_output_docx,
    _validate_output_markdown,
)

_ARTIFACT_DIR = Path(__file__).parent.parent / "fixtures" / "artifacts"
_MANIFEST_PATH = _ARTIFACT_DIR / "manifest.json"


def _load_manifest() -> list[dict]:
    data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return data["fixtures"]


def _manifest_ids(entry: dict) -> str:
    return entry["file"]


def test_manifest_covers_every_fixture() -> None:
    """Every .md fixture (except README) must have a manifest entry, and every
    manifest entry must point at a real file. Guards against a dropped-in
    fixture being silently skipped."""
    on_disk = {p.name for p in _ARTIFACT_DIR.glob("*.md") if p.name != "README.md"}
    in_manifest = {e["file"] for e in _load_manifest()}
    assert on_disk == in_manifest, (
        f"manifest/fixtures mismatch: only-on-disk={on_disk - in_manifest}, "
        f"only-in-manifest={in_manifest - on_disk}"
    )


@pytest.mark.parametrize("entry", _load_manifest(), ids=_manifest_ids)
def test_corpus_artifact_gate(entry: dict) -> None:
    """Each corpus artifact yields the manifest's expected gate outcome."""
    content = (_ARTIFACT_DIR / entry["file"]).read_text(encoding="utf-8")
    result = _validate_output_markdown(content)

    assert result["passed"] is entry["expect_pass"], (
        f"{entry['file']}: expected pass={entry['expect_pass']}, "
        f"got {result['passed']} with issues={result['issues']}"
    )

    if entry["expect_pass"]:
        assert result["issues"] == [], f"{entry['file']} should ship clean"
        # A passing fixture may still surface non-blocking content warnings
        # (e.g. scaffolding leakage, demoted from a gate per agentic-balance).
        for prefix in entry.get("warning_prefixes", []):
            assert any(w.startswith(prefix) for w in result["warnings"]), (
                f"{entry['file']}: expected a warning starting with {prefix!r}; "
                f"got {result['warnings']}"
            )
    else:
        for prefix in entry["issue_prefixes"]:
            assert any(issue.startswith(prefix) for issue in result["issues"]), (
                f"{entry['file']}: expected an issue starting with {prefix!r}; "
                f"got {result['issues']}"
            )


@pytest.mark.parametrize(
    "entry",
    [e for e in _load_manifest() if e.get("render_docx")],
    ids=_manifest_ids,
)
def test_corpus_clean_artifact_renders_clean_docx(entry: dict, tmp_path: Path) -> None:
    """Clean fixtures must render to a DOCX that passes the DOCX artifact gate —
    end-to-end coverage of the markdown -> DOCX renderer against long-form output."""
    pytest.importorskip("docx")
    from primr.output.markdown_converter import markdown_to_docx

    content = (_ARTIFACT_DIR / entry["file"]).read_text(encoding="utf-8")
    docx_path = tmp_path / f"{Path(entry['file']).stem}.docx"
    markdown_to_docx(content, docx_path, title="Corpus Fixture", subtitle="regression")

    assert docx_path.is_file()
    docx_result = _validate_output_docx(docx_path)
    assert docx_result["passed"], (
        f"{entry['file']} rendered DOCX failed validation: "
        f"issues={docx_result['issues']}, errors={docx_result['errors']}"
    )
