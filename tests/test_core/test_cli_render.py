"""Tests for the ``primr render`` subcommand (Markdown -> DOCX/TXT, zero cost)."""

from __future__ import annotations

from pathlib import Path

from primr.core.cli_render import is_render_command, run_render

_SAMPLE = (
    "# Acme Strategic Overview\n\n"
    "## Executive Summary\n\nAcme does X [cite: 1].\n\n"
    "## Sources\n\n[cite: 1] Acme - https://acme.example\n"
)


def _write(tmp_path: Path, name: str = "Acme_Strategic_Overview.md") -> Path:
    p = tmp_path / name
    p.write_text(_SAMPLE, encoding="utf-8")
    return p


def test_is_render_command_detection():
    assert is_render_command(["render", "x.md"]) is True
    assert is_render_command(["recon", "x.com"]) is False
    assert is_render_command([]) is False


def test_render_produces_docx_and_txt(tmp_path: Path):
    md = _write(tmp_path)
    rc = run_render(["render", str(md)])
    assert rc == 0
    docx = md.with_suffix(".docx")
    txt = md.with_suffix(".txt")
    assert docx.exists()
    assert docx.stat().st_size > 0
    assert txt.exists()
    assert txt.read_text(encoding="utf-8") == _SAMPLE


def test_render_no_txt_flag(tmp_path: Path):
    md = _write(tmp_path)
    rc = run_render(["render", str(md), "--no-txt"])
    assert rc == 0
    assert md.with_suffix(".docx").exists()
    assert not md.with_suffix(".txt").exists()


def test_render_output_dir(tmp_path: Path):
    md = _write(tmp_path)
    out = tmp_path / "deliverables"
    rc = run_render(["render", str(md), "--output-dir", str(out)])
    assert rc == 0
    assert (out / "Acme_Strategic_Overview.docx").exists()


def test_render_missing_file_returns_1(tmp_path: Path):
    rc = run_render(["render", str(tmp_path / "nope.md")])
    assert rc == 1


def test_render_empty_file_returns_1(tmp_path: Path):
    p = tmp_path / "empty.md"
    p.write_text("   \n", encoding="utf-8")
    assert run_render(["render", str(p)]) == 1


def test_render_directory_returns_1(tmp_path: Path):
    directory = tmp_path / "report.md"
    directory.mkdir()
    assert run_render(["render", str(directory)]) == 1


def test_render_keeps_first_h1_section_without_title_flag(tmp_path: Path):
    md = tmp_path / "ExampleCo_Strategic_Overview.md"
    md.write_text("# 1. Executive Summary\n\nAcme sells widgets.\n", encoding="utf-8")
    assert run_render(["render", str(md), "--no-txt"]) == 0
    from docx import Document

    text = "\n".join(p.text for p in Document(md.with_suffix(".docx")).paragraphs)
    assert "Executive Summary" in text
    assert "Acme sells widgets" in text


def test_render_dispatched_from_main(tmp_path: Path):
    """`primr render ...` routes to run_render via the main entrypoint."""
    from primr.core import cli

    md = _write(tmp_path)
    rc = cli.main(["render", str(md), "--no-txt"])
    assert rc == 0
    assert md.with_suffix(".docx").exists()
