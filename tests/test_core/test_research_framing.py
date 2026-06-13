"""Tests for ResearchFraming: the typed operator-intent object (tradecraft Step 1).

Pure and deterministic - no LLM, no network. Pins the two invariants the rest
of the pipeline relies on: an unspecified framing renders to an empty prompt
block (backward compatibility), and a specified one renders a stable,
delimited block containing exactly the supplied fields.
"""

from __future__ import annotations

import pytest

from primr.core.research_framing import (
    EMPTY_FRAMING,
    ResearchFraming,
    ResearchPurpose,
    resolve_run_framing,
)


class TestResearchPurpose:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("sales_pursuit", ResearchPurpose.SALES_PURSUIT),
            ("Sales-Pursuit", ResearchPurpose.SALES_PURSUIT),
            ("  DILIGENCE  ", ResearchPurpose.DILIGENCE),
            ("competitive intel", ResearchPurpose.COMPETITIVE_INTEL),
            ("partnership", ResearchPurpose.PARTNERSHIP),
            ("general", ResearchPurpose.GENERAL),
        ],
    )
    def test_from_str_parses_leniently(self, raw, expected):
        assert ResearchPurpose.from_str(raw) is expected

    @pytest.mark.parametrize("raw", [None, "", "nonsense", "ai_strategy"])
    def test_from_str_unknown_defaults_general(self, raw):
        assert ResearchPurpose.from_str(raw) is ResearchPurpose.GENERAL

    def test_every_member_has_a_label(self):
        for member in ResearchPurpose:
            assert isinstance(member.label, str)
            assert member.label

    def test_str_is_value(self):
        assert str(ResearchPurpose.SALES_PURSUIT) == "sales_pursuit"


class TestIsSpecified:
    def test_empty_is_not_specified(self):
        assert ResearchFraming().is_specified is False
        assert EMPTY_FRAMING.is_specified is False

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"audience": "VP Sales"},
            {"decision": "prioritize the account"},
            {"core_question": "is there budget?"},
            {"discovery_notes": "met them at a conference"},
            {"purpose": ResearchPurpose.DILIGENCE},
        ],
    )
    def test_any_field_makes_it_specified(self, kwargs):
        assert ResearchFraming(**kwargs).is_specified is True

    def test_general_purpose_alone_is_not_specified(self):
        assert ResearchFraming(purpose=ResearchPurpose.GENERAL).is_specified is False


class TestFromInputs:
    def test_trims_and_parses(self):
        f = ResearchFraming.from_inputs(
            purpose="diligence",
            audience="  the IC  ",
            decision="  go / no-go  ",
            core_question="  durable moat?  ",
            discovery_notes="  notes  ",
        )
        assert f.purpose is ResearchPurpose.DILIGENCE
        assert f.audience == "the IC"
        assert f.decision == "go / no-go"
        assert f.core_question == "durable moat?"
        assert f.discovery_notes == "notes"

    def test_all_none_is_empty(self):
        assert ResearchFraming.from_inputs() == ResearchFraming()

    def test_accepts_enum_purpose(self):
        f = ResearchFraming.from_inputs(purpose=ResearchPurpose.PARTNERSHIP)
        assert f.purpose is ResearchPurpose.PARTNERSHIP


class TestToPromptBlock:
    def test_unspecified_renders_empty(self):
        assert ResearchFraming().to_prompt_block() == ""

    def test_includes_only_supplied_fields(self):
        block = ResearchFraming(
            purpose=ResearchPurpose.SALES_PURSUIT,
            core_question="near-term cloud budget?",
        ).to_prompt_block()
        assert "Purpose: Sales pursuit" in block
        assert "Core question: near-term cloud budget?" in block
        assert "Audience:" not in block
        assert "Decision this informs:" not in block
        assert "Operator discovery notes:" not in block

    def test_general_purpose_line_omitted(self):
        block = ResearchFraming(audience="the board").to_prompt_block()
        assert "Purpose:" not in block
        assert "Audience: the board" in block

    def test_discovery_notes_rendered_last(self):
        block = ResearchFraming(
            audience="VP Sales", discovery_notes="UNIQUE_NOTE_TOKEN"
        ).to_prompt_block()
        assert block.index("UNIQUE_NOTE_TOKEN") > block.index("Audience:")

    def test_block_is_delimited(self):
        block = ResearchFraming(core_question="x").to_prompt_block()
        assert block.startswith("=== RESEARCH FRAMING (operator intent) ===")
        assert "=== END RESEARCH FRAMING ===" in block


class TestSerialization:
    def test_roundtrip(self):
        original = ResearchFraming.from_inputs(
            purpose="competitive_intel",
            audience="strategy team",
            decision="where to compete",
            core_question="what is their wedge?",
            discovery_notes="multi\nline\nnotes",
        )
        assert ResearchFraming.from_dict(original.to_dict()) == original

    def test_from_dict_none_is_empty(self):
        assert ResearchFraming.from_dict(None) == ResearchFraming()

    def test_to_dict_keys_stable(self):
        keys = set(ResearchFraming().to_dict())
        assert keys == {"purpose", "audience", "decision", "core_question", "discovery_notes"}


class TestResolveRunFraming:
    def test_no_inputs_returns_neutral_framing(self):
        framing, notes, error = resolve_run_framing()
        assert error is None
        assert notes is None
        assert framing == ResearchFraming()
        assert framing.is_specified is False

    def test_facets_only_no_notes(self):
        framing, notes, error = resolve_run_framing(purpose="diligence", core_question="moat?")
        assert error is None
        assert notes is None
        assert framing.purpose is ResearchPurpose.DILIGENCE
        assert framing.core_question == "moat?"

    def test_loads_discovery_notes_file(self, tmp_path):
        notes_file = tmp_path / "notes.md"
        notes_file.write_text("  met them at a conference  ", encoding="utf-8")
        framing, notes, error = resolve_run_framing(
            discovery_notes_path=str(notes_file), audience="VP Sales"
        )
        assert error is None
        assert notes == "met them at a conference"
        assert framing.discovery_notes == "met them at a conference"
        assert framing.audience == "VP Sales"

    def test_missing_file_returns_error(self, tmp_path):
        framing, notes, error = resolve_run_framing(discovery_notes_path=str(tmp_path / "nope.md"))
        assert framing is None
        assert notes is None
        assert error is not None
        assert "not found" in error

    def test_empty_file_is_not_an_error(self, tmp_path):
        notes_file = tmp_path / "empty.md"
        notes_file.write_text("   \n\n", encoding="utf-8")
        framing, notes, error = resolve_run_framing(discovery_notes_path=str(notes_file))
        assert error is None
        assert notes is None
        assert framing == ResearchFraming()
