"""Tests for durable host-level positive markers."""

from __future__ import annotations

import json

import pytest

from primr.data.scraping import host_markers
from primr.data.scraping.models import PageAccessAssessment, PageAccessState


@pytest.fixture(autouse=True)
def isolated_marker_state(tmp_path, monkeypatch):
    monkeypatch.setattr(host_markers, "STATE_FILE", tmp_path / "host_markers.json")
    host_markers.reset_all_for_testing()
    yield
    host_markers.reset_all_for_testing()


def test_record_positive_markers_normalizes_bounds_and_filters_sensitive_values():
    stored = host_markers.record_positive_markers(
        "https://www.example.com/private?token=leak",
        [
            "ExampleCo",
            "company",
            "api-key",
            "a1b2c3d4e5f6g7h8i9j0",
            "ExampleCo",
            "North America",
        ],
    )

    assert stored == ["exampleco", "north america"]
    assert host_markers.get_positive_markers("www.example.com") == stored

    payload = json.loads(host_markers.STATE_FILE.read_text(encoding="utf-8"))
    assert list(payload["hosts"]) == ["example.com"]
    assert payload["hosts"]["example.com"]["markers"] == stored
    assert "private" not in json.dumps(payload)
    assert "token" not in json.dumps(payload)


def test_learn_positive_markers_requires_success_and_matched_expected_markers():
    rejected = PageAccessAssessment(
        state=PageAccessState.SOFT_BLOCK,
        reason="challenge",
        confidence=0.9,
        matched_expected_markers=["exampleco"],
        matched_challenge_markers=["verify you are human"],
    )
    assert host_markers.learn_positive_markers("example.com", rejected, ["ExampleCo"]) == []

    accepted = PageAccessAssessment(
        state=PageAccessState.SUCCESS,
        reason="real page",
        confidence=0.9,
        matched_expected_markers=["exampleco", "company"],
    )
    learned = host_markers.learn_positive_markers(
        "https://www.example.com/", accepted, ["ExampleCo", "company", "MissingCo"]
    )

    assert learned == ["exampleco"]
    assert host_markers.get_positive_markers("example.com") == ["exampleco"]
