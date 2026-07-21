"""Tests for the Amazon Bedrock and Azure Foundry providers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.providers.azure_foundry import AzureFoundryProvider, resolve_foundry_base_url
from primr.ai.providers.bedrock import BedrockProvider

# ---------------------------------------------------------------------------
# Azure Foundry
# ---------------------------------------------------------------------------


def test_foundry_base_url_from_explicit(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://x.openai.azure.com/openai/v1/")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    assert resolve_foundry_base_url() == "https://x.openai.azure.com/openai/v1"


def test_foundry_base_url_derived_from_endpoint(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://res.openai.azure.com")
    assert resolve_foundry_base_url() == "https://res.openai.azure.com/openai/v1"


def test_foundry_base_url_none_when_unset(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    assert resolve_foundry_base_url() is None


def test_foundry_unavailable_without_base_url(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    monkeypatch.delenv("AZURE_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    assert AzureFoundryProvider().is_available() is False


def test_foundry_validate_reports_missing_base_url(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    monkeypatch.delenv("AZURE_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    result = AzureFoundryProvider().validate_credentials()
    assert result.ok is False
    assert "AZURE_OPENAI" in result.detail


def test_foundry_inherits_openai_compatible_chat():
    from primr.ai.providers.openai_compatible import OpenAICompatibleProvider

    assert issubclass(AzureFoundryProvider, OpenAICompatibleProvider)


# ---------------------------------------------------------------------------
# Amazon Bedrock
# ---------------------------------------------------------------------------


def test_bedrock_split_messages_separates_system():
    system, msgs = BedrockProvider._split_messages(
        [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    )
    assert system == [{"text": "be terse"}]
    assert msgs == [
        {"role": "user", "content": [{"text": "hi"}]},
        {"role": "assistant", "content": [{"text": "hello"}]},
    ]


def test_bedrock_chat_uses_converse_and_records_usage():
    p = BedrockProvider()
    fake = MagicMock()
    fake.converse.return_value = {
        "output": {"message": {"content": [{"text": "answer"}]}},
        "usage": {"inputTokens": 12, "outputTokens": 7, "cacheReadInputTokens": 2},
    }
    p._runtime = fake
    result = p.chat(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}],
        model="us.anthropic.claude-sonnet-5",
        max_tokens=500,
        temperature=0.5,
    )
    assert result.text == "answer"
    assert result.input_tokens == 12
    assert result.output_tokens == 7
    assert result.cached_input_tokens == 2
    call = fake.converse.call_args.kwargs
    assert call["modelId"] == "us.anthropic.claude-sonnet-5"
    assert call["system"] == [{"text": "sys"}]
    assert call["inferenceConfig"] == {"maxTokens": 500, "temperature": 0.5}


def test_bedrock_chat_requires_a_non_system_message():
    p = BedrockProvider()
    p._runtime = MagicMock()
    with pytest.raises(RuntimeError, match="at least one non-system message"):
        p.chat([{"role": "system", "content": "only"}], model="m")


def test_bedrock_chat_maps_quota_error():
    from primr.ai.providers.base import QuotaExhaustedError

    p = BedrockProvider()
    fake = MagicMock()
    fake.converse.side_effect = RuntimeError("You are not authorized to access this model")
    p._runtime = fake
    with pytest.raises(QuotaExhaustedError):
        p.chat([{"role": "user", "content": "q"}], model="m", retries=0)


def test_bedrock_validate_no_region(monkeypatch):
    import sys

    # Hermetic: boto3 may be absent, and its Session must report no region so the
    # aws-config fallback in _resolve_region also yields None.
    fake_boto3 = MagicMock()
    fake_boto3.Session.return_value.region_name = None
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("AWS_BEDROCK_REGION", raising=False)
    result = BedrockProvider().validate_credentials()
    assert result.ok is False
    assert "AWS_REGION" in result.detail


def test_bedrock_validate_reports_missing_boto3(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("no boto3")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = BedrockProvider().validate_credentials()
    assert result.ok is False
    assert "boto3" in result.detail


def test_bedrock_validate_ok(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "boto3", MagicMock())  # hermetic: boto3 may be absent
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bk-test")
    p = BedrockProvider()
    fake = MagicMock()
    fake.list_foundation_models.return_value = {"modelSummaries": [{}, {}, {}]}
    p._control = fake
    result = p.validate_credentials()
    assert result.ok is True
    assert "3 foundation models" in result.detail


def test_bedrock_region_falls_back_to_boto3_config(monkeypatch):
    """A region set only via `aws configure` (boto3 Session) is honored."""
    import sys

    from primr.ai.providers import bedrock as bmod

    for v in ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_BEDROCK_REGION"):
        monkeypatch.delenv(v, raising=False)
    fake_boto3 = MagicMock()
    fake_boto3.Session.return_value.region_name = "eu-west-1"
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    assert bmod._resolve_region() == "eu-west-1"
