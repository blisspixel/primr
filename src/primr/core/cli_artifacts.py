"""CLI rendering for bounded artifact inventory."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from primr.output.artifact_inventory import ArtifactRecord, scan_artifact_roots


def _group(record: ArtifactRecord) -> str:
    if record.artifact_type in {"run_state", "run_manifest"}:
        return "Run state"
    if record.artifact_type == "scrape_trace":
        return "Trace"
    return "Deliverables"


def list_recent_outputs(
    output_dir: str | Path,
    *,
    working_dir: str | Path | None = None,
    logs_dir: str | Path | None = None,
    json_output: bool = False,
) -> int:
    """List recent deliverables and diagnostic artifacts from one output root."""
    root = Path(output_dir)
    scans = [scan_artifact_roots([root])]
    roots = [str(root)]
    if working_dir is not None:
        roots.append(str(working_dir))
        scans.append(
            scan_artifact_roots(
                [working_dir], max_paths=5, max_depth=3, allowed_types=frozenset({"run_state"})
            )
        )
    if logs_dir is not None:
        roots.append(str(logs_dir))
        scans.append(
            scan_artifact_roots(
                [logs_dir],
                max_paths=5,
                max_depth=1,
                allowed_types=frozenset({"scrape_trace"}),
            )
        )
    records: list[ArtifactRecord] = []
    seen: set[Path] = set()
    for scan in scans:
        for record in cast("list[ArtifactRecord]", scan["artifacts"]):
            normalized = record.path.resolve(strict=False)
            if normalized not in seen:
                seen.add(normalized)
                records.append(record)
    records.sort(key=lambda record: record.modified_at or "", reverse=True)
    errors = [error for scan in scans for error in cast("list[str]", scan["errors"])]
    if json_output:
        from primr.core.cli_output import emit_json

        emit_json(
            {
                "schema": "primr.artifact-inventory",
                "schema_version": "1.0",
                "command": "list-recent",
                "roots": roots,
                "artifact_count": len(records),
                "truncated": any(bool(scan["truncated"]) for scan in scans),
                "errors": errors,
                "scan_stats": [
                    {
                        "root": scan_root,
                        "visited_entries": scan["visited_entries"],
                        "matched_count": scan["matched_count"],
                    }
                    for scan_root, scan in zip(roots, scans, strict=True)
                ],
                "artifacts": [record.as_dict() for record in records],
            }
        )
        return 1 if errors and not records else 0
    if not records:
        if errors:
            print("Unable to scan artifact roots:")
            for error in errors:
                print(f"  {error}")
            return 1
        print("No recent outputs found.")
        return 0

    print("\nRECENT RESEARCH OUTPUTS")
    print("-" * 60)
    for error in errors:
        print(f"Scan warning: {error}")
    limits = {"Deliverables": 20, "Run state": 5, "Trace": 5}
    for group in ("Deliverables", "Run state", "Trace"):
        rows = [record for record in records if _group(record) == group]
        if not rows:
            continue
        print(f"{group}:")
        for index, record in enumerate(rows[: limits[group]], 1):
            size_kb = (record.size_bytes or 0) / 1024
            modified = (record.modified_at or "")[:16].replace("T", " ")
            print(f"{index:2}. {record.path.name}")
            print(f"    {modified} | {size_kb:.1f} KB")
        if len(rows) > limits[group]:
            print(f"... and {len(rows) - limits[group]} more files")
    print("-" * 60)
    return 0
