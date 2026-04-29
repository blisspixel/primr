#!/usr/bin/env python3
"""Blind A/B judge for the continuous-reasoning pilot.

Compares two Primr runs of the same company — one with the standard fresh-call
reasoning chain, one with --continuous-reasoning — and produces a structured
verdict on whether the continuous-session topology meaningfully improved the
output.

Uses Gemini 2.5 Pro as the judge (different model family from Grok, the
generator) to reduce same-family bias. Reports are shuffled and labeled X/Y
before being shown to the judge.

Usage:
    python tools/pilot_judge.py <baseline_working_dir> <continuous_working_dir>

Both directories must contain at minimum:
    - report.md
    - analysis_workbook.md
    - cross_validation.json
    - _run_state.json
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

load_dotenv()

JUDGE_MODEL = "gemini-2.5-pro"
JUDGE_TEMPERATURE = 0.2


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _load_run(working_dir: Path) -> dict:
    state = json.loads(_read(working_dir / "_run_state.json") or "{}")
    return {
        "dir": str(working_dir),
        "company": state.get("company_name", "?"),
        "cost_usd": state.get("actual_cost_usd"),
        "report_words": state.get("report_words"),
        "started_at": state.get("started_at"),
        "completed_at": state.get("completed_at"),
        "report_md": _read(working_dir / "report.md"),
        "workbook_md": _read(working_dir / "analysis_workbook.md"),
        "cross_validation": _read(working_dir / "cross_validation.json"),
    }


JUDGE_PROMPT = """You are evaluating two consulting research briefs about the SAME company,
both produced by the same AI pipeline but with one variable changed: their
internal reasoning topology. You must NOT know which is which.

For each pair below, score 1-10 on the dimensions listed and pick a winner.
A "1" is unusable, a "5" is competent, a "10" is exceptional. Calibrate
honestly — if both are similar, give similar scores.

=== PAIR 1: ANALYSIS WORKBOOK ===
This is the structured pre-engagement workbook a consulting analyst produces
before writing the brief. Score on:
- DEPTH: Does it stress-test the company's narrative or just summarize their marketing?
- EVIDENCE DISCIPLINE: Are claims labeled (Confirmed/Reported/Estimated/Hypothesis)?
- STRATEGIC SHARPNESS: Are hypotheses, tensions, and narrative gaps genuinely insightful?
- USEFULNESS: Would this give a consultant a real edge in a discovery conversation?

WORKBOOK X:
{workbook_x}

WORKBOOK Y:
{workbook_y}

=== PAIR 2: CROSS-VALIDATION OUTPUT ===
This is the JSON output of a quality reviewer that scans the assembled report
for weak sections and contradictions. Score on:
- SPECIFICITY: Are the flagged issues concrete (vs. generic boilerplate)?
- USEFULNESS: Would acting on these findings actually improve the report?
- CALIBRATION: Did it find genuine issues, or did it nitpick / miss real problems?

CROSS-VALIDATION X:
{cv_x}

CROSS-VALIDATION Y:
{cv_y}

=== PAIR 3: FINAL REPORT ===
This is the assembled consulting brief. Score on:
- COHERENCE: Does it read as one analytical voice, or does it drift between sections?
- DEPTH: Does it produce strategic insight, or does it summarize/restate company marketing?
- SPECIFICITY: Are claims tied to evidence with confidence labels, or vague?
- ABSENCE OF DRIFT: Does the document stay focused on the strategic analysis the brief
  was supposed to deliver, or does it drift into meta-commentary about itself, its
  pipeline, or its own quality? (This is the specific failure mode we are testing for.)

REPORT X (first 60K chars):
{report_x}

REPORT Y (first 60K chars):
{report_y}

=== OUTPUT ===

Return RAW JSON only (no markdown fencing). Schema:

{{
  "workbook": {{
    "scores_x": {{"depth": int, "evidence_discipline": int, "strategic_sharpness": int, "usefulness": int}},
    "scores_y": {{"depth": int, "evidence_discipline": int, "strategic_sharpness": int, "usefulness": int}},
    "winner": "X" | "Y" | "tie",
    "reasoning": "2-3 sentences explaining the verdict"
  }},
  "cross_validation": {{
    "scores_x": {{"specificity": int, "usefulness": int, "calibration": int}},
    "scores_y": {{"specificity": int, "usefulness": int, "calibration": int}},
    "winner": "X" | "Y" | "tie",
    "reasoning": "2-3 sentences"
  }},
  "report": {{
    "scores_x": {{"coherence": int, "depth": int, "specificity": int, "absence_of_drift": int}},
    "scores_y": {{"coherence": int, "depth": int, "specificity": int, "absence_of_drift": int}},
    "winner": "X" | "Y" | "tie",
    "drift_observations": "Any meta-commentary, pipeline-self-reference, or QA-style drift you noticed in either report — be specific about where",
    "reasoning": "3-4 sentences explaining the overall verdict"
  }},
  "overall": {{
    "winner": "X" | "Y" | "tie",
    "confidence": "low" | "medium" | "high",
    "summary": "3-5 sentence verdict on which run produced the better strategic analysis and why"
  }}
}}
"""


def judge(arm_a: dict, arm_b: dict) -> dict:
    """Run the blind judge on two arms. Returns judge output + label mapping."""
    flip = random.random() < 0.5
    if flip:
        x, y = arm_b, arm_a
        label_map = {"X": "continuous", "Y": "baseline"}
    else:
        x, y = arm_a, arm_b
        label_map = {"X": "baseline", "Y": "continuous"}

    prompt = JUDGE_PROMPT.format(
        workbook_x=x["workbook_md"][:40000] or "(missing)",
        workbook_y=y["workbook_md"][:40000] or "(missing)",
        cv_x=x["cross_validation"] or "(missing)",
        cv_y=y["cross_validation"] or "(missing)",
        report_x=x["report_md"][:60000] or "(missing)",
        report_y=y["report_md"][:60000] or "(missing)",
    )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set; needed for the judge.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=JUDGE_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=JUDGE_TEMPERATURE,
            response_mime_type="application/json",
            max_output_tokens=8000,
        ),
    )
    raw = response.text or ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"_raw_response": raw, "_parse_error": True}

    return {
        "label_map": label_map,
        "judge_model": JUDGE_MODEL,
        "verdict": parsed,
        "input_chars": len(prompt),
        "usage": {
            "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", None),
            "output_tokens": getattr(response.usage_metadata, "candidates_token_count", None),
            "thoughts_tokens": getattr(response.usage_metadata, "thoughts_token_count", None),
        }
        if response.usage_metadata
        else {},
    }


def cost_summary(run: dict, label: str) -> str:
    cost = run.get("cost_usd")
    words = run.get("report_words")
    return f"{label}: cost=${cost:.4f}" + (f", {words} words" if words else "")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2

    baseline_dir = Path(argv[0]).resolve()
    continuous_dir = Path(argv[1]).resolve()
    if not baseline_dir.is_dir():
        print(f"baseline dir not found: {baseline_dir}", file=sys.stderr)
        return 1
    if not continuous_dir.is_dir():
        print(f"continuous dir not found: {continuous_dir}", file=sys.stderr)
        return 1

    arm_a = _load_run(baseline_dir)
    arm_b = _load_run(continuous_dir)

    print("=" * 70)
    print("PILOT: Continuous Reasoning A/B (WinMagic)")
    print("=" * 70)
    print(cost_summary(arm_a, "Arm A (baseline)"))
    print(cost_summary(arm_b, "Arm B (continuous)"))
    if arm_a.get("cost_usd") and arm_b.get("cost_usd"):
        delta = arm_b["cost_usd"] - arm_a["cost_usd"]
        pct = 100 * delta / arm_a["cost_usd"]
        print(f"Cost delta: ${delta:+.4f} ({pct:+.1f}%)")
    print()
    print(f"Calling judge ({JUDGE_MODEL})...")
    result = judge(arm_a, arm_b)

    out_dir = continuous_dir.parent
    judge_path = out_dir / f"judge_verdict_{continuous_dir.name}.json"
    judge_path.write_text(
        json.dumps(
            {
                "baseline_dir": str(baseline_dir),
                "continuous_dir": str(continuous_dir),
                "baseline_cost_usd": arm_a.get("cost_usd"),
                "continuous_cost_usd": arm_b.get("cost_usd"),
                "baseline_words": arm_a.get("report_words"),
                "continuous_words": arm_b.get("report_words"),
                "judge": result,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {judge_path}")
    print()

    verdict = result.get("verdict", {})
    if "_parse_error" in verdict:
        print("Judge response was not valid JSON. See file for raw text.")
        return 1

    label_map = result["label_map"]
    print("Label mapping (was hidden from judge):")
    for k, v in label_map.items():
        print(f"  {k} = {v}")
    print()
    for section in ("workbook", "cross_validation", "report", "overall"):
        block = verdict.get(section, {})
        if not block:
            continue
        winner_label = block.get("winner", "?")
        winner_real = label_map.get(winner_label, winner_label)
        print(f"--- {section.upper()} ---")
        print(f"  winner: {winner_label} ({winner_real})")
        for k in ("confidence", "summary", "reasoning", "drift_observations"):
            if k in block:
                print(f"  {k}: {block[k]}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
