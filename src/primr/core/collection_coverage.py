"""Collection counts bound to one explicit run or verified prep bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from primr.core.evidence_bundle_input import load_prepared_evidence, read_artifact_metadata
from primr.core.trusted_report import ReportSnapshotError
from primr.output.collection_coverage import CollectionCoverage
from primr.utils.atomic_io import atomic_write_text

_PAGE_TYPES = frozenset(
    {
        "first_party",
        "first_party_fallback",
        "archived_first_party",
        "regulatory",
        "reference",
        "model_synthesis",
        "public_fallback",
    }
)


def coverage_from_index(index: dict[str, Any], *, usable: bool | None = None) -> CollectionCoverage:
    """Count captured rows, preserving the collector's existing classification."""
    if index.get("schema") != "primr.evidence-source-index" or index.get("version") != "1.0":
        raise ValueError("Unsupported collection source index")
    rows = index.get("sources")
    if not isinstance(rows, list) or len(rows) > 2_000:
        raise ValueError("Invalid collection source rows")
    pages = first_party = hiring = 0
    identities: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid collection source row")
        identity = row.get("source_id")
        if not isinstance(identity, str) or not identity or identity in identities:
            raise ValueError("Invalid or duplicate collection source identity")
        identities.add(identity)
        source_type = row.get("source_type")
        if not isinstance(source_type, str):
            raise ValueError("Invalid collection source classification")
        if source_type == "hiring":
            if row.get("identity") != "verified" or not row.get("url"):
                raise ValueError("Unverified hiring source")
            hiring += 1
        elif source_type in _PAGE_TYPES:
            count = row.get("captured_characters")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("Invalid captured character count")
            if count:
                pages += 1
                first_party += source_type == "first_party"
        else:
            raise ValueError("Unknown collection source classification")
    return CollectionCoverage(
        pages_captured=pages, first_party_pages=first_party, hiring_postings=hiring, usable=usable
    )


def record_run_collection(
    folder_path: str, company_url: str | None, corpus: dict[str, str]
) -> None:
    """Persist the same source inventory used by prep, without another collection."""
    from primr.core.evidence_bundle import _build_source_rows
    from primr.core.run_state_io import _update_run_state

    index = {
        "schema": "primr.evidence-source-index",
        "version": "1.0",
        "sources": _build_source_rows(Path(folder_path), company_url or "", corpus),
    }
    summary = coverage_from_index(index)
    serialized = json.dumps(index, indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(Path(folder_path) / "source_index.json", serialized)
    _update_run_state(
        folder_path,
        collection_coverage={
            "source_index_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            "pages_captured": summary.pages_captured,
            "first_party_pages": summary.first_party_pages,
            "hiring_postings": summary.hiring_postings,
        },
    )


def load_run_coverage(folder_path: str | Path | None) -> CollectionCoverage:
    """Missing, tampered, or legacy records stay unknown, never guessed as zero."""
    if folder_path is None:
        return CollectionCoverage()
    root = Path(folder_path)
    try:
        state = read_artifact_metadata(root / "_run_state.json")
        record = state.get("collection_coverage")
        if not isinstance(record, dict):
            return CollectionCoverage()
        # The bounded reader verifies a stable, regular, non-link metadata file.
        index = read_artifact_metadata(root / "source_index.json")
        serialized = json.dumps(index, indent=2, ensure_ascii=False) + "\n"
        if hashlib.sha256(serialized.encode("utf-8")).hexdigest() != record.get(
            "source_index_sha256"
        ):
            return CollectionCoverage()
        summary = coverage_from_index(index)
        for key in ("pages_captured", "first_party_pages", "hiring_postings"):
            if record.get(key) != getattr(summary, key):
                return CollectionCoverage()
        return summary
    except (OSError, ValueError, TypeError):
        return CollectionCoverage()


def load_prep_coverage(bundle: str | Path) -> CollectionCoverage:
    """Explicit render inputs must pass the existing full prep integrity gate."""
    try:
        prepared = load_prepared_evidence(Path(bundle))
    except ReportSnapshotError as exc:
        raise ValueError("Cannot read a stable prep bundle") from exc
    index = json.loads(prepared.source_index)
    # Earlier source indexes recorded raw character counts only. The shared
    # reader has already verified their complete framing and source identities;
    # count the bound, nonempty captures instead of guessing from raw lengths.
    captured_characters = {source.source_id: len(source.text) for source in prepared.sources}
    for row in index["sources"]:
        if row.get("source_type") != "hiring" and "captured_characters" not in row:
            row["captured_characters"] = captured_characters.get(row["source_id"], 0)
    return coverage_from_index(index, usable=prepared.status == "completed")


def load_diagnostics_coverage(diagnostics_dir: str | Path | None) -> CollectionCoverage | None:
    """Use only an explicitly owned run's diagnostics directory."""
    if diagnostics_dir is None or Path(diagnostics_dir).name != "_diagnostics":
        return None
    return load_run_coverage(Path(diagnostics_dir).parent)
