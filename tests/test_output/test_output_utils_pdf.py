"""Tests for DOCX->PDF conversion fallback behavior in output utils."""

from __future__ import annotations

from unittest.mock import patch

from primr.output.output_utils import convert_docx_to_pdf


def test_convert_docx_to_pdf_returns_none_for_missing_docx(tmp_path):
    missing = tmp_path / "missing.docx"
    result = convert_docx_to_pdf(missing)
    assert result is None


def test_convert_docx_to_pdf_uses_docx2pdf_when_available(tmp_path):
    docx = tmp_path / "report.docx"
    pdf = tmp_path / "report.pdf"
    docx.write_text("docx", encoding="utf-8")

    def _fake_convert(_path: str) -> None:
        pdf.write_text("pdf", encoding="utf-8")

    with patch("docx2pdf.convert", side_effect=_fake_convert):
        result = convert_docx_to_pdf(docx)

    assert result == str(pdf)
    assert pdf.exists()


def test_convert_docx_to_pdf_falls_back_to_soffice(tmp_path):
    docx = tmp_path / "report.docx"
    pdf = tmp_path / "report.pdf"
    docx.write_text("docx", encoding="utf-8")

    def _fake_run(*_args, **_kwargs):
        pdf.write_text("pdf", encoding="utf-8")
        return None

    with (
        patch("docx2pdf.convert", side_effect=RuntimeError("docx2pdf fail")),
        patch("shutil.which", return_value="/usr/bin/soffice"),
        patch("subprocess.run", side_effect=_fake_run),
    ):
        result = convert_docx_to_pdf(docx)

    assert result == str(pdf)
    assert pdf.exists()
