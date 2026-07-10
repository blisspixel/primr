"""Architectural fitness functions: enforce the anti-slop rules in CLAUDE.md.

These are deterministic, zero-network gates that fail CI when the codebase
drifts away from its stated conventions. They are intentionally cheap and
boring: their job is to make "slop" fail a gate instead of a review comment.

Two rules enforced here:

1. **No new giant files / monsters can't grow.** A rise-only per-file line
   ceiling. New files must stay under ``NEW_FILE_MAX_LINES``; the existing
   large files are pinned at their current size in ``FILE_LINE_CEILINGS`` and
   may not exceed it. The fix for a failure is to *split the file*, not to bump
   the ceiling; ceilings only ever ratchet **down** (and a deliberate
   reduction when a file shrinks is welcome).

2. **One JSON library.** stdlib ``json`` only; no orjson/ujson/simplejson
   creeping in as a "faster" second way.

See CLAUDE.md ("Use the one seam") and ROADMAP → Engineering Standards.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "primr"

# New files may not exceed this. Existing offenders are pinned below.
NEW_FILE_MAX_LINES = 1000

# Rise-only ceilings for files that already exceed NEW_FILE_MAX_LINES. Pinned
# at their measured size (via str.splitlines) at the time this gate landed.
# A file here that grows past its ceiling fails the build. Split it instead.
# When a file is split and shrinks, lower its ceiling (or drop it once under
# NEW_FILE_MAX_LINES). Never raise a ceiling to make a growing file pass.
FILE_LINE_CEILINGS: dict[str, int] = {
    "core/research_agent.py": 4414,
    "core/cli.py": 3389,
    "ai/deep_research.py": 3890,
    "data/scraping/browsers.py": 1835,
    "data/hiring_signals.py": 1602,
    "core/model_eval.py": 1832,
    "data/scrape.py": 1836,
    "mcp_server/tools.py": 1596,
    "data/fallback_sources.py": 1084,
    "agentic/hooks.py": 1022,
    "core/research_orchestrator.py": 1087,
    "data/scraping/orchestrator.py": 1064,
    "data/scraping/structured_content.py": 1067,
}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _src_py_files() -> list[Path]:
    return [p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_file_exceeds_its_line_ceiling():
    """No source file grows past its ceiling; no new file is born a monster."""
    violations: list[str] = []
    for path in _src_py_files():
        rel = path.relative_to(SRC_ROOT).as_posix()
        ceiling = FILE_LINE_CEILINGS.get(rel, NEW_FILE_MAX_LINES)
        lines = _line_count(path)
        if lines > ceiling:
            if rel in FILE_LINE_CEILINGS:
                violations.append(
                    f"{rel}: {lines} lines exceeds its pinned ceiling {ceiling}. "
                    f"Split the file (do NOT raise the ceiling)."
                )
            else:
                violations.append(
                    f"{rel}: {lines} lines exceeds the {NEW_FILE_MAX_LINES}-line cap "
                    f"for files. Split it before merging."
                )
    assert not violations, "File-size ratchet failed:\n" + "\n".join(violations)


def test_ceiling_list_has_no_stale_entries():
    """Keep the ratchet honest: a pinned file that no longer exists, or has
    dropped below the new-file cap, should be removed from the dict (and a
    shrunk file's ceiling lowered) so the ratchet reflects reality."""
    stale: list[str] = []
    for rel, ceiling in FILE_LINE_CEILINGS.items():
        path = SRC_ROOT / rel
        if not path.exists():
            stale.append(f"{rel}: pinned but no longer exists; remove it.")
            continue
        lines = _line_count(path)
        if lines <= NEW_FILE_MAX_LINES:
            stale.append(
                f"{rel}: now {lines} lines (<= {NEW_FILE_MAX_LINES}); drop it from the dict."
            )
        elif lines < ceiling:
            stale.append(
                f"{rel}: now {lines} lines, ceiling is {ceiling}; lower the ceiling to {lines}."
            )
    assert not stale, "Stale ratchet entries (tighten them):\n" + "\n".join(stale)


_FORBIDDEN_JSON_IMPORT = re.compile(
    r"^\s*(?:import\s+(?:orjson|ujson|simplejson)\b|from\s+(?:orjson|ujson|simplejson)\b)",
    re.MULTILINE,
)


def test_single_json_library():
    """stdlib json only; no second JSON library sneaking in as a 'faster' way."""
    offenders: list[str] = []
    for path in _src_py_files():
        if _FORBIDDEN_JSON_IMPORT.search(path.read_text(encoding="utf-8")):
            offenders.append(path.relative_to(SRC_ROOT).as_posix())
    assert not offenders, (
        "Use stdlib json only (see CLAUDE.md). Found orjson/ujson/simplejson in:\n"
        + "\n".join(offenders)
    )


@pytest.mark.parametrize("doc", ["CLAUDE.md", "AGENTS.md"])
def test_agent_contracts_exist(doc):
    """Both the dev contract (CLAUDE.md) and the operate guide (AGENTS.md) ship."""
    assert (SRC_ROOT.parent.parent / doc).is_file(), f"{doc} is missing from the repo root"
