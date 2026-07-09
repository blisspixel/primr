"""Calibration-related CLI argument registration."""

from __future__ import annotations

import argparse


def add_calibration_arguments(parser: argparse.ArgumentParser) -> None:
    """Register arguments owned by the `primr calibrate` workflow."""
    parser.add_argument(
        "--calibrate-recent",
        type=int,
        metavar="N",
        help="With 'calibrate', audit the N most recent reports (one per company)",
    )
    parser.add_argument(
        "--max-per-label",
        type=int,
        default=10,
        metavar="N",
        help="With 'calibrate', max claims sampled per confidence label (default: 10)",
    )
    parser.add_argument(
        "--judge",
        type=str,
        choices=["cloud", "local", "auto"],
        default="cloud",
        help=(
            "With 'calibrate', which LLM judges traceability: cloud (fast tier, default), "
            "local (your OpenAI-compatible server, e.g. Ollama; errors if unavailable), "
            "or auto (local when reachable, else cloud)"
        ),
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        metavar="NAME",
        help="With '--judge local/auto', pin a specific local model instead of auto-picking",
    )
    parser.add_argument(
        "--judge-compare",
        action="store_true",
        help=(
            "With 'calibrate', judge the same claims with BOTH cloud and local and report "
            "agreement, measuring whether your local model can be trusted as the judge. "
            "Sidecars are written from the cloud verdicts."
        ),
    )
    parser.add_argument(
        "--pack-manifest",
        metavar="PATH",
        help=(
            "With 'calibrate', write a JSON manifest freezing the selected calibration "
            "pack, sidecar state, estimates, inference source-copy counts, "
            "and judge-agreement metadata."
        ),
    )
    parser.add_argument(
        "--pack-selection",
        metavar="PATH",
        help=(
            "With 'calibrate', read a curated calibration-pack selection JSON file "
            "with explicit report paths and representative coverage tags."
        ),
    )
    parser.add_argument(
        "--pack-selection-template",
        metavar="PATH",
        help=(
            "With 'calibrate', write a zero-spend curated selection template from "
            "the resolved reports. Tags are left empty for operator curation."
        ),
    )
    parser.add_argument(
        "--inspect-selection",
        metavar="PATH",
        help=(
            "With 'calibrate', print a zero-spend JSON inspection of a curated "
            "selection file and its representative coverage tags."
        ),
    )
    parser.add_argument(
        "--baseline-from",
        metavar="PATH",
        help=(
            "With 'calibrate', build a zero-spend baseline readiness artifact from an "
            "existing calibration pack manifest. Ready baselines require an explicit "
            "curated pack selection with representative tags."
        ),
    )
    parser.add_argument(
        "--baseline-out",
        metavar="PATH",
        help=(
            "With 'calibrate', write the baseline readiness JSON artifact. Requires "
            "--baseline-from or --pack-manifest."
        ),
    )
    parser.add_argument(
        "--baseline-md",
        metavar="PATH",
        help=(
            "With 'calibrate', write a Markdown summary for the baseline readiness "
            "artifact. Requires --baseline-from or --pack-manifest."
        ),
    )
    parser.add_argument(
        "--baseline-min-reports",
        type=int,
        default=5,
        metavar="N",
        help="With 'calibrate', minimum reports required for a baseline to be ready (default: 5)",
    )
    parser.add_argument(
        "--inspect-baseline",
        metavar="PATH",
        help=(
            "With 'calibrate', print a zero-spend JSON inspection of an existing "
            "baseline readiness artifact, including report-level blockers."
        ),
    )
    parser.add_argument(
        "--inspect-baseline-decision",
        metavar="PATH",
        help=(
            "With 'calibrate', print a zero-spend JSON inspection of an operator "
            "decision record against its recorded baseline artifact."
        ),
    )
    parser.add_argument(
        "--baseline-decision-from",
        metavar="PATH",
        help=(
            "With 'calibrate', record an explicit body-free operator decision from "
            "an existing baseline readiness artifact. Does not set environment variables."
        ),
    )
    parser.add_argument(
        "--baseline-decision-out",
        metavar="PATH",
        help="With '--baseline-decision-from', write the operator decision JSON artifact.",
    )
    parser.add_argument(
        "--baseline-decision",
        choices=["arm_gate", "keep_report_only"],
        help=("With '--baseline-decision-from', the explicit operator decision to record."),
    )
    parser.add_argument(
        "--baseline-decision-reviewer",
        metavar="TEXT",
        help="With '--baseline-decision-from', reviewer name or role for the decision record.",
    )
    parser.add_argument(
        "--baseline-decision-rationale",
        metavar="TEXT",
        help="With '--baseline-decision-from', operator rationale for the decision record.",
    )
    parser.add_argument(
        "--baseline-decision-note",
        action="append",
        default=[],
        metavar="TEXT",
        help="With '--baseline-decision-from', optional body-free review note. Repeatable.",
    )
