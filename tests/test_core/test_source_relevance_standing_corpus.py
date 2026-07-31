"""Standing source-relevance corpus: integrity, body-free scorecards, CLI path."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from primr.core import source_relevance_eval
from primr.core.cli_local_stage_eval import handle_source_relevance_fixture_eval
from primr.core.source_relevance_eval import (
    STANDING_CORPUS_ID,
    STANDING_CORPUS_REQUIRED_BACKENDS,
    build_source_relevance_eval_rows,
    inspect_standing_source_relevance_corpus,
    load_standing_source_relevance_corpus,
    standing_source_relevance_corpus_path,
)


class _Console:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.steps: list[str] = []

    def blank(self) -> None:
        return None

    def step(self, message: str) -> None:
        self.steps.append(message)

    def info(self, message: str) -> None:
        self.infos.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


def test_packaged_standing_corpus_path_exists() -> None:
    path = standing_source_relevance_corpus_path()
    assert path.is_file()
    assert path.name == "source_relevance_standing_v1.json"


def test_standing_corpus_inspection_is_scorecard_ready() -> None:
    inspection = inspect_standing_source_relevance_corpus()
    assert inspection["corpus_id"] == STANDING_CORPUS_ID
    assert inspection["status"] == "ready_for_scorecard"
    assert inspection["promotion_status"] == "not_promoted"
    assert inspection["decision_policy"] == "scorecard_input_only"
    assert inspection["blockers"] == []
    assert inspection["case_count"] >= 5
    assert not inspection["missing_representative_tags"]
    assert STANDING_CORPUS_REQUIRED_BACKENDS.issubset(set(inspection["backends_present"]))
    fingerprint = inspection["corpus_fingerprint"]
    assert fingerprint["size_bytes"] > 0
    assert len(fingerprint["sha256"]) == 64
    raw = standing_source_relevance_corpus_path().read_bytes()
    assert fingerprint["sha256"] == __import__("hashlib").sha256(raw).hexdigest()
    assert fingerprint["size_bytes"] == len(raw)


def test_standing_corpus_loads_and_scores_without_bodies() -> None:
    cases = load_standing_source_relevance_corpus()
    rows = build_source_relevance_eval_rows(cases)
    assert len(cases) >= 5
    assert len(rows) == len(cases) * 2
    backends = {row.backend_id for row in rows}
    assert backends == STANDING_CORPUS_REQUIRED_BACKENDS
    # Synthetic labels are intentionally imperfect across some cases.
    assert any(row.exact_match for row in rows)
    assert any(not row.exact_match for row in rows)
    serialized = json.dumps([row.__dict__ for row in rows])
    assert "http://" not in serialized
    assert "https://" not in serialized


def test_standing_corpus_rejects_body_fields(tmp_path: Path) -> None:
    payload = json.loads(standing_source_relevance_corpus_path().read_text(encoding="utf-8"))
    payload["cases"][0]["source_url"] = "https://must-not-pass.example"
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    inspection = inspect_standing_source_relevance_corpus(path=path)
    assert inspection["status"] == "blocked"
    assert "case_contains_source_body_fields" in inspection["blockers"]
    with pytest.raises(ValueError, match="not scorecard-ready"):
        load_standing_source_relevance_corpus(path)


def test_standing_corpus_rejects_self_promotion(tmp_path: Path) -> None:
    payload = json.loads(standing_source_relevance_corpus_path().read_text(encoding="utf-8"))
    payload["promotion_status"] = "promoted"
    path = tmp_path / "promoted.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    inspection = inspect_standing_source_relevance_corpus(path=path)
    assert "promotion_status_not_report_only" in inspection["blockers"]


def test_handle_source_relevance_standing_corpus_cli(tmp_path: Path) -> None:
    console = _Console()
    config = SimpleNamespace(
        eval_id="eval-standing-001",
        eval_root=str(tmp_path),
        eval_source_relevance_fixture=None,
        eval_source_relevance_standing_corpus=True,
    )
    code, quality_path = handle_source_relevance_fixture_eval(config=config, console=console)
    assert code == 0
    assert quality_path is not None
    assert quality_path.is_file()
    payload = json.loads(quality_path.read_text(encoding="utf-8"))
    assert payload["stage_id"] == "fast.source_relevance"
    assert payload["decision_policy"] == "scorecard_input_only"
    assert "must-not" not in quality_path.read_text(encoding="utf-8")
    assert any("Standing corpus" in line for line in console.infos)
    stage_root = tmp_path / "eval-standing-001" / "source_relevance_stage"
    comparison = json.loads(
        (stage_root / "source_relevance_backend_comparison.json").read_text(encoding="utf-8")
    )
    integrity = json.loads(
        (stage_root / "standing_corpus_integrity.json").read_text(encoding="utf-8")
    )
    assert comparison["evidence_type"] == "source_relevance_backend_comparison"
    assert comparison["promotion_status"] == "not_promoted"
    assert comparison["comparable_cases"] == 6
    assert "avg_f1_delta" in comparison["aggregate"]
    assert integrity["status"] == "ready_for_scorecard"
    assert (stage_root / "source_relevance_backend_comparison.md").is_file()


def test_backend_comparison_is_body_free() -> None:
    cases = load_standing_source_relevance_corpus()
    rows = build_source_relevance_eval_rows(cases)
    comparison = source_relevance_eval.build_source_relevance_backend_comparison(rows)
    text = json.dumps(comparison)
    assert "http://" not in text
    assert "https://" not in text
    assert comparison["blockers"] == []
    assert comparison["comparable_cases"] >= 5


def test_inspect_standing_corpus_cli_writes_integrity_json(tmp_path: Path) -> None:
    console = _Console()
    config = SimpleNamespace(
        eval_id="eval-inspect-001",
        eval_root=str(tmp_path),
    )
    from primr.core.cli_local_stage_eval import handle_inspect_standing_source_relevance_corpus

    code, path = handle_inspect_standing_source_relevance_corpus(config=config, console=console)
    assert code == 0
    assert path is not None
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "ready_for_scorecard"
    assert payload["promotion_status"] == "not_promoted"


def test_handle_source_relevance_rejects_fixture_and_standing_together(tmp_path: Path) -> None:
    console = _Console()
    config = SimpleNamespace(
        eval_id="eval-standing-002",
        eval_root=str(tmp_path),
        eval_source_relevance_fixture=str(tmp_path / "other.json"),
        eval_source_relevance_standing_corpus=True,
    )
    code, quality_path = handle_source_relevance_fixture_eval(config=config, console=console)
    assert code == 1
    assert quality_path is None
    assert console.errors


def test_standing_corpus_id_constant_matches_package_file() -> None:
    payload = json.loads(standing_source_relevance_corpus_path().read_text(encoding="utf-8"))
    assert payload["corpus_id"] == source_relevance_eval.STANDING_CORPUS_ID


@given(
    body_key=st.sampled_from(
        ["source_url", "source_text", "url", "text", "body", "snippet"]
    ),
    body_value=st.sampled_from(
        ["https://must-not-leak.example", "raw body text", ["x"], {"k": "v"}]
    ),
)
@settings(max_examples=20, deadline=None)
def test_standing_inspection_blocks_any_body_field(
    body_key: str, body_value: object
) -> None:
    payload = json.loads(standing_source_relevance_corpus_path().read_text(encoding="utf-8"))
    payload["cases"][0][body_key] = body_value
    inspection = inspect_standing_source_relevance_corpus(payload=payload)
    assert inspection["status"] == "blocked"
    assert "case_contains_source_body_fields" in inspection["blockers"]
