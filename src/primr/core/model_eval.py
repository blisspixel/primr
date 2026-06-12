"""
Versioned model/profile evaluation utilities.

This module compares report quality and estimated cost across profiles
using already-generated report artifacts. It is intentionally offline-first:
no API calls are required for analysis.
"""

from __future__ import annotations

import csv
import dataclasses
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
    from collections.abc import Callable
    from pathlib import Path


EVAL_PROFILES: tuple[str, ...] = ("full", "lite", "fast")
DEFAULT_BASELINE = "full"


# =============================================================================
# Profile Slot Registry
# =============================================================================
#
# v1.24.0 prerequisite: cross-provider eval needs dynamic per-(provider x model
# x role-recipe) profile slots, not the fixed 3-tuple ("full", "lite", "fast").
# Registering a new slot lets the eval harness add cells incrementally — for
# example, a post-I/O Gemini 3.2 Flash variant becomes:
#
#     register_eval_profile(EvalProfileSlot(
#         name="grok43-gemini32flashlite",
#         recipe=ProfileRecipe(
#             reasoning="grok-4.3",
#             writing="gemini-3.2-flash-lite",
#             utility="gemini-3-flash-preview",
#         ),
#         estimated_cost_usd=0.65,
#     ))
#
# After registration: run primr against the corpus once for that slot, score
# the new pairs, and the rest of the matrix is unchanged. No full re-do.
#
# The three built-in slots (full / lite / fast) are pre-registered so existing
# eval flows keep working unchanged.


@dataclass(frozen=True)
class ProfileRecipe:
    """Per-role model assignments for an eval profile slot.

    Each role corresponds to a primr pipeline stage class:
      - reasoning: gap analysis, workbook, cross-validation, strategy
      - writing: bulk section writing, polish
      - utility: scrape summaries, link selection, QA
      - premium_research: Deep Research Agent (premium mode only)

    Roles can be None when the slot inherits the default for that role from
    pick_model_for_role. Unknown roles are accepted but have no effect today;
    they reserve namespace for future pipeline stages.
    """

    reasoning: str | None = None
    writing: str | None = None
    utility: str | None = None
    premium_research: str | None = None
    extra: dict[str, str] | None = None  # forward-compat for new role names

    def role_assignments(self) -> dict[str, str]:
        """Return the populated role → model_id mapping (None entries dropped)."""
        out: dict[str, str] = {}
        if self.reasoning:
            out["reasoning"] = self.reasoning
        if self.writing:
            out["writing"] = self.writing
        if self.utility:
            out["utility"] = self.utility
        if self.premium_research:
            out["premium_research"] = self.premium_research
        if self.extra:
            for k, v in self.extra.items():
                if v:
                    out[k] = v
        return out


@dataclass(frozen=True)
class EvalProfileSlot:
    """One cell in the eval matrix.

    Attributes:
        name: Slot identifier used as the directory name under eval_root and
            in scorecards. Must be filesystem-safe.
        recipe: Optional per-role model assignments. None for legacy profiles
            ("full", "lite", "fast") whose recipe is implicit in primr's mode
            flags rather than a per-role override.
        estimated_cost_usd: Optional fixed-cost override. When None, the
            estimator falls back to the legacy mode-based estimator
            (used by built-in full/lite/fast slots).
        description: Human-readable summary of the recipe (e.g.,
            "Grok 4.3 reasoning + Gemini 3.1 Flash-Lite writing").
        is_builtin: True for the three legacy slots; protects them from
            accidental unregister at module-init.
    """

    name: str
    recipe: ProfileRecipe | None = None
    estimated_cost_usd: float | None = None
    description: str = ""
    is_builtin: bool = False


_PROFILE_REGISTRY: dict[str, EvalProfileSlot] = {}


def register_eval_profile(slot: EvalProfileSlot, *, replace: bool = False) -> None:
    """Register a new eval profile slot.

    Args:
        slot: The slot to register.
        replace: If True, replace an existing entry with the same name. If
            False (default), raise ValueError on collision so the caller is
            forced to think about whether the redefinition was intentional.

    Raises:
        ValueError: If a slot with this name is already registered and
            replace=False.
    """
    if not slot.name:
        raise ValueError("EvalProfileSlot.name must be non-empty")
    if not replace and slot.name in _PROFILE_REGISTRY:
        existing = _PROFILE_REGISTRY[slot.name]
        raise ValueError(
            f"Profile slot {slot.name!r} is already registered "
            f"(existing: {existing.description or 'no description'}). "
            f"Pass replace=True to override."
        )
    _PROFILE_REGISTRY[slot.name] = slot


def unregister_eval_profile(name: str) -> bool:
    """Remove a profile slot. Built-in slots cannot be removed.

    Returns:
        True if the slot was removed, False if it didn't exist.

    Raises:
        ValueError: If the named slot is a built-in (full / lite / fast).
    """
    slot = _PROFILE_REGISTRY.get(name)
    if slot is None:
        return False
    if slot.is_builtin:
        raise ValueError(
            f"Cannot unregister built-in profile slot {name!r}. "
            f"Built-in slots are required for back-compat with existing eval flows."
        )
    del _PROFILE_REGISTRY[name]
    return True


def get_eval_profile(name: str) -> EvalProfileSlot | None:
    """Look up a registered profile slot by name. Returns None if not found."""
    return _PROFILE_REGISTRY.get(name)


def list_eval_profile_names() -> tuple[str, ...]:
    """Return all registered profile slot names in registration order."""
    return tuple(_PROFILE_REGISTRY.keys())


def list_eval_profiles() -> tuple[EvalProfileSlot, ...]:
    """Return all registered profile slots in registration order."""
    return tuple(_PROFILE_REGISTRY.values())


def _register_builtin_profiles() -> None:
    """Register the three legacy profile slots. Called at module init."""
    for name, description in (
        ("full", "Default Grok 4.3 hybrid pipeline (reasoning + writing + strategy)"),
        ("lite", "Premium pipeline with Pro instead of Deep Research for strategy"),
        ("fast", "Grok 4.3 low-effort + 4.20-non-reasoning bulk writing"),
    ):
        register_eval_profile(
            EvalProfileSlot(
                name=name,
                recipe=None,  # legacy slots use mode flags, not per-role recipe
                estimated_cost_usd=None,  # falls back to mode-based cost estimator
                description=description,
                is_builtin=True,
            )
        )


_register_builtin_profiles()


def _register_v1_24_0_eval_matrix() -> None:
    """Side-effect import of the v1.24.0 cross-provider eval matrix.

    Wrapped so a missing config module (e.g., during a partial install or
    docs-only checkout) doesn't break the eval CLI for built-in slots.
    See src/primr/config/eval_profiles.py.
    """
    try:
        import primr.config.eval_profiles  # noqa: F401  - side-effect import
    except ImportError as e:
        logger.warning(
            "Could not load v1.24.0 cross-provider eval matrix: %s. "
            "Built-in slots (full/lite/fast) remain available.",
            e,
        )


_register_v1_24_0_eval_matrix()


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
    # Artifact-drift signal: count of leaked internal-scaffolding markers
    # (bare [workbook]/[cross-ref], bold "What to validate:" lines, informal
    # [cite: label]). Must stay 0 on shipped reports — see ROADMAP item #1.
    scaffolding_leaks: int = 0
    # Label-calibration signal, read from the report's `primr calibrate`
    # sidecar when present (the eval itself stays offline — calibration is a
    # separate bounded paid step). Decidable = traceable + untraceable +
    # no_source; unfetchable claims are excluded (harness couldn't decide).
    calibrated: bool = False
    confirmed_traceable: int = 0
    confirmed_decidable: int = 0
    reported_traceable: int = 0
    reported_decidable: int = 0

    def traceability(self, label: str) -> float | None:
        """Per-report traceability precision for Confirmed/Reported."""
        if label == "Confirmed":
            traceable, decidable = self.confirmed_traceable, self.confirmed_decidable
        elif label == "Reported":
            traceable, decidable = self.reported_traceable, self.reported_decidable
        else:
            return None
        if not decidable:
            return None
        return traceable / decidable


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
    # Sum of scaffolding-leak counts across the profile's reports (drift gate).
    total_scaffolding_leaks: int = 0
    # Label-calibration aggregate (pooled across calibrated reports).
    calibrated_report_count: int = 0
    confirmed_traceability: float | None = None
    reported_traceability: float | None = None


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


@dataclass(frozen=True)
class LLMJudgeMetadata:
    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None


@dataclass(frozen=True)
class JudgeCallResult:
    text: str
    input_tokens: int
    output_tokens: int
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
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "llc",
        "ltd",
        "limited",
        "plc",
        "lp",
        "llp",
        "gmbh",
        "sa",
        "ag",
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


def _load_calibration_counts(report_path: Path) -> dict[str, int] | None:
    """Read traceability counts from a report's calibration sidecar, if any.

    Written by ``primr calibrate`` (``qa.calibration_runner``). Returns None
    when no sidecar exists or it is unreadable — calibration is optional and
    its absence must never affect the offline eval.
    """
    from primr.qa.calibration_runner import sidecar_path_for

    sidecar = sidecar_path_for(report_path)
    if not sidecar.exists():
        return None
    try:
        per_label = json.loads(sidecar.read_text(encoding="utf-8")).get("per_label", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    counts: dict[str, int] = {}
    for label in ("Confirmed", "Reported"):
        stats = per_label.get(label, {})
        traceable = int(stats.get("traceable", 0))
        decidable = traceable + int(stats.get("untraceable", 0)) + int(stats.get("no_source", 0))
        counts[f"{label.lower()}_traceable"] = traceable
        counts[f"{label.lower()}_decidable"] = decidable
    return counts


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
        leakage = analyzer.analyze_scaffolding_leakage()
        calibration = _load_calibration_counts(path)

        key_total = len(structure["key_sections_found"]) + len(structure["key_sections_missing"])
        key_found = len(structure["key_sections_found"])

        # Deterministic quality score for cross-profile comparison.
        score = 0.0
        score += min(30.0, (citations["citation_coverage"] * 30.0))
        score += min(20.0, (key_found / max(1, key_total)) * 20.0)
        score += (
            20.0
            if citation_density["meets_threshold"]
            else min(20.0, citation_density["density_per_1000_words"] * 5.0)
        )
        score += (
            15.0 if confidence["meets_threshold"] else min(15.0, confidence["total_labels"] * 2.0)
        )
        score += (
            15.0 if hypothesis["meets_threshold"] else min(15.0, hypothesis["total_signals"] * 3.0)
        )
        quality_score = round(min(100.0, score), 2)

        section_ratio = key_found / max(1, key_total)
        citation_coverage = float(citations["citation_coverage"])
        confidence_ok = bool(confidence["meets_threshold"])
        trust_score = round(
            (citation_coverage * 50.0) + (section_ratio * 30.0) + (20.0 if confidence_ok else 10.0),
            2,
        )
        trust_gate_passed = citation_coverage >= 0.6 and section_ratio >= 0.75 and confidence_ok

        lower = content.lower()
        actionability_markers = [
            "next steps",
            "recommendation",
            "action",
            "roadmap",
            "timeline",
            "owner",
            "priority",
            "milestone",
        ]
        risk_markers = ["risk", "tradeoff", "constraint", "mitigation", "assumption"]
        probe_markers = [
            "key question",
            "discovery question",
            "worth validating",
            "hypothesis",
            "unknown",
            "to validate",
        ]
        action_hits = sum(lower.count(m) for m in actionability_markers)
        risk_hits = sum(lower.count(m) for m in risk_markers)
        probe_hits = sum(lower.count(m) for m in probe_markers)
        decision_utility = round(
            min(
                100.0,
                (action_hits * 5.0)
                + (risk_hits * 3.0)
                + (probe_hits * 2.0)
                + (section_ratio * 20.0),
            ),
            2,
        )

        heading_count = len(re.findall(r"^##\s+.+$", content, flags=re.MULTILINE))
        bullet_count = len(re.findall(r"^\s*[-*]\s+", content, flags=re.MULTILINE))
        table_count = content.count("|---")
        reuse_quality = round(
            min(
                100.0,
                (heading_count * 2.5)
                + (bullet_count * 0.6)
                + (table_count * 8.0)
                + (confidence["total_labels"] * 0.3),
            ),
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
                scaffolding_leaks=int(leakage["total_leaked"]),
                calibrated=calibration is not None,
                confirmed_traceable=(calibration or {}).get("confirmed_traceable", 0),
                confirmed_decidable=(calibration or {}).get("confirmed_decidable", 0),
                reported_traceable=(calibration or {}).get("reported_traceable", 0),
                reported_decidable=(calibration or {}).get("reported_decidable", 0),
            )
        )

    return metrics


def _estimated_profile_cost(profile: str) -> float:
    """Resolve estimated cost for a profile.

    Resolution order:
      1. If the slot is registered with an explicit estimated_cost_usd, use it.
      2. Else if the slot has a recipe (cross-provider eval slot), compute cost
         from the recipe's role models. Today this returns a placeholder using
         the recipe's writing model rate at default token volumes — sharpen
         once primr's per-role token estimates are exposed by the cost
         estimator (v1.24.0 follow-on).
      3. Else fall back to the legacy mode-based estimator using the well-known
         names ("fast", "lite", anything else = full).

    The registry-based path is used for v1.24.0 cross-provider eval slots; the
    legacy fallback keeps existing full/lite/fast eval flows unchanged.
    """
    slot = _PROFILE_REGISTRY.get(profile)
    if slot is not None and slot.estimated_cost_usd is not None:
        return slot.estimated_cost_usd

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
    # (dataclasses.replace keeps every other field — a hand-listed rebuild
    # here silently dropped new fields once already)
    for i, m in enumerate(metrics):
        metrics[i] = dataclasses.replace(
            m, utility_per_dollar=round(m.decision_utility_score / max(0.01, est_cost), 2)
        )

    calibrated = [m for m in metrics if m.calibrated]
    confirmed_decidable = sum(m.confirmed_decidable for m in calibrated)
    reported_decidable = sum(m.reported_decidable for m in calibrated)

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
        total_scaffolding_leaks=sum(m.scaffolding_leaks for m in metrics),
        calibrated_report_count=len(calibrated),
        confirmed_traceability=(
            round(sum(m.confirmed_traceable for m in calibrated) / confirmed_decidable, 3)
            if confirmed_decidable
            else None
        ),
        reported_traceability=(
            round(sum(m.reported_traceable for m in calibrated) / reported_decidable, 3)
            if reported_decidable
            else None
        ),
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


_SAFE_EVAL_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _safe_eval_dir(eval_root: Path, eval_id: str) -> Path:
    """Resolve ``eval_root / eval_id`` after rejecting traversal/separators.

    The CLI's --eval-id is forwarded as a filesystem component to write
    scorecards, manifests, and per-profile staged report copies. Without
    a containment check, '../' or absolute eval_id values silently escape
    eval_root and let the eval workflow create or copy files anywhere the
    process can write.
    """
    if not _SAFE_EVAL_ID_RE.fullmatch(eval_id):
        raise ValueError(f"Unsafe eval_id (allowed: [A-Za-z0-9._-], 1-128 chars): {eval_id!r}")
    resolved_root = eval_root.resolve()
    candidate = (eval_root / eval_id).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as e:
        raise ValueError(f"eval_id resolves outside eval_root: {eval_id!r}") from e
    return candidate


def _sanitize_target_company(target: str) -> str:
    """Strip path separators and traversal sequences from a company name
    before using it as a glob/filename component.
    """
    if not target:
        return "Unknown_Company"
    cleaned = re.sub(r"[\\/]", "_", target)
    cleaned = cleaned.replace("..", "_")
    # Drop glob metacharacters so an attacker-chosen company name can't
    # accidentally match unrelated files during stale-file cleanup.
    cleaned = re.sub(r"[\*\?\[\]]", "_", cleaned)
    return cleaned.strip(" .") or "Unknown_Company"


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
    eval_dir = _safe_eval_dir(eval_root, eval_id)
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
            safe_target = _sanitize_target_company(target)
            target_prefix = safe_target.replace(" ", "_") + "_Strategic_Overview"
            for stale in profile_dir.glob(f"{target_prefix}*"):
                if stale.is_file():
                    stale.unlink()
            if profile == "fast":
                target_key = _normalize_company_key(target)
                has_fast_history = any(
                    _company_similarity(target_key, key) >= 0.5 for key in fast_company_keys
                )
                if not has_fast_history:
                    continue
            selected = _best_report_for(target, profile)
            if not selected:
                continue
            safe_target = _sanitize_target_company(target)
            staged_name = f"{safe_target.replace(' ', '_')}_Strategic_Overview{selected.suffix}"
            staged_path = profile_dir / staged_name
            # Defense in depth: confirm the staged path stays under the
            # profile dir even after path resolution.
            if not staged_path.resolve().is_relative_to(profile_dir.resolve()):
                logger.warning(
                    "Skipping staged copy for %r — resolved path escapes profile dir",
                    target,
                )
                continue
            shutil.copy2(selected, staged_path)
            staged[profile].append(staged_path)
            profile_entries.append(
                {
                    "company": target,
                    "source_path": str(selected),
                    "staged_path": str(staged_path),
                }
            )
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
        gate = _calibration_gate_threshold()
        if (
            gate is not None
            and summary.confirmed_traceability is not None
            and summary.confirmed_traceability < gate
        ):
            rows.append(
                f"{summary.profile}: FAIL_CALIBRATION "
                f"(confirmed_traceability={summary.confirmed_traceability:.2f}; "
                f"requires >= {gate:.2f})"
            )
            continue
        quality_ratio = summary.avg_quality / max(1e-9, base.avg_quality)
        utility_ratio = summary.avg_decision_utility / max(1e-9, base.avg_decision_utility)
        cost_ratio = summary.estimated_cost_usd / max(1e-9, base.estimated_cost_usd)
        status = (
            "PASS"
            if utility_ratio >= quality_ratio_threshold and cost_ratio <= cost_ratio_threshold
            else "FAIL"
        )
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
    eval_dir = _safe_eval_dir(eval_root, eval_id)
    metrics_by_profile: dict[str, list[ReportMetrics]] = {}
    for profile in profiles:
        metrics = _find_profile_reports(eval_dir / profile, profile)
        metrics_by_profile[profile] = metrics

    if manifest_path:
        target_companies = _load_manifest_targets(manifest_path)
    else:
        baseline_companies = [m.company for m in metrics_by_profile.get(baseline, [])]
        target_companies = list(dict.fromkeys(baseline_companies))

    allowed_keys = (
        {_normalize_company_key(c) for c in target_companies} if target_companies else set()
    )

    all_metrics: list[ReportMetrics] = []
    profile_summaries: list[ProfileSummary] = []
    for profile in profiles:
        profile_metrics = metrics_by_profile.get(profile, [])
        if allowed_keys:
            profile_metrics = [
                m for m in profile_metrics if _normalize_company_key(m.company) in allowed_keys
            ]
        profile_summaries.append(_summarize_profile(profile, profile_metrics))
        all_metrics.extend(profile_metrics)

    missing_pairs = (
        _compute_missing_pairs(target_companies, profiles, all_metrics) if target_companies else []
    )
    decisions = _decision_table(
        profile_summaries, baseline, quality_ratio_threshold, cost_ratio_threshold
    )

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
    lines.append("## Artifact Drift")
    lines.append("")
    lines.append(
        "Scaffolding-leak markers ([workbook]/[cross-ref], bold 'What to validate:' "
        "lines, informal [cite: label]) that should never reach a shipped report. "
        "Target: 0 per profile (see ROADMAP item #1)."
    )
    lines.append("")
    lines.append("| Profile | Reports | Scaffolding Leaks | Status |")
    lines.append("|---|---:|---:|---|")
    for s in summaries:
        status = "clean" if s.total_scaffolding_leaks == 0 else "DRIFT"
        lines.append(f"| {s.profile} | {s.report_count} | {s.total_scaffolding_leaks} | {status} |")

    lines.append("")
    lines.append("## Label Calibration")
    lines.append("")
    lines.append(
        "Traceability of (Confirmed)/(Reported) claims against the fetched text "
        "of their cited sources, pooled from `primr calibrate` sidecars. "
        f"Gate threshold: {_calibration_gate_description()}."
    )
    lines.append("")
    lines.append("| Profile | Calibrated Reports | Confirmed | Reported | Status |")
    lines.append("|---|---:|---:|---:|---|")
    gate = _calibration_gate_threshold()
    for s in summaries:
        confirmed = (
            f"{s.confirmed_traceability:.0%}" if s.confirmed_traceability is not None else "-"
        )
        reported = f"{s.reported_traceability:.0%}" if s.reported_traceability is not None else "-"
        lines.append(
            f"| {s.profile} | {s.calibrated_report_count} | {confirmed} | {reported} "
            f"| {_calibration_status(s, gate)} |"
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


def _calibration_gate_threshold() -> float | None:
    """The Confirmed-claim traceability hard-gate threshold, if armed.

    ``PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY`` is a fraction in (0, 1]. Unset
    (the default until a measured baseline exists) means report-only: the
    scorecard shows the numbers but no profile fails on them. Once the
    baseline lands, the default flips to the measured floor per the 1.x
    design (docs/design/1x-completion.md, workstream 1).
    """
    import os

    raw = os.environ.get("PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Ignoring malformed PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY=%r", raw)
        return None
    if not 0.0 < value <= 1.0:
        logger.warning(
            "Ignoring out-of-range PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY=%r (need 0-1]", raw
        )
        return None
    return value


def _calibration_gate_description() -> str:
    gate = _calibration_gate_threshold()
    if gate is None:
        return "not armed (PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY unset; report-only until a baseline exists)"
    return f"Confirmed >= {gate:.0%} (PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY)"


def _calibration_status(summary: ProfileSummary, gate: float | None) -> str:
    if summary.calibrated_report_count == 0:
        return "no data"
    if summary.confirmed_traceability is None:
        return "no decidable Confirmed claims"
    if gate is not None and summary.confirmed_traceability < gate:
        return "BELOW GATE"
    return "ok"


def _round_or_blank(value: float | None) -> float | str:
    return round(value, 3) if value is not None else ""


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
                "scaffolding_leaks",
                "calibrated",
                "confirmed_traceability",
                "reported_traceability",
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
                    m.scaffolding_leaks,
                    m.calibrated,
                    _round_or_blank(m.traceability("Confirmed")),
                    _round_or_blank(m.traceability("Reported")),
                ]
            )


def _build_judge_prompt(
    *,
    base_metric: ReportMetrics,
    cand_metric: ReportMetrics,
    baseline_profile: str,
    candidate_profile: str,
) -> str:
    base_text = base_metric.report_path.read_text(encoding="utf-8", errors="ignore")
    cand_text = cand_metric.report_path.read_text(encoding="utf-8", errors="ignore")
    base_excerpt = base_text[:10_000]
    cand_excerpt = cand_text[:10_000]
    return f"""
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
```text
{base_excerpt}
```

Candidate report excerpt:
```text
{cand_excerpt}
```
"""


def _run_llm_judge(
    *,
    eval_result: EvaluationResult,
    baseline_profile: str,
    candidate_profile: str,
    max_pairs: int,
    passes: int,
    max_cost_usd: float,
    invoke: Callable[[str], JudgeCallResult],
) -> tuple[list[LLMJudgeRow], float]:
    by_profile_company: dict[tuple[str, str], ReportMetrics] = {}
    for metric in eval_result.metrics:
        by_profile_company[(metric.profile, _normalize_company_key(metric.company))] = metric

    baseline_companies = [
        _normalize_company_key(metric.company)
        for metric in eval_result.metrics
        if metric.profile == baseline_profile
    ]

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

    rows: list[LLMJudgeRow] = []
    total_cost = 0.0

    for company_key in baseline_companies:
        if len(rows) >= max_pairs:
            break
        base_metric = by_profile_company.get((baseline_profile, company_key))
        cand_metric = by_profile_company.get((candidate_profile, company_key))
        if not base_metric or not cand_metric:
            continue

        prompt = _build_judge_prompt(
            base_metric=base_metric,
            cand_metric=cand_metric,
            baseline_profile=baseline_profile,
            candidate_profile=candidate_profile,
        )

        baseline_aspect_sum = dict.fromkeys(aspect_keys, 0.0)
        candidate_aspect_sum = dict.fromkeys(aspect_keys, 0.0)
        rationale_parts: list[str] = []
        effective_passes = 0
        row_cost = 0.0

        for _ in range(max(1, passes)):
            if max_cost_usd > 0 and total_cost >= max_cost_usd:
                break
            result = invoke(prompt)
            total_cost += result.cost_usd
            row_cost += result.cost_usd

            parsed_baseline = dict.fromkeys(aspect_keys, base_metric.quality_score)
            parsed_candidate = dict.fromkeys(aspect_keys, cand_metric.quality_score)
            rationale = result.text.strip()
            try:
                raw = result.text.strip()
                start = raw.find("{")
                end = raw.rfind("}")
                if start >= 0 and end > start:
                    payload = json.loads(raw[start : end + 1])
                    b_obj = payload.get("baseline_aspects", {})
                    c_obj = payload.get("candidate_aspects", {})
                    for key in aspect_keys:
                        parsed_baseline[key] = float(b_obj.get(key, parsed_baseline[key]))
                        parsed_candidate[key] = float(c_obj.get(key, parsed_candidate[key]))
                    rationale = str(payload.get("rationale", rationale))
            except Exception as exc:
                logger.warning("Model eval JSON parse failed: %s", exc)

            for key in aspect_keys:
                baseline_aspect_sum[key] += max(0.0, min(100.0, parsed_baseline[key]))
                candidate_aspect_sum[key] += max(0.0, min(100.0, parsed_candidate[key]))
            rationale_parts.append(rationale[:240])
            effective_passes += 1

        if effective_passes == 0:
            continue

        baseline_aspects = {
            key: round(baseline_aspect_sum[key] / effective_passes, 2) for key in aspect_keys
        }
        candidate_aspects = {
            key: round(candidate_aspect_sum[key] / effective_passes, 2) for key in aspect_keys
        }

        base_score = round(sum(baseline_aspects[key] * weights[key] for key in aspect_keys), 2)
        cand_score = round(sum(candidate_aspects[key] * weights[key] for key in aspect_keys), 2)
        if abs(base_score - cand_score) <= 1.0:
            winner = "tie"
        else:
            winner = "baseline" if base_score > cand_score else "candidate"
        rationale = " | ".join(rationale_parts)[:600]
        winner_profile = (
            baseline_profile
            if winner == "baseline"
            else candidate_profile
            if winner == "candidate"
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


def run_grok_judge(
    *,
    eval_result: EvaluationResult,
    baseline_profile: str,
    candidate_profile: str,
    max_pairs: int,
    passes: int,
    max_cost_usd: float,
    model: str = "grok-4.3",
) -> tuple[list[LLMJudgeRow], float]:
    """Run optional Grok LLM judging on existing staged report pairs."""
    from primr.ai.grok_client import get_grok_session_usage, grok_llm

    def _invoke(prompt: str) -> JudgeCallResult:
        before = get_grok_session_usage()
        response = grok_llm(prompt, model=model, temperature=0.1, max_tokens=900)
        after = get_grok_session_usage()
        in_tokens = max(0, after["input_tokens"] - before["input_tokens"])
        out_tokens = max(0, after["output_tokens"] - before["output_tokens"])
        cost = PrimrModels.calculate_cost(PrimrModels.GROK_MODEL, in_tokens, out_tokens)
        return JudgeCallResult(
            text=response,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            cost_usd=cost,
        )

    return _run_llm_judge(
        eval_result=eval_result,
        baseline_profile=baseline_profile,
        candidate_profile=candidate_profile,
        max_pairs=max_pairs,
        passes=passes,
        max_cost_usd=max_cost_usd,
        invoke=_invoke,
    )


def run_local_judge(
    *,
    eval_result: EvaluationResult,
    baseline_profile: str,
    candidate_profile: str,
    max_pairs: int,
    passes: int,
    max_cost_usd: float,
    model: str,
    base_url: str | None = None,
    api_key_env: str = "LOCAL_LLM_API_KEY",
) -> tuple[list[LLMJudgeRow], float]:
    """Run optional local OpenAI-compatible LLM judging on staged report pairs."""
    from primr.ai.openai_compatible_client import chat_completion

    def _invoke(prompt: str) -> JudgeCallResult:
        result = chat_completion(
            prompt,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            temperature=0.1,
            max_tokens=900,
        )
        return JudgeCallResult(
            text=result.text,
            input_tokens=result.prompt_tokens,
            output_tokens=result.completion_tokens,
            cost_usd=0.0,
        )

    return _run_llm_judge(
        eval_result=eval_result,
        baseline_profile=baseline_profile,
        candidate_profile=candidate_profile,
        max_pairs=max_pairs,
        passes=passes,
        max_cost_usd=max_cost_usd,
        invoke=_invoke,
    )


def _model_slug(model: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", model.strip()).strip("-").lower()
    return slug or "model"


def get_eval_judge_candidate_profiles(
    eval_result: EvaluationResult,
    *,
    baseline_profile: str,
) -> list[str]:
    """Return non-baseline profiles with staged reports, preserving eval order."""
    return [
        summary.profile
        for summary in eval_result.profile_summaries
        if summary.profile != baseline_profile and summary.report_count > 0
    ]


def _winner_majority_label(winner_counts: dict[str, int]) -> str:
    if not winner_counts:
        return "unknown"
    return max(
        winner_counts.items(),
        key=lambda item: (item[1], item[0] != "tie", item[0]),
    )[0]


def write_local_judge_sweep_summary(
    path: Path,
    *,
    eval_id: str,
    baseline_profile: str,
    candidate_profiles: list[str],
    results: list[tuple[LLMJudgeMetadata, list[LLMJudgeRow], float]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, Any]] = []
    winner_counts: dict[str, int] = {}
    for metadata, rows, total_cost in results:
        row_winner_counts: dict[str, int] = {}
        for row in rows:
            row_winner_counts[row.winner_profile] = row_winner_counts.get(row.winner_profile, 0) + 1
        winner = _winner_majority_label(row_winner_counts) if row_winner_counts else "unknown"
        winner_counts[winner] = winner_counts.get(winner, 0) + 1
        avg_baseline = (
            round(sum(row.baseline_score for row in rows) / max(1, len(rows)), 2) if rows else 0.0
        )
        avg_candidate = (
            round(sum(row.candidate_score for row in rows) / max(1, len(rows)), 2) if rows else 0.0
        )
        aspect_names = (
            sorted({*rows[0].baseline_aspects.keys(), *rows[0].candidate_aspects.keys()})
            if rows
            else []
        )
        avg_baseline_aspects = {
            name: round(
                sum(row.baseline_aspects.get(name, 0.0) for row in rows) / max(1, len(rows)),
                2,
            )
            for name in aspect_names
        }
        avg_candidate_aspects = {
            name: round(
                sum(row.candidate_aspects.get(name, 0.0) for row in rows) / max(1, len(rows)),
                2,
            )
            for name in aspect_names
        }
        avg_aspect_gap = {
            name: round(avg_baseline_aspects[name] - avg_candidate_aspects[name], 2)
            for name in aspect_names
        }
        candidate_breakdown: dict[str, dict[str, Any]] = {}
        for candidate in sorted({row.candidate_profile for row in rows}):
            candidate_rows = [row for row in rows if row.candidate_profile == candidate]
            candidate_winner_counts: dict[str, int] = {}
            for row in candidate_rows:
                candidate_winner_counts[row.winner_profile] = (
                    candidate_winner_counts.get(row.winner_profile, 0) + 1
                )
            candidate_breakdown[candidate] = {
                "rows": len(candidate_rows),
                "winner_counts": candidate_winner_counts,
                "avg_baseline_score": round(
                    sum(row.baseline_score for row in candidate_rows) / max(1, len(candidate_rows)),
                    2,
                ),
                "avg_candidate_score": round(
                    sum(row.candidate_score for row in candidate_rows)
                    / max(1, len(candidate_rows)),
                    2,
                ),
            }
        summary_rows.append(
            {
                "model": metadata.model,
                "model_slug": _model_slug(metadata.model),
                "provider": metadata.provider,
                "base_url": metadata.base_url,
                "rows": len(rows),
                "companies_evaluated": sorted({row.company for row in rows}),
                "candidate_profiles_evaluated": sorted({row.candidate_profile for row in rows}),
                "winner_profile": winner,
                "row_winner_counts": row_winner_counts,
                "winner_consensus_rate": round(
                    row_winner_counts.get(winner, 0) / max(1, len(rows)),
                    4,
                ),
                "avg_baseline_score": avg_baseline,
                "avg_candidate_score": avg_candidate,
                "avg_score_gap": round(avg_baseline - avg_candidate, 2),
                "avg_baseline_aspects": avg_baseline_aspects,
                "avg_candidate_aspects": avg_candidate_aspects,
                "avg_aspect_gap": avg_aspect_gap,
                "candidate_profile_breakdown": candidate_breakdown,
                "total_cost_usd": round(total_cost, 4),
            }
        )

    majority_winner = _winner_majority_label(winner_counts) if winner_counts else "unknown"
    summary_rows.sort(
        key=lambda row: (
            row["winner_profile"] != majority_winner,
            -row["winner_consensus_rate"],
            -row["avg_score_gap"],
            -row["avg_baseline_score"],
            row["model"],
        )
    )
    recommended_models = [row["model"] for row in summary_rows[:3]]

    payload = {
        "eval_id": eval_id,
        "baseline_profile": baseline_profile,
        "candidate_profiles": candidate_profiles,
        "models_evaluated": len(results),
        "winner_counts": winner_counts,
        "majority_winner_profile": majority_winner,
        "ranking_method": (
            "majority winner alignment, then winner_consensus_rate desc, "
            "then avg_score_gap desc, then avg_baseline_score desc"
        ),
        "recommended_models": recommended_models,
        "results": summary_rows,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_local_judge_sweep_markdown(
    path: Path,
    *,
    eval_id: str,
    baseline_profile: str,
    candidate_profiles: list[str],
    results: list[tuple[LLMJudgeMetadata, list[LLMJudgeRow], float]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ranked: list[tuple[LLMJudgeMetadata, list[LLMJudgeRow], float, str, float, float, float]] = []
    winner_counts: dict[str, int] = {}
    for metadata, rows, total_cost in results:
        row_winner_counts: dict[str, int] = {}
        for row in rows:
            row_winner_counts[row.winner_profile] = row_winner_counts.get(row.winner_profile, 0) + 1
        winner = _winner_majority_label(row_winner_counts) if row_winner_counts else "unknown"
        avg_baseline = (
            round(sum(row.baseline_score for row in rows) / max(1, len(rows)), 2) if rows else 0.0
        )
        avg_candidate = (
            round(sum(row.candidate_score for row in rows) / max(1, len(rows)), 2) if rows else 0.0
        )
        consensus_rate = round(row_winner_counts.get(winner, 0) / max(1, len(rows)), 4)
        ranked.append(
            (metadata, rows, total_cost, winner, avg_baseline, avg_candidate, consensus_rate)
        )
        winner_counts[winner] = winner_counts.get(winner, 0) + 1
    majority_winner = _winner_majority_label(winner_counts) if winner_counts else "unknown"
    ranked.sort(
        key=lambda item: (
            item[3] != majority_winner,
            -item[6],
            -(item[4] - item[5]),
            -item[4],
            item[0].model,
        )
    )

    lines = [
        f"# Local Judge Sweep: {eval_id}",
        "",
        f"- Baseline profile: `{baseline_profile}`",
        f"- Candidate profiles: `{', '.join(candidate_profiles) if candidate_profiles else 'none'}`",
        f"- Models evaluated: `{len(results)}`",
        f"- Majority winner: `{majority_winner}`",
        "",
        "## Ranking",
        "",
        "| Rank | Model | Winner | Consensus | Avg Baseline | Avg Candidate | Gap | Rows | Cost |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for index, (
        metadata,
        rows,
        total_cost,
        winner,
        avg_baseline,
        avg_candidate,
        consensus_rate,
    ) in enumerate(ranked, start=1):
        lines.append(
            f"| {index} | {metadata.model} | {winner} | {consensus_rate:.0%} | {avg_baseline:.2f} | {avg_candidate:.2f} | {avg_baseline - avg_candidate:.2f} | {len(rows)} | {total_cost:.4f} |"
        )
        if rows:
            avg_gap_by_aspect = {
                name: round(
                    sum(
                        row.baseline_aspects.get(name, 0.0) - row.candidate_aspects.get(name, 0.0)
                        for row in rows
                    )
                    / max(1, len(rows)),
                    2,
                )
                for name in rows[0].baseline_aspects
            }
            top_gaps = sorted(
                avg_gap_by_aspect.items(), key=lambda item: abs(item[1]), reverse=True
            )[:3]
            if top_gaps:
                lines.append(
                    f"Top aspect gaps: {', '.join(f'{name}={gap:+.2f}' for name, gap in top_gaps)}"
                )
            candidate_profiles_seen = sorted({row.candidate_profile for row in rows})
            lines.append(f"Candidate profiles covered: {', '.join(candidate_profiles_seen)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_llm_judge_report(
    path: Path,
    rows: list[LLMJudgeRow],
    total_cost: float,
    metadata: LLMJudgeMetadata | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "total_cost_usd": total_cost,
        "rows": [
            {
                "company": row.company,
                "baseline_profile": row.baseline_profile,
                "candidate_profile": row.candidate_profile,
                "winner_profile": row.winner_profile,
                "baseline_score": row.baseline_score,
                "candidate_score": row.candidate_score,
                "baseline_aspects": row.baseline_aspects,
                "candidate_aspects": row.candidate_aspects,
                "passes": row.passes,
                "rationale": row.rationale,
                "cost_usd": row.cost_usd,
            }
            for row in rows
        ],
    }
    if metadata is not None:
        payload["metadata"] = {
            "provider": metadata.provider,
            "model": metadata.model,
            "base_url": metadata.base_url,
            "api_key_env": metadata.api_key_env,
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
        rules.append(
            "Increase citation density by grounding major claims with external or primary-source citations."
        )
    if avg_confidence < 24:
        rules.append(
            "Improve uncertainty calibration by labeling non-obvious claims with confidence tags."
        )
    if avg_words < 7200:
        rules.append(
            "Increase analytical depth: include more concrete evidence, tradeoffs, and decision implications per section."
        )
    if fast_summary.avg_decision_utility < 90:
        rules.append(
            "Strengthen decision utility: prioritize recommendations, risks, constraints, and next-step diagnostics."
        )
    if fast_summary.avg_trust < 92:
        rules.append(
            "Tighten trust discipline: avoid precise estimates unless directly sourced; otherwise state assumptions explicitly."
        )

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
                judge_insights.append(
                    f"Raise `{aspect}` quality (current LLM judge score: {score:.1f})."
                )
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
