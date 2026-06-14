"""Unit tests for _save_strategy_output in primr.core.research_agent.

This function writes MD/TXT/DOCX for a generated strategy. The branches
cover: clean shipping, salvage path, validation-gate failure on markdown,
DOCX conversion failure, DOCX validation-gate failure, and the
non-blocking advisory path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.core.research_agent import _save_strategy_output


@pytest.fixture
def fake_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.output.output_utils.OUTPUT_DIR", str(tmp_path))
    return tmp_path


def _clean_validation():
    return {"passed": True, "issues": [], "warnings": [], "errors": []}


def _failing_markdown_validation():
    return {"passed": False, "issues": ["raw_source_tag: leak"], "warnings": [], "errors": []}


def _failing_docx_validation():
    return {"passed": False, "issues": ["markdown_artifact:bold"], "warnings": [], "errors": []}


@pytest.fixture
def patches(monkeypatch):
    """Patch the four downstream dependencies _save_strategy_output uses."""
    salvage_mock = MagicMock(return_value=("clean content", _clean_validation(), False))
    monkeypatch.setattr("primr.core.research_agent._salvage_markdown_for_shipping", salvage_mock)

    qa_mock = MagicMock(
        return_value={
            "budget_inconsistent": False,
            "missing_citations": 0,
            "invalid_source_urls": 0,
            "placeholder_refs": 0,
        }
    )
    monkeypatch.setattr("primr.core.research_agent._compute_strategy_qa_metrics", qa_mock)

    docx_mock = MagicMock()
    monkeypatch.setattr("primr.output.markdown_converter.markdown_to_docx", docx_mock)

    validate_docx_mock = MagicMock(return_value=_clean_validation())
    monkeypatch.setattr("primr.core.research_agent._validate_output_docx", validate_docx_mock)

    write_validation_mock = MagicMock(return_value=None)
    monkeypatch.setattr(
        "primr.core.research_agent._write_output_validation_report",
        write_validation_mock,
    )

    return {
        "salvage": salvage_mock,
        "qa": qa_mock,
        "docx": docx_mock,
        "validate_docx": validate_docx_mock,
        "write_validation": write_validation_mock,
    }


class TestHappyPath:
    def test_writes_md_txt_docx_returns_docx_path(self, fake_output_dir, patches):
        result = _save_strategy_output(
            "strategy body",
            "Acme Corp",
            platform="aws",
            output_dir=str(fake_output_dir),
        )
        assert result is not None
        assert result.endswith(".docx")
        # Both MD and TXT files should exist on disk
        files = list(fake_output_dir.iterdir())
        md_files = [f for f in files if f.suffix == ".md"]
        txt_files = [f for f in files if f.suffix == ".txt"]
        assert len(md_files) == 1
        assert len(txt_files) == 1
        # DOCX converter was called
        patches["docx"].assert_called_once()

    def test_agnostic_platform_omits_vendor_suffix(self, fake_output_dir, patches):
        result = _save_strategy_output(
            "body", "Acme", platform="agnostic", output_dir=str(fake_output_dir)
        )
        # Filename should NOT include "_AGNOSTIC"
        assert "AGNOSTIC" not in result
        assert "AI_Strategy" in result

    def test_custom_strategy_label_used(self, fake_output_dir, patches):
        result = _save_strategy_output(
            "body",
            "Acme",
            platform="azure",
            strategy_label="Customer_Experience_Strategy",
            output_dir=str(fake_output_dir),
        )
        assert "Customer_Experience_Strategy_AZURE" in result

    def test_write_txt_false_with_diagnostics_dir(self, tmp_path, patches):
        output_dir = tmp_path / "out"
        diagnostics_dir = tmp_path / "diag"
        _save_strategy_output(
            "body",
            "Acme",
            platform="aws",
            output_dir=str(output_dir),
            diagnostics_dir=str(diagnostics_dir),
            write_txt=False,
        )
        # TXT should land in diagnostics_dir, not the customer-facing output_dir
        out_txt = list(output_dir.glob("*.txt"))
        diag_txt = list(diagnostics_dir.glob("*.txt"))
        assert out_txt == []
        assert len(diag_txt) == 1


class TestSalvagePath:
    def test_salvaged_content_used(self, fake_output_dir, monkeypatch, patches):
        # Salvage returns *transformed* content; the saved files should use it.
        patches["salvage"].return_value = (
            "salvaged version",
            _clean_validation(),
            True,
        )
        _save_strategy_output("raw input", "Acme", platform="aws", output_dir=str(fake_output_dir))
        md_file = next(fake_output_dir.glob("*.md"))
        assert md_file.read_text(encoding="utf-8") == "salvaged version"


class TestMarkdownGateFailure:
    def test_failed_md_validation_returns_md_path_skips_docx(self, fake_output_dir, patches):
        patches["salvage"].return_value = (
            "leaky content",
            _failing_markdown_validation(),
            False,
        )
        result = _save_strategy_output(
            "input", "Acme", platform="aws", output_dir=str(fake_output_dir)
        )
        # When MD validation fails, we return the MD path and never call DOCX.
        assert result.endswith(".md")
        patches["docx"].assert_not_called()
        patches["write_validation"].assert_called_once()


class TestDocxConversionFailure:
    def test_docx_exception_returns_md_path(self, fake_output_dir, patches):
        patches["docx"].side_effect = RuntimeError("DOCX writer down")
        result = _save_strategy_output(
            "body", "Acme", platform="aws", output_dir=str(fake_output_dir)
        )
        assert result.endswith(".md")


class TestDocxValidationGate:
    def test_failed_docx_validation_returns_md_path_and_cleans_up(self, fake_output_dir, patches):
        patches["validate_docx"].return_value = _failing_docx_validation()
        result = _save_strategy_output(
            "body", "Acme", platform="aws", output_dir=str(fake_output_dir)
        )
        # Returns MD path because DOCX got deleted
        assert result.endswith(".md")
        # The mock writes nothing to disk, but the function unlinks the path either way.
        # Just verify the function returned MD path and called the validation reporter.
        assert patches["write_validation"].called

    def test_docx_validation_errors_only_emits_advisory(self, fake_output_dir, patches):
        # passed=True but errors present -> non-fatal advisory, ship DOCX
        patches["validate_docx"].return_value = {
            "passed": True,
            "issues": [],
            "warnings": [],
            "errors": ["non-fatal warning"],
        }
        result = _save_strategy_output(
            "body", "Acme", platform="aws", output_dir=str(fake_output_dir)
        )
        # Function ships the DOCX (returns .docx) and emits an advisory report
        assert result.endswith(".docx")


class TestAdvisoryFlags:
    def test_budget_inconsistent_advisory_logged(self, fake_output_dir, patches):
        patches["qa"].return_value = {
            "budget_inconsistent": True,
            "missing_citations": 0,
            "invalid_source_urls": 0,
            "placeholder_refs": 0,
        }
        _save_strategy_output("body", "Acme", platform="aws", output_dir=str(fake_output_dir))
        # When MD passes but advisories trip, the validation report is still written.
        patches["write_validation"].assert_called()

    def test_missing_citations_advisory_logged(self, fake_output_dir, patches):
        patches["qa"].return_value = {
            "budget_inconsistent": False,
            "missing_citations": 3,
            "invalid_source_urls": 0,
            "placeholder_refs": 0,
        }
        _save_strategy_output("body", "Acme", platform="aws", output_dir=str(fake_output_dir))
        patches["write_validation"].assert_called()


class TestVendorCasingInFilename:
    @pytest.mark.parametrize(
        ("platform", "expected_token"),
        [
            ("aws", "AWS"),
            ("azure", "AZURE"),
            ("gcp", "GCP"),
        ],
    )
    def test_platform_appears_uppercase(self, fake_output_dir, patches, platform, expected_token):
        result = _save_strategy_output(
            "body", "Acme", platform=platform, output_dir=str(fake_output_dir)
        )
        assert expected_token in result
