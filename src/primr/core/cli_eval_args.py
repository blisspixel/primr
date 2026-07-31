"""Eval-related CLI argument registration."""

from __future__ import annotations

import argparse


def add_eval_arguments(parser: argparse.ArgumentParser) -> None:
    """Register arguments owned by the `primr --eval` workflow."""
    parser.add_argument(
        "--eval",
        action="store_true",
        dest="eval_mode",
        help="Run versioned model/profile evaluation scorecard (offline analysis by default)",
    )
    parser.add_argument(
        "--eval-id",
        type=str,
        metavar="EVAL_ID",
        help="Evaluation run id (e.g., eval-2026-02-r1)",
    )
    parser.add_argument(
        "--eval-root",
        type=str,
        default="output/evals",
        help="Root folder containing eval outputs (default: output/evals)",
    )
    parser.add_argument(
        "--eval-profiles",
        type=str,
        nargs="+",
        default=["full", "lite", "fast"],
        help=(
            "Profiles to compare (default: full lite fast). Any registered profile slot "
            "name is accepted; see primr.core.model_eval.list_eval_profile_names()."
        ),
    )
    parser.add_argument(
        "--eval-baseline",
        type=str,
        default="full",
        help="Baseline profile for quality/cost ratio comparison (default: full).",
    )
    parser.add_argument(
        "--eval-manifest",
        type=str,
        metavar="CSV_PATH",
        help="CSV manifest with company/company_name and website columns",
    )
    parser.add_argument(
        "--eval-run-missing",
        action="store_true",
        help="Execute missing profile/company runs with explicit spend guardrails",
    )
    parser.add_argument(
        "--eval-max-new-runs",
        type=int,
        default=0,
        help="Maximum number of missing runs when --eval-run-missing is set",
    )
    parser.add_argument(
        "--eval-max-estimated-cost",
        type=float,
        default=0.0,
        help="Hard spend cap in USD for missing runs",
    )
    parser.add_argument(
        "--eval-quality-ratio-threshold",
        type=float,
        default=0.8,
        help="Minimum quality ratio vs baseline for pass/fail (default: 0.8)",
    )
    parser.add_argument(
        "--eval-cost-ratio-threshold",
        type=float,
        default=0.2,
        help="Maximum estimated cost ratio vs baseline for pass/fail (default: 0.2)",
    )
    parser.add_argument(
        "--eval-company",
        type=str,
        help="Target a specific company for auto-staging from existing outputs",
    )
    parser.add_argument(
        "--eval-source-dir",
        type=str,
        default="output",
        help="Source directory to auto-stage reports from (default: output)",
    )
    parser.add_argument(
        "--eval-no-auto-stage",
        action="store_true",
        help="Disable automatic staging from existing local outputs",
    )
    parser.add_argument(
        "--eval-llm-judge",
        action="store_true",
        help="Optional LLM judge overlay for eval scorecard (incurs API cost)",
    )
    parser.add_argument(
        "--eval-judge-provider",
        type=str,
        choices=["grok", "local"],
        default="grok",
        help="LLM judge provider (default: grok; use local for OpenAI-compatible backends)",
    )
    parser.add_argument(
        "--eval-judge-model",
        type=str,
        default="grok-4.3",
        help="Model name for LLM judge",
    )
    parser.add_argument(
        "--eval-judge-models",
        type=str,
        nargs="+",
        default=None,
        help="For local judge sweeps, run the same eval across multiple model names",
    )
    parser.add_argument(
        "--eval-judge-model-list",
        type=str,
        default=None,
        help="Named local judge model list",
    )
    parser.add_argument(
        "--eval-judge-base-url",
        type=str,
        default=None,
        help="Base URL for local/OpenAI-compatible eval judge",
    )
    parser.add_argument(
        "--eval-judge-api-key-env",
        type=str,
        default="LOCAL_LLM_API_KEY",
        help="Environment variable containing the local judge API key",
    )
    parser.add_argument(
        "--eval-judge-max-pairs",
        type=int,
        default=1,
        help="Max company profile pairs to judge (default: 1)",
    )
    parser.add_argument(
        "--eval-judge-passes",
        type=int,
        default=1,
        help="Judge passes per pair for variance reduction (default: 1)",
    )
    parser.add_argument(
        "--eval-judge-max-cost",
        type=float,
        default=0.0,
        help="Hard cost cap in USD for LLM judge pass",
    )
    parser.add_argument(
        "--eval-local-stage",
        type=str,
        choices=["website-summary"],
        default=None,
        help="Run a local generation eval for a production-adjacent stage",
    )
    parser.add_argument(
        "--eval-local-stage-semantic-judge",
        action="store_true",
        dest="eval_stage_semantic_judge",
        help=(
            "For --eval-local-stage website-summary, run a local semantic judge pass "
            "and use its body-free quality evidence for same-command scorecards"
        ),
    )
    parser.add_argument(
        "--eval-local-stage-semantic-judge-model",
        type=str,
        default=None,
        dest="eval_stage_semantic_judge_model",
        help=(
            "Local/OpenAI-compatible model or comma-separated model panel for "
            "--eval-local-stage-semantic-judge (default: first resolved local stage model)"
        ),
    )
    parser.add_argument(
        "--eval-source-relevance-fixture",
        type=str,
        default=None,
        metavar="JSON_PATH",
        help=(
            "Build body-free fast.source_relevance quality evidence from labeled "
            "keep-list fixture JSON"
        ),
    )
    parser.add_argument(
        "--eval-source-relevance-standing-corpus",
        action="store_true",
        default=False,
        help=(
            "Use the packaged standing source-relevance corpus "
            "(source_relevance_standing_v1) for review-only host-vs-cloud "
            "scorecards. Scorecard input only; not a promotion gate."
        ),
    )
    parser.add_argument(
        "--eval-page-access-fixture",
        type=str,
        default=None,
        metavar="JSON_PATH",
        help=(
            "Build body-free page-access classifier eval artifacts from labeled "
            "sanitized HTML or trace access-assessment fixture JSON"
        ),
    )
    parser.add_argument(
        "--eval-working-root",
        type=str,
        default="working",
        help="Root directory containing working run folders for stage-level eval inputs",
    )
    parser.add_argument(
        "--eval-stage-scorecard",
        action="store_true",
        help="Write review-only routed-stage scorecard artifacts from route and quality evidence",
    )
    parser.add_argument(
        "--eval-stage-quality",
        type=str,
        metavar="JSON_PATH",
        help="Quality evidence JSON for --eval-stage-scorecard",
    )
    parser.add_argument(
        "--eval-stage-route-root",
        type=str,
        default=None,
        help="Root containing _run_state.json route ledgers (default: --eval-working-root)",
    )
    parser.add_argument(
        "--eval-stage-id",
        type=str,
        default=None,
        help="Optional stage id filter for the routed-stage scorecard",
    )
    parser.add_argument(
        "--eval-stage-min-quality-score",
        type=float,
        default=85.0,
        help="Minimum quality score for human-review candidacy (default: 85)",
    )
    parser.add_argument(
        "--eval-stage-max-failure-rate",
        type=float,
        default=0.0,
        help="Maximum observed route failure rate for human-review candidacy (default: 0)",
    )
