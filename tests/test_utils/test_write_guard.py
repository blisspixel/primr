"""Tests for the agentic-stage write allowlist (roadmap #11)."""

import pytest

from primr.utils.write_guard import (
    ArtifactWriteGuard,
    WriteGuardError,
)


@pytest.fixture
def target(tmp_path):
    path = tmp_path / "report.md"
    path.write_text("# Report\noriginal", encoding="utf-8")
    return path


class TestAllowlist:
    def test_target_write_allowed(self, target):
        guard = ArtifactWriteGuard(target)
        guard.write_text(target, "updated")
        assert target.read_text(encoding="utf-8") == "updated"

    def test_improved_variant_allowed(self, target):
        guard = ArtifactWriteGuard(target)
        improved = target.with_name("report_improved.md")
        guard.write_text(improved, "improved content")
        assert improved.read_text(encoding="utf-8") == "improved content"

    def test_sibling_file_rejected(self, target, tmp_path):
        guard = ArtifactWriteGuard(target)
        with pytest.raises(WriteGuardError, match="outside its allowlist"):
            guard.write_text(tmp_path / "other.md", "nope")

    def test_extra_allowed_admits_explicit_destinations(self, target, tmp_path):
        sidecar = tmp_path / "diagnostics_report.md"
        guard = ArtifactWriteGuard(target, extra_allowed=[sidecar])
        guard.write_text(sidecar, "sidecar content")
        assert sidecar.read_text(encoding="utf-8") == "sidecar content"

    def test_traversal_judged_after_resolution(self, target, tmp_path):
        guard = ArtifactWriteGuard(target)
        # Sneaky relative path that resolves back to an allowed file is fine...
        dotted = tmp_path / "sub" / ".." / "report.md"
        (tmp_path / "sub").mkdir()
        guard.write_text(dotted, "via traversal")
        assert target.read_text(encoding="utf-8") == "via traversal"
        # ...but one that escapes to a different file is rejected.
        escape = tmp_path / "sub" / ".." / "secrets.env"
        with pytest.raises(WriteGuardError):
            guard.check(escape)


class TestDenyList:
    def test_run_state_rejected_even_when_allowlisted(self, tmp_path):
        state = tmp_path / "_run_state.json"
        guard = ArtifactWriteGuard(tmp_path / "report.md", extra_allowed=[state])
        with pytest.raises(WriteGuardError, match="pipeline state file"):
            guard.check(state)

    def test_usage_history_rejected(self, tmp_path):
        usage = tmp_path / "usage_history.json"
        guard = ArtifactWriteGuard(tmp_path / "report.md", extra_allowed=[usage])
        with pytest.raises(WriteGuardError, match="pipeline state file"):
            guard.check(usage)

    @pytest.mark.parametrize("dirname", ["_raw_scrapes", "_hiring", "_diagnostics"])
    def test_pipeline_dirs_rejected(self, tmp_path, dirname):
        inside = tmp_path / dirname / "file.md"
        guard = ArtifactWriteGuard(tmp_path / "report.md", extra_allowed=[inside])
        with pytest.raises(WriteGuardError, match="pipeline-managed directory"):
            guard.check(inside)


class TestImproveIntegration:
    def test_improve_writes_through_guard(self, tmp_path):
        from primr.core.research_agent import improve_output_file

        report = tmp_path / "report.md"
        report.write_text("# Report\n\n## Section\nSome content here.\n", encoding="utf-8")

        result = improve_output_file(str(report), in_place=False, use_agentic=False)

        assert result is not None
        assert result.endswith("report_improved.md")
        assert (tmp_path / "report_improved.md").exists()

    def test_improve_in_place_still_works(self, tmp_path):
        from primr.core.research_agent import improve_output_file

        report = tmp_path / "report.md"
        report.write_text("# Report\n\n## Section\nSome content here.\n", encoding="utf-8")

        result = improve_output_file(str(report), in_place=True, use_agentic=False)

        assert result == str(report)
