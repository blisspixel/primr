"""Tests for company-name path-traversal containment in output utils.

``company_name`` is sanitized at the input boundary (``validate_company_name``
rejects ``/``, ``\\``, ``..``, and drive prefixes), but the report writers are
the last line of defense in front of a destructive ``shutil.rmtree``. These
tests pin the sink-level guard so a malicious or unvalidated name can never
zip or delete a directory outside WORKING_DIR.
"""

from __future__ import annotations

import pytest

from primr.output import output_utils


@pytest.fixture
def isolated_dirs(monkeypatch, tmp_path):
    """Point WORKING_DIR / OUTPUT_DIR at a throwaway tmp tree."""
    work = tmp_path / "working"
    out = tmp_path / "output"
    work.mkdir()
    out.mkdir()
    monkeypatch.setattr(output_utils, "WORKING_DIR", str(work))
    monkeypatch.setattr(output_utils, "OUTPUT_DIR", str(out))
    return tmp_path, work, out


def test_safe_working_subdir_allows_normal_name(isolated_dirs):
    _, work, _ = isolated_dirs
    result = output_utils._safe_working_subdir("Acme Corp")
    assert result == (work / "Acme_Corp").resolve()


@pytest.mark.parametrize(
    "malicious",
    ["../victim", "../../etc", "..\\..\\windows", "a/../../../b"],
)
def test_safe_working_subdir_rejects_traversal(isolated_dirs, malicious):
    with pytest.raises(ValueError, match="outside the working directory"):
        output_utils._safe_working_subdir(malicious)


def test_safe_working_subdir_rejects_absolute(isolated_dirs):
    tmp_path, _, _ = isolated_dirs
    abs_target = str(tmp_path / "elsewhere")
    with pytest.raises(ValueError, match="outside the working directory"):
        output_utils._safe_working_subdir(abs_target)


@pytest.mark.parametrize("blank", ["", "."])
def test_safe_working_subdir_rejects_working_dir_itself(isolated_dirs, blank):
    # An empty or "." name resolves to WORKING_DIR itself; returning it would
    # let cleanup() rmtree the entire working dir. Require a strict subdir.
    with pytest.raises(ValueError, match="outside the working directory"):
        output_utils._safe_working_subdir(blank)


def test_cleanup_blank_name_does_not_delete_working_dir(isolated_dirs):
    _, work, _ = isolated_dirs
    keep = work / "other_company"
    keep.mkdir()
    (keep / "report.md").write_text("keep me", encoding="utf-8")

    # cleanup("") must be a no-op (guard raises, cleanup swallows), not wipe WORKING_DIR.
    output_utils.cleanup("")

    assert work.exists()
    assert keep.exists()
    assert (keep / "report.md").exists()


def test_cleanup_does_not_delete_outside_working_dir(isolated_dirs):
    tmp_path, _, _ = isolated_dirs

    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "important.txt").write_text("do not delete", encoding="utf-8")

    # A traversal company_name would resolve to the victim dir; the guard must
    # turn this into a no-op (cleanup swallows the ValueError) rather than rmtree.
    output_utils.cleanup("../victim")

    assert victim.exists(), "cleanup must not delete directories outside WORKING_DIR"
    assert (victim / "important.txt").exists()


def test_zip_research_files_does_not_escape_output_dir(isolated_dirs):
    tmp_path, _, _ = isolated_dirs

    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "secret.txt").write_text("secret", encoding="utf-8")

    # Should not raise out (zip_research_files swallows) and must not produce a
    # zip outside OUTPUT_DIR or read the out-of-tree victim folder.
    output_utils.zip_research_files("../victim")

    # No zip artifact escaped above the output root.
    assert not any(tmp_path.glob("*.zip"))
    assert victim.exists()
