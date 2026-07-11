from datetime import datetime, timezone

import pytest

from primr.job_status import build_job_status, build_job_status_list, normalize_lifecycle_state


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pending", "queued"),
        ("accepted", "queued"),
        ("running", "in_progress"),
        ("requires_action", "requires_action"),
        ("succeeded", "completed"),
        ("expired", "failed"),
        ("canceled", "cancelled"),
        ("check_error", "unknown"),
        ("new-provider-state", "unknown"),
    ],
)
def test_normalize_lifecycle_state(raw, expected):
    assert normalize_lifecycle_state(raw) == expected


def test_snapshot_is_stable_allowlisted_and_normalizes_time():
    snapshot = build_job_status(
        job_id="job-1",
        source="agent_job",
        status="running",
        company_name="Acme",
        mode="full",
        stage="writing",
        percent=140,
        started_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
        artifacts_available=False,
    )
    assert set(snapshot) == {
        "schema",
        "schema_version",
        "job_id",
        "source",
        "lifecycle_state",
        "company_name",
        "mode",
        "progress",
        "timestamps",
        "artifacts_available",
        "error",
    }
    assert snapshot["lifecycle_state"] == "in_progress"
    assert snapshot["progress"]["percent"] == 100
    assert snapshot["timestamps"]["started_at"] == "2026-07-10T00:00:00Z"
    assert not ({"content", "result", "output_path", "artifact_url"} & set(snapshot))


def test_observation_error_is_not_a_failed_job():
    snapshot = build_job_status(
        source="provider_recovery",
        status="check_error",
        error_message="network down",
        error_source="local",
    )
    assert snapshot["lifecycle_state"] == "unknown"
    assert snapshot["error"]["kind"] == "observation"


def test_naive_timestamp_is_interpreted_in_local_timezone():
    naive = datetime(2026, 7, 10, 12, 0)
    snapshot = build_job_status(source="api_job", status="running", started_at=naive)
    expected = naive.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    assert snapshot["timestamps"]["started_at"] == expected


def test_list_envelope_is_versioned():
    assert build_job_status_list([]) == {
        "schema": "primr.job-status-list",
        "schema_version": "1.0",
        "jobs": [],
    }
