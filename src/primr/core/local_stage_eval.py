from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from primr.ai.summarize import summarize_scraped_content_local
from primr.core.model_eval import _company_similarity
from primr.core.stage_eval_scorecard import StageQualityEvidence
from primr.utils.security import mask_sensitive_data


@dataclass(frozen=True)
class WebsiteSummaryEvalInput:
    company: str
    working_dir: Path
    scraped_content_path: Path
    baseline_summary_path: Path


@dataclass(frozen=True)
class WebsiteSummaryEvalRow:
    company: str
    model: str
    working_dir: str
    input_pages: int
    local_summary_path: str
    baseline_summary_path: str
    baseline_words: int
    local_words: int
    baseline_source_sections: int
    local_source_sections: int
    baseline_source_citations: int
    local_source_citations: int
    baseline_open_questions: int
    local_open_questions: int
    baseline_has_synthesis: bool
    local_has_synthesis: bool
    source_section_ratio: float
    citation_ratio: float
    open_questions_ratio: float
    word_ratio: float
    completeness_score: float


@dataclass(frozen=True)
class WebsiteSummarySemanticEvalRow:
    company: str
    model: str
    judge_model: str
    working_dir: str
    semantic_score: float
    aspects: dict[str, float]
    rationale: str
    response_valid: bool
    input_tokens: int
    output_tokens: int


_SEMANTIC_ASPECT_WEIGHTS = {
    "strategic_coverage": 0.25,
    "factual_alignment": 0.35,
    "evidence_usefulness": 0.25,
    "uncertainty_calibration": 0.15,
}


def _display_company_name(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.replace("_", " ")).strip()


def parse_scraped_content_file(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^URL:\s*(?P<url>.+?)\n=+\n(?P<content>.*?)(?=^=+\nURL:\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    scraped: dict[str, str] = {}
    for match in pattern.finditer(text):
        url = match.group("url").strip()
        content = match.group("content").strip()
        if url and content:
            scraped[url] = content
    return scraped


def extract_summary_metrics(text: str) -> dict[str, Any]:
    words = len(re.findall(r"\b\w+\b", text))
    source_sections = len(re.findall(r"^### Source:", text, re.MULTILINE))
    source_citations = len(re.findall(r"\[Source:", text))
    has_synthesis = "## Cross-Page Synthesis" in text

    open_questions = 0
    match = re.search(
        r"^### Open Questions To Validate\s*$\n(?P<body>.*?)(?=^### |^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if match:
        body = match.group("body")
        open_questions = len(re.findall(r"^[-*]\s+", body, re.MULTILINE))

    return {
        "words": words,
        "source_sections": source_sections,
        "source_citations": source_citations,
        "open_questions": open_questions,
        "has_synthesis": has_synthesis,
    }


def _ratio_pct(local_value: int, baseline_value: int) -> float:
    if baseline_value <= 0:
        return 100.0 if local_value >= 0 else 0.0
    return round(min(100.0, (local_value / baseline_value) * 100.0), 2)


def _website_summary_completeness_score(
    *,
    baseline: dict[str, Any],
    local: dict[str, Any],
) -> float:
    source_score = _ratio_pct(local["source_sections"], baseline["source_sections"])
    citation_score = _ratio_pct(local["source_citations"], baseline["source_citations"])
    question_score = _ratio_pct(local["open_questions"], baseline["open_questions"])
    word_score = _ratio_pct(local["words"], baseline["words"])
    synthesis_score = 100.0 if local["has_synthesis"] == baseline["has_synthesis"] else 0.0
    return round(
        (source_score * 0.35)
        + (citation_score * 0.10)
        + (question_score * 0.15)
        + (word_score * 0.20)
        + (synthesis_score * 0.20),
        2,
    )


def _clamp_score(value: Any, fallback: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = fallback
    return round(max(0.0, min(100.0, numeric)), 2)


def _optional_score(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(100.0, numeric)), 2)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def build_website_summary_semantic_judge_prompt(
    *,
    company: str,
    baseline_summary: str,
    candidate_summary: str,
) -> str:
    """Build a local judge prompt for website-summary semantic quality."""

    return f"""Evaluate a candidate website-summary stage output against the current baseline for {company}.

Return only a compact JSON object with this shape:
{{
  "aspects": {{
    "strategic_coverage": 0-100,
    "factual_alignment": 0-100,
    "evidence_usefulness": 0-100,
    "uncertainty_calibration": 0-100
  }},
  "semantic_score": 0-100,
  "rationale": "one concise sentence"
}}

Scoring guidance:
- strategic_coverage: captures the company, offering, customer, partner, hiring, risk, and open-question signals that matter for downstream strategic analysis.
- factual_alignment: stays grounded in the provided website evidence and does not invent unsupported claims.
- evidence_usefulness: preserves source-linked facts and decision-useful distinctions rather than generic prose.
- uncertainty_calibration: flags gaps and unknowns honestly without overclaiming.

Baseline summary:
```text
{baseline_summary}
```

Candidate summary:
```text
{candidate_summary}
```
"""


def parse_website_summary_semantic_judge_response(
    text: str,
    *,
    fallback_score: float,
) -> tuple[float, dict[str, float], str, bool]:
    """Parse a semantic judge response without treating malformed output as truth."""

    fallback = _clamp_score(fallback_score, 0.0)
    fallback_aspects = dict.fromkeys(_SEMANTIC_ASPECT_WEIGHTS, fallback)
    payload = _extract_json_object(text)
    if payload is None:
        return (
            fallback,
            fallback_aspects,
            "Malformed semantic judge response; fell back to structural completeness score.",
            False,
        )

    raw_aspects = payload.get("aspects")
    aspects_obj = raw_aspects if isinstance(raw_aspects, dict) else {}
    aspects: dict[str, float] = {}
    parsed_aspect_count = 0
    for key in _SEMANTIC_ASPECT_WEIGHTS:
        score = _optional_score(aspects_obj.get(key))
        if score is not None:
            parsed_aspect_count += 1
            aspects[key] = score
        else:
            aspects[key] = fallback

    explicit_score = _optional_score(payload.get("semantic_score", payload.get("score")))
    if parsed_aspect_count == 0 and explicit_score is None:
        return (
            fallback,
            fallback_aspects,
            "Semantic judge JSON omitted numeric scores; fell back to structural completeness score.",
            False,
        )
    weighted_score = round(
        sum(aspects[key] * weight for key, weight in _SEMANTIC_ASPECT_WEIGHTS.items()),
        2,
    )
    semantic_score = explicit_score if explicit_score is not None else weighted_score
    rationale = str(payload.get("rationale", "")).strip()
    if not rationale:
        rationale = "Semantic judge returned scores without rationale."
    return semantic_score, aspects, rationale[:600], True


def find_latest_website_summary_eval_inputs(
    working_root: Path,
    *,
    companies: list[str] | None = None,
) -> list[WebsiteSummaryEvalInput]:
    results: list[WebsiteSummaryEvalInput] = []
    company_dirs = (
        [p for p in working_root.iterdir() if p.is_dir()] if working_root.exists() else []
    )

    if companies:
        for target in companies:
            best_company_dir: Path | None = None
            best_score = 0.0
            for company_dir in company_dirs:
                score = _company_similarity(target, _display_company_name(company_dir.name))
                if score > best_score:
                    best_score = score
                    best_company_dir = company_dir
            if not best_company_dir or best_score < 0.6:
                continue
            candidate_runs = [
                run_dir
                for run_dir in best_company_dir.iterdir()
                if run_dir.is_dir()
                and (run_dir / "scraped_content.txt").exists()
                and (run_dir / "scraped_website_summary.txt").exists()
            ]
            if not candidate_runs:
                continue
            selected = max(candidate_runs, key=lambda p: p.name)
            results.append(
                WebsiteSummaryEvalInput(
                    company=target,
                    working_dir=selected,
                    scraped_content_path=selected / "scraped_content.txt",
                    baseline_summary_path=selected / "scraped_website_summary.txt",
                )
            )
        return results

    for company_dir in company_dirs:
        candidate_runs = [
            run_dir
            for run_dir in company_dir.iterdir()
            if run_dir.is_dir()
            and (run_dir / "scraped_content.txt").exists()
            and (run_dir / "scraped_website_summary.txt").exists()
        ]
        if not candidate_runs:
            continue
        selected = max(candidate_runs, key=lambda p: p.name)
        results.append(
            WebsiteSummaryEvalInput(
                company=_display_company_name(company_dir.name),
                working_dir=selected,
                scraped_content_path=selected / "scraped_content.txt",
                baseline_summary_path=selected / "scraped_website_summary.txt",
            )
        )
    return sorted(results, key=lambda row: row.company.lower())


def run_local_website_summary_stage_eval(
    *,
    inputs: list[WebsiteSummaryEvalInput],
    model: str,
    output_root: Path,
    base_url: str | None = None,
    api_key_env: str = "LOCAL_LLM_API_KEY",
) -> list[WebsiteSummaryEvalRow]:
    rows: list[WebsiteSummaryEvalRow] = []
    model_slug = re.sub(r"[^a-zA-Z0-9]+", "-", model).strip("-").lower() or "model"

    for item in inputs:
        scraped_data = parse_scraped_content_file(item.scraped_content_path)
        if not scraped_data:
            continue
        company_slug = re.sub(r"[^a-zA-Z0-9]+", "_", item.company).strip("_") or "company"
        target_dir = output_root / model_slug / company_slug
        target_dir.mkdir(parents=True, exist_ok=True)
        local_summary = summarize_scraped_content_local(
            item.company,
            None,
            scraped_data,
            str(target_dir),
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            output_filename="scraped_website_summary.local.txt",
        )
        baseline_text = item.baseline_summary_path.read_text(encoding="utf-8")
        baseline_metrics = extract_summary_metrics(baseline_text)
        local_metrics = extract_summary_metrics(local_summary)
        rows.append(
            WebsiteSummaryEvalRow(
                company=item.company,
                model=model,
                working_dir=str(item.working_dir),
                input_pages=len(scraped_data),
                local_summary_path=str(target_dir / "scraped_website_summary.local.txt"),
                baseline_summary_path=str(item.baseline_summary_path),
                baseline_words=baseline_metrics["words"],
                local_words=local_metrics["words"],
                baseline_source_sections=baseline_metrics["source_sections"],
                local_source_sections=local_metrics["source_sections"],
                baseline_source_citations=baseline_metrics["source_citations"],
                local_source_citations=local_metrics["source_citations"],
                baseline_open_questions=baseline_metrics["open_questions"],
                local_open_questions=local_metrics["open_questions"],
                baseline_has_synthesis=baseline_metrics["has_synthesis"],
                local_has_synthesis=local_metrics["has_synthesis"],
                source_section_ratio=_ratio_pct(
                    local_metrics["source_sections"], baseline_metrics["source_sections"]
                ),
                citation_ratio=_ratio_pct(
                    local_metrics["source_citations"], baseline_metrics["source_citations"]
                ),
                open_questions_ratio=_ratio_pct(
                    local_metrics["open_questions"], baseline_metrics["open_questions"]
                ),
                word_ratio=_ratio_pct(local_metrics["words"], baseline_metrics["words"]),
                completeness_score=_website_summary_completeness_score(
                    baseline=baseline_metrics,
                    local=local_metrics,
                ),
            )
        )

    return rows


def run_local_website_summary_semantic_eval(
    *,
    rows: list[WebsiteSummaryEvalRow],
    judge_model: str,
    base_url: str | None = None,
    api_key_env: str = "LOCAL_LLM_API_KEY",
    max_rows: int | None = None,
) -> list[WebsiteSummarySemanticEvalRow]:
    """Judge website-summary stage outputs semantically with a local model."""

    from primr.ai.openai_compatible_client import chat_completion

    semantic_rows: list[WebsiteSummarySemanticEvalRow] = []
    selected_rows = rows[: max(0, max_rows)] if max_rows is not None else rows
    for row in selected_rows:
        baseline_summary = Path(row.baseline_summary_path).read_text(encoding="utf-8")
        candidate_summary = Path(row.local_summary_path).read_text(encoding="utf-8")
        prompt = build_website_summary_semantic_judge_prompt(
            company=row.company,
            baseline_summary=baseline_summary,
            candidate_summary=candidate_summary,
        )
        result = chat_completion(
            prompt,
            model=judge_model,
            base_url=base_url,
            api_key_env=api_key_env,
            temperature=0.1,
            max_tokens=700,
        )
        semantic_score, aspects, rationale, response_valid = (
            parse_website_summary_semantic_judge_response(
                result.text,
                fallback_score=row.completeness_score,
            )
        )
        semantic_rows.append(
            WebsiteSummarySemanticEvalRow(
                company=row.company,
                model=row.model,
                judge_model=judge_model,
                working_dir=row.working_dir,
                semantic_score=semantic_score,
                aspects=aspects,
                rationale=rationale,
                response_valid=response_valid,
                input_tokens=result.prompt_tokens,
                output_tokens=result.completion_tokens,
            )
        )
    return semantic_rows


def write_website_summary_stage_eval_report(
    path: Path,
    *,
    model: str,
    rows: list[WebsiteSummaryEvalRow],
    base_url: str | None,
    credential_env_var: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "base_url": base_url,
        "credential_env_var": credential_env_var,
        "companies_evaluated": len(rows),
        "avg_completeness_score": round(
            sum(row.completeness_score for row in rows) / max(1, len(rows)),
            2,
        ),
        "rows": [row.__dict__ for row in rows],
    }
    safe_json = mask_sensitive_data(json.dumps(payload, indent=2))

    # codeql[py/clear-text-storage-sensitive-data]
    path.write_text(safe_json, encoding="utf-8")


def write_website_summary_stage_eval_summary(
    path: Path,
    *,
    eval_id: str,
    results: list[tuple[str, list[WebsiteSummaryEvalRow]]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ranked: list[dict[str, str | int | float]] = []
    for model, rows in results:
        avg_score = (
            round(sum(row.completeness_score for row in rows) / max(1, len(rows)), 2)
            if rows
            else 0.0
        )
        avg_source_ratio = (
            round(sum(row.source_section_ratio for row in rows) / max(1, len(rows)), 2)
            if rows
            else 0.0
        )
        avg_word_ratio = (
            round(sum(row.word_ratio for row in rows) / max(1, len(rows)), 2) if rows else 0.0
        )
        avg_question_ratio = (
            round(sum(row.open_questions_ratio for row in rows) / max(1, len(rows)), 2)
            if rows
            else 0.0
        )
        ranked.append(
            {
                "model": model,
                "companies_evaluated": len(rows),
                "avg_completeness_score": avg_score,
                "avg_source_section_ratio": avg_source_ratio,
                "avg_word_ratio": avg_word_ratio,
                "avg_open_questions_ratio": avg_question_ratio,
            }
        )
    ranked.sort(
        key=lambda row: (
            -float(row["avg_completeness_score"]),
            -float(row["avg_source_section_ratio"]),
            -float(row["avg_word_ratio"]),
            row["model"],
        )
    )
    payload = {
        "eval_id": eval_id,
        "stage": "website-summary",
        "models_evaluated": len(results),
        "recommended_models": [row["model"] for row in ranked[:3]],
        "results": ranked,
    }
    safe_json = mask_sensitive_data(json.dumps(payload, indent=2))

    # codeql[py/clear-text-storage-sensitive-data]
    path.write_text(safe_json, encoding="utf-8")


def build_website_summary_semantic_agreement_summary(
    results: list[tuple[str, list[WebsiteSummarySemanticEvalRow]]],
    *,
    agreement_threshold_points: float = 10.0,
) -> dict[str, Any]:
    """Summarize local semantic judge agreement without using it as a gate."""

    model_summaries: list[dict[str, Any]] = []
    total_groups = 0
    total_agreed = 0
    all_spreads: list[float] = []

    for model, rows in results:
        by_company: dict[str, dict[str, float]] = {}
        for row in rows:
            if not row.response_valid:
                continue
            by_company.setdefault(row.company, {})[row.judge_model] = row.semantic_score

        spreads: list[float] = []
        for scores_by_judge in by_company.values():
            if len(scores_by_judge) < 2:
                continue
            scores = list(scores_by_judge.values())
            spreads.append(round(max(scores) - min(scores), 2))

        agreed_groups = sum(1 for spread in spreads if spread <= agreement_threshold_points)
        total_groups += len(spreads)
        total_agreed += agreed_groups
        all_spreads.extend(spreads)
        model_summaries.append(
            {
                "model": model,
                "comparable_groups": len(spreads),
                "agreed_groups": agreed_groups,
                "agreement_rate_pct": (
                    round((agreed_groups / len(spreads)) * 100.0, 2) if spreads else None
                ),
                "avg_score_spread": (round(sum(spreads) / len(spreads), 2) if spreads else None),
                "max_score_spread": max(spreads) if spreads else None,
            }
        )

    return {
        "agreement_threshold_points": agreement_threshold_points,
        "overall": {
            "comparable_groups": total_groups,
            "agreed_groups": total_agreed,
            "agreement_rate_pct": (
                round((total_agreed / total_groups) * 100.0, 2) if total_groups else None
            ),
            "avg_score_spread": (
                round(sum(all_spreads) / len(all_spreads), 2) if all_spreads else None
            ),
            "max_score_spread": max(all_spreads) if all_spreads else None,
        },
        "models": model_summaries,
    }


def write_website_summary_semantic_eval_report(
    path: Path,
    *,
    eval_id: str,
    judge_model: str,
    results: list[tuple[str, list[WebsiteSummarySemanticEvalRow]]],
    base_url: str | None,
    credential_env_var: str,
) -> None:
    """Write body-free semantic judge rows for website-summary stage evals."""

    path.parent.mkdir(parents=True, exist_ok=True)
    all_rows = [row for _, rows in results for row in rows]
    valid_rows = [row for row in all_rows if row.response_valid]
    judge_models = sorted({row.judge_model for row in all_rows})
    avg_score = (
        round(sum(row.semantic_score for row in all_rows) / max(1, len(all_rows)), 2)
        if all_rows
        else 0.0
    )
    judge_policy = (
        "local_judge_panel_review_signal_not_promotion_gate"
        if len(judge_models) > 1
        else "single_local_judge_review_signal_not_promotion_gate"
    )
    payload = {
        "schema_version": 1,
        "eval_id": eval_id,
        "stage": "website-summary",
        "evidence_type": "website_summary_semantic_eval",
        "decision_policy": "scorecard_input_only",
        "judge_policy": judge_policy,
        "judge_model": judge_model,
        "judge_models": judge_models,
        "base_url": base_url,
        "credential_env_var": credential_env_var,
        "rows_evaluated": len(all_rows),
        "valid_response_rows": len(valid_rows),
        "avg_semantic_score": avg_score,
        "agreement_summary": build_website_summary_semantic_agreement_summary(results),
        "results": [
            {
                "model": model,
                "rows": [asdict(row) for row in rows],
            }
            for model, rows in results
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_website_summary_semantic_quality_evidence(
    *,
    eval_id: str,
    results: list[tuple[str, list[WebsiteSummarySemanticEvalRow]]],
    stage_id: str = "fast.scrape_summary",
) -> list[StageQualityEvidence]:
    """Build scorecard-ready quality evidence from semantic judge rows."""

    evidence: list[StageQualityEvidence] = []
    for model, rows in results:
        valid_rows = [row for row in rows if row.response_valid]
        if not valid_rows:
            continue
        quality_score = round(
            sum(row.semantic_score for row in valid_rows) / max(1, len(valid_rows)),
            2,
        )
        judge_models = ",".join(sorted({row.judge_model for row in rows}))
        invalid_rows = len(rows) - len(valid_rows)
        source = f"website_summary_semantic:{eval_id}:{model}:judge={judge_models}"
        if invalid_rows:
            source += f":fallback_rows={invalid_rows}"
        evidence.append(
            StageQualityEvidence(
                stage_id=stage_id,
                backend_id=model,
                quality_score=quality_score,
                sample_size=len(valid_rows),
                source=source,
            )
        )
    return sorted(evidence, key=lambda row: (row.stage_id, row.backend_id))


def write_website_summary_semantic_quality_evidence(
    path: Path,
    *,
    eval_id: str,
    results: list[tuple[str, list[WebsiteSummarySemanticEvalRow]]],
    stage_id: str = "fast.scrape_summary",
) -> None:
    """Write semantic quality evidence for routed-stage scorecards."""

    path.parent.mkdir(parents=True, exist_ok=True)
    evidence = build_website_summary_semantic_quality_evidence(
        eval_id=eval_id,
        results=results,
        stage_id=stage_id,
    )
    payload = {
        "schema_version": 1,
        "evidence_type": "website_summary_semantic_quality",
        "decision_policy": "scorecard_input_only",
        "judge_policy": "single_local_judge_review_signal_not_promotion_gate",
        "eval_id": eval_id,
        "stage_id": stage_id,
        "quality_evidence": [asdict(row) for row in evidence],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_website_summary_stage_quality_evidence(
    *,
    eval_id: str,
    results: list[tuple[str, list[WebsiteSummaryEvalRow]]],
    stage_id: str = "fast.scrape_summary",
) -> list[StageQualityEvidence]:
    """Build scorecard-ready quality evidence from website-summary eval results."""

    evidence: list[StageQualityEvidence] = []
    for model, rows in results:
        if not rows:
            continue
        quality_score = round(
            sum(row.completeness_score for row in rows) / max(1, len(rows)),
            2,
        )
        evidence.append(
            StageQualityEvidence(
                stage_id=stage_id,
                backend_id=model,
                quality_score=quality_score,
                sample_size=len(rows),
                source=f"website_summary_stage:{eval_id}:{model}",
            )
        )
    return sorted(evidence, key=lambda row: (row.stage_id, row.backend_id))


def write_website_summary_stage_quality_evidence(
    path: Path,
    *,
    eval_id: str,
    results: list[tuple[str, list[WebsiteSummaryEvalRow]]],
    stage_id: str = "fast.scrape_summary",
) -> None:
    """Write structured quality evidence for routed-stage scorecards."""

    path.parent.mkdir(parents=True, exist_ok=True)
    evidence = build_website_summary_stage_quality_evidence(
        eval_id=eval_id,
        results=results,
        stage_id=stage_id,
    )
    payload = {
        "schema_version": 1,
        "evidence_type": "website_summary_stage_quality",
        "decision_policy": "scorecard_input_only",
        "eval_id": eval_id,
        "stage_id": stage_id,
        "quality_evidence": [asdict(row) for row in evidence],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_website_summary_stage_eval_markdown(
    path: Path,
    *,
    eval_id: str,
    results: list[tuple[str, list[WebsiteSummaryEvalRow]]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ranked_rows = []
    for model, rows in results:
        avg_score = (
            round(sum(row.completeness_score for row in rows) / max(1, len(rows)), 2)
            if rows
            else 0.0
        )
        avg_source_ratio = (
            round(sum(row.source_section_ratio for row in rows) / max(1, len(rows)), 2)
            if rows
            else 0.0
        )
        avg_word_ratio = (
            round(sum(row.word_ratio for row in rows) / max(1, len(rows)), 2) if rows else 0.0
        )
        avg_question_ratio = (
            round(sum(row.open_questions_ratio for row in rows) / max(1, len(rows)), 2)
            if rows
            else 0.0
        )
        ranked_rows.append(
            (model, rows, avg_score, avg_source_ratio, avg_word_ratio, avg_question_ratio)
        )
    ranked_rows.sort(key=lambda item: (-item[2], -item[3], -item[4], item[0]))

    lines = [
        f"# Local Website Summary Stage Eval: {eval_id}",
        "",
        "| Rank | Model | Companies | Avg Completeness | Source Ratio | Word Ratio | Open Questions Ratio |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for idx, (
        model,
        rows,
        avg_score,
        avg_source_ratio,
        avg_word_ratio,
        avg_question_ratio,
    ) in enumerate(ranked_rows, start=1):
        lines.append(
            f"| {idx} | {model} | {len(rows)} | {avg_score:.2f} | {avg_source_ratio:.2f} | {avg_word_ratio:.2f} | {avg_question_ratio:.2f} |"
        )
        for row in rows:
            lines.append(
                f"{row.company}: score={row.completeness_score:.2f}, pages={row.input_pages}, "
                f"sources={row.local_source_sections}/{row.baseline_source_sections}, "
                f"words={row.local_words}/{row.baseline_words}, "
                f"questions={row.local_open_questions}/{row.baseline_open_questions}, "
                f"synthesis={'yes' if row.local_has_synthesis else 'no'}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
