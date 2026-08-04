"""Layer-1 progressive working brief (deterministic, zero model calls).

Assembles a clearly incomplete mid-run artifact after scrape (+ recon) so
operators and agents have something useful before long reasoning finishes.
See ``docs/design/progressive-artifacts.md``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from primr.utils.atomic_io import atomic_write_text
from primr.utils.logging_config import get_logger
from primr.utils.validators import sanitize_for_filename

logger = get_logger(__name__)

WORKING_BRIEF_BANNER = "WORKING BRIEF — incomplete; not the Strategic Overview"
WORKING_BRIEF_MARKER = "Working_Brief"
_PENDING_STAGES: tuple[str, ...] = (
    "Research deepening",
    "Analysis workbook",
    "Report section writing",
    "Cross-validation",
    "Trust polish",
    "Strategy generation (if requested)",
)


@dataclass(frozen=True)
class WorkingBriefInput:
    """Body-free structured evidence for a working brief (no report prose)."""

    company_name: str
    website: str | None = None
    run_id: str | None = None
    scraped_urls: Sequence[str] = field(default_factory=tuple)
    pages_scraped: int = 0
    external_urls: Sequence[str] = field(default_factory=tuple)
    external_source_count: int = 0
    recon_excerpt: str | None = None
    hiring_postings_found: int | None = None
    hiring_postings_extracted: int | None = None
    hiring_source: str | None = None
    pending_stages: Sequence[str] = field(default_factory=lambda: _PENDING_STAGES)
    generated_at: datetime | None = None


def assemble_working_brief(payload: WorkingBriefInput) -> str:
    """Return markdown for a working brief. Pure: no I/O, no model calls."""
    when = payload.generated_at or datetime.now(timezone.utc)
    stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    company = (payload.company_name or "Company").strip() or "Company"
    website = (payload.website or "").strip()
    run_id = (payload.run_id or "").strip()

    lines: list[str] = [
        f"# {company} — Working Brief",
        "",
        f"> **{WORKING_BRIEF_BANNER}**",
        ">",
        "> This file is an intermediate, deterministic assembly of collected",
        "> evidence. It is not the Strategic Overview and must not be shipped",
        "> as a final deliverable.",
        "",
        "## Run",
        "",
        f"- **Company:** {company}",
    ]
    if website:
        lines.append(f"- **Website:** {website}")
    if run_id:
        lines.append(f"- **Run folder:** `{run_id}`")
    lines.extend([f"- **Generated:** {stamp}", ""])

    lines.extend(["## Recon / DNS", ""])
    if payload.recon_excerpt and payload.recon_excerpt.strip():
        lines.append("```")
        lines.append(payload.recon_excerpt.strip()[:4000])
        lines.append("```")
    else:
        lines.append("_No recon context available yet (skipped or not run)._")
    lines.append("")

    pages = payload.pages_scraped or len(payload.scraped_urls)
    lines.extend(
        [
            "## First-party collection",
            "",
            f"- **Pages scraped:** {pages}",
        ]
    )
    top_pages = list(payload.scraped_urls)[:15]
    if top_pages:
        lines.append("- **Sample URLs:**")
        for url in top_pages:
            lines.append(f"  - {url}")
    else:
        lines.append("- **Sample URLs:** _(none)_")
    lines.append("")

    ext_count = payload.external_source_count or len(payload.external_urls)
    domains = _unique_domains(payload.external_urls)
    lines.extend(
        [
            "## External sources",
            "",
            f"- **Validated sources:** {ext_count}",
        ]
    )
    if domains:
        lines.append("- **Domains:**")
        for domain in domains[:20]:
            lines.append(f"  - {domain}")
    else:
        lines.append("- **Domains:** _(none yet)_")
    lines.append("")

    lines.extend(["## Hiring signals", ""])
    if payload.hiring_postings_found is None and payload.hiring_postings_extracted is None:
        lines.append("_Hiring scan not finished or not run._")
    else:
        found = payload.hiring_postings_found or 0
        extracted = payload.hiring_postings_extracted or 0
        source = payload.hiring_source or "unknown"
        lines.append(f"- **Source:** {source}")
        lines.append(f"- **Postings found:** {found}")
        lines.append(f"- **Postings extracted:** {extracted}")
    lines.append("")

    lines.extend(
        [
            "## Still running",
            "",
            "The following stages have not produced a final Strategic Overview yet:",
            "",
        ]
    )
    for stage in payload.pending_stages:
        lines.append(f"- [ ] {stage}")
    lines.extend(
        [
            "",
            "---",
            "",
            f"_{WORKING_BRIEF_BANNER}_",
            "",
        ]
    )
    return "\n".join(lines)


def working_brief_filename(company_name: str, when: datetime | None = None) -> str:
    """Public deliverable filename (never Strategic_Overview)."""
    stamp = (when or datetime.now()).strftime("%m-%d-%Y")
    safe = sanitize_for_filename(company_name or "Company", max_length=200)
    return f"{safe}_{WORKING_BRIEF_MARKER}_{stamp}.md"


def write_working_brief(
    payload: WorkingBriefInput,
    *,
    working_folder: str | Path | None = None,
    public_output_dir: str | Path | None = None,
) -> list[Path]:
    """Write the brief to working folder and optional public output. Fail-open."""
    markdown = assemble_working_brief(payload)
    written: list[Path] = []
    when = payload.generated_at or datetime.now(timezone.utc)

    if working_folder is not None:
        path = Path(working_folder) / "working_brief.md"
        try:
            atomic_write_text(path, markdown)
            written.append(path)
        except OSError as exc:
            logger.warning("Working brief write failed for %s: %s", path, exc)

    if public_output_dir is not None:
        path = Path(public_output_dir) / working_brief_filename(payload.company_name, when)
        try:
            Path(public_output_dir).mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, markdown)
            written.append(path)
        except OSError as exc:
            logger.warning("Working brief public write failed for %s: %s", path, exc)

    return written


def read_recon_excerpt(folder_path: str | Path, *, max_chars: int = 4000) -> str | None:
    """Load a truncated recon context file when present."""
    path = Path(folder_path) / "_recon_context.txt"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return None
    return text[:max_chars]


def _unique_domains(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if not host or host in seen:
            continue
        seen.add(host)
        ordered.append(host)
    return ordered
