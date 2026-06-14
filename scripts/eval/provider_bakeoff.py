"""Provider/model bake-off — quality-per-dollar across the wired providers.

A cheap, insightful eval: run a handful of representative primr tasks (reasoning
+ writing tier) across every provider you have a key for, score each output with
a judge model, and report quality, cost, and latency side by side. A local
Ollama model can ride along as a free baseline.

This is a dev/research tool, not part of the shipped CLI. It reuses primr's
provider abstraction (``build_provider``) and cost model (``PrimrModels``) rather
than inventing a second way to call models.

Cost gate: it prints a pre-run estimate and refuses to spend without ``--yes``,
and aborts if the projected spend exceeds ``--max-cost`` (default $3.00).

Usage:
    uv run python scripts/eval/provider_bakeoff.py            # estimate only
    uv run python scripts/eval/provider_bakeoff.py --yes      # run it (cloud only)
    # add a free local Ollama baseline by naming the tag (machine-specific):
    uv run python scripts/eval/provider_bakeoff.py --yes --local-model <ollama-tag>
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from primr.ai.providers import KNOWN_PROVIDERS, build_provider
from primr.ai.providers.base import Provider
from primr.config.models import PrimrModels
from primr.utils.console import console

# ---------------------------------------------------------------------------
# The matrix — (label, provider name, model id). Entries whose provider has no
# key configured are skipped automatically at run time.
# ---------------------------------------------------------------------------
MATRIX: list[tuple[str, str, str]] = [
    ("Grok 4.3", "xai", "grok-4.3"),
    ("GPT-5.4 nano", "openai", "gpt-5.4-nano"),
    ("GPT-5.4 mini", "openai", "gpt-5.4-mini"),
    ("Claude Haiku 4.5", "anthropic", "claude-haiku-4-5"),
    ("Claude Sonnet 4.6", "anthropic", "claude-sonnet-4-6"),
]
# Free local baseline (Ollama). Opt in by passing --local-model <tag>; the tag is
# machine-specific so it is never hardcoded here.
LOCAL_PROVIDER = "ollama"

# A fixed, fictional subject so the eval is deterministic and ships no real data.
EXAMPLECO = (
    "ExampleCo (acme.example) is a Series B B2B SaaS company selling an AI-assisted "
    "contract-review platform to mid-market legal teams. ~180 employees, HQ in Austin, "
    "raised a $40M Series B in 2025 led by Northwind Ventures. Recent signals: opened a "
    "London office, posted 12 engineering roles, shipped an SOC 2 Type II report, and "
    "publicly named two Fortune 500 logos. Competes with incumbents Ironclad and Evisort."
)

# ---------------------------------------------------------------------------
# Tasks — drawn from primr's real tiers: reasoning (gap analysis / hypotheses)
# and writing (a brief section). Kept short to keep the eval cheap.
# ---------------------------------------------------------------------------
TASKS: list[dict[str, str]] = [
    {
        "id": "reasoning_gaps",
        "tier": "reasoning",
        "system": "You are a sharp B2B research analyst. Be specific and concise.",
        "prompt": f"{EXAMPLECO}\n\nList the 5 most important UNKNOWNS a strategic brief "
        "must resolve about this company, each with one sentence on why it matters. "
        "No preamble.",
    },
    {
        "id": "reasoning_hypotheses",
        "tier": "reasoning",
        "system": "You are a sharp B2B research analyst. Be specific and concise.",
        "prompt": f"{EXAMPLECO}\n\nPropose 3 testable hypotheses about this company's "
        "near-term strategy, each with the single best public signal that would confirm "
        "or refute it. No preamble.",
    },
    {
        "id": "reasoning_risks",
        "tier": "reasoning",
        "system": "You are a sharp B2B research analyst. Be specific and concise.",
        "prompt": f"{EXAMPLECO}\n\nIdentify the 3 biggest risks to this company over the "
        "next 18 months and rank them. One sentence each. No preamble.",
    },
    {
        "id": "writing_overview",
        "tier": "writing",
        "system": "You write tight, factual strategic-brief prose. No marketing fluff.",
        "prompt": f"{EXAMPLECO}\n\nWrite a 120-150 word 'Company Overview' section for a "
        "strategic brief. Lead with what they do and who buys it. No headings.",
    },
    {
        "id": "writing_gtm",
        "tier": "writing",
        "system": "You write tight, factual strategic-brief prose. No marketing fluff.",
        "prompt": f"{EXAMPLECO}\n\nWrite a 120-150 word 'Go-to-Market' section inferring "
        "their motion from the signals above. Flag inferences as inferences. No headings.",
    },
    {
        "id": "writing_hiring",
        "tier": "writing",
        "system": "You write tight, factual strategic-brief prose. No marketing fluff.",
        "prompt": f"{EXAMPLECO}\n\nWrite a 120-150 word 'Hiring & Expansion Signals' "
        "section. Tie each signal to a strategic implication. No headings.",
    },
]

# Rough token guesses for the pre-run estimate (input includes context+prompt).
EST_INPUT_TOKENS = 350
EST_OUTPUT_TOKENS = 450
JUDGE_INPUT_TOKENS = 600
JUDGE_OUTPUT_TOKENS = 120


@dataclass
class RunResult:
    label: str
    task_id: str
    tier: str
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    latency_s: float = 0.0
    score: float | None = None
    judge_reason: str = ""
    error: str = ""


@dataclass
class ModelAgg:
    label: str
    n: int = 0
    total_cost: float = 0.0
    total_latency: float = 0.0
    scores: list[float] = field(default_factory=list)
    errors: int = 0

    @property
    def avg_score(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0

    @property
    def avg_latency(self) -> float:
        return self.total_latency / self.n if self.n else 0.0


def _entry(name: str):
    return next((p for p in KNOWN_PROVIDERS if p.name == name), None)


def _provider_for(name: str) -> Provider | None:
    entry = _entry(name)
    if entry is None:
        return None
    try:
        prov = build_provider(entry)
        return prov if prov.is_available() else None
    except Exception:
        return None


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    """Cost via the registry; unknown (e.g. local) models are treated as free."""
    try:
        return PrimrModels.calculate_cost(model, in_tok, out_tok)
    except KeyError:
        return 0.0


def _resolve_matrix(local_model: str | None) -> list[tuple[str, str, str, Provider]]:
    matrix = list(MATRIX)
    if local_model:
        matrix.append((f"{local_model} (local)", LOCAL_PROVIDER, local_model))
    resolved = []
    for label, name, model in matrix:
        prov = _provider_for(name)
        if prov is None:
            console.muted(f"  skip {label}: provider '{name}' not configured/usable")
            continue
        resolved.append((label, name, model, prov))
    return resolved


def _estimate(matrix, judge_model: str) -> float:
    gens = len(matrix) * len(TASKS)
    total = 0.0
    for _label, _name, model, _prov in matrix:
        total += len(TASKS) * _cost(model, EST_INPUT_TOKENS, EST_OUTPUT_TOKENS)
    judge_total = gens * _cost(judge_model, JUDGE_INPUT_TOKENS, JUDGE_OUTPUT_TOKENS)
    return total + judge_total


def _judge(prov: Provider, model: str, task: dict, candidate: str) -> tuple[float | None, str]:
    rubric = (
        "Score the CANDIDATE answer to the TASK from 1-10 on accuracy, relevance, "
        "structure, and concision combined. Reply with ONLY compact JSON: "
        '{"score": <int 1-10>, "reason": "<=12 words"}.'
    )
    messages = [
        {"role": "system", "content": "You are a strict, fair evaluator."},
        {
            "role": "user",
            "content": f"{rubric}\n\nTASK:\n{task['prompt']}\n\nCANDIDATE:\n{candidate}",
        },
    ]
    try:
        resp = prov.chat(messages, model=model, max_tokens=200, temperature=0.0)
    except Exception as e:
        return None, f"judge error: {e}"
    raw = resp.text.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return float(data.get("score")), str(data.get("reason", ""))[:80]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return None, f"unparseable: {raw[:40]}"


def run(args: argparse.Namespace) -> int:
    judge_name, _, judge_model = args.judge.partition(":")
    judge_prov = _provider_for(judge_name)

    console.step("Bake-off matrix")
    matrix = _resolve_matrix(local_model=args.local_model)
    if not matrix:
        console.error("No providers configured. Run: primr keys set xai|openai|anthropic")
        return 1
    if judge_prov is None:
        console.error(f"Judge provider '{judge_name}' not configured (needed to score).")
        return 1

    projected = _estimate(matrix, judge_model)
    console.info(f"  {len(matrix)} models x {len(TASKS)} tasks = {len(matrix) * len(TASKS)} runs")
    console.info(f"  Judge: {args.judge}")
    console.warn(f"  Estimated spend: ${projected:.2f} (local arm is free)")

    if projected > args.max_cost:
        console.error(
            f"Projected ${projected:.2f} exceeds --max-cost ${args.max_cost:.2f}. Aborting."
        )
        return 1
    if not args.yes:
        console.info("  Dry run. Re-run with --yes to execute (cost gate).")
        return 0

    results: list[RunResult] = []
    aggs: dict[str, ModelAgg] = {}
    for label, _name, model, prov in matrix:
        aggs[label] = ModelAgg(label=label)
        for task in TASKS:
            r = RunResult(label=label, task_id=task["id"], tier=task["tier"])
            messages = [
                {"role": "system", "content": task["system"]},
                {"role": "user", "content": task["prompt"]},
            ]
            t0 = time.monotonic()
            try:
                resp = prov.chat(messages, model=model, max_tokens=700, temperature=0.4)
                r.latency_s = time.monotonic() - t0
                r.text = resp.text
                r.input_tokens = resp.input_tokens
                r.output_tokens = resp.output_tokens
                r.cost = _cost(model, resp.input_tokens, resp.output_tokens)
            except Exception as e:
                r.latency_s = time.monotonic() - t0
                r.error = str(e)[:120]
                aggs[label].errors += 1
                console.muted(f"  {label}/{task['id']}: error {r.error}")
                results.append(r)
                continue

            r.score, r.judge_reason = _judge(judge_prov, judge_model, task, r.text)
            agg = aggs[label]
            agg.n += 1
            agg.total_cost += r.cost
            agg.total_latency += r.latency_s
            if r.score is not None:
                agg.scores.append(r.score)
            console.ok(
                f"  {label:<22} {task['id']:<22} "
                f"score={r.score if r.score is not None else '?':<4} "
                f"${r.cost:.4f}  {r.latency_s:.1f}s"
            )
            results.append(r)

    _report(aggs, results, args.out)
    return 0


def _report(aggs: dict[str, ModelAgg], results: list[RunResult], out_path: str) -> None:
    console.step("Results — quality per dollar")
    rows = sorted(aggs.values(), key=lambda a: (-a.avg_score, a.total_cost))
    console.info(
        f"  {'Model':<24}{'avg score':<11}{'$ total':<10}{'$/run':<10}{'latency':<9}{'errors'}"
    )
    for a in rows:
        per = a.total_cost / a.n if a.n else 0.0
        console.info(
            f"  {a.label:<24}{a.avg_score:<11.2f}${a.total_cost:<9.4f}${per:<9.4f}"
            f"{a.avg_latency:<8.1f}s {a.errors}"
        )
    # Value pick: best score per dollar among paid models that actually ran.
    paid = [a for a in rows if a.total_cost > 0 and a.scores]
    if paid:
        best_value = max(paid, key=lambda a: a.avg_score / max(a.total_cost, 1e-9))
        best_quality = max(rows, key=lambda a: a.avg_score)
        console.blank()
        console.ok(f"  Best quality:      {best_quality.label} ({best_quality.avg_score:.2f})")
        console.ok(
            f"  Best value (paid): {best_value.label} ({best_value.avg_score:.2f} @ ${best_value.total_cost:.4f})"
        )

    payload = {
        "summary": [
            {
                "label": a.label,
                "avg_score": round(a.avg_score, 3),
                "total_cost": round(a.total_cost, 5),
                "avg_latency_s": round(a.avg_latency, 2),
                "n": a.n,
                "errors": a.errors,
            }
            for a in rows
        ],
        "runs": [vars(r) for r in results],
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    console.info(f"  Wrote {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Provider/model quality-per-dollar bake-off")
    ap.add_argument("--yes", action="store_true", help="Actually run (otherwise estimate only)")
    ap.add_argument(
        "--max-cost", type=float, default=3.0, help="Abort if projected spend exceeds this"
    )
    ap.add_argument(
        "--judge", default="anthropic:claude-haiku-4-5", help="provider:model used to score"
    )
    ap.add_argument(
        "--local-model",
        default=None,
        help="Ollama model tag to add as a free local baseline (e.g. 'qwen3:8b'). Off by default.",
    )
    ap.add_argument("--out", default="output/eval/provider_bakeoff.json", help="Results JSON path")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
