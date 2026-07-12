"""Atomic terminal audit manifests for supervised research workers."""

from __future__ import annotations

import json
from pathlib import Path

from primr.mcp_server.job_store import ResearchJobState
from primr.utils.atomic_io import atomic_replace
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


def write_terminal_manifest(
    *,
    job: ResearchJobState,
    output_dir: Path,
    company_url: str,
    mode: str,
    budget_usd: float | None,
    return_code: int | None,
    cancel_reason: str | None,
    termination_method: str | None,
) -> str | None:
    """Persist a compact audit manifest and return its path on success."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "run_manifest.json"
    temp_path = manifest_path.with_suffix(".tmp")
    actual_time_minutes = None
    if job.completion_time is not None:
        elapsed = job.completion_time - job.start_time
        actual_time_minutes = max(0, int(elapsed.total_seconds() / 60))
    manifest = {
        "schema_version": "1.1",
        "job_id": job.job_id,
        "company_name": job.company_name,
        "company_url": company_url,
        "mode": mode,
        "estimate": {
            "cost_usd": None,
            "time_minutes": None,
            "estimated_at": None,
        },
        "approval": {
            "token": None,
            "approved_at": None,
            "approved_by": job.owner_client_id or "stdio",
            "bound_to_estimate": False,
        },
        "budget": {
            "approved_ceiling_usd": budget_usd,
            "runtime_budget_active": bool(budget_usd and budget_usd > 0),
            "enforcement": None,
        },
        "execution": {
            "started_at": job.start_time.isoformat(),
            "completed_at": (
                job.completion_time.isoformat() if job.completion_time is not None else None
            ),
            "status": job.get_status().value,
            "actual_cost_usd": None,
            "actual_time_minutes": actual_time_minutes,
        },
        "termination": {
            "worker_exit_confirmed": True,
            "worker_return_code": return_code,
            "reason": cancel_reason or job.error_type,
            "method": termination_method or "cooperative",
            "remote_provider_status": "unknown",
        },
        "artifacts": list(job.output_paths),
    }
    try:
        with open(temp_path, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
        atomic_replace(temp_path, manifest_path)
    except (OSError, TypeError, ValueError):
        temp_path.unlink(missing_ok=True)
        logger.exception("Failed to write terminal manifest for job %s", job.job_id)
        return None
    return str(manifest_path)


__all__ = ["write_terminal_manifest"]
