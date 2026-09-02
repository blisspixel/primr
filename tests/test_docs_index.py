"""The docs index (`docs/README.md`) must stay in lockstep with the doc tree.

Two failure modes rot a documentation map: a new doc lands but never gets
listed (readers cannot find it), or an entry outlives the file it points to
(a dead link). Both are caught here without needing git history, so the check
is safe under a shallow CI checkout.

The `Updated` column dates in the index are informational (git last-commit
dates, refreshed on review) and are deliberately not asserted here -- pinning
exact dates would be brittle across rebases and squash merges. What must never
drift is *coverage* and *link validity*, which is what this test guards.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
INDEX = DOCS_DIR / "README.md"

_LINK = re.compile(r"\]\(([^)]+)\)")


def _index_link_targets() -> list[str]:
    return _LINK.findall(INDEX.read_text(encoding="utf-8"))


def test_every_top_level_doc_is_listed_in_the_index() -> None:
    targets = {Path(t).name for t in _index_link_targets()}
    missing = sorted(
        path.name
        for path in DOCS_DIR.glob("*.md")
        if path.name != "README.md" and path.name not in targets
    )
    assert not missing, f"docs/README.md must link every doc under docs/. Missing: {missing}"


def test_every_relative_index_link_resolves() -> None:
    broken: list[str] = []
    for target in _index_link_targets():
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        resolved = (DOCS_DIR / target.split("#", 1)[0]).resolve()
        if not resolved.exists():
            broken.append(target)
    assert not broken, f"docs/README.md has links that do not resolve: {broken}"


def test_next_steps_has_one_versioned_executable_card() -> None:
    brief = (DOCS_DIR / "NEXT_STEPS.md").read_text(encoding="utf-8")
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    released = pyproject["project"]["version"]

    baseline = re.search(r"^Released baseline: \*\*v(?P<version>\d+\.\d+\.\d+)\*\*$", brief, re.M)
    candidate = re.search(
        r"^Next implementation candidate: \*\*v(?P<version>\d+\.\d+\.\d+)\*\*$",
        brief,
        re.M,
    )

    assert brief.count("## Current executable card") == 1
    assert baseline is not None
    assert baseline.group("version") == released
    assert candidate is not None
    assert tuple(map(int, candidate.group("version").split("."))) > tuple(
        map(int, released.split("."))
    )


def test_current_planning_avoids_delivery_date_and_effort_promises() -> None:
    brief = (DOCS_DIR / "NEXT_STEPS.md").read_text(encoding="utf-8")
    prohibited = (
        r"\bwill take\b",
        r"\bexpected to take\b",
        r"\bship by\b",
        r"\bETA\b",
        r"\bnext (?:week|month|quarter)\b",
        r"\b\d+\s+(?:business\s+)?(?:day|week|month)s?\b",
    )

    matches = [pattern for pattern in prohibited if re.search(pattern, brief, re.I)]
    assert not matches, f"NEXT_STEPS.md contains delivery-date or effort promises: {matches}"


def test_roadmap_delegates_the_current_queue_to_next_steps() -> None:
    roadmap = (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "### Version ladder (logical order, no schedules)" in roadmap
    assert "**Next implementation candidate:** v1.39.14" in roadmap
    assert "The canonical executable queue lives in" in roadmap
    assert "[`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md)" in roadmap
