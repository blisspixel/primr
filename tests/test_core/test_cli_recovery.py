"""Unit tests for primr.core.cli_recovery.

Focused tests for the filename-sanitizer, recovered-basename builder,
file-saver, latest-run-state finder, and end-to-end resume command.
"""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from primr.core import cli_recovery
from primr.core.cli_recovery import (
    _build_recovered_basename,
    _find_latest_run_state,
    _safe_interaction_fragment,
    _sanitize_output_stem,
    _save_recovered_outputs,
    _show_latest_run_state_hint,
    resume_pending_jobs,
)


@pytest.fixture(autouse=True)
def _bridge_pending_job_test_seam(monkeypatch):
    """Keep legacy test fixtures explicit while production reads fail closed."""
    import primr.ai.deep_research as deep_research

    monkeypatch.setattr(
        cli_recovery,
        "_read_pending_jobs",
        lambda: (True, deep_research.get_pending_jobs()),
    )


# ---------------------------------------------------------------------------
# _sanitize_output_stem
# ---------------------------------------------------------------------------


class TestSanitizeOutputStem:
    def test_strips_disallowed_chars(self):
        assert _sanitize_output_stem("Acme Corp / Inc!") == "Acme_Corp_Inc"

    def test_collapses_internal_spaces(self):
        assert _sanitize_output_stem("Acme   Corp") == "Acme_Corp"

    def test_collapses_multiple_underscores(self):
        assert _sanitize_output_stem("__Acme__Corp__") == "Acme_Corp"

    def test_preserves_hyphens(self):
        assert _sanitize_output_stem("co-located-team") == "co-located-team"

    def test_falls_back_to_recovered(self):
        assert _sanitize_output_stem("") == "Recovered"
        assert _sanitize_output_stem("!!!") == "Recovered"
        assert _sanitize_output_stem(None) == "Recovered"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _build_recovered_basename
# ---------------------------------------------------------------------------


class TestBuildRecoveredBasename:
    def _job(self, **metadata):
        return {"type": "deep_research", "metadata": metadata}

    def test_ai_strategy_with_vendor(self):
        name = _build_recovered_basename(
            "iid",
            self._job(company_name="ExampleCo", cloud_vendor="aws", report_kind="ai_strategy"),
        )
        date_str = datetime.now().strftime("%m-%d-%Y")
        assert name == f"ExampleCo_AI_Strategy_AWS_{date_str}"

    def test_ai_strategy_agnostic_vendor_omits_tag(self):
        name = _build_recovered_basename(
            "iid",
            self._job(
                company_name="ExampleCo",
                cloud_vendor="agnostic",
                report_kind="ai_strategy",
            ),
        )
        assert "agnostic" not in name.lower()
        assert "AI_Strategy" in name

    def test_legacy_strategy_type_field(self):
        # When metadata uses strategy_type instead of report_kind
        name = _build_recovered_basename(
            "iid",
            self._job(company_name="ExampleCo", strategy_type="ai", cloud_vendor="azure"),
        )
        assert "AI_Strategy_AZURE" in name

    @pytest.mark.parametrize(
        ("kind", "expected_label"),
        [
            ("customer_experience", "Customer_Experience_Strategy"),
            ("modern_security_compliance", "Modern_Security_Compliance_Strategy"),
            ("data_fabric_strategy", "Data_Fabric_Strategy"),
        ],
    )
    def test_other_strategy_kinds(self, kind, expected_label):
        name = _build_recovered_basename(
            "iid",
            self._job(company_name="ExampleCo", report_kind=kind),
        )
        assert expected_label in name
        assert "ExampleCo" in name

    def test_strategic_overview(self):
        name = _build_recovered_basename(
            "iid",
            self._job(company_name="ExampleCo", report_kind="strategic_overview"),
        )
        assert "Strategic_Overview" in name
        assert "ExampleCo" in name

    def test_falls_back_to_recovered_pattern(self):
        # No report_kind, no strategy_type -> falls back to recovered_<type>_<id8>
        name = _build_recovered_basename("abc12345xyz", {"type": "deep_research"})
        token = _safe_interaction_fragment("abc12345xyz")
        assert name.startswith(f"recovered_deep_research_{token}")

    def test_non_dict_metadata_treated_as_empty(self):
        name = _build_recovered_basename(
            "abc12345xyz", {"type": "deep_research", "metadata": "not a dict"}
        )
        token = _safe_interaction_fragment("abc12345xyz")
        assert name.startswith(f"recovered_deep_research_{token}")

    def test_interaction_fragments_resist_separator_collisions(self):
        first = _safe_interaction_fragment("a/b")
        second = _safe_interaction_fragment("a\\b")

        assert first != second
        assert "/" not in first
        assert "\\" not in first
        assert "/" not in second
        assert "\\" not in second


# ---------------------------------------------------------------------------
# _save_recovered_outputs
# ---------------------------------------------------------------------------


class TestSaveRecoveredOutputs:
    def test_real_converter_publishes_verified_bundle(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))
        job = {
            "type": "deep_research",
            "metadata": {"company_name": "ExampleCo", "report_kind": "strategic_overview"},
        }

        outputs = _save_recovered_outputs("iid-real", job, "# Title\n\nRecovered body")

        assert set(outputs) == {"md", "txt", "docx"}
        assert all(
            Path(path).is_file() and Path(path).stat().st_size > 0 for path in outputs.values()
        )
        assert zipfile.is_zipfile(outputs["docx"])
        assert not list(tmp_path.glob(".primr-recovery-*"))

    def test_writes_md_and_txt_and_calls_docx_converter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))

        job = {
            "type": "deep_research",
            "metadata": {
                "company_name": "ExampleCo",
                "cloud_vendor": "aws",
                "report_kind": "ai_strategy",
            },
        }
        content = "# Title\n\nbody text"

        def render_docx(**kwargs):
            Path(kwargs["output_path"]).write_bytes(b"docx")

        with patch(
            "primr.output.markdown_converter.markdown_to_docx", side_effect=render_docx
        ) as docx_mock:
            outputs = _save_recovered_outputs("iid-abc-12345", job, content)

        assert outputs["md"].endswith(".md")
        assert outputs["txt"].endswith(".txt")
        assert outputs["docx"].endswith(".docx")
        with open(outputs["md"], encoding="utf-8") as f:
            assert "body text" in f.read()
        with open(outputs["txt"], encoding="utf-8") as f:
            assert "body text" in f.read()
        docx_mock.assert_called_once()

    def test_title_branches_for_kinds(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))

        for kind, expected_prefix in [
            ("strategic_overview", "Strategic Overview"),
            ("ai_strategy", "AI Strategy"),
            ("other_unknown_kind", "Recovered Research"),
        ]:

            def render_docx(**kwargs):
                Path(kwargs["output_path"]).write_bytes(b"docx")

            with patch(
                "primr.output.markdown_converter.markdown_to_docx", side_effect=render_docx
            ) as docx_mock:
                job = {
                    "type": "deep_research",
                    "metadata": {"company_name": "ExampleCo", "report_kind": kind},
                }
                _save_recovered_outputs("iid", job, "body")
                _args, kwargs = docx_mock.call_args
                assert kwargs["title"].startswith(f"{expected_prefix}: ExampleCo")

    def test_conversion_failure_publishes_no_canonical_siblings(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))
        job = {
            "type": "deep_research",
            "metadata": {"company_name": "ExampleCo", "report_kind": "strategic_overview"},
        }

        with (
            patch(
                "primr.output.markdown_converter.markdown_to_docx",
                side_effect=RuntimeError("render failed"),
            ),
            pytest.raises(RuntimeError, match="render failed"),
        ):
            _save_recovered_outputs("iid", job, "body")

        assert list(tmp_path.glob("ExampleCo_Strategic_Overview_*.*")) == []
        assert list(tmp_path.glob(".primr-recovery-*")) == []

    def test_zero_byte_docx_publishes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))
        job = {"type": "deep_research"}

        def render_empty_docx(**kwargs):
            Path(kwargs["output_path"]).touch()

        with (
            patch(
                "primr.output.markdown_converter.markdown_to_docx",
                side_effect=render_empty_docx,
            ),
            pytest.raises(RuntimeError, match="empty"),
        ):
            _save_recovered_outputs("iid", job, "body")

        assert list(tmp_path.iterdir()) == []

    def test_promotion_failure_removes_new_outputs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))
        job = {"type": "deep_research"}

        def render_docx(**kwargs):
            Path(kwargs["output_path"]).write_bytes(b"docx")

        real_replace = cli_recovery.atomic_replace
        failed = False

        def fail_txt_promotion(src, dst):
            nonlocal failed
            src_path = Path(src)
            dst_path = Path(dst)
            if not failed and dst_path.parent == tmp_path and dst_path.suffix == ".txt":
                failed = True
                raise PermissionError("locked")
            return real_replace(src_path, dst_path)

        with (
            patch("primr.output.markdown_converter.markdown_to_docx", side_effect=render_docx),
            patch("primr.core.cli_recovery.atomic_replace", side_effect=fail_txt_promotion),
            pytest.raises(PermissionError, match="locked"),
        ):
            _save_recovered_outputs("iid", job, "body")

        assert not list(tmp_path.glob("recovered_deep_research_iid_*.*"))
        assert not list(tmp_path.glob(".primr-recovery-*"))

    def test_promotion_failure_restores_existing_outputs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))
        job = {"type": "deep_research"}
        base_name = _build_recovered_basename("iid", job)
        existing = {suffix: tmp_path / f"{base_name}.{suffix}" for suffix in ("md", "txt", "docx")}
        for suffix, path in existing.items():
            path.write_bytes(f"old-{suffix}".encode())

        def render_docx(**kwargs):
            Path(kwargs["output_path"]).write_bytes(b"new-docx")

        real_replace = cli_recovery.atomic_replace
        failed = False

        def fail_txt_promotion(src, dst):
            nonlocal failed
            src_path = Path(src)
            dst_path = Path(dst)
            is_staged_publish = src_path.parent.name.startswith(".primr-recovery-")
            if (
                not failed
                and is_staged_publish
                and dst_path.parent == tmp_path
                and dst_path.suffix == ".txt"
            ):
                failed = True
                raise PermissionError("locked")
            return real_replace(src_path, dst_path)

        with (
            patch("primr.output.markdown_converter.markdown_to_docx", side_effect=render_docx),
            patch("primr.core.cli_recovery.atomic_replace", side_effect=fail_txt_promotion),
            pytest.raises(PermissionError, match="locked"),
        ):
            _save_recovered_outputs("iid", job, "new body")

        for suffix, path in existing.items():
            assert path.read_bytes() == f"old-{suffix}".encode()
        assert not list(tmp_path.glob(".primr-recovery-*"))

    def test_keyboard_interrupt_restores_existing_outputs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))
        job = {"type": "deep_research"}
        base_name = _build_recovered_basename("iid", job)
        existing = {suffix: tmp_path / f"{base_name}.{suffix}" for suffix in ("md", "txt", "docx")}
        for suffix, path in existing.items():
            path.write_bytes(f"old-{suffix}".encode())

        def render_docx(**kwargs):
            Path(kwargs["output_path"]).write_bytes(b"new-docx")

        real_replace = cli_recovery.atomic_replace
        interrupted = False

        def interrupt_txt_promotion(src, dst):
            nonlocal interrupted
            src_path = Path(src)
            dst_path = Path(dst)
            if (
                not interrupted
                and src_path.parent.name.startswith(".primr-recovery-")
                and dst_path.parent == tmp_path
                and dst_path.suffix == ".txt"
            ):
                interrupted = True
                raise KeyboardInterrupt
            return real_replace(src_path, dst_path)

        with (
            patch("primr.output.markdown_converter.markdown_to_docx", side_effect=render_docx),
            patch("primr.core.cli_recovery.atomic_replace", side_effect=interrupt_txt_promotion),
            pytest.raises(KeyboardInterrupt),
        ):
            _save_recovered_outputs("iid", job, "new body")

        for suffix, path in existing.items():
            assert path.read_bytes() == f"old-{suffix}".encode()
        assert not list(tmp_path.glob(".primr-recovery-*"))

    def test_staged_docx_symlink_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))
        external = tmp_path.parent / f"{tmp_path.name}-external-docx"
        external.write_bytes(b"external")

        def render_symlink(**kwargs):
            try:
                os.symlink(external, kwargs["output_path"])
            except OSError as exc:
                pytest.skip(f"symlink creation unavailable: {exc}")

        with (
            patch(
                "primr.output.markdown_converter.markdown_to_docx",
                side_effect=render_symlink,
            ),
            pytest.raises(RuntimeError, match="missing or empty"),
        ):
            _save_recovered_outputs("iid", {"type": "deep_research"}, "body")

        assert external.read_bytes() == b"external"
        assert not list(tmp_path.glob("recovered_deep_research_*.*"))

    def test_preexisting_output_symlink_is_not_replaced(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))
        job = {"type": "deep_research"}
        base_name = _build_recovered_basename("iid", job)
        external = tmp_path.parent / f"{tmp_path.name}-existing-target"
        external.write_bytes(b"external")
        linked_output = tmp_path / f"{base_name}.md"
        try:
            os.symlink(external, linked_output)
        except OSError as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")

        with pytest.raises(RuntimeError, match="symbolic-link"):
            _save_recovered_outputs("iid", job, "body")

        assert linked_output.is_symlink()
        assert external.read_bytes() == b"external"


# ---------------------------------------------------------------------------
# _find_latest_run_state
# ---------------------------------------------------------------------------


class TestFindLatestRunState:
    def test_returns_none_when_no_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "WORKING_DIR", str(tmp_path))
        assert _find_latest_run_state() is None

    def test_returns_newest_by_mtime(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "WORKING_DIR", str(tmp_path))
        older = tmp_path / "Co" / "older"
        newer = tmp_path / "Co" / "newer"
        older.mkdir(parents=True)
        newer.mkdir(parents=True)
        older_state = older / "_run_state.json"
        newer_state = newer / "_run_state.json"
        older_state.write_text(json.dumps({"company_name": "Old"}), encoding="utf-8")
        newer_state.write_text(json.dumps({"company_name": "New"}), encoding="utf-8")
        os.utime(older_state, (100, 100))
        os.utime(newer_state, (200, 200))

        found = _find_latest_run_state()
        assert found is not None
        _, state = found
        assert state["company_name"] == "New"

    def test_skips_corrupt_newer_file_and_returns_older_valid(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "WORKING_DIR", str(tmp_path))
        older = tmp_path / "Co" / "older"
        newer = tmp_path / "Co" / "newer_bad"
        older.mkdir(parents=True)
        newer.mkdir(parents=True)
        older_state = older / "_run_state.json"
        newer_state = newer / "_run_state.json"
        older_state.write_text(json.dumps({"company_name": "OK"}), encoding="utf-8")
        newer_state.write_text("{not-json", encoding="utf-8")
        os.utime(older_state, (100, 100))
        os.utime(newer_state, (200, 200))

        found = _find_latest_run_state()
        assert found is not None
        assert found[1]["company_name"] == "OK"

    def test_skips_non_dict_top_level(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "WORKING_DIR", str(tmp_path))
        d = tmp_path / "Co" / "run"
        d.mkdir(parents=True)
        (d / "_run_state.json").write_text("[1,2,3]", encoding="utf-8")
        assert _find_latest_run_state() is None


# ---------------------------------------------------------------------------
# _show_latest_run_state_hint
# ---------------------------------------------------------------------------


class TestShowLatestRunStateHint:
    def test_no_op_when_no_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "WORKING_DIR", str(tmp_path))
        # No state files anywhere, so the function returns silently.
        _show_latest_run_state_hint()

    def test_prints_summary_when_state_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "WORKING_DIR", str(tmp_path))
        d = tmp_path / "Co" / "run"
        d.mkdir(parents=True)
        (d / "_run_state.json").write_text(
            json.dumps(
                {
                    "company_name": "ExampleCo",
                    "mode": "fast",
                    "status": "running",
                    "current_phase": "scrape",
                    "updated_at": "2026-05-18T10:00:00",
                }
            ),
            encoding="utf-8",
        )
        with patch("primr.core.cli_recovery.console") as console_mock:
            _show_latest_run_state_hint()
        # Multiple info() calls; at least one mentions our company.
        all_calls = " ".join(str(call) for call in console_mock.info.call_args_list)
        assert "ExampleCo" in all_calls
        assert "--resume-local" in all_calls

    def test_derives_company_from_path_and_omits_unknown_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_recovery, "WORKING_DIR", str(tmp_path))
        run_dir = tmp_path / "ExampleCo" / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "_run_state.json").write_text(
            json.dumps({"updated_at": "2026-07-10T12:00:00"}),
            encoding="utf-8",
        )

        with patch("primr.core.cli_recovery.console") as console_mock:
            _show_latest_run_state_hint()

        all_calls = " ".join(str(call) for call in console_mock.info.call_args_list)
        assert "Company: ExampleCo" in all_calls
        assert "Updated: 2026-07-10T12:00:00" in all_calls
        assert "unknown" not in all_calls.lower()


# ---------------------------------------------------------------------------
# resume_pending_jobs (orchestration paths)
# ---------------------------------------------------------------------------


class TestResumePendingJobs:
    def test_returns_0_when_no_pending(self, monkeypatch):
        import primr.ai.deep_research as dr

        monkeypatch.setattr(dr, "get_pending_jobs", dict)
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: Mock())
        # _show_latest_run_state_hint walks the filesystem; isolate it.
        with patch("primr.core.cli_recovery._show_latest_run_state_hint"):
            assert resume_pending_jobs() == 0

    def test_unreadable_registry_returns_nonzero_without_creating_client(self, monkeypatch, capsys):
        import primr.ai.deep_research as dr

        client_factory = Mock()
        monkeypatch.setattr(cli_recovery, "_read_pending_jobs", lambda: (False, {}))
        monkeypatch.setattr(dr, "get_deep_research_client", client_factory)

        assert resume_pending_jobs() == 1
        client_factory.assert_not_called()
        assert "could not read the recovery registry" in capsys.readouterr().out

    def test_returns_1_on_check_error(self, monkeypatch):
        client = Mock()
        client.check_job.return_value = {
            "status": "check_error",
            "error": "Server disconnected",
        }
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr, "get_pending_jobs", lambda: {"j1": {"description": "x", "type": "deep_research"}}
        )
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        assert resume_pending_jobs() == 1

    def test_returns_0_on_in_progress_only(self, monkeypatch):
        client = Mock()
        client.check_job.return_value = {"status": "in_progress"}
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr, "get_pending_jobs", lambda: {"j1": {"description": "x", "type": "deep_research"}}
        )
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        assert resume_pending_jobs() == 0

    def test_empty_content_treated_as_failure(self, monkeypatch):
        client = Mock()
        client.check_job.return_value = {"status": "completed", "content": ""}
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr, "get_pending_jobs", lambda: {"j1": {"description": "x", "type": "deep_research"}}
        )
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        # No finalized, one failed -> returns 1
        assert resume_pending_jobs() == 1

    def test_removes_completed_job_only_after_outputs_are_saved(self, monkeypatch):
        client = Mock()
        client.check_job.return_value = {"status": "completed", "content": "Final content"}
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr, "get_pending_jobs", lambda: {"j1": {"description": "x", "type": "deep_research"}}
        )
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        with (
            patch(
                "primr.core.cli_recovery._save_recovered_outputs",
                return_value={"md": "a.md", "docx": "a.docx", "txt": "a.txt"},
            ),
            patch(
                "primr.ai.job_persistence.acknowledge_pending_job_after_outputs",
                return_value=True,
            ) as acknowledge_mock,
        ):
            assert resume_pending_jobs() == 0

        acknowledge_mock.assert_called_once()
        interaction_id, paths = acknowledge_mock.call_args.args
        assert interaction_id == "j1"
        assert list(paths) == ["a.md", "a.docx", "a.txt"]

    def test_keeps_completed_job_when_finalization_fails(self, tmp_path, monkeypatch):
        client = Mock()
        client.check_job.return_value = {"status": "completed", "content": "Final content"}
        import primr.ai.deep_research as dr

        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))
        monkeypatch.setattr(
            dr, "get_pending_jobs", lambda: {"j1": {"description": "x", "type": "deep_research"}}
        )
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        with (
            patch(
                "primr.core.cli_recovery._save_recovered_outputs",
                side_effect=RuntimeError("docx fail"),
            ),
            patch("primr.ai.job_persistence.remove_pending_job") as remove_mock,
        ):
            assert resume_pending_jobs() == 1

        remove_mock.assert_not_called()

    def test_fallback_write_failure_does_not_abort_later_jobs(self, tmp_path, monkeypatch):
        client = Mock()
        client.check_job.side_effect = [
            {"status": "completed", "content": "First"},
            {"status": "completed", "content": "Second"},
        ]
        import primr.ai.deep_research as dr

        monkeypatch.setattr(cli_recovery, "OUTPUT_DIR", str(tmp_path))
        monkeypatch.setattr(
            dr,
            "get_pending_jobs",
            lambda: {
                "j1": {"description": "first", "type": "deep_research"},
                "j2": {"description": "second", "type": "deep_research"},
            },
        )
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        with (
            patch(
                "primr.core.cli_recovery._save_recovered_outputs",
                side_effect=[
                    RuntimeError("render failed"),
                    {"md": "b.md", "txt": "b.txt", "docx": "b.docx"},
                ],
            ),
            patch(
                "primr.core.cli_recovery.atomic_write_text",
                side_effect=PermissionError("fallback locked"),
            ),
            patch(
                "primr.ai.job_persistence.acknowledge_pending_job_after_outputs",
                return_value=True,
            ) as acknowledge,
            patch("primr.core.cli_recovery.console") as console_mock,
        ):
            assert resume_pending_jobs() == 1

        assert client.check_job.call_count == 2
        acknowledge.assert_called_once()
        errors = " ".join(str(call) for call in console_mock.error.call_args_list)
        assert "Fallback TXT could not be saved" in errors

    def test_fallback_path_rejection_does_not_abort_later_jobs(self, monkeypatch):
        client = Mock()
        client.check_job.side_effect = [
            {"status": "completed", "content": "First"},
            {"status": "completed", "content": "Second"},
        ]
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr,
            "get_pending_jobs",
            lambda: {
                "j1": {"description": "first", "type": "deep_research"},
                "j2": {"description": "second", "type": "deep_research"},
            },
        )
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        with (
            patch(
                "primr.core.cli_recovery._save_recovered_outputs",
                side_effect=[
                    RuntimeError("render failed"),
                    {"md": "b.md", "txt": "b.txt", "docx": "b.docx"},
                ],
            ),
            patch(
                "primr.core.cli_recovery._recovery_output_path",
                side_effect=RuntimeError("symbolic-link recovery output"),
            ),
            patch(
                "primr.ai.job_persistence.acknowledge_pending_job_after_outputs",
                return_value=True,
            ) as acknowledge,
            patch("primr.core.cli_recovery.console") as console_mock,
        ):
            assert resume_pending_jobs() == 1

        assert client.check_job.call_count == 2
        acknowledge.assert_called_once()
        errors = " ".join(str(call) for call in console_mock.error.call_args_list)
        assert "Fallback TXT could not be saved" in errors

    def test_removes_provider_terminal_failure_during_explicit_resume(self, monkeypatch):
        client = Mock()
        client.check_job.return_value = {
            "status": "failed",
            "error": "provider error",
            "terminal": True,
        }
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr, "get_pending_jobs", lambda: {"j1": {"description": "x", "type": "deep_research"}}
        )
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        with patch("primr.ai.job_persistence.remove_pending_job") as remove_mock:
            assert resume_pending_jobs() == 1

        remove_mock.assert_called_once_with("j1")

    def test_unknown_status_counts_as_failure(self, monkeypatch):
        client = Mock()
        client.check_job.return_value = {"status": "weird_state"}
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr, "get_pending_jobs", lambda: {"j1": {"description": "x", "type": "deep_research"}}
        )
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        assert resume_pending_jobs() == 1
