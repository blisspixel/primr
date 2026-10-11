"""Discover website-summary inputs and resolve artifact-owned provenance."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from primr.core.evidence_bundle_input import read_artifact_metadata
from primr.core.model_eval import _company_similarity
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class WebsiteSummaryEvalInput:
    company: str
    working_dir: Path
    scraped_content_path: Path
    baseline_summary_path: Path
    baseline_kind: str = "provider_run"
    baseline_model: str | None = None


def _display_company_name(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.replace("_", " ")).strip()


def _present(path: Path) -> bool:
    # Dangling links and non-regular markers are present, never legacy absence.
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _bounded_text(value: Any, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("Invalid evaluation provenance text")
    return value.strip()


def resolve_website_summary_eval_input(item: WebsiteSummaryEvalInput) -> WebsiteSummaryEvalInput:
    """Artifact markers govern after copying, renaming, or direct library calls.

    A present invalid marker is an error, never evidence of a legacy provider
    run. Check both input parents as well as the caller's working directory so
    default or stale caller labels cannot select the permissive legacy parser.
    """
    roots = dict.fromkeys(
        path.absolute()
        for path in (
            item.working_dir,
            item.scraped_content_path.parent,
            item.baseline_summary_path.parent,
        )
    )
    drafts: set[tuple[str, str]] = set()
    prepared_companies: set[str] = set()
    for root in roots:
        draft_path = root / "draft_manifest.json"
        if _present(draft_path):
            metadata = read_artifact_metadata(draft_path, max_bytes=64_000)
            backend = metadata.get("backend")
            if (
                metadata.get("schema") != "primr.local-draft"
                or metadata.get("version") != "1.0"
                or metadata.get("status") != "completed"
                or metadata.get("baseline_kind") != "local_draft"
                or not isinstance(backend, dict)
            ):
                raise ValueError(
                    "Invalid or incomplete draft provenance; cannot evaluate as a provider run"
                )
            drafts.add(
                (
                    _bounded_text(metadata.get("company_name"), 200),
                    _bounded_text(backend.get("model"), 256),
                )
            )
        prep_path = root / "prep_manifest.json"
        if _present(prep_path):
            metadata = read_artifact_metadata(prep_path)
            if (
                metadata.get("schema") != "primr.host-evidence-bundle"
                or metadata.get("version") != "1.0"
                or metadata.get("status") not in {"completed", "partial"}
            ):
                raise ValueError(
                    "Invalid or incomplete prep provenance; cannot evaluate as a provider run"
                )
            prepared_companies.add(_bounded_text(metadata.get("company_name"), 200))
    if len(drafts) > 1 or len(prepared_companies | {company for company, _ in drafts}) > 1:
        raise ValueError("Conflicting evaluation provenance")
    if drafts:
        company, model = next(iter(drafts))
        return replace(item, company=company, baseline_kind="local_draft", baseline_model=model)
    if prepared_companies:
        return replace(
            item,
            company=next(iter(prepared_companies)),
            baseline_kind="prepared_evidence",
            baseline_model=None,
        )
    # A copied prep source index remains prepared input even if its manifest was
    # omitted. The index format is specific to prep, not historical provider runs.
    index_path = item.scraped_content_path.parent / "source_index.json"
    if _present(index_path):
        index = read_artifact_metadata(index_path)
        if index.get("schema") != "primr.evidence-source-index" or index.get("version") != "1.0":
            raise ValueError("Invalid prepared source provenance")
        return replace(item, baseline_kind="prepared_evidence", baseline_model=None)
    return item


def _visible_directories(root: Path) -> list[Path]:
    return [path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")]


def _discover_candidates(working_root: Path) -> list[WebsiteSummaryEvalInput]:
    # Support direct copied artifacts, flat prep/draft folders, and the existing
    # company/run layout. Folder names and depth do not confer provider trust.
    locations = [(working_root, _display_company_name(working_root.name))]
    for company_dir in _visible_directories(working_root):
        company = _display_company_name(company_dir.name)
        locations.append((company_dir, company))
        locations.extend((run, company) for run in _visible_directories(company_dir))
    results: list[WebsiteSummaryEvalInput] = []
    for candidate, company in locations:
        source = candidate / "scraped_content.txt"
        summary = candidate / "scraped_website_summary.txt"
        if not source.is_file() or not summary.is_file():
            continue
        try:
            item = resolve_website_summary_eval_input(
                WebsiteSummaryEvalInput(company, candidate, source, summary)
            )
        except (OSError, ValueError, UnicodeError) as exc:
            logger.warning(
                "Skipping evaluation input with invalid provenance at %s: %s", candidate, exc
            )
            continue
        results.append(item)
    return results


def _preferred(items: list[WebsiteSummaryEvalInput]) -> WebsiteSummaryEvalInput:
    providers = [item for item in items if item.baseline_kind == "provider_run"]
    return max(providers or items, key=lambda item: item.working_dir.as_posix())


def find_latest_website_summary_eval_inputs(
    working_root: Path, *, companies: list[str] | None = None
) -> list[WebsiteSummaryEvalInput]:
    """Prefer genuine provider baselines; keep prepared/local artifacts review-only."""
    if not working_root.is_dir():
        return []
    candidates = _discover_candidates(working_root)
    if companies:
        results: list[WebsiteSummaryEvalInput] = []
        for target in companies:
            if not candidates:
                break
            closest = max(candidates, key=lambda item: _company_similarity(target, item.company))
            if _company_similarity(target, closest.company) < 0.6:
                continue
            matches = [
                item for item in candidates if item.company.casefold() == closest.company.casefold()
            ]
            results.append(replace(_preferred(matches), company=target))
    else:
        grouped: dict[str, list[WebsiteSummaryEvalInput]] = {}
        for item in candidates:
            grouped.setdefault(item.company.casefold(), []).append(item)
        results = [_preferred(items) for items in grouped.values()]
    return sorted(results, key=lambda row: row.company.casefold())
