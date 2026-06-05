"""Guard against real company / third-party product names leaking into code.

The no-real-company-data rule (see docs/CONTRIBUTING.md) says fixtures,
comments, prompts, and tests must use generic placeholders (Acme Corp,
example.com), never real research-subject companies or their branded
products. A branded product once slipped into test fixtures and a prompt
example and shipped before being caught - this test makes that class of leak
fail CI instead.

Detection: a denylist of known bare company/brand tokens (including the
"+"-suffixed branded product form that previously leaked). The tokens are
stored base64-ENCODED so the plaintext names do not themselves appear in the
repo (which would violate the very rule this guard enforces); they are decoded
only at runtime for matching. A purely structural "Word+" heuristic was tried
and dropped - it false-positived on legitimate tokens like "Ctrl+", model
tier names, etc.

Scope: `src/primr/` (code + prompts) and `tests/`. Docs are intentionally NOT
scanned - they legitimately reference allowed vendor/tech product names and
are governed by review. Generic industry terms (SAM, Azure, Copilot, ...) are
allowed; only distinctive brand/company tokens are blocked.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Known bare company / brand tokens, base64-encoded so the plaintext does not
# appear in the repo. Decoded at runtime. Add new entries (encode a lowercase
# token) as real companies are researched.
_ENCODED_DENYLIST = [
    "c29mdGNob2ljZQ==",
    "c2FtLXBsdXM=",
    "c2FtKw==",
    "c2VtcHJh",
    "bW9sZXg=",
    "d2lubWFnaWM=",
    "bGV4aXRhcw==",
    "YmFsY2Fu",
    "cmVhbCBtYXR0ZXJz",
    "cmVhbG1hdHRlcnM=",
    "bmludGVuZG8=",
    "cGF0YWdvbmlh",
    "YmFzZWNhbXA=",
    "Z2xlbmRpbXBsZXg=",
    "c2thZ2l0IHZhbGxleQ==",
    "cmlzZXdlbGw=",
    "d2VzdGdhdGU=",
]
_DECODED = [base64.b64decode(t).decode("utf-8") for t in _ENCODED_DENYLIST]
_NAME_RE = re.compile("|".join(re.escape(t) for t in _DECODED), re.IGNORECASE)

_SCAN_DIRS = ["src/primr", "tests"]
_SCAN_SUFFIXES = {".py", ".yaml", ".yml"}
_SELF = Path(__file__).resolve()


def _iter_files():
    for rel in _SCAN_DIRS:
        for path in (REPO_ROOT / rel).rglob("*"):
            if path.suffix not in _SCAN_SUFFIXES:
                continue
            if "__pycache__" in path.parts:
                continue
            if path.resolve() == _SELF:
                continue
            yield path


def test_no_real_company_or_brand_names_in_code():
    """Fail if a denylisted name appears in code/prompts/tests."""
    hits: list[str] = []
    for path in _iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _NAME_RE.search(line):
                rel = path.relative_to(REPO_ROOT).as_posix()
                hits.append(f"{rel}:{lineno}: denylisted name")
    assert not hits, (
        "Real company / brand names found in code (use generic placeholders "
        "like 'Acme Corp' / 'the SAM platform'):\n  " + "\n  ".join(hits)
    )
