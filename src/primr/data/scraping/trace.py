"""
Scrape trace artifact logging for debugging and QA.

Schema is stable and versioned for analytics.
"""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .models import ErrorType, ScrapeResult

# Trace schema version - increment when format changes
TRACE_SCHEMA_VERSION = "1.0"


@dataclass
class TraceHeader:
    """Header written at start of trace file."""
    schema_version: str
    run_id: str
    company: str
    started_at: str


@dataclass
class TraceEntry:
    """
    Single URL scrape trace (stable schema).

    NOTE: Internal representation uses typed Attempt objects.
    File output serializes to dicts via asdict() for JSON compatibility.
    """
    # Identifiers
    run_id: str
    url: str
    timestamp: str

    # Tier attempts (serialized from typed Attempt records)
    tier_attempts: list  # list[dict] when serialized
    success_tier: str | None

    # Block detection (enums as strings for queryability)
    blocked: bool
    block_type: str | None  # "soft_block", "hard_block", "challenge", etc.
    blocked_reason: str | None

    # Response metadata
    http_status: int | None
    content_type: str | None
    final_url: str | None

    # Timing
    elapsed_total_ms: float

    # Content metrics
    extracted_text_length: int | None
    validation_result: dict | None  # Serialized ValidationResult


class TraceLogger:
    """
    Persist scrape traces as JSON Lines for debugging and analytics.

    Format:
    - Line 1: TraceHeader (schema version, run ID, company, start time)
    - Lines 2+: TraceEntry per URL

    One file per run: logs/scrape_traces/{company}_{timestamp}.jsonl
    """

    def __init__(
        self,
        company_name: str,
        output_dir: Path | None = None,
    ):
        """
        Initialize trace logger.

        Args:
            company_name: Company being scraped (used in filename)
            output_dir: Directory for trace files (default: logs/scrape_traces)
        """
        self.company = self._sanitize_filename(company_name)
        self.run_id = str(uuid.uuid4())
        self.started_at = datetime.now().isoformat()

        # Set up output directory
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path("logs") / "scrape_traces"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create trace file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = self.output_dir / f"{self.company}_{timestamp}.jsonl"

        # Write header
        self._write_header()

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize company name for use in filename."""
        # Replace problematic characters
        sanitized = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        sanitized = "".join(c for c in sanitized if c.isalnum() or c in "_-")
        return sanitized[:50]  # Limit length

    def _write_header(self) -> None:
        """Write header as first line."""
        header = TraceHeader(
            schema_version=TRACE_SCHEMA_VERSION,
            run_id=self.run_id,
            company=self.company,
            started_at=self.started_at,
        )
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(json.dumps(asdict(header)) + "\n")

    def log(self, result: ScrapeResult) -> None:
        """
        Log a ScrapeResult as a trace entry.

        Args:
            result: ScrapeResult to log
        """
        # Serialize attempts (typed Attempt -> dict)
        tier_attempts = []
        for attempt in result.attempts:
            attempt_dict = {
                "tier": attempt.tier,
                "success": attempt.success,
                "error": attempt.error,
                "error_type": attempt.error_type.value if attempt.error_type else None,
                "elapsed_ms": attempt.elapsed_ms,
                "http_status": attempt.http_status,
                "blocked_reason": attempt.blocked_reason,
            }
            tier_attempts.append(attempt_dict)

        # Determine block status
        blocked = result.error_type in (ErrorType.SOFT_BLOCK, ErrorType.HARD_BLOCK)
        block_type = result.error_type.value if result.error_type else None

        # Serialize validation result
        validation_dict = None
        if result.validation:
            validation_dict = {
                "valid": result.validation.valid,
                "reason": result.validation.reason,
                "content_density": result.validation.content_density,
                "is_duplicate_template": result.validation.is_duplicate_template,
            }

        entry = TraceEntry(
            run_id=self.run_id,
            url=result.url,
            timestamp=datetime.now().isoformat(),
            tier_attempts=tier_attempts,
            success_tier=result.tier,
            blocked=blocked,
            block_type=block_type,
            blocked_reason=result.blocked_reason,
            http_status=result.http_status,
            content_type=result.content_type,
            final_url=result.final_url,
            elapsed_total_ms=result.elapsed_ms or 0,
            extracted_text_length=len(result.extracted_text) if result.extracted_text else None,
            validation_result=validation_dict,
        )

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")

    def get_path(self) -> Path:
        """Get the path to the trace file."""
        return self.path

    def get_run_id(self) -> str:
        """Get the run ID for this trace."""
        return self.run_id


def read_trace_file(path: Path) -> tuple[TraceHeader, list[TraceEntry]]:
    """
    Read a trace file and return header + entries.

    Args:
        path: Path to trace file

    Returns:
        Tuple of (header, list of entries)
    """
    entries = []
    header = None

    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            data = json.loads(line.strip())
            if i == 0:
                # First line is header
                header = TraceHeader(**data)
            else:
                # Subsequent lines are entries
                entries.append(TraceEntry(**data))

    return header, entries
