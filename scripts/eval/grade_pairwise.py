"""Pairwise, bias-controlled grading of two briefs on matched sections.

Implements the June 2026 LLM-as-judge consensus so a result is defensible:
- Pairwise (A vs B), not absolute 1-10 scoring (less noisy, less length-biased).
- Position bias: every pair is judged in BOTH orders; an order-dependent verdict
  is recorded as a tie (the judge was reacting to position, not content).
- Length bias: the judge contract explicitly says not to reward length/padding.
- Self-preference: a 3-judge panel across families (OpenAI + xAI + Gemini). The
  Anthropic family is excluded as a judge because it is a candidate writer.
  Per-judge results are reported so same-family pairings (e.g. a Gemini judge on
  a Gemini-written candidate) are visible, not hidden.
- Pinned contract: temperature 0, fixed rubric prompt.

Quality is genuinely a judgment; this makes the judgment multi-dimensional,
cross-checked, and reproducible rather than one vibe number. Citation/traceability
is reported separately as a neutral descriptor, never folded into "better".

    py -3.12 scripts/eval/grade_pairwise.py \
        --baseline "output/<standard>.md" --candidate "output/<premium>.md" \
        --label premium-opus-reason
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from primr.ai.providers import KNOWN_PROVIDERS, build_provider
from primr.config.env import load_primr_env
from primr.utils.console import console

# Matched analytical sections to compare head-to-head (skipped if absent in either
# brief). Chosen to exercise analysis, not boilerplate.
SECTIONS = [
    "Executive Summary",
    "SWOT Analysis",
    "Strategic Positioning Hypothesis",
    "Competitive Landscape",
    "Strategic Tensions",
]

# 3-judge panel across families. Anthropic is excluded - it writes a candidate,
# so using it as judge would be self-preference. Grok shares a family with the
# baseline writer; the Gemini judge shares with a Gemini-written candidate - both
# are reported per-judge so the reader sees it.
JUDGES = [
    ("openai", "gpt-5.4-mini"),
    ("xai", "grok-4.3"),
    ("gemini", "gemini-3.1-flash-lite"),
]

RUBRIC = (
    "You are grading two excerpts (A and B) - the SAME section of a strategic "
    "company brief, written by two different systems. Pick which is the stronger "
    "STRATEGIC ANALYSIS, judging: analytical depth (non-obvious insight, causal "
    "reasoning), specificity (concrete facts/numbers over generic claims), "
    "actionability (useful to a decision-maker), and factual care (claims are "
    "careful, not overconfident). Do NOT reward length, verbosity, or padding - "
    "if one is longer but not better, that is not a point in its favour. "
    'Reply with ONLY compact JSON: {"winner": "A" | "B" | "tie", "reason": "<=15 words"}.'
)


def _provider(name: str):
    entry = next((p for p in KNOWN_PROVIDERS if p.name == name), None)
    return build_provider(entry) if entry else None


def _sections(md: str) -> dict[str, str]:
    """Split a brief into {heading: body} by level-2 markdown headings."""
    out: dict[str, str] = {}
    cur, buf = None, []
    for line in md.splitlines():
        m = re.match(r"^##\s+(.*)", line)
        if m:
            if cur is not None:
                out[cur.strip()] = "\n".join(buf).strip()
            cur, buf = m.group(1), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur.strip()] = "\n".join(buf).strip()
    return out


def _match(want: str, have: dict[str, str]) -> str | None:
    for k in have:
        if want.lower() in k.lower():
            return k
    return None


def _judge_once(prov, model: str, sec: str, a: str, b: str) -> str:
    msg = [
        {"role": "system", "content": "You are a precise, unbiased evaluator."},
        {"role": "user", "content": f"{RUBRIC}\n\nSection: {sec}\n\n[A]\n{a}\n\n[B]\n{b}"},
    ]
    try:
        resp = prov.chat(msg, model=model, max_tokens=120, temperature=0.0)
    except Exception as e:
        return f"error:{str(e)[:40]}"
    raw = resp.text.strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s >= 0 and e > s:
        try:
            return str(json.loads(raw[s : e + 1]).get("winner", "tie")).upper()
        except (json.JSONDecodeError, ValueError):
            pass
    return "TIE"


def _verdict(prov, model, sec, base, cand) -> str:
    """Both orderings; order-dependent => tie. Returns 'candidate'|'baseline'|'tie'."""
    # Order 1: A=baseline, B=candidate
    v1 = _judge_once(prov, model, sec, base, cand)
    # Order 2: A=candidate, B=baseline
    v2 = _judge_once(prov, model, sec, cand, base)
    if v1.startswith("error") or v2.startswith("error"):
        return "tie"
    win1 = "candidate" if v1 == "B" else ("baseline" if v1 == "A" else "tie")
    win2 = "candidate" if v2 == "A" else ("baseline" if v2 == "B" else "tie")
    return win1 if win1 == win2 else "tie"  # disagreement across orders = tie


def main() -> int:
    ap = argparse.ArgumentParser(description="Pairwise bias-controlled brief grading")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--label", default="candidate")
    ap.add_argument(
        "--judges",
        default=None,
        help="Override the panel: comma-separated provider:model (e.g. "
        "'ollama:qwen3:8b' for a FREE local judge while developing). Default is "
        "the cross-family cloud panel.",
    )
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    load_primr_env()

    panel = JUDGES
    if args.judges:
        panel = []
        for item in args.judges.split(","):
            item = item.strip()
            if not item:
                continue
            name, _, model = item.partition(":")  # model keeps any ':' in an ollama tag
            panel.append((name, model))

    base_secs = _sections(Path(args.baseline).read_text(encoding="utf-8"))
    cand_secs = _sections(Path(args.candidate).read_text(encoding="utf-8"))
    judges = [(n, m, _provider(n)) for n, m in panel]
    judges = [(n, m, p) for n, m, p in judges if p is not None]
    console.info(f"Judges: {', '.join(f'{n}:{m}' for n, m, _ in judges)}")

    rows = []
    tally = {"candidate": 0, "baseline": 0, "tie": 0}
    for want in SECTIONS:
        bk, ck = _match(want, base_secs), _match(want, cand_secs)
        if not bk or not ck:
            console.muted(f"  skip '{want}' (missing in one brief)")
            continue
        per_judge = {}
        for n, m, p in judges:
            v = _verdict(p, m, want, base_secs[bk], cand_secs[ck])
            per_judge[n] = v
            tally[v] += 1
        # majority across judges for this section
        votes = list(per_judge.values())
        maj = max(("candidate", "baseline", "tie"), key=votes.count)
        rows.append({"section": want, "majority": maj, "per_judge": per_judge})
        console.ok(f"  {want:<34} -> {maj:<10} {per_judge}")

    n_judge_section = sum(tally.values()) or 1
    console.blank()
    console.step(f"Pairwise result: {args.label} vs baseline")
    console.info(
        f"  candidate wins: {tally['candidate']}  ties: {tally['tie']}  baseline wins: {tally['baseline']}  (of {n_judge_section} judge-sections)"
    )
    sec_maj = [r["majority"] for r in rows]
    console.info(
        f"  by section majority -> candidate {sec_maj.count('candidate')} / "
        f"tie {sec_maj.count('tie')} / baseline {sec_maj.count('baseline')}"
    )

    out = args.out or f"output/eval/pairwise_{args.label}.json"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(
        json.dumps({"label": args.label, "tally": tally, "sections": rows}, indent=2),
        encoding="utf-8",
    )
    console.info(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
