"""Tests for filesystem-backed tracked-company profiles."""

from __future__ import annotations

import json

import pytest

from primr.agentic.company_profiles import (
    CompanyProfileStore,
    get_default_company_profile_path,
)
from primr.utils.validators import InputValidationError
from tests.secret_fixtures import fake_xai_api_key


def test_default_company_profile_path_uses_user_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIMR_DATA_DIR", str(tmp_path / "data"))

    path = get_default_company_profile_path()

    assert path == tmp_path / "data" / "company_profiles"
    assert path.is_dir()


def test_track_creates_profile_json(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)

    profile = store.track("Acme Corp", "https://acme.example")

    assert profile.name == "Acme Corp"
    assert profile.url == "https://acme.example"
    assert profile.freshness_status == "unrun"
    profile_path = store.profile_dir(profile) / "profile.json"
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    assert data["name"] == "Acme Corp"
    assert data["retention"]["policy"] == "keep_until_cleared"
    assert data["classification"] == "operator_data_third_party_profile"


def test_tracking_existing_profile_preserves_created_at_and_run_pointers(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)
    first = store.track("Acme Corp", "https://acme.example")
    profile_path = store.profile_dir(first) / "profile.json"
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    data["run_pointers"] = ["runs/acme/001"]
    profile_path.write_text(json.dumps(data), encoding="utf-8")

    second = store.track("Acme Corp", "https://www.acme.example")

    assert second.created_at == first.created_at
    assert second.url == "https://www.acme.example"
    assert second.run_pointers[0].run_id == "runs/acme/001"


def test_record_run_updates_profile_and_export_run_history(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)
    store.track("Acme Corp", "https://acme.example")

    profile = store.record_run(
        "Acme Corp",
        "job-20260630-acme",
        artifacts=["output/acme/report.md", "output/acme/report.docx"],
        manifest_path="output/acme/run_manifest.json",
        recorded_at="2026-06-30T12:00:00+00:00",
    )

    assert profile.last_run_at == "2026-06-30T12:00:00+00:00"
    assert profile.freshness_status == "tracked"
    assert profile.run_pointers[0].run_id == "job-20260630-acme"
    export = store.export_profile("Acme Corp")
    gap_ids = {gap["id"] for gap in export.payload["flagged_gaps"]}
    assert "run_history" not in gap_ids
    assert export.payload["run_history"][0]["manifest_path"] == "output/acme/run_manifest.json"
    markdown = export.markdown_path.read_text(encoding="utf-8")
    assert "## Run History" in markdown
    assert "job-20260630-acme [completed]" in markdown


def test_record_run_deduplicates_and_limits_run_history(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)
    store.track("Acme Corp", "https://acme.example")

    for index in range(25):
        store.record_run("Acme Corp", f"job-{index}", recorded_at=f"2026-06-30T00:{index:02}:00Z")
    store.record_run("Acme Corp", "job-3", recorded_at="2026-06-30T13:00:00Z")

    profile = store.get_profile("Acme Corp")
    assert profile is not None
    assert len(profile.run_pointers) == 20
    assert profile.run_pointers[0].run_id == "job-3"
    assert sum(pointer.run_id == "job-3" for pointer in profile.run_pointers) == 1


def test_record_run_rejects_secret_like_artifact(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)
    store.track("Acme Corp", "https://acme.example")
    secret = fake_xai_api_key()

    with pytest.raises(InputValidationError):
        store.record_run(
            "Acme Corp",
            "job-1",
            artifacts=[f"output/acme/{secret}-report.md"],
        )


def test_record_run_missing_profile_raises(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)

    with pytest.raises(InputValidationError):
        store.record_run("Missing Corp", "job-1")


def test_list_profiles_is_sorted_and_skips_malformed_files(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)
    store.track("Zulu Corp", "https://zulu.example")
    store.track("Acme Corp", "https://acme.example")
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    (bad_dir / "profile.json").write_text("{not json", encoding="utf-8")

    profiles = store.list_profiles()

    assert [profile.name for profile in profiles] == ["Acme Corp", "Zulu Corp"]


def test_get_profile_by_name(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)
    store.track("Acme Corp", "https://acme.example")

    profile = store.get_profile("Acme Corp")

    assert profile is not None
    assert profile.name == "Acme Corp"


def test_export_profile_writes_json_and_markdown_bundle(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)
    store.track("Acme Corp", "https://acme.example")

    export = store.export_profile(
        "Acme Corp",
        hypotheses=[
            {
                "id": "h1",
                "claim": "Acme is testing AI logistics",
                "confidence": "validated",
                "topic": "strategy",
                "evidence": ["public case study"],
            }
        ],
    )

    assert export.json_path.is_file()
    assert export.markdown_path.is_file()
    payload = json.loads(export.json_path.read_text(encoding="utf-8"))
    assert payload["type"] == "Company"
    assert payload["company"]["name"] == "Acme Corp"
    assert payload["hypotheses"][0]["confidence"] == "validated"
    markdown = export.markdown_path.read_text(encoding="utf-8")
    assert "type: Company" in markdown
    assert "[validated] Acme is testing AI logistics" in markdown


def test_export_profile_marks_empty_hypothesis_gap(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)
    store.track("Acme Corp", "https://acme.example")

    export = store.export_profile("Acme Corp")

    gap_ids = {gap["id"] for gap in export.payload["flagged_gaps"]}
    assert "hypotheses" in gap_ids


def test_export_missing_profile_raises(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)

    with pytest.raises(InputValidationError):
        store.export_profile("Missing Corp")


def test_export_rejects_secret_like_hypothesis_payload(tmp_path):
    store = CompanyProfileStore(root_path=tmp_path)
    store.track("Acme Corp", "https://acme.example")
    secret = fake_xai_api_key()

    with pytest.raises(InputValidationError):
        store.export_profile(
            "Acme Corp",
            hypotheses=[
                {
                    "id": "h1",
                    "claim": f"{secret} must not leave memory",
                    "confidence": "untested",
                }
            ],
        )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://acme.example",
        "https://user:pass@acme.example",
        "https://acme.example/?api_key=" + fake_xai_api_key(),
    ],
)
def test_track_rejects_unsafe_urls(tmp_path, url):
    store = CompanyProfileStore(root_path=tmp_path)

    with pytest.raises(InputValidationError):
        store.track("Acme Corp", url)
