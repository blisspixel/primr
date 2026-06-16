"""Regression tests for the correctness bugs found in bug-hunt round 1.

Each test pins a specific defect so it cannot silently return. See the
PR/commit for the full triage; one test class per fix.
"""

from __future__ import annotations

import pytest

from primr.ai.error_policy import is_invalid_api_key_error
from primr.core.cli_batch import _csv_safe
from primr.data.scraping.models import ErrorType, ScrapeResult
from primr.output.markdown_converter import render_table
from primr.qa.report_analyzer import ReportAnalyzer
from primr.utils.run_budget import RunBudget
from primr.utils.security import (
    canonicalize_numeric_host,
    is_safe_url,
    mask_sensitive_data,
)


class TestSSRFOutOfRangePort:
    """is_safe_url must not crash on an out-of-range port.

    `urllib`'s parsed.port is a lazy property that raises ValueError for a port
    outside 0-65535; the security check must return (False, reason), not raise.
    """

    @pytest.mark.parametrize("url", ["http://example.com:99999/", "https://example.com:70000/x"])
    def test_out_of_range_port_returns_false_not_raises(self, url: str) -> None:
        ok, reason = is_safe_url(url)
        assert ok is False
        assert reason  # a non-empty explanation

    def test_normal_port_still_evaluated(self) -> None:
        # A valid explicit port should not be rejected by the port guard itself
        # (loopback is still blocked for SSRF reasons, which is the expected no).
        ok, reason = is_safe_url("http://127.0.0.1:8080/")
        assert ok is False
        assert "port" not in (reason or "").lower()


class TestOpenAIKeyRedaction:
    """Modern sk-proj-/sk-svcacct- keys must be redacted, not just classic ones."""

    def test_classic_key_redacted(self) -> None:
        masked = mask_sensitive_data("token sk-" + "a" * 48 + " end")
        assert "[OPENAI_API_KEY]" in masked
        assert "sk-" + "a" * 48 not in masked

    def test_project_key_redacted(self) -> None:
        # Bare key in a message/traceback (no "api_key=" prefix to trigger the
        # generic rule) — this is the path the fixed sk- pattern must catch.
        key = "sk-proj-" + "Abc123_" * 6 + "XYZ"
        masked = mask_sensitive_data(f"call failed with token {key} returned 401")
        assert key not in masked
        assert "[OPENAI_API_KEY]" in masked

    def test_service_account_key_redacted(self) -> None:
        key = "sk-svcacct-" + "Def456-" * 5 + "QRS"
        masked = mask_sensitive_data(f"leaked in traceback: {key}")
        assert key not in masked


class TestErrorTypeEmptyContent:
    """The vision tier references ErrorType.EMPTY_CONTENT; it must exist."""

    def test_member_exists(self) -> None:
        assert ErrorType.EMPTY_CONTENT.value == "empty_content"

    def test_scrape_result_accepts_it(self) -> None:
        result = ScrapeResult(
            url="https://example.com",
            success=False,
            error_type=ErrorType.EMPTY_CONTENT,
            error="insufficient content",
        )
        assert result.error_type is ErrorType.EMPTY_CONTENT


class TestCitationHeadingWithTrailingWords:
    """analyze_citations must locate the bibliography even when the heading has
    trailing words (e.g. '## Sources Consulted'), not zero the grade component.
    """

    def test_sources_consulted_heading_resolves_citations(self, tmp_path) -> None:
        content = (
            "# Report\n\n"
            "Some claim [cite: 1] and another [cite: 2].\n\n"
            "## Sources Consulted\n\n"
            "[cite: 1] https://a.example\n"
            "[cite: 2] https://b.example\n"
        )
        path = tmp_path / "Report.md"
        path.write_text(content, encoding="utf-8")

        result = ReportAnalyzer(str(path)).analyze_citations()

        assert result["defined_citations"] == 2
        assert result["missing_citations"] == []
        assert result["citation_coverage"] == 1.0


class TestTableSeparatorSkipped:
    """render_table must skip multi-column separator rows (|---|---|), which
    carry internal pipes, instead of rendering them as a data row.
    """

    def test_multicolumn_separator_not_rendered_as_row(self) -> None:
        docx = pytest.importorskip("docx")
        doc = docx.Document()
        render_table(
            doc,
            ["| A | B |", "|---|---|", "| 1 | 2 |"],
        )
        table = doc.tables[0]
        # Header + one data row only — the separator must not become a row.
        assert len(table.rows) == 2
        cell_texts = [c.text for row in table.rows for c in row.cells]
        assert not any("---" in t for t in cell_texts)


class TestBudgetBoundaryConsistency:
    """would_exceed and exceeded must agree on the exact-ceiling case."""

    def test_exactly_at_ceiling_agrees(self) -> None:
        rb = RunBudget(5.0)
        rb.sync_spend(5.0)
        assert rb.exceeded() is True
        assert rb.would_exceed(0.0) is True

    def test_next_cost_landing_on_ceiling_is_exceed(self) -> None:
        rb = RunBudget(5.0)
        rb.sync_spend(3.0)
        # 3 + 2 == 5 == ceiling -> would_exceed must be True (was False before).
        assert rb.would_exceed(2.0) is True

    def test_under_ceiling_does_not_exceed(self) -> None:
        rb = RunBudget(5.0)
        rb.sync_spend(3.0)
        assert rb.would_exceed(1.0) is False


class TestInvalidApiKeyClassification:
    """is_invalid_api_key_error must not fire on a generic 'Invalid argument'."""

    def test_invalid_argument_is_not_auth_error(self) -> None:
        assert is_invalid_api_key_error("Invalid argument: bad request to the api") is False

    def test_invalid_request_is_not_auth_error(self) -> None:
        assert is_invalid_api_key_error("400 invalid request: api parameter") is False

    @pytest.mark.parametrize(
        "msg",
        [
            "Invalid API key provided",
            "incorrect api key",
            "401 Unauthorized",
            "authentication_error: invalid x-api-key",
        ],
    )
    def test_genuine_auth_errors_match(self, msg: str) -> None:
        assert is_invalid_api_key_error(msg) is True


class TestNumericHostTrailingDot:
    """The numeric-IP backstop must still decode a trailing-dot literal."""

    def test_loopback_with_trailing_dot(self) -> None:
        assert canonicalize_numeric_host("127.0.0.1.") == "127.0.0.1"

    def test_decimal_literal_with_trailing_dot(self) -> None:
        # 2130706433 == 127.0.0.1; the trailing dot must not bypass decoding.
        assert canonicalize_numeric_host("2130706433.") == "127.0.0.1"


class TestCsvInjectionLeadingWhitespace:
    """_csv_safe must neutralize payloads with leading whitespace/newlines."""

    def test_leading_space_formula_neutralized(self) -> None:
        assert _csv_safe(" =SUM(A1)").startswith("' ")

    def test_leading_newline_formula_neutralized(self) -> None:
        assert _csv_safe("\n=cmd").startswith("'")

    def test_plain_value_untouched(self) -> None:
        assert _csv_safe("Acme Corp") == "Acme Corp"

    def test_classic_leading_equals_still_neutralized(self) -> None:
        assert _csv_safe("=cmd") == "'=cmd"
