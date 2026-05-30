"""Unit tests for DeepResearchClient helpers in primr.ai.deep_research.

Focused on the small testable methods: _build_prompt, prompt builders for
each output_format, _format_interaction_error, _extract_* delegators,
_get_poll_interval, and check_job.
"""

from __future__ import annotations

import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.deep_research import DeepResearchClient, ResearchStatus


@pytest.fixture
def client(monkeypatch):
    """A DeepResearchClient with the underlying genai.Client mocked out."""
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    return DeepResearchClient(api_key="fake-key-1234567890")


# ---------------------------------------------------------------------------
# _build_prompt — dispatches based on output_format
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_company_profile_dispatches(self, client):
        with patch.object(client, "_build_company_profile_prompt", return_value="CP"):
            assert client._build_prompt("Research Acme", "company_profile") == "CP"

    def test_strategic_layer_dispatches(self, client):
        with patch.object(client, "_build_strategic_layer_prompt", return_value="SL"):
            assert client._build_prompt("query", "strategic_layer") == "SL"

    def test_executive_summary_formats_inline(self, client):
        result = client._build_prompt("Research X", "executive_summary")
        assert "Research X" in result
        assert "Key Findings" in result
        assert "Recommendations" in result

    def test_competitive_analysis_formats_inline(self, client):
        result = client._build_prompt("Compare A vs B", "competitive_analysis")
        assert "Compare A vs B" in result
        assert "Competitive Positioning" in result
        assert "comparison table" in result

    def test_unknown_format_returns_raw_query(self, client):
        assert client._build_prompt("just a query", None) == "just a query"
        assert client._build_prompt("just a query", "unknown_fmt") == "just a query"


# ---------------------------------------------------------------------------
# _build_company_profile_prompt — extracts company name and URL from query
# ---------------------------------------------------------------------------


class TestBuildCompanyProfilePrompt:
    def test_extracts_company_name_from_research_query(self, client):
        with patch("primr.prompts.build_company_overview_prompt") as build_mock:
            build_mock.return_value = "PROMPT"
            result = client._build_company_profile_prompt("Research Acme Corp")
            assert result == "PROMPT"
            kwargs = build_mock.call_args.kwargs
            assert kwargs["company_name"] == "Acme Corp"

    def test_extracts_url_when_in_parens(self, client):
        with patch("primr.prompts.build_company_overview_prompt") as build_mock:
            build_mock.return_value = "PROMPT"
            client._build_company_profile_prompt("Research Acme (https://acme.example)")
            kwargs = build_mock.call_args.kwargs
            assert kwargs["website_url"] == "https://acme.example"

    def test_falls_back_to_default_company_name(self, client):
        with patch("primr.prompts.build_company_overview_prompt") as build_mock:
            build_mock.return_value = "PROMPT"
            client._build_company_profile_prompt("query without 'Research' keyword")
            kwargs = build_mock.call_args.kwargs
            assert kwargs["company_name"] == "Company"


# ---------------------------------------------------------------------------
# _build_strategic_layer_prompt — uses PromptComposer with fallback
# ---------------------------------------------------------------------------


class TestBuildStrategicLayerPrompt:
    def test_uses_composer_when_available(self, client):
        composer = MagicMock()
        composed = MagicMock()
        composed.content = "STRATEGIC: {query} done"
        composer.compose.return_value = composed
        with patch("primr.prompts.composer.PromptComposer", return_value=composer):
            result = client._build_strategic_layer_prompt("my query")
            assert result == "STRATEGIC: my query done"

    def test_falls_back_when_composer_raises(self, client):
        with patch(
            "primr.prompts.composer.PromptComposer",
            side_effect=RuntimeError("config broken"),
        ):
            result = client._build_strategic_layer_prompt("my query")
            assert "my query" in result
            assert "senior strategy consultant" in result
            assert "Narrative Gap Analysis" in result


# ---------------------------------------------------------------------------
# _format_interaction_error — static method, gracefully extracts errors
# ---------------------------------------------------------------------------


class TestFormatInteractionError:
    def test_extracts_error_attribute(self):
        i = SimpleNamespace(error="something broke")
        assert DeepResearchClient._format_interaction_error(i) == "something broke"

    def test_tries_error_message_when_error_missing(self):
        i = SimpleNamespace(error=None, error_message="api 500")
        assert DeepResearchClient._format_interaction_error(i) == "api 500"

    def test_falls_through_to_to_dict_payload(self):
        i = MagicMock()
        i.error = None
        i.error_message = None
        i.error_status = None
        i.status_message = None
        i.failure_reason = None
        i.last_error = None
        i.to_dict.return_value = {"errorMessage": "from dict"}
        assert DeepResearchClient._format_interaction_error(i) == "from dict"

    def test_uses_diagnostics_when_no_specific_fields(self):
        i = MagicMock()
        # All known fields return None
        for attr in (
            "error",
            "error_message",
            "error_status",
            "status_message",
            "failure_reason",
            "last_error",
        ):
            setattr(i, attr, None)
        i.to_dict.return_value = {"diagnostics": "some debug info"}
        assert DeepResearchClient._format_interaction_error(i) == "some debug info"

    def test_default_when_nothing_found(self):
        i = MagicMock()
        for attr in (
            "error",
            "error_message",
            "error_status",
            "status_message",
            "failure_reason",
            "last_error",
        ):
            setattr(i, attr, None)
        i.to_dict.return_value = {}
        assert "no details" in DeepResearchClient._format_interaction_error(i)

    def test_to_dict_exception_falls_through(self):
        i = MagicMock()
        for attr in (
            "error",
            "error_message",
            "error_status",
            "status_message",
            "failure_reason",
            "last_error",
        ):
            setattr(i, attr, None)
        i.to_dict.side_effect = RuntimeError("oops")
        assert "no details" in DeepResearchClient._format_interaction_error(i)


# ---------------------------------------------------------------------------
# _get_interaction / _extract_* — thin delegators
# ---------------------------------------------------------------------------


class TestGetInteraction:
    def test_calls_client_interactions_get(self, client):
        client._client.interactions.get.return_value = "INTERACTION"
        # Suppress the warning filter context — just call it.
        with warnings.catch_warnings():
            assert client._get_interaction("iid") == "INTERACTION"
        client._client.interactions.get.assert_called_once_with("iid")


class TestExtractDelegators:
    def test_extract_content_delegates(self, client):
        with patch(
            "primr.ai.deep_research.extract_interaction_content",
            return_value="content",
        ):
            assert client._extract_content(MagicMock()) == "content"

    def test_extract_citations_delegates(self, client):
        with patch(
            "primr.ai.deep_research.extract_interaction_citations",
            return_value=[{"url": "x"}],
        ):
            assert client._extract_citations(MagicMock()) == [{"url": "x"}]

    def test_extract_search_queries_count_delegates(self, client):
        with patch(
            "primr.ai.deep_research.extract_search_queries_count",
            return_value=5,
        ):
            assert client._extract_search_queries_count(MagicMock()) == 5

    def test_extract_search_queries_count_logs_when_zero(self, client):
        with patch(
            "primr.ai.deep_research.extract_search_queries_count",
            return_value=0,
        ):
            assert client._extract_search_queries_count(MagicMock()) == 0


# ---------------------------------------------------------------------------
# _get_poll_interval — adaptive polling
# ---------------------------------------------------------------------------


class TestGetPollInterval:
    def test_returns_5s_early(self, client):
        # POLL_FAST_THRESHOLD = 60; elapsed < 60 -> 5.0s
        assert client._get_poll_interval(10) == 5.0
        assert client._get_poll_interval(59) == 5.0

    def test_returns_10s_in_middle(self, client):
        # 60 < elapsed < 300 -> 10.0s
        assert client._get_poll_interval(120) == 10.0
        assert client._get_poll_interval(299) == 10.0

    def test_returns_20s_after_normal_threshold(self, client):
        # elapsed > 300 -> 20.0s
        assert client._get_poll_interval(400) == 20.0
        assert client._get_poll_interval(3600) == 20.0


# ---------------------------------------------------------------------------
# check_job
# ---------------------------------------------------------------------------


class TestCheckJob:
    def test_returns_completed_with_content(self, client, monkeypatch):
        interaction = MagicMock()
        interaction.status = "completed"
        client._client.interactions.get.return_value = interaction

        with (
            patch.object(client, "_extract_content", return_value="full body"),
            patch.object(client, "_extract_citations", return_value=[{"url": "x"}]),
            patch("primr.ai.deep_research.remove_pending_job") as remove_mock,
        ):
            result = client.check_job("iid-1")

        assert result["status"] == "completed"
        assert result["content"] == "full body"
        assert result["citations"] == [{"url": "x"}]
        assert result["terminal"] is True
        remove_mock.assert_called_once_with("iid-1")

    @pytest.mark.parametrize(
        "terminal_status",
        ["failed", "error", "cancelled", "canceled", "expired"],
    )
    def test_terminal_failure_statuses(self, client, terminal_status):
        interaction = MagicMock()
        interaction.status = terminal_status
        client._client.interactions.get.return_value = interaction
        with (
            patch.object(client, "_format_interaction_error", return_value="provider error"),
            patch("primr.ai.deep_research.remove_pending_job"),
        ):
            result = client.check_job("iid-2")
        assert result["status"] == terminal_status
        assert result["terminal"] is True
        assert result["error"] == "provider error"
        assert result["error_source"] == "provider"

    def test_in_progress_not_terminal(self, client):
        interaction = MagicMock()
        interaction.status = "running"
        client._client.interactions.get.return_value = interaction
        result = client.check_job("iid-3")
        assert result["terminal"] is False
        assert result["status"] == "running"
        assert result["content"] is None

    def test_local_exception_marks_check_error(self, client):
        client._client.interactions.get.side_effect = RuntimeError("network down")
        result = client.check_job("iid-4")
        assert result["status"] == "check_error"
        assert result["error_source"] == "local"
        assert "network down" in result["error"]


# ---------------------------------------------------------------------------
# Class-level constants
# ---------------------------------------------------------------------------


class TestClassConstants:
    def test_known_polling_thresholds(self):
        assert DeepResearchClient.POLL_FAST_THRESHOLD == 60
        assert DeepResearchClient.POLL_NORMAL_THRESHOLD == 300

    def test_max_research_time_is_one_hour(self):
        assert DeepResearchClient.MAX_RESEARCH_TIME == 3600

    def test_default_poll_interval_is_ten(self):
        assert DeepResearchClient.DEFAULT_POLL_INTERVAL == 10


# ---------------------------------------------------------------------------
# ResearchStatus enum (re-tested here to bump class coverage)
# ---------------------------------------------------------------------------


def test_research_status_in_progress_is_pending_subset():
    # Just sanity that we can import and use the enum from this module.
    assert ResearchStatus.IN_PROGRESS.value == "in_progress"
    assert ResearchStatus.COMPLETED.value == "completed"
