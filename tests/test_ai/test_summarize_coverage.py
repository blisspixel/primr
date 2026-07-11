"""Coverage tests for primr.ai.summarize.

Targets generate_prompt validation, page preparation/clamping, batch packing,
the retry/short-response callback loop, the empty-page formatting branch,
summarize_with_retries, and the local-backend variant. All LLM calls mocked.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai import summarize
from primr.ai.provider_availability import LocalCapacityBusyError

# ---------------------------------------------------------------------------
# generate_prompt
# ---------------------------------------------------------------------------


def test_generate_prompt_unknown_raises():
    with pytest.raises(ValueError, match="not found"):
        summarize.generate_prompt("does_not_exist_prompt")


def test_generate_prompt_formats_known_template():
    # scraped_website_summary is referenced by _summarize_page and exists in
    # prompts.json. It should format without raising.
    out = summarize.generate_prompt(
        "scraped_website_summary",
        company_name="Acme",
        company_website="acme.example",
        website_source="https://acme.example/about",
    )
    assert "Acme" in out


# ---------------------------------------------------------------------------
# _prepare_page_for_summary
# ---------------------------------------------------------------------------


def test_prepare_page_clamps_long_text():
    long_text = "word " * 20000  # well over the char limit
    prepared = summarize._prepare_page_for_summary(long_text, "https://x.example")
    assert len(prepared) <= summarize._BATCH_PAGE_CHAR_LIMIT


def test_prepare_page_short_text_passthrough():
    prepared = summarize._prepare_page_for_summary("Acme makes widgets.", "https://x.example")
    assert "widgets" in prepared


# ---------------------------------------------------------------------------
# _build_summary_batches
# ---------------------------------------------------------------------------


def test_build_summary_batches_by_page_count():
    pages = [(f"u{i}", "abc") for i in range(20)]
    batches = summarize._build_summary_batches(pages)
    # 20 pages, max 8 per batch -> 3 batches (8, 8, 4)
    assert [len(b) for b in batches] == [8, 8, 4]


def test_build_summary_batches_by_char_limit():
    big = "x" * (summarize._BATCH_MAX_CHARS - 100)
    pages = [("u0", big), ("u1", big), ("u2", "small")]
    batches = summarize._build_summary_batches(pages)
    # The second big page exceeds the char cap -> flush after first.
    assert len(batches) >= 2


def test_build_summary_batches_empty():
    assert summarize._build_summary_batches([]) == []


# ---------------------------------------------------------------------------
# _summarize_with_callback
# ---------------------------------------------------------------------------


def test_summarize_callback_returns_valid_first_try():
    out = summarize._summarize_with_callback(
        "content", summarize_fn=lambda c, m: "x" * 300, min_length=200
    )
    assert out == "x" * 300


def test_summarize_callback_short_response_used_anyway():
    with patch("primr.ai.summarize.time.sleep"):
        out = summarize._summarize_with_callback(
            "content",
            summarize_fn=lambda c, m: "short",
            retries=2,
            min_length=200,
        )
        # Below min_length on every attempt, but non-empty -> returned anyway.
        assert out == "short"


def test_summarize_callback_all_empty_returns_empty():
    with patch("primr.ai.summarize.time.sleep"):
        out = summarize._summarize_with_callback(
            "content", summarize_fn=lambda c, m: "", retries=2, min_length=10
        )
    assert out == ""


def test_summarize_callback_handles_exception_then_succeeds():
    calls = {"n": 0}

    def _fn(content, min_length):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return "x" * 300

    with patch("primr.ai.summarize.time.sleep"):
        out = summarize._summarize_with_callback(
            "content", summarize_fn=_fn, retries=3, min_length=200
        )
    assert out == "x" * 300
    assert calls["n"] == 2


def test_summarize_callback_preserves_structured_local_busy_result():
    busy_error = LocalCapacityBusyError(reason="local_capacity_timeout_busy")
    summarize_fn = MagicMock(side_effect=busy_error)

    with (
        patch("primr.ai.summarize.time.sleep") as sleep_mock,
        pytest.raises(LocalCapacityBusyError) as caught,
    ):
        summarize._summarize_with_callback(
            "content",
            summarize_fn=summarize_fn,
            retries=3,
            min_length=200,
        )

    assert caught.value is busy_error
    summarize_fn.assert_called_once()
    sleep_mock.assert_not_called()


# ---------------------------------------------------------------------------
# _summarize_page empty-content branch
# ---------------------------------------------------------------------------


def test_summarize_page_no_content_branch():
    with patch("primr.ai.summarize.time.sleep"):
        out = summarize._summarize_page(
            "Acme",
            "acme.example",
            "https://acme.example/empty",
            "prepared text",
            summarize_fn=lambda c, m: "",
        )
    assert "No meaningful content found" in out
    assert "https://acme.example/empty" in out


def test_summarize_page_with_content():
    out = summarize._summarize_page(
        "Acme",
        "acme.example",
        "https://acme.example/about",
        "prepared text",
        summarize_fn=lambda c, m: "y" * 300,
    )
    assert "### Source: https://acme.example/about" in out


# ---------------------------------------------------------------------------
# summarize_with_retries + _invoke_default_summary_model
# ---------------------------------------------------------------------------


def test_summarize_with_retries_delegates():
    with patch(
        "primr.ai.summarize._invoke_default_summary_model",
        return_value="z" * 300,
    ):
        out = summarize.summarize_with_retries("content", min_length=200)
    assert out == "z" * 300


def test_invoke_default_summary_model_strips(monkeypatch):
    monkeypatch.setattr("primr.ai.summarize.llm", lambda *a, **k: "  result  ")
    assert summarize._invoke_default_summary_model("prompt", 100) == "result"


# ---------------------------------------------------------------------------
# summarize_scraped_content skips blank pages
# ---------------------------------------------------------------------------


def test_summarize_scraped_content_skips_blank(tmp_path):
    data = {
        "https://acme.example/a": "Real content about Acme.",
        "https://acme.example/b": "   ",  # blank -> skipped
    }
    with patch("primr.ai.summarize._invoke_summary_model", return_value="fact " * 60) as mock_fn:
        summarize.summarize_scraped_content("Acme", "acme.example", data, str(tmp_path))
    # Only the non-blank page is summarized.
    assert mock_fn.call_count == 1


def test_summarize_scraped_content_routes_model_to_llm(monkeypatch, tmp_path):
    data = {"https://acme.example/a": "Real content about Acme."}
    route = SimpleNamespace(
        model_name="routed-scrape-summary-model",
        log_metadata=lambda: {
            "stage_id": "fast.scrape_summary",
            "inference_profile": "hybrid",
            "backend_id": "routed-scrape-summary-model",
        },
    )
    resolver = patch("primr.ai.stage_routing.resolve_stage_model", return_value=route)
    llm_calls = []

    def _llm(*_args, **kwargs):
        llm_calls.append(kwargs)
        return "fact " * 60

    monkeypatch.setattr("primr.ai.summarize.llm", _llm)
    with resolver as mock_resolver:
        summarize.summarize_scraped_content("Acme", "acme.example", data, str(tmp_path))

    mock_resolver.assert_called_once_with("fast.scrape_summary", legacy_model_type="scraping")
    assert llm_calls[0]["model"] == "routed-scrape-summary-model"


def test_summarize_scraped_content_records_route_usage(monkeypatch, tmp_path):
    data = {"https://acme.example/a": "Real content about Acme."}
    route = SimpleNamespace(
        model_name="routed-scrape-summary-model",
        log_metadata=lambda: {
            "stage_id": "fast.scrape_summary",
            "inference_profile": "hybrid",
            "backend_id": "routed-scrape-summary-model",
            "backend_kind": "cloud_api",
            "billing_mode": "api_dollars",
            "routed": True,
            "route_reasons": ["meets_context"],
            "expected_input_tokens": 70_000,
            "expected_output_tokens": 5_000,
        },
    )
    monkeypatch.setattr("primr.ai.stage_routing.resolve_stage_model", lambda *_a, **_k: route)
    monkeypatch.setattr("primr.ai.summarize.llm", lambda *_a, **_k: "fact " * 60)
    monkeypatch.setattr(
        "primr.ai.summarize.stage_routing.capture_stage_usage",
        lambda: {"routed-scrape-summary-model": {"input_tokens": 0}},
    )
    monkeypatch.setattr(
        "primr.ai.summarize.stage_routing.stage_usage_delta",
        lambda _before: {
            "actual_input_tokens": 240,
            "actual_output_tokens": 80,
            "actual_cached_input_tokens": 40,
            "actual_cost_usd": 0.00012,
            "actual_usage_by_model": {
                "routed-scrape-summary-model": {
                    "input_tokens": 240,
                    "output_tokens": 80,
                    "cached_input_tokens": 40,
                    "actual_cost_usd": 0.00012,
                }
            },
        },
    )

    summarize.summarize_scraped_content("Acme", "acme.example", data, str(tmp_path))

    state = json.loads((tmp_path / "_run_state.json").read_text(encoding="utf-8"))
    [record] = state["stage_routes"]
    assert record["outcome"] == "selected"
    assert record["stage_id"] == "fast.scrape_summary"
    assert record["input_items"] == 1
    assert record["output_items"] == 1
    assert record["expected_input_tokens"] == 70_000
    assert record["expected_output_tokens"] == 5_000
    assert record["actual_input_tokens"] == 240
    assert record["actual_output_tokens"] == 80
    assert record["actual_cached_input_tokens"] == 40
    assert record["actual_cost_usd"] == 0.00012
    assert record["actual_usage_by_model"]["routed-scrape-summary-model"]["output_tokens"] == 80
    assert "prompt" not in record
    assert "response" not in record


def test_summarize_scraped_content_agent_unavailable_uses_local_excerpt(monkeypatch, tmp_path):
    data = {
        "https://acme.example/about": (
            "Acme builds secure analytics platforms for regulated teams. " * 40
        )
    }
    route = SimpleNamespace(
        model_name="",
        execution_mode="unavailable",
        log_metadata=lambda: {
            "stage_id": "fast.scrape_summary",
            "inference_profile": "agent",
            "backend_id": "agent-profile-unavailable",
            "backend_kind": "host_agent",
            "billing_mode": "unknown",
            "routed": False,
            "execution_mode": "unavailable",
            "route_reasons": ["agent_profile_unavailable"],
            "expected_input_tokens": 70_000,
            "expected_output_tokens": 5_000,
        },
    )
    llm_mock = MagicMock(side_effect=AssertionError("cloud LLM should not run"))
    usage_mock = MagicMock(side_effect=AssertionError("usage should not be captured"))
    monkeypatch.setattr("primr.ai.stage_routing.resolve_stage_model", lambda *_a, **_k: route)
    monkeypatch.setattr("primr.ai.summarize.llm", llm_mock)
    monkeypatch.setattr(
        "primr.ai.summarize.stage_routing.capture_stage_usage",
        usage_mock,
    )

    summary = summarize.summarize_scraped_content(
        "Acme",
        "https://acme.example",
        data,
        str(tmp_path),
    )

    assert "Deterministic source excerpt" in summary
    assert "secure analytics platforms" in summary
    llm_mock.assert_not_called()
    usage_mock.assert_not_called()
    state = json.loads((tmp_path / "_run_state.json").read_text(encoding="utf-8"))
    [record] = state["stage_routes"]
    assert record["outcome"] == "fallback"
    assert record["backend_id"] == "agent-profile-unavailable"
    assert record["failure_class"] == "agent_profile_unavailable"
    assert record["input_items"] == 1
    assert record["output_items"] == 1
    assert "prompt" not in record
    assert "response" not in record


def test_summarize_scraped_content_local_adapter_gap_records_accurate_failure(
    monkeypatch, tmp_path
):
    data = {"https://acme.example/about": "Acme platform evidence. " * 40}
    route = SimpleNamespace(
        model_name="",
        execution_mode="unavailable",
        reasons=("local_adapter_unavailable", "no_paid_fallback"),
        log_metadata=lambda: {
            "stage_id": "fast.scrape_summary",
            "inference_profile": "local",
            "backend_id": "local-adapter-unavailable",
            "backend_kind": "local",
            "billing_mode": "zero_api_runtime",
            "routed": False,
            "execution_mode": "unavailable",
            "route_reasons": ["local_adapter_unavailable", "no_paid_fallback"],
            "availability": {"available": True, "state": "available"},
            "expected_input_tokens": 70_000,
            "expected_output_tokens": 5_000,
        },
    )
    monkeypatch.setattr("primr.ai.stage_routing.resolve_stage_model", lambda *_a, **_k: route)

    summary = summarize.summarize_scraped_content(
        "Acme",
        "https://acme.example",
        data,
        str(tmp_path),
    )

    assert "Deterministic source excerpt" in summary
    state = json.loads((tmp_path / "_run_state.json").read_text(encoding="utf-8"))
    [record] = state["stage_routes"]
    assert record["failure_class"] == "local_adapter_unavailable"
    assert record["availability"] == {"available": True, "state": "available"}


def test_summarize_scraped_content_records_and_propagates_local_busy(monkeypatch, tmp_path):
    data = {"https://acme.example/about": "Acme platform evidence. " * 40}
    route = SimpleNamespace(
        model_name="local-model",
        execution_mode="llm",
        reasons=("available",),
        log_metadata=lambda: {
            "stage_id": "fast.scrape_summary",
            "inference_profile": "local",
            "backend_id": "local-model",
            "backend_kind": "local",
            "billing_mode": "zero_api_runtime",
            "routed": True,
            "execution_mode": "llm",
            "route_reasons": ["available"],
            "expected_input_tokens": 70_000,
            "expected_output_tokens": 5_000,
        },
    )
    busy_error = LocalCapacityBusyError(reason="local_capacity_timeout_busy")
    busy_error.__cause__ = RuntimeError("private endpoint detail")
    monkeypatch.setattr("primr.ai.stage_routing.resolve_stage_model", lambda *_a, **_k: route)
    monkeypatch.setattr(
        "primr.ai.summarize.stage_routing.capture_stage_usage",
        dict,
    )
    monkeypatch.setattr(
        "primr.ai.summarize.summarize_scraped_content_with_callback",
        MagicMock(side_effect=busy_error),
    )

    with pytest.raises(LocalCapacityBusyError):
        summarize.summarize_scraped_content(
            "Acme",
            "https://acme.example",
            data,
            str(tmp_path),
        )

    state_text = (tmp_path / "_run_state.json").read_text(encoding="utf-8")
    state = json.loads(state_text)
    [record] = state["stage_routes"]
    assert record["failure_class"] == "local_capacity_busy"
    assert record["capacity_failure"]["state"] == "busy"
    assert "private endpoint detail" not in state_text


# ---------------------------------------------------------------------------
# summarize_scraped_content_local
# ---------------------------------------------------------------------------


def test_summarize_scraped_content_local(tmp_path):
    data = {"https://acme.example/a": "Real content about Acme."}

    class _Result:
        text = "local " * 60

    with patch(
        "primr.ai.openai_compatible_client.chat_completion", return_value=_Result()
    ) as mock_chat:
        summarize.summarize_scraped_content_local(
            "Acme",
            "acme.example",
            data,
            str(tmp_path),
            model="local-model",
        )
    assert mock_chat.called
    out_file = tmp_path / "scraped_website_summary.local.txt"
    assert out_file.exists()
