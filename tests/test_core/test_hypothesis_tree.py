"""Tests for the Day-1 hypothesis tree (tradecraft Step 2).

Pure and deterministic - the LLM is injected. Covers the data model and its
serialization, the agentic-Hypothesis adapter, the markdown artifact, the
prompt builder, tolerant JSON parsing, and the generate orchestrator (including
the fail-soft paths).
"""

from __future__ import annotations

import json

from primr.agentic.models import ConfidenceLevel, Hypothesis
from primr.core.hypothesis_tree import (
    DiagnosticHypothesis,
    HypothesisTree,
    IssueBranch,
    build_hypothesis_tree_prompt,
    generate_hypothesis_tree,
    parse_hypothesis_tree,
)


def _sample_tree() -> HypothesisTree:
    return HypothesisTree(
        company="Acme Corp",
        core_question="Is there a near-term cloud-migration budget?",
        branches=(
            IssueBranch(
                issue="What is their infrastructure posture?",
                hypotheses=(
                    DiagnosticHypothesis(
                        claim="They are mid-migration to Azure",
                        supporting=("Azure DNS records", "hiring for Azure roles"),
                        counter=("Legacy on-prem job postings still open",),
                        test_question="Do recent job posts require Azure or on-prem skills?",
                    ),
                ),
            ),
        ),
    )


class TestDiagnosticHypothesis:
    def test_roundtrip(self):
        h = DiagnosticHypothesis(
            claim="c",
            supporting=("s1", "s2"),
            counter=("x",),
            test_question="q?",
            confidence=ConfidenceLevel.UNTESTED,
        )
        assert DiagnosticHypothesis.from_dict(h.to_dict()) == h

    def test_from_dict_tolerates_missing_fields(self):
        h = DiagnosticHypothesis.from_dict({"claim": "only claim"})
        assert h.claim == "only claim"
        assert h.supporting == ()
        assert h.counter == ()
        assert h.test_question == ""
        assert h.confidence is ConfidenceLevel.UNTESTED

    def test_from_dict_trims_and_drops_empty_evidence(self):
        h = DiagnosticHypothesis.from_dict({"claim": " c ", "supporting": [" a ", "", "  ", "b"]})
        assert h.claim == "c"
        assert h.supporting == ("a", "b")

    def test_to_agentic_hypothesis_adapter(self):
        h = DiagnosticHypothesis(claim="they sell to SMB", supporting=("pricing page",))
        agentic = h.to_agentic_hypothesis(node_id="h1", topic="GTM")
        assert isinstance(agentic, Hypothesis)
        assert agentic.id == "h1"
        assert agentic.claim == "they sell to SMB"
        assert agentic.topic == "GTM"
        assert agentic.evidence == ["pricing page"]
        assert agentic.confidence is ConfidenceLevel.UNTESTED


class TestTreeSerialization:
    def test_roundtrip(self):
        tree = _sample_tree()
        assert HypothesisTree.from_dict(tree.to_dict()) == tree

    def test_to_json_is_valid_json(self):
        tree = _sample_tree()
        loaded = json.loads(tree.to_json())
        assert loaded["company"] == "Acme Corp"
        assert loaded["branches"][0]["hypotheses"][0]["claim"] == "They are mid-migration to Azure"

    def test_from_dict_skips_malformed_branches_and_hypotheses(self):
        data = {
            "company": "Acme",
            "branches": [
                {"issue": "", "hypotheses": [{"claim": "x"}]},  # no issue -> dropped
                {"issue": "Good", "hypotheses": [{"claim": ""}, {"claim": "kept"}]},
                "not-a-dict",
            ],
        }
        tree = HypothesisTree.from_dict(data)
        assert len(tree.branches) == 1
        assert tree.branches[0].issue == "Good"
        assert len(tree.branches[0].hypotheses) == 1
        assert tree.branches[0].hypotheses[0].claim == "kept"


class TestTreeHelpers:
    def test_is_empty_true_when_no_hypotheses(self):
        assert HypothesisTree(company="A").is_empty is True
        assert HypothesisTree(company="A", branches=(IssueBranch(issue="i"),)).is_empty is True

    def test_is_empty_false_with_a_hypothesis(self):
        assert _sample_tree().is_empty is False

    def test_iter_hypotheses(self):
        pairs = list(_sample_tree().iter_hypotheses())
        assert len(pairs) == 1
        branch, hyp = pairs[0]
        assert branch.issue.startswith("What is their")
        assert hyp.claim.startswith("They are mid-migration")


class TestMarkdown:
    def test_empty_tree_markdown(self):
        md = HypothesisTree(company="Acme Corp").to_markdown()
        assert "Day-1 Hypothesis Tree: Acme Corp" in md
        assert "No hypotheses formed" in md

    def test_populated_markdown_contains_fields(self):
        md = _sample_tree().to_markdown()
        assert "Core question:" in md
        assert "What is their infrastructure posture?" in md
        assert "They are mid-migration to Azure" in md
        assert "Supporting:" in md
        assert "Counter / alternative:" in md
        assert "Test:" in md
        assert "untested" in md


class TestPromptBuilder:
    def test_includes_signals_and_company(self):
        prompt = build_hypothesis_tree_prompt(
            company="Acme Corp",
            core_question="moat?",
            recon_summary="Azure DNS",
            homepage_text="We optimize logistics",
            hiring_summary="Hiring 3 ML engineers",
        )
        assert "Acme Corp" in prompt
        assert "moat?" in prompt
        assert "Azure DNS" in prompt
        assert "We optimize logistics" in prompt
        assert "Hiring 3 ML engineers" in prompt
        assert "MECE" in prompt

    def test_labels_empty_sections(self):
        prompt = build_hypothesis_tree_prompt(
            company="Acme",
            core_question="",
            recon_summary="",
            homepage_text="",
            hiring_summary="",
        )
        assert "(none)" in prompt
        # No core-question line when none supplied.
        assert "core question is:" not in prompt


class TestParse:
    def test_parses_clean_json(self):
        raw = json.dumps(
            {
                "branches": [
                    {
                        "issue": "Posture",
                        "hypotheses": [
                            {
                                "claim": "Azure migration",
                                "supporting": ["dns"],
                                "counter": ["legacy roles"],
                                "test_question": "azure or on-prem?",
                            }
                        ],
                    }
                ]
            }
        )
        tree = parse_hypothesis_tree(raw, company="Acme", core_question="q?")
        assert tree.company == "Acme"
        assert tree.core_question == "q?"
        assert tree.branches[0].hypotheses[0].claim == "Azure migration"

    def test_parses_fenced_json(self):
        raw = '```json\n{"branches": [{"issue": "I", "hypotheses": [{"claim": "c"}]}]}\n```'
        tree = parse_hypothesis_tree(raw, company="Acme")
        assert tree.branches[0].hypotheses[0].claim == "c"

    def test_parses_json_embedded_in_prose(self):
        raw = 'Here is the tree:\n{"branches": [{"issue": "I", "hypotheses": [{"claim": "c"}]}]}\nDone.'
        tree = parse_hypothesis_tree(raw, company="Acme")
        assert tree.branches[0].issue == "I"

    def test_unparseable_returns_empty_tree(self):
        tree = parse_hypothesis_tree("not json at all", company="Acme", core_question="q")
        assert tree.is_empty
        assert tree.company == "Acme"
        assert tree.core_question == "q"

    def test_blank_returns_empty_tree(self):
        assert parse_hypothesis_tree("   ", company="Acme").is_empty


class TestGenerate:
    def test_generate_with_injected_llm(self):
        canned = json.dumps({"branches": [{"issue": "I", "hypotheses": [{"claim": "the claim"}]}]})
        captured = {}

        def fake_llm(prompt: str) -> str:
            captured["prompt"] = prompt
            return canned

        tree = generate_hypothesis_tree(
            company="Acme Corp",
            core_question="moat?",
            recon_summary="Azure DNS",
            llm=fake_llm,
        )
        assert "Acme Corp" in captured["prompt"]
        assert tree.branches[0].hypotheses[0].claim == "the claim"

    def test_generate_failsoft_on_llm_error(self):
        def boom(_prompt: str) -> str:
            raise RuntimeError("model down")

        tree = generate_hypothesis_tree(company="Acme", core_question="q", llm=boom)
        assert tree.is_empty
        assert tree.company == "Acme"
        assert tree.core_question == "q"

    def test_generate_failsoft_on_garbage_output(self):
        tree = generate_hypothesis_tree(company="Acme", llm=lambda _p: "sorry, no JSON")
        assert tree.is_empty
