"""Tests for blocked-site CLI summaries."""

from __future__ import annotations

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
