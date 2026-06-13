"""Day-1 hypothesis tree (tradecraft Step 2).

Elite research teams form a provisional answer on day one and gather evidence
to *refute* it, rather than collecting everything and then looking for a story.
primr already gathers a cheap signal layer early (DNS recon, the homepage,
hiring signals); this module turns that layer into a MECE issue tree *before*
the expensive collection runs.

Each hypothesis is built to be refuted: it carries supporting and counter
evidence slots and a diagnostic test question that would discriminate it from
its alternatives. The tree is emitted as an inspectable artifact
(``hypothesis_tree.md`` / ``hypothesis_tree.json``), mirroring the skill-pack
``role_plan`` so an operator (or agent) can audit and prune it.

This module is generation + serialization only; wiring it into the pipeline and
using it to steer collection (Step 2b / Step 4) lands separately. Generation
takes an injectable ``llm`` callable, so the structure is fully testable with no
network. Confidence starts ``UNTESTED`` by construction (Day-1, pre-evidence),
reusing the ``agentic`` model's ``ConfidenceLevel``.

See ``docs/design/research-tradecraft.md`` (Step 2).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from primr.agentic.models import ConfidenceLevel, Hypothesis
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class DiagnosticHypothesis:
    """A single hypothesis built to be refuted.

    Attributes:
        claim: The testable statement.
        supporting: Cheap-signal evidence that would support the claim.
        counter: Counter-evidence or the alternative explanation to weigh.
        test_question: The diagnostic question whose answer best discriminates
            this claim from its alternatives (what to go find out).
        confidence: Starts ``UNTESTED`` at Day-1, before collection.
    """

    claim: str
    supporting: tuple[str, ...] = ()
    counter: tuple[str, ...] = ()
    test_question: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.UNTESTED

    def to_dict(self) -> dict[str, object]:
        return {
            "claim": self.claim,
            "supporting": list(self.supporting),
            "counter": list(self.counter),
            "test_question": self.test_question,
            "confidence": self.confidence.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DiagnosticHypothesis:
        return cls(
            claim=str(data.get("claim", "")).strip(),
            supporting=_as_str_tuple(data.get("supporting")),
            counter=_as_str_tuple(data.get("counter")),
            test_question=str(data.get("test_question", "")).strip(),
            confidence=_parse_confidence(data.get("confidence")),
        )

    def to_agentic_hypothesis(self, *, node_id: str, topic: str) -> Hypothesis:
        """Adapt to the ``agentic`` Hypothesis model for tracking/memory interop.

        The tree is the Day-1 planning artifact; the agentic ``Hypothesis`` is
        the unit the hypothesis-tracking subsystem evolves as evidence arrives.
        Supporting slots seed ``evidence``; the branch issue becomes ``topic``.
        """
        return Hypothesis(
            id=node_id,
            claim=self.claim,
            confidence=self.confidence,
            evidence=list(self.supporting),
            topic=topic,
        )


@dataclass(frozen=True)
class IssueBranch:
    """A MECE branch of the issue tree: one question, its candidate hypotheses."""

    issue: str
    hypotheses: tuple[DiagnosticHypothesis, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"issue": self.issue, "hypotheses": [h.to_dict() for h in self.hypotheses]}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> IssueBranch:
        raw_hyps = data.get("hypotheses")
        hyps = raw_hyps if isinstance(raw_hyps, list) else []
        parsed = tuple(
            DiagnosticHypothesis.from_dict(h)
            for h in hyps
            if isinstance(h, dict) and str(h.get("claim", "")).strip()
        )
        return cls(issue=str(data.get("issue", "")).strip(), hypotheses=parsed)


@dataclass(frozen=True)
class HypothesisTree:
    """The Day-1 issue tree for a company.

    ``branches`` are the MECE issues; each holds hypotheses built to be refuted.
    """

    company: str
    core_question: str = ""
    branches: tuple[IssueBranch, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        """True when no branch carries a hypothesis (nothing to steer with)."""
        return not any(b.hypotheses for b in self.branches)

    def iter_hypotheses(self) -> Iterator[tuple[IssueBranch, DiagnosticHypothesis]]:
        """Yield (branch, hypothesis) pairs across the whole tree."""
        for branch in self.branches:
            for hyp in branch.hypotheses:
                yield branch, hyp

    def to_dict(self) -> dict[str, object]:
        return {
            "company": self.company,
            "core_question": self.core_question,
            "branches": [b.to_dict() for b in self.branches],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> HypothesisTree:
        raw_branches = data.get("branches")
        branches = raw_branches if isinstance(raw_branches, list) else []
        parsed = tuple(
            IssueBranch.from_dict(b)
            for b in branches
            if isinstance(b, dict) and str(b.get("issue", "")).strip()
        )
        return cls(
            company=str(data.get("company", "")).strip(),
            core_question=str(data.get("core_question", "")).strip(),
            branches=parsed,
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Render the inspectable ``hypothesis_tree.md`` artifact."""
        lines = [f"# Day-1 Hypothesis Tree: {self.company}", ""]
        if self.core_question:
            lines += [f"**Core question:** {self.core_question}", ""]
        if self.is_empty:
            lines.append("_No hypotheses formed from the available Day-1 signals._")
            return "\n".join(lines)

        lines += [
            "Each hypothesis is built to be refuted. Confidence starts "
            "*untested*; the test question is what to go find out.",
            "",
        ]
        for i, branch in enumerate(self.branches, start=1):
            lines.append(f"## {i}. {branch.issue}")
            lines.append("")
            for j, hyp in enumerate(branch.hypotheses, start=1):
                lines.append(f"### {i}.{j} {hyp.claim}  _({hyp.confidence})_")
                if hyp.supporting:
                    lines.append("- **Supporting:** " + "; ".join(hyp.supporting))
                if hyp.counter:
                    lines.append("- **Counter / alternative:** " + "; ".join(hyp.counter))
                if hyp.test_question:
                    lines.append(f"- **Test:** {hyp.test_question}")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Generation (prompt builder + parser + orchestrator)
# ---------------------------------------------------------------------------


def build_hypothesis_tree_prompt(
    *,
    company: str,
    core_question: str,
    recon_summary: str,
    homepage_text: str,
    hiring_summary: str,
) -> str:
    """Build the Day-1 hypothesis-tree prompt from the cheap signal layer.

    Pure: deterministic given its inputs. Empty signal sections are labeled so
    the model knows what it is (and is not) working from.
    """
    question_line = (
        f"The engagement's core question is: {core_question}\n" if core_question.strip() else ""
    )
    return f"""You are a strategy analyst forming a DAY-1 hypothesis tree for {company},
BEFORE any deep research. You have only cheap early signals (below). Do not
invent facts; reason from what these signals plausibly imply.
{question_line}
Build a MECE issue tree: a small set of distinct, non-overlapping issues
(questions that matter for understanding this company), each with 2-3
candidate hypotheses. Every hypothesis must be built to be REFUTED:
- "claim": the testable statement
- "supporting": signals that would support it (from the data below)
- "counter": the alternative explanation or what would disprove it
- "test_question": the single best question to answer next to discriminate it

=== DNS / RECON SIGNALS ===
{recon_summary or "(none)"}

=== HOMEPAGE ===
{homepage_text or "(none)"}

=== HIRING SIGNALS ===
{hiring_summary or "(none)"}

Return ONLY JSON, no prose, in exactly this shape:
{{"branches": [{{"issue": "...", "hypotheses": [
  {{"claim": "...", "supporting": ["..."], "counter": ["..."], "test_question": "..."}}
]}}]}}
"""


def parse_hypothesis_tree(raw: str, *, company: str, core_question: str = "") -> HypothesisTree:
    """Parse the model's JSON into a HypothesisTree, tolerantly.

    Strips ``` fences, parses the first JSON object, and skips malformed
    branches/hypotheses rather than failing the run. Returns an empty tree (no
    branches) when nothing parseable is found.
    """
    payload = _extract_json_object(raw)
    if payload is None:
        logger.warning("Hypothesis tree: no parseable JSON in model output")
        return HypothesisTree(company=company, core_question=core_question)
    payload["company"] = company
    payload["core_question"] = core_question
    return HypothesisTree.from_dict(payload)


def generate_hypothesis_tree(
    *,
    company: str,
    core_question: str = "",
    recon_summary: str = "",
    homepage_text: str = "",
    hiring_summary: str = "",
    llm: Callable[[str], str] | None = None,
) -> HypothesisTree:
    """Generate the Day-1 hypothesis tree from the cheap signal layer.

    ``llm`` takes the prompt and returns the model's text; inject it for tests.
    When omitted, a utility-tier default is used lazily. Any generation error
    degrades to an empty tree (logged) rather than aborting the caller.
    """
    prompt = build_hypothesis_tree_prompt(
        company=company,
        core_question=core_question,
        recon_summary=recon_summary,
        homepage_text=homepage_text,
        hiring_summary=hiring_summary,
    )
    call = llm if llm is not None else _default_llm
    try:
        raw = call(prompt)
    except Exception as e:  # never let Day-1 planning abort the run
        logger.warning("Hypothesis tree generation failed: %s", e)
        return HypothesisTree(company=company, core_question=core_question)
    return parse_hypothesis_tree(raw, company=company, core_question=core_question)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_str_tuple(value: object) -> tuple[str, ...]:
    """Coerce a JSON value into a tuple of non-empty trimmed strings."""
    if not isinstance(value, list):
        return ()
    return tuple(str(v).strip() for v in value if str(v).strip())


def _parse_confidence(value: object) -> ConfidenceLevel:
    """Parse a confidence string, defaulting to UNTESTED."""
    if isinstance(value, ConfidenceLevel):
        return value
    try:
        return ConfidenceLevel(str(value).strip().lower())
    except (ValueError, AttributeError):
        return ConfidenceLevel.UNTESTED


def _extract_json_object(raw: str) -> dict[str, object] | None:
    """Pull the first JSON object out of model output, tolerating code fences."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if text.startswith("```"):
        # Drop the opening fence (``` or ```json) and the closing fence.
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
    return parsed if isinstance(parsed, dict) else None


def save_hypothesis_tree(tree: HypothesisTree, folder_path: str | Path) -> None:
    """Write the inspectable ``hypothesis_tree.{md,json}`` artifacts; never raises.

    Mirrors the skill-pack ``role_plan`` artifacts so an operator (or agent) can
    audit and prune the Day-1 tree. A write failure is logged, not raised, so an
    artifact-write problem can't abort the run.
    """
    try:
        base = Path(folder_path)
        (base / "hypothesis_tree.md").write_text(tree.to_markdown(), encoding="utf-8")
        (base / "hypothesis_tree.json").write_text(tree.to_json(), encoding="utf-8")
    except OSError as e:
        logger.warning("Could not write hypothesis tree artifact: %s", e)


def _default_llm(prompt: str) -> str:
    """Lazy utility-tier default LLM call (kept thin; the seam is what tests use).

    Day-1 tree formation is a cheap, structured pass, so it routes to the fast
    tier with shallow thinking. Step 2b wiring may swap in a failover-wrapped
    call; the injectable ``llm`` seam keeps that decision out of this module.
    """
    from primr.ai.llm import llm as _llm

    return _llm(prompt, model_type="fast", temperature=0.4, thinking_level="low")
