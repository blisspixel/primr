"""Enforced write allowlist for agentic artifact-modification stages.

``primr improve --improve-agentic`` (and any future agentic pipeline stage
that modifies artifacts: expert perspective passes, strategy enrichment,
cross-validation regeneration) must only ever write the target output file.
Before this guard that was a trust-based policy — "the LLM should only edit
the report". This module turns it into an architectural constraint: all
artifact writes in agentic stages flow through :class:`ArtifactWriteGuard`,
which checks the resolved destination against an explicit allowlist before
any byte hits disk.

Run state (``_run_state.json``), raw scrapes (``_raw_scrapes/``), and other
pipeline-internal files are deny-listed unconditionally — they are rejected
even if a caller mistakenly adds them to the allowlist.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

from primr.utils.logging_config import get_logger

logger = get_logger("utils.write_guard")

# Pipeline-internal files an agentic stage must never touch, allowlist or not.
DENIED_NAMES = frozenset({"_run_state.json", "usage_history.json"})
DENIED_DIR_NAMES = frozenset({"_raw_scrapes", "_hiring", "_diagnostics"})


class WriteGuardError(PermissionError):
    """An agentic stage attempted to write outside its allowlist."""


class ArtifactWriteGuard:
    """Write gate for a single agentic stage.

    The guard is constructed with the stage's target output file. The target
    and its ``*_improved`` sibling are allowlisted; everything else is
    rejected. ``extra_allowed`` admits additional explicit destinations
    (e.g. a sidecar diagnostics report) when a stage legitimately needs them.
    """

    def __init__(self, target_path: str | Path, extra_allowed: Iterable[str | Path] = ()):
        target = Path(target_path).resolve()
        improved_variant = target.with_name(f"{target.stem}_improved{target.suffix}")
        self._allowed: set[Path] = {target, improved_variant}
        for extra in extra_allowed:
            self._allowed.add(Path(extra).resolve())
        self.target_path = target

    def check(self, path: str | Path) -> Path:
        """Validate a destination; return its resolved Path or raise.

        Resolution happens before checking, so ``..`` traversal and symlink
        tricks are judged by where the write actually lands.
        """
        resolved = Path(path).resolve()

        if resolved.name in DENIED_NAMES:
            raise WriteGuardError(
                f"Agentic stage may not write pipeline state file: {resolved}"
            )
        if any(part in DENIED_DIR_NAMES for part in resolved.parts):
            raise WriteGuardError(
                f"Agentic stage may not write into a pipeline-managed directory: {resolved}"
            )
        if resolved not in self._allowed:
            allowed = ", ".join(str(p) for p in sorted(self._allowed))
            raise WriteGuardError(
                f"Agentic stage attempted to write outside its allowlist: {resolved} "
                f"(allowed: {allowed})"
            )
        return resolved

    def write_text(self, path: str | Path, content: str, encoding: str = "utf-8") -> Path:
        """Checked replacement for ``Path.write_text``."""
        resolved = self.check(path)
        resolved.write_text(content, encoding=encoding)
        logger.debug("Write guard allowed write: %s (%d chars)", resolved, len(content))
        return resolved
