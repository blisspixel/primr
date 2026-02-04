"""
Job Runner - Wraps Primr CLI for cloud execution.

Input (via JOB_SPEC env var or /job/spec.json):
{
    "job_id": "abc123",
    "deployment": "prod",
    "execution_id": "ecs-task-xyz",
    "attempt": 1,
    "company_name": "Acme Corp",
    "company_url": "https://acme.example",
    "mode": "full",  # scrape | deep | full
    "options": {
        "cloud_vendor": "aws",
        "no_qa": false
    }
}

Output:
- Artifacts written to ARTIFACT_STORE_URL/{job_id}/
- Manifest written to {job_id}/manifest.json
- Progress events to events.jsonl artifact
- Structured logs to _logs/runner.jsonl artifact
- Heartbeat to _heartbeat.json every 5 minutes
- Exit code: 0 = success, 1 = failure, 130 = cancelled

Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.12
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from deploy.storage import ArtifactStore

# Import observability utilities
from deploy.observability import (
    redact_sensitive,
    redact_dict,
    Tracer,
    MetricsCollector,
)

# Version for manifest
RUNNER_VERSION = "1.0.0"

# Exit codes
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INVALID_SPEC = 2
EXIT_SECRETS_MISSING = 3
EXIT_TIMEOUT = 124
EXIT_CANCELLED = 130

# Default timeout (60 minutes)
DEFAULT_TIMEOUT_SECONDS = 60 * 60
MAX_TIMEOUT_SECONDS = 120 * 60

# Heartbeat interval (5 minutes)
HEARTBEAT_INTERVAL_SECONDS = 5 * 60

# Expected artifacts by mode
EXPECTED_ARTIFACTS = {
    "scrape": ["scraped_content.txt", "insights.txt"],
    "deep": ["dossier.txt", "report.docx", "report.md"],
    "full": ["scraped_content.txt", "insights.txt", "dossier.txt", "report.docx", "report.md"],
}

# Logger setup
logger = logging.getLogger("runner")


@dataclass
class JobSpec:
    """Job specification parsed from environment or file."""

    job_id: str
    deployment: str
    execution_id: str
    attempt: int
    company_name: str
    company_url: str
    mode: str  # scrape, deep, full
    options: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        """Validate job spec fields."""
        if not self.job_id:
            raise ValueError("job_id is required")
        if not self.deployment:
            raise ValueError("deployment is required")
        if not self.execution_id:
            raise ValueError("execution_id is required")
        if self.attempt < 1:
            raise ValueError("attempt must be >= 1")
        if not self.company_name and not self.company_url:
            raise ValueError("company_name or company_url is required")
        if self.mode not in ("scrape", "deep", "full"):
            raise ValueError(f"Invalid mode: {self.mode}. Must be scrape, deep, or full")
        # Clamp timeout to max
        if self.timeout_seconds > MAX_TIMEOUT_SECONDS:
            self.timeout_seconds = MAX_TIMEOUT_SECONDS

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobSpec":
        """Create JobSpec from dictionary."""
        return cls(
            job_id=data.get("job_id", ""),
            deployment=data.get("deployment", ""),
            execution_id=data.get("execution_id", ""),
            attempt=data.get("attempt", 1),
            company_name=data.get("company_name", ""),
            company_url=data.get("company_url", ""),
            mode=data.get("mode", "full"),
            options=data.get("options", {}),
            timeout_seconds=data.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "deployment": self.deployment,
            "execution_id": self.execution_id,
            "attempt": self.attempt,
            "company_name": self.company_name,
            "company_url": self.company_url,
            "mode": self.mode,
            "options": self.options,
            "timeout_seconds": self.timeout_seconds,
        }


# ArtifactStore protocol is defined in deploy/storage.py
# Import it when needed to avoid circular imports


def parse_job_spec() -> JobSpec:
    """
    Parse job specification from JOB_SPEC env var or /job/spec.json.
    
    Returns:
        JobSpec instance
        
    Raises:
        ValueError: If job spec is invalid or missing
    """
    # Try environment variable first
    job_spec_env = os.environ.get("JOB_SPEC")
    if job_spec_env:
        try:
            data = json.loads(job_spec_env)
            logger.info({"event": "job_spec_loaded", "source": "env"})
            return JobSpec.from_dict(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in JOB_SPEC env var: {e}") from e

    # Try file
    spec_file = Path("/job/spec.json")
    if spec_file.exists():
        try:
            data = json.loads(spec_file.read_text())
            logger.info({"event": "job_spec_loaded", "source": "file", "path": str(spec_file)})
            return JobSpec.from_dict(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {spec_file}: {e}") from e

    raise ValueError("No job spec found. Set JOB_SPEC env var or provide /job/spec.json")


def get_expected_artifacts(mode: str) -> list[str]:
    """Return expected artifacts for each mode."""
    return EXPECTED_ARTIFACTS.get(mode, EXPECTED_ARTIFACTS["full"])


class RunnerState:
    """Thread-safe state for the runner."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel_requested = False
        self._current_stage = "initializing"
        self._percent = 0
        self._started_at: datetime | None = None
        self._process: subprocess.Popen | None = None

    @property
    def cancel_requested(self) -> bool:
        with self._lock:
            return self._cancel_requested

    @cancel_requested.setter
    def cancel_requested(self, value: bool) -> None:
        with self._lock:
            self._cancel_requested = value

    @property
    def current_stage(self) -> str:
        with self._lock:
            return self._current_stage

    @current_stage.setter
    def current_stage(self, value: str) -> None:
        with self._lock:
            self._current_stage = value

    @property
    def percent(self) -> int:
        with self._lock:
            return self._percent

    @percent.setter
    def percent(self, value: int) -> None:
        with self._lock:
            self._percent = value

    @property
    def started_at(self) -> datetime | None:
        with self._lock:
            return self._started_at

    @started_at.setter
    def started_at(self, value: datetime | None) -> None:
        with self._lock:
            self._started_at = value

    @property
    def process(self) -> subprocess.Popen | None:
        with self._lock:
            return self._process

    @process.setter
    def process(self, value: subprocess.Popen | None) -> None:
        with self._lock:
            self._process = value


# Global state
_state = RunnerState()


def handle_sigterm(signum: int, frame: Any) -> None:
    """Handle SIGTERM signal for graceful cancellation."""
    _state.cancel_requested = True
    logger.info({"event": "cancellation_requested", "signal": signum})

    # Try to terminate the subprocess if running
    proc = _state.process
    if proc and proc.poll() is None:
        logger.info({"event": "terminating_subprocess"})
        proc.terminate()


def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""
    # SIGINT works on all platforms
    signal.signal(signal.SIGINT, handle_sigterm)
    # SIGTERM only exists on Unix-like systems
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, handle_sigterm)


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


def format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class StructuredLogger:
    """Logger that writes structured JSON logs to a file with redaction."""

    def __init__(self, log_file: Path) -> None:
        self.log_file = log_file
        self._lock = threading.Lock()
        # Ensure parent directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(self, level: str, event: str, **kwargs: Any) -> None:
        """Write a structured log entry with sensitive data redacted."""
        # Redact sensitive data from kwargs
        redacted_kwargs = {}
        for key, value in kwargs.items():
            if isinstance(value, dict):
                redacted_kwargs[key] = redact_dict(value)
            elif isinstance(value, str):
                redacted_kwargs[key] = redact_sensitive(value)
            else:
                redacted_kwargs[key] = value

        entry = {
            "ts": format_timestamp(utc_now()),
            "level": level,
            "event": event,
            **redacted_kwargs,
        }
        with self._lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def info(self, event: str, **kwargs: Any) -> None:
        self.log("info", event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self.log("warning", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self.log("error", event, **kwargs)


class EventWriter:
    """Writer for progress events to events.jsonl."""

    def __init__(
        self,
        events_file: Path | None = None,
        store: "ArtifactStore | None" = None,
        job_id: str | None = None,
    ) -> None:
        """
        Initialize event writer.
        
        Can write to either a local file or an artifact store.
        
        Args:
            events_file: Local file path (for local mode)
            store: Artifact store (for cloud mode)
            job_id: Job ID (required when using store)
        """
        self.events_file = events_file
        self.store = store
        self.job_id = job_id
        self._lock = threading.Lock()

        # Ensure parent directory exists for local file
        if events_file:
            events_file.parent.mkdir(parents=True, exist_ok=True)

    def write_event(self, stage: str, percent: int, message: str) -> None:
        """Write a progress event."""
        entry = {
            "ts": format_timestamp(utc_now()),
            "stage": stage,
            "percent": percent,
            "message": message,
        }

        if self.store and self.job_id:
            # Write to artifact store
            try:
                self.store.append_event(self.job_id, entry)
            except Exception as e:
                logger.warning({"event": "event_write_failed", "error": str(e)})
        elif self.events_file:
            # Write to local file
            with self._lock:
                with open(self.events_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")


class HeartbeatWriter:
    """Writer for heartbeat updates."""

    def __init__(
        self,
        heartbeat_file: Path | None,
        job_spec: JobSpec,
        store: "ArtifactStore | None" = None,
    ) -> None:
        """
        Initialize heartbeat writer.
        
        Can write to either a local file or an artifact store.
        
        Args:
            heartbeat_file: Local file path (for local mode, can be None if using store)
            job_spec: Job specification
            store: Artifact store (for cloud mode)
        """
        self.heartbeat_file = heartbeat_file
        self.job_spec = job_spec
        self.store = store
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Ensure parent directory exists for local file
        if heartbeat_file:
            heartbeat_file.parent.mkdir(parents=True, exist_ok=True)

    def _write_heartbeat(self) -> None:
        """Write current heartbeat to file or store."""
        heartbeat = {
            "job_id": self.job_spec.job_id,
            "execution_id": self.job_spec.execution_id,
            "attempt": self.job_spec.attempt,
            "last_heartbeat": format_timestamp(utc_now()),
            "stage": _state.current_stage,
            "percent": _state.percent,
        }

        if self.store:
            # Write to artifact store
            try:
                self.store.update_heartbeat(self.job_spec.job_id, heartbeat)
            except Exception as e:
                logger.warning({"event": "heartbeat_store_write_failed", "error": str(e)})

        if self.heartbeat_file:
            # Write atomically via temp file (for local mode or as backup)
            with self._lock:
                temp_file = self.heartbeat_file.with_suffix(".tmp")
                temp_file.write_text(json.dumps(heartbeat, indent=2))
                temp_file.rename(self.heartbeat_file)

    def _heartbeat_loop(self) -> None:
        """Background thread that writes heartbeat every 5 minutes."""
        while not self._stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
            try:
                self._write_heartbeat()
                logger.info({"event": "heartbeat_written"})
            except Exception as e:
                logger.error({"event": "heartbeat_write_failed", "error": str(e)})

    def start(self) -> None:
        """Start the heartbeat background thread."""
        # Write initial heartbeat immediately
        self._write_heartbeat()
        # Start background thread
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the heartbeat background thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        # Write final heartbeat
        try:
            self._write_heartbeat()
        except Exception:
            pass


def build_primr_command(job_spec: JobSpec, output_dir: Path) -> list[str]:
    """
    Build the primr CLI command from job spec.
    
    Args:
        job_spec: Job specification
        output_dir: Directory for output artifacts
        
    Returns:
        Command as list of strings
    """
    cmd = [
        sys.executable, "-m", "primr",
        job_spec.company_name,
        job_spec.company_url,
        "--output-dir", str(output_dir),
        "--skip-confirm",  # Non-interactive
    ]

    # Map job mode to primr mode
    mode_map = {
        "scrape": "scrape-only",
        "deep": "deep-research",
        "full": "complete",
    }
    primr_mode = mode_map.get(job_spec.mode, "complete")
    cmd.extend(["--mode", primr_mode])

    # Add options
    options = job_spec.options
    if options.get("cloud_vendor"):
        cmd.extend(["--cloud-vendor", options["cloud_vendor"]])
    if options.get("no_qa"):
        cmd.append("--no-qa")

    return cmd


def run_primr(
    job_spec: JobSpec,
    output_dir: Path,
    event_writer: EventWriter,
    struct_logger: StructuredLogger,
) -> tuple[int, str | None]:
    """
    Execute primr CLI and capture output.
    
    Args:
        job_spec: Job specification
        output_dir: Directory for output artifacts
        event_writer: Writer for progress events
        struct_logger: Structured logger
        
    Returns:
        Tuple of (exit_code, error_message)
    """
    cmd = build_primr_command(job_spec, output_dir)
    struct_logger.info("primr_starting", command=" ".join(cmd))
    event_writer.write_event("starting", 0, f"Starting primr in {job_spec.mode} mode")

    _state.current_stage = "running"
    _state.percent = 5

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        _state.process = proc

        # Read output line by line
        output_lines: list[str] = []
        if proc.stdout:
            for line in proc.stdout:
                line = line.rstrip()
                output_lines.append(line)
                struct_logger.info("primr_output", line=line)

                # Update progress based on output patterns
                if "scraping" in line.lower() or "scanning" in line.lower():
                    _state.current_stage = "scrape"
                    _state.percent = 20
                    event_writer.write_event("scrape", 20, "Scraping website content")
                elif "insight" in line.lower() or "extract" in line.lower():
                    _state.current_stage = "insights"
                    _state.percent = 50
                    event_writer.write_event("insights", 50, "Extracting insights")
                elif "research" in line.lower():
                    _state.current_stage = "deep_research"
                    _state.percent = 70
                    event_writer.write_event("deep_research", 70, "Running deep research")
                elif "report" in line.lower() or "generat" in line.lower():
                    _state.current_stage = "report"
                    _state.percent = 90
                    event_writer.write_event("report", 90, "Generating report")

                # Check for cancellation
                if _state.cancel_requested:
                    struct_logger.info("cancellation_acknowledged")
                    proc.terminate()
                    proc.wait(timeout=10)
                    return EXIT_CANCELLED, "user_cancelled"

        # Wait for completion
        exit_code = proc.wait()
        _state.process = None

        if exit_code == 0:
            _state.current_stage = "complete"
            _state.percent = 100
            event_writer.write_event("complete", 100, "Job completed successfully")
            struct_logger.info("primr_completed", exit_code=exit_code)
            return EXIT_SUCCESS, None
        else:
            error_msg = f"primr exited with code {exit_code}"
            struct_logger.error("primr_failed", exit_code=exit_code, output="\n".join(output_lines[-20:]))
            return EXIT_FAILURE, error_msg

    except subprocess.TimeoutExpired:
        struct_logger.error("primr_timeout")
        if _state.process:
            _state.process.kill()
        return EXIT_TIMEOUT, "timeout"
    except Exception as e:
        struct_logger.error("primr_exception", error=str(e))
        return EXIT_FAILURE, str(e)


def map_exit_code(primr_exit: int, error: str | None) -> int:
    """
    Map primr exit code to runner exit code.
    
    Args:
        primr_exit: Exit code from primr
        error: Error message if any
        
    Returns:
        Runner exit code
    """
    # Check error message first for special cases
    if error == "user_cancelled":
        return EXIT_CANCELLED
    if error == "timeout":
        return EXIT_TIMEOUT
    # Then check primr exit code
    if primr_exit == 0:
        return EXIT_SUCCESS
    return EXIT_FAILURE


def main() -> int:
    """
    Main entry point for the job runner.
    
    Returns:
        Exit code (0=success, 1=failure, 130=cancelled)
    """
    # Import manifest and storage modules
    from deploy.manifest import JobManifest, build_manifest, ManifestAlreadyExistsError
    from deploy.storage import create_store, LocalStore

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='{"ts": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    # Setup signal handlers
    setup_signal_handlers()

    # Parse job spec
    try:
        job_spec = parse_job_spec()
    except ValueError as e:
        logger.error({"event": "invalid_job_spec", "error": str(e)})
        return EXIT_INVALID_SPEC

    logger.info({
        "event": "job_starting",
        "job_id": job_spec.job_id,
        "deployment": job_spec.deployment,
        "mode": job_spec.mode,
        "attempt": job_spec.attempt,
    })

    # Setup artifact store
    artifact_store_url = os.environ.get("ARTIFACT_STORE_URL", "")
    if not artifact_store_url:
        logger.error({"event": "missing_artifact_store_url"})
        return EXIT_FAILURE

    # Create artifact store
    try:
        store = create_store(artifact_store_url, job_spec.deployment)
    except ValueError as e:
        logger.error({"event": "invalid_artifact_store_url", "error": str(e)})
        return EXIT_FAILURE

    # For local stores, we also need a local output directory for primr
    # For cloud stores, we use a temp directory and upload artifacts after
    if isinstance(store, LocalStore):
        output_dir = Path(artifact_store_url) / job_spec.deployment / job_spec.job_id
    else:
        output_dir = Path(tempfile.mkdtemp(prefix=f"primr_{job_spec.job_id}_"))

    output_dir.mkdir(parents=True, exist_ok=True)

    # Setup structured logger (always local for now)
    log_file = output_dir / "_logs" / "runner.jsonl"
    struct_logger = StructuredLogger(log_file)
    struct_logger.info("runner_starting", job_id=job_spec.job_id, version=RUNNER_VERSION)

    # Setup tracing (optional - enabled via OTEL_EXPORTER_* env vars)
    tracer = Tracer(
        service_name="primr-runner",
        job_id=job_spec.job_id,
        deployment=job_spec.deployment,
    )

    # Setup metrics collector
    metrics = MetricsCollector(
        job_id=job_spec.job_id,
        deployment=job_spec.deployment,
    )

    # Setup event writer with store integration
    events_file = output_dir / "events.jsonl"
    event_writer = EventWriter(
        events_file=events_file,
        store=store,
        job_id=job_spec.job_id,
    )
    event_writer.write_event("initializing", 0, "Job runner initializing")

    # Setup heartbeat writer with store integration
    heartbeat_file = output_dir / "_heartbeat.json"
    heartbeat_writer = HeartbeatWriter(
        heartbeat_file=heartbeat_file,
        job_spec=job_spec,
        store=store,
    )

    # Record start time
    _state.started_at = utc_now()
    submitted_at = _state.started_at  # For manifest

    # Start heartbeat (updates every 5 minutes)
    heartbeat_writer.start()

    try:
        # Run primr with tracing
        with tracer.span("primr_execution", {"mode": job_spec.mode}) as span:
            exit_code, error = run_primr(job_spec, output_dir, event_writer, struct_logger)

            # Check for cancellation
            if _state.cancel_requested:
                exit_code = EXIT_CANCELLED
                error = "user_cancelled"

            # Determine status
            if exit_code == EXIT_SUCCESS:
                status = "SUCCEEDED"
                tracer.set_success(span)
            elif exit_code == EXIT_CANCELLED:
                status = "CANCELLED"
            else:
                status = "FAILED"
                if span:
                    span.set_attribute("error.message", error or "unknown")

        # Record metrics
        completed_at = utc_now()
        if _state.started_at:
            duration = (completed_at - _state.started_at).total_seconds()
            metrics.record_duration("job_execution", duration, {"status": status, "mode": job_spec.mode})
        metrics.record_count("job_completed", labels={"status": status, "mode": job_spec.mode})

        # Upload artifacts to store if not local
        if not isinstance(store, LocalStore):
            _upload_artifacts_to_store(output_dir, store, job_spec.job_id, struct_logger)

        # Build manifest
        manifest = build_manifest(
            job_spec=job_spec,
            output_dir=output_dir,
            status=status,
            error=error,
            submitted_at=submitted_at,
            started_at=_state.started_at,
            completed_at=completed_at,
        )

        # Write manifest LAST with conditional check (manifest-as-commit pattern)
        try:
            store.put_manifest(job_spec.job_id, manifest)
            struct_logger.info("manifest_written", job_id=manifest.job_id, status=manifest.status)
            written = True
        except ManifestAlreadyExistsError:
            # Another attempt already wrote manifest - check its status
            existing = store.get_manifest(job_spec.job_id)
            if existing:
                struct_logger.info("late_writer_detected", existing_status=existing.status)
                if existing.status == "SUCCEEDED":
                    return EXIT_SUCCESS
            written = False

        if not written:
            struct_logger.warning("late_writer_failure")
            return EXIT_FAILURE

        struct_logger.info("job_completed", status=status, exit_code=exit_code)
        return map_exit_code(exit_code, error)

    except Exception as e:
        struct_logger.error("runner_exception", error=str(e))

        # Try to write FAILED manifest
        try:
            manifest = build_manifest(
                job_spec=job_spec,
                output_dir=output_dir,
                status="FAILED",
                error=str(e),
                submitted_at=submitted_at,
                started_at=_state.started_at,
                completed_at=utc_now(),
            )
            store.put_manifest(job_spec.job_id, manifest)
        except Exception:
            pass

        return EXIT_FAILURE

    finally:
        # Stop heartbeat
        heartbeat_writer.stop()

        # Handle SIGTERM - always write CANCELLED manifest
        if _state.cancel_requested:
            try:
                manifest = build_manifest(
                    job_spec=job_spec,
                    output_dir=output_dir,
                    status="CANCELLED",
                    error="user_cancelled",
                    submitted_at=submitted_at,
                    started_at=_state.started_at,
                    completed_at=utc_now(),
                )
                store.put_manifest(job_spec.job_id, manifest)
                struct_logger.info("cancelled_manifest_written")
            except ManifestAlreadyExistsError:
                # Already written, that's fine
                pass
            except Exception as e:
                struct_logger.error("cancelled_manifest_write_failed", error=str(e))

        # Clean up temp directory for cloud stores
        if not isinstance(store, LocalStore):
            try:
                import shutil
                shutil.rmtree(output_dir, ignore_errors=True)
            except Exception:
                pass


def _upload_artifacts_to_store(
    output_dir: Path,
    store: "ArtifactStore",
    job_id: str,
    struct_logger: StructuredLogger,
) -> None:
    """
    Upload local artifacts to the artifact store.
    
    Used when running with cloud stores (S3, GCS, Azure Blob).
    """
    # Upload all files in output directory
    for file_path in output_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(output_dir)
            key = f"{job_id}/{rel_path}"

            # Determine content type
            suffix = file_path.suffix.lower()
            content_types = {
                ".json": "application/json",
                ".jsonl": "application/x-ndjson",
                ".txt": "text/plain",
                ".md": "text/markdown",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
            content_type = content_types.get(suffix, "application/octet-stream")

            try:
                store.put(key, file_path.read_bytes(), content_type)
                struct_logger.info("artifact_uploaded", key=key)
            except Exception as e:
                struct_logger.error("artifact_upload_failed", key=key, error=str(e))


if __name__ == "__main__":
    sys.exit(main())
