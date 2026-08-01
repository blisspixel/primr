"""Tests for server-issued MCP approval tokens."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from primr.mcp_server import approval_tokens
from primr.mcp_server.server import create_mcp_server
from tests.mcp_server.sdk_compat import call_tool_handler


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = str(Path(tmpdir) / "test_journal.json")
        s = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
        s.rate_limiter.reset()
        yield s


async def _call(server, name: str, arguments: dict) -> dict:
    result = await call_tool_handler(server, name, arguments)
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_estimate_run_returns_approval_token(server):
    data = await _call(
        server,
        "estimate_run",
        {"company_url": "https://example.com", "mode": "full"},
    )

    assert data["approval_token"]
    assert data["approval_token_id"]
    assert data["approval_expires_at"].endswith("Z")


@pytest.mark.asyncio
async def test_research_requires_approval_token_when_enforced(server, monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")

    data = await _call(
        server,
        "research_company",
        {
            "company_name": "Acme Corp",
            "company_url": "https://example.com",
            "mode": "full",
            "max_estimated_cost_usd": 100.0,
        },
    )

    assert data["error"] is True
    assert data["error_type"] == "approval_token_required"


@pytest.mark.asyncio
async def test_research_accepts_matching_approval_token_when_enforced(server, monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    estimate = await _call(
        server,
        "estimate_run",
        {
            "company_url": "https://example.com",
            "mode": "full",
            "platforms": ["microsoft"],
            "strategy_type": "ai",
        },
    )
    assert estimate["platforms"] == ["azure"]

    data = await _call(
        server,
        "research_company",
        {
            "company_name": "Acme Corp",
            "company_url": "https://example.com",
            "mode": "full",
            "platform": "azure",
            "max_estimated_cost_usd": estimate["estimated_cost_usd"],
            "approval_token": estimate["approval_token"],
        },
    )

    assert data["accepted"] is True
    assert "job_id" in data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "shape,error_type",
    [
        ({"platforms": ["azure"]}, "unsupported_platforms_parameter"),
        ({"platform": "ms"}, "unsupported_platform_fanout"),
        ({"strategy_type": "customer_experience"}, "unsupported_strategy_type"),
    ],
)
async def test_research_rejects_unexecutable_shape_before_job_creation(server, shape, error_type):
    from primr.mcp_server.tools import _handle_research_company

    result = await _handle_research_company(
        server,
        {
            "company_name": "Acme Corp",
            "company_url": "https://example.com",
            "mode": "full",
            **shape,
        },
        "stdio",
    )
    data = json.loads(result[0].text)

    assert data["error"] is True
    assert data["error_type"] == error_type
    assert server.job_store.get_active() is None


@pytest.mark.asyncio
async def test_research_rejects_approval_args_swap(server, monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    estimate = await _call(
        server,
        "estimate_run",
        {"company_url": "https://example.com", "mode": "full"},
    )

    data = await _call(
        server,
        "research_company",
        {
            "company_name": "Acme Corp",
            "company_url": "https://example.org",
            "mode": "full",
            "max_estimated_cost_usd": 100.0,
            "approval_token": estimate["approval_token"],
        },
    )

    assert data["error"] is True
    assert data["error_type"] == "invalid_approval_token"
    assert "arguments do not match" in data["message"]


@pytest.mark.asyncio
async def test_research_rejects_platform_swap_after_approval(server, monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    estimate = await _call(
        server,
        "estimate_run",
        {
            "company_url": "https://example.com",
            "mode": "full",
            "platforms": ["azure"],
        },
    )

    data = await _call(
        server,
        "research_company",
        {
            "company_name": "Acme Corp",
            "company_url": "https://example.com",
            "mode": "full",
            "platform": "aws",
            "max_estimated_cost_usd": estimate["estimated_cost_usd"],
            "approval_token": estimate["approval_token"],
        },
    )

    assert data["error"] is True
    assert data["error_type"] == "invalid_approval_token"
    assert "arguments do not match" in data["message"]
    assert server.job_store.get_active() is None


@pytest.mark.asyncio
async def test_approval_token_is_single_use_for_strategy(server, monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    report = Path("output/test_approval_token_report.md")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# report", encoding="utf-8")
    estimate = await _call(server, "estimate_strategy", {"strategy_type": "customer_experience"})
    args = {
        "report_path": report.name,
        "strategy_type": "customer_experience",
        "max_estimated_cost_usd": estimate["estimated_cost_usd"],
        "approval_token": estimate["approval_token"],
    }

    try:
        with patch(
            "primr.mcp_server.tools.run_strategy_generation",
            new=AsyncMock(
                return_value={
                    "output_path": "output/strategy.md",
                    "strategy_type": "customer_experience",
                    "qa_score": None,
                }
            ),
        ):
            first = await _call(server, "generate_strategy", args)
            second = await _call(server, "generate_strategy", args)
    finally:
        report.unlink(missing_ok=True)

    assert first["success"] is True
    assert second["error"] is True
    assert second["error_type"] == "invalid_approval_token"
    assert "already used" in second["message"]


@pytest.mark.asyncio
async def test_tampered_approval_token_is_rejected(server, monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    estimate = await _call(server, "estimate_run", {"company_url": "https://example.com"})
    payload, signature = estimate["approval_token"].split(".", 1)
    replacement = "A" if signature[-1] != "A" else "B"
    token = f"{payload}.{signature[:-1]}{replacement}"

    data = await _call(
        server,
        "research_company",
        {
            "company_name": "Acme Corp",
            "company_url": "https://example.com",
            "max_estimated_cost_usd": 100.0,
            "approval_token": token,
        },
    )

    assert data["error"] is True
    assert data["error_type"] == "invalid_approval_token"


def test_approval_token_is_bound_to_issuing_process(monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    monkeypatch.setenv("PRIMR_MCP_APPROVAL_TOKEN_SECRET", "s" * 32)
    approval = approval_tokens.issue_approval_token(
        tool_name="generate_strategy",
        approval_args={"strategy_type": "ai_strategy", "platform": "agnostic"},
        max_cost_usd=1.0,
    )
    monkeypatch.setattr(approval_tokens, "_PROCESS_INSTANCE_ID", "replacement-process")

    error = approval_tokens.enforce_approval_token(
        tool_name="generate_strategy",
        approval_args={"strategy_type": "ai_strategy", "platform": "agnostic"},
        estimated_cost_usd=1.0,
        approval_token=approval["approval_token"],
    )

    assert error is not None
    assert error["error_type"] == "invalid_approval_token"
    assert "another server process" in error["message"]


def test_process_mismatch_does_not_consume_token(monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    approval_args = {"strategy_type": "ai_strategy", "platform": "agnostic"}
    approval = approval_tokens.issue_approval_token(
        tool_name="generate_strategy",
        approval_args=approval_args,
        max_cost_usd=1.0,
    )
    original_instance = approval_tokens._PROCESS_INSTANCE_ID
    monkeypatch.setattr(approval_tokens, "_PROCESS_INSTANCE_ID", "replacement-process")

    rejected = approval_tokens.enforce_approval_token(
        tool_name="generate_strategy",
        approval_args=approval_args,
        estimated_cost_usd=1.0,
        approval_token=approval["approval_token"],
    )
    monkeypatch.setattr(approval_tokens, "_PROCESS_INSTANCE_ID", original_instance)
    accepted = approval_tokens.enforce_approval_token(
        tool_name="generate_strategy",
        approval_args=approval_args,
        estimated_cost_usd=1.0,
        approval_token=approval["approval_token"],
    )

    assert rejected is not None
    assert accepted is None


@pytest.mark.parametrize("mutation", ["legacy_version", "missing_instance"])
def test_legacy_or_unbound_approval_tokens_are_rejected(monkeypatch, mutation):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    approval_args = {"strategy_type": "ai_strategy", "platform": "agnostic"}
    approval = approval_tokens.issue_approval_token(
        tool_name="generate_strategy",
        approval_args=approval_args,
        max_cost_usd=1.0,
    )
    payload = approval_tokens._decode_token(approval["approval_token"])
    if mutation == "legacy_version":
        payload["v"] = 1
    else:
        payload.pop("instance")
    encoded = approval_tokens._b64encode_json(payload)
    token = f"{encoded}.{approval_tokens._sign(encoded)}"

    error = approval_tokens.enforce_approval_token(
        tool_name="generate_strategy",
        approval_args=approval_args,
        estimated_cost_usd=1.0,
        approval_token=token,
    )

    assert error is not None
    assert error["error_type"] == "invalid_approval_token"


def test_same_process_approval_remains_single_use(monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    approval_args = {"strategy_type": "ai_strategy", "platform": "agnostic"}
    approval = approval_tokens.issue_approval_token(
        tool_name="generate_strategy",
        approval_args=approval_args,
        max_cost_usd=1.0,
    )

    first = approval_tokens.enforce_approval_token(
        tool_name="generate_strategy",
        approval_args=approval_args,
        estimated_cost_usd=1.0,
        approval_token=approval["approval_token"],
    )
    second = approval_tokens.enforce_approval_token(
        tool_name="generate_strategy",
        approval_args=approval_args,
        estimated_cost_usd=1.0,
        approval_token=approval["approval_token"],
    )

    assert first is None
    assert second is not None
    assert "already used" in second["message"]
