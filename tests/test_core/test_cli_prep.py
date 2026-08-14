"""Tests for ``primr prep`` command handling."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from primr.cli_prep import _create_prep_parser, is_prep_command, run_prep_cli
from primr.core.evidence_bundle import DEFAULT_MAX_PAGES as COLLECTOR_DEFAULT_MAX_PAGES
from primr.core.evidence_bundle import EvidenceBundleResult


def test_prep_command_predicate() -> None:
    assert is_prep_command(["prep", "Acme", "https://acme.example"])
    assert not is_prep_command(["skills", "Acme"])


def test_prep_help_describes_host_capability_without_vendor_roster() -> None:
    parser = _create_prep_parser()
    help_text = parser.format_help()
    normalized_help = " ".join(help_text.split())

    assert parser.get_default("max_pages") == COLLECTOR_DEFAULT_MAX_PAGES
    assert "capable agent host" in help_text
    assert "existing plan capacity" in help_text
    assert "or another host agent" not in help_text
    assert (
        "Preview collection or skill installation with zero network requests, "
        "model calls, or file writes."
    ) in normalized_help


def test_prep_dry_run_has_no_collection(tmp_path, monkeypatch, capsys) -> None:
    collect = MagicMock()
    monkeypatch.setattr("primr.cli_prep.collect_evidence_bundle", collect)

    result = run_prep_cli(
        ["prep", "Acme", "https://acme.example", "--dry-run", "--output-dir", str(tmp_path)]
    )

    assert result == 0
    collect.assert_not_called()
    output = capsys.readouterr().out
    assert "Incremental API spend: $0.00" in output
    assert "Model calls during collection: 0" in output
    assert "Network requests: 0 (dry run)" in output
    assert "Files written: 0 (dry run)" in output


def test_prep_dry_run_rejects_invalid_url(capsys) -> None:
    result = run_prep_cli(["prep", "Acme", "javascript:alert(1)", "--dry-run"])
    assert result == 2
    err = capsys.readouterr().err
    assert "Invalid public company URL" in err


def test_prep_runs_collector_and_reports_paths(tmp_path, monkeypatch, capsys) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    expected = EvidenceBundleResult(
        status="completed",
        bundle_dir=bundle,
        manifest_path=bundle / "prep_manifest.json",
        host_packet_path=bundle / "research_packet.md",
        source_index_path=bundle / "source_index.json",
        workflow_path=bundle / "HOST_WORKFLOW.md",
        pages_collected=4,
        hiring_postings=7,
        recon_collected=True,
        coverage_warnings=(),
    )
    collect = MagicMock(return_value=expected)
    monkeypatch.setattr("primr.cli_prep.collect_evidence_bundle", collect)

    result = run_prep_cli(
        ["prep", "Acme", "https://acme.example", "--max-pages", "8", "--skip-hiring"]
    )

    assert result == 0
    collect.assert_called_once_with(
        "Acme",
        "https://acme.example",
        output_root=Path("output"),
        max_pages=8,
        include_recon=True,
        include_hiring=False,
    )
    output = capsys.readouterr().out
    assert "Primr prep complete" in output
    assert "Source index:" in output
    assert "Evidence packet:" in output
    assert "Host workflow:" in output
    assert "Hiring signals: skipped" in output
    assert "Next: give the bundle" in output


def test_prep_reports_partial_bundle_and_limitations(tmp_path, monkeypatch, capsys) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    expected = EvidenceBundleResult(
        status="partial",
        bundle_dir=bundle,
        manifest_path=bundle / "prep_manifest.json",
        host_packet_path=bundle / "research_packet.md",
        source_index_path=bundle / "source_index.json",
        workflow_path=bundle / "HOST_WORKFLOW.md",
        pages_collected=0,
        hiring_postings=0,
        recon_collected=False,
        coverage_warnings=("No first-party page content was collected.",),
    )
    monkeypatch.setattr("primr.cli_prep.collect_evidence_bundle", lambda *_a, **_k: expected)

    assert run_prep_cli(["prep", "ExampleCo", "https://example.co"]) == 0

    output = capsys.readouterr().out
    assert "Primr prep partial for ExampleCo" in output
    assert "bundle is usable" in output
    assert "Coverage notes:" in output
    assert "No first-party page content was collected." in output
    assert "Manifest:" in output


def test_prep_rejects_out_of_range_page_cap(capsys) -> None:
    assert run_prep_cli(["prep", "Acme", "https://acme.example", "--max-pages", "51"]) == 2
    assert "between 1 and 50" in capsys.readouterr().err


def test_prep_cli_installs_packaged_skill(tmp_path, capsys) -> None:
    destination = tmp_path / "skills" / "primr-zero"

    code = run_prep_cli(["prep", "--install-skill", str(destination)])

    assert code == 0
    assert (destination / "SKILL.md").is_file()
    assert (destination / "references" / "report-contract.md").is_file()
    assert "installed" in capsys.readouterr().out.lower()


def test_prep_skill_install_dry_run_is_non_mutating(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    destination = Path("skills") / "primr-zero"
    expected_destination = tmp_path / destination
    install = MagicMock()
    monkeypatch.setattr("primr.cli_prep.install_bundled_skill", install)

    code = run_prep_cli(["prep", "--install-skill", str(destination), "--dry-run"])

    assert code == 0
    install.assert_not_called()
    assert not destination.exists()
    output = capsys.readouterr().out
    assert "Primr Zero skill installation plan" in output
    assert f"Requested destination: {expected_destination}" in output
    assert "Incremental API spend: $0.00" in output
    assert "Model calls: 0" in output
    assert "Network requests: 0" in output
    assert "Files written: 0 (dry run)" in output
    assert "installed" not in output.lower()


def test_prep_collection_interruption_returns_recoverable_state(
    monkeypatch,
    capsys,
) -> None:
    collect = MagicMock(side_effect=KeyboardInterrupt)
    monkeypatch.setattr("primr.cli_prep.collect_evidence_bundle", collect)
    monkeypatch.setitem(sys.modules, "primr.core.cli_errors", None)

    code = run_prep_cli(["prep", "ExampleCo", "https://example.co"])

    assert code == 130
    error = capsys.readouterr().err
    assert "Primr prep interrupted." in error
    assert "Any incomplete staging was removed." in error
    assert "Check the output directory before retrying." in error
    assert "Traceback" not in error


def test_prep_skill_install_interruption_requires_destination_inspection(
    monkeypatch,
    capsys,
) -> None:
    install = MagicMock(side_effect=KeyboardInterrupt)
    monkeypatch.setattr("primr.cli_prep.install_bundled_skill", install)

    code = run_prep_cli(["prep", "--install-skill", "relative-skill"])

    assert code == 130
    error = capsys.readouterr().err
    assert "Primr Zero skill installation interrupted." in error
    assert "Inspect the destination before using or retrying it." in error
    assert "Traceback" not in error


def test_prep_collection_failure_remains_visible(monkeypatch, capsys) -> None:
    collect = MagicMock(side_effect=RuntimeError("collector unavailable"))
    monkeypatch.setattr("primr.cli_prep.collect_evidence_bundle", collect)

    code = run_prep_cli(["prep", "ExampleCo", "https://example.co"])

    assert code == 1
    assert capsys.readouterr().err == "Primr prep failed: collector unavailable\n"


def test_prep_skill_install_failure_remains_visible(monkeypatch, capsys) -> None:
    install = MagicMock(side_effect=ValueError("unsafe destination"))
    monkeypatch.setattr("primr.cli_prep.install_bundled_skill", install)

    code = run_prep_cli(["prep", "--install-skill", "relative-skill"])

    assert code == 1
    assert capsys.readouterr().err == "Primr Zero skill installation failed: unsafe destination\n"
