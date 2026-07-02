"""Tests for the self-documenting output/working folder READMEs (roadmap #12)."""

from __future__ import annotations

from primr.config.config import (
    _OUTPUT_README,
    _WORKING_README,
    _ensure_dir_readme,
)


class TestEnsureDirReadme:
    def test_writes_readme_once(self, tmp_path):
        _ensure_dir_readme(str(tmp_path), _OUTPUT_README)
        readme = tmp_path / "README.md"
        assert readme.exists()
        assert "primr output/" in readme.read_text(encoding="utf-8")

    def test_never_overwrites_user_edits(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("my notes", encoding="utf-8")
        _ensure_dir_readme(str(tmp_path), _OUTPUT_README)
        assert readme.read_text(encoding="utf-8") == "my notes"

    def test_unwritable_directory_is_tolerated(self, tmp_path, monkeypatch):
        from pathlib import Path

        def deny(self, *a, **k):
            raise OSError("read-only")

        monkeypatch.setattr(Path, "write_text", deny)
        _ensure_dir_readme(str(tmp_path), _OUTPUT_README)  # must not raise
        assert not (tmp_path / "README.md").exists()

    def test_contents_state_what_is_safe_to_delete(self):
        assert "Safe to" in _OUTPUT_README
        assert "Safe to delete" in _WORKING_README
        assert "_run_state.json" in _WORKING_README
        # The guidance must send users to output/ for deliverables.
        assert "output/" in _WORKING_README
