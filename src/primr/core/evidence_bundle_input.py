"""Verified, bounded prep-bundle inputs for offline evidence consumers."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from primr.core.trusted_report import (
    ReportSnapshotError,
    stable_report_snapshot,
    validate_trusted_report,
)

MAX_METADATA_BYTES = 2_000_000
MAX_SCRAPED_BYTES = 8_000_000


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    url: str
    text: str


@dataclass(frozen=True)
class PreparedEvidence:
    root: Path
    company: str
    status: str
    limitations: tuple[str, ...]
    sources: tuple[EvidenceSource, ...]
    indexed_sources: int
    scraped_content: str
    source_index: str
    manifest_sha256: str


def parse_scraped_content_text(text: str) -> dict[str, str]:
    """Read the shared URL-delimited scrape format used by prep and run folders."""
    pattern = re.compile(
        r"^URL:\s*(?P<url>.+?)\n=+\n(?P<content>.*?)(?=^=+\nURL:\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    scraped: dict[str, str] = {}
    for match in pattern.finditer(text):
        url, content = match.group("url").strip(), match.group("content").strip()
        if url and content:
            scraped[url] = content
    return scraped


def _read_verified(root: Path, name: str, max_bytes: int) -> bytes:
    report = validate_trusted_report(root / name, allowed_roots=[root], max_bytes=max_bytes)
    with (
        tempfile.TemporaryDirectory(prefix="primr-draft-input-") as directory,
        stable_report_snapshot(report, directory) as snapshot,
    ):
        return snapshot.read_bytes()


def _object(content: bytes) -> dict[str, Any]:
    try:
        value = json.loads(content.decode("utf-8"))
    except RecursionError as exc:
        raise ValueError("Prep metadata exceeds the JSON nesting limit") from exc
    if not isinstance(value, dict):
        raise ValueError("Prep metadata must be a JSON object")
    return value


def read_artifact_metadata(path: Path, *, max_bytes: int = MAX_METADATA_BYTES) -> dict[str, Any]:
    """Read bounded JSON metadata through the same no-link snapshot boundary."""
    try:
        return _object(_read_verified(path.parent, path.name, max_bytes))
    except ReportSnapshotError as exc:
        raise ValueError("Cannot read stable artifact metadata") from exc


def _bind_prepared_sources(index: dict[str, Any], text: str) -> tuple[EvidenceSource, ...]:
    """Reconcile every serialized frame with a captured row before assigning IDs.

    Bodies are untrusted and can contain apparent headers. The real writer emits
    one frame per captured URL. Extra, duplicate, or missing frames are ambiguous
    even when the containing artifact hashes match. Hiring metadata is not text.
    """
    if index.get("schema") != "primr.evidence-source-index" or index.get("version") != "1.0":
        raise ValueError("Unsupported prep source index")
    rows = index.get("sources")
    if not isinstance(rows, list) or len(rows) > 2_000:
        raise ValueError("Source index is malformed or exceeds the allowed size")
    source_ids: set[str] = set()
    captured: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Source index entries must be objects")
        source_id, url, characters = row.get("source_id"), row.get("url"), row.get("characters")
        if (
            not isinstance(source_id, str)
            or not re.fullmatch(r"S[0-9]{3,6}", source_id)
            or source_id in source_ids
            or not isinstance(url, str)
            or not 0 < len(url) <= 2_048
            or not isinstance(characters, int)
            or isinstance(characters, bool)
            or not 0 <= characters <= MAX_SCRAPED_BYTES
        ):
            raise ValueError("Source index has invalid or repeated source identities")
        source_ids.add(source_id)
        digest = row.get("captured_text_sha256")
        if "captured_text_sha256" in row or "captured_characters" in row:
            count = row.get("captured_characters")
            if (
                not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not isinstance(count, int)
                or isinstance(count, bool)
                or not 0 <= count <= characters
            ):
                raise ValueError("Invalid captured source digest or character count")
        elif (
            row.get("source_type") == "hiring"
            or row.get("collection_method") == "public_hiring_collection"
        ):
            if characters != 0:
                raise ValueError("Metadata-only source cannot contain captured text")
            continue
        if url in captured:
            raise ValueError("Ambiguous captured source URL; recollect evidence with primr prep")
        captured[url] = row

    headers = list(re.finditer(r"^={60}\nURL: (?P<url>[^\n]+)\n={60}\n", text, re.MULTILINE))
    framed: dict[str, str] = {}
    for position, header in enumerate(headers):
        url = header.group("url").strip()
        if url in framed or url not in captured:
            raise ValueError("Ambiguous prep source framing; recollect evidence with primr prep")
        end = headers[position + 1].start() if position + 1 < len(headers) else len(text)
        framed[url] = text[header.end() : end].strip()
    if set(framed) != set(captured):
        raise ValueError(
            "Missing or ambiguous captured source frames; recollect evidence with primr prep"
        )

    sources: list[EvidenceSource] = []
    for url, row in captured.items():
        body = framed[url]
        digest = row.get("captured_text_sha256")
        if digest is not None:
            valid = (
                len(body) == row["captured_characters"]
                and hashlib.sha256(body.encode("utf-8")).hexdigest() == digest
            )
        else:
            # Legacy writers counted raw text but serialized content.strip().
            # A smaller count is valid; complete unique framing prevents a body
            # delimiter from silently truncating or reassigning that text.
            valid = len(body) <= row["characters"]
        if not valid:
            raise ValueError(
                "Captured source content binding failed; recollect evidence with primr prep"
            )
        if body:
            sources.append(EvidenceSource(row["source_id"], url, body))
    return tuple(sources)


def parse_prepared_scraped_content_files(path: Path) -> dict[str, str]:
    """Keep copied prep input in local-draft evaluation on the same strict seam."""
    root = path.parent
    text = _read_verified(root, path.name, MAX_SCRAPED_BYTES).decode("utf-8")
    index = _object(_read_verified(root, "source_index.json", MAX_METADATA_BYTES))
    return {source.url: source.text for source in _bind_prepared_sources(index, text)}


def load_prepared_evidence(bundle: str | Path) -> PreparedEvidence:
    """Bind required source bytes to the prep manifest without following links."""
    root = Path(bundle).expanduser().absolute()
    manifest_bytes = _read_verified(root, "prep_manifest.json", MAX_METADATA_BYTES)
    manifest = _object(manifest_bytes)
    if (
        manifest.get("schema") != "primr.host-evidence-bundle"
        or manifest.get("version") != "1.0"
        or manifest.get("status") not in {"completed", "partial"}
    ):
        raise ValueError("Expected a supported, published Primr prep bundle")
    company = manifest.get("company_name")
    if (
        not isinstance(company, str)
        or not company.strip()
        or len(company) > 200
        or any(ord(char) < 32 for char in company)
    ):
        raise ValueError("Prep bundle must have a bounded company name")
    inventory = manifest.get("artifacts")
    if not isinstance(inventory, list):
        raise ValueError("Prep manifest has no artifact inventory")
    content: dict[str, bytes] = {}
    for name, limit in (
        ("source_index.json", MAX_METADATA_BYTES),
        ("scraped_content.txt", MAX_SCRAPED_BYTES),
    ):
        records = [row for row in inventory if isinstance(row, dict) and row.get("path") == name]
        if len(records) != 1:
            raise ValueError(f"Prep manifest must identify exactly one {name}")
        data = _read_verified(root, name, limit)
        if (
            records[0].get("size_bytes") != len(data)
            or records[0].get("sha256") != hashlib.sha256(data).hexdigest()
        ):
            raise ValueError(f"Prep manifest hash or size mismatch for {name}")
        content[name] = data
    index = _object(content["source_index.json"])
    scraped_text = content["scraped_content.txt"].decode("utf-8")
    sources = _bind_prepared_sources(index, scraped_text)
    if not sources:
        raise ValueError("No indexed source has captured text; collect evidence before drafting")
    quality = manifest.get("quality", {})
    limitations = quality.get("limitations", []) if isinstance(quality, dict) else []
    return PreparedEvidence(
        root=root.resolve(),
        company=company.strip(),
        status=manifest["status"],
        limitations=tuple(str(value)[:500] for value in limitations[:20])
        if isinstance(limitations, list)
        else (),
        sources=sources,
        indexed_sources=len(index["sources"]),
        scraped_content=scraped_text,
        source_index=content["source_index.json"].decode("utf-8"),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )
