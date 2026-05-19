"""Tests for validate_context_files and generate_initial_overview."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.research_agent import (
    generate_initial_overview,
    validate_context_files,
)


class TestValidateContextFiles:
    def test_empty_list_returns_empty_tuples(self):
        valid, invalid, warnings = validate_context_files([])
        assert valid == []
        assert invalid == []
        assert warnings == []

    def test_missing_file_marked_invalid(self, tmp_path):
        bogus = str(tmp_path / "no_such.pdf")
        valid, invalid, warnings = validate_context_files([bogus])
        assert valid == []
        assert invalid
        assert invalid[0][0] == bogus
        assert "not found" in invalid[0][1].lower()

    def test_supported_extension_marked_valid(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4")
        valid, invalid, _ = validate_context_files([str(f)])
        assert str(f) in valid
        assert invalid == []

    def test_txt_supported(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("content", encoding="utf-8")
        valid, invalid, _ = validate_context_files([str(f)])
        assert str(f) in valid
        assert invalid == []

    def test_docx_marked_invalid_with_warning(self, tmp_path):
        f = tmp_path / "doc.docx"
        f.write_bytes(b"PK")  # docx zip magic
        valid, invalid, warnings = validate_context_files([str(f)])
        assert valid == []
        assert any("docx" in reason.lower() or "word" in reason.lower() for _, reason in invalid)
        assert warnings  # tip emitted

    def test_xlsx_marked_invalid(self, tmp_path):
        f = tmp_path / "spreadsheet.xlsx"
        f.write_bytes(b"PK")
        valid, invalid, _ = validate_context_files([str(f)])
        assert valid == []
        assert any("excel" in reason.lower() or "csv" in reason.lower() for _, reason in invalid)

    def test_unknown_extension_marked_invalid(self, tmp_path):
        f = tmp_path / "weird.xyz"
        f.write_text("data", encoding="utf-8")
        valid, invalid, _ = validate_context_files([str(f)])
        assert valid == []
        assert any("Unsupported file type" in reason for _, reason in invalid)

    def test_mixed_list(self, tmp_path):
        good = tmp_path / "g.pdf"
        good.write_bytes(b"%PDF")
        bad = tmp_path / "b.xlsx"
        bad.write_bytes(b"PK")
        missing = str(tmp_path / "m.pdf")
        valid, invalid, _ = validate_context_files([str(good), str(bad), missing])
        assert str(good) in valid
        assert len(invalid) == 2


class TestGenerateInitialOverview:
    def test_writes_overview_to_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value="Acme is a widget company..."),
        )
        result = generate_initial_overview(
            "Acme", "https://acme.example", "Tech", str(tmp_path)
        )
        assert result == "Acme is a widget company..."
        out = tmp_path / "Acme_Draft_Overview.txt"
        assert out.exists()
        assert out.read_text(encoding="utf-8") == "Acme is a widget company..."

    def test_handles_no_website(self, tmp_path, monkeypatch):
        mock = MagicMock(return_value="overview body")
        monkeypatch.setattr("primr.core.research_agent.llm", mock)
        generate_initial_overview("Acme", None, "Tech", str(tmp_path))
        # Prompt should contain "N/A" for missing website
        prompt = mock.call_args.args[0]
        assert "N/A" in prompt
