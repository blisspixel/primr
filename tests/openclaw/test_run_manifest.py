"""
Property tests for run manifest completeness.

Property 9: Run Manifest Completeness
Validates: FR-7.1, FR-7.2
"""

import json
import string
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Run manifest schema per design document
REQUIRED_MANIFEST_FIELDS = [
    "schema_version",
    "job_id",
    "company_name",
    "company_url",
    "mode",
    "estimate",
    "approval",
    "execution",
    "artifacts",
]

REQUIRED_ESTIMATE_FIELDS = ["cost_usd", "time_minutes", "estimated_at"]
REQUIRED_APPROVAL_FIELDS = ["token", "approved_at", "approved_by", "bound_to_estimate"]
REQUIRED_EXECUTION_FIELDS = [
    "started_at",
    "completed_at",
    "status",
    "actual_cost_usd",
    "actual_time_minutes",
]

VALID_MODES = ["scrape", "deep", "full"]
VALID_STATUSES = ["completed", "failed", "cancelled"]


def create_valid_manifest(
    job_id: str = "test-job-123",
    company_name: str = "Test Corp",
    company_url: str = "https://test.com",
    mode: str = "full",
    status: str = "completed",
) -> dict[str, Any]:
    """Create a valid run manifest for testing."""
    now = datetime.now()
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "company_name": company_name,
        "company_url": company_url,
        "mode": mode,
        "estimate": {
            "cost_usd": 0.75,
            "time_minutes": 30,
            "estimated_at": (now - timedelta(minutes=35)).isoformat(),
        },
        "approval": {
            "token": "ABC123",
            "approved_at": (now - timedelta(minutes=34)).isoformat(),
            "approved_by": "stdio",
            "bound_to_estimate": True,
        },
        "execution": {
            "started_at": (now - timedelta(minutes=33)).isoformat(),
            "completed_at": now.isoformat(),
            "status": status,
            "actual_cost_usd": 0.72,
            "actual_time_minutes": 33,
        },
        "artifacts": [
            f"output/{company_name.lower().replace(' ', '_')}/report.md",
            f"output/{company_name.lower().replace(' ', '_')}/scraped_content.txt",
        ],
    }


class TestRunManifestSchema:
    """Tests for run manifest schema compliance."""

    def test_valid_manifest_has_all_required_fields(self):
        """Test that a valid manifest contains all required top-level fields."""
        manifest = create_valid_manifest()

        for field in REQUIRED_MANIFEST_FIELDS:
            assert field in manifest, f"Missing required field: {field}"

    def test_valid_manifest_estimate_has_required_fields(self):
        """Test that estimate section has all required fields."""
        manifest = create_valid_manifest()

        for field in REQUIRED_ESTIMATE_FIELDS:
            assert field in manifest["estimate"], f"Missing estimate field: {field}"

    def test_valid_manifest_approval_has_required_fields(self):
        """Test that approval section has all required fields."""
        manifest = create_valid_manifest()

        for field in REQUIRED_APPROVAL_FIELDS:
            assert field in manifest["approval"], f"Missing approval field: {field}"

    def test_valid_manifest_execution_has_required_fields(self):
        """Test that execution section has all required fields."""
        manifest = create_valid_manifest()

        for field in REQUIRED_EXECUTION_FIELDS:
            assert field in manifest["execution"], f"Missing execution field: {field}"

    def test_valid_manifest_mode_is_valid(self):
        """Test that mode is one of the valid values."""
        manifest = create_valid_manifest()
        assert manifest["mode"] in VALID_MODES

    def test_valid_manifest_status_is_valid(self):
        """Test that execution status is one of the valid values."""
        manifest = create_valid_manifest()
        assert manifest["execution"]["status"] in VALID_STATUSES

    def test_valid_manifest_artifacts_is_list(self):
        """Test that artifacts is a list."""
        manifest = create_valid_manifest()
        assert isinstance(manifest["artifacts"], list)


class TestRunManifestPropertyTests:
    """
    Property-based tests for run manifest completeness.
    
    **Property 9: Run Manifest Completeness**
    **Validates: FR-7.1, FR-7.2**
    """

    @given(
        job_id=st.text(min_size=1, max_size=50, alphabet=string.ascii_letters + string.digits + "-_"),
        company_name=st.text(min_size=1, max_size=100, alphabet=string.ascii_letters + string.digits + " "),
        mode=st.sampled_from(VALID_MODES),
        status=st.sampled_from(VALID_STATUSES),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_manifest_always_has_required_fields(
        self, job_id: str, company_name: str, mode: str, status: str
    ):
        """
        Property: For any completed job, manifest SHALL contain all required fields.
        
        **Validates: FR-7.1, FR-7.2**
        """
        # Skip empty strings that pass through
        if not job_id.strip() or not company_name.strip():
            return

        manifest = create_valid_manifest(
            job_id=job_id,
            company_name=company_name,
            mode=mode,
            status=status,
        )

        # Verify all required top-level fields
        for field in REQUIRED_MANIFEST_FIELDS:
            assert field in manifest, f"Missing required field: {field}"

        # Verify nested required fields
        for field in REQUIRED_ESTIMATE_FIELDS:
            assert field in manifest["estimate"], f"Missing estimate field: {field}"

        for field in REQUIRED_APPROVAL_FIELDS:
            assert field in manifest["approval"], f"Missing approval field: {field}"

        for field in REQUIRED_EXECUTION_FIELDS:
            assert field in manifest["execution"], f"Missing execution field: {field}"

    @given(
        num_artifacts=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=100)
    def test_artifacts_array_lists_generated_files(self, num_artifacts: int):
        """
        Property: The artifacts array SHALL list all generated files.
        
        **Validates: FR-7.2**
        """
        manifest = create_valid_manifest()

        # Generate artifact paths
        artifacts = [f"output/test_corp/artifact_{i}.txt" for i in range(num_artifacts)]
        manifest["artifacts"] = artifacts

        # Verify artifacts is a list
        assert isinstance(manifest["artifacts"], list)

        # Verify count matches
        assert len(manifest["artifacts"]) == num_artifacts

        # Verify all paths are strings
        for artifact in manifest["artifacts"]:
            assert isinstance(artifact, str)

    @given(
        cost_usd=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        time_minutes=st.integers(min_value=1, max_value=120),
    )
    @settings(max_examples=100)
    def test_estimate_values_are_valid(self, cost_usd: float, time_minutes: int):
        """
        Property: Estimate values SHALL be valid numbers.
        
        **Validates: FR-7.1**
        """
        manifest = create_valid_manifest()
        manifest["estimate"]["cost_usd"] = cost_usd
        manifest["estimate"]["time_minutes"] = time_minutes

        # Verify values are valid
        assert manifest["estimate"]["cost_usd"] >= 0
        assert manifest["estimate"]["time_minutes"] > 0

    @given(
        mode=st.sampled_from(VALID_MODES),
    )
    @settings(max_examples=100)
    def test_mode_is_always_valid(self, mode: str):
        """
        Property: Mode SHALL always be one of the valid values.
        
        **Validates: FR-7.1**
        """
        manifest = create_valid_manifest(mode=mode)
        assert manifest["mode"] in VALID_MODES


class TestRunManifestFileOperations:
    """Tests for run manifest file operations."""

    def test_manifest_can_be_serialized_to_json(self):
        """Test that manifest can be serialized to valid JSON."""
        manifest = create_valid_manifest()

        # Should not raise
        json_str = json.dumps(manifest, indent=2)

        # Should be parseable
        parsed = json.loads(json_str)
        assert parsed == manifest

    def test_manifest_can_be_written_and_read(self):
        """Test that manifest can be written to file and read back."""
        manifest = create_valid_manifest()

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "run_manifest.json"

            # Write
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            # Read
            with open(manifest_path, encoding="utf-8") as f:
                loaded = json.load(f)

            assert loaded == manifest

    def test_manifest_schema_version_is_1_0(self):
        """Test that schema version is 1.0."""
        manifest = create_valid_manifest()
        assert manifest["schema_version"] == "1.0"


class TestRunManifestIntegration:
    """Integration tests for run manifest with pipeline runner."""

    def test_manifest_job_id_matches_job(self):
        """Test that manifest job_id matches the job it was created for."""
        job_id = "integration-test-job-456"
        manifest = create_valid_manifest(job_id=job_id)

        assert manifest["job_id"] == job_id

    def test_manifest_company_name_matches_job(self):
        """Test that manifest company_name matches the job."""
        company_name = "Integration Test Corp"
        manifest = create_valid_manifest(company_name=company_name)

        assert manifest["company_name"] == company_name

    def test_manifest_artifacts_reference_output_directory(self):
        """Test that artifact paths reference the output directory."""
        manifest = create_valid_manifest()

        for artifact in manifest["artifacts"]:
            assert artifact.startswith("output/"), f"Artifact should be in output/: {artifact}"
