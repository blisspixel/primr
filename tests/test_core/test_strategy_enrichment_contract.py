"""Tests for strategy-specific enrichment framing."""

from primr.core.strategy_enrichment_contract import strategy_document_context


def test_ai_strategy_gets_business_first_platform_emphasis():
    label, emphasis = strategy_document_context("AI Strategy", "agnostic")

    assert label == "business-first AI strategy"
    assert "AGNOSTIC" in emphasis
    assert "not a predetermined vendor answer" in emphasis


def test_generic_strategy_gets_no_platform_emphasis():
    label, emphasis = strategy_document_context("Customer Experience", "Customer Experience")

    assert label == "Customer Experience document"
    assert emphasis == ""
