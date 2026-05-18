"""
Job Manifest - Manifest generation and management for job artifacts.

The manifest captures job inputs, outputs, timing, versions, and checksums.
It is written LAST after all artifacts are complete (manifest-as-commit semantics).

Key features:
- Conditional create: fails if manifest already exists (prevents overwrites)
- Late-writer rule: if manifest exists, read it and exit accordingly
- Atomic writes: temp file + rename for local, conditional PUT for object stores

Requirements: 2.2, 2.3, 2.4, 2.5, 2.6
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

    from deploy.runner import JobSpec, StructuredLogger

# Version for manifest
RUNNER_VERSION = "1.0.0"

# Expected artifacts by mode
EXPECTED_ARTIFACTS = {
    "scrape": ["scraped_content.txt", "insights.txt"],
    "deep": ["dossier.txt", "report.docx", "report.md"],
    "full": ["scraped_content.txt", "insights.txt", "dossier.txt", "report.docx", "report.md"],
}


class ManifestAlreadyExistsError(Exception):
    """Raised when attempting to write a manifest that already exists."""


@dataclass
class ArtifactMeta:
    """Metadata for a single artifact."""

    size_bytes: int
    checksum_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "size_bytes": self.size_bytes,
            "checksum_sha256": self.checksum_sha256,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactMeta:
        return cls(
            size_bytes=data.get("size_bytes", 0),
            checksum_sha256=data.get("checksum_sha256", ""),
        )


@dataclass
class JobTiming:
    """Timing information for a job."""

    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobTiming:
        return cls(
            submitted_at=data.get("submitted_at", ""),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            duration_seconds=data.get("duration_seconds"),
        )


@dataclass
class JobCost:
    """Cost information for a job."""

    estimated_usd: float
    actual_compute_usd: float | None = None
    actual_llm_usd: float | None = None
    actual_known: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimated_usd": self.estimated_usd,
            "actual_compute_usd": self.actual_compute_usd,
            "actual_llm_usd": self.actual_llm_usd,
            "actual_known": self.actual_known,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobCost:
        return cls(
            estimated_usd=data.get("estimated_usd", 0.0),
            actual_compute_usd=data.get("actual_compute_usd"),
            actual_llm_usd=data.get("actual_llm_usd"),
            actual_known=data.get("actual_known", False),
        )


@dataclass
class JobInputs:
    """Input parameters for a job."""

    company_name: str
    company_url: str
    mode: str
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "company_url": self.company_url,
            "mode": self.mode,
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobInputs:
        return cls(
            company_name=data.get("company_name", ""),
            company_url=data.get("company_url", ""),
            mode=data.get("mode", "full"),
            options=data.get("options", {}),
        )


@dataclass
class JobVersions:
    """Version information for a job."""

    primr: str
    runner: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "primr": self.primr,
            "runner": self.runner,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobVersions:
        return cls(
            primr=data.get("primr", "unknown"),
            runner=data.get("runner", RUNNER_VERSION),
        )


@dataclass
class JobManifest:
    """
    Complete job manifest capturing all job metadata.

    The manifest is written LAST after all artifacts are complete.
    Its presence signals job completion (manifest-as-commit semantics).
    """

    job_id: str
    idempotency_key: str
    deployment: str
    execution_id: str
    attempt: int
    status: str  # SUCCEEDED, FAILED, CANCELLED
    inputs: JobInputs
    expected_artifacts: list[str]
    timing: JobTiming
    cost: JobCost
    artifacts: dict[str, ArtifactMeta]
    versions: JobVersions
    error: str | None = None
    manifest_written_by: str = "runner"

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to dictionary for JSON serialization."""
        return {
            "job_id": self.job_id,
            "idempotency_key": self.idempotency_key,
            "deployment": self.deployment,
            "execution_id": self.execution_id,
            "attempt": self.attempt,
            "status": self.status,
            "inputs": self.inputs.to_dict(),
            "expected_artifacts": self.expected_artifacts,
            "timing": self.timing.to_dict(),
            "cost": self.cost.to_dict(),
            "artifacts": {k: v.to_dict() for k, v in self.artifacts.items()},
            "versions": self.versions.to_dict(),
            "error": self.error,
            "manifest_written_by": self.manifest_written_by,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert manifest to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobManifest:
        """Create manifest from dictionary."""
        artifacts = {}
        for name, meta in data.get("artifacts", {}).items():
            artifacts[name] = ArtifactMeta.from_dict(meta)

        return cls(
            job_id=data.get("job_id", ""),
            idempotency_key=data.get("idempotency_key", ""),
            deployment=data.get("deployment", ""),
            execution_id=data.get("execution_id", ""),
            attempt=data.get("attempt", 1),
            status=data.get("status", ""),
            inputs=JobInputs.from_dict(data.get("inputs", {})),
            expected_artifacts=data.get("expected_artifacts", []),
            timing=JobTiming.from_dict(data.get("timing", {})),
            cost=JobCost.from_dict(data.get("cost", {})),
            artifacts=artifacts,
            versions=JobVersions.from_dict(data.get("versions", {})),
            error=data.get("error"),
            manifest_written_by=data.get("manifest_written_by", "runner"),
        )

    @classmethod
    def load(cls, path: Path) -> JobManifest | None:
        """Load manifest from file, returns None if not found."""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return cls.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None


def compute_checksum(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_file_size(file_path: Path) -> int:
    """Get file size in bytes."""
    return file_path.stat().st_size


def scan_artifacts(output_dir: Path) -> dict[str, ArtifactMeta]:
    """
    Scan output directory for artifacts and compute checksums.

    Args:
        output_dir: Directory containing job artifacts

    Returns:
        Dictionary mapping artifact name to metadata
    """
    artifacts = {}

    # Scan for known artifact files
    artifact_patterns = [
        "scraped_content.txt",
        "insights.txt",
        "dossier.txt",
        "report.docx",
        "report.md",
        "events.jsonl",
    ]

    for pattern in artifact_patterns:
        file_path = output_dir / pattern
        if file_path.exists():
            artifacts[pattern] = ArtifactMeta(
                size_bytes=get_file_size(file_path),
                checksum_sha256=compute_checksum(file_path),
            )

    # Also scan for any .txt files in the output directory
    for file_path in output_dir.glob("*.txt"):
        name = file_path.name
        if name not in artifacts and not name.startswith("_"):
            artifacts[name] = ArtifactMeta(
                size_bytes=get_file_size(file_path),
                checksum_sha256=compute_checksum(file_path),
            )

    return artifacts


def get_primr_version() -> str:
    """Get the installed primr version."""
    try:
        from primr import __version__

        return __version__
    except ImportError:
        return "unknown"


def format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def estimate_cost(mode: str, duration_seconds: int | None) -> JobCost:
    """
    Estimate job cost based on mode and duration.

    Cost estimates are rough approximations:
    - scrape: ~$0.01-0.05 (minimal LLM usage)
    - deep: ~$0.50-1.50 (moderate LLM usage)
    - full: ~$1.00-3.00 (heavy LLM usage)

    Compute cost is based on Fargate pricing (~$0.04/vCPU-hour, ~$0.004/GB-hour)
    """
    # Base estimates by mode
    mode_estimates = {
        "scrape": 0.05,
        "deep": 1.00,
        "full": 2.00,
    }
    estimated_usd = mode_estimates.get(mode, 2.00)

    # Compute actual compute cost if duration known
    actual_compute_usd = None
    if duration_seconds:
        # Assume 2 vCPU, 4GB memory
        vcpu_hours = (duration_seconds / 3600) * 2
        gb_hours = (duration_seconds / 3600) * 4
        actual_compute_usd = round(vcpu_hours * 0.04 + gb_hours * 0.004, 4)

    return JobCost(
        estimated_usd=estimated_usd,
        actual_compute_usd=actual_compute_usd,
        actual_llm_usd=None,  # Not tracked in v1
        actual_known=False,
    )


def build_manifest(
    job_spec: JobSpec,
    output_dir: Path,
    status: str,
    error: str | None,
    submitted_at: datetime,
    started_at: datetime | None,
    completed_at: datetime,
) -> JobManifest:
    """
    Build a job manifest from job spec and execution results.

    Args:
        job_spec: Job specification
        output_dir: Directory containing job artifacts
        status: Job status (SUCCEEDED, FAILED, CANCELLED)
        error: Error message if failed
        submitted_at: When job was submitted
        started_at: When job started running
        completed_at: When job completed

    Returns:
        JobManifest instance
    """
    # Calculate duration
    duration_seconds = None
    if started_at and completed_at:
        duration_seconds = int((completed_at - started_at).total_seconds())

    # Scan artifacts
    artifacts = scan_artifacts(output_dir)

    # Get expected artifacts for mode
    expected = EXPECTED_ARTIFACTS.get(job_spec.mode, EXPECTED_ARTIFACTS["full"])

    # Build timing
    timing = JobTiming(
        submitted_at=format_timestamp(submitted_at),
        started_at=format_timestamp(started_at) if started_at else None,
        completed_at=format_timestamp(completed_at),
        duration_seconds=duration_seconds,
    )

    # Estimate cost
    cost = estimate_cost(job_spec.mode, duration_seconds)

    # Build inputs
    inputs = JobInputs(
        company_name=job_spec.company_name,
        company_url=job_spec.company_url,
        mode=job_spec.mode,
        options=job_spec.options,
    )

    # Build versions
    versions = JobVersions(
        primr=get_primr_version(),
        runner=RUNNER_VERSION,
    )

    return JobManifest(
        job_id=job_spec.job_id,
        idempotency_key=job_spec.options.get("idempotency_key", ""),
        deployment=job_spec.deployment,
        execution_id=job_spec.execution_id,
        attempt=job_spec.attempt,
        status=status,
        inputs=inputs,
        expected_artifacts=expected,
        timing=timing,
        cost=cost,
        artifacts=artifacts,
        versions=versions,
        error=error,
        manifest_written_by="runner",
    )


def write_manifest_local(output_dir: Path, manifest: JobManifest) -> None:
    """
    Write manifest atomically to local filesystem.

    Uses temp file + rename for atomicity.
    Raises ManifestAlreadyExistsError if manifest already exists.

    Args:
        output_dir: Directory to write manifest to
        manifest: Manifest to write
    """
    manifest_path = output_dir / "manifest.json"

    # Check if manifest already exists (conditional create)
    if manifest_path.exists():
        raise ManifestAlreadyExistsError(f"Manifest already exists: {manifest_path}")

    # Write to temp file first
    fd, temp_path = tempfile.mkstemp(
        suffix=".json",
        prefix="manifest_",
        dir=output_dir,
    )
    try:
        os.close(fd)
        temp_file = Path(temp_path)
        temp_file.write_text(manifest.to_json())

        # Atomic rename (POSIX guarantees atomicity for rename on same filesystem)
        # Check again before rename (race condition window is small but exists)
        if manifest_path.exists():
            temp_file.unlink()
            raise ManifestAlreadyExistsError(f"Manifest already exists: {manifest_path}")

        temp_file.rename(manifest_path)
    except Exception:
        # Clean up temp file on error
        try:
            Path(temp_path).unlink()
        except OSError:
            pass
        raise


def write_manifest_safe(
    output_dir: Path,
    manifest: JobManifest,
    logger: StructuredLogger | None = None,
) -> bool:
    """
    Write manifest with late-writer protection.

    Returns True if written, False if already exists.

    Args:
        output_dir: Directory to write manifest to
        manifest: Manifest to write
        logger: Optional structured logger

    Returns:
        True if manifest was written, False if it already existed
    """
    try:
        write_manifest_local(output_dir, manifest)
        if logger:
            logger.info("manifest_written", job_id=manifest.job_id, status=manifest.status)
        return True
    except ManifestAlreadyExistsError:
        # Another attempt already wrote manifest - check its status
        existing = JobManifest.load(output_dir / "manifest.json")
        if existing:
            if logger:
                logger.info("late_writer_detected", existing_status=existing.status)
        return False
