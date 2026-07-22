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
