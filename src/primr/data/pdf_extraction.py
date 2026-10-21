"""One-shot native PDF extraction with owned process and output budgets.

The executable worker loads platform resource support before the PDF parser.
Launching this file directly avoids the data package compatibility exports and
installs limits before importing or opening the native parser.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_PDF_TEXT_CHARS = 250_000
PDF_TIMEOUT_SECONDS = 12.0
PDF_MEMORY_BYTES = 1024 * 1024 * 1024
_TRUNCATED = "\n\n[PDF extraction truncated at its page/text budget]"


def extract_pdf_text(pdf_bytes: bytes) -> str | None:
    """Return bounded local text; parser failure, timeout and limits fail closed."""
    from primr.utils.logging_config import get_logger

    logger = get_logger(__name__)
    if not pdf_bytes or len(pdf_bytes) > MAX_PDF_BYTES or not pdf_bytes.startswith(b"%PDF-"):
        return None
    allowed = {
        "SYSTEMROOT",
        "WINDIR",
        "TMP",
        "TEMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "PATH",
        "HOME",
        "USERPROFILE",
        "LOCALAPPDATA",
        "FONTCONFIG_PATH",
        "FONTCONFIG_FILE",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    try:
        # Inherit the parent's process group / Windows Job. No scheduler or
        # detached child is introduced; cancellation retains existing ownership.
        with subprocess.Popen(
            [sys.executable, "-I", str(Path(__file__).resolve())],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
        ) as process:
            completed = False
            try:
                output, _ = process.communicate(pdf_bytes, timeout=PDF_TIMEOUT_SECONDS)
                completed = True
            finally:
                if not completed:
                    process.kill()
                    process.communicate()
        if process.returncode != 0 or len(output) > MAX_PDF_TEXT_CHARS * 4:
            logger.debug(
                "Local PDF worker rejected output (exit=%s, bytes=%d)",
                process.returncode,
                len(output),
            )
            return None
        text = output.decode("utf-8").strip()
        return text or None
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.debug("Local PDF extraction failed: %s", type(exc).__name__)
        return None


def _extract_in_process(pdf_bytes: bytes) -> str:
    """Worker-only page traversal; never called by a production parent path."""
    import fitz

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts: list[str] = []
    remaining = MAX_PDF_TEXT_CHARS - len(_TRUNCATED)
    truncated = False
    try:
        for index, page in enumerate(document):
            if index >= MAX_PDF_PAGES:
                truncated = True
                break
            text = page.get_text("text")
            if len(text) > remaining:
                parts.append(text[:remaining])
                truncated = True
                break
            parts.append(text)
            remaining -= len(text) + 1
            if remaining <= 0:
                truncated = True
                break
    finally:
        document.close()
    result = "\n".join(parts).strip()
    return result + _TRUNCATED if truncated and result else result


def _install_limits() -> Any:
    """Set OS memory limits before importing or opening a native PDF."""
    if sys.platform == "win32":
        import uuid

        # The trusted installed source root is explicit; -I ignores ambient
        # PYTHONPATH and working-directory module substitution.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from primr.utils.windows_job import attach_current_process, create_worker_job

        owner = create_worker_job(
            "Local\\Primr-pdf-" + uuid.uuid4().hex, memory_limit_bytes=PDF_MEMORY_BYTES
        )
        attach_current_process(owner.name)
        return owner
    import resource

    memory_limit = PDF_MEMORY_BYTES
    if sys.platform == "darwin":
        import psutil

        # Darwin counts existing runtime/shared-library mappings and rejects
        # a limit below them. Bound subsequent allocation, before PDF loading.
        memory_limit += int(psutil.Process().memory_info().vms)
    for kind, limit in (
        (resource.RLIMIT_AS, memory_limit),
        (resource.RLIMIT_CPU, math.ceil(PDF_TIMEOUT_SECONDS)),
    ):
        for inherited in resource.getrlimit(kind):
            if inherited != resource.RLIM_INFINITY:
                limit = min(limit, inherited)
        resource.setrlimit(kind, (limit, limit))
    return None


def _worker() -> int:
    try:
        owner = _install_limits()
        # Native diagnostics must not fill the data pipe. Retain a separate
        # writer solely for our bounded result, and discard native stdout.
        output_fd = os.dup(sys.stdout.fileno())
        with open(os.devnull, "wb") as discard:
            os.dup2(discard.fileno(), sys.stdout.fileno())
        with os.fdopen(output_fd, "wb") as output:
            pdf_bytes = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
            if len(pdf_bytes) > MAX_PDF_BYTES or not pdf_bytes.startswith(b"%PDF-"):
                return 1
            text = _extract_in_process(pdf_bytes)
            output.write(text.encode("utf-8"))
            output.flush()
        # Keep Windows kill-on-close ownership live until process exit.
        _ = owner
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(_worker())
