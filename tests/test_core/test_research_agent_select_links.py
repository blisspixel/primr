"""Tests for select_links_with_llm, _validate_scrape_quality, format_tier_stats."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from primr.core.research_agent import (
    _validate_scrape_quality,
    format_tier_stats,
    select_links_with_llm,
)
from primr.utils.model_policy import disable_model_calls


def _link(url: str, anchor: str | None = None):
    return SimpleNamespace(url=url, anchor_text=anchor) if anchor else SimpleNamespace(url=url)


class TestValidateScrapeQuality:
    def test_passes_with_sufficient_content(self):
        corpus = {f"https://x{i}.example": "x" * 2000 for i in range(5)}
        ok, _ = _validate_scrape_quality(corpus, min_pages=3, min_chars=5000)
        assert ok is True

    def test_fails_when_too_few_pages(self):
        corpus = {"https://x.example": "x" * 50000}
        ok, reason = _validate_scrape_quality(corpus, min_pages=5, min_chars=100)
        assert ok is False
        assert "pages" in reason

    def test_fails_when_too_few_chars(self):
        corpus = {f"https://x{i}.example": "tiny" for i in range(20)}
        ok, _ = _validate_scrape_quality(corpus, min_pages=3, min_chars=100000)
        assert ok is False

    def test_handles_none_values(self):
        corpus = {"https://x.example": None, "https://y.example": None}
        ok, _ = _validate_scrape_quality(corpus, min_pages=1, min_chars=1)
        assert ok is False  # None becomes 0 chars

    def test_empty_corpus(self):
        ok, reason = _validate_scrape_quality({})
        assert ok is False
        assert "0 pages" in reason


class TestFormatTierStats:
    def test_single_tier(self):
        result = format_tier_stats({"playwright": 5})
        assert "5 browser" in result

    def test_multiple_tiers_sorted_descending(self):
        result = format_tier_stats({"requests": 2, "playwright": 10, "httpx": 5})
        # Tiers should be sorted by count descending
        assert result.index("10 browser") < result.index("5 HTTP/2")
        assert result.index("5 HTTP/2") < result.index("2 HTTP")

    def test_unknown_tier_uses_raw_name(self):
        result = format_tier_stats({"weird_tier": 1})
        assert "1 weird_tier" in result

    def test_empty_returns_empty(self):
        assert format_tier_stats({}) == ""


class TestSelectLinksWithLLM:
    def test_returns_empty_for_empty_links(self):
        assert select_links_with_llm([], "Acme", "https://acme.example") == []

    def test_returns_all_when_under_max(self):
        links = [_link(f"https://a.example/{i}") for i in range(5)]
        result = select_links_with_llm(links, "Acme", "https://acme.example", max_links=10)
        assert len(result) == 5

    def test_no_model_policy_uses_bounded_heuristic_selection(self, monkeypatch):
        links = [_link(f"https://a.example/{i}") for i in range(100)]
        llm_mock = MagicMock(side_effect=AssertionError("model call attempted"))
        monkeypatch.setattr("primr.core.research_agent.llm", llm_mock)

        with disable_model_calls():
            result = select_links_with_llm(
                links,
                "Acme",
                "https://acme.example",
                max_links=12,
            )

        assert result == [f"https://a.example/{i}" for i in range(12)]
        llm_mock.assert_not_called()

    def test_llm_returns_valid_subset(self, monkeypatch):
        links = [_link(f"https://a.example/{i}") for i in range(100)]
        llm_response = "\n".join(f"https://a.example/{i}" for i in range(10))
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value=llm_response),
        )
        result = select_links_with_llm(links, "Acme", "https://acme.example", max_links=50)
        assert len(result) == 10
        assert all(u.startswith("https://a.example/") for u in result)

    def test_llm_filters_hallucinated_urls(self, monkeypatch):
        links = [_link(f"https://a.example/{i}") for i in range(100)]
        # Half valid, half hallucinated
        llm_response = (
            "\n".join(f"https://a.example/{i}" for i in range(5))
            + "\nhttps://hallucinated.example/x\nhttps://hallucinated.example/y"
        )
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value=llm_response),
        )
        result = select_links_with_llm(links, "Acme", "https://acme.example")
        assert len(result) == 5
        assert not any("hallucinated" in u for u in result)

    def test_falls_back_when_llm_fails(self, monkeypatch):
        links = [_link(f"https://a.example/{i}") for i in range(100)]
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(side_effect=RuntimeError("llm down")),
        )
        result = select_links_with_llm(links, "Acme", "https://acme.example", max_links=30)
        # Should fall back to first 30 by heuristic
        assert len(result) == 30

    def test_falls_back_when_llm_returns_only_invalid(self, monkeypatch):
        links = [_link(f"https://a.example/{i}") for i in range(100)]
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value="garbage\nmore garbage\n"),
        )
        result = select_links_with_llm(links, "Acme", "https://acme.example", max_links=20)
        # No valid URLs from LLM -> fallback
        assert len(result) == 20

    def test_anchor_text_included_in_prompt(self, monkeypatch):
        links = [_link(f"https://a.example/{i}", f"anchor {i}") for i in range(100)]
        llm_mock = MagicMock(return_value="https://a.example/0\n")
        monkeypatch.setattr("primr.core.research_agent.llm", llm_mock)
        select_links_with_llm(links, "Acme", "https://acme.example")
        # Prompt should include anchor texts
        prompt = llm_mock.call_args.args[0]
        assert "anchor 0" in prompt
