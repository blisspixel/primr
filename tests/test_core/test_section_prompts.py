"""Unit tests for primr.core.section_prompts.

Pure-function tests for the four prompt builders + the persisted-feedback
loader extracted from research_agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import patch

import pytest

from primr.core.section_prompts import (
    _build_fast_analysis_prompt,
    _build_fast_batch_prompt,
    _build_fast_section_prompt,
    _build_link_selection_prompt,
    _load_fast_feedback_guidance,
)
from primr.qa.report_analyzer import SCAFFOLDING_PROHIBITION_GUIDANCE


@dataclass
class _FakeSection:
    """Minimal SectionConfig substitute carrying the attributes builders read."""

    id: str
    name: str = "Sample Section"
    purpose: str = "Explain the section."
    covers: list[str] = field(default_factory=lambda: ["item 1", "item 2"])
    depth: str | None = "Thorough analysis"
    position: str | None = "middle"
    part: int = 1


@dataclass
class _FakeGeneratedSection:
    """Minimal GeneratedSection substitute."""

    title: str
    content: str


# ---------------------------------------------------------------------------
# _load_fast_feedback_guidance
# ---------------------------------------------------------------------------


class TestLoadFastFeedbackGuidance:
    def test_returns_empty_when_file_missing(self, tmp_path, monkeypatch):
        # Point at a path that does not exist.
        monkeypatch.setattr(
            "primr.core.section_prompts.FAST_FEEDBACK_RULES_PATH",
            str(tmp_path / "missing.md"),
        )
        assert _load_fast_feedback_guidance() == ""

    def test_returns_file_contents(self, tmp_path, monkeypatch):
        path = tmp_path / "rules.md"
        path.write_text("guidance text", encoding="utf-8")
        monkeypatch.setattr("primr.core.section_prompts.FAST_FEEDBACK_RULES_PATH", str(path))
        assert _load_fast_feedback_guidance() == "guidance text"

    def test_returns_empty_when_file_blank(self, tmp_path, monkeypatch):
        path = tmp_path / "rules.md"
        path.write_text("   \n\n", encoding="utf-8")
        monkeypatch.setattr("primr.core.section_prompts.FAST_FEEDBACK_RULES_PATH", str(path))
        assert _load_fast_feedback_guidance() == ""

    def test_caps_at_4000_chars(self, tmp_path, monkeypatch):
        path = tmp_path / "rules.md"
        path.write_text("x" * 5_000, encoding="utf-8")
        monkeypatch.setattr("primr.core.section_prompts.FAST_FEEDBACK_RULES_PATH", str(path))
        assert len(_load_fast_feedback_guidance()) == 4_000

    def test_returns_empty_on_read_error(self, tmp_path, monkeypatch):
        path = tmp_path / "rules.md"
        path.write_text("text", encoding="utf-8")
        monkeypatch.setattr("primr.core.section_prompts.FAST_FEEDBACK_RULES_PATH", str(path))
        # Patch read_text to raise
        with patch(
            "primr.core.section_prompts.Path.read_text",
            side_effect=PermissionError("locked"),
        ):
            assert _load_fast_feedback_guidance() == ""


# ---------------------------------------------------------------------------
# _build_link_selection_prompt
# ---------------------------------------------------------------------------


class TestBuildLinkSelectionPrompt:
    def test_includes_core_fields(self):
        with patch(
            "primr.core.section_prompts.get_focus_areas_for_org_type",
            return_value=["leadership", "strategy"],
        ):
            prompt = _build_link_selection_prompt(
                company_name="Acme Corp",
                website="https://acme.example",
                links_text="- https://acme.example/about\n- https://acme.example/team",
                max_links=25,
                organization_type="commercial",
            )
        assert "Acme Corp" in prompt
        assert "https://acme.example" in prompt
        assert "commercial" in prompt
        assert "leadership" in prompt
        assert "strategy" in prompt
        assert "25" in prompt
        assert "/about" in prompt

    def test_focus_areas_bulleted(self):
        with patch(
            "primr.core.section_prompts.get_focus_areas_for_org_type",
            return_value=["alpha", "beta"],
        ):
            prompt = _build_link_selection_prompt(
                "C", "https://c.example", "links", 10, "commercial"
            )
        assert "- alpha" in prompt
        assert "- beta" in prompt


# ---------------------------------------------------------------------------
# _build_fast_analysis_prompt
# ---------------------------------------------------------------------------


class TestBuildFastAnalysisPrompt:
    def test_includes_company_and_website(self):
        prompt = _build_fast_analysis_prompt(
            "Acme Corp",
            "https://acme.example",
            "raw corpus text",
            "external sources text",
        )
        assert "Acme Corp" in prompt
        assert "https://acme.example" in prompt
        assert "raw corpus text" in prompt
        assert "external sources text" in prompt

    def test_handles_missing_website(self):
        prompt = _build_fast_analysis_prompt("Acme", None, "raw", "ext")
        assert "N/A" in prompt

    def test_structured_workbook_markers_present(self):
        prompt = _build_fast_analysis_prompt("Acme", "https://a.example", "r", "e")
        for marker in (
            "Structured Analysis Workbook",
            "Company Basics",
            "Competitive Landscape",
            "Strategic Hypotheses",
            "Discovery Questions",
        ):
            assert marker in prompt

    def test_repeats_company_name_in_consulting_guidance(self):
        # The prompt template references the company name multiple times to anchor
        # the consulting framing.
        prompt = _build_fast_analysis_prompt("UniqueCo", "https://u.example", "r", "e")
        assert prompt.count("UniqueCo") >= 2


# ---------------------------------------------------------------------------
# _build_fast_batch_prompt
# ---------------------------------------------------------------------------


class TestBuildFastBatchPrompt:
    def _build(self, **overrides):
        defaults = {
            "company_name": "Acme Corp",
            "website": "https://acme.example",
            "analysis_workbook": "WORKBOOK",
            "raw_corpus_subset": "RAW",
            "external_sources": "EXT",
            "source_urls": ["https://a.example", "https://b.example"],
            "sections": [_FakeSection(id="s1", name="Section One")],
            "previous_sections": [],
            "batch_number": 0,
            "total_batches": 3,
        }
        defaults.update(overrides)
        with patch(
            "primr.core.section_prompts._load_fast_feedback_guidance",
            return_value="",
        ):
            return _build_fast_batch_prompt(**defaults)

    def test_includes_batch_metadata(self):
        prompt = self._build()
        assert "Batch:** 1 of 3" in prompt
        assert "WORKBOOK" in prompt
        assert "RAW" in prompt
        assert "EXT" in prompt

    def test_includes_scaffolding_prohibition(self):
        # The batch writer must be told not to leak the markers the ship-time
        # gate strips (ROADMAP Active Queue #2).
        prompt = self._build()
        assert SCAFFOLDING_PROHIBITION_GUIDANCE in prompt

    def test_no_previous_sections_message(self):
        prompt = self._build(previous_sections=[])
        assert "first batch" in prompt

    def test_previous_sections_summarized(self):
        prior = [
            _FakeGeneratedSection("Prior A", "alpha " * 600),
            _FakeGeneratedSection("Prior B", "beta " * 50),
        ]
        prompt = self._build(previous_sections=prior)
        assert "Prior A" in prompt
        assert "Prior B" in prompt
        # 600-word section gets truncated to 400 + "..."; original "alpha" should still appear
        assert "alpha" in prompt

    def test_section_block_included(self):
        sections = [
            _FakeSection(
                id="s",
                name="My Section",
                purpose="explain X",
                covers=["topic 1", "topic 2"],
                depth="3 pages",
                position="anchor",
            )
        ]
        prompt = self._build(sections=sections)
        assert "My Section" in prompt
        assert "explain X" in prompt
        assert "topic 1" in prompt
        assert "topic 2" in prompt
        assert "3 pages" in prompt
        assert "anchor" in prompt

    def test_empty_sources_block(self):
        prompt = self._build(source_urls=[])
        assert "(no external sources)" in prompt

    def test_feedback_guidance_block_included_when_present(self):
        with patch(
            "primr.core.section_prompts._load_fast_feedback_guidance",
            return_value="REVISED RULES",
        ):
            prompt = _build_fast_batch_prompt(
                "Acme",
                "https://a.example",
                "WB",
                "RAW",
                "EXT",
                ["https://a.example"],
                [_FakeSection(id="s")],
                [],
                0,
                1,
            )
        assert "REVISED RULES" in prompt
        assert "FAST FEEDBACK GUIDANCE" in prompt

    def test_default_depth_when_missing(self):
        sections = [_FakeSection(id="s", depth=None, position=None)]
        prompt = self._build(sections=sections)
        assert "Thorough analysis" in prompt
        assert "middle" in prompt


# ---------------------------------------------------------------------------
# _build_fast_section_prompt
# ---------------------------------------------------------------------------


class TestBuildFastSectionPrompt:
    def _build(self, **overrides):
        defaults = {
            "company_name": "Acme",
            "website": "https://a.example",
            "analysis_workbook": "WB",
            "raw_corpus_subset": "RAW",
            "external_sources": "EXT",
            "source_urls": ["https://a.example/1"],
            "section": _FakeSection(id="executive_summary", name="Exec"),
            "written_sections": [],
            "section_index": 0,
            "all_section_names": ["Exec", "Other"],
            "reasoning_mode": "standard",
        }
        defaults.update(overrides)
        with patch(
            "primr.core.section_prompts._load_fast_feedback_guidance",
            return_value="",
        ):
            return _build_fast_section_prompt(**defaults)

    def test_toc_markers(self):
        prompt = self._build(all_section_names=["A", "B", "C"], section_index=1)
        assert "[DONE] A" in prompt
        assert "[NOW]  B" in prompt
        assert "[QUEUED] C" in prompt

    def test_includes_scaffolding_prohibition(self):
        # Single-section writer carries the same prohibition as the batch writer.
        prompt = self._build()
        assert SCAFFOLDING_PROHIBITION_GUIDANCE in prompt

    def test_first_section_message_when_no_previous(self):
        prompt = self._build(written_sections=[])
        assert "first section" in prompt

    def test_constrained_evidence_mode_text(self):
        prompt = self._build(reasoning_mode="constrained_evidence")
        assert "CONSTRAINED-EVIDENCE MODE" in prompt

    def test_standard_mode_text(self):
        prompt = self._build(reasoning_mode="standard")
        assert "STANDARD-EVIDENCE MODE" in prompt

    def test_framework_section_uses_full_prior_content(self):
        # Framework + executive_summary sections get FULL prior content, not 300-word trim.
        prior = [_FakeGeneratedSection("Prior", "word " * 1000)]
        prompt = self._build(
            section=_FakeSection(id="executive_summary", name="Exec"),
            written_sections=prior,
        )
        # Full content should produce many "word" occurrences (>= 400, well past 300).
        assert prompt.count("word") >= 500

    def test_regular_section_truncates_prior(self):
        prior = [_FakeGeneratedSection("Prior", "word " * 1000)]
        prompt = self._build(
            section=_FakeSection(id="other", name="Other", position="middle"),
            written_sections=prior,
        )
        # Trimmed at 300 words + "..." suffix
        assert "..." in prompt

    def test_word_target_reflects_section_id(self):
        prompt = self._build(section=_FakeSection(id="executive_summary", name="Exec"))
        assert "1,200" in prompt

    def test_word_target_default_for_unknown_id(self):
        prompt = self._build(section=_FakeSection(id="random", name="Random"))
        assert "800" in prompt

    def test_empty_sources_block(self):
        prompt = self._build(source_urls=[])
        assert "(no external sources)" in prompt

    def test_section_block_emitted_with_xml_envelope_instructions(self):
        prompt = self._build()
        assert "<section>" in prompt
        assert "<title>" in prompt
        assert "<body>" in prompt

    def test_missing_website_shows_na(self):
        prompt = self._build(website=None)
        assert "N/A" in prompt


@pytest.mark.parametrize(
    ("section_index", "total"),
    [(0, 5), (2, 5), (4, 5)],
)
def test_section_prompt_index_in_header(section_index, total):
    with patch(
        "primr.core.section_prompts._load_fast_feedback_guidance",
        return_value="",
    ):
        prompt = _build_fast_section_prompt(
            "Acme",
            "https://a.example",
            "WB",
            "RAW",
            "EXT",
            [],
            _FakeSection(id="s", name="Name"),
            [],
            section_index,
            [f"Name-{i}" for i in range(total)],
            reasoning_mode="standard",
        )
    assert f"Section:** {section_index + 1} of {total}" in prompt


# ---------------------------------------------------------------------------
# Prompt cache preparation (Active Queue #8): cached prefix / volatile suffix
# ---------------------------------------------------------------------------


class TestPromptCachePrefixSplit:
    """The prefix must be byte-identical across parallel section writes."""

    def _shared_kwargs(self):
        return {
            "company_name": "Acme Corp",
            "website": "https://acme.example",
            "analysis_workbook": "## Workbook\nshared analysis content",
            "raw_corpus_subset": "shared scraped corpus",
            "external_sources": "shared external research",
            "source_urls": ["https://a.example", "https://b.example"],
        }

    def _sections(self):
        return [
            _FakeSection(id="exec", name="Executive Summary", position="framework"),
            _FakeSection(id="market", name="Market Landscape"),
            _FakeSection(id="tech", name="Technology Stack"),
        ]

    def test_section_prefix_identical_across_sections(self, tmp_path, monkeypatch):
        from primr.core.section_prompts import build_fast_section_prompt_parts

        monkeypatch.setattr(
            "primr.core.section_prompts.FAST_FEEDBACK_RULES_PATH",
            str(tmp_path / "missing.md"),
        )
        sections = self._sections()
        names = [s.name for s in sections]
        written = [_FakeGeneratedSection(title="Intro", content="intro words " * 50)]

        prefixes = []
        suffixes = []
        for idx, section in enumerate(sections):
            prefix, suffix = build_fast_section_prompt_parts(
                **self._shared_kwargs(),
                section=section,
                written_sections=written,
                section_index=idx,
                all_section_names=names,
                reasoning_mode="standard" if idx != 2 else "constrained_evidence",
            )
            prefixes.append(prefix)
            suffixes.append(suffix)

        # Byte-identical prefix across all parallel writes — this is the
        # cacheable unit. Different sections, indexes, and reasoning modes
        # must not perturb it.
        assert prefixes[0] == prefixes[1] == prefixes[2]
        # Suffixes carry the per-section variation.
        assert len(set(suffixes)) == 3

    def test_prefix_contains_shared_context_only(self, tmp_path, monkeypatch):
        from primr.core.section_prompts import build_fast_section_prompt_parts

        monkeypatch.setattr(
            "primr.core.section_prompts.FAST_FEEDBACK_RULES_PATH",
            str(tmp_path / "missing.md"),
        )
        section = _FakeSection(id="market", name="Market Landscape")
        prefix, suffix = build_fast_section_prompt_parts(
            **self._shared_kwargs(),
            section=section,
            written_sections=[_FakeGeneratedSection(title="Done Sec", content="prior words")],
            section_index=1,
            all_section_names=["Done Sec", "Market Landscape"],
        )

        # Shared context lives in the prefix
        assert "shared analysis content" in prefix
        assert "shared scraped corpus" in prefix
        assert "shared external research" in prefix
        assert "https://a.example" in prefix
        assert SCAFFOLDING_PROHIBITION_GUIDANCE in prefix
        # Per-section content must NOT leak into the prefix
        assert "Market Landscape" not in prefix
        assert "REPORT TABLE OF CONTENTS" not in prefix
        assert "Done Sec" not in prefix
        # ...and lives in the suffix instead
        assert "Market Landscape" in suffix
        assert "REPORT TABLE OF CONTENTS" in suffix
        assert "PREVIOUS SECTIONS" in suffix
        assert "LENGTH:" in suffix

    def test_full_prompt_is_prefix_plus_suffix(self, tmp_path, monkeypatch):
        from primr.core.section_prompts import build_fast_section_prompt_parts

        monkeypatch.setattr(
            "primr.core.section_prompts.FAST_FEEDBACK_RULES_PATH",
            str(tmp_path / "missing.md"),
        )
        section = _FakeSection(id="market", name="Market Landscape")
        kwargs = {
            **self._shared_kwargs(),
            "section": section,
            "written_sections": [],
            "section_index": 0,
            "all_section_names": ["Market Landscape"],
        }
        prefix, suffix = build_fast_section_prompt_parts(**kwargs)
        assert _build_fast_section_prompt(**kwargs) == prefix + suffix

    def test_batch_prefix_identical_across_batches(self, tmp_path, monkeypatch):
        from primr.core.section_prompts import build_fast_batch_prompt_parts

        monkeypatch.setattr(
            "primr.core.section_prompts.FAST_FEEDBACK_RULES_PATH",
            str(tmp_path / "missing.md"),
        )
        sections = self._sections()

        prefix_one, suffix_one = build_fast_batch_prompt_parts(
            **self._shared_kwargs(),
            sections=sections[:2],
            previous_sections=[],
            batch_number=0,
            total_batches=2,
        )
        prefix_two, suffix_two = build_fast_batch_prompt_parts(
            **self._shared_kwargs(),
            sections=sections[2:],
            previous_sections=[_FakeGeneratedSection(title="Exec", content="words " * 20)],
            batch_number=1,
            total_batches=2,
        )

        assert prefix_one == prefix_two
        assert suffix_one != suffix_two
        assert "Batch: 1 of 2" in suffix_one.replace("**", "")
        assert "Batch: 2 of 2" in suffix_two.replace("**", "")


# ---------------------------------------------------------------------------
# Research framing threading (tradecraft Step 1): the operator-intent block
# must reach the workbook + section prompts, sit in the cacheable prefix only,
# and leave the prompt byte-identical when no framing was supplied.
# ---------------------------------------------------------------------------

_FRAMING_TOKEN = "FRAMING_INTENT_TOKEN_XYZ"
_FRAMING_BLOCK = (
    "=== RESEARCH FRAMING (operator intent) ===\n"
    f"Core question: {_FRAMING_TOKEN}\n"
    "=== END RESEARCH FRAMING ==="
)


class TestFramingThreadsIntoPrompts:
    def _shared_kwargs(self):
        return {
            "company_name": "Acme Corp",
            "website": "https://acme.example",
            "analysis_workbook": "## Workbook\nshared analysis content",
            "raw_corpus_subset": "shared scraped corpus",
            "external_sources": "shared external research",
            "source_urls": ["https://a.example"],
        }

    def _missing_feedback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "primr.core.section_prompts.FAST_FEEDBACK_RULES_PATH",
            str(tmp_path / "missing.md"),
        )

    def test_analysis_prompt_includes_framing_when_supplied(self):
        from primr.core.section_prompts import _build_fast_analysis_prompt

        with_framing = _build_fast_analysis_prompt(
            "Acme Corp", "https://acme.example", "corpus", "ext", framing_block=_FRAMING_BLOCK
        )
        assert _FRAMING_TOKEN in with_framing

    def test_analysis_prompt_unchanged_when_framing_empty(self):
        from primr.core.section_prompts import _build_fast_analysis_prompt

        baseline = _build_fast_analysis_prompt("Acme Corp", "https://acme.example", "corpus", "ext")
        empty = _build_fast_analysis_prompt(
            "Acme Corp", "https://acme.example", "corpus", "ext", framing_block=""
        )
        assert baseline == empty
        assert _FRAMING_TOKEN not in baseline

    def test_section_framing_in_prefix_not_suffix(self, tmp_path, monkeypatch):
        from primr.core.section_prompts import build_fast_section_prompt_parts

        self._missing_feedback(tmp_path, monkeypatch)
        prefix, suffix = build_fast_section_prompt_parts(
            **self._shared_kwargs(),
            section=_FakeSection(id="market", name="Market Landscape"),
            written_sections=[],
            section_index=0,
            all_section_names=["Market Landscape"],
            framing_block=_FRAMING_BLOCK,
        )
        # Framing is run-shared -> belongs in the cacheable prefix, never the suffix.
        assert _FRAMING_TOKEN in prefix
        assert _FRAMING_TOKEN not in suffix

    def test_section_prefix_unchanged_when_framing_empty(self, tmp_path, monkeypatch):
        from primr.core.section_prompts import build_fast_section_prompt_parts

        self._missing_feedback(tmp_path, monkeypatch)
        kwargs = dict(
            **self._shared_kwargs(),
            section=_FakeSection(id="market", name="Market Landscape"),
            written_sections=[],
            section_index=0,
            all_section_names=["Market Landscape"],
        )
        baseline_prefix, _ = build_fast_section_prompt_parts(**kwargs)
        empty_prefix, _ = build_fast_section_prompt_parts(**kwargs, framing_block="")
        assert baseline_prefix == empty_prefix
        assert _FRAMING_TOKEN not in baseline_prefix

    def test_section_prefix_identical_across_sections_with_framing(self, tmp_path, monkeypatch):
        from primr.core.section_prompts import build_fast_section_prompt_parts

        self._missing_feedback(tmp_path, monkeypatch)
        names = ["Market Landscape", "Technology Stack"]
        prefixes = []
        for idx, name in enumerate(names):
            prefix, _ = build_fast_section_prompt_parts(
                **self._shared_kwargs(),
                section=_FakeSection(id=str(idx), name=name),
                written_sections=[],
                section_index=idx,
                all_section_names=names,
                framing_block=_FRAMING_BLOCK,
            )
            prefixes.append(prefix)
        # Run-shared framing must not break the byte-identical cached prefix (#8).
        assert prefixes[0] == prefixes[1]
        assert _FRAMING_TOKEN in prefixes[0]

    def test_batch_prefix_includes_framing(self, tmp_path, monkeypatch):
        from primr.core.section_prompts import build_fast_batch_prompt_parts

        self._missing_feedback(tmp_path, monkeypatch)
        prefix, suffix = build_fast_batch_prompt_parts(
            **self._shared_kwargs(),
            sections=[_FakeSection(id="market", name="Market Landscape")],
            previous_sections=[],
            batch_number=0,
            total_batches=1,
            framing_block=_FRAMING_BLOCK,
        )
        assert _FRAMING_TOKEN in prefix
        assert _FRAMING_TOKEN not in suffix
