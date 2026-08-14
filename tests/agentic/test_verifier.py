"""
Tests for VerifierSubagent claim verification pipeline.

Covers: data structures, trust score math, serialization round-trips,
claim extraction parsing, search parallelism, classification, prompt loading,
JSON save, end-to-end pipeline with mocked LLM, VerificationGateHook,
orchestrator integration, and cost estimator integration.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.primr.agentic.subagents.base import SubagentContext
from src.primr.agentic.subagents.verifier import (
    ClaimVerification,
    VerifiableClaim,
    VerificationResult,
    VerifierSubagent,
)

# =============================================================================
# Helpers
# =============================================================================


@pytest.fixture(autouse=True)
def _no_network_evidence_fetch(monkeypatch):
    """Kill real HTTP in the evidence-fetch step for every test in this file.

    The classifier now fetches page content for each search hit; unit tests
    must never reach the network. Default stub: every URL fetches
    successfully with generic third-party-looking content. Tests that need
    specific evidence override via `primr.data.fallback_sources._http_get`.
    """

    def fake_http_get(url, timeout=15.0, headers=None, params=None):
        return 200, b"<html><body><p>stub evidence content for tests</p></body></html>", url

    monkeypatch.setattr("primr.data.fallback_sources._http_get", fake_http_get)


def _write_report(content: str) -> Path:
    """Write content to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    )
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


def _make_context(report_path: Path, company_name: str = "TestCo") -> SubagentContext:
    """Build a minimal SubagentContext pointing at a report file."""
    return SubagentContext(
        company_name=company_name,
        company_url="https://testco.com",
        working_dir=report_path.parent,
        parent_results={"report_path": report_path},
    )


def _make_verifier(content: str = "test", **kwargs) -> tuple[VerifierSubagent, Path]:
    """Shortcut: write a report and return (verifier, report_path)."""
    path = _write_report(content)
    ctx = _make_context(path, company_name=kwargs.pop("company_name", "TestCo"))
    return VerifierSubagent(ctx, **kwargs), path


SAMPLE_REPORT = (
    "# Strategic Overview: TestCo\n"
    "## Executive Summary\n"
    "TestCo generated $50M in revenue in 2025. (Confirmed)\n"
    "They have 500 employees across 3 offices. (Reported)\n"
    "## Key Insights\n"
    "TestCo uses AWS for cloud infrastructure. (Confirmed)\n"
    "They are considering a partnership with Acme Inc. (Hypothesis)\n"
    "## Sources\n"
    "https://testco.com/about\n"
)


# =============================================================================
# VerificationResult tests
# =============================================================================


class TestVerificationResult:
    """Tests for VerificationResult data class."""

    def test_trust_score_basic(self):
        result = VerificationResult(
            trust_score=0.75,
            verified_count=3,
            unverified_count=1,
            contradicted_count=0,
        )
        assert result.trust_percentage == 75
        assert result.total_claims == 4

    def test_trust_score_zero_claims(self):
        result = VerificationResult(trust_score=0.0)
        assert result.total_claims == 0
        assert result.trust_percentage == 0

    def test_trust_score_perfect(self):
        result = VerificationResult(trust_score=1.0, verified_count=5)
        assert result.trust_percentage == 100

    def test_trust_score_boundary_rounding(self):
        """trust_percentage should truncate, not round."""
        result = VerificationResult(trust_score=0.999)
        assert result.trust_percentage == 99  # int(0.999 * 100) = 99

    def test_trust_score_near_zero(self):
        result = VerificationResult(trust_score=0.004)
        assert result.trust_percentage == 0  # int(0.4) = 0

    def test_counts_sum_correctly(self):
        result = VerificationResult(
            trust_score=0.5,
            verified_count=2,
            unverified_count=1,
            contradicted_count=1,
        )
        total = result.verified_count + result.unverified_count + result.contradicted_count
        assert result.total_claims == total

    def test_serialization_round_trip(self):
        """to_dict should produce JSON-serializable output that preserves all fields."""
        claim = VerifiableClaim("Revenue was $50M", "Executive Summary", 5)
        cv = ClaimVerification(
            claim=claim,
            status="verified",
            supporting_sources=["https://example.com"],
            explanation="Confirmed by annual report",
            search_query="TestCo revenue",
        )
        result = VerificationResult(
            trust_score=0.8,
            verified_count=4,
            unverified_count=1,
            contradicted_count=0,
            claim_results=[cv],
            duration_seconds=30.567,
        )
        d = result.to_dict()

        # Verify it's JSON-serializable
        roundtripped = json.loads(json.dumps(d))
        assert roundtripped["trust_score"] == 0.8
        assert roundtripped["trust_percentage"] == 80
        assert roundtripped["total_claims"] == 5
        assert roundtripped["duration_seconds"] == 30.6  # rounded to 1dp
        assert len(roundtripped["claim_results"]) == 1

        cr = roundtripped["claim_results"][0]
        assert cr["claim_text"] == "Revenue was $50M"
        assert cr["section"] == "Executive Summary"
        assert cr["importance"] == 5
        assert cr["status"] == "verified"
        assert cr["supporting_sources"] == ["https://example.com"]
        assert cr["explanation"] == "Confirmed by annual report"
        assert cr["search_query"] == "TestCo revenue"

    def test_empty_claim_results_serialization(self):
        result = VerificationResult(trust_score=0.0)
        d = result.to_dict()
        assert d["claim_results"] == []
        assert d["total_claims"] == 0


# =============================================================================
# VerifiableClaim tests
# =============================================================================


class TestVerifiableClaim:
    def test_to_dict(self):
        claim = VerifiableClaim("Has 500 employees", "Summary", 4)
        d = claim.to_dict()
        assert d == {"claim_text": "Has 500 employees", "section": "Summary", "importance": 4}

    def test_to_dict_preserves_all_fields(self):
        claim = VerifiableClaim("claim", "sec", 1)
        d = claim.to_dict()
        assert set(d.keys()) == {"claim_text", "section", "importance"}


# =============================================================================
# ClaimVerification tests
# =============================================================================


class TestClaimVerification:
    def test_to_dict_includes_claim_fields(self):
        claim = VerifiableClaim("Revenue is $10M", "Summary", 5)
        cv = ClaimVerification(
            claim=claim,
            status="contradicted",
            supporting_sources=["https://a.com", "https://b.com"],
            explanation="Sources show $5M",
            search_query="TestCo revenue 10M",
        )
        d = cv.to_dict()
        assert d["claim_text"] == "Revenue is $10M"
        assert d["status"] == "contradicted"
        assert len(d["supporting_sources"]) == 2
        assert d["search_query"] == "TestCo revenue 10M"

    def test_to_dict_defaults(self):
        claim = VerifiableClaim("test", "S", 3)
        cv = ClaimVerification(claim=claim, status="unverified")
        d = cv.to_dict()
        assert d["supporting_sources"] == []
        assert d["explanation"] == ""
        assert d["search_query"] == ""


# =============================================================================
# VerifierSubagent — execute() edge cases
# =============================================================================


class TestVerifierSubagent:
    """Tests for VerifierSubagent execution."""

    def test_no_report_path_raises(self):
        """Missing report_path should raise SubagentError."""
        from primr.agentic.errors import SubagentError

        context = SubagentContext(
            company_name="TestCo",
            company_url="https://testco.com",
            working_dir=Path(tempfile.mkdtemp()),
            parent_results={},
        )
        verifier = VerifierSubagent(context)
        with pytest.raises(SubagentError, match="No report_path"):
            asyncio.run(verifier.execute())

    def test_nonexistent_report_raises(self):
        """Nonexistent report path should raise SubagentError."""
        from primr.agentic.errors import SubagentError

        context = SubagentContext(
            company_name="TestCo",
            company_url="https://testco.com",
            working_dir=Path(tempfile.mkdtemp()),
            parent_results={"report_path": Path("/nonexistent/report.txt")},
        )
        verifier = VerifierSubagent(context)
        with pytest.raises(SubagentError, match="not found"):
            asyncio.run(verifier.execute())

    def test_empty_report_returns_zero_trust(self):
        """Empty report text should return 0 claims, 0 trust score."""
        report_path = _write_report("")
        context = _make_context(report_path)
        verifier = VerifierSubagent(context)
        result = asyncio.run(verifier.execute())
        assert result.is_success
        assert result.status.value == "completed"
        assert result.data.trust_score == 0.0
        assert result.data.total_claims == 0
        assert result.metrics["claims_extracted"] == 0

    def test_whitespace_only_report_returns_zero_trust(self):
        """Whitespace-only report should be treated as empty."""
        report_path = _write_report("   \n\n\t  ")
        context = _make_context(report_path)
        verifier = VerifierSubagent(context)
        result = asyncio.run(verifier.execute())
        assert result.is_success
        assert result.data.total_claims == 0

    def test_report_path_as_string(self):
        """report_path provided as string should be auto-converted to Path."""
        report_path = _write_report("")
        context = SubagentContext(
            company_name="TestCo",
            company_url="https://testco.com",
            working_dir=report_path.parent,
            parent_results={"report_path": str(report_path)},  # string, not Path
        )
        verifier = VerifierSubagent(context)
        result = asyncio.run(verifier.execute())
        assert result.is_success

    def test_max_claims_property(self):
        verifier, _ = _make_verifier(max_claims=10)
        assert verifier.max_claims == 10

    def test_default_max_claims(self):
        verifier, _ = _make_verifier()
        assert verifier.max_claims == 20

    def test_get_required_tools_empty(self):
        verifier, _ = _make_verifier()
        assert verifier.get_required_tools() == []

    def test_name_is_set(self):
        verifier, _ = _make_verifier()
        assert verifier.name == "VerifierSubagent"

    def test_general_exception_returns_failed_result(self):
        """Non-SubagentError exceptions should return FAILED result, not raise."""
        report_path = _write_report(SAMPLE_REPORT)
        context = _make_context(report_path)
        verifier = VerifierSubagent(context)

        # Make _extract_claims raise a non-SubagentError
        with patch.object(verifier, "_extract_claims", side_effect=ValueError("boom")):
            result = asyncio.run(verifier.execute())
            assert result.is_failure
            assert result.status.value == "failed"
            assert "boom" in result.error
            assert result.metrics["duration_seconds"] > 0


# =============================================================================
# Claim extraction parsing
# =============================================================================


class TestClaimExtraction:
    """Tests for JSON parsing and claim extraction logic."""

    def test_parse_json_response_plain(self):
        verifier, _ = _make_verifier()
        response = '[{"claim_text": "Revenue was $50M", "section": "Summary", "importance": 5}]'
        result = verifier._parse_json_response(response)
        assert len(result) == 1
        assert result[0]["claim_text"] == "Revenue was $50M"

    def test_parse_json_response_with_markdown_fencing(self):
        verifier, _ = _make_verifier()
        response = '```json\n[{"claim_text": "test", "section": "S", "importance": 3}]\n```'
        result = verifier._parse_json_response(response)
        assert len(result) == 1

    def test_parse_json_response_bare_fencing(self):
        """Markdown fence without 'json' language tag."""
        verifier, _ = _make_verifier()
        response = '```\n[{"a": 1}]\n```'
        result = verifier._parse_json_response(response)
        assert result == [{"a": 1}]

    def test_parse_json_invalid_raises(self):
        verifier, _ = _make_verifier()
        with pytest.raises(json.JSONDecodeError):
            verifier._parse_json_response("not valid json at all")

    def test_max_claims_cap(self):
        """Claims should be capped at max_claims."""
        verifier, _ = _make_verifier(max_claims=3)
        claims_json = json.dumps(
            [
                {"claim_text": f"Claim {i}", "section": "S", "importance": i % 5 + 1}
                for i in range(10)
            ]
        )

        import primr.ai.llm as llm_mod

        with patch.object(llm_mod, "llm", return_value=claims_json):
            claims = asyncio.run(verifier._extract_claims("some report text"))
            assert len(claims) <= 3

    def test_priority_ordering(self):
        """Claims should be sorted by importance (highest first)."""
        verifier, _ = _make_verifier()
        claims_json = json.dumps(
            [
                {"claim_text": "Low", "section": "S", "importance": 1},
                {"claim_text": "High", "section": "S", "importance": 5},
                {"claim_text": "Mid", "section": "S", "importance": 3},
            ]
        )

        import primr.ai.llm as llm_mod

        with patch.object(llm_mod, "llm", return_value=claims_json):
            claims = asyncio.run(verifier._extract_claims("some report text"))
            assert claims[0].importance == 5
            assert claims[1].importance == 3
            assert claims[2].importance == 1

    def test_importance_clamped_to_1_5(self):
        """Importance values outside 1-5 should be clamped."""
        verifier, _ = _make_verifier()
        claims_json = json.dumps(
            [
                {"claim_text": "A", "section": "S", "importance": 0},
                {"claim_text": "B", "section": "S", "importance": 99},
                {"claim_text": "C", "section": "S", "importance": -5},
            ]
        )

        import primr.ai.llm as llm_mod

        with patch.object(llm_mod, "llm", return_value=claims_json):
            claims = asyncio.run(verifier._extract_claims("text"))
            importances = {c.claim_text: c.importance for c in claims}
            assert importances["A"] == 1  # clamped from 0
            assert importances["B"] == 5  # clamped from 99
            assert importances["C"] == 1  # clamped from -5

    def test_non_dict_items_skipped(self):
        """Non-dict items in the LLM response array should be silently skipped."""
        verifier, _ = _make_verifier()
        claims_json = json.dumps(
            [
                {"claim_text": "Valid", "section": "S", "importance": 3},
                "not a dict",
                42,
                None,
            ]
        )

        import primr.ai.llm as llm_mod

        with patch.object(llm_mod, "llm", return_value=claims_json):
            claims = asyncio.run(verifier._extract_claims("text"))
            assert len(claims) == 1
            assert claims[0].claim_text == "Valid"

    def test_non_list_response_is_extraction_failure(self):
        """A malformed extraction response must not look like zero claims."""
        verifier, _ = _make_verifier()

        import primr.ai.llm as llm_mod

        with (
            patch.object(llm_mod, "llm", return_value='{"not": "a list"}'),
            pytest.raises(RuntimeError, match="non-list"),
        ):
            asyncio.run(verifier._extract_claims("text"))

    def test_llm_exception_is_extraction_failure(self):
        """LLM failure must not be reclassified as a claim-free report."""
        verifier, _ = _make_verifier()

        import primr.ai.llm as llm_mod

        with (
            patch.object(llm_mod, "llm", side_effect=RuntimeError("API down")),
            pytest.raises(RuntimeError, match="API down"),
        ):
            asyncio.run(verifier._extract_claims("text"))

    def test_long_report_sampling_covers_late_sections(self):
        verifier, _ = _make_verifier()
        report = "\n".join(
            f"## Section {index}\n" + (f"fact-{index} " * 500) for index in range(12)
        )

        sampled = verifier._sample_report_sections(report, max_chars=6_000)

        assert len(sampled) <= 6_000
        assert "## Section 0" in sampled
        assert "## Section 11" in sampled
        assert "fact-11" in sampled

    def test_missing_fields_use_defaults(self):
        """Claims with missing fields should use sensible defaults."""
        verifier, _ = _make_verifier()
        claims_json = json.dumps(
            [
                {"claim_text": "Only text"},  # no section, no importance
            ]
        )

        import primr.ai.llm as llm_mod

        with patch.object(llm_mod, "llm", return_value=claims_json):
            claims = asyncio.run(verifier._extract_claims("text"))
            assert len(claims) == 1
            assert claims[0].section == "unknown"
            assert claims[0].importance == 3  # default


# =============================================================================
# Search query building
# =============================================================================


class TestSearchQueryBuilding:
    def test_builds_queries_with_company_name(self):
        verifier, _ = _make_verifier()
        claims = [VerifiableClaim("Revenue was $50M in 2025", "Summary", 5)]
        queries = verifier._build_search_queries(claims)
        assert len(queries) == 1
        _, query = queries[0]
        assert "TestCo" in query
        assert "Revenue" in query

    def test_long_claim_truncated_in_query(self):
        """Claims longer than 60 chars should be truncated in the query."""
        verifier, _ = _make_verifier()
        long_claim = "A" * 100
        claims = [VerifiableClaim(long_claim, "S", 3)]
        queries = verifier._build_search_queries(claims)
        _, query = queries[0]
        # Should be "TestCo " + first 60 chars (no trailing punctuation)
        assert len(query) < len("TestCo " + long_claim)

    def test_trailing_punctuation_stripped(self):
        verifier, _ = _make_verifier()
        claims = [VerifiableClaim("Revenue was $50M.", "S", 3)]
        queries = verifier._build_search_queries(claims)
        _, query = queries[0]
        assert not query.endswith(".")

    def test_empty_claims_empty_queries(self):
        verifier, _ = _make_verifier()
        queries = verifier._build_search_queries([])
        assert queries == []

    def test_multiple_claims_produce_multiple_queries(self):
        verifier, _ = _make_verifier()
        claims = [
            VerifiableClaim("Claim A", "S", 5),
            VerifiableClaim("Claim B", "S", 3),
        ]
        queries = verifier._build_search_queries(claims)
        assert len(queries) == 2


# =============================================================================
# Search parallelism
# =============================================================================


class TestSearchClaims:
    def test_individual_failure_returns_empty(self):
        """Individual search failures should return empty results, not crash."""
        verifier, _ = _make_verifier()

        claim_queries = [
            (VerifiableClaim("Test claim", "S", 3), "TestCo test claim"),
        ]

        with patch("primr.data.search_utils.search_web", side_effect=ConnectionError("fail")):
            results = verifier._search_claims(claim_queries)
            assert "Test claim" in results
            assert results["Test claim"] == []

    def test_successful_search_returns_hits(self):
        """Successful search should return the hit list."""
        verifier, _ = _make_verifier()
        mock_hits = [{"title": "TestCo revenue", "url": "https://example.com/1"}]

        claim_queries = [
            (VerifiableClaim("Revenue $50M", "S", 5), "TestCo Revenue $50M"),
        ]

        with patch("primr.data.search_utils.search_web", return_value=mock_hits):
            results = verifier._search_claims(claim_queries)
            assert results["Revenue $50M"] == mock_hits

    def test_mixed_success_and_failure(self):
        """Some searches succeed, some fail — each handled independently."""
        verifier, _ = _make_verifier()

        call_count = 0

        def alternating_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise ConnectionError("fail")
            return [{"title": "hit", "url": "https://x.com"}]

        claim_queries = [
            (VerifiableClaim(f"Claim {i}", "S", 3), f"TestCo Claim {i}") for i in range(4)
        ]

        with patch("primr.data.search_utils.search_web", side_effect=alternating_search):
            results = verifier._search_claims(claim_queries)
            assert len(results) == 4
            # At least some should have results, some empty
            has_results = sum(1 for v in results.values() if len(v) > 0)
            has_empty = sum(1 for v in results.values() if len(v) == 0)
            assert has_results > 0
            assert has_empty > 0

    def test_empty_queries_returns_empty(self):
        verifier, _ = _make_verifier()
        results = verifier._search_claims([])
        assert results == {}

    def test_non_list_return_from_search_returns_empty(self):
        """If search_web returns a non-list, should be treated as empty."""
        verifier, _ = _make_verifier()
        claim_queries = [
            (VerifiableClaim("Test", "S", 3), "TestCo Test"),
        ]

        with patch("primr.data.search_utils.search_web", return_value="not a list"):
            results = verifier._search_claims(claim_queries)
            assert results["Test"] == []


# =============================================================================
# Classification
# =============================================================================


class TestClassification:
    def test_batch_sizing(self):
        """Classification should process in batches of CLASSIFICATION_BATCH_SIZE."""
        verifier, _ = _make_verifier()
        claims = [VerifiableClaim(f"Claim {i}", "S", 3) for i in range(12)]
        search_results = {f"Claim {i}": [] for i in range(12)}

        call_count = 0

        def mock_llm(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            return json.dumps(
                [
                    {"status": "unverified", "explanation": "no data", "supporting_sources": []}
                    for _ in range(5)
                ]
            )

        with patch("primr.ai.llm.llm", side_effect=mock_llm):
            verifications = asyncio.run(verifier._classify_results(claims, search_results))
            assert call_count == 3  # ceil(12/5)
            assert len(verifications) == 12

    def test_classification_failure_returns_unverified(self):
        """Failed classification should default to unverified."""
        verifier, _ = _make_verifier()
        claims = [VerifiableClaim("Test", "S", 3)]
        search_results = {"Test": []}

        with patch("primr.ai.llm.llm", side_effect=RuntimeError("LLM down")):
            verifications = asyncio.run(verifier._classify_results(claims, search_results))
            assert len(verifications) == 1
            assert verifications[0].status == "unverified"
            assert "Classification error" in verifications[0].explanation

    def test_invalid_status_defaults_to_unverified(self):
        """LLM returning an unknown status value should default to unverified."""
        verifier, _ = _make_verifier()
        claims = [VerifiableClaim("Test", "S", 3)]
        search_results = {"Test": []}

        response = json.dumps(
            [{"status": "maybe_true", "explanation": "dunno", "supporting_sources": []}]
        )

        with patch("primr.ai.llm.llm", return_value=response):
            verifications = asyncio.run(verifier._classify_results(claims, search_results))
            assert verifications[0].status == "unverified"

    def test_fewer_classifications_than_claims(self):
        """If LLM returns fewer classifications than claims in batch, extras get unverified."""
        verifier, _ = _make_verifier()
        claims = [
            VerifiableClaim("Claim A", "S", 3),
            VerifiableClaim("Claim B", "S", 3),
            VerifiableClaim("Claim C", "S", 3),
        ]
        search_results = {c.claim_text: [] for c in claims}

        # Only return 1 classification for 3 claims
        response = json.dumps(
            [
                {
                    "status": "verified",
                    "explanation": "found",
                    "supporting_sources": ["https://x.com"],
                }
            ]
        )

        with patch("primr.ai.llm.llm", return_value=response):
            verifications = asyncio.run(verifier._classify_results(claims, search_results))
            assert len(verifications) == 3
            assert verifications[0].status == "verified"
            assert verifications[1].status == "unverified"
            assert verifications[2].status == "unverified"

    def test_classification_non_list_response(self):
        """LLM returning non-list for classification should not crash."""
        verifier, _ = _make_verifier()
        claims = [VerifiableClaim("Test", "S", 3)]
        search_results = {"Test": []}

        with patch("primr.ai.llm.llm", return_value='{"not": "a list"}'):
            verifications = asyncio.run(verifier._classify_results(claims, search_results))
            assert len(verifications) == 1
            assert verifications[0].status == "unverified"

    def test_search_results_passed_to_classification(self):
        """Verify search results are included in the classification prompt."""
        verifier, _ = _make_verifier()
        claims = [VerifiableClaim("Revenue was $50M", "S", 5)]
        search_results = {
            "Revenue was $50M": [
                {"title": "TestCo Annual Report", "url": "https://testco.com/report"},
                {"title": "Forbes Coverage", "url": "https://forbes.com/testco"},
            ]
        }

        captured_prompt = []

        def capture_llm(prompt, **kwargs):
            captured_prompt.append(prompt)
            return json.dumps(
                [{"status": "verified", "explanation": "found", "supporting_sources": []}]
            )

        with patch("primr.ai.llm.llm", side_effect=capture_llm):
            asyncio.run(verifier._classify_results(claims, search_results))
            assert len(captured_prompt) == 1
            assert "TestCo Annual Report" in captured_prompt[0]
            assert "https://testco.com/report" in captured_prompt[0]


# =============================================================================
# Prompt loading
# =============================================================================


class TestPromptLoading:
    def test_load_claim_extraction_prompt(self):
        verifier, _ = _make_verifier()
        prompt = verifier._load_prompt("claim_extraction")
        assert "{report_text}" in prompt
        assert "{max_claims}" in prompt

    def test_load_classification_prompt(self):
        verifier, _ = _make_verifier()
        prompt = verifier._load_prompt("classification")
        assert "{claims_with_results}" in prompt

    def test_load_nonexistent_prompt_returns_empty(self):
        verifier, _ = _make_verifier()
        prompt = verifier._load_prompt("does_not_exist")
        assert prompt == ""


# =============================================================================
# JSON save
# =============================================================================


class TestSaveResult:
    def test_save_creates_verification_json(self):
        report_path = _write_report("test")
        verifier, _ = _make_verifier()
        result = VerificationResult(
            trust_score=0.7,
            verified_count=7,
            unverified_count=3,
            claim_results=[],
            duration_seconds=10.0,
        )
        verifier._save_result(report_path, result)

        output_path = report_path.parent / "verification.json"
        assert output_path.exists()
        with open(output_path) as f:
            saved = json.load(f)
        assert saved["trust_score"] == 0.7
        assert saved["verified_count"] == 7

    def test_save_overwrites_existing(self):
        report_path = _write_report("test")
        verifier, _ = _make_verifier()

        output_path = report_path.parent / "verification.json"
        output_path.write_text('{"old": true}')

        result = VerificationResult(trust_score=0.9, verified_count=9)
        verifier._save_result(report_path, result)

        with open(output_path) as f:
            saved = json.load(f)
        assert saved["trust_score"] == 0.9
        assert "old" not in saved


# =============================================================================
# End-to-end pipeline (mocked LLM + search)
# =============================================================================


class TestEndToEnd:
    def test_full_pipeline_with_mocks(self):
        """End-to-end: report → extract → search → classify → result."""
        report_path = _write_report(SAMPLE_REPORT)
        context = _make_context(report_path)
        verifier = VerifierSubagent(context, max_claims=3)

        extraction_response = json.dumps(
            [
                {"claim_text": "Revenue was $50M", "section": "Executive Summary", "importance": 5},
                {"claim_text": "500 employees", "section": "Executive Summary", "importance": 4},
                {"claim_text": "Uses AWS", "section": "Key Insights", "importance": 3},
            ]
        )
        classification_response = json.dumps(
            [
                {
                    "status": "verified",
                    "explanation": "Confirmed by SEC filing",
                    "supporting_sources": ["https://sec.gov"],
                },
                {"status": "unverified", "explanation": "No data found", "supporting_sources": []},
                {
                    "status": "contradicted",
                    "explanation": "Uses GCP actually",
                    "supporting_sources": ["https://cloud.google.com"],
                },
            ]
        )

        llm_calls = []

        def mock_llm(prompt, **kwargs):
            llm_calls.append(prompt)
            if len(llm_calls) == 1:
                return extraction_response
            return classification_response

        mock_hits = [{"title": "Hit", "url": "https://example.com"}]

        import primr.ai.llm as llm_mod

        with (
            patch.object(llm_mod, "llm", side_effect=mock_llm),
            patch("primr.data.search_utils.search_web", return_value=mock_hits),
        ):
            result = asyncio.run(verifier.execute())

        assert result.is_success
        assert result.status.value == "completed"
        data = result.data
        assert data.verified_count == 1
        assert data.unverified_count == 1
        assert data.contradicted_count == 1
        assert data.total_claims == 3
        # trust = 1/3
        assert abs(data.trust_score - 1 / 3) < 0.01
        assert data.trust_percentage == 33
        assert data.duration_seconds > 0
        assert len(data.claim_results) == 3

        # Verify metrics on SubagentResult
        assert result.metrics["claims_extracted"] == 3
        assert result.metrics["verified"] == 1
        assert result.metrics["contradicted"] == 1

    def test_pipeline_extraction_failure_returns_failed_result(self):
        """Extraction failure stays non-throwing but is not reported as success."""
        report_path = _write_report(SAMPLE_REPORT)
        context = _make_context(report_path)
        verifier = VerifierSubagent(context)

        import primr.ai.llm as llm_mod

        with (
            patch.object(llm_mod, "llm", side_effect=RuntimeError("LLM offline")),
            patch.object(verifier, "_save_result") as save_result,
        ):
            result = asyncio.run(verifier.execute())

        assert not result.is_success
        assert result.status.value == "failed"
        assert "LLM offline" in result.error
        save_result.assert_not_called()

    def test_genuine_zero_claims_save_a_completed_result(self):
        report_path = _write_report(SAMPLE_REPORT)
        verifier = VerifierSubagent(_make_context(report_path))

        import primr.ai.llm as llm_mod

        with patch.object(llm_mod, "llm", return_value="[]"):
            result = asyncio.run(verifier.execute())

        assert result.is_success
        assert result.data.total_claims == 0
        assert (report_path.parent / "verification.json").exists()

    def test_pipeline_saves_verification_json(self):
        """Pipeline should write verification.json alongside the report."""
        report_path = _write_report(SAMPLE_REPORT)
        context = _make_context(report_path)
        verifier = VerifierSubagent(context, max_claims=1)

        extraction_response = json.dumps(
            [
                {"claim_text": "Revenue $50M", "section": "Summary", "importance": 5},
            ]
        )
        classification_response = json.dumps(
            [
                {"status": "verified", "explanation": "found", "supporting_sources": []},
            ]
        )

        call_idx = 0

        def mock_llm(prompt, **kwargs):
            nonlocal call_idx
            call_idx += 1
            return extraction_response if call_idx == 1 else classification_response

        import primr.ai.llm as llm_mod

        with (
            patch.object(llm_mod, "llm", side_effect=mock_llm),
            patch("primr.data.search_utils.search_web", return_value=[]),
        ):
            asyncio.run(verifier.execute())

        json_path = report_path.parent / "verification.json"
        assert json_path.exists()
        with open(json_path) as f:
            saved = json.load(f)
        assert saved["trust_percentage"] == 100


# =============================================================================
# VerificationGateHook
# =============================================================================


class TestVerificationGateHook:
    def test_warns_on_low_trust(self):
        from src.primr.agentic.hooks import (
            HookContext,
            HookResult,
            HookType,
            VerificationGateHook,
        )

        hook = VerificationGateHook(min_trust_score=0.5)
        assert hook.hook_type == HookType.POST_TOOL_USE
        assert hook.priority == 55

        # Simulate a verify stage result with low trust
        mock_result = MagicMock()
        mock_result.data.trust_score = 0.3

        context = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="verify",
            result=mock_result,
        )
        response = asyncio.run(hook.execute(context))
        assert response.result == HookResult.WARN
        assert "30%" in response.message
        assert "50%" in response.message
        assert hook.last_trust_score == 0.3

    def test_allows_on_sufficient_trust(self):
        from src.primr.agentic.hooks import (
            HookContext,
            HookResult,
            HookType,
            VerificationGateHook,
        )

        hook = VerificationGateHook(min_trust_score=0.5)
        mock_result = MagicMock()
        mock_result.data.trust_score = 0.8

        context = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="verify",
            result=mock_result,
        )
        response = asyncio.run(hook.execute(context))
        assert response.result == HookResult.ALLOW
        assert hook.last_trust_score == 0.8

    def test_skips_non_verify_stage(self):
        from src.primr.agentic.hooks import (
            HookContext,
            HookResult,
            HookType,
            VerificationGateHook,
        )

        hook = VerificationGateHook()
        context = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="write",
            result=MagicMock(),
        )
        response = asyncio.run(hook.execute(context))
        assert response.result == HookResult.ALLOW
        assert hook.last_trust_score is None

    def test_allows_when_no_trust_data(self):
        from src.primr.agentic.hooks import (
            HookContext,
            HookResult,
            HookType,
            VerificationGateHook,
        )

        hook = VerificationGateHook()
        context = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="verify",
            result=None,
        )
        response = asyncio.run(hook.execute(context))
        assert response.result == HookResult.ALLOW

    def test_boundary_trust_score_at_threshold(self):
        """Trust score exactly at threshold should ALLOW, not WARN."""
        from src.primr.agentic.hooks import (
            HookContext,
            HookResult,
            HookType,
            VerificationGateHook,
        )

        hook = VerificationGateHook(min_trust_score=0.5)
        mock_result = MagicMock()
        mock_result.data.trust_score = 0.5

        context = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="verify",
            result=mock_result,
        )
        response = asyncio.run(hook.execute(context))
        assert response.result == HookResult.ALLOW


# =============================================================================
# Orchestrator config / state integration
# =============================================================================


class TestOrchestratorIntegration:
    def test_verifying_state_exists(self):
        from src.primr.agentic.orchestrator import OrchestratorState

        assert hasattr(OrchestratorState, "VERIFYING")
        assert OrchestratorState.VERIFYING.value == "verifying"

    def test_enable_verification_config(self):
        from src.primr.agentic.orchestrator import OrchestratorConfig

        config = OrchestratorConfig(enable_verification=True)
        assert config.enable_verification is True

    def test_enable_verification_default_false(self):
        from src.primr.agentic.orchestrator import OrchestratorConfig

        config = OrchestratorConfig()
        assert config.enable_verification is False

    def test_verifier_exported_from_subagents(self):
        from src.primr.agentic.subagents import VerificationResult, VerifierSubagent

        assert VerifierSubagent is not None
        assert VerificationResult is not None


# =============================================================================
# Cost estimator integration
# =============================================================================


class TestCostEstimatorIntegration:
    def test_verify_false_no_overhead(self):
        from src.primr.utils.cost_estimator import estimate_cost

        est_without = estimate_cost("scrape-only", verify=False, use_historical=False)
        est_with = estimate_cost("scrape-only", verify=True, use_historical=False)
        assert est_with.total_cost > est_without.total_cost

    def test_verify_adds_duration(self):
        from src.primr.utils.cost_estimator import estimate_cost

        est_without = estimate_cost("scrape-only", verify=False, use_historical=False)
        est_with = estimate_cost("scrape-only", verify=True, use_historical=False)
        # Duration string should differ
        assert est_with.duration_minutes != est_without.duration_minutes

    def test_verify_note_in_output(self):
        from src.primr.utils.cost_estimator import estimate_cost

        est = estimate_cost("scrape-only", verify=True, use_historical=False)
        assert any("verification" in n.lower() for n in est.notes)


# =============================================================================
# CLI integration
# =============================================================================


class TestCLIIntegration:
    def test_cli_config_has_verify_field(self):
        from src.primr.core.cli import CLIConfig, Command

        config = CLIConfig(command=Command.RESEARCH, verify=True)
        assert config.verify is True

    def test_cli_config_verify_default_false(self):
        from src.primr.core.cli import CLIConfig, Command

        config = CLIConfig(command=Command.RESEARCH)
        assert config.verify is False


# =============================================================================
# Evidence-based classification (verify upgrade)
# =============================================================================


class TestEvidenceFetching:
    def test_provenance_first_party_vs_third(self):
        verifier, _ = _make_verifier()
        assert verifier._source_provenance("https://testco.com/about") == "first_party"
        assert verifier._source_provenance("https://investors.testco.com/q3") == "first_party"
        assert verifier._source_provenance("https://news.example.com/a") == "third_party"
        assert verifier._source_provenance("") == "third_party"

    def test_fetch_evidence_enriches_hits(self):
        verifier, _ = _make_verifier()
        search_results = {
            "claim A": [
                {"title": "T1", "url": "https://news.example.com/a"},
                {"title": "T2", "url": "https://testco.com/press"},
            ]
        }
        evidence = verifier._fetch_evidence(search_results)
        enriched = evidence["claim A"]
        assert enriched[0]["provenance"] == "third_party"
        assert enriched[1]["provenance"] == "first_party"
        assert all(e["fetched"] for e in enriched)
        assert "stub evidence content" in enriched[0]["snippet"]

    def test_fetch_failure_falls_back_to_title_only(self, monkeypatch):
        def failing_get(url, timeout=15.0, headers=None, params=None):
            return None, None, None

        monkeypatch.setattr("primr.data.fallback_sources._http_get", failing_get)
        verifier, _ = _make_verifier()
        evidence = verifier._fetch_evidence(
            {"claim A": [{"title": "T1", "url": "https://news.example.com/a"}]}
        )
        hit = evidence["claim A"][0]
        assert hit["fetched"] is False
        assert hit["snippet"] == ""

    def test_snippet_truncated(self, monkeypatch):
        big = b"<html><body><p>" + b"word " * 5000 + b"</p></body></html>"

        def big_get(url, timeout=15.0, headers=None, params=None):
            return 200, big, url

        monkeypatch.setattr("primr.data.fallback_sources._http_get", big_get)
        verifier, _ = _make_verifier()
        evidence = verifier._fetch_evidence(
            {"c": [{"title": "T", "url": "https://news.example.com/a"}]}
        )
        assert len(evidence["c"][0]["snippet"]) <= verifier.EVIDENCE_SNIPPET_CHARS

    def test_duplicate_urls_fetched_once(self, monkeypatch):
        calls = []

        def counting_get(url, timeout=15.0, headers=None, params=None):
            calls.append(url)
            return 200, b"<html><body>x</body></html>", url

        monkeypatch.setattr("primr.data.fallback_sources._http_get", counting_get)
        verifier, _ = _make_verifier()
        shared = {"title": "T", "url": "https://news.example.com/a"}
        verifier._fetch_evidence({"c1": [shared], "c2": [shared]})
        assert calls.count("https://news.example.com/a") == 1


class TestEvidenceClassification:
    def _claims(self):
        return [VerifiableClaim(claim_text="TestCo revenue was $50M", section="Exec", importance=5)]

    def test_evidence_reaches_classifier_prompt(self):
        verifier, _ = _make_verifier()
        captured = {}

        def mock_llm(prompt, **kwargs):
            captured["prompt"] = prompt
            return json.dumps(
                [
                    {
                        "claim_text": "TestCo revenue was $50M",
                        "status": "verified",
                        "explanation": "evidence supports",
                        "supporting_sources": ["https://news.example.com/a"],
                    }
                ]
            )

        with patch("primr.ai.llm.llm", side_effect=mock_llm):
            results = asyncio.run(
                verifier._classify_results(
                    self._claims(),
                    {
                        "TestCo revenue was $50M": [
                            {"title": "T1", "url": "https://news.example.com/a"}
                        ]
                    },
                )
            )
        assert "stub evidence content" in captured["prompt"]
        assert '"provenance": "third_party"' in captured["prompt"]
        assert results[0].status == "verified"
        assert results[0].evidence_sources[0]["provenance"] == "third_party"
        assert results[0].first_party_downgrade is False

    def test_first_party_only_support_downgraded(self):
        verifier, _ = _make_verifier()

        def mock_llm(prompt, **kwargs):
            return json.dumps(
                [
                    {
                        "claim_text": "TestCo revenue was $50M",
                        "status": "verified",
                        "explanation": "the company says so",
                        "supporting_sources": [
                            "https://testco.com/press",
                            "https://investors.testco.com/q3",
                        ],
                    }
                ]
            )

        with patch("primr.ai.llm.llm", side_effect=mock_llm):
            results = asyncio.run(
                verifier._classify_results(
                    self._claims(),
                    {
                        "TestCo revenue was $50M": [
                            {"title": "PR", "url": "https://testco.com/press"}
                        ]
                    },
                )
            )
        assert results[0].status == "unverified"
        assert results[0].first_party_downgrade is True
        assert "self-corroboration" in results[0].explanation

    def test_third_party_support_not_downgraded(self):
        verifier, _ = _make_verifier()

        def mock_llm(prompt, **kwargs):
            return json.dumps(
                [
                    {
                        "claim_text": "TestCo revenue was $50M",
                        "status": "verified",
                        "explanation": "independent coverage",
                        "supporting_sources": [
                            "https://testco.com/press",
                            "https://news.example.com/a",
                        ],
                    }
                ]
            )

        with patch("primr.ai.llm.llm", side_effect=mock_llm):
            results = asyncio.run(
                verifier._classify_results(
                    self._claims(),
                    {
                        "TestCo revenue was $50M": [
                            {"title": "T", "url": "https://news.example.com/a"}
                        ]
                    },
                )
            )
        assert results[0].status == "verified"
        assert results[0].first_party_downgrade is False

    def test_unretrievable_evidence_marked_in_prompt(self, monkeypatch):
        def failing_get(url, timeout=15.0, headers=None, params=None):
            return None, None, None

        monkeypatch.setattr("primr.data.fallback_sources._http_get", failing_get)
        verifier, _ = _make_verifier()
        captured = {}

        def mock_llm(prompt, **kwargs):
            captured["prompt"] = prompt
            return json.dumps([])

        with patch("primr.ai.llm.llm", side_effect=mock_llm):
            asyncio.run(
                verifier._classify_results(
                    self._claims(),
                    {
                        "TestCo revenue was $50M": [
                            {"title": "T", "url": "https://news.example.com/a"}
                        ]
                    },
                )
            )
        assert "content not retrievable" in captured["prompt"]

    def test_serialization_includes_evidence_fields(self):
        claim = VerifiableClaim(claim_text="c", section="s", importance=3)
        cv = ClaimVerification(
            claim=claim,
            status="unverified",
            evidence_sources=[
                {"url": "https://x.example", "provenance": "third_party", "fetched": True}
            ],
            first_party_downgrade=True,
        )
        d = cv.to_dict()
        assert d["evidence_sources"][0]["provenance"] == "third_party"
        assert d["first_party_downgrade"] is True
