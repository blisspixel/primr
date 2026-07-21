"""The ``primr render`` subcommand: convert a Markdown report to DOCX (+ TXT).

Primr's provider-backed pipeline renders DOCX internally, but the Primr Zero /
host-assisted path writes Markdown directly and had no way to reach that
converter — so host-written dossiers stayed Markdown-only. This verb exposes the
existing ``markdown_to_docx`` renderer as a standalone, **zero-cost** step (no
model calls, no network), so any Markdown report — however it was produced —
gets the same ``.docx``/``.txt`` artifacts as a paid run.

Dispatched from ``primr.core.cli`` like the other noun/verb subcommands.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from primr.utils.console import console


def is_render_command(args: list[str] | None) -> bool:
    """Return True for a ``primr render ...`` invocation."""
    argv = args if args is not None else sys.argv[1:]
    return len(argv) >= 1 and argv[0] == "render"


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="primr render",
        description="Convert a Markdown report to DOCX (and TXT). Zero cost: no model calls.",
    )
    parser.add_argument("report", help="Path to the Markdown (.md) report to render.")
    parser.add_argument("--title", default=None, help="Optional document title override.")
    parser.add_argument("--subtitle", default=None, help="Optional document subtitle.")
    parser.add_argument("--no-txt", action="store_true", help="Skip the plain-text (.txt) sibling.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Write artifacts here instead of beside the source file.",
    )
    return parser


def run_render(args: list[str] | None) -> int:
    """Render a Markdown report to DOCX (+ TXT). Returns a process exit code."""
    argv = args if args is not None else sys.argv[1:]
    parsed = _create_parser().parse_args(argv[1:])

    source = Path(parsed.report)
    if not source.exists():
        console.error(f"Report not found: {source}")
        return 1
    if source.suffix.lower() not in {".md", ".markdown", ".txt"}:
        console.warn(f"Rendering a non-Markdown file ({source.suffix}); proceeding anyway.")

    try:
        markdown_text = source.read_text(encoding="utf-8")
    except Exception as exc:
        console.error(f"Could not read {source}: {exc}")
        return 1
    if not markdown_text.strip():
        console.error(f"Report is empty: {source}")
        return 1

    dest_dir = Path(parsed.output_dir) if parsed.output_dir else source.parent
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        console.error(f"Output directory not writable: {dest_dir} ({exc})")
        return 1

    stem = source.stem
    title = parsed.title or stem.replace("_", " ")

    docx_path = dest_dir / f"{stem}.docx"
    try:
        from primr.output.markdown_converter import markdown_to_docx

        markdown_to_docx(
            markdown_text=markdown_text,
            output_path=docx_path,
            title=title,
            subtitle=parsed.subtitle,
        )
        console.ok(f"DOCX: {docx_path}")
    except Exception as exc:
        console.error(f"DOCX conversion failed: {exc}")
        return 1

    if not parsed.no_txt:
        txt_path = dest_dir / f"{stem}.txt"
        try:
            txt_path.write_text(markdown_text, encoding="utf-8")
            console.ok(f"TXT:  {txt_path}")
        except Exception as exc:
            console.warn(f"TXT sibling skipped: {exc}")

    console.info("Rendered with no model calls or network requests ($0.00).")
    return 0
