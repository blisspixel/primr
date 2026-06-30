"""
Coverage-focused tests for primr.core.vendor_research.

Covers dataclass helpers, path resolution, freshness/staleness branches of
get_or_generate (sync + async), preflight validation, vendor metadata,
prompt building, and generate_vendor_research success/failure paths.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.ai.deep_research import ResearchStatus
from primr.core.vendor_research import (
    VendorResearchFile,
    VendorResearchResult,
    _allow_vendor_auto_refresh,
    _build_vendor_prompt,
    _get_vendor_metadata,
    _validate_vendor_research_preflight,
    _vendor_research_age,
    generate_vendor_research,
    get_manual_research_path,
    get_or_generate_vendor_research,
    get_or_generate_vendor_research_sync,
    get_vendor_research_path,
    is_vendor_research_current,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# dataclasses
# ---------------------------------------------------------------------------


def test_vendor_research_file_exists_and_age(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_text("data", encoding="utf-8")
    vrf = VendorResearchFile(path=f, vendor="azure", month="2026-01", is_manual=False)
    assert vrf.exists is True
    # Freshly written file: age is ~0 (allow +/-1 day for clock/fs rounding).
    assert abs(vrf.age_days) <= 1


def test_vendor_research_file_missing_age_negative(tmp_path: Path):
    vrf = VendorResearchFile(
        path=tmp_path / "missing.txt", vendor="aws", month="m", is_manual=False
    )
    assert vrf.exists is False
    assert vrf.age_days == -1


def test_vendor_research_result_paths_only_existing(tmp_path: Path):
    real = tmp_path / "real.txt"
    real.write_text("x", encoding="utf-8")
    missing = tmp_path / "missing.txt"
    result = VendorResearchResult(
        files=(
            VendorResearchFile(real, "azure", "m", False),
            VendorResearchFile(missing, "azure", "m", False),
        ),
        generated=False,
        duration_seconds=1.0,
    )
    assert result.paths == [real]


# ---------------------------------------------------------------------------
# path resolution / freshness
# ---------------------------------------------------------------------------


def test_get_vendor_research_path_default_month():
    p = get_vendor_research_path("Azure")
    assert "vendor-research-azure-" in p.name
    assert p.suffix == ".txt"


def test_get_vendor_research_path_explicit_month():
    p = get_vendor_research_path("aws", month="2025-12")
    assert p.name == "vendor-research-aws-2025-12.txt"


def test_get_manual_research_path_non_azure_is_none():
    assert get_manual_research_path("aws") is None


def test_get_manual_research_path_azure_when_missing():
    with patch("primr.core.vendor_research.Path") as mock_path:
        instance = MagicMock()
        instance.exists.return_value = False
        # Path(...) / "docs" / "..." chain returns instance
        mock_path.return_value.__truediv__.return_value.__truediv__.return_value = instance
        assert get_manual_research_path("azure") is None


def test_vendor_research_age_missing(tmp_path: Path):
    exists, age = _vendor_research_age(tmp_path / "nope.txt")
    assert exists is False
    assert age is None


def test_vendor_research_age_present(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    exists, age = _vendor_research_age(f)
    assert exists is True
    assert age is not None
    assert abs(age) <= 1


def test_is_vendor_research_current_fresh(tmp_path: Path):
    fresh = tmp_path / "vendor-research-aws-2026-01.txt"
    fresh.write_text("x", encoding="utf-8")
    with (
        patch("primr.core.vendor_research.get_manual_research_path", return_value=None),
        patch("primr.core.vendor_research.get_vendor_research_path", return_value=fresh),
    ):
        assert is_vendor_research_current("aws") is True


def test_is_vendor_research_current_missing(tmp_path: Path):
    missing = tmp_path / "missing.txt"
    with (
        patch("primr.core.vendor_research.get_manual_research_path", return_value=None),
        patch("primr.core.vendor_research.get_vendor_research_path", return_value=missing),
    ):
        assert is_vendor_research_current("aws") is False


def test_is_vendor_research_current_stale(tmp_path: Path):
    stale = tmp_path / "stale.txt"
    stale.write_text("x", encoding="utf-8")
    old = time.time() - 60 * 86400
    os.utime(stale, (old, old))
    with (
        patch("primr.core.vendor_research.get_manual_research_path", return_value=None),
        patch("primr.core.vendor_research.get_vendor_research_path", return_value=stale),
    ):
        assert is_vendor_research_current("aws") is False


def test_is_vendor_research_current_manual_fresh(tmp_path: Path):
    manual = tmp_path / "manual.txt"
    manual.write_text("x", encoding="utf-8")
    with patch("primr.core.vendor_research.get_manual_research_path", return_value=manual):
        assert is_vendor_research_current("azure") is True


# ---------------------------------------------------------------------------
# _allow_vendor_auto_refresh
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("val", "expected"), [("1", True), ("true", True), ("YES", True), ("0", False)]
)
def test_allow_vendor_auto_refresh(monkeypatch, val, expected):
    monkeypatch.setenv("PRIMR_ALLOW_VENDOR_REFRESH", val)
    assert _allow_vendor_auto_refresh() is expected


def test_allow_vendor_auto_refresh_unset(monkeypatch):
    monkeypatch.delenv("PRIMR_ALLOW_VENDOR_REFRESH", raising=False)
    assert _allow_vendor_auto_refresh() is False


# ---------------------------------------------------------------------------
# get_or_generate_vendor_research_sync
# ---------------------------------------------------------------------------


def test_sync_fresh_reused(tmp_path: Path):
    fresh = tmp_path / "vendor-research-aws-2026-01.txt"
    fresh.write_text("x", encoding="utf-8")
    with patch("primr.core.vendor_research.get_vendor_research_path", return_value=fresh):
        paths = get_or_generate_vendor_research_sync("aws")
    assert str(fresh) in paths


def test_sync_stale_reused_without_refresh(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PRIMR_ALLOW_VENDOR_REFRESH", raising=False)
    stale = tmp_path / "vendor-research-aws-2026-01.txt"
    stale.write_text("x", encoding="utf-8")
    old = time.time() - 60 * 86400
    os.utime(stale, (old, old))
    with patch("primr.core.vendor_research.get_vendor_research_path", return_value=stale):
        paths = get_or_generate_vendor_research_sync("aws")
    assert str(stale) in paths


def test_sync_azure_includes_manual(tmp_path: Path):
    manual = tmp_path / "manual.txt"
    manual.write_text("x", encoding="utf-8")
    fresh = tmp_path / "vendor-research-azure-2026-01.txt"
    fresh.write_text("x", encoding="utf-8")
    with (
        patch("primr.core.vendor_research.get_manual_research_path", return_value=manual),
        patch("primr.core.vendor_research.get_vendor_research_path", return_value=fresh),
    ):
        paths = get_or_generate_vendor_research_sync("azure")
    assert str(manual) in paths


def test_sync_missing_skips_without_opt_in(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PRIMR_ALLOW_VENDOR_REFRESH", raising=False)
    missing = tmp_path / "missing.txt"
    with (
        patch("primr.core.vendor_research.get_vendor_research_path", return_value=missing),
        patch(
            "primr.core.vendor_research.generate_vendor_research_sync",
            return_value=str(tmp_path / "generated.txt"),
        ) as mock_gen,
    ):
        paths = get_or_generate_vendor_research_sync("aws")
    assert not mock_gen.called
    assert paths == []


def test_sync_generates_missing_with_explicit_opt_in(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PRIMR_ALLOW_VENDOR_REFRESH", "1")
    missing = tmp_path / "missing.txt"
    with (
        patch("primr.core.vendor_research.get_vendor_research_path", return_value=missing),
        patch(
            "primr.core.vendor_research.generate_vendor_research_sync",
            return_value=str(tmp_path / "generated.txt"),
        ) as mock_gen,
    ):
        paths = get_or_generate_vendor_research_sync("aws")
    assert mock_gen.called
    assert str(tmp_path / "generated.txt") in paths


# ---------------------------------------------------------------------------
# get_or_generate_vendor_research (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_fresh_reused(tmp_path: Path):
    fresh = tmp_path / "vendor-research-aws-2026-01.txt"
    fresh.write_text("x", encoding="utf-8")
    with patch("primr.core.vendor_research.get_vendor_research_path", return_value=fresh):
        result = await get_or_generate_vendor_research("aws")
    assert result.generated is False
    assert fresh in result.paths


@pytest.mark.asyncio
async def test_async_stale_reused(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PRIMR_ALLOW_VENDOR_REFRESH", raising=False)
    stale = tmp_path / "vendor-research-aws-2026-01.txt"
    stale.write_text("x", encoding="utf-8")
    old = time.time() - 60 * 86400
    os.utime(stale, (old, old))
    with patch("primr.core.vendor_research.get_vendor_research_path", return_value=stale):
        result = await get_or_generate_vendor_research("aws")
    assert result.generated is False
    assert stale in result.paths


@pytest.mark.asyncio
async def test_async_missing_skips_without_opt_in(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PRIMR_ALLOW_VENDOR_REFRESH", raising=False)
    missing = tmp_path / "missing.txt"
    generated = tmp_path / "generated.txt"
    generated.write_text("x", encoding="utf-8")
    with (
        patch("primr.core.vendor_research.get_vendor_research_path", return_value=missing),
        patch(
            "primr.core.vendor_research.generate_vendor_research",
            new=AsyncMock(return_value=str(generated)),
        ) as mock_gen,
    ):
        result = await get_or_generate_vendor_research("aws")
    assert not mock_gen.called
    assert result.generated is False
    assert result.paths == []


@pytest.mark.asyncio
async def test_async_generates_missing_with_explicit_opt_in(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PRIMR_ALLOW_VENDOR_REFRESH", "1")
    missing = tmp_path / "missing.txt"
    generated = tmp_path / "generated.txt"
    generated.write_text("x", encoding="utf-8")
    with (
        patch("primr.core.vendor_research.get_vendor_research_path", return_value=missing),
        patch(
            "primr.core.vendor_research.generate_vendor_research",
            new=AsyncMock(return_value=str(generated)),
        ) as mock_gen,
    ):
        result = await get_or_generate_vendor_research("aws")
    assert mock_gen.called
    assert result.generated is True
    assert generated in result.paths


@pytest.mark.asyncio
async def test_async_force_refresh(tmp_path: Path):
    existing = tmp_path / "vendor-research-aws-2026-01.txt"
    existing.write_text("x", encoding="utf-8")
    generated = tmp_path / "generated.txt"
    generated.write_text("x", encoding="utf-8")
    with (
        patch("primr.core.vendor_research.get_vendor_research_path", return_value=existing),
        patch(
            "primr.core.vendor_research.generate_vendor_research",
            new=AsyncMock(return_value=str(generated)),
        ) as mock_gen,
    ):
        result = await get_or_generate_vendor_research("aws", force_refresh=True)
    assert mock_gen.called
    assert result.generated is True


# ---------------------------------------------------------------------------
# preflight / metadata / prompt
# ---------------------------------------------------------------------------


def test_preflight_invalid_vendor():
    with patch("primr.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.api.gemini_key = "fake"
        errors = _validate_vendor_research_preflight("badcloud")
    assert any("Invalid vendor" in e for e in errors)


def test_preflight_missing_api_key():
    with patch("primr.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.api.gemini_key = None
        errors = _validate_vendor_research_preflight("aws")
    assert any("GEMINI_API_KEY" in e for e in errors)


def test_preflight_passes_valid():
    with patch("primr.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.api.gemini_key = "fake"
        errors = _validate_vendor_research_preflight("aws")
    assert errors == []


@pytest.mark.parametrize("vendor", ["azure", "aws", "gcp", "agnostic", "private"])
def test_vendor_metadata_has_keys(vendor):
    meta = _get_vendor_metadata(vendor)
    assert {"name", "conference", "platform"} <= set(meta)


def test_vendor_metadata_unknown_falls_back():
    meta = _get_vendor_metadata("weird")
    assert meta == _get_vendor_metadata("agnostic")


def test_build_vendor_prompt_contains_vendor_name():
    prompt = _build_vendor_prompt("aws")
    assert "Amazon Web Services (AWS)" in prompt
    assert "Foundation Models" in prompt
    assert "Sources" in prompt


# ---------------------------------------------------------------------------
# generate_vendor_research
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_vendor_research_preflight_fail():
    with patch(
        "primr.core.vendor_research._validate_vendor_research_preflight",
        return_value=["boom"],
    ):
        result = await generate_vendor_research("aws")
    assert result is None


@pytest.mark.asyncio
async def test_generate_vendor_research_success(tmp_path: Path):
    out = tmp_path / "vendor-research-aws-2026-01.txt"

    fake_result = MagicMock()
    fake_result.status = ResearchStatus.COMPLETED
    fake_result.content = "Research body content"
    fake_result.duration_seconds = 120.0

    client = MagicMock()
    client.research = AsyncMock(return_value=fake_result)

    with (
        patch(
            "primr.core.vendor_research._validate_vendor_research_preflight",
            return_value=[],
        ),
        patch("primr.core.vendor_research.get_vendor_research_path", return_value=out),
        patch("primr.ai.deep_research.get_deep_research_client", return_value=client),
    ):
        result = await generate_vendor_research("aws")

    assert result == str(out)
    assert out.read_text(encoding="utf-8") == "Research body content"


@pytest.mark.asyncio
async def test_generate_vendor_research_failed_status(tmp_path: Path):
    fake_result = MagicMock()
    fake_result.status = ResearchStatus.FAILED
    fake_result.content = ""

    client = MagicMock()
    client.research = AsyncMock(return_value=fake_result)

    with (
        patch(
            "primr.core.vendor_research._validate_vendor_research_preflight",
            return_value=[],
        ),
        patch(
            "primr.core.vendor_research.get_vendor_research_path",
            return_value=tmp_path / "out.txt",
        ),
        patch("primr.ai.deep_research.get_deep_research_client", return_value=client),
    ):
        result = await generate_vendor_research("aws")
    assert result is None


@pytest.mark.asyncio
async def test_generate_vendor_research_exception(tmp_path: Path):
    client = MagicMock()
    client.research = AsyncMock(side_effect=RuntimeError("network down"))

    with (
        patch(
            "primr.core.vendor_research._validate_vendor_research_preflight",
            return_value=[],
        ),
        patch(
            "primr.core.vendor_research.get_vendor_research_path",
            return_value=tmp_path / "out.txt",
        ),
        patch("primr.ai.deep_research.get_deep_research_client", return_value=client),
    ):
        result = await generate_vendor_research("aws")
    assert result is None
