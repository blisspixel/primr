"""Relevance-ranked context assembly for the section-writing stage.

The section writer's evidence subset has been a blind first-N-chars truncation of
the scraped corpus, shared across all sections. This ranks the corpus's
``[Page: ...]`` blocks by relevance to a reference text (the analysis workbook,
which already distilled the run's key themes) and keeps the most-relevant blocks
up to a character budget, so the budget is spent on signal rather than on scrape
order.

This is context *assembly* — a relevance rank, deterministic and dependency-free
— not a content gate (it never judges quality or blocks shipping). Its effect on
the brief is validated by eval, not asserted (see docs/design/eval-plan.md
Eval 4). It stays *shared* across sections, preserving the cached prompt prefix
from roadmap #8; per-section routing is a separate, eval-gated step.
"""

from __future__ import annotations

import re
from collections import Counter

# Corpus blocks are "\n\n"-separated and page blocks start with "[Page:" (the
# same shape fast_run_gaps / the analysis prompt rely on).
_PAGE_SPLIT = re.compile(r"\n\n(?=\[Page:)")
_WORD = re.compile(r"[a-z0-9]{3,}")  # 3+ char tokens, lowercased

# Cheap stoplist (no nltk dependency): high-frequency words that carry no
# relevance signal, plus a few corpus-generic terms.
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "were",
        "has",
        "have",
        "will",
        "its",
        "their",
        "our",
        "you",
        "your",
        "can",
        "not",
        "but",
        "all",
        "any",
        "into",
        "more",
        "than",
        "other",
        "such",
        "may",
        "also",
        "which",
        "who",
        "what",
        "when",
        "where",
        "they",
        "them",
        "been",
        "would",
        "company",
        "business",
        "services",
        "service",
        "products",
        "product",
        "page",
        "home",
        "about",
    }
)


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


def rank_corpus_by_relevance(raw_corpus: str, reference_text: str, budget_chars: int) -> str:
    """Return the most relevant slice of ``raw_corpus`` within ``budget_chars``.

    Splits the corpus into ``[Page: ...]`` blocks, scores each by term overlap
    with ``reference_text``, and concatenates the highest-scoring blocks (most
    relevant first) until the budget is reached.

    Conservative fallbacks (never raise, never return empty for non-empty input):
    - corpus already within budget -> returned unchanged (no reordering), so small
      runs are byte-identical;
    - no ``[Page:]`` structure, or an empty reference -> plain leading truncation
      (the prior behavior), so we never do worse than before.
    """
    if budget_chars <= 0 or len(raw_corpus) <= budget_chars:
        return raw_corpus

    blocks = [b for b in _PAGE_SPLIT.split(raw_corpus) if b.strip()]
    if len(blocks) <= 1:
        return raw_corpus[:budget_chars]

    ref = Counter(_tokens(reference_text))
    if not ref:
        return raw_corpus[:budget_chars]

    def score(block: str) -> float:
        toks = _tokens(block)
        if not toks:
            return 0.0
        # Sum reference frequencies for the block's distinct terms, normalized by
        # sqrt(length) so a long page can't dominate on raw count alone.
        hit = sum(ref[t] for t in set(toks) if t in ref)
        return hit / (len(toks) ** 0.5)

    ranked = sorted(blocks, key=score, reverse=True)

    out: list[str] = []
    used = 0
    for block in ranked:
        cost = len(block) + 2  # the "\n\n" join
        if used + cost > budget_chars:
            continue  # skip; a smaller later block may still fit
        out.append(block)
        used += cost
    if not out:  # every block individually exceeds the budget -> truncate the top
        return ranked[0][:budget_chars]
    return "\n\n".join(out)
