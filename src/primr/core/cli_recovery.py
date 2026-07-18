"""CLI recovery helpers for resuming pending Deep Research jobs.

Extracted from `primr.core.cli` for isolated unit testing.

These helpers cover three concerns: sanitizing user-provided text into
safe filename stems, deriving canonical output basenames + save paths
for recovered content, and walking the local working/ tree to surface
the most recently updated run-state JSON. The user-facing
``resume_pending_jobs`` command wires them all together.
"""

from __future__ import annotations

import glob
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from primr.config.config import OUTPUT_DIR, WORKING_DIR
from primr.utils.atomic_io import atomic_replace, atomic_write_text
from primr.utils.console import console

logger = logging.getLogger(__name__)

_ACTIVE_JOB_STATUSES = frozenset({"in_progress", "pending", "queued", "running"})
_TERMINAL_FAILURE_STATUSES = frozenset({"failed", "error", "cancelled", "canceled", "expired"})


class _RollbackIncompleteError(RuntimeError):
    """Raised when an artifact promotion failure cannot be fully rolled back."""


def _sanitize_output_stem(value: str) -> str:
    """Convert user/model-provided names into safe filename stems."""
    cleaned = re.sub(r"[^A-Za-z0-9 _-]", "", (value or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "Recovered"


def _safe_interaction_fragment(interaction_id: str) -> str:
    """Return a bounded filename-safe, collision-resistant identifier fragment."""
    normalized = str(interaction_id)
    readable = _sanitize_output_stem(normalized)[:8]
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{readable}-{digest}"


def _recovery_output_path(output_root: Path, filename: str) -> Path:
    """Build an output path and fail closed if it escapes the configured root."""
    resolved_root = output_root.resolve()
    target = output_root / filename
    if target.is_symlink():
        raise RuntimeError("Refusing to replace a symbolic-link recovery output")
    if target.resolve(strict=False).parent != resolved_root:
        raise RuntimeError("Refusing recovery output outside the configured output directory")
    return target


def _build_recovered_basename(interaction_id: str, job_info: dict[str, Any]) -> str:
    """Build canonical output basename for recovered jobs."""
    metadata: dict[str, Any] = (
        job_info.get("metadata", {}) if isinstance(job_info.get("metadata"), dict) else {}
    )
    report_kind = str(metadata.get("report_kind", "")).lower()
    strategy_type = str(metadata.get("strategy_type", "")).lower()
    company_name = _sanitize_output_stem(str(metadata.get("company_name", "")).strip())
    cloud_vendor = str(metadata.get("cloud_vendor", "")).lower().strip()
    date_str = datetime.now().strftime("%m-%d-%Y")

    if report_kind == "ai_strategy" or strategy_type == "ai":
        vendor_tag = ""
        if cloud_vendor and cloud_vendor != "agnostic":
            vendor_tag = f"_{_sanitize_output_stem(cloud_vendor).upper()}"
        return f"{company_name}_AI_Strategy{vendor_tag}_{date_str}"

    if report_kind in {
        "customer_experience",
        "modern_security_compliance",
        "data_fabric_strategy",
    }:
        labels = {
            "customer_experience": "Customer_Experience_Strategy",
            "modern_security_compliance": "Modern_Security_Compliance_Strategy",
            "data_fabric_strategy": "Data_Fabric_Strategy",
        }
        label = labels.get(report_kind, _sanitize_output_stem(report_kind))
        return f"{company_name}_{label}_{date_str}"

    if report_kind == "strategic_overview":
        return f"{company_name}_Strategic_Overview_{date_str}"

    job_type = _sanitize_output_stem(str(job_info.get("type", "deep_research")))
    return f"recovered_{job_type}_{_safe_interaction_fragment(interaction_id)}_{date_str}"


def _require_nonempty_artifact(path: Path) -> None:
    """Reject an absent, empty, non-regular, or symbolic-link artifact."""
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"Recovered artifact could not be inspected: {path.name}") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
        raise RuntimeError(f"Recovered artifact is missing or empty: {path.name}")


def _publish_recovered_bundle(
    staged: dict[str, Path],
    final: dict[str, Path],
    *,
    stage_root: Path,
) -> None:
    """Promote a complete recovery bundle and roll back in-process failures."""
    backup_root = stage_root / ".backups"
    backup_root.mkdir()
    backups: dict[str, Path] = {}
    published: list[str] = []

    try:
        for artifact_type, final_path in final.items():
            if final_path.exists() or final_path.is_symlink():
                try:
                    metadata = final_path.lstat()
                except OSError as inspection_error:
                    raise RuntimeError(
                        f"Recovery output could not be inspected: {final_path.name}"
                    ) from inspection_error
                if not stat.S_ISREG(metadata.st_mode):
                    raise RuntimeError(
                        f"Refusing to replace non-file recovery output: {final_path.name}"
                    )
                backup_path = backup_root / f"{artifact_type}.previous"
                atomic_replace(final_path, backup_path)
                backups[artifact_type] = backup_path

        for artifact_type, staged_path in staged.items():
            atomic_replace(staged_path, final[artifact_type])
            published.append(artifact_type)

        for final_path in final.values():
            _require_nonempty_artifact(final_path)
    except BaseException as exc:
        rollback_errors: list[BaseException] = []
        for artifact_type in reversed(published):
            try:
                final[artifact_type].unlink(missing_ok=True)
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)
        for artifact_type, backup_path in backups.items():
            try:
                if backup_path.exists() or backup_path.is_symlink():
                    atomic_replace(backup_path, final[artifact_type])
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise _RollbackIncompleteError(
                "Recovered artifact publication failed and rollback was incomplete; "
                f"staged and backup files remain at {stage_root}"
            ) from exc
        raise


def _cleanup_recovery_stage(stage_root: Path) -> None:
    """Remove a recovery staging directory or surface the retained path."""
    try:
        shutil.rmtree(stage_root)
    except OSError:
        logger.exception("Failed to remove recovery staging directory %s", stage_root)
        console.warn(f"Recovery staging cleanup failed; inspect: {stage_root}")


def _save_recovered_outputs(
    interaction_id: str,
    job_info: dict[str, Any],
    content: str,
) -> dict[str, str]:
    """Stage, verify, and publish canonical MD/TXT/DOCX recovery outputs."""
    from primr.output.markdown_converter import markdown_to_docx

    output_root = Path(OUTPUT_DIR)
    output_root.mkdir(parents=True, exist_ok=True)
    base_name = _build_recovered_basename(interaction_id, job_info)
    final = {
        artifact_type: _recovery_output_path(output_root, f"{base_name}.{artifact_type}")
        for artifact_type in ("md", "txt", "docx")
    }
    stage_root = Path(tempfile.mkdtemp(prefix=".primr-recovery-", dir=output_root))
    staged = {
        artifact_type: stage_root / final_path.name for artifact_type, final_path in final.items()
    }
    preserve_stage = False

    metadata: dict[str, Any] = (
        job_info.get("metadata", {}) if isinstance(job_info.get("metadata"), dict) else {}
    )
    company_name = str(metadata.get("company_name", "")).strip() or "Recovered"
    report_kind = str(metadata.get("report_kind", "")).lower()
    cloud_vendor = str(metadata.get("cloud_vendor", "")).strip()
    if report_kind == "strategic_overview":
        title = f"Strategic Overview: {company_name}"
    elif report_kind == "ai_strategy":
        title = f"AI Strategy: {company_name}"
    else:
        title = f"Recovered Research: {company_name}"

    subtitle_parts = ["Recovered from background job", interaction_id[:8]]
    if cloud_vendor:
        subtitle_parts.append(cloud_vendor.upper())
    subtitle = " | ".join(subtitle_parts)

    try:
        staged["md"].write_text(content, encoding="utf-8")
        staged["txt"].write_text(content, encoding="utf-8")
        markdown_to_docx(
            markdown_text=content,
            output_path=staged["docx"],
            title=title,
            subtitle=subtitle,
        )
        for staged_path in staged.values():
            _require_nonempty_artifact(staged_path)
        _publish_recovered_bundle(staged, final, stage_root=stage_root)
    except _RollbackIncompleteError:
        preserve_stage = True
        raise
    finally:
        if not preserve_stage:
            _cleanup_recovery_stage(stage_root)

    return {artifact_type: str(path) for artifact_type, path in final.items()}


def _find_latest_run_state() -> tuple[str, dict[str, Any]] | None:
    """Find the most recently updated run state file under working/."""
    pattern = os.path.join(WORKING_DIR, "*", "*", "_run_state.json")
    candidates = glob.glob(pattern)
    if not candidates:
        return None

    for state_path in sorted(candidates, key=os.path.getmtime, reverse=True):
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
            if isinstance(state, dict):
                return state_path, state
        except Exception as e:
            logger.warning("Skipping corrupt state file %s: %s", state_path, e)
            continue
    return None


def _show_latest_run_state_hint() -> None:
    """Print the latest local run state summary if available."""
    latest = _find_latest_run_state()
    if not latest:
        return
    path, state = latest
    company = str(state.get("company_name", "")).strip()
    if not company or company.lower() == "unknown":
        company = Path(path).parent.parent.name
    fields = (
        ("Company", company),
        ("Mode", state.get("mode")),
        ("Status", state.get("status")),
        ("Phase", state.get("current_phase")),
        ("Updated", state.get("updated_at")),
    )
    console.blank()
    console.info("Latest local run state:")
    for label, value in fields:
        rendered = str(value or "").strip()
        if rendered and rendered.lower() != "unknown":
            console.info(f"  {label}: {rendered}")
    console.info(f"  File: {path}")
    console.info("  Next: rerun the original company and URL with `--resume-local`.")


def _local_run_status_snapshot() -> dict[str, Any] | None:
    """Return the latest local run as a canonical status snapshot."""
    latest = _find_latest_run_state()
    if not latest:
        return None
    path, state = latest
    from primr.job_status import build_job_status

    company = str(state.get("company_name", "")).strip()
    if not company or company.lower() == "unknown":
        company = Path(path).parent.parent.name
    return build_job_status(
        job_id=state.get("run_id"),
        source="local_run",
        status=state.get("status"),
        company_name=company,
        mode=state.get("mode"),
        stage=state.get("current_phase"),
        percent=state.get("stage_progress_percent"),
        started_at=state.get("started_at"),
        updated_at=state.get("updated_at"),
        completed_at=state.get("completed_at"),
        artifacts_available=None,
        error_message=state.get("error"),
        error_source="local_run" if state.get("error") else None,
    )


def _read_pending_jobs() -> tuple[bool, dict[str, dict[str, Any]]]:
    """Read provider recovery records without collapsing corruption into emptiness."""
    from primr.ai.job_persistence import get_pending_jobs_with_status

    return get_pending_jobs_with_status()


def _check_pending_jobs_json(jobs: dict[str, dict[str, Any]]) -> int:
    """Emit one versioned status-list object for machine consumers."""
    from primr.ai.deep_research import get_deep_research_client
    from primr.core.cli_output import emit_json
    from primr.job_status import build_job_status, build_job_status_list

    snapshots: list[dict[str, Any]] = []
    terminal_or_observation_error = False
    client = get_deep_research_client() if jobs else None
    for interaction_id, job_info in jobs.items():
        result = client.check_job(interaction_id)
        status = str(result.get("status", "unknown")).lower()
        metadata = job_info.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        if status in _TERMINAL_FAILURE_STATUSES or status == "check_error":
            terminal_or_observation_error = True
        snapshots.append(
            build_job_status(
                job_id=interaction_id,
                source="provider_recovery",
                status=status,
                company_name=metadata.get("company_name", job_info.get("company_name")),
                mode=metadata.get("mode", job_info.get("mode")),
                stage=result.get("stage"),
                percent=result.get("stage_progress_percent"),
                submitted_at=job_info.get("started"),
                updated_at=result.get("updated_at"),
                artifacts_available=False if status == "completed" else None,
                error_message=result.get("error"),
                error_code=result.get("error_code"),
                error_source=result.get("error_source"),
            )
        )
    local = _local_run_status_snapshot()
    if local:
        snapshots.append(local)
    emit_json(build_job_status_list(snapshots))
    return 1 if terminal_or_observation_error else 0


def check_pending_jobs(json_output: bool = False) -> int:
    """Inspect cloud and local recovery state without writing artifacts."""
    from primr.ai.deep_research import get_deep_research_client
    from primr.core.cli_output import emit_json
    from primr.job_status import build_job_status_list

    read_success, jobs = _read_pending_jobs()
    if not read_success:
        message = (
            "Pending-job status could not read the recovery registry. "
            "No job state was reported or changed."
        )
        if json_output:
            payload = build_job_status_list([])
            payload["status"] = "error"
            payload["error"] = {"kind": "recovery_registry_unreadable", "message": message}
            emit_json(payload)
        else:
            console.banner("Research Job Status")
            console.error(message)
        return 1
    if json_output:
        return _check_pending_jobs_json(jobs)
    console.banner("Research Job Status")
    if not jobs:
        console.info("No pending cloud jobs found.")
        _show_latest_run_state_hint()
        return 0

    console.info(f"Found {len(jobs)} pending cloud job(s)")
    client = get_deep_research_client()
    completed = 0
    active = 0
    terminal_failures = 0
    check_errors = 0

    for interaction_id, job_info in jobs.items():
        description = str(job_info.get("description", "Unknown"))[:60]
        console.step(f"Checking: {description}...")
        console.info(f"  ID: {interaction_id}")
        started = str(job_info.get("started", "")).strip()
        if started:
            console.info(f"  Started: {started}")

        result = client.check_job(interaction_id)
        status = str(result.get("status", "unknown")).lower()
        error = result.get("error")
        error_source = result.get("error_source")

        if status == "completed":
            completed += 1
            console.ok("  Status: COMPLETED")
            if not result.get("content"):
                console.warn("  Result content is empty; the job remains recoverable.")
            console.info("  Next: run `primr --resume-latest` to finalize available outputs.")
            continue

        if status in _TERMINAL_FAILURE_STATUSES:
            terminal_failures += 1
            console.error(f"  Status: {status.upper()}")
            if error_source == "provider":
                console.error("  Source: Cloud provider reported terminal failure")
            console.error(f"  Error: {error or 'Unknown'}")
            console.info("  Next: run `primr --resume-latest` to acknowledge terminal jobs.")
            continue

        if status == "check_error":
            check_errors += 1
            console.error("  Status: CHECK ERROR")
            if error_source == "local":
                console.error("  Source: Local API connectivity/status check")
            console.error(f"  Error: {error or 'Unknown'}")
            console.info("  Job may still be running. Re-run `primr --check-jobs` later.")
            continue

        if status in _ACTIVE_JOB_STATUSES:
            active += 1
            console.info(f"  Status: {status.upper()} (still running)")
            continue

        console.info(f"  Status: {status.upper()}")
        if error:
            console.info(f"  Detail: {error}")

    console.blank()
    console.info(
        f"Cloud summary: completed={completed}, active={active}, "
        f"terminal={terminal_failures}, check_errors={check_errors}"
    )
    _show_latest_run_state_hint()
    return 1 if terminal_failures or check_errors else 0


def resume_pending_jobs() -> int:
    """Recover and finalize pending jobs into canonical outputs."""
    from primr.ai.deep_research import get_deep_research_client
    from primr.ai.job_persistence import remove_pending_job

    console.banner("Resume Pending Jobs")
    read_success, jobs = _read_pending_jobs()
    if not read_success:
        console.error(
            "Pending-job recovery could not read the recovery registry. "
            "No jobs were finalized or changed."
        )
        return 1
    if not jobs:
        console.info("No pending jobs found.")
        _show_latest_run_state_hint()
        return 0

    console.info(f"Found {len(jobs)} pending job(s)")
    client = get_deep_research_client()

    finalized = 0
    still_running = 0
    failed = 0
    check_errors = 0

    for interaction_id, job_info in jobs.items():
        description = str(job_info.get("description", "Unknown"))[:60]
        console.step(f"Resuming: {description}...")
        result = client.check_job(interaction_id)
        status = result.get("status", "unknown")
        error = result.get("error")

        if status == "completed":
            content = result.get("content", "")
            if not content:
                console.error("  Completed but returned empty content")
                failed += 1
                continue

            try:
                outputs = _save_recovered_outputs(interaction_id, job_info, content)
                console.ok("  Status: COMPLETED")
                console.ok(f"  Finalized MD: {outputs['md']}")
                console.ok(f"  Finalized DOCX: {outputs['docx']}")
                from primr.ai.job_persistence import acknowledge_pending_job_after_outputs

                if not acknowledge_pending_job_after_outputs(interaction_id, outputs.values()):
                    console.error(
                        "  Outputs saved, but the pending job record could not be updated"
                    )
                    check_errors += 1
                finalized += 1
            except Exception as e:
                console.error(f"  Finalization failed: {e}")
                try:
                    fallback_path = _recovery_output_path(
                        Path(OUTPUT_DIR),
                        f"recovered_deep_research_{_safe_interaction_fragment(interaction_id)}.txt",
                    )
                    atomic_write_text(fallback_path, content)
                except Exception as fallback_error:
                    console.error(f"  Fallback TXT could not be saved: {fallback_error}")
                else:
                    console.ok(f"  Saved fallback TXT: {fallback_path}")
                failed += 1
            continue

        if status in _ACTIVE_JOB_STATUSES:
            console.info(f"  Status: {status.upper()}")
            still_running += 1
            continue

        if status == "check_error":
            console.error("  Status: CHECK ERROR")
            console.error(f"  Error: {error or 'Unknown'}")
            check_errors += 1
            continue

        console.error(f"  Status: {status.upper()}")
        console.error(f"  Error: {error or 'Unknown'}")
        if bool(result.get("terminal", False)) or status in _TERMINAL_FAILURE_STATUSES:
            if remove_pending_job(interaction_id):
                console.info("  Removed terminal job from the pending list.")
            else:
                console.error("  The terminal job could not be removed from the pending list")
                check_errors += 1
        failed += 1

    console.blank()
    console.info(
        f"Summary: finalized={finalized}, in_progress={still_running}, "
        f"failed={failed}, check_errors={check_errors}"
    )

    if check_errors > 0:
        console.info(
            "A provider status check or local recovery-state update failed. "
            "Review the error above, then re-run `primr --resume-latest`."
        )
    if failed > 0 or check_errors > 0:
        return 1
    return 0
