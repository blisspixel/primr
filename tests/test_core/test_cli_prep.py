"""Tests for ``primr prep`` command handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from primr.core.cli_prep import is_prep_command, run_prep_cli
from primr.core.evidence_bundle import EvidenceBundleResult


def test_prep_command_predicate() -> None:
    assert is_prep_command(["prep", "Acme", "https://acme.example"])
    assert not is_prep_command(["skills", "Acme"])


def test_prep_dry_run_has_no_collection(tmp_path, monkeypatch, capsys) -> None:
    collect = MagicMock()
    monkeypatch.setattr("primr.core.cli_prep.collect_evidence_bundle", collect)

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


def test_prep_runs_collector_and_reports_paths(tmp_path, monkeypatch, capsys) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    expected = EvidenceBundleResult(
        bundle_dir=bundle,
        manifest_path=bundle / "prep_manifest.json",
        host_packet_path=bundle / "research_packet.md",
        source_index_path=bundle / "source_index.json",
        pages_collected=4,
        hiring_postings=7,
        recon_collected=True,
    )
    collect = MagicMock(return_value=expected)
    monkeypatch.setattr("primr.core.cli_prep.collect_evidence_bundle", collect)

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
    assert "Evidence packet:" in capsys.readouterr().out


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
