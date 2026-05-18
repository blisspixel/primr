from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from primr.ai.summarize import summarize_scraped_content_local
from primr.core.model_eval import _company_similarity


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


def write_website_summary_stage_eval_report(
    path: Path,
    *,
    model: str,
    rows: list[WebsiteSummaryEvalRow],
    base_url: str | None,
    api_key_env: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "companies_evaluated": len(rows),
        "avg_completeness_score": round(
            sum(row.completeness_score for row in rows) / max(1, len(rows)),
            2,
        ),
        "rows": [row.__dict__ for row in rows],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
