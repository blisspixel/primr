"""Pending Deep Research job persistence.

Extracted from `primr.ai.deep_research` for isolated unit testing.

These helpers manage the `pending_research_jobs.json` file under
`LOGS_DIR`, using a module-level file lock to prevent concurrent-write
corruption when the same process kicks off multiple research runs.
Atomic writes go via temp file + replace to keep the file consistent
even if the process dies mid-write.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_jobs_file_lock = threading.Lock()


def _get_jobs_file_path() -> str:
    """Get path to the jobs tracking file."""
    from primr.config.config import LOGS_DIR

    return os.path.join(LOGS_DIR, "pending_research_jobs.json")


def save_pending_job(
    interaction_id: str,
    job_type: str,
    description: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Save a pending research job for later recovery.

    Thread-safe: Uses file locking to prevent concurrent write corruption.
    """
    jobs_file = _get_jobs_file_path()

    with _jobs_file_lock:
        jobs = {}
        if os.path.exists(jobs_file):
            try:
                with open(jobs_file, encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        jobs = json.loads(content)
                        if not isinstance(jobs, dict):
                            logger.warning("Jobs file corrupted (not a dict), resetting")
                            jobs = {}
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load jobs file, resetting: {e}")
                jobs = {}

        jobs[interaction_id] = {
            "type": job_type,
            "description": description,
            "started": datetime.now().isoformat(),
            "status": "pending",
            "metadata": metadata or {},
        }

        os.makedirs(os.path.dirname(jobs_file), exist_ok=True)
        temp_file = jobs_file + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(jobs, f, indent=2)
            if os.path.exists(jobs_file):
                os.replace(temp_file, jobs_file)
            else:
                os.rename(temp_file, jobs_file)
        except OSError as e:
            logger.error(f"Failed to save jobs file: {e}")
            if os.path.exists(temp_file):
                with contextlib.suppress(OSError):
                    os.remove(temp_file)
            raise

    logger.info(f"Saved pending job: {interaction_id} ({job_type})")


def remove_pending_job(interaction_id: str) -> None:
    """Remove a job from the pending list (after completion or failure).

    Thread-safe: Uses file locking to prevent concurrent write corruption.
    """
    jobs_file = _get_jobs_file_path()

    with _jobs_file_lock:
        if not os.path.exists(jobs_file):
            return

        try:
            with open(jobs_file, encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return
                jobs = json.loads(content)
                if not isinstance(jobs, dict):
                    logger.warning("Jobs file corrupted, cannot remove job")
                    return

            if interaction_id in jobs:
                del jobs[interaction_id]
                temp_file = jobs_file + ".tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(jobs, f, indent=2)
                os.replace(temp_file, jobs_file)
                logger.info(f"Removed completed job: {interaction_id}")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to remove job {interaction_id}: {e}")


def get_pending_jobs() -> dict[str, dict[str, Any]]:
    """Get all pending research jobs.

    Thread-safe: Uses file locking for consistent reads.
    """
    jobs_file = _get_jobs_file_path()

    with _jobs_file_lock:
        if not os.path.exists(jobs_file):
            return {}

        try:
            with open(jobs_file, encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                result = json.loads(content)
                if not isinstance(result, dict):
                    logger.warning("Jobs file corrupted (not a dict)")
                    return {}
                return result
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read jobs file: {e}")
            return {}
