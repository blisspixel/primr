"""CLI helper for local stage eval artifact generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from primr.core import local_stage_eval, source_relevance_eval


def handle_website_summary_local_stage_eval(
    *,
    config: Any,
    eval_metrics: Any,
    judge_models: list[str],
    missing_models: list[str],
    console: Any,
) -> tuple[int, Path | None]:
    """Run website-summary local stage eval and return generated quality evidence."""

    console.blank()
    console.step("Local Stage Eval")
    if config.eval_judge_model_list:
        console.info(f"Local stage model list: {config.eval_judge_model_list}")
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
        [config.eval_company]
        if config.eval_company
        else sorted({metric.company for metric in eval_metrics})
    )
    inputs = local_stage_eval.find_latest_website_summary_eval_inputs(
        Path(config.eval_working_root),
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
    stage_root = Path(config.eval_root) / config.eval_id / "website_summary_stage"
    stage_results: list[tuple[str, list[local_stage_eval.WebsiteSummaryEvalRow]]] = []
    for model_name in judge_models:
        console.info(f"Running local website-summary stage model: {model_name}")
        stage_rows = local_stage_eval.run_local_website_summary_stage_eval(
            inputs=inputs,
            model=model_name,
            output_root=stage_root,
            base_url=config.eval_judge_base_url,
            api_key_env=config.eval_judge_api_key_env,
        )
        stage_results.append((model_name, stage_rows))
        model_slug = _model_slug(model_name)
        report_path = stage_root / f"website_summary_stage.{model_slug}.json"
        local_stage_eval.write_website_summary_stage_eval_report(
            report_path,
            model=model_name,
            rows=stage_rows,
            base_url=config.eval_judge_base_url,
            api_key_env=config.eval_judge_api_key_env,
        )
        console.info(f"  companies: {len(stage_rows)}")
        console.info(f"  output: {report_path}")

    summary_json = stage_root / "website_summary_stage_summary.json"
    summary_md = stage_root / "website_summary_stage_summary.md"
    local_stage_eval.write_website_summary_stage_eval_summary(
        summary_json,
        eval_id=config.eval_id,
        results=stage_results,
    )
    local_stage_eval.write_website_summary_stage_eval_markdown(
        summary_md,
        eval_id=config.eval_id,
        results=stage_results,
    )
    generated_stage_quality_path = stage_root / "website_summary_stage_quality_evidence.json"
    local_stage_eval.write_website_summary_stage_quality_evidence(
        generated_stage_quality_path,
        eval_id=config.eval_id,
        results=stage_results,
    )
    selected_quality_path = generated_stage_quality_path
    console.info(f"Local stage eval summary: {summary_json}")
    console.info(f"Local stage eval markdown: {summary_md}")
    console.info(f"Local stage quality evidence: {generated_stage_quality_path}")

    if config.eval_stage_semantic_judge:
        semantic_judge_models = _semantic_judge_models(config, default_model=judge_models[0])
        console.info(
            "Running local website-summary semantic judge(s): " + ", ".join(semantic_judge_models)
        )
        semantic_results: list[
            tuple[str, list[local_stage_eval.WebsiteSummarySemanticEvalRow]]
        ] = []
        for model_name, stage_rows in stage_results:
            semantic_rows: list[local_stage_eval.WebsiteSummarySemanticEvalRow] = []
            for semantic_judge_model in semantic_judge_models:
                semantic_rows.extend(
                    local_stage_eval.run_local_website_summary_semantic_eval(
                        rows=stage_rows,
                        judge_model=semantic_judge_model,
                        base_url=config.eval_judge_base_url,
                        api_key_env=config.eval_judge_api_key_env,
                    )
                )
            semantic_results.append((model_name, semantic_rows))
            console.info(f"  judged {model_name}: {len(semantic_rows)} row(s)")

        semantic_report_path = stage_root / "website_summary_stage_semantic_eval.json"
        semantic_quality_path = stage_root / "website_summary_stage_semantic_quality_evidence.json"
        local_stage_eval.write_website_summary_semantic_eval_report(
            semantic_report_path,
            eval_id=config.eval_id,
            judge_model=", ".join(semantic_judge_models),
            results=semantic_results,
            base_url=config.eval_judge_base_url,
            api_key_env=config.eval_judge_api_key_env,
        )
        local_stage_eval.write_website_summary_semantic_quality_evidence(
            semantic_quality_path,
            eval_id=config.eval_id,
            results=semantic_results,
        )
        selected_quality_path = semantic_quality_path
        console.info(f"Local stage semantic eval: {semantic_report_path}")
        console.info(f"Local stage semantic quality evidence: {semantic_quality_path}")

    return 0, selected_quality_path


def handle_stage_quality_generation(
    config: Any,
    eval_metrics: Any,
    judge_models: list[str],
    missing_models: list[str],
    console: Any,
) -> tuple[int, Path | None]:
    """Run optional stage-quality evidence generators for eval scorecards."""

    generated_path: Path | None = None
    if config.eval_local_stage == "website-summary":
        exit_code, generated_path = handle_website_summary_local_stage_eval(
            config=config,
            eval_metrics=eval_metrics,
            judge_models=judge_models,
            missing_models=missing_models,
            console=console,
        )
        if exit_code != 0:
            return exit_code, generated_path
    if config.eval_source_relevance_fixture:
        return handle_source_relevance_fixture_eval(config=config, console=console)
    return 0, generated_path


def handle_source_relevance_fixture_eval(
    *,
    config: Any,
    console: Any,
) -> tuple[int, Path | None]:
    """Build source-relevance fixture evidence for review-only scorecards."""

    console.blank()
    console.step("Source Relevance Stage Eval")
    fixture_path = Path(config.eval_source_relevance_fixture)
    try:
        cases = source_relevance_eval.load_source_relevance_eval_fixture(fixture_path)
        rows = source_relevance_eval.build_source_relevance_eval_rows(cases)
    except (OSError, ValueError) as exc:
        console.error(f"Source relevance fixture eval failed: {exc}")
        return 1, None

    if not rows:
        console.error("Source relevance fixture eval produced no candidate rows.")
        return 1, None

    stage_root = Path(config.eval_root) / config.eval_id / "source_relevance_stage"
    report_path = stage_root / "source_relevance_stage_eval.json"
    markdown_path = stage_root / "source_relevance_stage_eval.md"
    quality_path = stage_root / "source_relevance_stage_quality_evidence.json"
    source_relevance_eval.write_source_relevance_stage_eval_report(
        report_path,
        eval_id=config.eval_id,
        fixture_path=fixture_path,
        rows=rows,
    )
    source_relevance_eval.write_source_relevance_stage_eval_markdown(
        markdown_path,
        eval_id=config.eval_id,
        rows=rows,
    )
    source_relevance_eval.write_source_relevance_stage_quality_evidence(
        quality_path,
        eval_id=config.eval_id,
        rows=rows,
    )
    console.info(f"Source relevance cases: {len({row.case_id for row in rows})}")
    console.info(f"Source relevance candidate rows: {len(rows)}")
    console.info(f"Source relevance eval: {report_path}")
    console.info(f"Source relevance eval markdown: {markdown_path}")
    console.info(f"Source relevance quality evidence: {quality_path}")
    return 0, quality_path


def _model_slug(model_name: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9]+", "-", model_name).strip("-").lower() or "model"


def _semantic_judge_models(config: Any, *, default_model: str) -> list[str]:
    raw = config.eval_stage_semantic_judge_model
    if not raw:
        return [default_model]
    models = [part.strip() for part in raw.split(",") if part.strip()]
    return list(dict.fromkeys(models)) or [default_model]
