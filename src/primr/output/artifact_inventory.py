"""Bounded, content-free inventory of Primr output artifacts."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_DELIVERABLE_SUFFIXES = frozenset({".md", ".txt", ".docx", ".pdf"})
_NON_ARTIFACT_NAMES = frozenset({"readme.md", "changelog.md", "license.md", "license.txt"})
_REPORT_ARTIFACT_TYPES = frozenset({"report_markdown", "report_text", "report_docx", "report_pdf"})
_DIAGNOSTIC_ARTIFACT_TYPES = frozenset(
    {"calibration_sidecar", "qa_summary", "verification_summary"}
)
_PRIMARY_REPORT_MARKERS = ("strategic_overview", "company_overview")
_ADDITIONAL_STRATEGY_MODULE_MARKERS = ("ai_first_transformation", "skills_ideation")


def classify_artifact(path: Path) -> str:
    """Classify an artifact from its exact name and suffix."""
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name in _NON_ARTIFACT_NAMES:
        return "artifact"
    if name.endswith(".calibration.json"):
        return "calibration_sidecar"
    if name == "run_manifest.json" or (name.startswith("run_manifest_") and name.endswith(".json")):
        return "run_manifest"
    if name.endswith("_run_state.json"):
        return "run_state"
    if suffix == ".jsonl" and "scrape_trace" in str(path.parent).lower():
        return "scrape_trace"
    if name.endswith(("_qa.json", "_qa_report.json")) or (
        suffix == ".txt" and "_qa_report_" in name
    ):
        return "qa_summary"
    if name == "verification.json" or name.endswith(("_verify.json", "_verification.json")):
        return "verification_summary"
    return {
        ".md": "report_markdown",
        ".txt": "report_text",
        ".docx": "report_docx",
        ".pdf": "report_pdf",
        ".json": "json_artifact",
    }.get(suffix, "artifact")


def infer_artifact_role(path: Path, artifact_type: str | None = None) -> str:
    """Infer a content-free downstream role from a filename and artifact type."""
    resolved_type = artifact_type or classify_artifact(path)
    stem = path.stem.lower()
    if resolved_type in _REPORT_ARTIFACT_TYPES:
        if any(marker in stem for marker in _PRIMARY_REPORT_MARKERS):
            return "primary_report"
        padded_stem = f"_{stem}_"
        if "_strategy_" in padded_stem or any(
            marker in stem for marker in _ADDITIONAL_STRATEGY_MODULE_MARKERS
        ):
            return "strategy_module"
        if "skills_pack" in stem:
            return "skill_pack"
        return "report"
    if resolved_type in _DIAGNOSTIC_ARTIFACT_TYPES:
        return "diagnostic"
    if resolved_type in {"run_manifest", "run_state", "scrape_trace"}:
        return "run_metadata"
    return "supporting_artifact"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


@dataclass(frozen=True)
class ArtifactRecord:
    """Metadata for one explicit or discovered artifact."""

    path: Path
    artifact_type: str
    exists: bool
    size_bytes: int | None
    modified_at: str | None
    content_hash: str | None
    source: str

    @property
    def artifact_role(self) -> str:
        """Return the semantic role used by downstream artifact consumers."""
        return infer_artifact_role(self.path, self.artifact_type)

    @classmethod
    def inspect(cls, path: Path, *, source: str, include_hash: bool = False) -> ArtifactRecord:
        exists = path.is_file()
        if not exists:
            return cls(path, classify_artifact(path), False, None, None, None, source)
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        return cls(
            path,
            classify_artifact(path),
            True,
            stat.st_size,
            modified,
            _hash_file(path) if include_hash else None,
            source,
        )

    def as_dict(self, *, index: int | None = None) -> dict[str, object]:
        data: dict[str, object] = {
            "artifact_type": self.artifact_type,
            "artifact_role": self.artifact_role,
            "file_name": self.path.name,
            "file_path": str(self.path),
            "exists": self.exists,
            "source": self.source,
        }
        if index is not None:
            data["index"] = index
        if self.exists:
            data["size_bytes"] = self.size_bytes
            data["modified_at"] = self.modified_at
            if self.content_hash is not None:
                data["content_hash"] = self.content_hash
        return data


@dataclass(frozen=True)
class ExplicitInventoryResult:
    """Bounded explicit-path inventory plus truthful truncation state."""

    records: list[ArtifactRecord]
    truncated: bool


def inventory_explicit_result(
    paths: Iterable[str | os.PathLike[str]],
    *,
    expand_adjacent: bool = False,
    include_hash: bool = False,
    max_paths: int = 256,
) -> ExplicitInventoryResult:
    """Inventory explicit paths, with optional exact same-run sibling expansion."""
    explicit_paths: list[Path] = []
    records: list[ArtifactRecord] = []
    seen: set[Path] = set()
    truncated = False

    def add(path: Path, source: str) -> None:
        normalized = path.resolve(strict=False)
        if normalized in seen or len(records) >= max_paths:
            return
        seen.add(normalized)
        records.append(ArtifactRecord.inspect(path, source=source, include_hash=include_hash))

    for index, path in enumerate(paths):
        if index >= max_paths:
            truncated = True
            break
        explicit = Path(path)
        explicit_paths.append(explicit)
        add(explicit, "explicit")
    if expand_adjacent:
        for path in explicit_paths:
            for suffix in _DELIVERABLE_SUFFIXES:
                sibling = path.with_suffix(suffix)
                if sibling.is_file():
                    if len(records) >= max_paths:
                        truncated = True
                        break
                    add(sibling, "adjacent")
            if truncated:
                break
    return ExplicitInventoryResult(records=records, truncated=truncated)


def inventory_explicit(
    paths: Iterable[str | os.PathLike[str]],
    *,
    expand_adjacent: bool = False,
    include_hash: bool = False,
    max_paths: int = 256,
) -> list[ArtifactRecord]:
    """Compatibility wrapper returning records from the bounded inventory."""
    return inventory_explicit_result(
        paths,
        expand_adjacent=expand_adjacent,
        include_hash=include_hash,
        max_paths=max_paths,
    ).records


def scan_artifact_roots(
    roots: Iterable[str | os.PathLike[str]],
    *,
    max_paths: int = 256,
    max_depth: int = 4,
    max_entries: int = 4096,
    allowed_types: frozenset[str] | None = None,
) -> dict[str, object]:
    """Scan known roots without following directory symlinks or reading bodies."""
    records: list[ArtifactRecord] = []
    errors: list[str] = []
    truncated = False
    visited_entries = 0
    seen_files: set[Path] = set()
    stack = [(Path(root), 0) for root in roots]
    while stack and visited_entries < max_entries:
        directory, depth = stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if visited_entries >= max_entries:
                        truncated = True
                        break
                    visited_entries += 1
                    if entry.is_dir(follow_symlinks=False) and depth < max_depth:
                        stack.append((Path(entry.path), depth + 1))
                    elif entry.is_file(follow_symlinks=False):
                        path = Path(entry.path)
                        artifact_type = classify_artifact(path)
                        if artifact_type == "artifact" or (
                            artifact_type == "json_artifact" and path.name != "run_manifest.json"
                        ):
                            continue
                        if allowed_types is not None and artifact_type not in allowed_types:
                            continue
                        normalized = path.resolve(strict=False)
                        if normalized in seen_files:
                            continue
                        seen_files.add(normalized)
                        records.append(ArtifactRecord.inspect(path, source="discovered"))
        except OSError as exc:
            errors.append(f"{directory}: {exc}")
    records.sort(key=lambda row: row.modified_at or "", reverse=True)
    matched_count = len(records)
    if matched_count > max_paths:
        truncated = True
        records = records[:max_paths]
    return {
        "artifacts": records,
        "errors": errors,
        "truncated": truncated or bool(stack),
        "visited_entries": visited_entries,
        "matched_count": matched_count,
    }
