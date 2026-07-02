"""Unit tests for primr.core.strategy_prompt_parts.

Pins the roadmap #8 invariant for the strategy stage: the cached prefix is
byte-identical across strategy calls of one run, per-call material stays in
the volatile suffix, and prefix + suffix reproduces the legacy combined
prompt shape exactly.
"""

from __future__ import annotations

from unittest.mock import patch

from primr.core.strategy_prompt_parts import (
    AI_STRATEGY_ARTIFACTS,
    YAML_STRATEGY_ARTIFACTS,
    build_strategy_context_prefix,
    build_strategy_prompt_parts,
    read_artifact_blocks,
)

HEADER = "Use the following context documents to inform your analysis:\n\n"


def _legacy_combined_prompt(report, artifact_blocks, vendor_blocks, strategy_prompt):
    """The exact assembly the strategy loops used before the parts split."""
    context_parts = [f"--- Company Report ---\n{report[:50_000]}"]
    context_parts.extend(artifact_blocks)
    context_parts.extend(vendor_blocks)
    return HEADER + "\n\n".join(context_parts) + "\n\n---\n\n" + strategy_prompt


class TestReadArtifactBlocks:
    def test_reads_existing_artifacts_in_spec_order(self, tmp_path):
        (tmp_path / "insights.txt").write_text("insight body", encoding="utf-8")
        (tmp_path / "analysis_workbook.md").write_text("workbook body", encoding="utf-8")
        blocks = read_artifact_blocks(str(tmp_path), AI_STRATEGY_ARTIFACTS)
        assert blocks == [
            "--- insights.txt ---\ninsight body",
            "--- analysis_workbook.md ---\nworkbook body",
        ]

    def test_missing_files_skipped(self, tmp_path):
        assert read_artifact_blocks(str(tmp_path), AI_STRATEGY_ARTIFACTS) == []

    def test_blank_content_skipped(self, tmp_path):
        (tmp_path / "insights.txt").write_text("   \n\t ", encoding="utf-8")
        assert read_artifact_blocks(str(tmp_path), AI_STRATEGY_ARTIFACTS) == []

    def test_content_truncated_to_limit(self, tmp_path):
        (tmp_path / "gap_analysis.md").write_text("x" * 20_000, encoding="utf-8")
        blocks = read_artifact_blocks(str(tmp_path), AI_STRATEGY_ARTIFACTS)
        assert blocks == ["--- gap_analysis.md ---\n" + "x" * 15_000]

    def test_read_failure_logged_and_skipped(self, tmp_path):
        (tmp_path / "insights.txt").write_text("readable", encoding="utf-8")
        with patch("builtins.open", side_effect=PermissionError("locked")):
            blocks = read_artifact_blocks(str(tmp_path), AI_STRATEGY_ARTIFACTS)
        assert blocks == []

    def test_nested_artifact_path_resolves(self, tmp_path):
        hiring = tmp_path / "_hiring"
        hiring.mkdir()
        (hiring / "hiring_signals.md").write_text("signals", encoding="utf-8")
        blocks = read_artifact_blocks(str(tmp_path), YAML_STRATEGY_ARTIFACTS)
        assert blocks == ["--- _hiring/hiring_signals.md ---\nsignals"]


class TestBuildStrategyContextPrefix:
    def test_report_truncated_to_50k(self):
        prefix = build_strategy_context_prefix("r" * 60_000, [])
        assert prefix == HEADER + "--- Company Report ---\n" + "r" * 50_000

    def test_shared_blocks_appended_in_order(self):
        prefix = build_strategy_context_prefix("report", ["--- a ---\n1", "--- b ---\n2"])
        assert prefix == HEADER + "--- Company Report ---\nreport\n\n--- a ---\n1\n\n--- b ---\n2"


class TestBuildStrategyPromptParts:
    def test_prefix_identical_across_strategy_prompts(self):
        prefix = build_strategy_context_prefix("report", ["--- a ---\n1"])
        p1, _ = build_strategy_prompt_parts(prefix, "azure strategy")
        p2, _ = build_strategy_prompt_parts(prefix, "aws strategy", ["--- vendor.md ---\ndoc"])
        assert p1 == p2 == prefix

    def test_volatile_material_never_in_prefix(self):
        prefix = build_strategy_context_prefix("report", [])
        cached, suffix = build_strategy_prompt_parts(
            prefix, "strategy prompt", ["--- vendor.md ---\nvendor-only detail"]
        )
        assert "vendor-only detail" not in cached
        assert "strategy prompt" not in cached
        assert "vendor-only detail" in suffix
        assert suffix.endswith("strategy prompt")

    def test_concatenation_matches_legacy_with_vendor_blocks(self):
        artifact_blocks = ["--- insights.txt ---\nideas"]
        vendor_blocks = ["--- azure_doc.md ---\nvendor content"]
        prefix = build_strategy_context_prefix("report body", artifact_blocks)
        cached, suffix = build_strategy_prompt_parts(prefix, "the strategy prompt", vendor_blocks)
        assert cached + suffix == _legacy_combined_prompt(
            "report body", artifact_blocks, vendor_blocks, "the strategy prompt"
        )

    def test_concatenation_matches_legacy_without_vendor_blocks(self):
        prefix = build_strategy_context_prefix("report body", [])
        cached, suffix = build_strategy_prompt_parts(prefix, "yaml strategy prompt")
        assert cached + suffix == _legacy_combined_prompt(
            "report body", [], [], "yaml strategy prompt"
        )
