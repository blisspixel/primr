"""
Additional coverage for AnalystSubagent.

These tests exercise the analyst's full execute() lifecycle, the insight
generation paths (file corpus, directory corpus, ImportError fallback, and
the summarize delegation), topic/finding extraction branches, and the
SubagentError propagation path. The summarize pipeline is mocked so no
network/LLM calls happen.

Validates: insight synthesis + hypothesis generation logic.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import types
from pathlib import Path

import pytest

from primr.agentic.errors import SubagentError
from primr.agentic.models import ConfidenceLevel, Hypothesis
from primr.agentic.subagents.analyst import AnalysisResult, AnalystSubagent
from primr.agentic.subagents.base import (
    SubagentContext,
    SubagentStatus,
)


def _context(working_dir: Path, **parent) -> SubagentContext:
    return SubagentContext(
        company_name="Acme Corp",
        company_url="https://acme.example",
        working_dir=working_dir,
        parent_results=parent,
    )


# =============================================================================
# AnalysisResult helpers
# =============================================================================


def test_analysis_result_hypothesis_count_and_to_dict():
    with tempfile.TemporaryDirectory() as tmp:
        h = Hypothesis(id="h_1", claim="Uses cloud", confidence=ConfidenceLevel.UNTESTED)
        result = AnalysisResult(
            insights_path=Path(tmp) / "insights.txt",
            hypotheses=[h],
            confidence_scores={"h_1": 0.7},
            topics_identified=["technology"],
            key_findings=["Strong cloud adoption"],
        )

        assert result.hypothesis_count == 1
        assert result.average_confidence == 0.7

        data = result.to_dict()
        assert data["hypothesis_count"] == 1
        assert data["average_confidence"] == 0.7
        assert data["topics_identified"] == ["technology"]
        assert len(data["hypotheses"]) == 1


def test_analysis_result_average_confidence_empty():
    with tempfile.TemporaryDirectory() as tmp:
        result = AnalysisResult(insights_path=Path(tmp) / "x.txt")
        assert result.average_confidence == 0.0


# =============================================================================
# hypothesis_expiry_days property + get_required_tools
# =============================================================================


def test_hypothesis_expiry_days_property_and_required_tools():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)), hypothesis_expiry_days=30)
        assert analyst.hypothesis_expiry_days == 30
        assert analyst.get_required_tools() == []


# =============================================================================
# _classify_topic branches
# =============================================================================


def test_classify_topic_all_categories():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)))

        assert analyst._classify_topic("Built on a cloud platform with an API") == "technology"
        assert analyst._classify_topic("Strong revenue growth and funding") == "financials"
        assert analyst._classify_topic("The CEO and founder lead the board") == "leadership"
        assert analyst._classify_topic("New product launch this quarter") == "products"
        assert analyst._classify_topic("A mission-driven culture with strong values") == "culture"
        assert analyst._classify_topic("Something entirely unrelated zzz") == "general"


# =============================================================================
# _generate_hypotheses branches
# =============================================================================


def test_generate_hypotheses_from_claims():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)))
        hyps = analyst._generate_hypotheses({"claims": ["Uses cloud platform", "  ", ""]})

        # Empty/whitespace claims are filtered out.
        assert len(hyps) == 1
        assert hyps[0].claim == "Uses cloud platform"
        assert hyps[0].confidence == ConfidenceLevel.UNTESTED
        assert hyps[0].topic == "technology"
        assert hyps[0].expires_at is not None


def test_generate_hypotheses_falls_back_to_key_points():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)))
        # No "claims" key -> falls back to "key_points".
        hyps = analyst._generate_hypotheses({"key_points": ["Revenue grew 20%"]})
        assert len(hyps) == 1
        assert hyps[0].topic == "financials"


def test_generate_hypotheses_skips_non_strings():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)))
        hyps = analyst._generate_hypotheses({"claims": [123, None, "Valid claim text here"]})
        assert len(hyps) == 1
        assert hyps[0].claim == "Valid claim text here"


# =============================================================================
# _score_confidence branches
# =============================================================================


def test_score_confidence_rewards_evidence_topic_and_length():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)))

        rich = Hypothesis(
            id="rich",
            claim="A moderately sized claim about cloud platform usage and growth",
            confidence=ConfidenceLevel.UNTESTED,
            topic="technology",
            evidence=["e1", "e2", "e3", "e4", "e5"],  # caps at +0.3
        )
        plain = Hypothesis(
            id="plain",
            claim="x",  # too short, general topic, no evidence
            confidence=ConfidenceLevel.UNTESTED,
            topic="general",
        )

        scores = analyst._score_confidence([rich, plain])
        # rich: 0.5 + 0.3 (evidence cap) + 0.1 (topic) + 0.1 (length) = 1.0
        assert scores["rich"] == 1.0
        # plain: just base 0.5
        assert scores["plain"] == 0.5
        assert all(0.0 <= s <= 1.0 for s in scores.values())


# =============================================================================
# _extract_topics / _extract_key_findings branches
# =============================================================================


def test_extract_topics_combines_explicit_and_claim_derived():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)))
        topics = analyst._extract_topics(
            {
                "topics": ["custom"],
                "claims": ["Revenue grew strongly", "no topic match here zzz"],
            }
        )
        # "custom" explicit + "financials" derived; "general" excluded
        assert "custom" in topics
        assert "financials" in topics
        assert "general" not in topics
        assert topics == sorted(topics)


def test_extract_key_findings_from_findings_key():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)))
        findings = analyst._extract_key_findings({"key_findings": ["a", "b", "", None, "c"]})
        # Falsy items filtered.
        assert findings == ["a", "b", "c"]


def test_extract_key_findings_falls_back_to_summary_and_coerces_string():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)))
        # No key_findings -> summary; string summary becomes single-element list.
        findings = analyst._extract_key_findings({"summary": "Single summary line"})
        assert findings == ["Single summary line"]


def test_extract_key_findings_limits_to_ten():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)))
        findings = analyst._extract_key_findings(
            {"key_findings": [f"finding {i}" for i in range(20)]}
        )
        assert len(findings) == 10


# =============================================================================
# _generate_insights paths (summarize mocked)
# =============================================================================


def _install_fake_summarize(monkeypatch, written_lines):
    """Install a fake primr.ai.summarize module that writes a summary file."""

    fake_module = types.ModuleType("primr.ai.summarize")

    def summarize_scraped_content(company_name, company_website, scraped_data, folder_path):
        out = Path(folder_path) / "scraped_website_summary.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(written_lines), encoding="utf-8")

    fake_module.summarize_scraped_content = summarize_scraped_content  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "primr.ai.summarize", fake_module)


def test_generate_insights_file_corpus(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        corpus = working / "corpus.txt"
        corpus.write_text("Acme builds cloud software.", encoding="utf-8")

        _install_fake_summarize(
            monkeypatch,
            ["Header line", "- First claim about cloud", "- Second claim about growth", "plain"],
        )

        analyst = AnalystSubagent(_context(working, corpus_path=corpus))
        path, data = asyncio.run(analyst._generate_insights(corpus))

        assert path == working / "scraped_website_summary.txt"
        assert data["claims"] == ["First claim about cloud", "Second claim about growth"]


def test_generate_insights_dir_corpus(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        corpus_dir = working / "corpus"
        corpus_dir.mkdir()
        (corpus_dir / "page1.txt").write_text("content one", encoding="utf-8")
        (corpus_dir / "page2.txt").write_text("content two", encoding="utf-8")

        _install_fake_summarize(monkeypatch, ["- Only claim"])

        analyst = AnalystSubagent(_context(working, corpus_path=corpus_dir))
        path, data = asyncio.run(analyst._generate_insights(corpus_dir))

        assert path.exists()
        assert data["claims"] == ["Only claim"]


def test_generate_insights_missing_summary_file(monkeypatch):
    """When summarize writes nothing, insights_data has no claims."""
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        corpus = working / "corpus.txt"
        corpus.write_text("data", encoding="utf-8")

        fake_module = types.ModuleType("primr.ai.summarize")
        fake_module.summarize_scraped_content = (  # type: ignore[attr-defined]
            lambda **kwargs: None
        )
        monkeypatch.setitem(sys.modules, "primr.ai.summarize", fake_module)

        analyst = AnalystSubagent(_context(working, corpus_path=corpus))
        path, data = asyncio.run(analyst._generate_insights(corpus))

        assert path == working / "scraped_website_summary.txt"
        assert data == {}


def test_generate_insights_nonexistent_corpus_path(monkeypatch):
    """A corpus path that is neither file nor dir -> empty scraped_data."""
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        missing = working / "does_not_exist.txt"

        _install_fake_summarize(monkeypatch, ["- A claim"])

        analyst = AnalystSubagent(_context(working, corpus_path=missing))
        path, data = asyncio.run(analyst._generate_insights(missing))

        assert path.exists()
        assert data["claims"] == ["A claim"]


def test_generate_insights_import_error_fallback(monkeypatch):
    """ImportError on summarize -> mock insights file is written."""
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        corpus = working / "corpus.txt"
        corpus.write_text("data", encoding="utf-8")

        # Force the import inside _generate_insights to fail.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "primr.ai.summarize":
                raise ImportError("not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        analyst = AnalystSubagent(_context(working, corpus_path=corpus))
        path, data = asyncio.run(analyst._generate_insights(corpus))

        assert path == working / "insights.md"
        assert path.exists()
        assert data == {}
        assert "Acme Corp" in path.read_text(encoding="utf-8")


# =============================================================================
# execute() lifecycle
# =============================================================================


def test_execute_success(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        corpus = working / "corpus.txt"
        corpus.write_text("Acme builds cloud software.", encoding="utf-8")

        _install_fake_summarize(
            monkeypatch,
            ["- Acme uses a cloud platform and API", "- Revenue grew strongly this year"],
        )

        analyst = AnalystSubagent(_context(working, corpus_path=corpus))
        result = asyncio.run(analyst.execute())

        assert result.is_success
        assert result.status == SubagentStatus.COMPLETED
        assert len(result.hypotheses) == 2
        assert result.data is not None
        assert result.data.hypothesis_count == 2
        assert "technology" in result.data.topics_identified
        assert result.get_metric("hypothesis_count") == 2.0
        assert analyst.status == SubagentStatus.COMPLETED


def test_execute_accepts_string_corpus_path(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        corpus = working / "corpus.txt"
        corpus.write_text("data", encoding="utf-8")

        _install_fake_summarize(monkeypatch, ["- Single claim"])

        # Pass corpus_path as a string to exercise the str->Path coercion.
        analyst = AnalystSubagent(_context(working, corpus_path=str(corpus)))
        result = asyncio.run(analyst.execute())

        assert result.is_success


def test_execute_missing_corpus_raises_subagent_error():
    with tempfile.TemporaryDirectory() as tmp:
        analyst = AnalystSubagent(_context(Path(tmp)))  # no corpus_path
        with pytest.raises(SubagentError):
            asyncio.run(analyst.execute())


def test_execute_unexpected_error_returns_failed_result(monkeypatch):
    """A non-SubagentError raised during analysis yields a FAILED result."""
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        corpus = working / "corpus.txt"
        corpus.write_text("data", encoding="utf-8")

        analyst = AnalystSubagent(_context(working, corpus_path=corpus))

        async def boom(_corpus_path):
            raise RuntimeError("synthesis exploded")

        monkeypatch.setattr(analyst, "_generate_insights", boom)

        result = asyncio.run(analyst.execute())

        assert result.is_failure
        assert result.status == SubagentStatus.FAILED
        assert "synthesis exploded" in (result.error or "")
        assert result.get_metric("duration_seconds") >= 0.0
        assert analyst.status == SubagentStatus.FAILED
