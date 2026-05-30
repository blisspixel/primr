"""Coverage tests for primr.ai.summarize.

Targets generate_prompt validation, page preparation/clamping, batch packing,
the retry/short-response callback loop, the empty-page formatting branch,
summarize_with_retries, and the local-backend variant. All LLM calls mocked.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from primr.ai import summarize

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
    out = summarize._summarize_with_callback(
        "content",
        summarize_fn=lambda c, m: "short",
        retries=2,
        min_length=200,
    )
    # Below min_length on every attempt, but non-empty -> returned anyway.
    with patch("primr.ai.summarize.time.sleep"):
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


# ---------------------------------------------------------------------------
# _summarize_page empty-content branch
# ---------------------------------------------------------------------------


def test_summarize_page_no_content_branch():
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
    with patch(
        "primr.ai.summarize._invoke_default_summary_model",
        return_value="fact " * 60,
    ) as mock_fn:
        summarize.summarize_scraped_content("Acme", "acme.example", data, str(tmp_path))
    # Only the non-blank page is summarized.
    assert mock_fn.call_count == 1


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
