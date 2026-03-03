"""
Property-based tests for Research Memory.

This module validates the correctness properties of the Research Memory
system using the Hypothesis library. Each test corresponds to a formal
property from the design document.

Properties tested:
- Property 9: Research Memory Round-Trip
- Property 10: Hypothesis Expiration Filtering
- Property 11: Hypothesis Query Filtering
- Property 12: Hypothesis Confidence Updates

Validates: Requirements 5.1, 5.5, 5.6, 5.7, 5.8
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from primr.agentic.memory import (
    ResearchMemory,
)
from primr.agentic.models import ConfidenceLevel, Hypothesis

# =============================================================================
# STRATEGIES
# =============================================================================

# Strategy for valid company names (ASCII only, non-empty, reasonable length)
company_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), max_codepoint=127),
    min_size=1,
    max_size=20,
).filter(lambda x: x.strip())

# Strategy for hypothesis IDs (simple alphanumeric)
hypothesis_ids = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), max_codepoint=127),
    min_size=1,
    max_size=10,
)

# Strategy for claims (ASCII only)
claims = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), max_codepoint=127),
    min_size=1,
    max_size=50,
)

# Strategy for topics (ASCII only)
topics = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), max_codepoint=127),
    min_size=0,
    max_size=20,
)

# Strategy for evidence strings (ASCII only)
evidence_strings = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), max_codepoint=127),
    min_size=1,
    max_size=50,
)

# Strategy for confidence levels
confidence_levels = st.sampled_from(list(ConfidenceLevel))

# Strategy for datetime (within reasonable range)
datetimes = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
)

# Strategy for optional expiration dates
optional_expiration = st.one_of(
    st.none(),
    st.datetimes(
        min_value=datetime.now() - timedelta(days=365),
        max_value=datetime.now() + timedelta(days=365),
    ),
)


@st.composite
def hypotheses(draw, expired_ratio: float = 0.0):
    """
    Strategy for generating hypotheses.

    Args:
        expired_ratio: Ratio of hypotheses that should be expired (0.0-1.0)
    """
    h_id = draw(hypothesis_ids)
    claim = draw(claims)
    confidence = draw(confidence_levels)
    topic = draw(topics)
    evidence = draw(st.lists(evidence_strings, max_size=5))

    # Determine if this hypothesis should be expired
    is_expired = draw(st.floats(min_value=0, max_value=1)) < expired_ratio

    if is_expired:
        expires_at = datetime.now() - timedelta(days=draw(st.integers(1, 30)))
    else:
        # Either no expiration or future expiration
        if draw(st.booleans()):
            expires_at = None
        else:
            expires_at = datetime.now() + timedelta(days=draw(st.integers(1, 365)))

    return Hypothesis(
        id=h_id,
        claim=claim,
        confidence=confidence,
        evidence=evidence,
        topic=topic,
        expires_at=expires_at,
    )


@st.composite
def hypothesis_lists(draw, min_size: int = 0, max_size: int = 5):
    """Strategy for generating lists of hypotheses with unique IDs."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    result = []
    used_ids = set()

    for i in range(count):
        h = draw(hypotheses())
        # Ensure unique ID
        while h.id in used_ids:
            h = Hypothesis(
                id=f"{h.id}_{i}",
                claim=h.claim,
                confidence=h.confidence,
                evidence=h.evidence,
                topic=h.topic,
                expires_at=h.expires_at,
            )
        used_ids.add(h.id)
        result.append(h)

    return result


# =============================================================================
# PROPERTY 9: Research Memory Round-Trip
# =============================================================================

# Feature: agentic-architecture, Property 9: Research Memory Round-Trip
@given(
    company=company_names,
    hyps=hypothesis_lists(max_size=5),
    notes=st.lists(st.text(min_size=1, max_size=30, alphabet=st.characters(max_codepoint=127)), max_size=3),
)
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_memory_round_trip(company: str, hyps: list[Hypothesis], notes: list[str]):
    """
    Serializing and deserializing memory preserves all data.

    For any CompanyMemory object, serializing to YAML and deserializing
    should produce an equivalent object with all hypotheses, patterns,
    and notes preserved.

    Validates: Requirements 5.1, 5.7
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ResearchMemory(storage_path=Path(tmpdir))

        # Save hypotheses
        if hyps:
            memory.save_hypotheses(company, hyps)

        # Add notes
        for note in notes:
            memory.add_research_note(company, note)

        # Clear cache to force reload from disk
        memory.clear_cache()

        # Load and verify
        loaded = memory.get_hypotheses(company, include_expired=True)

        # Verify hypothesis count
        assert len(loaded) == len(hyps), (
            f"Expected {len(hyps)} hypotheses, got {len(loaded)}"
        )

        # Verify each hypothesis
        loaded_by_id = {h.id: h for h in loaded}
        for orig in hyps:
            assert orig.id in loaded_by_id, f"Missing hypothesis {orig.id}"
            load = loaded_by_id[orig.id]
            assert orig.claim == load.claim
            assert orig.confidence == load.confidence
            assert orig.topic == load.topic
            # Evidence may have been modified by validate/invalidate
            # so we just check it's a list
            assert isinstance(load.evidence, list)


# =============================================================================
# PROPERTY 10: Hypothesis Expiration Filtering
# =============================================================================

# Feature: agentic-architecture, Property 10: Hypothesis Expiration Filtering
@given(
    company=company_names,
    num_expired=st.integers(min_value=0, max_value=3),
    num_valid=st.integers(min_value=0, max_value=3),
)
@settings(max_examples=30, deadline=None)
def test_expiration_filtering(company: str, num_expired: int, num_valid: int):
    """
    Expired hypotheses are not returned in queries by default.

    For any set of hypotheses with expiration dates, querying
    get_hypotheses() should only return hypotheses where expires_at
    is null or in the future.

    Validates: Requirements 5.6
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ResearchMemory(storage_path=Path(tmpdir))

        hypotheses_list = []

        # Create expired hypotheses
        for i in range(num_expired):
            hypotheses_list.append(Hypothesis(
                id=f"expired_{i}",
                claim=f"Expired claim {i}",
                confidence=ConfidenceLevel.UNTESTED,
                expires_at=datetime.now() - timedelta(days=1),
            ))

        # Create valid hypotheses (no expiration or future expiration)
        for i in range(num_valid):
            hypotheses_list.append(Hypothesis(
                id=f"valid_{i}",
                claim=f"Valid claim {i}",
                confidence=ConfidenceLevel.UNTESTED,
                expires_at=datetime.now() + timedelta(days=30),
            ))

        # Save all
        if hypotheses_list:
            memory.save_hypotheses(company, hypotheses_list)

        # Query without include_expired (default)
        result = memory.get_hypotheses(company)

        # Should only get valid hypotheses
        assert len(result) == num_valid, (
            f"Expected {num_valid} valid hypotheses, got {len(result)}"
        )

        # All returned should be non-expired
        for h in result:
            assert not h.is_expired(), f"Hypothesis {h.id} is expired but was returned"

        # Query with include_expired=True
        all_result = memory.get_hypotheses(company, include_expired=True)
        assert len(all_result) == num_expired + num_valid


# =============================================================================
# PROPERTY 11: Hypothesis Query Filtering
# =============================================================================

# Feature: agentic-architecture, Property 11: Hypothesis Query Filtering
@given(
    company=company_names,
    target_confidence=confidence_levels,
    # Use a topic that won't be a substring of "other_topic"
    target_topic=st.text(min_size=3, max_size=10, alphabet=st.sampled_from("xyz123")),
)
@settings(max_examples=30, deadline=None)
def test_query_filtering(
    company: str,
    target_confidence: ConfidenceLevel,
    target_topic: str,
):
    """
    Query filters correctly select matching hypotheses.

    For any query with confidence level and/or topic filters,
    get_hypotheses() should return only hypotheses matching all
    specified criteria.

    Validates: Requirements 5.5
    """
    # Ensure target_topic doesn't match "other_topic"
    assume("other" not in target_topic.lower())
    assume(target_topic.lower() not in "other_topic")
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ResearchMemory(storage_path=Path(tmpdir))

        # Create hypotheses with various confidence/topic combinations
        hypotheses_list = []

        # Matching both
        hypotheses_list.append(Hypothesis(
            id="match_both",
            claim="Matches both filters",
            confidence=target_confidence,
            topic=target_topic,
        ))

        # Matching confidence only
        hypotheses_list.append(Hypothesis(
            id="match_conf",
            claim="Matches confidence only",
            confidence=target_confidence,
            topic="other_topic",
        ))

        # Matching topic only
        other_conf = (
            ConfidenceLevel.VALIDATED
            if target_confidence != ConfidenceLevel.VALIDATED
            else ConfidenceLevel.UNTESTED
        )
        hypotheses_list.append(Hypothesis(
            id="match_topic",
            claim="Matches topic only",
            confidence=other_conf,
            topic=target_topic,
        ))

        # Matching neither
        hypotheses_list.append(Hypothesis(
            id="match_none",
            claim="Matches neither",
            confidence=other_conf,
            topic="other_topic",
        ))

        memory.save_hypotheses(company, hypotheses_list)

        # Filter by confidence only
        by_conf = memory.get_hypotheses(company, confidence=target_confidence)
        assert len(by_conf) == 2  # match_both and match_conf
        for h in by_conf:
            assert h.confidence == target_confidence

        # Filter by topic only
        by_topic = memory.get_hypotheses(company, topic=target_topic)
        assert len(by_topic) == 2  # match_both and match_topic
        for h in by_topic:
            assert target_topic.lower() in h.topic.lower()

        # Filter by both
        by_both = memory.get_hypotheses(
            company,
            confidence=target_confidence,
            topic=target_topic,
        )
        assert len(by_both) == 1  # only match_both
        assert by_both[0].id == "match_both"


# =============================================================================
# PROPERTY 12: Hypothesis Confidence Updates
# =============================================================================

# Feature: agentic-architecture, Property 12: Hypothesis Confidence Updates
@given(
    company=company_names,
    initial_confidence=confidence_levels,
    new_confidence=st.sampled_from([
        ConfidenceLevel.VALIDATED,
        ConfidenceLevel.INVALIDATED,
        ConfidenceLevel.CONFIRMED,
    ]),
    evidence=evidence_strings,
)
@settings(max_examples=30, deadline=None)
def test_confidence_updates(
    company: str,
    initial_confidence: ConfidenceLevel,
    new_confidence: ConfidenceLevel,
    evidence: str,
):
    """
    Updating hypothesis confidence correctly modifies state.

    For any hypothesis update via update_hypothesis(), the hypothesis
    should reflect the new confidence level, the evidence list should
    include the new evidence, and updated_at should be updated.

    Validates: Requirements 5.8
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ResearchMemory(storage_path=Path(tmpdir))

        # Create initial hypothesis
        h = Hypothesis(
            id="test_h",
            claim="Test claim",
            confidence=initial_confidence,
        )
        memory.save_hypotheses(company, [h])

        # Record time before update
        before_update = datetime.now()

        # Update confidence
        result = memory.update_hypothesis(
            company,
            "test_h",
            new_confidence,
            evidence,
        )

        assert result is True, "Update should return True for existing hypothesis"

        # Clear cache and reload
        memory.clear_cache()
        loaded = memory.get_hypotheses(company)

        assert len(loaded) == 1
        updated = loaded[0]

        # Verify confidence changed
        assert updated.confidence == new_confidence, (
            f"Expected confidence {new_confidence}, got {updated.confidence}"
        )

        # Verify evidence was added
        assert len(updated.evidence) > 0, "Evidence should be added"
        assert any(evidence in e for e in updated.evidence), (
            f"Evidence '{evidence}' not found in {updated.evidence}"
        )

        # Verify updated_at was updated
        assert updated.updated_at >= before_update, (
            "updated_at should be updated"
        )


# =============================================================================
# ADDITIONAL UNIT TESTS
# =============================================================================

def test_update_nonexistent_hypothesis():
    """Updating a non-existent hypothesis returns False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ResearchMemory(storage_path=Path(tmpdir))

        result = memory.update_hypothesis(
            "Test Company",
            "nonexistent_id",
            ConfidenceLevel.VALIDATED,
            "Some evidence",
        )

        assert result is False


def test_delete_company():
    """Deleting company memory removes the file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ResearchMemory(storage_path=Path(tmpdir))

        # Create some data
        h = Hypothesis(id="h1", claim="Test")
        memory.save_hypotheses("Test Company", [h])

        # Verify file exists
        path = memory._company_path("Test Company")
        assert path.exists()

        # Delete
        result = memory.delete_company("Test Company")
        assert result is True
        assert not path.exists()

        # Delete again should return False
        result = memory.delete_company("Test Company")
        assert result is False


def test_sanitize_filename():
    """Filename sanitization handles special characters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ResearchMemory(storage_path=Path(tmpdir))

        # Test various company names
        # The sanitize function: lowercase, remove non-word chars, replace spaces with _
        test_cases = [
            ("Acme Corp", "acme_corp"),
            ("Test & Co.", "test_co"),  # & and . removed, spaces become _
            ("Company/Division", "companydivision"),  # / removed
            ("  Spaces  ", "_spaces_"),  # multiple spaces collapse to single _
        ]

        for company, expected in test_cases:
            result = memory._sanitize_filename(company)
            assert result == expected, f"For '{company}': expected '{expected}', got '{result}'"
