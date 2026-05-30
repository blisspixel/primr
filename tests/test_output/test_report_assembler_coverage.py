"""Additional coverage tests for primr.output.report_assembler.ReportAssembler."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from primr.core.report_models import (
    ConfidenceLevel,
    ConfidenceNote,
    SectionContent,
    SourceCitation,
    SourceType,
)
from primr.output.report_assembler import ReportAssembler


def _src(
    url: str = "https://example.com", title: str = "Src", excerpt: str = "x"
) -> SourceCitation:
    return SourceCitation(
        url=url,
        title=title,
        source_type=SourceType.COMPANY_WEBSITE,
        accessed_at=datetime(2026, 5, 1),
        excerpt=excerpt,
    )


def _section(title: str = "S", content: str = "c", sources=None) -> SectionContent:
    return SectionContent(title=title, content=content, sources=sources or [_src()])


def _report():
    assembler = ReportAssembler()
    return assembler, assembler.assemble(
        company_name="Acme",
        website="https://acme.example",
        industry="Tech",
        executive_summary=_section("Executive Summary", "Summary body"),
        sections=[_section("Section 1", "Body")],
        insights=[],
        research_duration=10.0,
    )


# --------------------------------------------------------------------------- #
# generate_sources_appendix
# --------------------------------------------------------------------------- #
def test_generate_sources_appendix_empty():
    assembler = ReportAssembler()
    assert assembler.generate_sources_appendix([]) == "No sources cited."


def test_generate_sources_appendix_truncates_long_excerpt():
    assembler = ReportAssembler()
    long_excerpt = "z" * 200
    out = assembler.generate_sources_appendix([_src(excerpt=long_excerpt)])
    assert "..." in out
    assert "Excerpt:" in out


# --------------------------------------------------------------------------- #
# to_markdown with confidence notes value rendering
# --------------------------------------------------------------------------- #
def test_to_markdown_renders_confidence_notes():
    assembler = ReportAssembler()
    note = ConfidenceNote(
        statement="Revenue estimate",
        confidence=ConfidenceLevel.ESTIMATED,
        basis="employee count",
    )
    section = SectionContent(
        title="Financials",
        content="content",
        sources=[_src()],
        confidence_notes=[note],
    )
    report = assembler.assemble(
        company_name="Acme",
        website="https://acme.example",
        industry="Tech",
        executive_summary=_section("Executive Summary", "Summary"),
        sections=[section],
        insights=[],
        research_duration=5.0,
    )
    md = assembler.to_markdown(report)
    assert "Confidence Notes" in md
    assert "Revenue estimate" in md
    assert "employee count" in md


# --------------------------------------------------------------------------- #
# export_docx
# --------------------------------------------------------------------------- #
def test_export_docx_success(tmp_path):
    assembler, report = _report()
    out = tmp_path / "report.docx"
    ok = assembler.export_docx(report, str(out))
    assert ok is True
    assert out.exists()


def test_export_docx_save_failure(tmp_path):
    assembler, report = _report()
    out = tmp_path / "report.docx"
    with patch("docx.document.Document.save", side_effect=OSError("locked")):
        ok = assembler.export_docx(report, str(out))
    assert ok is False


# --------------------------------------------------------------------------- #
# export_pdf fallback timestamp branch
# --------------------------------------------------------------------------- #
def test_export_pdf_fallback_uses_timestamp_when_docx_exists(tmp_path):
    assembler, report = _report()

    def _fake_export_docx(_report, docx_path):
        Path(docx_path).write_text("docx", encoding="utf-8")
        return True

    target_pdf = tmp_path / "final.pdf"
    # A sibling DOCX already exists -> fallback must use a timestamped name.
    (tmp_path / "final.docx").write_text("existing", encoding="utf-8")

    with (
        patch.object(assembler, "export_docx", side_effect=_fake_export_docx),
        patch("subprocess.run", side_effect=FileNotFoundError("no soffice")),
    ):
        ok = assembler.export_pdf(report, str(target_pdf))

    assert ok is False
    # The original sibling should be preserved and a timestamped fallback created.
    timestamped = list(tmp_path.glob("final_*.docx"))
    assert timestamped


def test_export_pdf_returns_false_when_docx_export_fails(tmp_path):
    assembler, report = _report()
    target_pdf = tmp_path / "out.pdf"
    with patch.object(assembler, "export_docx", return_value=False):
        ok = assembler.export_pdf(report, str(target_pdf))
    assert ok is False


def test_export_pdf_success_in_place(tmp_path):
    assembler, report = _report()

    def _fake_export_docx(_report, docx_path):
        Path(docx_path).write_text("docx", encoding="utf-8")
        return True

    def _fake_run(cmd, check, capture_output):
        outdir = Path(cmd[5])
        temp_docx = Path(cmd[6])
        (outdir / f"{temp_docx.stem}.pdf").write_text("pdf", encoding="utf-8")
        return Mock(returncode=0)

    target_pdf = tmp_path / "result.pdf"
    with (
        patch.object(assembler, "export_docx", side_effect=_fake_export_docx),
        patch("subprocess.run", side_effect=_fake_run),
    ):
        ok = assembler.export_pdf(report, str(target_pdf))

    assert ok is True
    assert target_pdf.exists()
