from primr.core.budget_policy import describe_budget_enforcement


class TestBudgetPolicy:
    def test_fast_full_runs_have_runtime_checkpoints(self):
        policy = describe_budget_enforcement(
            mode="complete",
            fast_mode=True,
            premium_mode=False,
        )

        assert policy.runtime_checkpoints is True
        assert "research deepening" in policy.checkpointed_stages
        assert "strategy generation" in policy.checkpointed_stages
        assert "core workbook" in policy.runtime

    def test_premium_runs_are_estimate_gated_only(self):
        policy = describe_budget_enforcement(
            mode="complete",
            fast_mode=False,
            premium_mode=True,
        )

        assert policy.runtime_checkpoints is False
        assert policy.checkpointed_stages == ()
        assert "estimate-gated only" in policy.runtime

    def test_scrape_runs_are_estimate_gated_only(self):
        policy = describe_budget_enforcement(
            mode="scrape-only",
            fast_mode=False,
            premium_mode=False,
        )

        assert policy.runtime_checkpoints is False
        assert "not wired" in policy.runtime

    def test_agent_payload_is_json_safe(self):
        policy = describe_budget_enforcement(
            mode="full",
            fast_mode=True,
            premium_mode=False,
        )

        payload = policy.as_dict()

        assert payload["runtime_checkpoints"] is True
        assert isinstance(payload["checkpointed_stages"], list)
