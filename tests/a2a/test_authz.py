"""Tests for A2A per-skill authorization."""

from unittest.mock import MagicMock

from primr.a2a.authz import (
    A2A_SKILL_REQUIRED_SCOPES,
    a2a_scope_denied_text,
    authorize_a2a_skill,
)


def _auth_context(scopes: list[str], *, authenticated: bool = True) -> MagicMock:
    context = MagicMock()
    context.is_authenticated = authenticated
    context.scopes = scopes
    return context


def test_scope_table_covers_public_skills_and_cancel() -> None:
    """Every exposed A2A operation has an explicit minimum scope."""
    assert A2A_SKILL_REQUIRED_SCOPES == {
        "estimate_research": ("read",),
        "check_jobs": ("read",),
        "system_health": ("read",),
        "read_artifacts_by_job": ("read",),
        "read_qa_summary_by_job": ("read",),
        "read_usage_summary_by_job": ("read",),
        "read_source_summary_by_job": ("read",),
        "read_trace_summary_by_job": ("read",),
        "read_stage_scorecard": ("read",),
        "research_company": ("research",),
        "run_qa": ("research",),
        "cancel_task": ("research",),
    }


def test_read_skill_accepts_read_scope() -> None:
    decision = authorize_a2a_skill("check_jobs", _auth_context(["read"]))
    assert decision.allowed
    assert decision.missing_scopes == ()


def test_research_skill_denies_read_only_scope() -> None:
    decision = authorize_a2a_skill("research_company", _auth_context(["read"]))
    assert not decision.allowed
    assert decision.missing_scopes == ("research",)
    assert "insufficient_scope" in a2a_scope_denied_text("research_company", decision)


def test_research_skill_accepts_legacy_write_scope() -> None:
    decision = authorize_a2a_skill("research_company", _auth_context(["read", "write"]))
    assert decision.allowed


def test_admin_scope_satisfies_research_skill() -> None:
    decision = authorize_a2a_skill("run_qa", _auth_context(["admin"]))
    assert decision.allowed


def test_unauthenticated_local_context_remains_permissive() -> None:
    decision = authorize_a2a_skill("research_company", _auth_context([], authenticated=False))
    assert decision.allowed
    assert decision.reason == "stdio_or_unauthenticated_local_context"


def test_unknown_skill_deferred_to_dispatch() -> None:
    decision = authorize_a2a_skill("not_registered", _auth_context([]))
    assert decision.allowed
    assert decision.reason == "unknown_skill_deferred_to_dispatch"
