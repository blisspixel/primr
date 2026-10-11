"""Tests for blocked-site CLI summaries."""

from __future__ import annotations

import pytest

from primr.data.scraping.blocked_summary import (
    build_blocked_site_summary,
    emit_blocked_site_summary,
)
from primr.data.scraping.models import PageAccessAssessment, PageAccessState, ScrapeResult


class RecordingConsole:
    def __init__(self):
        self.events: list[tuple[str, str]] = []

    def fail(self, msg):
        self.events.append(("fail", msg))

    def warn(self, msg):
        self.events.append(("warn", msg))

    def muted(self, msg):
        self.events.append(("muted", msg))


def test_blocked_site_summary_includes_evidence_recovery_count_and_next_action():
    result = ScrapeResult(
        url="https://example.com",
        success=False,
        error="challenge shell",
        access_assessment=PageAccessAssessment(
            state=PageAccessState.SOFT_BLOCK,
            reason="blocked",
            confidence=0.9,
            evidence=[
                "soft_block_detector: https://user:pass@example.com/private?token=abc",
                "visible_text_length:42",
            ],
        ),
    )

    lines = build_blocked_site_summary(
        result,
        "origin blocked at https://example.com/secret?api_key=short",
        recovery_count=0,
    )
    joined = "\n".join(lines)

    assert "Evidence: origin blocked at https://example.com" in joined
    assert "visible_text_length:42" in joined
    assert "0 same-site candidate page(s)" in joined
    assert "--mode deep" in joined
    assert "user:pass" not in joined
    assert "token=abc" not in joined
    assert "api_key=short" not in joined
    assert "/private" not in joined


def test_emit_blocked_site_summary_uses_console_methods():
    console = RecordingConsole()
    result = ScrapeResult(url="https://example.com", success=False, error="access denied")

    emit_blocked_site_summary(console, "example.com", result, None, recovery_count=2)

    assert console.events[0] == ("fail", "Could not access example.com")
    assert any(kind == "muted" and "Evidence: access denied" in msg for kind, msg in console.events)
    assert any(
        kind == "muted" and "2 same-site candidate page(s)" in msg for kind, msg in console.events
    )


@pytest.mark.parametrize("state", [PageAccessState.THIN_CONTENT, PageAccessState.UNKNOWN])
def test_reachable_insufficient_page_is_reported_without_block_diagnosis(state):
    console = RecordingConsole()
    result = ScrapeResult(
        url="https://example.com",
        success=False,
        http_status=200,
        error="Content signals are inconclusive",
        access_assessment=PageAccessAssessment(
            state=state,
            reason="insufficient content",
            visible_text_length=140,
            evidence=["visible_text_length:140"],
        ),
    )
    emit_blocked_site_summary(console, "example.com", result, None, recovery_count=0)
    assert console.events[0][0] == "warn"
    assert "Reached example.com" in console.events[0][1]
    messages = "\n".join(msg for _, msg in console.events)
    assert "visible_text_length:140" in messages
    assert "collecting additional public sources" in messages
    assert "Could not access" not in messages
    assert "check site availability" not in messages


@pytest.mark.parametrize("status", [None, 403, 429])
def test_insufficient_assessment_without_success_status_does_not_claim_reachable(status):
    console = RecordingConsole()
    result = ScrapeResult(
        url="https://example.com",
        success=False,
        http_status=status,
        access_assessment=PageAccessAssessment(state=PageAccessState.UNKNOWN),
    )
    emit_blocked_site_summary(console, "example.com", result, None, recovery_count=0)
    assert console.events[0] == ("fail", "Could not access example.com")
