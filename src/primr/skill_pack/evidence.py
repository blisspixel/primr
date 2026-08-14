"""Standalone evidence collection for the skill pack pipeline.

When `primr skills <Company> <url>` is run without `--from-report`, this
module produces just enough evidence — DNS recon + hiring signals — into
a fresh working directory so the pipeline has something to ground on.
Explicit career URLs can supply hiring evidence without implying a DNS
recon target.

This is intentionally NARROWER than `primr scrape`: no full corpus build,
no link discovery, no LLM summarization of pages. Recon is free; hiring
signals are ~3-5 free DDG searches + 1 small LLM triage call.

Cost target for the standalone evidence phase: ~$0.02-0.05. Time: 30-90s.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _extract_domain(url: str) -> str | None:
    """Reuse the same domain-extraction logic the research pipeline uses."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = (parsed.hostname or "").lower()
        if not host:
            return None
        # Strip a single www. prefix; preserve www2/wwwx subdomains.
        if host.startswith("www.") and host.count(".") >= 2:
            host = host[4:]
        return host
    except Exception:
        return None


def collect_evidence(
    company_name: str,
    company_url: str | None,
    working_dir: Path,
    *,
    corpus: dict[str, str] | None = None,
    career_urls: list[str] | None = None,
    skip_recon: bool = False,
    skip_hiring: bool = False,
) -> dict[str, str | None]:
    """Run recon + hiring against the company, writing into `working_dir`.

    Returns a dict with paths to the written files (or None for any
    source that failed or was skipped). The pipeline can then read those
    files via the standard discovery.load_evidence() path.

    Both phases fail open: a missing recon or hiring file is handled
    upstream by the discovery prompt's sparse-signal mode.
    """
    working_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, str | None] = {"recon": None, "hiring": None}
    career_urls = career_urls or []

    if not skip_recon and company_url:
        result["recon"] = _collect_recon(company_url, working_dir)

    hiring_seed_url = company_url or (career_urls[0] if career_urls else None)
    if not skip_hiring and hiring_seed_url:
        result["hiring"] = _collect_hiring(
            company_name,
            hiring_seed_url,
            working_dir,
            corpus=corpus,
            career_urls=career_urls,
        )

    return result


def _collect_recon(company_url: str, working_dir: Path) -> str | None:
    domain = _extract_domain(company_url)
    if not domain:
        logger.warning("Could not extract domain from %s — skipping recon", company_url)
        return None

    try:
        from recon_tool.resolver import resolve_tenant

        from primr.core.recon_context import format_recon_context
        from primr.utils.async_utils import run_sync_new_loop
        from primr.utils.atomic_io import atomic_write_text
    except ImportError as exc:
        logger.warning("recon-tool unavailable — skipping recon: %s", exc)
        return None

    try:
        # MCP generate_skill_pack and other async callers already have a loop.
        # asyncio.run() would fail there and silently drop DNS/tenant evidence.
        info, _ = run_sync_new_loop(asyncio.wait_for(resolve_tenant(domain), timeout=20.0))
    except Exception as exc:
        logger.warning("Recon failed for %s: %s", domain, exc)
        return None

    try:
        text = format_recon_context(info)
        out_path = working_dir / "_recon_context.txt"
        atomic_write_text(out_path, text)
        logger.info("Wrote recon context to %s", out_path)
        return str(out_path)
    except Exception as exc:
        logger.warning("Failed to write recon context: %s", exc)
        return None


def _collect_hiring(
    company_name: str,
    company_url: str,
    working_dir: Path,
    *,
    corpus: dict[str, str] | None = None,
    career_urls: list[str] | None = None,
) -> str | None:
    if os.getenv("PRIMR_SKIP_HIRING_SIGNALS", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("Hiring signals skipped via PRIMR_SKIP_HIRING_SIGNALS env var")
        return None

    try:
        from primr.data.hiring_signals import gather_hiring_signals
    except ImportError as exc:
        logger.warning("Hiring signals module unavailable: %s", exc)
        return None

    try:
        signals = gather_hiring_signals(
            company_name,
            company_url,
            corpus=corpus,
            working_folder=str(working_dir),
            career_urls=career_urls or [],
        )
    except Exception as exc:
        logger.warning("Hiring signals collection failed: %s", exc)
        return None

    if signals is None:
        logger.info("Hiring signals returned None (no postings found)")
        return None

    hiring_path = working_dir / "_hiring" / "hiring_signals.md"
    if hiring_path.exists():
        logger.info("Wrote hiring signals to %s", hiring_path)
        return str(hiring_path)
    return None


__all__ = ["collect_evidence"]
