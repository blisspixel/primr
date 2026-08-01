"""Tests for the extracted strategy-generation stage (roadmap #23, Batch C).

Pins the stage orchestration: budget checkpoint, per-vendor AI strategy
pipeline (single + parallel dispatch), YAML strategy loop, QA trust-stat
assembly, and failure isolation. LLM-backed helpers are patched at the
research_agent seam (they are lazy-imported there until their own
extraction); the YAML loop reads the real strategy YAML from the package.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.core.fast_run_strategy import StrategyPhaseResult, run_strategy_phase

CLEAN_QA = {
    "qa_gate_passed": True,
    "placeholder_refs": 0,
    "source_urls": 5,
    "citation_defs": 5,
    "missing_citations": 0,
    "invalid_source_urls": 0,
    "budget_inconsistent": False,
}


@pytest.fixture
def seams(monkeypatch, tmp_path):
    mocks = {
        "build_ai_prompt": MagicMock(return_value="ai strategy prompt"),
        "vendor_research": MagicMock(return_value=[]),
        "enrich": MagicMock(side_effect=lambda content, *a, **k: content),
        "prepare": MagicMock(side_effect=lambda content, *a, **k: (content, dict(CLEAN_QA), [])),
        "save": MagicMock(
            side_effect=lambda content, company, vendor, **k: str(tmp_path / f"{vendor}.docx")
        ),
        "build_yaml_prompt": MagicMock(return_value="yaml strategy prompt"),
        "session_cost": MagicMock(return_value=0.50),
        "failover": MagicMock(return_value="## Strategy\ncontent body"),
    }
    monkeypatch.setattr(
        "primr.core.research_agent._build_ai_strategy_prompt", mocks["build_ai_prompt"]
    )
    monkeypatch.setattr(
        "primr.core.fast_run_strategy.get_or_generate_vendor_research_sync",
        mocks["vendor_research"],
    )
    monkeypatch.setattr("primr.core.research_agent._enrich_strategy_content", mocks["enrich"])
    monkeypatch.setattr("primr.core.research_agent._prepare_strategy_for_output", mocks["prepare"])
    monkeypatch.setattr("primr.core.research_agent._save_strategy_output", mocks["save"])
    monkeypatch.setattr(
        "primr.core.research_agent._build_strategy_prompt_from_yaml", mocks["build_yaml_prompt"]
    )
    monkeypatch.setattr(
        "primr.core.research_agent._compute_session_llm_cost", mocks["session_cost"]
    )
    monkeypatch.setattr(
        "primr.pipeline.integration.strategy_with_recovery",
        lambda executor, fn, folder: SimpleNamespace(success=True, output=fn(), skip_reason=None),
    )
    monkeypatch.setattr("primr.core.fast_run_strategy.call_with_failover", mocks["failover"])
    agnostic_research_path = tmp_path / "vendor-research-agnostic.txt"
    monkeypatch.setattr(
        "primr.core.fast_run_strategy.get_vendor_research_path",
        lambda _vendor: agnostic_research_path,
    )
    monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: None)

    from primr.ai.capability_routing import InferenceProfile
    from primr.ai.stage_routing import StageModelRoute

    def fake_resolve(stage_id, legacy_model_type="writing", **kwargs):
        # Empty model_name keeps caller-supplied grok_writing/reasoning identity.
        return StageModelRoute(
            stage_id=stage_id,
            profile=InferenceProfile.CLOUD,
            model_name="",
            backend_id="cloud-backend",
            backend_kind="cloud",
            billing_mode="metered_api",
            estimated_cost_usd=None,
            expected_input_tokens=1,
            expected_output_tokens=1,
            routed=True,
            reasons=("test",),
            rejections=(),
            execution_mode="llm",
        )

    monkeypatch.setattr("primr.ai.stage_routing.resolve_stage_model", fake_resolve)
    monkeypatch.setattr("primr.ai.stage_routing.capture_stage_usage", dict)
    monkeypatch.setattr("primr.ai.stage_routing.stage_usage_delta", lambda before: None)
    monkeypatch.setattr("primr.ai.stage_routing.record_stage_route_usage", lambda *a, **k: None)

    mocks["agnostic_research_path"] = agnostic_research_path
    mocks["tmp"] = tmp_path
    return mocks


def _call(seams, **overrides) -> StrategyPhaseResult:
    defaults = {
        "has_strategies": True,
        "ai_strategy": True,
        "platforms": ["azure"],
        "strategy_types": None,
        "company_label": "AcmeCo",
        "website": "https://acme.example",
        "report_content": "## Report\nbody",
        "analysis_workbook": "workbook",
        "validated_source_urls": ["https://acme.example/about"],
        "discovery_notes_content": None,
        "refresh_vendor_research": False,
        "grok_reasoning": "reasoner-model",
        "grok_writing": "writer-model",
        "folder_path": str(seams["tmp"]),
        "output_dir": None,
        "diagnostics_dir": None,
        "write_txt": False,
        "recovery_executor": object(),
        "total_phases": 6,
    }
    defaults.update(overrides)
    return run_strategy_phase(**defaults)


class TestSkipPaths:
    def test_no_strategies_returns_empty(self, seams):
        result = _call(seams, has_strategies=False)
        assert result.strategy_paths == {}
        assert result.strategy_trust_stats == []
        seams["failover"].assert_not_called()

    def test_budget_exceeded_skips_generation(self, seams, monkeypatch):
        budget = MagicMock()
        budget.exceeded.return_value = True
        budget.max_cost = 1.50
        monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: budget)
        result = _call(seams)
        assert result.strategy_paths == {}
        assert result.strategy_outcome.status == "failed"
        assert result.strategy_outcome.skipped_targets == ("ai:azure",)
        seams["failover"].assert_not_called()
        budget.sync_spend.assert_called_once_with(0.50)

    def test_budget_under_cap_proceeds(self, seams, monkeypatch):
        budget = MagicMock()
        budget.exceeded.return_value = False
        monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: budget)
        result = _call(seams)
        assert "ai" in result.strategy_paths


class TestYAMLBudgetCheckpoint:
    """The strategy stage rechecks --budget between YAML strategy documents, so a
    multi-strategy run stops once the ceiling is reached (consistent with the
    Phase-2/5 checkpoints). Strategies already produced still ship."""

    _TYPES = ["customer_experience", "modern_security_compliance"]

    def test_skips_remaining_strategies_when_budget_exceeded_mid_loop(self, seams, monkeypatch):
        budget = MagicMock()
        budget.max_cost = 1.50
        # entry: under cap (proceed); first YAML type: under cap; second: over cap.
        budget.exceeded.side_effect = [False, False, True]
        monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: budget)

        result = _call(seams, ai_strategy=False, platforms=None, strategy_types=self._TYPES)

        assert "customer_experience" in result.strategy_paths
        assert "modern_security_compliance" not in result.strategy_paths
        # Only the first strategy's writing call ran; the second was skipped.
        assert seams["failover"].call_count == 1

    def test_generates_all_strategies_with_headroom(self, seams, monkeypatch):
        budget = MagicMock()
        budget.exceeded.return_value = False
        monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: budget)

        result = _call(seams, ai_strategy=False, platforms=None, strategy_types=self._TYPES)

        assert "customer_experience" in result.strategy_paths
        assert "modern_security_compliance" in result.strategy_paths
        assert seams["failover"].call_count == 2


class TestVendorBudgetCheckpoint:
    """Each AI-strategy vendor re-checks --budget at dispatch (bug-hunt
    finding: the stage-entry gate alone let multi-vendor runs overrun)."""

    def test_vendors_skipped_when_budget_reached_after_stage_entry(self, seams, monkeypatch):
        budget = MagicMock()
        budget.max_cost = 1.50
        # Stage entry sees headroom; by vendor dispatch the ceiling is hit.
        checks = iter([False])
        budget.exceeded.side_effect = lambda: next(checks, True)
        monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: budget)

        result = _call(seams, platforms=["azure", "aws"])

        assert result.strategy_paths == {}
        seams["failover"].assert_not_called()

    def test_vendors_proceed_with_headroom(self, seams, monkeypatch):
        budget = MagicMock()
        budget.exceeded.return_value = False
        monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: budget)

        result = _call(seams, platforms=["azure", "aws"])

        assert set(result.strategy_paths) == {"ai_azure", "ai_aws"}
        assert seams["failover"].call_count == 2


class TestAIStrategySingleVendor:
    def test_full_pipeline_saves_with_ai_key(self, seams):
        result = _call(seams)
        assert result.strategy_paths == {"ai": str(seams["tmp"] / "azure.docx")}
        assert result.strategy_outcome.status == "completed"
        seams["enrich"].assert_called_once()
        seams["prepare"].assert_called_once()

    def test_trust_stats_assembled(self, seams):
        result = _call(seams)
        assert len(result.strategy_trust_stats) == 1
        label, stats = result.strategy_trust_stats[0]
        assert label == "AI Strategy"
        assert dict(stats)["Gate"] == "PASS"
        assert dict(stats)["Sources"] == "5 valid"

    def test_vendor_research_skipped_for_agnostic(self, seams):
        _call(seams, platforms=["agnostic"])
        seams["vendor_research"].assert_not_called()

    def test_default_vendor_cache_lookup_disables_ambient_refresh(self, seams):
        _call(seams)

        seams["vendor_research"].assert_called_once_with(
            "azure",
            force_refresh=False,
            allow_auto_refresh=False,
            lite=True,
        )

    def test_explicit_refresh_reaches_agnostic_vendor_generation(self, seams):
        refreshed = seams["tmp"] / "refreshed-agnostic.txt"
        refreshed.write_text("Fresh cross-industry context.", encoding="utf-8")
        seams["vendor_research"].return_value = [str(refreshed)]
        seams["agnostic_research_path"].write_text(
            "Stale cross-industry context.",
            encoding="utf-8",
        )

        _call(
            seams,
            platforms=["agnostic"],
            refresh_vendor_research=True,
        )

        call = seams["vendor_research"].call_args
        assert call.args == ("agnostic",)
        # Freshness-aware refresh: reuse a current cache, regenerate only when
        # stale or missing (force_refresh=False, allow_auto_refresh=True).
        assert call.kwargs["force_refresh"] is False
        assert call.kwargs["allow_auto_refresh"] is True
        assert callable(call.kwargs["task_observer"])
        prompt = seams["failover"].call_args.args[1]
        assert "Fresh cross-industry context." in prompt
        assert "Stale cross-industry context." not in prompt

    def test_failed_agnostic_refresh_falls_back_to_cached_context(self, seams):
        seams["vendor_research"].return_value = []
        seams["agnostic_research_path"].write_text(
            "Fallback cross-industry context.",
            encoding="utf-8",
        )

        _call(
            seams,
            platforms=["agnostic"],
            refresh_vendor_research=True,
        )

        prompt = seams["failover"].call_args.args[1]
        assert prompt.count("Fallback cross-industry context.") == 1

    def test_vendor_cache_failure_is_body_safe_and_non_blocking(self, seams, caplog):
        seams["vendor_research"].side_effect = OSError("private-vendor-cache-location")

        result = _call(seams)

        assert "ai" in result.strategy_paths
        assert seams["failover"].call_count == 1
        assert "private-vendor-cache-location" not in caplog.text

    def test_multi_vendor_refresh_is_resolved_before_parallel_writing(self, seams):
        caller_thread = threading.current_thread().name
        lookup_threads: list[str] = []

        def resolve(_vendor, **_kwargs):
            lookup_threads.append(threading.current_thread().name)
            return []

        seams["vendor_research"].side_effect = resolve

        _call(
            seams,
            platforms=["azure", "aws", "gcp"],
            refresh_vendor_research=True,
        )

        assert lookup_threads == [caller_thread, caller_thread, caller_thread]
        assert seams["failover"].call_count == 3

    def test_refresh_count_tracks_only_provider_tasks_that_started(self, seams):
        def refreshed(_vendor, **kwargs):
            kwargs["task_observer"]("started")
            kwargs["task_observer"]("completed")
            return []

        seams["vendor_research"].side_effect = refreshed

        result = _call(seams, refresh_vendor_research=True)

        assert result.vendor_refresh_tasks_started == 1
        assert result.vendor_refresh_outcome.status == "completed"

    def test_refresh_without_budget_headroom_reuses_cache(self, seams, monkeypatch):
        skip = MagicMock(return_value=True)
        monkeypatch.setattr(
            "primr.core.fast_run_strategy.skip_stage_if_cost_would_exceed",
            skip,
        )

        result = _call(seams, refresh_vendor_research=True)

        assert result.vendor_refresh_tasks_started == 0
        seams["vendor_research"].assert_called_once_with(
            "azure",
            force_refresh=False,
            allow_auto_refresh=False,
            lite=True,
        )
        skip.assert_called_once()

    def test_later_refresh_gate_includes_earlier_submitted_task(self, seams, monkeypatch):
        observed_spend: list[float] = []

        def budget_gate(spend, _incremental_cost, _label):
            observed_spend.append(spend)
            return len(observed_spend) == 2

        def refresh(_vendor, **kwargs):
            observer = kwargs.get("task_observer")
            if observer:
                observer("started")
                observer("completed")
            return []

        monkeypatch.setattr(
            "primr.core.fast_run_strategy.skip_stage_if_cost_would_exceed",
            budget_gate,
        )
        seams["vendor_research"].side_effect = refresh

        result = _call(
            seams,
            platforms=["azure", "aws"],
            refresh_vendor_research=True,
        )

        assert observed_spend == [0.50, 3.00]
        assert result.vendor_refresh_tasks_started == 1
        assert result.vendor_refresh_outcome.status == "partial"
        assert result.vendor_refresh_outcome.completed_vendors == ("azure",)
        assert result.vendor_refresh_outcome.skipped_vendors == ("aws",)
        assert seams["vendor_research"].call_args_list[1].kwargs == {
            "force_refresh": False,
            "allow_auto_refresh": False,
            "lite": True,
        }

    def test_mixed_refresh_uses_fresh_cross_industry_context_for_every_vendor(self, seams):
        vendor_path = seams["tmp"] / "vendor-research-aws.txt"
        vendor_path.write_text("AWS capability evidence.", encoding="utf-8")
        seams["agnostic_research_path"].write_text(
            "Stale cross-industry context.", encoding="utf-8"
        )

        def refresh(vendor, **_kwargs):
            if vendor == "agnostic":
                seams["agnostic_research_path"].write_text(
                    "Fresh cross-industry context.", encoding="utf-8"
                )
                return [str(seams["agnostic_research_path"])]
            return [str(vendor_path)]

        seams["vendor_research"].side_effect = refresh

        _call(
            seams,
            platforms=["aws", "agnostic"],
            refresh_vendor_research=True,
        )

        prompts = [call.args[1] for call in seams["failover"].call_args_list]
        aws_prompt = next(prompt for prompt in prompts if "AWS capability evidence." in prompt)
        assert "Fresh cross-industry context." in aws_prompt
        assert "Stale cross-industry context." not in aws_prompt

    def test_cached_cross_industry_research_reaches_agnostic_prompt_once(self, seams):
        seams["agnostic_research_path"].write_text(
            "Cross-industry value pools and operating-model evidence.",
            encoding="utf-8",
        )

        _call(seams, platforms=["agnostic"])

        prompt = seams["failover"].call_args.args[1]
        assert prompt.count("Cross-industry value pools") == 1
        assert prompt.count("--- Cross-industry AI research ---") == 1
        seams["vendor_research"].assert_not_called()

    def test_vendor_prompt_combines_vendor_and_cross_industry_research(self, seams):
        vendor_path = seams["tmp"] / "vendor-research-azure.txt"
        vendor_path.write_text("Vendor capability evidence.", encoding="utf-8")
        seams["vendor_research"].return_value = [str(vendor_path)]
        seams["agnostic_research_path"].write_text(
            "Cross-industry operating evidence.",
            encoding="utf-8",
        )

        _call(seams)

        prompt = seams["failover"].call_args.args[1]
        assert prompt.count("Vendor capability evidence.") == 1
        assert prompt.count("Cross-industry operating evidence.") == 1

    def test_cached_cross_industry_research_is_bounded(self, seams):
        seams["agnostic_research_path"].write_text(
            "A" * 30_000 + "DO_NOT_INCLUDE",
            encoding="utf-8",
        )

        _call(seams, platforms=["agnostic"])

        prompt = seams["failover"].call_args.args[1]
        assert "A" * 30_000 in prompt
        assert "DO_NOT_INCLUDE" not in prompt

    def test_linked_cross_industry_cache_is_rejected_without_blocking(self, seams):
        source = seams["tmp"] / "source-research.txt"
        source.write_text("LINKED_CONTEXT_MUST_NOT_EGRESS", encoding="utf-8")
        seams["agnostic_research_path"].hardlink_to(source)

        result = _call(seams, platforms=["agnostic"])

        assert "ai" in result.strategy_paths
        prompt = seams["failover"].call_args.args[1]
        assert "LINKED_CONTEXT_MUST_NOT_EGRESS" not in prompt
        seams["vendor_research"].assert_not_called()

    def test_in_place_cache_mutation_is_rejected(self, seams, monkeypatch):
        from primr.core import trusted_report

        cache_path = seams["agnostic_research_path"]
        cache_path.write_text("MUTATING_CONTEXT", encoding="utf-8")
        real_digest = trusted_report.hashlib.file_digest

        def digest_then_mutate(handle, algorithm):
            digest = real_digest(handle, algorithm)
            metadata = cache_path.stat()
            cache_path.touch()
            if cache_path.stat().st_mtime_ns == metadata.st_mtime_ns:
                cache_path.write_text("MUTATING_CONTEXT_CHANGED", encoding="utf-8")
            return digest

        monkeypatch.setattr(trusted_report.hashlib, "file_digest", digest_then_mutate)

        result = _call(seams, platforms=["agnostic"])

        prompt = seams["failover"].call_args.args[1]
        assert "MUTATING_CONTEXT" not in prompt
        assert "ai" in result.strategy_paths

    def test_cache_lookup_failure_is_body_safe_and_non_blocking(self, seams, monkeypatch, caplog):
        monkeypatch.setattr(
            "primr.core.fast_run_strategy.get_vendor_research_path",
            MagicMock(side_effect=OSError("private-cache-location")),
        )

        result = _call(seams, platforms=["agnostic"])

        assert "ai" in result.strategy_paths
        assert "private-cache-location" not in caplog.text
        seams["vendor_research"].assert_not_called()

    def test_llm_failure_abandons_vendor_without_raising(self, seams):
        seams["failover"].side_effect = RuntimeError("API down")
        result = _call(seams)
        assert result.strategy_paths == {}
        assert result.strategy_outcome.status == "failed"
        assert result.strategy_outcome.failed_targets == ("ai:azure",)
        seams["save"].assert_not_called()

    def test_enrich_failure_keeps_original_content(self, seams):
        seams["enrich"].side_effect = RuntimeError("enrich down")
        result = _call(seams)
        assert "ai" in result.strategy_paths  # still saved
        prepared_content = seams["prepare"].call_args.args[0]
        assert prepared_content.startswith("## Strategy")


class TestAIStrategyMultiVendor:
    def test_parallel_vendors_get_prefixed_keys(self, seams):
        result = _call(seams, platforms=["azure", "aws"])
        assert set(result.strategy_paths) == {"ai_azure", "ai_aws"}
        assert len(result.strategy_trust_stats) == 2
        labels = {label for label, _ in result.strategy_trust_stats}
        assert labels == {"AI Strategy (AZURE)", "AI Strategy (AWS)"}

    def test_one_vendor_failing_does_not_block_others(self, seams):
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if kwargs.get("max_tokens") and calls["n"] == 1:
                raise RuntimeError("first vendor died")
            return "## Strategy\ncontent body"

        seams["failover"].side_effect = flaky
        result = _call(seams, platforms=["azure", "aws"])
        assert len(result.strategy_paths) == 1
        assert result.strategy_outcome.status == "partial"
        assert len(result.strategy_outcome.completed_targets) == 1
        assert len(result.strategy_outcome.failed_targets) == 1


class TestYamlStrategies:
    def test_real_yaml_strategy_loads_and_saves(self, seams):
        result = _call(
            seams, ai_strategy=False, platforms=None, strategy_types=["customer_experience"]
        )
        assert "customer_experience" in result.strategy_paths
        seams["build_yaml_prompt"].assert_called_once()
        config = seams["build_yaml_prompt"].call_args.args[0]
        assert "meta" in config  # real YAML parsed from the package

    def test_unknown_yaml_skipped_cleanly(self, seams):
        result = _call(
            seams, ai_strategy=False, platforms=None, strategy_types=["nonexistent_strategy"]
        )
        assert result.strategy_paths == {}

    def test_ai_stype_skipped_in_yaml_loop(self, seams):
        result = _call(seams, ai_strategy=False, platforms=None, strategy_types=["ai"])
        assert result.strategy_paths == {}
        seams["build_yaml_prompt"].assert_not_called()


class TestCachedPrefixSharing:
    """Roadmap #8: strategy calls in one run share a byte-identical cached prefix."""

    def _sent_prompts(self, seams):
        # call_with_failover(LLMRole.WRITING, prompt, ...) - prompt is arg 1.
        return [c.args[1] for c in seams["failover"].call_args_list]

    def test_ai_vendors_share_context_prefix(self, seams):
        from primr.core.strategy_prompt_parts import (
            AI_STRATEGY_ARTIFACTS,
            build_strategy_context_prefix,
            read_artifact_blocks,
        )

        (seams["tmp"] / "insights.txt").write_text("shared insight", encoding="utf-8")
        seams["build_ai_prompt"].side_effect = lambda company, vendor, notes: f"{vendor} prompt"

        _call(seams, platforms=["azure", "aws"])

        prompts = self._sent_prompts(seams)
        assert len(prompts) == 2
        expected_prefix = build_strategy_context_prefix(
            "## Report\nbody",
            read_artifact_blocks(str(seams["tmp"]), AI_STRATEGY_ARTIFACTS),
        )
        assert all(p.startswith(expected_prefix) for p in prompts)
        # The suffixes differ (vendor-specific prompts) - only the prefix is shared.
        suffixes = {p[len(expected_prefix) :] for p in prompts}
        assert suffixes == {"\n\n---\n\nazure prompt", "\n\n---\n\naws prompt"}

    def test_yaml_strategies_share_context_prefix(self, seams):
        # _recon_context.txt is an UNTRUSTED_ARTIFACTS member: it is fenced
        # with a per-call nonce, so the expected prefix cannot be recomputed
        # out-of-band. Instead pin that both sent prompts carry a byte-identical
        # context prefix (everything before the parts divider) built ONCE.
        (seams["tmp"] / "_recon_context.txt").write_text("recon block", encoding="utf-8")
        seams["build_yaml_prompt"].side_effect = lambda config, company, notes: (
            f"{config['meta']['name']} prompt"
        )

        _call(
            seams,
            ai_strategy=False,
            platforms=None,
            strategy_types=["customer_experience", "data_strategy"],
        )

        prompts = self._sent_prompts(seams)
        assert len(prompts) == 2
        prefixes = {p.split("\n\n---\n\n")[0] for p in prompts}
        assert len(prefixes) == 1  # byte-identical cached prefix across types
        (shared_prefix,) = prefixes
        assert shared_prefix.startswith("Use the following context documents")
        assert "recon block" in shared_prefix
        # The scraped-adjacent artifact is fenced as data inside the prefix.
        assert "UNTRUSTED_ARTIFACT_BEGIN" in shared_prefix
        assert prompts[0] != prompts[1]
