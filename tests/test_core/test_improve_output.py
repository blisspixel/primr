from pathlib import Path

from primr.core.research_agent import (
    _clean_strategy_output,
    _compute_strategy_qa_metrics,
    improve_output_file,
)


def test_compute_strategy_qa_metrics_flags_budget_inconsistency():
    content = (
        "# AI Strategy: Demo\n\n"
        "We recommend $5-8M Year 1 investment.\n\n"
        "## Investment Framework\n\n"
        "**Year 1**: Tech $1.5M, People $2M, Impl $1.5M. **Total $5M**.\n\n"
        "## BOARD SUMMARY\n\n"
        "Quick Wins: $1M\n"
        "Bigger Bets: $4M\n"
        "Org/People: $2.5M\n"
        "**Total: $7.5M**\n"
        "[Source: https://example.com/a]\n"
        "[Source: https://example.com/b]\n"
    )
    metrics = _compute_strategy_qa_metrics(content)
    assert metrics["budget_inconsistent"] is True
    assert metrics["source_urls"] >= 2


def test_clean_strategy_output_strips_internal_placeholders():
    content = "Claim [Reported: Analysis Context].\n\n[citation inventory: 1=example.com]\n"
    cleaned = _clean_strategy_output(content)
    assert "Analysis Context" not in cleaned
    assert "citation inventory" not in cleaned.lower()


def test_improve_output_file_writes_improved_report(tmp_path: Path):
    p = tmp_path / "demo.md"
    p.write_text(
        "## Executive Summary\n\n"
        "Claim [Source: https://example.com/a].\n\n"
        "[citation inventory: 1=example.com]\n",
        encoding="utf-8",
    )

    out = improve_output_file(str(p), in_place=False, use_agentic=False)
    assert out is not None
    out_path = Path(out)
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    assert "## Sources" in text
    assert "citation inventory" not in text.lower()
