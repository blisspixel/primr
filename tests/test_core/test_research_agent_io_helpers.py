"""Tests for I/O helpers in research_agent: ensure_valid_url, save_section_output,
consolidate_working_folder."""

from __future__ import annotations

import os

import pytest

from primr.core.research_agent import (
    consolidate_working_folder,
    ensure_valid_url,
    save_section_output,
)


class TestEnsureValidUrl:
    def test_none_returns_none(self):
        assert ensure_valid_url(None) is None

    def test_empty_returns_none(self):
        assert ensure_valid_url("") is None

    def test_https_url_unchanged(self):
        assert ensure_valid_url("https://acme.example") == "https://acme.example"

    def test_http_url_unchanged(self):
        assert ensure_valid_url("http://acme.example") == "http://acme.example"

    def test_bare_domain_gets_https(self):
        assert ensure_valid_url("acme.example") == "https://acme.example"

    def test_strips_whitespace(self):
        assert ensure_valid_url("  acme.example  ") == "https://acme.example"


class TestSaveSectionOutput:
    def test_writes_content_to_file(self, tmp_path):
        save_section_output(str(tmp_path), "overview", "section body")
        out = tmp_path / "overview.txt"
        assert out.exists()
        assert out.read_text(encoding="utf-8") == "section body"

    def test_unicode_content_preserved(self, tmp_path):
        save_section_output(str(tmp_path), "sec", "café résumé 日本語")
        assert (tmp_path / "sec.txt").read_text(encoding="utf-8") == "café résumé 日本語"

    def test_oserror_logged_not_raised(self, tmp_path, monkeypatch, caplog):
        # Use a non-existent path to trigger OSError
        bogus = tmp_path / "does_not_exist"
        # Should NOT raise
        save_section_output(str(bogus), "sec", "body")


class TestConsolidateWorkingFolder:
    def test_missing_folder_raises_value_error(self, tmp_path):
        bogus = tmp_path / "no_such"
        with pytest.raises(ValueError, match="Working folder not found"):
            consolidate_working_folder(str(bogus))

    def test_no_txt_files_raises_value_error(self, tmp_path):
        empty = tmp_path / "Acme_Corp"
        empty.mkdir()
        with pytest.raises(ValueError, match=r"No \.txt files"):
            consolidate_working_folder(str(empty))

    def test_consolidates_multiple_files(self, tmp_path):
        folder = tmp_path / "Acme_Corp"
        folder.mkdir()
        (folder / "overview.txt").write_text("overview body", encoding="utf-8")
        (folder / "products.txt").write_text("products body", encoding="utf-8")
        result_path = consolidate_working_folder(str(folder))
        assert os.path.exists(result_path)
        with open(result_path, encoding="utf-8") as f:
            content = f.read()
        assert "Acme Corp" in content  # underscores converted to spaces
        assert "Overview" in content
        assert "Products" in content
        assert "overview body" in content
        assert "products body" in content
        os.remove(result_path)

    def test_skips_empty_files(self, tmp_path):
        folder = tmp_path / "Acme"
        folder.mkdir()
        (folder / "filled.txt").write_text("content here", encoding="utf-8")
        (folder / "empty.txt").write_text("", encoding="utf-8")
        result_path = consolidate_working_folder(str(folder))
        with open(result_path, encoding="utf-8") as f:
            content = f.read()
        assert "content here" in content
        # Empty file's section header should NOT be in output
        assert "## Empty" not in content
        os.remove(result_path)

    def test_timestamped_folder_uses_parent_as_company(self, tmp_path):
        # working/Acme/2026-03-04_1530/ — company should be "Acme"
        parent = tmp_path / "Acme_Corp"
        parent.mkdir()
        run_folder = parent / "2026-03-04_1530"
        run_folder.mkdir()
        (run_folder / "s.txt").write_text("body", encoding="utf-8")
        result_path = consolidate_working_folder(str(run_folder))
        with open(result_path, encoding="utf-8") as f:
            content = f.read()
        # Company name extracted from parent
        assert "Acme Corp" in content
        os.remove(result_path)
