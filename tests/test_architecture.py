"""Architectural fitness functions: enforce the anti-slop rules in CLAUDE.md.

These are deterministic, zero-network gates that fail CI when the codebase
drifts away from its stated conventions. They are intentionally cheap and
boring: their job is to make "slop" fail a gate instead of a review comment.

Six rules enforced here:

1. **No new giant files / monsters can't grow.** A rise-only per-file line
   ceiling. New files must stay under ``NEW_FILE_MAX_LINES``; the existing
   large files are pinned at their current size in ``FILE_LINE_CEILINGS`` and
   may not exceed it. The fix for a failure is to *split the file*, not to bump
   the ceiling; ceilings only ever ratchet **down** (and a deliberate
   reduction when a file shrinks is welcome). A split must still create a
   coherent boundary; line count alone is not a design reason.

2. **One JSON library.** stdlib ``json`` only; no orjson/ujson/simplejson
   creeping in as a "faster" second way.

3. **Package-map coverage.** Every importable top-level package appears in the
   concern-level map in ``docs/ARCHITECTURE.md``.

4. **Acyclic MCP controller boundary.** Only composition roots may import the
   concrete MCP server module. Other consumers use the structural context.

5. **No accidental micro-modules.** Sub-40-line modules require an explicit
   architectural rationale, and empty non-package modules are forbidden.

6. **Import-cycle ratchet.** Existing broad cycle components are pinned and
   may only shrink. New or growing first-party import cycles fail CI.

See CLAUDE.md ("Use the one seam") and ROADMAP → Engineering Standards.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "primr"
ARCHITECTURE_DOC = SRC_ROOT.parent.parent / "docs" / "ARCHITECTURE.md"

# New files may not exceed this. Existing offenders are pinned below.
NEW_FILE_MAX_LINES = 1000

# Rise-only ceilings for files that already exceed NEW_FILE_MAX_LINES. Pinned
# at their measured size (via str.splitlines) at the time this gate landed.
# A file here that grows past its ceiling fails the build. Split it instead.
# When a file is split and shrinks, lower its ceiling (or drop it once under
# NEW_FILE_MAX_LINES). Never raise a ceiling to make a growing file pass.
FILE_LINE_CEILINGS: dict[str, int] = {
    # research_agent.py and cli.py remain below their committed-main baselines.
    # These ceilings track the current measured sizes and may only shrink.
    "core/research_agent.py": 4262,
    "core/cli.py": 2449,
    "ai/deep_research.py": 3812,
    "data/scraping/browsers.py": 1835,
    "data/hiring_signals.py": 1577,
    "core/model_eval.py": 1828,
    "data/scrape.py": 1828,
    "data/fallback_sources.py": 1084,
    # cli_batch_runtime.py received extracted batch-runtime code during the
    # cli.py decomposition; pinned here now that it exceeds the new-file cap.
    "core/cli_batch_runtime.py": 1043,
    "agentic/hooks.py": 1010,
    "data/scraping/orchestrator.py": 1064,
    "data/scraping/structured_content.py": 1067,
}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _src_py_files() -> list[Path]:
    return [p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


MIN_MODULE_REVIEW_LINES = 40

# Small modules can be excellent boundaries. This ledger prevents file-count
# growth from becoming an unreviewed side effect of the maximum-size ratchet.
# Entries must state the boundary they own; a new tiny module fails until its
# reason is reviewed here. When an entry grows past the threshold, remove it.
INTENTIONAL_TINY_MODULES: dict[str, str] = {
    "__main__.py": "python -m primr composition shim",
    "cli_entry.py": "lightweight public CLI import boundary",
    "a2a/skill_ids.py": "wire-protocol skill identifiers",
    "a2a/status_events.py": "A2A status-event translation boundary",
    "ai/deep_research_polling.py": "pure polling schedule policy",
    "config/sections_config.py": "section configuration compatibility surface",
    "core/cli_prep.py": "legacy prep-command import compatibility surface",
    "core/cli_help.py": "backward-compatible CLI help import surface",
    "core/strategy_enrichment_contract.py": "strategy review and repair framing policy",
    "data/first_party_url.py": "first-party URL policy seam",
    "mcp_server/cloud_detect.py": "cloud-runtime adapter",
    "mcp_server/qa_operations.py": "shared QA operation boundary",
    "mcp_server/resource_summary_utils.py": "compact resource-summary policy",
    "mcp_server/server_context.py": "cross-transport structural context",
    "mcp_server/worker_environment.py": "least-privilege worker environment boundary",
    "primr_cli.py": "legacy console-entry compatibility shim",
    "qa/artifact_fingerprints.py": "artifact identity policy",
    "qa/calibration_judge_agreement.py": "judge-agreement calculation seam",
    "utils/timeutils.py": "shared UTC clock seam",
}


def test_tiny_modules_have_reviewed_boundaries():
    """Sub-40-line modules must own a reviewed boundary, not just moved lines."""
    current = {
        path.relative_to(SRC_ROOT).as_posix()
        for path in _src_py_files()
        if path.name != "__init__.py" and _line_count(path) < MIN_MODULE_REVIEW_LINES
    }
    documented = set(INTENTIONAL_TINY_MODULES)
    undocumented = sorted(current - documented)
    stale = sorted(documented - current)
    assert not undocumented, (
        "New tiny modules need a real "
        "policy, protocol, lifecycle, adapter, composition, or test boundary; "
        "do not add a rationale for line-count-only splits.\n"
        f"Undocumented: {undocumented}"
    )
    assert not stale, f"Remove tiny-module rationale entries that grew or disappeared: {stale}"


def test_no_empty_non_package_modules():
    """Empty source modules add a navigation hop without owning behavior."""
    empty = sorted(
        path.relative_to(SRC_ROOT).as_posix()
        for path in _src_py_files()
        if path.name != "__init__.py" and not path.read_text(encoding="utf-8").strip()
    )
    assert not empty, "Remove empty non-package modules:\n" + "\n".join(empty)


EXPECTED_IMPORT_CYCLES = {
    frozenset(
        {
            "primr",
            "primr.core.cli",
            "primr.core.cli_dispatch",
            "primr.core.cli_doctor",
            "primr.core.cli_update",
            "primr.core.deep_research_runner",
            "primr.core.fast_run_sections",
            "primr.core.fast_run_strategy",
            "primr.core.fast_run_trust",
            "primr.core.fast_run_validation",
            "primr.core.research_agent",
            "primr.core.research_orchestrator",
        }
    ),
    frozenset(
        {
            "primr.ai.llm",
            "primr.ai.routing",
            "primr.config.eval_profiles",
            "primr.core.model_eval",
            "primr.utils.cost_estimator",
        }
    ),
    frozenset(
        {
            "primr.data.fallback_sources",
            "primr.data.first_party_pdf",
            "primr.data.first_party_structured_data",
        }
    ),
}


def _module_name(path: Path) -> str:
    parts = path.relative_to(SRC_ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(("primr", *parts))


def _resolved_internal_imports(
    path: Path,
    tree: ast.AST,
    known_modules: set[str],
) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names if alias.name in known_modules)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        base = _resolved_import_from_module(path, node)
        if base in known_modules:
            targets.add(base)
        targets.update(
            f"{base}.{alias.name}"
            for alias in node.names
            if f"{base}.{alias.name}" in known_modules
        )
    return targets


def _strongly_connected_components(graph: dict[str, set[str]]) -> set[frozenset[str]]:
    index = 0
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: set[frozenset[str]] = set()

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph[node]:
            if target not in indexes:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[target])
        if lowlinks[node] != indexes[node]:
            return
        component: set[str] = set()
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.add(member)
            if member == node:
                break
        if len(component) > 1:
            components.add(frozenset(component))

    for node in sorted(graph):
        if node not in indexes:
            visit(node)
    return components


def test_first_party_import_cycles_match_burndown_baseline():
    """New or growing import-cycle components fail; existing ones may shrink."""
    files = _src_py_files()
    known_modules = {_module_name(path) for path in files}
    graph = {
        _module_name(path): _resolved_internal_imports(
            path,
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path)),
            known_modules,
        )
        for path in files
    }
    actual = _strongly_connected_components(graph)
    assert actual == EXPECTED_IMPORT_CYCLES, (
        "First-party import-cycle baseline changed. New or larger cycles must "
        "be removed. If a cycle shrank, tighten EXPECTED_IMPORT_CYCLES.\n"
        f"Expected: {sorted(map(sorted, EXPECTED_IMPORT_CYCLES))}\n"
        f"Actual: {sorted(map(sorted, actual))}"
    )


@pytest.mark.parametrize(
    "modules",
    [
        ("primr.ai.deep_research", "primr.ai.file_search_resources"),
        ("primr.ai.file_search_resources", "primr.ai.deep_research"),
        ("primr.config.models", "primr.config.settings"),
        ("primr.config.settings", "primr.config.models"),
        ("primr.config.config", "primr.utils.errors"),
        ("primr.utils.errors", "primr.config.config"),
        ("primr.utils", "primr.utils.security"),
        ("primr.utils.security", "primr.utils"),
        ("primr.core.cli_init", "primr.core.cli_doctor"),
        ("primr.core.cli_doctor", "primr.core.cli_init"),
        ("primr.core.cli_errors", "primr.core.cli_update"),
        ("primr.core.cli_update", "primr.core.cli_errors"),
        ("primr.core.section_regeneration", "primr.core.research_agent"),
        ("primr.core.research_agent", "primr.core.section_regeneration"),
        ("primr.core.cli_plan", "primr.core.research_agent"),
        ("primr.core.research_agent", "primr.core.cli_plan"),
        ("primr.core.fast_run_gaps", "primr.core.research_agent"),
        ("primr.core.research_agent", "primr.core.fast_run_gaps"),
        ("primr.core.fast_run_summary", "primr.core.research_agent"),
        ("primr.core.research_agent", "primr.core.fast_run_summary"),
        ("primr.core.fast_run_collection", "primr.core.research_agent"),
        ("primr.core.research_agent", "primr.core.fast_run_collection"),
        ("primr.core.fast_run_setup", "primr.core.research_agent"),
        ("primr.core.research_agent", "primr.core.fast_run_setup"),
        ("primr.core.refine", "primr.core.research_agent"),
        ("primr.core.research_agent", "primr.core.refine"),
    ],
)
def test_removed_cycle_pairs_import_cleanly_in_fresh_interpreters(modules):
    """Former cycle pairs remain order-independent without partial modules."""
    source_parent = str(SRC_ROOT.parent)
    expected_package = str((SRC_ROOT / "__init__.py").resolve())
    imports = "; ".join(f"import {module}" for module in modules)
    statement = (
        f"import sys; sys.path.insert(0, {source_parent!r}); import primr; "
        f"assert primr.__file__ == {expected_package!r}; {imports}"
    )
    subprocess.run(
        [sys.executable, "-B", "-c", statement],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


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


def test_architecture_package_map_covers_top_level_packages():
    """Every current top-level package is named in the architecture map."""
    text = ARCHITECTURE_DOC.read_text(encoding="utf-8")
    package_map = text.split("## Module Structure", 1)[1].split("## Error Handling Strategy", 1)[0]
    packages = sorted(
        path.name
        for path in SRC_ROOT.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    )

    missing = [package for package in packages if f"{package}/" not in package_map]
    assert not missing, "Packages missing from docs/ARCHITECTURE.md module map:\n" + "\n".join(
        missing
    )


def _resolved_import_from_module(path: Path, node: ast.ImportFrom) -> str:
    """Resolve an ``ImportFrom`` node within the ``primr`` package."""
    if node.level == 0:
        return node.module or ""

    rel = path.relative_to(SRC_ROOT)
    package_parts = ["primr", *rel.parts[:-1]]
    keep = max(0, len(package_parts) - (node.level - 1))
    module_parts = (node.module or "").split(".") if node.module else []
    return ".".join([*package_parts[:keep], *module_parts])


def _imports_concrete_mcp_server(path: Path, tree: ast.AST) -> bool:
    """Detect absolute and package-relative imports of the concrete server."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "primr.mcp_server.server" for alias in node.names
        ):
            return True
        if not isinstance(node, ast.ImportFrom):
            continue
        module = _resolved_import_from_module(path, node)
        if module == "primr.mcp_server.server":
            return True
        if module == "primr.mcp_server" and any(alias.name == "server" for alias in node.names):
            return True
    return False


def test_only_composition_roots_import_concrete_mcp_server():
    """Keep concrete server construction out of reusable modules and type edges."""
    allowed = {"a2a/cli.py", "mcp_server/cli.py"}
    offenders: list[str] = []
    for path in _src_py_files():
        rel = path.relative_to(SRC_ROOT).as_posix()
        if rel in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _imports_concrete_mcp_server(path, tree):
            offenders.append(rel)

    assert not offenders, (
        "Import MCPServerContext instead of the concrete server outside composition roots:\n"
        + "\n".join(offenders)
    )


@pytest.mark.parametrize(
    ("relative_path", "statement"),
    [
        ("a2a/example.py", "import primr.mcp_server.server"),
        ("a2a/example.py", "from primr.mcp_server.server import PrimrMCPServer"),
        ("a2a/example.py", "from primr.mcp_server import server"),
        ("mcp_server/example.py", "from . import server"),
        ("a2a/example.py", "from ..mcp_server import server"),
    ],
)
def test_concrete_mcp_server_import_detector(relative_path: str, statement: str):
    """Cover every supported static import spelling for the concrete module."""
    path = SRC_ROOT / relative_path
    assert _imports_concrete_mcp_server(path, ast.parse(statement))


@pytest.mark.parametrize("doc", ["CLAUDE.md", "AGENTS.md"])
def test_agent_contracts_exist(doc):
    """Both the dev contract (CLAUDE.md) and the operate guide (AGENTS.md) ship."""
    assert (SRC_ROOT.parent.parent / doc).is_file(), f"{doc} is missing from the repo root"
