"""Offline calibration runner: audit label evidence on shipped reports.

The runner turns the label-calibration harness (``qa.label_calibration``)
into a one-command audit over reports already on disk. No research run is
required. Per report it samples labeled claims (free, deterministic),
fetches cited sources, and judges support plus optional evidence dimensions,
persisting the result as a ``<report>.calibration.json`` sidecar that the
model_eval scorecard reads.

Cost profile: claim extraction is free; the paid part is bounded source-review
calls (``max_per_label`` x 2 labels x ``max_sources_per_claim``), usually a
small fraction of a dollar per report on the fast tier. ``dry_run=True`` stops
after extraction and reports exactly how many judge calls a live pass would
make.

All effects (fetching, judging, sidecar writes) are injectable or
switchable so tests stay offline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from primr.qa.label_calibration import EvidenceReview

from primr.qa.artifact_fingerprints import artifact_fingerprint
from primr.qa.calibration_selection import CalibrationPackSelection
from primr.qa.label_calibration import (
    DEFAULT_MAX_PER_LABEL,
    TRACEABLE_LABELS,
    build_judge_prompt,
    calibrate_claims,
    extract_labeled_claims,
    parse_judge_answer,
)
from primr.utils.logging_config import get_logger

logger = get_logger("qa.calibration_runner")

# Sidecar filename suffix appended to the full report filename, so the
# pairing survives reports that share a stem across extensions.
SIDECAR_SUFFIX = ".calibration.json"

# Default per-judge-call cost assumption for the dry-run preview (fast-tier,
# one-word answer, ~1.2k tokens in). Deliberately conservative.
_EST_COST_PER_JUDGE_CALL_USD = 0.0005
_MAX_SOURCES_PER_CLAIM = 2


@dataclass(frozen=True)
class ReportCalibrationOutcome:
    """Result of calibrating (or dry-running) one report."""

    report_path: Path
    claims_sampled: int
    judgeable_claims: int
    estimated_judge_calls: int
    sidecar_path: Path | None = None
    per_label: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def sidecar_path_for(report_path: Path) -> Path:
    """The calibration sidecar path for a report file."""
    return report_path.with_name(report_path.name + SIDECAR_SUFFIX)


@dataclass
class JudgeSelection:
    """Which judge a calibration run uses, with provenance for the sidecar.

    A calibration number is meaningless without knowing what judged it, so
    the selection travels into every sidecar as ``judge: {kind, model}``.
    ``cloud_fallbacks`` counts local-judge calls that had to fall back to
    the cloud judge mid-run (flaky local server) - non-zero means the
    sidecar's verdicts are mixed-provenance.
    """

    kind: str  # "cloud" | "local"
    model: str  # model identity (or "fast-tier" for the cloud default)
    judge_fn: Callable[[str, str], bool] | None = None  # None = harness default
    cloud_fallbacks: int = 0

    def to_metadata(self) -> dict[str, Any]:
        meta: dict[str, Any] = {"kind": self.kind, "model": self.model}
        if self.cloud_fallbacks:
            meta["cloud_fallbacks"] = self.cloud_fallbacks
        return meta


def make_local_judge(
    model: str,
    *,
    base_url: str | None = None,
    complete_fn: Callable[..., Any] | None = None,
    on_fallback: Callable[[str, str], bool] | None = None,
    fallback_counter: list[int] | None = None,
) -> Callable[[str, str], bool]:
    """A traceability judge backed by a local OpenAI-compatible model.

    Uses the exact same prompt as the cloud judge so verdicts never depend
    on the backend. On a local-call failure each judgment raises unless the
    caller explicitly provides ``on_fallback``. A flaky local server must not
    silently spend through the cloud judge or masquerade as untraceable claims.
    """

    def _judge(claim_sentence: str, source_text: str) -> bool:
        from primr.ai.openai_compatible_client import chat_completion

        complete = complete_fn or chat_completion
        try:
            result = complete(
                build_judge_prompt(claim_sentence, source_text),
                model=model,
                base_url=base_url,
                temperature=0.0,
                # Room for reasoning-family think blocks before the verdict.
                max_tokens=512,
                retries=1,
            )
            return parse_judge_answer(result.text)
        except Exception as e:
            if on_fallback is not None:
                logger.warning(
                    "Local judge call failed (%s); using configured fallback: %s", model, e
                )
                if fallback_counter is not None:
                    fallback_counter[0] += 1
                return on_fallback(claim_sentence, source_text)
            logger.warning("Local judge call failed (%s); cloud fallback is disabled: %s", model, e)
            raise RuntimeError(
                f"Local judge call failed for model {model!r}; cloud fallback is disabled"
            ) from e

    return _judge


def resolve_judge(
    mode: str = "cloud",
    *,
    model: str | None = None,
    base_url: str | None = None,
    list_models_fn: Callable[..., list[str]] | None = None,
    make_local_judge_fn: Callable[..., Callable[[str, str], bool]] | None = None,
) -> JudgeSelection:
    """Resolve the judge for a calibration run.

    - ``cloud``: the harness default (fast-tier LLM). Always works.
    - ``local``: an explicit opt-in - raises with a clear message when no
      local server or usable model is found, and local call failures stay
      local instead of spending through cloud fallback.
    - ``auto``: prefer local when a server with a usable model is
      reachable, otherwise cloud. Never errors.

    ``model`` pins a specific local model (any OpenAI-compatible name),
    bypassing the family-preference pick.
    """
    if mode not in ("cloud", "local", "auto"):
        raise ValueError(f"Unknown judge mode: {mode!r} (expected cloud, local, or auto)")
    if mode == "cloud":
        return JudgeSelection(kind="cloud", model="fast-tier")

    from primr.ai.local_inference import list_local_models, pick_local_judge_model

    list_models = list_models_fn or list_local_models
    installed = list_models(base_url)
    picked = model if model else pick_local_judge_model(installed)
    if model and installed and model not in installed:
        logger.warning(
            "Pinned judge model %r is not in the local server's model list; trying anyway", model
        )

    if not picked or (not installed and not model):
        if mode == "local":
            raise RuntimeError(
                "No local inference server with a usable model was found "
                "(checked the OpenAI-compatible /models endpoint at the "
                "configured base URL - set LOCAL_LLM_BASE_URL or "
                "OLLAMA_BASE_URL if your server is not on localhost:11434). "
                "Use --judge auto to fall back to the cloud judge instead."
            )
        return JudgeSelection(kind="cloud", model="fast-tier")

    selection = JudgeSelection(kind="local", model=picked)
    fallback_counter = [0]
    build = make_local_judge_fn or make_local_judge
    judge_fn = build(picked, base_url=base_url, fallback_counter=fallback_counter)

    def _counting_judge(claim_sentence: str, source_text: str) -> bool:
        verdict = judge_fn(claim_sentence, source_text)
        selection.cloud_fallbacks = fallback_counter[0]
        return verdict

    selection.judge_fn = _counting_judge
    return selection


def resolve_reports(
    target: str | None,
    *,
    recent: int | None = None,
    output_dir: Path | None = None,
) -> list[Path]:
    """Resolve the report files a calibration run covers.

    ``target`` may be an explicit file path or a company name (resolved to
    the company's most recent markdown Strategic Overview). ``recent``
    selects the N most recent Strategic Overview reports instead, one per
    company (latest wins). Markdown is preferred over txt because the
    harness parses markdown structure.
    """
    out_dir = output_dir if output_dir is not None else Path("output")

    if target:
        candidate = Path(target)
        if candidate.is_file():
            return [candidate]
        if any(sep in target for sep in ("/", "\\")) or candidate.suffix:
            raise FileNotFoundError(f"Report file not found: {target}")
        matches = [
            p
            for p in out_dir.glob(f"*{target}*Strategic_Overview*.md")
            if not p.name.endswith(SIDECAR_SUFFIX)
        ]
        if not matches:
            raise FileNotFoundError(
                f"No Strategic Overview markdown found for company '{target}' in {out_dir}"
            )
        return [max(matches, key=lambda p: p.stat().st_mtime)]

    count = recent if recent is not None else 1
    candidates = sorted(
        (p for p in out_dir.glob("*Strategic_Overview*.md") if not p.name.endswith(SIDECAR_SUFFIX)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    latest_per_company: dict[str, Path] = {}
    for path in candidates:
        company = path.name.split("_Strategic_Overview")[0]
        if company not in latest_per_company:
            latest_per_company[company] = path
        if len(latest_per_company) >= count:
            break
    if not latest_per_company:
        raise FileNotFoundError(f"No Strategic Overview markdown reports found in {out_dir}")
    return list(latest_per_company.values())


def _estimate_judge_calls(claims: list[Any]) -> int:
    return sum(
        min(_MAX_SOURCES_PER_CLAIM, len(c.source_urls))
        for c in claims
        if c.label in TRACEABLE_LABELS and c.source_urls
    )


def estimate_cost_usd(judge_calls: int) -> float:
    """Conservative dry-run cost preview for a number of judge calls."""
    return round(judge_calls * _EST_COST_PER_JUDGE_CALL_USD, 4)


def run_calibration(
    report_paths: list[Path],
    *,
    max_per_label: int = DEFAULT_MAX_PER_LABEL,
    dry_run: bool = False,
    write_sidecar: bool = True,
    fetch_fn: Callable[[str], str] | None = None,
    judge_fn: Callable[[str, str], bool] | None = None,
    review_fn: Callable[[str, str], EvidenceReview] | None = None,
    judge_selection: JudgeSelection | None = None,
) -> list[ReportCalibrationOutcome]:
    """Calibrate each report, persisting a sidecar JSON per report.

    With ``dry_run`` the run stops after the free extraction step and the
    outcomes carry the claim counts and the judge-call estimate only. A
    report that cannot be read or parsed records an ``error`` outcome
    instead of failing the batch.

    ``judge_selection`` (from :func:`resolve_judge`) supplies the judge and
    stamps its provenance into each sidecar; an explicit ``judge_fn`` wins
    over it (test seam).
    """
    selection = judge_selection or JudgeSelection(kind="cloud", model="fast-tier")
    effective_judge = judge_fn if judge_fn is not None else selection.judge_fn

    outcomes: list[ReportCalibrationOutcome] = []
    for path in report_paths:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            outcomes.append(
                ReportCalibrationOutcome(
                    report_path=path,
                    claims_sampled=0,
                    judgeable_claims=0,
                    estimated_judge_calls=0,
                    error=f"unreadable: {e}",
                )
            )
            continue

        claims = extract_labeled_claims(content, max_per_label=max_per_label)
        judgeable = [c for c in claims if c.label in TRACEABLE_LABELS and c.source_urls]
        judge_calls = _estimate_judge_calls(claims)

        if dry_run:
            outcomes.append(
                ReportCalibrationOutcome(
                    report_path=path,
                    claims_sampled=len(claims),
                    judgeable_claims=len(judgeable),
                    estimated_judge_calls=judge_calls,
                )
            )
            continue

        try:
            report = calibrate_claims(
                claims, fetch_fn=fetch_fn, judge_fn=effective_judge, review_fn=review_fn
            )
        except Exception as e:
            outcomes.append(
                ReportCalibrationOutcome(
                    report_path=path,
                    claims_sampled=len(claims),
                    judgeable_claims=len(judgeable),
                    estimated_judge_calls=judge_calls,
                    error=f"calibration_failed: {e}",
                )
            )
            continue
        payload = report.to_dict()
        payload["report_file"] = path.name
        payload["max_per_label"] = max_per_label
        payload["judge"] = selection.to_metadata()

        sidecar: Path | None = None
        if write_sidecar:
            sidecar = sidecar_path_for(path)
            sidecar.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("Calibration sidecar written: %s", sidecar)

        outcomes.append(
            ReportCalibrationOutcome(
                report_path=path,
                claims_sampled=len(claims),
                judgeable_claims=len(judgeable),
                estimated_judge_calls=judge_calls,
                sidecar_path=sidecar,
                per_label=payload["per_label"],
            )
        )
    return outcomes


@dataclass(frozen=True)
class JudgeAgreement:
    """Cloud-vs-local judge agreement over the same decidable claims.

    The cheap way to decide whether a *particular* local setup can be
    trusted with calibration: judge the same claims with both backends
    once, and let the agreement rate speak. Only claims both judges could
    decide (traceable/untraceable) are compared.
    """

    compared: int
    agreed: int
    local_model: str

    @property
    def agreement(self) -> float | None:
        if not self.compared:
            return None
        return self.agreed / self.compared


_DECIDED = ("traceable", "untraceable")


def compare_judges(
    report_paths: list[Path],
    *,
    local_selection: JudgeSelection,
    max_per_label: int = DEFAULT_MAX_PER_LABEL,
    fetch_fn: Callable[[str], str] | None = None,
    cloud_judge_fn: Callable[[str, str], bool] | None = None,
) -> tuple[list[ReportCalibrationOutcome], JudgeAgreement]:
    """Run cloud-judged calibration (the record), plus local on the same claims.

    The cloud pass writes the sidecars - it is the result of record. The
    local pass reuses the same fetched sources (one fetch per URL across
    both passes) and is compared verdict-by-verdict. Returns the cloud
    outcomes and the agreement summary.
    """
    # Shared fetch cache so sources are fetched once across both passes,
    # and a memoized cloud judge so each (claim, source) pair is billed
    # exactly once even though the sidecar pass and the comparison pass
    # both consult it.
    fetch_cache: dict[str, str] = {}
    base_fetch = fetch_fn
    if base_fetch is None:
        from primr.qa.label_calibration import _default_fetch

        base_fetch = _default_fetch

    def cached_fetch(url: str) -> str:
        if url not in fetch_cache:
            fetch_cache[url] = base_fetch(url)
        return fetch_cache[url]

    base_cloud_judge = cloud_judge_fn
    if base_cloud_judge is None:
        from primr.qa.label_calibration import _default_judge

        base_cloud_judge = _default_judge
    judge_cache: dict[tuple[str, str], bool] = {}

    def cached_cloud_judge(claim_sentence: str, source_text: str) -> bool:
        key = (claim_sentence, source_text)
        if key not in judge_cache:
            judge_cache[key] = base_cloud_judge(claim_sentence, source_text)
        return judge_cache[key]

    cloud_outcomes = run_calibration(
        report_paths,
        max_per_label=max_per_label,
        fetch_fn=cached_fetch,
        judge_fn=cached_cloud_judge,
        judge_selection=JudgeSelection(kind="cloud", model="fast-tier"),
    )

    compared = 0
    agreed = 0
    per_report: dict[Path, JudgeAgreement] = {}
    for path in report_paths:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        claims = extract_labeled_claims(content, max_per_label=max_per_label)
        cloud_report = calibrate_claims(claims, fetch_fn=cached_fetch, judge_fn=cached_cloud_judge)
        local_report = calibrate_claims(
            claims, fetch_fn=cached_fetch, judge_fn=local_selection.judge_fn
        )
        report_compared = 0
        report_agreed = 0
        for cloud_result, local_result in zip(
            cloud_report.results, local_report.results, strict=True
        ):
            if cloud_result.verdict in _DECIDED and local_result.verdict in _DECIDED:
                compared += 1
                report_compared += 1
                if cloud_result.verdict == local_result.verdict:
                    agreed += 1
                    report_agreed += 1
        per_report[path] = JudgeAgreement(
            compared=report_compared,
            agreed=report_agreed,
            local_model=local_selection.model,
        )

    agreement = JudgeAgreement(compared=compared, agreed=agreed, local_model=local_selection.model)
    _stamp_judge_agreement(cloud_outcomes, per_report)
    return cloud_outcomes, agreement


def _stamp_judge_agreement(
    outcomes: list[ReportCalibrationOutcome],
    per_report: dict[Path, JudgeAgreement],
) -> None:
    """Persist per-report cloud-vs-local agreement beside calibration verdicts."""
    for outcome in outcomes:
        if outcome.sidecar_path is None:
            continue
        agreement = per_report.get(outcome.report_path)
        if agreement is None:
            continue
        try:
            payload = json.loads(outcome.sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not stamp judge agreement into %s", outcome.sidecar_path)
            continue
        if not isinstance(payload, dict):
            continue
        payload["judge_agreement"] = {
            "scope": "report",
            "local_model": agreement.local_model,
            "compared": agreement.compared,
            "agreed": agreement.agreed,
            "agreement": agreement.agreement,
        }
        outcome.sidecar_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _read_sidecar_payload(report_path: Path) -> dict[str, Any] | None:
    sidecar = sidecar_path_for(report_path)
    if not sidecar.exists():
        return None
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_calibration_pack_manifest(
    manifest_path: Path,
    report_paths: list[Path],
    outcomes: list[ReportCalibrationOutcome],
    *,
    max_per_label: int,
    judge_selection: JudgeSelection | None = None,
    judge_agreement: JudgeAgreement | None = None,
    judge_metadata: dict[str, Any] | None = None,
    selection: CalibrationPackSelection | None = None,
) -> dict[str, Any]:
    """Write a manifest freezing the selected calibration pack."""
    by_report = {outcome.report_path: outcome for outcome in outcomes}
    total_calls = sum(outcome.estimated_judge_calls for outcome in outcomes)
    sidecar_per_label = _aggregate_existing_sidecar_per_label(report_paths)
    if judge_metadata is not None:
        judge_meta = judge_metadata
    elif judge_selection is not None:
        judge_meta = judge_selection.to_metadata()
    else:
        judge_meta = None
    payload: dict[str, Any] = {
        "manifest_format": "primr.calibration_pack.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "max_per_label": max_per_label,
        "judge": judge_meta,
        "totals": {
            "reports": len(report_paths),
            "claims_sampled": sum(outcome.claims_sampled for outcome in outcomes),
            "judgeable_claims": sum(outcome.judgeable_claims for outcome in outcomes),
            "estimated_judge_calls": total_calls,
            "estimated_cloud_cost_usd": estimate_cost_usd(total_calls),
            "failures": sum(1 for outcome in outcomes if outcome.error),
            "sidecars_present": sum(1 for path in report_paths if sidecar_path_for(path).exists()),
        },
        "per_label": aggregate_per_label(outcomes),
        "existing_sidecar_per_label": sidecar_per_label,
        "judge_agreement": (
            {
                "local_model": judge_agreement.local_model,
                "compared": judge_agreement.compared,
                "agreed": judge_agreement.agreed,
                "agreement": judge_agreement.agreement,
            }
            if judge_agreement is not None
            else None
        ),
        "representation": (
            selection.to_manifest_representation()
            if selection is not None
            else {
                "selection_format": None,
                "selection_path": None,
                "required_tags": [],
                "present_tags": [],
                "missing_tags": [],
            }
        ),
        "reports": [],
    }

    for report_path in report_paths:
        outcome = by_report.get(report_path)
        sidecar = sidecar_path_for(report_path)
        sidecar_payload = _read_sidecar_payload(report_path)
        report_fingerprint = artifact_fingerprint(report_path)
        sidecar_fingerprint = artifact_fingerprint(sidecar)
        entry: dict[str, Any] = {
            "report_path": report_path.as_posix(),
            "report_file": report_path.name,
            "report_size_bytes": report_fingerprint["size_bytes"],
            "report_content_hash": report_fingerprint["content_hash"],
            "sidecar_path": sidecar.as_posix(),
            "sidecar_exists": sidecar.exists(),
            "sidecar_size_bytes": sidecar_fingerprint["size_bytes"],
            "sidecar_content_hash": sidecar_fingerprint["content_hash"],
            "claims_sampled": outcome.claims_sampled if outcome else 0,
            "judgeable_claims": outcome.judgeable_claims if outcome else 0,
            "estimated_judge_calls": outcome.estimated_judge_calls if outcome else 0,
            "error": outcome.error if outcome else None,
            "coverage_tags": list(selection.tags_for(report_path)) if selection else [],
        }
        if sidecar_payload is not None:
            entry["sidecar"] = {
                "judge": sidecar_payload.get("judge"),
                "judge_agreement": sidecar_payload.get("judge_agreement"),
                "per_label": sidecar_payload.get("per_label", {}),
                "validation_rubric": sidecar_payload.get("validation_rubric", {}),
            }
        payload["reports"].append(entry)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def _aggregate_existing_sidecar_per_label(report_paths: list[Path]) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = {}
    keys = (
        "sampled",
        "traceable",
        "untraceable",
        "no_source",
        "unfetchable",
        "exempt",
        "source_copied",
    )
    for report_path in report_paths:
        payload = _read_sidecar_payload(report_path)
        per_label = payload.get("per_label", {}) if payload else {}
        if not isinstance(per_label, dict):
            continue
        for label, stats in per_label.items():
            if not isinstance(stats, dict):
                continue
            bucket = totals.setdefault(label, dict.fromkeys(keys, 0))
            for key in keys:
                bucket[key] += int(stats.get(key, 0) or 0)
    return totals


def aggregate_per_label(outcomes: list[ReportCalibrationOutcome]) -> dict[str, dict[str, int]]:
    """Sum per-label verdict counts across calibrated outcomes."""
    totals: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        for label, stats in outcome.per_label.items():
            bucket = totals.setdefault(
                label,
                {
                    "sampled": 0,
                    "traceable": 0,
                    "untraceable": 0,
                    "no_source": 0,
                    "unfetchable": 0,
                    "exempt": 0,
                    "source_copied": 0,
                },
            )
            for key in bucket:
                bucket[key] += int(stats.get(key, 0))
    return totals


def aggregate_precision(totals: dict[str, dict[str, int]], label: str) -> float | None:
    """Pooled traceability precision for a label across reports."""
    stats = totals.get(label)
    if not stats:
        return None
    decidable = stats["traceable"] + stats["untraceable"] + stats["no_source"]
    if not decidable:
        return None
    return stats["traceable"] / decidable
