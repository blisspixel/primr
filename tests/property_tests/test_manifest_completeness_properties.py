"""
Property Test: Manifest Completeness

**Property 3: Manifest Completeness**
All completed jobs have required manifest fields.

**Validates: Requirements 2.2, 2.3**

This test ensures that job manifests contain all required fields
for proper job tracking and artifact retrieval.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from deploy.manifest import (
    JobCost,
    JobInputs,
    JobManifest,
    JobTiming,
    JobVersions,
    build_manifest,
)
from deploy.runner import JobSpec

# =============================================================================
# STRATEGIES
# =============================================================================

@st.composite
def job_specs(draw: st.DrawFn) -> JobSpec:
    """Generate valid job specifications."""
    job_id = draw(st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=8,
        max_size=24,
    ))
    deployment = draw(st.sampled_from(["dev", "staging", "prod"]))
    execution_id = draw(st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
        min_size=10,
        max_size=50,
    ))
    attempt = draw(st.integers(min_value=1, max_value=10))
    company_name = draw(st.text(min_size=1, max_size=100).filter(lambda x: x.strip()))
    company_url = draw(st.from_regex(r"https://[a-z]+\.[a-z]+", fullmatch=True))
    mode = draw(st.sampled_from(["scrape", "deep", "full"]))

    return JobSpec(
        job_id=job_id,
        deployment=deployment,
        execution_id=execution_id,
        attempt=attempt,
        company_name=company_name,
        company_url=company_url,
        mode=mode,
    )


@st.composite
def job_statuses(draw: st.DrawFn) -> str:
    """Generate valid job statuses."""
    return draw(st.sampled_from(["SUCCEEDED", "FAILED", "CANCELLED"]))


# =============================================================================
# REQUIRED FIELDS
# =============================================================================

REQUIRED_MANIFEST_FIELDS = [
    "job_id",
    "deployment",
    "execution_id",
    "attempt",
    "status",
    "inputs",
    "timing",
    "cost",
    "artifacts",
    "expected_artifacts",
    "versions",
]


# =============================================================================
# PROPERTY TESTS
# =============================================================================

class TestManifestCompleteness:
    """
    Property 3: Manifest Completeness

    All completed jobs have required manifest fields.

    **Validates: Requirements 2.2, 2.3**
    """

    def test_manifest_has_all_required_fields(self) -> None:
        """Manifest should have all required fields."""
        manifest = JobManifest(
            job_id="test123",
            idempotency_key="idem-key",
            deployment="prod",
            execution_id="exec-456",
            attempt=1,
            status="SUCCEEDED",
            inputs=JobInputs(company_name="Test", company_url="https://test.com", mode="full"),
            expected_artifacts=["report.md"],
            timing=JobTiming(submitted_at="2026-01-01T00:00:00Z", started_at="2026-01-01T00:01:00Z", completed_at="2026-01-01T00:15:00Z"),
            cost=JobCost(estimated_usd=1.0),
            artifacts={},
            versions=JobVersions(primr="1.0.0", runner="1.0.0"),
        )

        manifest_dict = manifest.to_dict()

        for field in REQUIRED_MANIFEST_FIELDS:
            assert field in manifest_dict, f"Missing required field: {field}"

    @given(job_specs(), job_statuses())
    @settings(max_examples=50, deadline=None)
    def test_built_manifest_has_required_fields(
        self,
        job_spec: JobSpec,
        status: str,
    ) -> None:
        """Built manifests should always have required fields."""
        import tempfile
        from pathlib import Path

        # Create temp output directory
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Build manifest
            now = datetime.now(timezone.utc)
            manifest = build_manifest(
                job_spec=job_spec,
                output_dir=output_dir,
                status=status,
                error=None if status == "SUCCEEDED" else "test error",
                submitted_at=now,
                started_at=now,
                completed_at=now,
            )

            manifest_dict = manifest.to_dict()

            # Check all required fields
            for field in REQUIRED_MANIFEST_FIELDS:
                assert field in manifest_dict, f"Missing required field: {field}"

    @given(job_specs())
    @settings(max_examples=30)
    def test_manifest_job_id_matches_spec(self, job_spec: JobSpec) -> None:
        """Manifest job_id should match the job spec."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            now = datetime.now(timezone.utc)

            manifest = build_manifest(
                job_spec=job_spec,
                output_dir=output_dir,
                status="SUCCEEDED",
                error=None,
                submitted_at=now,
                started_at=now,
                completed_at=now,
            )

            assert manifest.job_id == job_spec.job_id

    @given(job_specs())
    @settings(max_examples=30)
    def test_manifest_deployment_matches_spec(self, job_spec: JobSpec) -> None:
        """Manifest deployment should match the job spec."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            now = datetime.now(timezone.utc)

            manifest = build_manifest(
                job_spec=job_spec,
                output_dir=output_dir,
                status="SUCCEEDED",
                error=None,
                submitted_at=now,
                started_at=now,
                completed_at=now,
            )

            assert manifest.deployment == job_spec.deployment

    @given(job_specs())
    @settings(max_examples=30)
    def test_manifest_attempt_matches_spec(self, job_spec: JobSpec) -> None:
        """Manifest attempt should match the job spec."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            now = datetime.now(timezone.utc)

            manifest = build_manifest(
                job_spec=job_spec,
                output_dir=output_dir,
                status="SUCCEEDED",
                error=None,
                submitted_at=now,
                started_at=now,
                completed_at=now,
            )

            assert manifest.attempt == job_spec.attempt


class TestManifestTimestamps:
    """Test manifest timestamp requirements."""

    @given(job_specs())
    @settings(max_examples=30)
    def test_timestamps_are_iso_format(self, job_spec: JobSpec) -> None:
        """Timestamps should be in ISO 8601 format."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            now = datetime.now(timezone.utc)

            manifest = build_manifest(
                job_spec=job_spec,
                output_dir=output_dir,
                status="SUCCEEDED",
                error=None,
                submitted_at=now,
                started_at=now,
                completed_at=now,
            )

            # Check timing fields
            timing = manifest.timing
            for ts_field in ["submitted_at", "started_at", "completed_at"]:
                ts_value = getattr(timing, ts_field)
                if ts_value:
                    assert ts_value.endswith("Z"), f"{ts_field} should end with Z"
                    # Should be parseable
                    datetime.fromisoformat(ts_value.replace("Z", "+00:00"))

    @given(job_specs())
    @settings(max_examples=30)
    def test_completed_at_after_started_at(self, job_spec: JobSpec) -> None:
        """completed_at should be >= started_at."""
        import tempfile
        from datetime import timedelta
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            submitted = datetime.now(timezone.utc)
            started = submitted + timedelta(seconds=1)
            completed = started + timedelta(minutes=5)

            manifest = build_manifest(
                job_spec=job_spec,
                output_dir=output_dir,
                status="SUCCEEDED",
                error=None,
                submitted_at=submitted,
                started_at=started,
                completed_at=completed,
            )

            timing = manifest.timing
            started_dt = datetime.fromisoformat(timing.started_at.replace("Z", "+00:00"))
            completed_dt = datetime.fromisoformat(timing.completed_at.replace("Z", "+00:00"))

            assert completed_dt >= started_dt


class TestManifestSerialization:
    """Test manifest serialization/deserialization."""

    @given(job_specs(), job_statuses())
    @settings(max_examples=30)
    def test_manifest_roundtrip(self, job_spec: JobSpec, status: str) -> None:
        """Manifest should survive JSON roundtrip."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            now = datetime.now(timezone.utc)

            original = build_manifest(
                job_spec=job_spec,
                output_dir=output_dir,
                status=status,
                error=None if status == "SUCCEEDED" else "error",
                submitted_at=now,
                started_at=now,
                completed_at=now,
            )

            # Serialize and deserialize
            json_str = original.to_json()
            restored = JobManifest.from_dict(json.loads(json_str))

            # Check key fields match
            assert restored.job_id == original.job_id
            assert restored.deployment == original.deployment
            assert restored.status == original.status
            assert restored.attempt == original.attempt
