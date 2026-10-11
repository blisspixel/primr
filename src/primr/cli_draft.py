"""Import-light command for explicit local inference over a prep bundle."""

from __future__ import annotations

import argparse
import sys


def run_draft_cli(args: list[str] | None) -> int:
    """Preview or execute a bounded local draft without cloud configuration."""
    argv = args if args is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="primr draft", description="Write a cited local draft from a Primr prep bundle."
    )
    parser.add_argument("bundle", help="Published prep bundle directory.")
    parser.add_argument(
        "--local", action="store_true", required=True, help="Use only the configured local runtime."
    )
    parser.add_argument(
        "--model", help="Installed model ID (default: preferred installed chat family)."
    )
    parser.add_argument(
        "--max-chunks", type=int, default=12, help="Source-chunk cap, 1-24 (default: 12)."
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180,
        help="Request timeout in seconds, 10-300 (default: 180).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify sources and live models; make no inference calls or report files.",
    )
    parsed = parser.parse_args(argv[1:])

    from primr.ai.provider_availability import LocalCapacityBusyError
    from primr.core.local_draft import DraftCapacityBusyError, plan_local_draft, run_local_draft

    try:
        plan = plan_local_draft(
            parsed.bundle,
            model=parsed.model,
            max_chunks=parsed.max_chunks,
            timeout_seconds=parsed.timeout,
        )
        print(f"Local draft plan for {plan.evidence.company}:")
        print(f"  Model: {plan.runtime.model}; quantization: {plan.runtime.quantization}")
        print(f"  Runtime: {plan.runtime.runtime}; endpoint: {plan.runtime.base_url}")
        print(f"  Source chunks: {len(plan.chunks)}; request cap: {plan.maximum_requests}")
        print(
            f"  Conservative planning time: {plan.maximum_requests}-{plan.maximum_requests * 3} minutes; CPU loading or queues may take longer."
        )
        print(f"  Per-request timeout: {plan.timeout_seconds:g} seconds")
        print("  Recorded model API spend: $0.00; no cloud fallback, downloads, or model pulls")
        print("  Local draft, not the validated Primr report")
        if parsed.dry_run:
            print("  Inference calls: 0; report files written: 0 (dry run)")
            return 0
        result = run_local_draft(plan)
    except LocalCapacityBusyError as exc:
        print(
            f"Local capacity is busy. Retry after {exc.retry_after_seconds} seconds; no cloud fallback.",
            file=sys.stderr,
        )
        if isinstance(exc, DraftCapacityBusyError):
            print(f"  Checkpoint: {exc.checkpoint}", file=sys.stderr)
        return 75
    except KeyboardInterrupt:
        print("Local draft interrupted; incomplete report staging was removed.", file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Local draft failed: {exc}", file=sys.stderr)
        return 1
    print(f"Local draft complete: {result.claims} cited claims; recorded model API spend $0.00")
    print(f"  Markdown: {result.markdown_path}")
    print(f"  DOCX: {result.docx_path}")
    print(f"  Provenance: {result.manifest_path}")
    return 0
