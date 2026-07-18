"""Pending Deep Research job persistence.

Extracted from `primr.ai.deep_research` for isolated unit testing.

These helpers manage the `pending_research_jobs.json` file under
`LOGS_DIR`, using thread and operating-system file locks to serialize
read-modify-write mutations across Primr processes. Atomic writes go via a
temp file plus `atomic_replace` (which retries transient Windows file locks)
to keep the file consistent even if a process dies mid-write.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import logging
import os
import stat
import threading
import time
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from primr.utils.atomic_io import atomic_replace

logger = logging.getLogger(__name__)

_jobs_file_lock = threading.Lock()
_LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_POLL_SECONDS = 0.05


def _get_jobs_file_path() -> str:
    """Get path to the jobs tracking file."""
    from primr.config.config import LOGS_DIR

    return os.path.join(LOGS_DIR, "pending_research_jobs.json")


def _try_lock(stream: BinaryIO) -> None:
    """Acquire one byte of the persistent lock file without waiting."""
    stream.seek(0)
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        return

    fcntl = importlib.import_module("fcntl")
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(stream: BinaryIO) -> None:
    """Release the platform lock held by ``stream``."""
    stream.seek(0)
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return

    fcntl = importlib.import_module("fcntl")
    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _pending_jobs_mutation_lock(jobs_file: str) -> Iterator[None]:
    """Serialize one pending-job mutation across local Primr processes."""
    parent = os.path.dirname(jobs_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    lock_path = f"{jobs_file}.lock"
    stream = open(lock_path, "a+b")  # noqa: SIM115
    acquired = False
    try:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()

        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        while True:
            try:
                _try_lock(stream)
                acquired = True
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Timed out waiting for pending-job registry lock: {lock_path}"
                    ) from exc
                time.sleep(_LOCK_POLL_SECONDS)
        yield
    finally:
        if acquired:
            try:
                _unlock(stream)
            except OSError as exc:
                logger.warning("Failed to release pending-job registry lock: %s", exc)
        stream.close()


def save_pending_job(
    interaction_id: str,
    job_type: str,
    description: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Save a pending research job for later recovery.

    Safe across threads and processes that use these persistence helpers.
    """
    jobs_file = _get_jobs_file_path()

    with _jobs_file_lock, _pending_jobs_mutation_lock(jobs_file):
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
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load jobs file, resetting: {e}")
                jobs = {}

        jobs[interaction_id] = {
            "type": job_type,
            "description": description,
            "started": datetime.now().isoformat(),
            "status": "pending",
            "metadata": metadata or {},
        }

        temp_file = jobs_file + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(jobs, f, indent=2)
            atomic_replace(temp_file, jobs_file)
        except OSError as e:
            logger.error(f"Failed to save jobs file: {e}")
            if os.path.exists(temp_file):
                with contextlib.suppress(OSError):
                    os.remove(temp_file)
            raise

    logger.info(f"Saved pending job: {interaction_id} ({job_type})")


def remove_pending_jobs(interaction_ids: Iterable[str]) -> tuple[bool, int]:
    """Atomically remove selected pending-job records.

    Only identifiers supplied by the caller are removed. Records added after an
    operator preview therefore remain available for recovery. The return value
    is ``(success, removed_count)``; malformed or unwritable state fails closed.
    """
    requested_ids = frozenset(interaction_ids)
    if not requested_ids:
        return True, 0

    jobs_file = _get_jobs_file_path()

    try:
        with _jobs_file_lock, _pending_jobs_mutation_lock(jobs_file):
            temp_file = jobs_file + ".tmp"
            temp_owned = False
            try:
                if not os.path.exists(jobs_file):
                    return True, 0

                with open(jobs_file, encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        return True, 0
                    jobs = json.loads(content)
                    if not isinstance(jobs, dict):
                        logger.warning("Jobs file corrupted, cannot remove pending records")
                        return False, 0

                matched_ids = requested_ids.intersection(jobs)
                if not matched_ids:
                    return True, 0

                for interaction_id in matched_ids:
                    del jobs[interaction_id]
                with open(temp_file, "w", encoding="utf-8") as f:
                    temp_owned = True
                    json.dump(jobs, f, indent=2)
                atomic_replace(temp_file, jobs_file)
                logger.info("Removed %d pending job record(s)", len(matched_ids))
                return True, len(matched_ids)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
                logger.warning("Failed to remove pending job records: %s", e)
                if temp_owned and os.path.exists(temp_file):
                    with contextlib.suppress(OSError):
                        os.remove(temp_file)
                return False, 0
    except OSError as e:
        logger.warning("Pending-job mutation could not start safely: %s", e)
        return False, 0


def remove_pending_job(interaction_id: str) -> bool:
    """Remove one job after completion or failure.

    Returns ``True`` when the job is absent after the operation and ``False``
    when persistence could not be read or updated safely.
    """
    success, _ = remove_pending_jobs((interaction_id,))
    return success


def acknowledge_pending_job_after_outputs(
    interaction_id: str,
    output_paths: Iterable[str | os.PathLike[str]],
) -> bool:
    """Acknowledge a pending job only after every required output is durable.

    A durable output is a closed, regular, non-empty file. Callers define the
    required artifact contract by passing exactly the paths that must exist.
    """
    if not interaction_id:
        return True

    paths = tuple(Path(path) for path in output_paths)
    if not paths:
        logger.warning("Refusing to acknowledge job %s without output paths", interaction_id)
        return False

    for path in paths:
        try:
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
                logger.warning(
                    "Retaining job %s because required output is not durable: %s",
                    interaction_id,
                    path,
                )
                return False
        except OSError as exc:
            logger.warning(
                "Retaining job %s because required output could not be inspected: %s",
                interaction_id,
                exc,
            )
            return False

    return remove_pending_job(interaction_id)


def get_pending_jobs_with_status() -> tuple[bool, dict[str, dict[str, Any]]]:
    """Read pending jobs and report whether persisted state was valid.

    Thread-safe: Uses file locking for consistent reads.
    """
    jobs_file = _get_jobs_file_path()

    with _jobs_file_lock:
        if not os.path.exists(jobs_file):
            return True, {}

        try:
            with open(jobs_file, encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return True, {}
                result = json.loads(content)
                if not isinstance(result, dict):
                    logger.warning("Jobs file corrupted (not a dict)")
                    return False, {}
                if not all(isinstance(job, dict) for job in result.values()):
                    logger.warning("Jobs file corrupted (job entry is not an object)")
                    return False, {}
                return True, result
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read jobs file: {e}")
            return False, {}


def get_pending_jobs() -> dict[str, dict[str, Any]]:
    """Get pending jobs, preserving the legacy empty-on-read-failure API."""
    _, jobs = get_pending_jobs_with_status()
    return jobs
