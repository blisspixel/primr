"""Unit tests for primr.core.section_planning.

Pure-function tests for word-target / max-token sizing, reasoning-mode
selection, and the YAML-loading section grouper.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from primr.core.section_planning import (
    _HIGH_DEPTH_SECTION_IDS,
    _PART_LABELS,
    _determine_section_reasoning_mode,
    _get_section_max_tokens,
    _get_section_word_target,
    _group_sections_by_part,
)


@dataclass
class _FakeSection:
    """Minimal SectionConfig stand-in carrying just the attributes we read."""

    id: str
    depth: str | None = ""
    position: str | None = "middle"
    part: int = 1


class TestPartLabels:
    def test_has_all_five_parts(self):
        assert set(_PART_LABELS) == {1, 2, 3, 4, 5}

    def test_labels_are_strings(self):
        for label in _PART_LABELS.values():
            assert isinstance(label, str)
            assert label


class TestHighDepthSectionIds:
    def test_known_ids_present(self):
        for known in (
            "executive_summary",
            "competitive_landscape",
            "company_history",
            "engagement_opportunities",
        ):
            assert known in _HIGH_DEPTH_SECTION_IDS

    def test_is_frozenset(self):
        assert isinstance(_HIGH_DEPTH_SECTION_IDS, frozenset)


class TestGetSectionWordTarget:
    def test_high_depth_id_returns_1200(self):
        section = _FakeSection(id="executive_summary", depth="thorough")
        assert _get_section_word_target(section) == 1_200

    def test_depth_mentions_pages_returns_1200(self):
        section = _FakeSection(id="other_id", depth="3 pages of analysis")
        assert _get_section_word_target(section) == 1_200

    def test_depth_mentions_comprehensive_returns_1200(self):
        section = _FakeSection(id="other_id", depth="Comprehensive treatment")
        assert _get_section_word_target(section) == 1_200

    def test_framework_position_returns_800(self):
        section = _FakeSection(id="swot", depth="standard", position="framework")
        assert _get_section_word_target(section) == 800

    def test_default_returns_800(self):
        section = _FakeSection(id="anything", depth="default analysis")
        assert _get_section_word_target(section) == 800

    def test_handles_none_depth(self):
        section = _FakeSection(id="x", depth=None)
        assert _get_section_word_target(section) == 800

    def test_depth_case_insensitive(self):
        section = _FakeSection(id="x", depth="3 PAGES TOTAL")
        assert _get_section_word_target(section) == 1_200


class TestGetSectionMaxTokens:
    def test_high_depth_section_returns_6000(self):
        section = _FakeSection(id="executive_summary", depth="")
        assert _get_section_max_tokens(section) == 6_000

    def test_default_section_returns_4000(self):
        section = _FakeSection(id="generic", depth="")
        assert _get_section_max_tokens(section) == 4_000

    def test_framework_section_returns_4000(self):
        section = _FakeSection(id="swot", depth="", position="framework")
        assert _get_section_max_tokens(section) == 4_000


class TestDetermineSectionReasoningMode:
    def test_unknown_section_id_returns_standard(self):
        section = _FakeSection(id="unknown_id")
        assert _determine_section_reasoning_mode(section, "workbook content") == "standard"

    def test_financial_profile_with_evidence_returns_standard(self):
        section = _FakeSection(id="financial_profile")
        workbook = "Revenue grew 12% with healthy margin"
        assert _determine_section_reasoning_mode(section, workbook) == "standard"

    def test_financial_profile_without_evidence_returns_constrained(self):
        section = _FakeSection(id="financial_profile")
        workbook = "No financial info here at all"
        assert _determine_section_reasoning_mode(section, workbook) == "constrained_evidence"

    def test_company_history_with_evidence(self):
        section = _FakeSection(id="company_history")
        workbook = "Founded in 2010, completed an acquisition in 2015"
        assert _determine_section_reasoning_mode(section, workbook) == "standard"

    def test_company_history_without_evidence(self):
        section = _FakeSection(id="company_history")
        assert (
            _determine_section_reasoning_mode(section, "irrelevant content")
            == "constrained_evidence"
        )

    def test_industry_outlook_with_evidence(self):
        section = _FakeSection(id="industry_outlook")
        workbook = "Industry trend points to consolidation"
        assert _determine_section_reasoning_mode(section, workbook) == "standard"

    def test_industry_outlook_without_evidence(self):
        section = _FakeSection(id="industry_outlook")
        assert _determine_section_reasoning_mode(section, "") == "constrained_evidence"

    def test_empty_workbook_returns_constrained_for_known_id(self):
        section = _FakeSection(id="financial_profile")
        assert _determine_section_reasoning_mode(section, "") == "constrained_evidence"

    def test_none_workbook_returns_constrained_for_known_id(self):
        section = _FakeSection(id="financial_profile")
        assert _determine_section_reasoning_mode(section, None) == "constrained_evidence"

    def test_case_insensitive_match(self):
        section = _FakeSection(id="financial_profile")
        assert _determine_section_reasoning_mode(section, "REVENUE is strong") == "standard"


class TestGroupSectionsByPart:
    def test_groups_in_part_order(self):
        # Build a fake config with sections in parts 1, 2, 3 (out of order).
        sections = [
            _FakeSection(id="a", part=3),
            _FakeSection(id="b", part=1),
            _FakeSection(id="c", part=2),
            _FakeSection(id="d", part=1),
        ]
        config = MagicMock()
        config.sections = sections

        with patch(
            "primr.prompts.loader.load_prompt_config",
            return_value=config,
        ):
            groups = _group_sections_by_part()

        # Three buckets, sorted by part number ascending
        assert len(groups) == 3
        assert [s.id for s in groups[0]] == ["b", "d"]  # part 1
        assert [s.id for s in groups[1]] == ["c"]  # part 2
        assert [s.id for s in groups[2]] == ["a"]  # part 3

    def test_handles_single_part(self):
        sections = [_FakeSection(id="x", part=1)]
        config = MagicMock()
        config.sections = sections

        with patch(
            "primr.prompts.loader.load_prompt_config",
            return_value=config,
        ):
            groups = _group_sections_by_part()

        assert len(groups) == 1
        assert groups[0][0].id == "x"


@pytest.mark.parametrize(
    ("section_id", "expected_words"),
    [
        ("executive_summary", 1_200),
        ("competitive_landscape", 1_200),
        ("company_history", 1_200),
        ("engagement_opportunities", 1_200),
        ("financial_profile", 800),
        ("industry_outlook", 800),
    ],
)
def test_word_target_for_canonical_section_ids(section_id, expected_words):
    section = _FakeSection(id=section_id)
    assert _get_section_word_target(section) == expected_words
