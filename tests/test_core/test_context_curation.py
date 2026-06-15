"""Tests for relevance-ranked section-evidence assembly (context curation).

Deterministic, no LLM/network. Pins the conservative fallbacks (never worse than
plain truncation) and that relevance ranking keeps signal within budget.
"""

from __future__ import annotations

from primr.core.context_curation import rank_corpus_by_relevance


def _page(name: str, body: str) -> str:
    return f"[Page: {name}]\n{body}"


class TestRankCorpusByRelevance:
    def test_corpus_within_budget_is_unchanged(self):
        corpus = _page("home", "short body about widgets")
        assert rank_corpus_by_relevance(corpus, "widgets", 100_000) == corpus

    def test_zero_budget_returns_unchanged(self):
        corpus = "x" * 50
        assert rank_corpus_by_relevance(corpus, "ref", 0) == corpus

    def test_no_page_markers_falls_back_to_truncation(self):
        corpus = "a" * 500  # no [Page:] structure
        out = rank_corpus_by_relevance(corpus, "ref", 100)
        assert out == corpus[:100]

    def test_empty_reference_falls_back_to_truncation(self):
        corpus = "\n\n".join(_page(str(i), "body " * 50) for i in range(5))
        out = rank_corpus_by_relevance(corpus, "", 200)
        assert out == corpus[:200]

    def test_relevant_page_kept_irrelevant_dropped_under_budget(self):
        # Three same-size pages; only the middle one matches the reference terms.
        filler = "lorem ipsum dolor sit amet " * 20
        relevant = "quantum encryption latency throughput " * 20
        corpus = "\n\n".join([_page("a", filler), _page("b", relevant), _page("c", filler)])
        # Budget fits ~one page worth.
        budget = len(_page("b", relevant)) + 10
        out = rank_corpus_by_relevance(corpus, "quantum encryption throughput", budget)
        assert "quantum encryption" in out
        assert len(out) <= budget

    def test_budget_is_respected(self):
        corpus = "\n\n".join(_page(str(i), "alpha beta gamma " * 30) for i in range(10))
        budget = 1_000
        out = rank_corpus_by_relevance(corpus, "alpha beta", budget)
        assert 0 < len(out) <= budget

    def test_oversized_top_block_is_truncated_not_empty(self):
        # Every block exceeds the budget -> return a truncation of the top block.
        big = _page("a", "relevant term " * 500)
        corpus = "\n\n".join([big, _page("b", "noise " * 500)])
        budget = 200
        out = rank_corpus_by_relevance(corpus, "relevant term", budget)
        assert out  # non-empty
        assert len(out) <= budget
