"""Tests that the Phase 5/6 section-regeneration prompts carry the scaffolding
prohibition.

These are the regeneration counterparts to the Phase 4 writer prompts in
section_prompts.py. Like the writer, they must instruct the model not to emit
the internal-scaffolding markers the ship-time gate strips, so a regenerated
weak section does not reintroduce drift the original cleanup removed (ROADMAP
Active Queue #2). We monkeypatch the LLM boundary and inspect the captured
prompt rather than making a live call.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.ai.routing import Role
from primr.core import section_regeneration
from primr.core.research_agent import (
    _fast_regenerate_section,
    _strategy_regenerate_section,
)
from primr.qa.report_analyzer import SCAFFOLDING_PROHIBITION_GUIDANCE


class TestFastRegenerateSectionPrompt:
    def test_default_model_comes_directly_from_routing(self, monkeypatch):
        routed_roles = []
        call = MagicMock(return_value="## Competitive Landscape\n\nrewritten body")
        monkeypatch.setattr(
            section_regeneration,
            "pick_model_for_role",
            lambda role: routed_roles.append(role) or "routed-writing-model",
        )
        monkeypatch.setattr("primr.pipeline.llm_failover.call_with_failover", call)

        _fast_regenerate_section(
            company_name="Acme Corp",
            website="https://acme.example",
            section_title="Competitive Landscape",
            section_content="## Competitive Landscape\n\noriginal body",
            analysis_workbook="WORKBOOK",
            new_evidence="NEW EVIDENCE",
            source_urls=["https://a.example"],
        )

        assert routed_roles == [Role.WRITING]
        assert call.call_args.kwargs["preferred_model"] == "routed-writing-model"

    def test_prompt_includes_scaffolding_prohibition(self, monkeypatch):
        mock = MagicMock(return_value="## Competitive Landscape\n\nrewritten body")
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock)
        _fast_regenerate_section(
            company_name="Acme Corp",
            website="https://acme.example",
            section_title="Competitive Landscape",
            section_content="## Competitive Landscape\n\noriginal body",
            analysis_workbook="WORKBOOK",
            new_evidence="NEW EVIDENCE",
            source_urls=["https://a.example"],
        )
        prompt = mock.call_args.args[0]
        assert SCAFFOLDING_PROHIBITION_GUIDANCE in prompt


class TestStrategyRegenerateSectionPrompt:
    def test_prompt_includes_scaffolding_prohibition(self, monkeypatch):
        mock = MagicMock(return_value="## Migration Path\n\nrewritten body")
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock)
        _strategy_regenerate_section(
            company_name="Acme Corp",
            vendor="azure",
            section_title="Migration Path",
            section_content="## Migration Path\n\noriginal body",
            new_evidence="NEW EVIDENCE",
            analysis_workbook="WORKBOOK",
        )
        prompt = mock.call_args.args[0]
        assert SCAFFOLDING_PROHIBITION_GUIDANCE in prompt
        assert "business-first AI strategy" in prompt
        assert "not a predetermined vendor answer" in prompt
        assert "Name services, prices" in prompt

    def test_generic_strategy_is_not_reframed_as_ai(self, monkeypatch):
        mock = MagicMock(return_value="## Service Model\n\nrewritten body")
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock)

        _strategy_regenerate_section(
            company_name="Acme Corp",
            vendor="Customer Experience",
            section_title="Service Model",
            section_content="## Service Model\n\noriginal body",
            new_evidence="NEW EVIDENCE",
            analysis_workbook="WORKBOOK",
            label="Customer Experience",
        )

        prompt = mock.call_args.args[0]
        assert "Customer Experience document" in prompt
        assert "business-first AI strategy" not in prompt
        assert "PLATFORM EVALUATION EMPHASIS" not in prompt

    def test_prompt_requires_plain_text_validate_line(self, monkeypatch):
        # The strategy-regen prompt previously lacked the plain-text "What to
        # validate:" instruction the batch/section writers carry; closing that
        # gap is part of the same hardening.
        mock = MagicMock(return_value="## Migration Path\n\nrewritten body")
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock)
        _strategy_regenerate_section(
            company_name="Acme Corp",
            vendor="azure",
            section_title="Migration Path",
            section_content="## Migration Path\n\noriginal body",
            new_evidence="NEW EVIDENCE",
            analysis_workbook="WORKBOOK",
        )
        prompt = mock.call_args.args[0]
        assert "plain text" in prompt
