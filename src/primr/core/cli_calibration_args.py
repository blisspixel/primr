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
            "pack, sidecar state, estimates, and judge-agreement metadata."
        ),
    )
    parser.add_argument(
        "--baseline-from",
        metavar="PATH",
        help=(
            "With 'calibrate', build a zero-spend baseline readiness artifact from an "
            "existing calibration pack manifest."
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
