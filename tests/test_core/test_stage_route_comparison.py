import json
from pathlib import Path

from primr.core.stage_route_comparison import (
    compare_stage_routes,
    find_run_state_files,
    load_stage_route_records,
    write_stage_route_comparison_json,
    write_stage_route_comparison_markdown,
)


def _write_run_state(path: Path, routes: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"report_body": "must not be copied", "stage_routes": routes}),
        encoding="utf-8",
    )


def test_stage_route_comparison_aggregates_body_free_metrics(tmp_path: Path) -> None:
    run_a = tmp_path / "Acme" / "run-a" / "_run_state.json"
    run_b = tmp_path / "Acme" / "run-b" / "_run_state.json"
    _write_run_state(
        run_a,
        [
            {
                "stage_id": "fast.scrape_summary",
                "backend_id": "gemini-flash",
                "backend_kind": "cloud_api",
                "billing_mode": "api_dollars",
                "inference_profile": "cloud",
                "outcome": "selected",
                "duration_seconds": 2.0,
                "actual_input_tokens": 100,
                "actual_output_tokens": 25,
                "actual_cached_input_tokens": 10,
                "actual_cost_usd": 0.001,
                "prompt": "must not be copied",
                "response": "must not be copied",
            },
            {
                "stage_id": "fast.scrape_summary",
                "backend_id": "gemini-flash",
                "backend_kind": "cloud_api",
                "billing_mode": "api_dollars",
                "inference_profile": "cloud",
                "outcome": "fallback",
                "duration_seconds": 4.0,
                "failure_class": "RuntimeError",
                "actual_input_tokens": 50,
                "actual_output_tokens": 0,
                "actual_cost_usd": 0.0005,
            },
        ],
    )
    _write_run_state(
        run_b,
        [
            {
                "stage_id": "fast.source_relevance",
                "backend_id": "local-qwen",
                "backend_kind": "local",
                "billing_mode": "local_runtime",
                "inference_profile": "hybrid",
                "outcome": "selected",
                "duration_seconds": 1.5,
                "actual_input_tokens": 80,
                "actual_output_tokens": 12,
            }
        ],
    )

    records = load_stage_route_records(find_run_state_files(tmp_path))
    rows = compare_stage_routes(records)

    assert [row.stage_id for row in rows] == ["fast.scrape_summary", "fast.source_relevance"]
    scrape = rows[0]
    assert scrape.attempts == 2
    assert scrape.selected_attempts == 1
    assert scrape.fallback_attempts == 1
    assert scrape.failed_attempts == 1
    assert scrape.actual_input_tokens == 150
    assert scrape.actual_output_tokens == 25
    assert scrape.actual_cached_input_tokens == 10
    assert scrape.actual_cost_usd == 0.0015
    assert scrape.avg_duration_seconds == 3.0
    assert scrape.failure_classes == {"RuntimeError": 1}


def test_stage_route_comparison_writes_stable_artifacts(tmp_path: Path) -> None:
    records = [
        {
            "stage_id": "fast.source_relevance",
            "backend_id": "gemini-flash",
            "backend_kind": "cloud_api",
            "billing_mode": "api_dollars",
            "inference_profile": "cloud",
            "outcome": "selected",
            "duration_seconds": 1.0,
            "actual_input_tokens": 10,
            "actual_output_tokens": 5,
            "actual_cost_usd": 0.0001,
            "prompt": "must not be copied",
        }
    ]
    rows = compare_stage_routes(records, stage_id="fast.source_relevance")
    json_path = tmp_path / "route-comparison.json"
    md_path = tmp_path / "route-comparison.md"

    write_stage_route_comparison_json(
        json_path,
        rows=rows,
        stage_id="fast.source_relevance",
    )
    write_stage_route_comparison_markdown(md_path, rows=rows)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["stage_id"] == "fast.source_relevance"
    assert payload["rows"][0]["backend_id"] == "gemini-flash"
    assert "prompt" not in json_path.read_text(encoding="utf-8")

    markdown = md_path.read_text(encoding="utf-8")
    assert "| fast.source_relevance | gemini-flash | cloud |" in markdown
    assert "must not be copied" not in markdown
