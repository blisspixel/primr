"""Every relative link in the project's Markdown must resolve.

The index test (`test_docs_index.py`) guards the doc map specifically; this one
guards *all* Markdown in the repo -- READMEs, guides, skills, design notes,
example docs -- so a renamed or deleted file can never leave a dead link behind
in prose. External links (http/https/mailto) and pure anchors are out of scope;
only on-disk relative targets are checked, which needs no network and is safe
under a shallow CI checkout.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Build snapshots, vendored trees, and generated output are not source docs.
_EXCLUDED_PARTS = {
    ".venv",
    "node_modules",
    ".agent",
    ".git",
    "site",
    "htmlcov",
    "__pycache__",
}

_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _markdown_files() -> list[Path]:
    return [
        path for path in REPO_ROOT.rglob("*.md") if not _EXCLUDED_PARTS.intersection(path.parts)
    ]


def test_all_relative_markdown_links_resolve() -> None:
    broken: list[str] = []
    for md in _markdown_files():
        text = md.read_text(encoding="utf-8", errors="replace")
        for match in _LINK.finditer(text):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:", "#", "tel:")):
                continue
            path_part = target.split("#", 1)[0].strip()
            if not path_part:
                continue
            if not (md.parent / path_part).resolve().exists():
                broken.append(f"{md.relative_to(REPO_ROOT)} -> {target}")
    assert not broken, "Broken relative Markdown links:\n" + "\n".join(broken)
