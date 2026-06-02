"""Coverage-focused unit tests for `primr.skill_pack.evidence`.

These exercise the standalone evidence-collection orchestration:
domain extraction, the recon and hiring sub-collectors, their fail-open
error paths, env-var skipping, and the top-level `collect_evidence` toggles.

All LLM/recon/hiring seams are mocked — no network, no API calls. The
sub-collectors import their dependencies lazily inside the function body,
so we patch the *source* modules (`recon_tool.resolver`,
`primr.core.recon_context`, `primr.data.hiring_signals`) which the lazy
`from ... import ...` statements resolve against.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from primr.skill_pack import evidence
from primr.skill_pack.evidence import (
    _collect_hiring,
    _collect_recon,
    _extract_domain,
    collect_evidence,
)


# --------------------------------------------------------------------------- #
# _extract_domain
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://acme.example", "acme.example"),
        ("http://acme.example/path?q=1", "acme.example"),
        ("acme.example", "acme.example"),  # no scheme -> https:// prepended
        ("HTTPS://ACME.EXAMPLE", "acme.example"),  # lowercased
        ("https://www.acme.example", "acme.example"),  # single www. stripped
        ("https://www.acme.example/jobs", "acme.example"),
    ],
)
def test_extract_domain_happy_paths(url: str, expected: str) -> None:
    assert _extract_domain(url) == expected


def test_extract_domain_preserves_www2_subdomain() -> None:
    # www2 is not the literal "www." prefix, so it must be preserved.
    assert _extract_domain("https://www2.acme.example") == "www2.acme.example"


def test_extract_domain_does_not_strip_www_for_bare_two_label_host() -> None:
    # "www.example" has only one dot (count < 2) so the www. is NOT stripped.
    assert _extract_domain("https://www.example") == "www.example"


def test_extract_domain_returns_none_for_empty_host() -> None:
    assert _extract_domain("https://") is None
    assert _extract_domain("") is None


def test_extract_domain_returns_none_on_parse_exception() -> None:
    with patch("urllib.parse.urlparse", side_effect=ValueError("boom")):
        assert _extract_domain("https://acme.example") is None


# --------------------------------------------------------------------------- #
# helpers for patching the lazily-imported recon seam
# --------------------------------------------------------------------------- #
def _install_recon_modules(
    monkeypatch: pytest.MonkeyPatch,
    *,
    resolve_tenant: object,
    format_recon_context: object,
) -> None:
    """Install fake `recon_tool.resolver` + patch `format_recon_context`.

    `_collect_recon` does `from recon_tool.resolver import resolve_tenant`
    and `from primr.core.recon_context import format_recon_context`.
    """
    fake_resolver = types.ModuleType("recon_tool.resolver")
    fake_resolver.resolve_tenant = resolve_tenant  # type: ignore[attr-defined]
    fake_pkg = types.ModuleType("recon_tool")
    monkeypatch.setitem(sys.modules, "recon_tool", fake_pkg)
    monkeypatch.setitem(sys.modules, "recon_tool.resolver", fake_resolver)
    monkeypatch.setattr(
        "primr.core.recon_context.format_recon_context",
        format_recon_context,
    )


# --------------------------------------------------------------------------- #
# _collect_recon
# --------------------------------------------------------------------------- #
def test_collect_recon_returns_none_when_domain_unextractable(tmp_path: Path) -> None:
    assert _collect_recon("https://", tmp_path) is None


def test_collect_recon_returns_none_when_recon_tool_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force the lazy import of recon_tool.resolver to fail.
    monkeypatch.setitem(sys.modules, "recon_tool.resolver", None)
    assert _collect_recon("https://acme.example", tmp_path) is None


def test_collect_recon_returns_none_when_resolve_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(domain: str):
        raise RuntimeError("resolver exploded")

    fmt = MagicMock(return_value="unused")
    _install_recon_modules(monkeypatch, resolve_tenant=_boom, format_recon_context=fmt)
    assert _collect_recon("https://acme.example", tmp_path) is None
    fmt.assert_not_called()


def test_collect_recon_writes_context_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel_info = object()

    async def _resolve(domain: str):
        assert domain == "acme.example"
        return sentinel_info, {"some": "meta"}

    fmt = MagicMock(return_value="RECON CONTEXT BODY")
    _install_recon_modules(monkeypatch, resolve_tenant=_resolve, format_recon_context=fmt)

    out = _collect_recon("https://www.acme.example", tmp_path)

    expected = tmp_path / "_recon_context.txt"
    assert out == str(expected)
    assert expected.read_text(encoding="utf-8") == "RECON CONTEXT BODY"
    # format_recon_context must receive the resolved TenantInfo object.
    fmt.assert_called_once_with(sentinel_info)


def test_collect_recon_returns_none_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _resolve(domain: str):
        return object(), {}

    # format succeeds but writing the file raises.
    fmt = MagicMock(return_value="body")
    _install_recon_modules(monkeypatch, resolve_tenant=_resolve, format_recon_context=fmt)
    monkeypatch.setattr(Path, "write_text", MagicMock(side_effect=OSError("disk full")))
    assert _collect_recon("https://acme.example", tmp_path) is None


# --------------------------------------------------------------------------- #
# _collect_hiring
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("flag", ["1", "true", "YES", " Yes "])
def test_collect_hiring_skipped_via_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    monkeypatch.setenv("PRIMR_SKIP_HIRING_SIGNALS", flag)
    # Should short-circuit before importing the hiring module.
    assert _collect_hiring("Acme Corp", "https://acme.example", tmp_path) is None


def test_collect_hiring_env_falsey_does_not_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRIMR_SKIP_HIRING_SIGNALS", "0")
    gather = MagicMock(return_value=None)  # returns None -> no postings path
    fake_mod = types.ModuleType("primr.data.hiring_signals")
    fake_mod.gather_hiring_signals = gather  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "primr.data.hiring_signals", fake_mod)

    assert _collect_hiring("Acme Corp", "https://acme.example", tmp_path) is None
    gather.assert_called_once()


def test_collect_hiring_returns_none_when_module_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRIMR_SKIP_HIRING_SIGNALS", raising=False)
    monkeypatch.setitem(sys.modules, "primr.data.hiring_signals", None)
    assert _collect_hiring("Acme Corp", "https://acme.example", tmp_path) is None


def test_collect_hiring_returns_none_when_gather_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRIMR_SKIP_HIRING_SIGNALS", raising=False)
    gather = MagicMock(side_effect=RuntimeError("ATS down"))
    fake_mod = types.ModuleType("primr.data.hiring_signals")
    fake_mod.gather_hiring_signals = gather  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "primr.data.hiring_signals", fake_mod)
    assert _collect_hiring("Acme Corp", "https://acme.example", tmp_path) is None


def test_collect_hiring_returns_none_when_signals_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRIMR_SKIP_HIRING_SIGNALS", raising=False)
    gather = MagicMock(return_value=None)
    fake_mod = types.ModuleType("primr.data.hiring_signals")
    fake_mod.gather_hiring_signals = gather  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "primr.data.hiring_signals", fake_mod)
    assert _collect_hiring("Acme Corp", "https://acme.example", tmp_path) is None


def test_collect_hiring_returns_none_when_file_not_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # gather returns a truthy signals object but never writes the .md file.
    monkeypatch.delenv("PRIMR_SKIP_HIRING_SIGNALS", raising=False)
    gather = MagicMock(return_value=object())
    fake_mod = types.ModuleType("primr.data.hiring_signals")
    fake_mod.gather_hiring_signals = gather  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "primr.data.hiring_signals", fake_mod)
    assert _collect_hiring("Acme Corp", "https://acme.example", tmp_path) is None


def test_collect_hiring_returns_path_when_file_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRIMR_SKIP_HIRING_SIGNALS", raising=False)

    expected = tmp_path / "_hiring" / "hiring_signals.md"

    def _gather(name, url, *, corpus, working_folder):
        # Simulate the real module writing its output file.
        assert corpus is None
        assert working_folder == str(tmp_path)
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text("# Hiring signals\n", encoding="utf-8")
        return object()

    fake_mod = types.ModuleType("primr.data.hiring_signals")
    fake_mod.gather_hiring_signals = _gather  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "primr.data.hiring_signals", fake_mod)

    out = _collect_hiring("Acme Corp", "https://acme.example", tmp_path)
    assert out == str(expected)


# --------------------------------------------------------------------------- #
# collect_evidence (top-level orchestration + toggles)
# --------------------------------------------------------------------------- #
def test_collect_evidence_creates_working_dir_and_delegates(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "run"
    with (
        patch.object(evidence, "_collect_recon", return_value="/recon.txt") as mock_recon,
        patch.object(evidence, "_collect_hiring", return_value="/hiring.md") as mock_hiring,
    ):
        result = collect_evidence("Acme Corp", "https://acme.example", target)

    assert target.is_dir()
    assert result == {"recon": "/recon.txt", "hiring": "/hiring.md"}
    mock_recon.assert_called_once_with("https://acme.example", target)
    mock_hiring.assert_called_once_with("Acme Corp", "https://acme.example", target)


def test_collect_evidence_skip_recon(tmp_path: Path) -> None:
    with (
        patch.object(evidence, "_collect_recon") as mock_recon,
        patch.object(evidence, "_collect_hiring", return_value="/hiring.md"),
    ):
        result = collect_evidence("Acme Corp", "https://acme.example", tmp_path, skip_recon=True)
    mock_recon.assert_not_called()
    assert result == {"recon": None, "hiring": "/hiring.md"}


def test_collect_evidence_skip_hiring(tmp_path: Path) -> None:
    with (
        patch.object(evidence, "_collect_recon", return_value="/recon.txt"),
        patch.object(evidence, "_collect_hiring") as mock_hiring,
    ):
        result = collect_evidence("Acme Corp", "https://acme.example", tmp_path, skip_hiring=True)
    mock_hiring.assert_not_called()
    assert result == {"recon": "/recon.txt", "hiring": None}


def test_collect_evidence_skip_both_returns_all_none(tmp_path: Path) -> None:
    with (
        patch.object(evidence, "_collect_recon") as mock_recon,
        patch.object(evidence, "_collect_hiring") as mock_hiring,
    ):
        result = collect_evidence(
            "Acme Corp",
            "https://acme.example",
            tmp_path,
            skip_recon=True,
            skip_hiring=True,
        )
    mock_recon.assert_not_called()
    mock_hiring.assert_not_called()
    assert result == {"recon": None, "hiring": None}
