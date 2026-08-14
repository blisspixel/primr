"""Coverage tests for primr.ai.client.

Targets error-classification branches (daily quota, invalid key, timeout),
fallback-model retry, timeout enforcement, response/usage extraction edge
cases, usage-summary cost math, and the thin wrapper functions. All genai
calls are mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.client import AIClient, TokenUsage, llm, llm_fast, reset_client
from primr.utils.errors import AIError


@pytest.fixture(autouse=True)
def _reset():
    reset_client()
    yield
    reset_client()


@pytest.fixture
def client():
    with (
        patch("primr.ai.client.genai.Client") as mock_client_class,
        patch("primr.ai.client.get_settings") as mock_get,
    ):
        settings = MagicMock()
        settings.api.gemini_key = "test-key"
        settings.ai.flash_model = "flash-x"
        settings.ai.pro_model = "pro-x"
        settings.ai.max_retries = 3
        settings.ai.model_fallbacks = {}
        mock_get.return_value = settings
        inst = MagicMock()
        mock_client_class.return_value = inst
        c = AIClient()
        c._mock_client = inst
        yield c


def _resp(text="hello", in_tok=10, out_tok=5):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(prompt_token_count=in_tok, candidates_token_count=out_tok),
    )


# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------


def test_token_usage_total():
    assert TokenUsage(3, 4).total_tokens == 7


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_generate_rejects_empty_prompt(client):
    with pytest.raises(ValueError, match="prompt cannot be empty"):
        client.generate("   ")


def test_generate_rejects_bad_temperature(client):
    with pytest.raises(ValueError, match="temperature"):
        client.generate("hi", temperature=5.0)


def test_generate_rejects_bad_thinking_level(client):
    with pytest.raises(ValueError, match="thinking_level"):
        client.generate("hi", thinking_level="extreme")


# ---------------------------------------------------------------------------
# Success + usage tracking
# ---------------------------------------------------------------------------


def test_generate_tracks_usage(client):
    client._mock_client.models.generate_content.return_value = _resp()
    out = client.generate("hi")
    assert out == "hello"
    assert client.total_input_tokens == 10
    assert client.total_output_tokens == 5
    assert client.call_count == 1
    assert "flash-x" in client.usage_by_model


# ---------------------------------------------------------------------------
# Error classification branches
# ---------------------------------------------------------------------------


def test_generate_daily_quota_raises_immediately(client):
    client._mock_client.models.generate_content.side_effect = Exception("boom")
    with (
        patch("primr.ai.client.is_daily_quota_exhausted", return_value=True),
        pytest.raises(AIError, match="Daily API quota exhausted"),
    ):
        client.generate("hi")


def test_generate_invalid_key_raises_immediately(client):
    client._mock_client.models.generate_content.side_effect = Exception("bad key")
    with (
        patch("primr.ai.client.is_daily_quota_exhausted", return_value=False),
        patch("primr.ai.client.is_invalid_api_key_error", return_value=True),
        pytest.raises(AIError, match="Invalid API key"),
    ):
        client.generate("hi")


def test_generate_timeout_error_raises(client):
    client._mock_client.models.generate_content.side_effect = Exception("timed out")
    with (
        patch("primr.ai.client.is_daily_quota_exhausted", return_value=False),
        patch("primr.ai.client.is_invalid_api_key_error", return_value=False),
        patch("primr.ai.client.is_timeout_error", return_value=True),
        pytest.raises(AIError),
    ):
        client.generate("hi")


def test_generate_retries_then_succeeds_with_fallback(client):
    client._settings.model_fallbacks = {"flash-x": ["fallback-model"]}
    client._mock_client.models.generate_content.side_effect = [
        Exception("transient 503"),
        _resp(text="recovered"),
    ]
    with (
        patch("primr.ai.client.is_daily_quota_exhausted", return_value=False),
        patch("primr.ai.client.is_invalid_api_key_error", return_value=False),
        patch("primr.ai.client.is_timeout_error", return_value=False),
        patch("primr.ai.client.is_rate_limit_error", return_value=True),
        patch("primr.ai.client.calculate_retry_delay", return_value=0),
        patch("primr.ai.client.time.sleep"),
    ):
        out = client.generate("hi", max_retries=2)
    assert out == "recovered"


def test_generate_exhausts_retries_raises(client):
    client._mock_client.models.generate_content.side_effect = Exception("persistent")
    with (
        patch("primr.ai.client.is_daily_quota_exhausted", return_value=False),
        patch("primr.ai.client.is_invalid_api_key_error", return_value=False),
        patch("primr.ai.client.is_timeout_error", return_value=False),
        patch("primr.ai.client.is_rate_limit_error", return_value=False),
        patch("primr.ai.client.calculate_retry_delay", return_value=0),
        patch("primr.ai.client.time.sleep"),
        pytest.raises(AIError, match="failed after"),
    ):
        client.generate("hi", max_retries=2)


# ---------------------------------------------------------------------------
# Timeout enforcement (deadline path)
# ---------------------------------------------------------------------------


def test_generate_timeout_deadline_exceeded(client):
    # monotonic returns: deadline-calc, then a far-future value so remaining<=0.
    times = iter([100.0, 1000.0, 1000.0, 1000.0])
    with (
        patch("primr.ai.client.time.monotonic", lambda: next(times)),
        pytest.raises(AIError),
    ):
        client.generate("hi", timeout=1.0, max_retries=1)


# ---------------------------------------------------------------------------
# _extract_usage edge cases
# ---------------------------------------------------------------------------


def test_extract_usage_no_metadata(client):
    assert client._extract_usage(SimpleNamespace()) is None
    assert client._extract_usage(SimpleNamespace(usage_metadata=None)) is None


def test_extract_usage_non_int_counts(client):
    resp = SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count="x", candidates_token_count=5)
    )
    assert client._extract_usage(resp) is None


def test_extract_usage_negative_counts(client):
    resp = SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count=-1, candidates_token_count=5)
    )
    assert client._extract_usage(resp) is None


def test_extract_usage_valid(client):
    resp = SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=8)
    )
    usage = client._extract_usage(resp)
    assert usage.input_tokens == 12
    assert usage.output_tokens == 8


# ---------------------------------------------------------------------------
# _validate_response_text edge cases
# ---------------------------------------------------------------------------


def test_validate_response_none(client):
    with pytest.raises(AIError, match="None response"):
        client._validate_response_text(None)


def test_validate_response_missing_text_attr(client):
    obj = object()
    with pytest.raises(AIError, match="missing 'text'"):
        client._validate_response_text(obj)


def test_validate_response_candidate_fallback(client):
    part = SimpleNamespace(text="from candidate")
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    resp = SimpleNamespace(text=None, candidates=[candidate])
    assert client._validate_response_text(resp) == "from candidate"


def test_validate_response_none_no_candidates(client):
    resp = SimpleNamespace(text=None)
    with pytest.raises(AIError, match="no candidates"):
        client._validate_response_text(resp)


def test_validate_response_empty_text(client):
    resp = SimpleNamespace(text="   ")
    with pytest.raises(AIError, match="empty response"):
        client._validate_response_text(resp)


# ---------------------------------------------------------------------------
# _get_model + _get_fallback_model
# ---------------------------------------------------------------------------


def test_get_model_flash_types(client):
    assert client._get_model("scraping") == "flash-x"
    assert client._get_model("fast") == "flash-x"


def test_get_model_pro_types(client):
    assert client._get_model("analysis") == "pro-x"
    assert client._get_model("report") == "pro-x"


def test_get_model_unknown_defaults_to_flash(client):
    assert client._get_model("nonsense") == "flash-x"


def test_get_fallback_model_none(client):
    assert client._get_fallback_model("flash-x") is None


# ---------------------------------------------------------------------------
# generate_with_context / generate_fast
# ---------------------------------------------------------------------------


def test_generate_with_context_builds_prompt(client):
    captured = {}

    def _gen(prompt, **kwargs):
        captured["prompt"] = prompt
        return "ok"

    client.generate = _gen  # type: ignore
    client.generate_with_context("Question?", {"Background": "facts", "Empty": ""})
    assert "## Background" in captured["prompt"]
    assert "Empty" not in captured["prompt"]


def test_generate_fast_uses_low_thinking(client):
    captured = {}

    def _gen(prompt, **kwargs):
        captured.update(kwargs)
        return "ok"

    client.generate = _gen  # type: ignore
    client.generate_fast("hi")
    assert captured["thinking_level"] == "low"


# ---------------------------------------------------------------------------
# get_usage_summary + reset_usage
# ---------------------------------------------------------------------------


def test_usage_summary_with_per_call_cost(client):
    client.usage_by_model = {
        "flash-x": {
            "input_tokens": 1000,
            "output_tokens": 500,
            "calls": 1,
            "cost": 0.25,
        }
    }
    client.call_count = 1
    client.total_input_tokens = 1000
    client.total_output_tokens = 500
    with patch("primr.config.models.PrimrModels.get_price", return_value=(1.0, 2.0)):
        summary = client.get_usage_summary()
    assert summary["total_cost"] == pytest.approx(0.25)
    assert summary["total_tokens"] == 1500


def test_usage_summary_no_usage_uses_pro_fallback(client):
    client.total_input_tokens = 1_000_000
    client.total_output_tokens = 1_000_000
    fake_pro = SimpleNamespace(cost_per_1m_input_tokens=2.0, cost_per_1m_output_tokens=4.0)
    with patch("primr.config.models.PrimrModels.get_active_pro_model", return_value=fake_pro):
        summary = client.get_usage_summary()
    assert summary["input_cost"] == pytest.approx(2.0)
    assert summary["output_cost"] == pytest.approx(4.0)
    assert summary["total_cost"] == pytest.approx(6.0)


def test_reset_usage(client):
    client.total_input_tokens = 10
    client.usage_by_model = {"m": {}}
    client.reset_usage()
    assert client.total_input_tokens == 0
    assert client.usage_by_model == {}


# ---------------------------------------------------------------------------
# close + context manager
# ---------------------------------------------------------------------------


def test_close_calls_underlying_close(client):
    closed = {"v": False}

    def _close():
        closed["v"] = True

    client._client.close = _close
    client.close()
    assert closed["v"] is True


def test_context_manager(client):
    client._client.close = MagicMock()
    with client as c:
        assert c is client


# ---------------------------------------------------------------------------
# Module-level wrappers
# ---------------------------------------------------------------------------


def test_llm_wrapper(monkeypatch):
    fake = MagicMock()
    fake.generate.return_value = "wrapped"
    monkeypatch.setattr("primr.ai.client.get_client", lambda: fake)
    assert llm("hi") == "wrapped"
    assert fake.generate.called


def test_llm_fast_wrapper(monkeypatch):
    fake = MagicMock()
    fake.generate_fast.return_value = "fast"
    monkeypatch.setattr("primr.ai.client.get_client", lambda: fake)
    assert llm_fast("hi") == "fast"
