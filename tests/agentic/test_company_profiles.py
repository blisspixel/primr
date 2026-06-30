"""Tests for filesystem-backed tracked-company profiles."""

from __future__ import annotations

import json

import pytest

from primr.agentic.company_profiles import (
    CompanyProfileStore,
    get_default_company_profile_path,
)
from primr.utils.validators import InputValidationError


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
    assert second.run_pointers == ("runs/acme/001",)


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

    with pytest.raises(InputValidationError):
        store.export_profile(
            "Acme Corp",
            hypotheses=[
                {
                    "id": "h1",
                    "claim": "xai-1234567890abcdef must not leave memory",
                    "confidence": "untested",
                }
            ],
        )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://acme.example",
        "https://user:pass@acme.example",
        "https://acme.example/?api_key=xai-1234567890abcdef",
    ],
)
def test_track_rejects_unsafe_urls(tmp_path, url):
    store = CompanyProfileStore(root_path=tmp_path)

    with pytest.raises(InputValidationError):
        store.track("Acme Corp", url)
