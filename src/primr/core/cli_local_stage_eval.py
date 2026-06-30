"""CLI helper for local stage eval artifact generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from primr.core import local_stage_eval


def handle_website_summary_local_stage_eval(
    *,
    eval_id: str,
    eval_root: str,
    eval_working_root: str,
    eval_company: str | None,
    eval_metrics: Any,
    judge_models: list[str],
    missing_models: list[str],
    eval_judge_model_list: str | None,
    eval_judge_base_url: str | None,
    eval_judge_api_key_env: str,
    console: Any,
) -> tuple[int, Path | None]:
    """Run website-summary local stage eval and return generated quality evidence."""

    console.blank()
    console.step("Local Stage Eval")
    if eval_judge_model_list:
        console.info(f"Local stage model list: {eval_judge_model_list}")
    if missing_models:
        console.warn(
            "Skipping local stage models not installed in Ollama: " + ", ".join(missing_models)
        )
    if not judge_models:
        console.error(
            "No local models available for stage eval after resolving the requested list."
        )
        return 1, None

    target_companies = (
        [eval_company] if eval_company else sorted({metric.company for metric in eval_metrics})
    )
    inputs = local_stage_eval.find_latest_website_summary_eval_inputs(
        Path(eval_working_root),
        companies=target_companies or None,
    )
    if not inputs:
        console.warn(
            "No working folders with scraped_content.txt and scraped_website_summary.txt found for local stage eval."
        )
        return 0, None

    console.info(
        f"Stage=website-summary, Companies={', '.join(row.company for row in inputs)}, "
        f"Models={', '.join(judge_models)}"
    )
    stage_root = Path(eval_root) / eval_id / "website_summary_stage"
    stage_results: list[tuple[str, list[Any]]] = []
    for model_name in judge_models:
        console.info(f"Running local website-summary stage model: {model_name}")
        stage_rows = local_stage_eval.run_local_website_summary_stage_eval(
            inputs=inputs,
            model=model_name,
            output_root=stage_root,
            base_url=eval_judge_base_url,
            api_key_env=eval_judge_api_key_env,
        )
        stage_results.append((model_name, stage_rows))
        model_slug = _model_slug(model_name)
        report_path = stage_root / f"website_summary_stage.{model_slug}.json"
        local_stage_eval.write_website_summary_stage_eval_report(
            report_path,
            model=model_name,
            rows=stage_rows,
            base_url=eval_judge_base_url,
            api_key_env=eval_judge_api_key_env,
        )
        console.info(f"  companies: {len(stage_rows)}")
        console.info(f"  output: {report_path}")

    summary_json = stage_root / "website_summary_stage_summary.json"
    summary_md = stage_root / "website_summary_stage_summary.md"
    local_stage_eval.write_website_summary_stage_eval_summary(
        summary_json,
        eval_id=eval_id,
        results=stage_results,
    )
    local_stage_eval.write_website_summary_stage_eval_markdown(
        summary_md,
        eval_id=eval_id,
        results=stage_results,
    )
    generated_stage_quality_path = stage_root / "website_summary_stage_quality_evidence.json"
    local_stage_eval.write_website_summary_stage_quality_evidence(
        generated_stage_quality_path,
        eval_id=eval_id,
        results=stage_results,
    )
    console.info(f"Local stage eval summary: {summary_json}")
    console.info(f"Local stage eval markdown: {summary_md}")
    console.info(f"Local stage quality evidence: {generated_stage_quality_path}")
    return 0, generated_stage_quality_path


def _model_slug(model_name: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9]+", "-", model_name).strip("-").lower() or "model"
