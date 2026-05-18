"""
Unit tests for manifest generation.

Tests:
- Manifest generation with all required fields (Requirements 2.2, 2.3)
- Checksum generation (Requirements 2.3)
- Late-writer handling (Requirements 2.6)
- Atomic writes (Requirements 2.4, 2.5)

Requirements: 2.2, 2.3, 2.4, 2.5, 2.6
"""

import hashlib
import json
from datetime import datetime, timezone

import pytest

from deploy.manifest import (
    EXPECTED_ARTIFACTS,
    ArtifactMeta,
    JobCost,
    JobInputs,
    JobManifest,
    JobTiming,
    JobVersions,
    ManifestAlreadyExistsError,
    build_manifest,
    compute_checksum,
    estimate_cost,
    format_timestamp,
    get_file_size,
    scan_artifacts,
    write_manifest_local,
    write_manifest_safe,
)


class TestArtifactMeta:
    """Tests for ArtifactMeta dataclass."""

    def test_to_dict(self):
        """Test converting ArtifactMeta to dictionary."""
        meta = ArtifactMeta(size_bytes=1024, checksum_sha256="abc123")
        data = meta.to_dict()

        assert data["size_bytes"] == 1024
        assert data["checksum_sha256"] == "abc123"

    def test_from_dict(self):
        """Test creating ArtifactMeta from dictionary."""
        data = {"size_bytes": 2048, "checksum_sha256": "def456"}
        meta = ArtifactMeta.from_dict(data)

        assert meta.size_bytes == 2048
        assert meta.checksum_sha256 == "def456"


class TestJobTiming:
    """Tests for JobTiming dataclass."""

    def test_to_dict(self):
        """Test converting JobTiming to dictionary."""
        timing = JobTiming(
            submitted_at="2026-02-03T10:00:00Z",
            started_at="2026-02-03T10:00:05Z",
            completed_at="2026-02-03T10:35:00Z",
            duration_seconds=2095,
        )
        data = timing.to_dict()

        assert data["submitted_at"] == "2026-02-03T10:00:00Z"
        assert data["started_at"] == "2026-02-03T10:00:05Z"
        assert data["completed_at"] == "2026-02-03T10:35:00Z"
        assert data["duration_seconds"] == 2095

    def test_from_dict(self):
        """Test creating JobTiming from dictionary."""
        data = {
            "submitted_at": "2026-02-03T10:00:00Z",
            "started_at": "2026-02-03T10:00:05Z",
        }
        timing = JobTiming.from_dict(data)

        assert timing.submitted_at == "2026-02-03T10:00:00Z"
        assert timing.started_at == "2026-02-03T10:00:05Z"
        assert timing.completed_at is None
        assert timing.duration_seconds is None


class TestJobCost:
    """Tests for JobCost dataclass."""

    def test_to_dict(self):
        """Test converting JobCost to dictionary."""
        cost = JobCost(
            estimated_usd=2.50,
            actual_compute_usd=0.42,
            actual_llm_usd=None,
            actual_known=False,
        )
        data = cost.to_dict()

        assert data["estimated_usd"] == 2.50
        assert data["actual_compute_usd"] == 0.42
        assert data["actual_llm_usd"] is None
        assert data["actual_known"] is False

    def test_from_dict(self):
        """Test creating JobCost from dictionary."""
        data = {"estimated_usd": 1.25}
        cost = JobCost.from_dict(data)

        assert cost.estimated_usd == 1.25
        assert cost.actual_compute_usd is None
        assert cost.actual_known is False


class TestJobInputs:
    """Tests for JobInputs dataclass."""

    def test_to_dict(self):
        """Test converting JobInputs to dictionary."""
        inputs = JobInputs(
            company_name="Acme Corp",
            company_url="https://acme.example",
            mode="full",
            options={"cloud_vendor": "aws"},
        )
        data = inputs.to_dict()

        assert data["company_name"] == "Acme Corp"
        assert data["company_url"] == "https://acme.example"
        assert data["mode"] == "full"
        assert data["options"] == {"cloud_vendor": "aws"}

    def test_from_dict(self):
        """Test creating JobInputs from dictionary."""
        data = {
            "company_name": "Test Co",
            "company_url": "https://test.example",
            "mode": "scrape",
        }
        inputs = JobInputs.from_dict(data)

        assert inputs.company_name == "Test Co"
        assert inputs.mode == "scrape"
        assert inputs.options == {}


class TestJobVersions:
    """Tests for JobVersions dataclass."""

    def test_to_dict(self):
        """Test converting JobVersions to dictionary."""
        versions = JobVersions(primr="1.5.1", runner="1.0.0")
        data = versions.to_dict()

        assert data["primr"] == "1.5.1"
        assert data["runner"] == "1.0.0"

    def test_from_dict(self):
        """Test creating JobVersions from dictionary."""
        data = {"primr": "2.0.0", "runner": "1.1.0"}
        versions = JobVersions.from_dict(data)

        assert versions.primr == "2.0.0"
        assert versions.runner == "1.1.0"


class TestJobManifest:
    """Tests for JobManifest dataclass."""

    def test_to_dict_complete(self):
        """Test converting complete JobManifest to dictionary."""
        manifest = JobManifest(
            job_id="test-123",
            idempotency_key="client-key",
            deployment="prod",
            execution_id="ecs-task-xyz",
            attempt=1,
            status="SUCCEEDED",
            inputs=JobInputs(
                company_name="Acme Corp",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=["report.docx", "report.md"],
            timing=JobTiming(
                submitted_at="2026-02-03T10:00:00Z",
                started_at="2026-02-03T10:00:05Z",
                completed_at="2026-02-03T10:35:00Z",
                duration_seconds=2095,
            ),
            cost=JobCost(estimated_usd=2.00),
            artifacts={
                "report.docx": ArtifactMeta(size_bytes=45678, checksum_sha256="abc123"),
            },
            versions=JobVersions(primr="1.5.1", runner="1.0.0"),
            error=None,
            manifest_written_by="runner",
        )

        data = manifest.to_dict()

        assert data["job_id"] == "test-123"
        assert data["idempotency_key"] == "client-key"
        assert data["deployment"] == "prod"
        assert data["execution_id"] == "ecs-task-xyz"
        assert data["attempt"] == 1
        assert data["status"] == "SUCCEEDED"
        assert data["inputs"]["company_name"] == "Acme Corp"
        assert data["expected_artifacts"] == ["report.docx", "report.md"]
        assert data["timing"]["duration_seconds"] == 2095
        assert data["cost"]["estimated_usd"] == 2.00
        assert data["artifacts"]["report.docx"]["size_bytes"] == 45678
        assert data["versions"]["primr"] == "1.5.1"
        assert data["error"] is None
        assert data["manifest_written_by"] == "runner"

    def test_to_json(self):
        """Test converting JobManifest to JSON string."""
        manifest = JobManifest(
            job_id="test-123",
            idempotency_key="key",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            status="SUCCEEDED",
            inputs=JobInputs("Test", "https://test.example", "full"),
            expected_artifacts=[],
            timing=JobTiming("2026-02-03T10:00:00Z"),
            cost=JobCost(1.0),
            artifacts={},
            versions=JobVersions("1.0.0", "1.0.0"),
        )

        json_str = manifest.to_json()
        data = json.loads(json_str)

        assert data["job_id"] == "test-123"

    def test_from_dict(self):
        """Test creating JobManifest from dictionary."""
        data = {
            "job_id": "test-456",
            "idempotency_key": "key-456",
            "deployment": "staging",
            "execution_id": "task-2",
            "attempt": 2,
            "status": "FAILED",
            "inputs": {
                "company_name": "Failed Co",
                "company_url": "https://failed.example",
                "mode": "deep",
            },
            "expected_artifacts": ["dossier.txt"],
            "timing": {
                "submitted_at": "2026-02-03T10:00:00Z",
            },
            "cost": {"estimated_usd": 1.50},
            "artifacts": {},
            "versions": {"primr": "1.5.0", "runner": "1.0.0"},
            "error": "timeout",
            "manifest_written_by": "reconciler",
        }

        manifest = JobManifest.from_dict(data)

        assert manifest.job_id == "test-456"
        assert manifest.status == "FAILED"
        assert manifest.attempt == 2
        assert manifest.error == "timeout"
        assert manifest.manifest_written_by == "reconciler"

    def test_load_from_file(self, tmp_path):
        """Test loading JobManifest from file."""
        manifest_data = {
            "job_id": "file-test",
            "idempotency_key": "key",
            "deployment": "prod",
            "execution_id": "task-1",
            "attempt": 1,
            "status": "SUCCEEDED",
            "inputs": {"company_name": "Test", "company_url": "", "mode": "full"},
            "expected_artifacts": [],
            "timing": {"submitted_at": "2026-02-03T10:00:00Z"},
            "cost": {"estimated_usd": 1.0},
            "artifacts": {},
            "versions": {"primr": "1.0.0", "runner": "1.0.0"},
        }

        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data))

        manifest = JobManifest.load(manifest_file)

        assert manifest is not None
        assert manifest.job_id == "file-test"
        assert manifest.status == "SUCCEEDED"

    def test_load_missing_file(self, tmp_path):
        """Test loading from non-existent file returns None."""
        manifest_file = tmp_path / "missing.json"
        manifest = JobManifest.load(manifest_file)

        assert manifest is None

    def test_load_invalid_json(self, tmp_path):
        """Test loading invalid JSON returns None."""
        manifest_file = tmp_path / "invalid.json"
        manifest_file.write_text("not valid json")

        manifest = JobManifest.load(manifest_file)

        assert manifest is None


class TestChecksumGeneration:
    """Tests for checksum generation."""

    def test_compute_checksum(self, tmp_path):
        """Test computing SHA-256 checksum of a file."""
        test_file = tmp_path / "test.txt"
        content = b"Hello, World!"
        test_file.write_bytes(content)

        checksum = compute_checksum(test_file)

        # Verify against known SHA-256
        expected = hashlib.sha256(content).hexdigest()
        assert checksum == expected

    def test_compute_checksum_large_file(self, tmp_path):
        """Test checksum computation for larger files."""
        test_file = tmp_path / "large.txt"
        # Create a file larger than the chunk size (8192 bytes)
        content = b"x" * 20000
        test_file.write_bytes(content)

        checksum = compute_checksum(test_file)

        expected = hashlib.sha256(content).hexdigest()
        assert checksum == expected

    def test_get_file_size(self, tmp_path):
        """Test getting file size."""
        test_file = tmp_path / "test.txt"
        content = b"Hello, World!"
        test_file.write_bytes(content)

        size = get_file_size(test_file)

        assert size == len(content)


class TestScanArtifacts:
    """Tests for artifact scanning."""

    def test_scan_artifacts_finds_files(self, tmp_path):
        """Test that scan_artifacts finds expected artifact files."""
        # Create some artifact files
        (tmp_path / "scraped_content.txt").write_text("scraped content")
        (tmp_path / "insights.txt").write_text("insights")
        (tmp_path / "report.md").write_text("# Report")

        artifacts = scan_artifacts(tmp_path)

        assert "scraped_content.txt" in artifacts
        assert "insights.txt" in artifacts
        assert "report.md" in artifacts
        assert len(artifacts) == 3

    def test_scan_artifacts_computes_checksums(self, tmp_path):
        """Test that scan_artifacts computes checksums correctly."""
        content = "test content"
        (tmp_path / "insights.txt").write_text(content)

        artifacts = scan_artifacts(tmp_path)

        expected_checksum = hashlib.sha256(content.encode()).hexdigest()
        assert artifacts["insights.txt"].checksum_sha256 == expected_checksum

    def test_scan_artifacts_ignores_underscore_files(self, tmp_path):
        """Test that files starting with underscore are ignored."""
        (tmp_path / "_heartbeat.json").write_text("{}")
        (tmp_path / "_internal.txt").write_text("internal")
        (tmp_path / "insights.txt").write_text("insights")

        artifacts = scan_artifacts(tmp_path)

        assert "_heartbeat.json" not in artifacts
        assert "_internal.txt" not in artifacts
        assert "insights.txt" in artifacts

    def test_scan_artifacts_empty_directory(self, tmp_path):
        """Test scanning empty directory returns empty dict."""
        artifacts = scan_artifacts(tmp_path)
        assert artifacts == {}


class TestBuildManifest:
    """Tests for build_manifest function."""

    def test_build_manifest_success(self, tmp_path):
        """Test building manifest for successful job."""
        # Create mock job spec
        from deploy.runner import JobSpec

        spec = JobSpec(
            job_id="test-123",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            company_name="Test Co",
            company_url="https://test.example",
            mode="full",
            options={"idempotency_key": "client-key"},
        )

        # Create some artifacts
        (tmp_path / "report.md").write_text("# Report")

        submitted = datetime(2026, 2, 3, 10, 0, 0, tzinfo=timezone.utc)
        started = datetime(2026, 2, 3, 10, 0, 5, tzinfo=timezone.utc)
        completed = datetime(2026, 2, 3, 10, 35, 0, tzinfo=timezone.utc)

        manifest = build_manifest(
            job_spec=spec,
            output_dir=tmp_path,
            status="SUCCEEDED",
            error=None,
            submitted_at=submitted,
            started_at=started,
            completed_at=completed,
        )

        assert manifest.job_id == "test-123"
        assert manifest.deployment == "prod"
        assert manifest.execution_id == "task-1"
        assert manifest.attempt == 1
        assert manifest.status == "SUCCEEDED"
        assert manifest.error is None
        assert manifest.manifest_written_by == "runner"
        assert "report.md" in manifest.artifacts
        assert manifest.timing.duration_seconds == 2095  # 34 min 55 sec

    def test_build_manifest_failure(self, tmp_path):
        """Test building manifest for failed job."""
        from deploy.runner import JobSpec

        spec = JobSpec(
            job_id="test-456",
            deployment="staging",
            execution_id="task-2",
            attempt=1,
            company_name="Failed Co",
            company_url="https://failed.example",
            mode="deep",
        )

        submitted = datetime(2026, 2, 3, 10, 0, 0, tzinfo=timezone.utc)
        started = datetime(2026, 2, 3, 10, 0, 5, tzinfo=timezone.utc)
        completed = datetime(2026, 2, 3, 10, 5, 0, tzinfo=timezone.utc)

        manifest = build_manifest(
            job_spec=spec,
            output_dir=tmp_path,
            status="FAILED",
            error="timeout",
            submitted_at=submitted,
            started_at=started,
            completed_at=completed,
        )

        assert manifest.status == "FAILED"
        assert manifest.error == "timeout"

    def test_build_manifest_expected_artifacts(self, tmp_path):
        """Test that expected_artifacts is set based on mode."""
        from deploy.runner import JobSpec

        for mode, expected in EXPECTED_ARTIFACTS.items():
            spec = JobSpec(
                job_id=f"test-{mode}",
                deployment="prod",
                execution_id="task-1",
                attempt=1,
                company_name="Test Co",
                company_url="https://test.example",
                mode=mode,
            )

            now = datetime.now(timezone.utc)
            manifest = build_manifest(
                job_spec=spec,
                output_dir=tmp_path,
                status="SUCCEEDED",
                error=None,
                submitted_at=now,
                started_at=now,
                completed_at=now,
            )

            assert manifest.expected_artifacts == expected


class TestWriteManifestLocal:
    """Tests for local manifest writing."""

    def test_write_manifest_creates_file(self, tmp_path):
        """Test that write_manifest_local creates the manifest file."""
        manifest = JobManifest(
            job_id="test-123",
            idempotency_key="key",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            status="SUCCEEDED",
            inputs=JobInputs("Test", "https://test.example", "full"),
            expected_artifacts=[],
            timing=JobTiming("2026-02-03T10:00:00Z"),
            cost=JobCost(1.0),
            artifacts={},
            versions=JobVersions("1.0.0", "1.0.0"),
        )

        write_manifest_local(tmp_path, manifest)

        manifest_file = tmp_path / "manifest.json"
        assert manifest_file.exists()

        # Verify content
        data = json.loads(manifest_file.read_text())
        assert data["job_id"] == "test-123"

    def test_write_manifest_fails_if_exists(self, tmp_path):
        """Test that write_manifest_local fails if manifest already exists."""
        # Create existing manifest
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text('{"job_id": "existing"}')

        manifest = JobManifest(
            job_id="new-123",
            idempotency_key="key",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            status="SUCCEEDED",
            inputs=JobInputs("Test", "https://test.example", "full"),
            expected_artifacts=[],
            timing=JobTiming("2026-02-03T10:00:00Z"),
            cost=JobCost(1.0),
            artifacts={},
            versions=JobVersions("1.0.0", "1.0.0"),
        )

        with pytest.raises(ManifestAlreadyExistsError):
            write_manifest_local(tmp_path, manifest)

        # Verify original manifest unchanged
        data = json.loads(manifest_file.read_text())
        assert data["job_id"] == "existing"


class TestWriteManifestSafe:
    """Tests for safe manifest writing with late-writer protection."""

    def test_write_manifest_safe_success(self, tmp_path):
        """Test successful manifest write returns True."""
        manifest = JobManifest(
            job_id="test-123",
            idempotency_key="key",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            status="SUCCEEDED",
            inputs=JobInputs("Test", "https://test.example", "full"),
            expected_artifacts=[],
            timing=JobTiming("2026-02-03T10:00:00Z"),
            cost=JobCost(1.0),
            artifacts={},
            versions=JobVersions("1.0.0", "1.0.0"),
        )

        result = write_manifest_safe(tmp_path, manifest)

        assert result is True
        assert (tmp_path / "manifest.json").exists()

    def test_write_manifest_safe_already_exists(self, tmp_path):
        """Test that write_manifest_safe returns False if manifest exists."""
        # Create existing manifest
        existing_manifest = {
            "job_id": "existing",
            "status": "SUCCEEDED",
            "idempotency_key": "key",
            "deployment": "prod",
            "execution_id": "task-1",
            "attempt": 1,
            "inputs": {"company_name": "Test", "company_url": "", "mode": "full"},
            "expected_artifacts": [],
            "timing": {"submitted_at": "2026-02-03T10:00:00Z"},
            "cost": {"estimated_usd": 1.0},
            "artifacts": {},
            "versions": {"primr": "1.0.0", "runner": "1.0.0"},
        }
        (tmp_path / "manifest.json").write_text(json.dumps(existing_manifest))

        new_manifest = JobManifest(
            job_id="new-123",
            idempotency_key="key",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            status="SUCCEEDED",
            inputs=JobInputs("Test", "https://test.example", "full"),
            expected_artifacts=[],
            timing=JobTiming("2026-02-03T10:00:00Z"),
            cost=JobCost(1.0),
            artifacts={},
            versions=JobVersions("1.0.0", "1.0.0"),
        )

        result = write_manifest_safe(tmp_path, new_manifest)

        assert result is False

        # Verify original manifest unchanged
        data = json.loads((tmp_path / "manifest.json").read_text())
        assert data["job_id"] == "existing"

    def test_late_writer_rule_succeeded(self, tmp_path):
        """Test late-writer rule: if existing manifest shows SUCCEEDED, return False."""
        existing_manifest = {
            "job_id": "existing",
            "status": "SUCCEEDED",
            "idempotency_key": "key",
            "deployment": "prod",
            "execution_id": "task-1",
            "attempt": 1,
            "inputs": {"company_name": "Test", "company_url": "", "mode": "full"},
            "expected_artifacts": [],
            "timing": {"submitted_at": "2026-02-03T10:00:00Z"},
            "cost": {"estimated_usd": 1.0},
            "artifacts": {},
            "versions": {"primr": "1.0.0", "runner": "1.0.0"},
        }
        (tmp_path / "manifest.json").write_text(json.dumps(existing_manifest))

        new_manifest = JobManifest(
            job_id="late-writer",
            idempotency_key="key",
            deployment="prod",
            execution_id="task-2",
            attempt=2,
            status="SUCCEEDED",
            inputs=JobInputs("Test", "https://test.example", "full"),
            expected_artifacts=[],
            timing=JobTiming("2026-02-03T10:00:00Z"),
            cost=JobCost(1.0),
            artifacts={},
            versions=JobVersions("1.0.0", "1.0.0"),
        )

        result = write_manifest_safe(tmp_path, new_manifest)

        # Late writer should not overwrite
        assert result is False

    def test_late_writer_rule_failed(self, tmp_path):
        """Test late-writer rule: if existing manifest shows FAILED, return False."""
        existing_manifest = {
            "job_id": "existing",
            "status": "FAILED",
            "error": "timeout",
            "idempotency_key": "key",
            "deployment": "prod",
            "execution_id": "task-1",
            "attempt": 1,
            "inputs": {"company_name": "Test", "company_url": "", "mode": "full"},
            "expected_artifacts": [],
            "timing": {"submitted_at": "2026-02-03T10:00:00Z"},
            "cost": {"estimated_usd": 1.0},
            "artifacts": {},
            "versions": {"primr": "1.0.0", "runner": "1.0.0"},
        }
        (tmp_path / "manifest.json").write_text(json.dumps(existing_manifest))

        new_manifest = JobManifest(
            job_id="late-writer",
            idempotency_key="key",
            deployment="prod",
            execution_id="task-2",
            attempt=2,
            status="SUCCEEDED",
            inputs=JobInputs("Test", "https://test.example", "full"),
            expected_artifacts=[],
            timing=JobTiming("2026-02-03T10:00:00Z"),
            cost=JobCost(1.0),
            artifacts={},
            versions=JobVersions("1.0.0", "1.0.0"),
        )

        result = write_manifest_safe(tmp_path, new_manifest)

        # Late writer should not overwrite failure record
        assert result is False


class TestEstimateCost:
    """Tests for cost estimation."""

    def test_estimate_cost_scrape(self):
        """Test cost estimation for scrape mode."""
        cost = estimate_cost("scrape", None)
        assert cost.estimated_usd == 0.05

    def test_estimate_cost_deep(self):
        """Test cost estimation for deep mode."""
        cost = estimate_cost("deep", None)
        assert cost.estimated_usd == 1.00

    def test_estimate_cost_full(self):
        """Test cost estimation for full mode."""
        cost = estimate_cost("full", None)
        assert cost.estimated_usd == 2.00

    def test_estimate_cost_with_duration(self):
        """Test cost estimation includes compute cost when duration known."""
        cost = estimate_cost("full", 3600)  # 1 hour

        assert cost.estimated_usd == 2.00
        assert cost.actual_compute_usd is not None
        assert cost.actual_compute_usd > 0
        assert cost.actual_known is False  # LLM cost not tracked

    def test_estimate_cost_unknown_mode(self):
        """Test cost estimation for unknown mode defaults to full."""
        cost = estimate_cost("unknown", None)
        assert cost.estimated_usd == 2.00


class TestFormatTimestamp:
    """Tests for timestamp formatting."""

    def test_format_timestamp(self):
        """Test timestamp formatting."""
        dt = datetime(2026, 2, 3, 10, 30, 45, tzinfo=timezone.utc)
        formatted = format_timestamp(dt)
        assert formatted == "2026-02-03T10:30:45Z"
