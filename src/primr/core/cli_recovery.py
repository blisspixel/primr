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
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from primr.config.config import OUTPUT_DIR, WORKING_DIR
from primr.utils.console import console

logger = logging.getLogger(__name__)


def _sanitize_output_stem(value: str) -> str:
    """Convert user/model-provided names into safe filename stems."""
    cleaned = re.sub(r"[^A-Za-z0-9 _-]", "", (value or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "Recovered"


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
        vendor_tag = (
            f"_{cloud_vendor.upper()}" if cloud_vendor and cloud_vendor != "agnostic" else ""
        )
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

    job_type = _sanitize_output_stem(job_info.get("type", "deep_research"))
    return f"recovered_{job_type}_{interaction_id[:8]}_{date_str}"


def _save_recovered_outputs(
    interaction_id: str,
    job_info: dict[str, Any],
    content: str,
) -> dict[str, str]:
    """Save recovered content to canonical MD/TXT/DOCX paths."""
    from primr.output.markdown_converter import markdown_to_docx

    base_name = _build_recovered_basename(interaction_id, job_info)
    base_path = Path(OUTPUT_DIR) / base_name
    md_path = str(base_path.with_suffix(".md"))
    txt_path = str(base_path.with_suffix(".txt"))
    docx_path = str(base_path.with_suffix(".docx"))

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(content)

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

    markdown_to_docx(
        markdown_text=content,
        output_path=Path(docx_path),
        title=title,
        subtitle=subtitle,
    )

    return {"md": md_path, "txt": txt_path, "docx": docx_path}


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
    company = state.get("company_name", "Unknown")
    mode = state.get("mode", "unknown")
    status = state.get("status", "unknown")
    phase = state.get("current_phase", "unknown")
    updated = state.get("updated_at", "unknown")
    console.blank()
    console.info("Latest local run state:")
    console.info(f"  Company: {company}")
    console.info(f"  Mode: {mode}")
    console.info(f"  Status: {status}")
    console.info(f"  Phase: {phase}")
    console.info(f"  Updated: {updated}")
    console.info(f"  File: {path}")


def resume_pending_jobs() -> int:
    """Recover and finalize pending jobs into canonical outputs."""
    from primr.ai.deep_research import get_deep_research_client, get_pending_jobs

    console.banner("Resume Pending Jobs")
    jobs = get_pending_jobs()
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
                finalized += 1
            except Exception as e:
                fallback_path = os.path.join(
                    OUTPUT_DIR, f"recovered_deep_research_{interaction_id[:8]}.txt"
                )
                with open(fallback_path, "w", encoding="utf-8") as f:
                    f.write(content)
                console.error(f"  Finalization failed: {e}")
                console.ok(f"  Saved fallback TXT: {fallback_path}")
                failed += 1
            continue

        if status == "in_progress":
            console.info("  Status: IN PROGRESS")
            still_running += 1
            continue

        if status == "check_error":
            console.error("  Status: CHECK ERROR")
            console.error(f"  Error: {error or 'Unknown'}")
            check_errors += 1
            continue

        console.error(f"  Status: {status}")
        console.error(f"  Error: {error or 'Unknown'}")
        failed += 1

    console.blank()
    console.info(
        f"Summary: finalized={finalized}, in_progress={still_running}, "
        f"failed={failed}, check_errors={check_errors}"
    )

    if check_errors > 0:
        console.info(
            "Network/API issue detected during resume. Re-run `primr --resume-latest` "
            "when connectivity is stable."
        )
        # Only signal failure when nothing was finalized — a transient check
        # error on one job must not mask other jobs that completed successfully.
        if finalized == 0:
            return 1
    if failed > 0 and finalized == 0:
        return 1
    return 0
