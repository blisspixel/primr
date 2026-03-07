"""
Versioned model/profile evaluation utilities.

This module compares report quality and estimated cost across profiles
using already-generated report artifacts. It is intentionally offline-first:
no API calls are required for analysis.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from primr.config.models import PrimrModels
from primr.qa.report_analyzer import ReportAnalyzer
from primr.utils.cost_estimator import estimate_cost

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pathlib import Path


EVAL_PROFILES: tuple[str, ...] = ("full", "lite", "fast")
DEFAULT_BASELINE = "full"


@dataclass(frozen=True)
class ReportMetrics:
    company: str
    profile: str
    report_path: Path
    quality_score: float
    word_count: int
    estimated_pages: float
    citation_density: float
    citations_total: int
    key_sections_found: int
    key_sections_total: int
    confidence_labels: int
    trust_score: float
    decision_utility_score: float
    reuse_quality_score: float
    trust_gate_passed: bool
    utility_per_dollar: float


@dataclass(frozen=True)
class ProfileSummary:
    profile: str
    report_count: int
    avg_quality: float
    avg_trust: float
    avg_decision_utility: float
    avg_reuse_quality: float
    avg_word_count: float
    avg_pages: float
    avg_citation_density: float
    avg_utility_per_dollar: float
    trust_pass_rate: float
    estimated_cost_usd: float


@dataclass(frozen=True)
class EvaluationResult:
    eval_id: str
    eval_root: Path
    baseline: str
    profile_summaries: list[ProfileSummary]
    metrics: list[ReportMetrics]
    missing_pairs: list[tuple[str, str]]  # (company, profile)
    decision_rows: list[str]
    scorecard_md: Path
    scorecard_csv: Path


@dataclass(frozen=True)
class LLMJudgeRow:
    company: str
    baseline_profile: str
    candidate_profile: str
    winner_profile: str
    baseline_score: float
    candidate_score: float
    baseline_aspects: dict[str, float]
    candidate_aspects: dict[str, float]
    passes: int
    rationale: str
    cost_usd: float


def _extract_company_from_filename(report_path: Path) -> str:
    stem = report_path.stem
    markers = (
        "_Strategic_Overview_",
        "_Strategic_Overview",
        "_AI_Strategy_",
        "_AI_Recommendation_",
    )
    for marker in markers:
        if marker in stem:
            stem = stem.split(marker, 1)[0]
            break
    return stem.replace("_", " ").strip()


def _normalize_company_key(company: str) -> str:
    return re.sub(r"\s+", " ", company).strip().lower()


def _tokenize_company(company: str) -> set[str]:
    legal_suffixes = {
        "inc", "incorporated", "corp", "corporation", "co", "company",
        "llc", "ltd", "limited", "plc", "lp", "llp", "gmbh", "sa", "ag",
    }
    tokens = {t for t in re.findall(r"[a-z0-9]+", company.lower()) if t}
    stripped = {t for t in tokens if t not in legal_suffixes}
    return stripped or tokens


def _company_similarity(a: str, b: str) -> float:
    ta = _tokenize_company(a)
    tb = _tokenize_company(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _find_profile_reports(profile_dir: Path, profile: str) -> list[ReportMetrics]:
    if not profile_dir.exists():
        return []

    candidate_paths: list[Path] = []
    for ext in ("*.md", "*.txt"):
        candidate_paths.extend(profile_dir.glob(ext))

    # Compare main strategic overview outputs only.
    candidate_paths = [p for p in candidate_paths if "Strategic_Overview" in p.name]
    candidate_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    # Keep latest report per company.
    latest_by_company: dict[str, Path] = {}
    for path in candidate_paths:
        company = _extract_company_from_filename(path)
        if company and company not in latest_by_company:
            latest_by_company[company] = path

    metrics: list[ReportMetrics] = []
    for company, path in latest_by_company.items():
        analyzer = ReportAnalyzer(str(path))
        content = analyzer.content
        citations = analyzer.analyze_citations()
        structure = analyzer.analyze_structure()
        quality = analyzer.analyze_content_quality()
        confidence = analyzer.analyze_confidence_labels()
        citation_density = analyzer.analyze_citation_density()
        hypothesis = analyzer.analyze_hypothesis_coverage()

        key_total = len(structure["key_sections_found"]) + len(structure["key_sections_missing"])
        key_found = len(structure["key_sections_found"])

        # Deterministic quality score for cross-profile comparison.
        score = 0.0
        score += min(30.0, (citations["citation_coverage"] * 30.0))
        score += min(20.0, (key_found / max(1, key_total)) * 20.0)
        score += 20.0 if citation_density["meets_threshold"] else min(20.0, citation_density["density_per_1000_words"] * 5.0)
        score += 15.0 if confidence["meets_threshold"] else min(15.0, confidence["total_labels"] * 2.0)
        score += 15.0 if hypothesis["meets_threshold"] else min(15.0, hypothesis["total_signals"] * 3.0)
        quality_score = round(min(100.0, score), 2)

        section_ratio = key_found / max(1, key_total)
        citation_coverage = float(citations["citation_coverage"])
        confidence_ok = bool(confidence["meets_threshold"])
        trust_score = round(
            (citation_coverage * 50.0) +
            (section_ratio * 30.0) +
            (20.0 if confidence_ok else 10.0),
            2,
        )
        trust_gate_passed = (
            citation_coverage >= 0.6
            and section_ratio >= 0.75
            and confidence_ok
        )

        lower = content.lower()
        actionability_markers = [
            "next steps", "recommendation", "action", "roadmap",
            "timeline", "owner", "priority", "milestone",
        ]
        risk_markers = ["risk", "tradeoff", "constraint", "mitigation", "assumption"]
        probe_markers = [
            "key question", "discovery question", "worth validating",
            "hypothesis", "unknown", "to validate",
        ]
        action_hits = sum(lower.count(m) for m in actionability_markers)
        risk_hits = sum(lower.count(m) for m in risk_markers)
        probe_hits = sum(lower.count(m) for m in probe_markers)
        decision_utility = round(
            min(100.0, (action_hits * 5.0) + (risk_hits * 3.0) + (probe_hits * 2.0) + (section_ratio * 20.0)),
            2,
        )

        heading_count = len(re.findall(r"^##\s+.+$", content, flags=re.MULTILINE))
        bullet_count = len(re.findall(r"^\s*[-*]\s+", content, flags=re.MULTILINE))
        table_count = content.count("|---")
        reuse_quality = round(
            min(100.0, (heading_count * 2.5) + (bullet_count * 0.6) + (table_count * 8.0) + (confidence["total_labels"] * 0.3)),
            2,
        )

        metrics.append(
            ReportMetrics(
                company=company,
                profile=profile,
                report_path=path,
                quality_score=quality_score,
                word_count=quality["word_count"],
                estimated_pages=quality["estimated_pages"],
                citation_density=citation_density["density_per_1000_words"],
                citations_total=citation_density["total_citations"],
                key_sections_found=key_found,
                key_sections_total=key_total,
                confidence_labels=confidence["total_labels"],
                trust_score=trust_score,
                decision_utility_score=decision_utility,
                reuse_quality_score=reuse_quality,
                trust_gate_passed=trust_gate_passed,
                utility_per_dollar=0.0,  # set during profile summarization
            )
        )

    return metrics


def _estimated_profile_cost(profile: str) -> float:
    if profile == "fast":
        return estimate_cost("complete", include_ai_strategy=True, fast_mode=True).total_cost
    if profile == "lite":
        return estimate_cost("complete", include_ai_strategy=True, lite_strategy=True).total_cost
    return estimate_cost("complete", include_ai_strategy=True).total_cost


def _summarize_profile(profile: str, metrics: list[ReportMetrics]) -> ProfileSummary:
    count = len(metrics)
    est_cost = round(_estimated_profile_cost(profile), 2)
    if count == 0:
        return ProfileSummary(
            profile=profile,
            report_count=0,
            avg_quality=0.0,
            avg_trust=0.0,
            avg_decision_utility=0.0,
            avg_reuse_quality=0.0,
            avg_word_count=0.0,
            avg_pages=0.0,
            avg_citation_density=0.0,
            avg_utility_per_dollar=0.0,
            trust_pass_rate=0.0,
            estimated_cost_usd=est_cost,
        )

    avg_quality = round(sum(m.quality_score for m in metrics) / count, 2)
    avg_trust = round(sum(m.trust_score for m in metrics) / count, 2)
    avg_decision_utility = round(sum(m.decision_utility_score for m in metrics) / count, 2)
    avg_reuse_quality = round(sum(m.reuse_quality_score for m in metrics) / count, 2)
    avg_utility_per_dollar = round(avg_decision_utility / max(0.01, est_cost), 2)
    trust_pass_rate = round(sum(1 for m in metrics if m.trust_gate_passed) / count, 2)

    # backfill utility_per_dollar per-row with profile economics
    for i, m in enumerate(metrics):
        metrics[i] = ReportMetrics(
            company=m.company,
            profile=m.profile,
            report_path=m.report_path,
            quality_score=m.quality_score,
            word_count=m.word_count,
            estimated_pages=m.estimated_pages,
            citation_density=m.citation_density,
            citations_total=m.citations_total,
            key_sections_found=m.key_sections_found,
            key_sections_total=m.key_sections_total,
            confidence_labels=m.confidence_labels,
            trust_score=m.trust_score,
            decision_utility_score=m.decision_utility_score,
            reuse_quality_score=m.reuse_quality_score,
            trust_gate_passed=m.trust_gate_passed,
            utility_per_dollar=round(m.decision_utility_score / max(0.01, est_cost), 2),
        )

    return ProfileSummary(
        profile=profile,
        report_count=count,
        avg_quality=avg_quality,
        avg_trust=avg_trust,
        avg_decision_utility=avg_decision_utility,
        avg_reuse_quality=avg_reuse_quality,
        avg_word_count=round(sum(m.word_count for m in metrics) / count, 1),
        avg_pages=round(sum(m.estimated_pages for m in metrics) / count, 2),
        avg_citation_density=round(sum(m.citation_density for m in metrics) / count, 2),
        avg_utility_per_dollar=avg_utility_per_dollar,
        trust_pass_rate=trust_pass_rate,
        estimated_cost_usd=est_cost,
    )


def _load_manifest_targets(manifest_path: Path) -> list[str]:
    if not manifest_path.exists():
        return []
    companies: list[str] = []
    with open(manifest_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = (row.get("company") or row.get("company_name") or "").strip()
            if raw:
                companies.append(raw)
    # Preserve order, dedupe.
    seen: set[str] = set()
    ordered: list[str] = []
    for company in companies:
        if company not in seen:
            ordered.append(company)
            seen.add(company)
    return ordered


def _compute_missing_pairs(
    target_companies: list[str],
    profiles: tuple[str, ...],
    metrics: list[ReportMetrics],
) -> list[tuple[str, str]]:
    by_profile: dict[str, set[str]] = {p: set() for p in profiles}
    for m in metrics:
        by_profile.setdefault(m.profile, set()).add(_normalize_company_key(m.company))

    missing: list[tuple[str, str]] = []
    for company in target_companies:
        key = _normalize_company_key(company)
        for profile in profiles:
            if key not in by_profile.get(profile, set()):
                missing.append((company, profile))
    return missing


def _load_fast_companies_from_usage(usage_file: Path) -> list[str]:
    if not usage_file.exists():
        return []
    try:
        records = json.loads(usage_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to load usage file %s: %s", usage_file, e)
        return []

    companies: list[str] = []
    for rec in records:
        if str(rec.get("mode", "")).lower() != "fast":
            continue
        company = str(rec.get("company", "")).strip()
        if company:
            companies.append(company)

    seen: set[str] = set()
    ordered: list[str] = []
    for company in companies:
        key = _normalize_company_key(company)
        if key not in seen:
            ordered.append(company)
            seen.add(key)
    return ordered


def _find_strategic_reports(source_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for ext in ("*.md", "*.txt"):
        candidates.extend(source_dir.glob(f"*Strategic_Overview*{ext[1:]}"))
    return [p for p in candidates if p.is_file()]


def auto_stage_existing_reports(
    *,
    eval_id: str,
    eval_root: Path,
    source_dir: Path,
    profiles: tuple[str, ...],
    company: str | None = None,
    usage_file: Path | None = None,
) -> dict[str, list[Path]]:
    """
    Stage local existing report outputs into eval profile folders (no API spend).

    Returns:
        Mapping profile -> staged files.
    """
    eval_dir = eval_root / eval_id
    eval_dir.mkdir(parents=True, exist_ok=True)
    all_reports = _find_strategic_reports(source_dir)
    if not all_reports:
        return {p: [] for p in profiles}

    # Highest mtime first.
    all_reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    fast_companies: list[str] = []
    if usage_file:
        fast_companies = _load_fast_companies_from_usage(usage_file)
    fast_company_keys = [_normalize_company_key(c) for c in fast_companies]

    target_companies: list[str]
    if company:
        target_companies = [company]
    else:
        target_companies = fast_companies[:]
        if not target_companies:
            # Fallback: pick top company by most recent report.
            target_companies = [_extract_company_from_filename(all_reports[0])]

    staged: dict[str, list[Path]] = {p: [] for p in profiles}

    def _best_report_for(target_company: str, profile: str) -> Path | None:
        scored: list[tuple[float, int, int, Path]] = []
        for path in all_reports:
            candidate_company = _extract_company_from_filename(path)
            sim = _company_similarity(target_company, candidate_company)
            if sim < 0.34:
                continue
            size = path.stat().st_size
            ext_pref = 1 if path.suffix.lower() == ".md" else 0
            scored.append((sim, size, ext_pref, path))
        if not scored:
            return None

        # Prefer highest similarity first.
        top_sim = max(s for s, _, _, _ in scored)
        near = [item for item in scored if item[0] >= top_sim - 0.01]
        # Fast reports tend to be shorter; full/lite tend to be longer.
        if profile == "fast":
            near.sort(key=lambda t: (t[1], -t[2], -t[0]))
        else:
            near.sort(key=lambda t: (-t[1], -t[2], -t[0]))
        return near[0][3]

    manifest_profiles: dict[str, list[dict[str, str]]] = {}
    manifest: dict[str, Any] = {
        "eval_id": eval_id,
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(source_dir),
        "targets": target_companies,
        "profiles": manifest_profiles,
    }

    for profile in profiles:
        profile_dir = eval_dir / profile
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_entries: list[dict[str, str]] = []
        for target in target_companies:
            target_prefix = target.replace(" ", "_") + "_Strategic_Overview"
            for stale in profile_dir.glob(f"{target_prefix}*"):
                if stale.is_file():
                    stale.unlink()
            if profile == "fast":
                target_key = _normalize_company_key(target)
                has_fast_history = any(
                    _company_similarity(target_key, key) >= 0.5
                    for key in fast_company_keys
                )
                if not has_fast_history:
                    continue
            selected = _best_report_for(target, profile)
            if not selected:
                continue
            staged_name = f"{target.replace(' ', '_')}_Strategic_Overview{selected.suffix}"
            staged_path = profile_dir / staged_name
            shutil.copy2(selected, staged_path)
            staged[profile].append(staged_path)
            profile_entries.append({
                "company": target,
                "source_path": str(selected),
                "staged_path": str(staged_path),
            })
        manifest_profiles[profile] = profile_entries

    (eval_dir / "staging_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return staged


def _decision_table(
    summaries: list[ProfileSummary],
    baseline: str,
    quality_ratio_threshold: float,
    cost_ratio_threshold: float,
) -> list[str]:
    by_profile = {s.profile: s for s in summaries}
    base = by_profile.get(baseline)
    if not base or base.report_count == 0:
        return ["Baseline has no reports. Generate or place baseline outputs first."]

    rows: list[str] = []
    for summary in summaries:
        if summary.profile == baseline:
            rows.append(f"{summary.profile}: baseline")
            continue
        if summary.report_count == 0:
            rows.append(f"{summary.profile}: MISSING (no staged reports for comparison)")
            continue
        if summary.trust_pass_rate < 1.0:
            rows.append(
                f"{summary.profile}: FAIL_TRUST "
                f"(trust_pass_rate={summary.trust_pass_rate:.2f}; requires 1.00)"
            )
            continue
        quality_ratio = summary.avg_quality / max(1e-9, base.avg_quality)
        utility_ratio = summary.avg_decision_utility / max(1e-9, base.avg_decision_utility)
        cost_ratio = summary.estimated_cost_usd / max(1e-9, base.estimated_cost_usd)
        status = "PASS" if utility_ratio >= quality_ratio_threshold and cost_ratio <= cost_ratio_threshold else "FAIL"
        rows.append(
            f"{summary.profile}: {status} "
            f"(utility_ratio={utility_ratio:.2f}, quality_ratio={quality_ratio:.2f}, "
            f"cost_ratio={cost_ratio:.2f}, target_utility>={quality_ratio_threshold:.2f}, "
            f"target_cost<={cost_ratio_threshold:.2f})"
        )
    return rows


def evaluate_outputs(
    *,
    eval_id: str,
    eval_root: Path,
    profiles: tuple[str, ...],
    baseline: str,
    quality_ratio_threshold: float,
    cost_ratio_threshold: float,
    manifest_path: Path | None = None,
) -> EvaluationResult:
    eval_dir = eval_root / eval_id
    metrics_by_profile: dict[str, list[ReportMetrics]] = {}
    for profile in profiles:
        metrics = _find_profile_reports(eval_dir / profile, profile)
        metrics_by_profile[profile] = metrics

    if manifest_path:
        target_companies = _load_manifest_targets(manifest_path)
    else:
        baseline_companies = [m.company for m in metrics_by_profile.get(baseline, [])]
        target_companies = list(dict.fromkeys(baseline_companies))

    allowed_keys = {_normalize_company_key(c) for c in target_companies} if target_companies else set()

    all_metrics: list[ReportMetrics] = []
    profile_summaries: list[ProfileSummary] = []
    for profile in profiles:
        profile_metrics = metrics_by_profile.get(profile, [])
        if allowed_keys:
            profile_metrics = [
                m for m in profile_metrics
                if _normalize_company_key(m.company) in allowed_keys
            ]
        profile_summaries.append(_summarize_profile(profile, profile_metrics))
        all_metrics.extend(profile_metrics)

    missing_pairs = _compute_missing_pairs(target_companies, profiles, all_metrics) if target_companies else []
    decisions = _decision_table(profile_summaries, baseline, quality_ratio_threshold, cost_ratio_threshold)

    scorecard_md = eval_dir / "scorecard.md"
    scorecard_csv = eval_dir / "scorecard.csv"
    _write_scorecard_markdown(
        scorecard_md,
        eval_id=eval_id,
        baseline=baseline,
        summaries=profile_summaries,
        decisions=decisions,
        missing_pairs=missing_pairs,
    )
    _write_scorecard_csv(scorecard_csv, all_metrics)

    return EvaluationResult(
        eval_id=eval_id,
        eval_root=eval_root,
        baseline=baseline,
        profile_summaries=profile_summaries,
        metrics=all_metrics,
        missing_pairs=missing_pairs,
        decision_rows=decisions,
        scorecard_md=scorecard_md,
        scorecard_csv=scorecard_csv,
    )


def _write_scorecard_markdown(
    path: Path,
    *,
    eval_id: str,
    baseline: str,
    summaries: list[ProfileSummary],
    decisions: list[str],
    missing_pairs: list[tuple[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Primr Eval Scorecard: {eval_id}",
        "",
        f"- Baseline profile: `{baseline}`",
        "",
        "## Profile Summary",
        "",
        "| Profile | Reports | Trust Pass | Avg Utility | Avg Trust | Avg Reuse | Avg Quality | Utility/$ | Est. Cost (USD) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            f"| {s.profile} | {s.report_count} | {s.trust_pass_rate:.2f} | {s.avg_decision_utility:.2f} | "
            f"{s.avg_trust:.2f} | {s.avg_reuse_quality:.2f} | {s.avg_quality:.2f} | "
            f"{s.avg_utility_per_dollar:.2f} | {s.estimated_cost_usd:.2f} |"
        )

    lines.append("")
    lines.append("## Decision")
    lines.append("")
    for row in decisions:
        lines.append(f"- {row}")

    lines.append("")
    lines.append("## Missing Runs")
    lines.append("")
    if not missing_pairs:
        lines.append("- None")
    else:
        for company, profile in missing_pairs:
            lines.append(f"- {company} -> {profile}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_scorecard_csv(path: Path, metrics: list[ReportMetrics]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "company",
                "profile",
                "report_path",
                "quality_score",
                "trust_score",
                "decision_utility_score",
                "reuse_quality_score",
                "trust_gate_passed",
                "utility_per_dollar",
                "word_count",
                "estimated_pages",
                "citation_density_per_1000_words",
                "citations_total",
                "key_sections_found",
                "key_sections_total",
                "confidence_labels",
            ]
        )
        for m in metrics:
            writer.writerow(
                [
                    m.company,
                    m.profile,
                    str(m.report_path),
                    m.quality_score,
                    m.trust_score,
                    m.decision_utility_score,
                    m.reuse_quality_score,
                    m.trust_gate_passed,
                    m.utility_per_dollar,
                    m.word_count,
                    m.estimated_pages,
                    m.citation_density,
                    m.citations_total,
                    m.key_sections_found,
                    m.key_sections_total,
                    m.confidence_labels,
                ]
            )


def run_grok_judge(
    *,
    eval_result: EvaluationResult,
    baseline_profile: str,
    candidate_profile: str,
    max_pairs: int,
    passes: int,
    max_cost_usd: float,
    model: str = "grok-4-1-fast-reasoning",
) -> tuple[list[LLMJudgeRow], float]:
    """
    Run optional Grok LLM judging on existing staged report pairs.
    """
    from primr.ai.grok_client import get_grok_session_usage, grok_llm

    by_profile_company: dict[tuple[str, str], ReportMetrics] = {}
    for m in eval_result.metrics:
        by_profile_company[(m.profile, _normalize_company_key(m.company))] = m

    baseline_companies = [
        _normalize_company_key(m.company)
        for m in eval_result.metrics
        if m.profile == baseline_profile
    ]

    rows: list[LLMJudgeRow] = []
    total_cost = 0.0

    for company_key in baseline_companies:
        if len(rows) >= max_pairs:
            break
        base_metric = by_profile_company.get((baseline_profile, company_key))
        cand_metric = by_profile_company.get((candidate_profile, company_key))
        if not base_metric or not cand_metric:
            continue

        base_text = base_metric.report_path.read_text(encoding="utf-8", errors="ignore")
        cand_text = cand_metric.report_path.read_text(encoding="utf-8", errors="ignore")

        # Keep prompt bounded to control cost.
        base_excerpt = base_text[:10_000]
        cand_excerpt = cand_text[:10_000]

        prompt = f"""
You are grading two strategy reports for the same company.
Return STRICT JSON only:
{{
  "winner_profile": "baseline|candidate|tie",
  "baseline_aspects": {{
    "strategic_usefulness": 0-100,
    "evidence_quality": 0-100,
    "clarity_coherence": 0-100,
    "actionability": 0-100,
    "uncertainty_calibration": 0-100,
    "coverage_completeness": 0-100
  }},
  "candidate_aspects": {{
    "strategic_usefulness": 0-100,
    "evidence_quality": 0-100,
    "clarity_coherence": 0-100,
    "actionability": 0-100,
    "uncertainty_calibration": 0-100,
    "coverage_completeness": 0-100
  }},
  "rationale": "short explanation"
}}

Scoring dimensions:
- strategic usefulness for company intelligence
- evidence quality / citation trustworthiness
- clarity and coherence
- actionability for decision-makers
- uncertainty calibration (confidence labels, avoids overclaiming)
- coverage/completeness of key sections

Use this fixed weighted rubric for overall score:
- strategic_usefulness: 25%
- evidence_quality: 20%
- clarity_coherence: 15%
- actionability: 20%
- uncertainty_calibration: 10%
- coverage_completeness: 10%

Company: {base_metric.company}
Baseline profile ({baseline_profile}) metrics:
- quality_score={base_metric.quality_score}
- words={base_metric.word_count}
- citations={base_metric.citations_total}

Candidate profile ({candidate_profile}) metrics:
- quality_score={cand_metric.quality_score}
- words={cand_metric.word_count}
- citations={cand_metric.citations_total}

Baseline report excerpt:
\"\"\"{base_excerpt}\"\"\"

Candidate report excerpt:
\"\"\"{cand_excerpt}\"\"\"
"""
        aspect_keys = [
            "strategic_usefulness",
            "evidence_quality",
            "clarity_coherence",
            "actionability",
            "uncertainty_calibration",
            "coverage_completeness",
        ]
        weights = {
            "strategic_usefulness": 0.25,
            "evidence_quality": 0.20,
            "clarity_coherence": 0.15,
            "actionability": 0.20,
            "uncertainty_calibration": 0.10,
            "coverage_completeness": 0.10,
        }
        baseline_aspect_sum = dict.fromkeys(aspect_keys, 0.0)
        candidate_aspect_sum = dict.fromkeys(aspect_keys, 0.0)
        rationale_parts: list[str] = []
        effective_passes = 0
        row_cost = 0.0

        for _ in range(max(1, passes)):
            if total_cost >= max_cost_usd:
                break
            before = get_grok_session_usage()
            response = grok_llm(prompt, model=model, temperature=0.1, max_tokens=900)
            after = get_grok_session_usage()

            in_tokens = max(0, after["input_tokens"] - before["input_tokens"])
            out_tokens = max(0, after["output_tokens"] - before["output_tokens"])
            call_cost = PrimrModels.calculate_cost(PrimrModels.GROK_MODEL, in_tokens, out_tokens)
            total_cost += call_cost
            row_cost += call_cost

            parsed_baseline = dict.fromkeys(aspect_keys, base_metric.quality_score)
            parsed_candidate = dict.fromkeys(aspect_keys, cand_metric.quality_score)
            rationale = response.strip()
            try:
                raw = response.strip()
                start = raw.find("{")
                end = raw.rfind("}")
                if start >= 0 and end > start:
                    payload = json.loads(raw[start:end + 1])
                    b_obj = payload.get("baseline_aspects", {})
                    c_obj = payload.get("candidate_aspects", {})
                    for k in aspect_keys:
                        parsed_baseline[k] = float(b_obj.get(k, parsed_baseline[k]))
                        parsed_candidate[k] = float(c_obj.get(k, parsed_candidate[k]))
                    rationale = str(payload.get("rationale", rationale))
            except Exception as e:
                logger.warning("Model eval JSON parse failed: %s", e)

            for k in aspect_keys:
                baseline_aspect_sum[k] += max(0.0, min(100.0, parsed_baseline[k]))
                candidate_aspect_sum[k] += max(0.0, min(100.0, parsed_candidate[k]))
            rationale_parts.append(rationale[:240])
            effective_passes += 1

        if effective_passes == 0:
            continue

        baseline_aspects = {
            k: round(baseline_aspect_sum[k] / effective_passes, 2)
            for k in aspect_keys
        }
        candidate_aspects = {
            k: round(candidate_aspect_sum[k] / effective_passes, 2)
            for k in aspect_keys
        }

        base_score = round(sum(baseline_aspects[k] * weights[k] for k in aspect_keys), 2)
        cand_score = round(sum(candidate_aspects[k] * weights[k] for k in aspect_keys), 2)
        if abs(base_score - cand_score) <= 1.0:
            winner = "tie"
        else:
            winner = "baseline" if base_score > cand_score else "candidate"
        rationale = " | ".join(rationale_parts)[:600]

        winner_profile = (
            baseline_profile if winner == "baseline"
            else candidate_profile if winner == "candidate"
            else "tie"
        )
        rows.append(
            LLMJudgeRow(
                company=base_metric.company,
                baseline_profile=baseline_profile,
                candidate_profile=candidate_profile,
                winner_profile=winner_profile,
                baseline_score=round(base_score, 2),
                candidate_score=round(cand_score, 2),
                baseline_aspects=baseline_aspects,
                candidate_aspects=candidate_aspects,
                passes=effective_passes,
                rationale=rationale[:600],
                cost_usd=round(row_cost, 4),
            )
        )

    return rows, round(total_cost, 4)


def write_llm_judge_report(path: Path, rows: list[LLMJudgeRow], total_cost: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total_cost_usd": total_cost,
        "rows": [
            {
                "company": r.company,
                "baseline_profile": r.baseline_profile,
                "candidate_profile": r.candidate_profile,
                "winner_profile": r.winner_profile,
                "baseline_score": r.baseline_score,
                "candidate_score": r.candidate_score,
                "baseline_aspects": r.baseline_aspects,
                "candidate_aspects": r.candidate_aspects,
                "passes": r.passes,
                "rationale": r.rationale,
                "cost_usd": r.cost_usd,
            }
            for r in rows
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_fast_feedback_guidance(
    path: Path,
    *,
    eval_result: EvaluationResult,
    judge_rows: list[LLMJudgeRow] | None = None,
) -> None:
    """
    Generate a persistent fast-mode prompt guidance file from eval outputs.

    This creates a lightweight feedback loop so future `--fast` runs can
    incorporate observed quality gaps from deterministic eval + optional LLM judge.
    """
    fast_summary = next((s for s in eval_result.profile_summaries if s.profile == "fast"), None)
    fast_metrics = [m for m in eval_result.metrics if m.profile == "fast"]
    if not fast_summary or not fast_metrics:
        return

    avg_words = sum(m.word_count for m in fast_metrics) / max(1, len(fast_metrics))
    avg_citations = sum(m.citations_total for m in fast_metrics) / max(1, len(fast_metrics))
    avg_confidence = sum(m.confidence_labels for m in fast_metrics) / max(1, len(fast_metrics))
    avg_citation_density = sum(m.citation_density for m in fast_metrics) / max(1, len(fast_metrics))

    rules: list[str] = [
        "Prefer verified facts over speculative numbers; use 'Not publicly disclosed' when evidence is missing.",
        "Every section must end with exactly one 'What to validate:' line with a concrete discovery check.",
        "Use concise executive prose; remove repetitive claims and resolve contradictions into one evidence-backed statement.",
    ]

    if avg_citations < 18 or avg_citation_density < 1.2:
        rules.append("Increase citation density by grounding major claims with external or primary-source citations.")
    if avg_confidence < 24:
        rules.append("Improve uncertainty calibration by labeling non-obvious claims with confidence tags.")
    if avg_words < 7200:
        rules.append("Increase analytical depth: include more concrete evidence, tradeoffs, and decision implications per section.")
    if fast_summary.avg_decision_utility < 90:
        rules.append("Strengthen decision utility: prioritize recommendations, risks, constraints, and next-step diagnostics.")
    if fast_summary.avg_trust < 92:
        rules.append("Tighten trust discipline: avoid precise estimates unless directly sourced; otherwise state assumptions explicitly.")

    judge_insights: list[str] = []
    for row in judge_rows or []:
        if row.baseline_profile == "fast":
            aspects = row.baseline_aspects
        elif row.candidate_profile == "fast":
            aspects = row.candidate_aspects
        else:
            continue
        for aspect, score in aspects.items():
            if score < 80:
                judge_insights.append(f"Raise `{aspect}` quality (current LLM judge score: {score:.1f}).")
        if row.rationale:
            judge_insights.append(f"Judge note ({row.company}): {row.rationale}")

    # Deduplicate while preserving order.
    seen: set[str] = set()
    deduped_rules: list[str] = []
    for rule in [*rules, *judge_insights[:3]]:
        key = rule.strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped_rules.append(rule.strip())

    lines = [
        "# Fast Report Feedback Guidance",
        "",
        "Generated from eval signals to improve future `--fast` report quality.",
        "",
        f"- Eval ID: `{eval_result.eval_id}`",
        f"- Fast reports analyzed: `{len(fast_metrics)}`",
        f"- Avg quality: `{fast_summary.avg_quality:.2f}`",
        f"- Avg trust: `{fast_summary.avg_trust:.2f}`",
        f"- Avg decision utility: `{fast_summary.avg_decision_utility:.2f}`",
        f"- Avg words: `{avg_words:.0f}`",
        f"- Avg citations: `{avg_citations:.1f}`",
        "",
        "## Rules",
        "",
    ]
    lines.extend(f"- {r}" for r in deduped_rules)
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
