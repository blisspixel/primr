from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from primr.config.inference import (
    HOST_AGENT_MAY_BILL_ENV,
    INFERENCE_PROFILE_ENV,
    configure_inference_environment,
    host_agent_may_bill_acknowledged,
)
from primr.core.cli_inference import (
    HOST_AGENT_ESTIMATE_NOTE,
    append_inference_estimate_note,
    inference_estimate_metadata,
    prepare_batch_inference_runtime,
    prepare_inference_runtime,
    validate_inference_options,
)


def _config(*, profile: str = "hybrid", acknowledged: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        inference_profile=profile,
        acknowledge_host_agent_may_bill=acknowledged,
    )


def test_host_billing_acknowledgment_requires_exact_value() -> None:
    assert host_agent_may_bill_acknowledged({HOST_AGENT_MAY_BILL_ENV: "1"}) is True
    assert host_agent_may_bill_acknowledged({HOST_AGENT_MAY_BILL_ENV: "true"}) is False
    assert host_agent_may_bill_acknowledged({HOST_AGENT_MAY_BILL_ENV: "yes"}) is False
    assert host_agent_may_bill_acknowledged({}) is False


def test_configure_inference_environment_clears_stale_acknowledgment() -> None:
    environment = {HOST_AGENT_MAY_BILL_ENV: "1"}

    configure_inference_environment("cloud", False, environment=environment)

    assert environment == {INFERENCE_PROFILE_ENV: "cloud"}


def test_configure_inference_environment_records_explicit_acknowledgment() -> None:
    environment: dict[str, str] = {}

    configure_inference_environment("hybrid", True, environment=environment)

    assert environment == {
        INFERENCE_PROFILE_ENV: "hybrid",
        HOST_AGENT_MAY_BILL_ENV: "1",
    }


def test_acknowledgment_requires_hybrid_profile() -> None:
    assert (
        validate_inference_options("cloud", True)
        == "--acknowledge-host-agent-may-bill requires --inference hybrid"
    )
    assert validate_inference_options("hybrid", True) is None
    assert validate_inference_options("cloud", False) is None


def test_prepare_runtime_warns_and_exports_acknowledgment(monkeypatch) -> None:
    console = SimpleNamespace(error=MagicMock(), warn=MagicMock())
    monkeypatch.delenv(INFERENCE_PROFILE_ENV, raising=False)
    monkeypatch.delenv(HOST_AGENT_MAY_BILL_ENV, raising=False)

    assert prepare_inference_runtime(_config(), console) is True

    assert host_agent_may_bill_acknowledged() is True
    assert __import__("os").environ[INFERENCE_PROFILE_ENV] == "hybrid"
    console.error.assert_not_called()
    console.warn.assert_called_once()


def test_prepare_runtime_rejects_invalid_pair_without_mutating_environment(monkeypatch) -> None:
    console = SimpleNamespace(error=MagicMock(), warn=MagicMock())
    monkeypatch.setenv(INFERENCE_PROFILE_ENV, "existing")
    monkeypatch.delenv(HOST_AGENT_MAY_BILL_ENV, raising=False)

    assert prepare_inference_runtime(_config(profile="cloud"), console) is False

    assert __import__("os").environ[INFERENCE_PROFILE_ENV] == "existing"
    assert host_agent_may_bill_acknowledged() is False
    console.error.assert_called_once()
    console.warn.assert_not_called()


def test_batch_runtime_rejects_experimental_host_fanout(monkeypatch) -> None:
    console = SimpleNamespace(error=MagicMock(), warn=MagicMock())
    monkeypatch.delenv(HOST_AGENT_MAY_BILL_ENV, raising=False)

    assert prepare_batch_inference_runtime(_config(), console) is False

    assert host_agent_may_bill_acknowledged() is False
    console.error.assert_called_once_with(
        "--acknowledge-host-agent-may-bill is limited to single-company research"
    )


def test_batch_runtime_applies_non_host_profile(monkeypatch) -> None:
    console = SimpleNamespace(error=MagicMock(), warn=MagicMock())
    monkeypatch.setenv(HOST_AGENT_MAY_BILL_ENV, "1")

    assert (
        prepare_batch_inference_runtime(
            _config(profile="hybrid", acknowledged=False),
            console,
        )
        is True
    )

    assert __import__("os").environ[INFERENCE_PROFILE_ENV] == "hybrid"
    assert host_agent_may_bill_acknowledged() is False
    console.error.assert_not_called()


def test_estimate_note_is_added_once_only_when_acknowledged() -> None:
    estimate = SimpleNamespace(notes=[])

    append_inference_estimate_note(_config(), estimate)
    append_inference_estimate_note(_config(), estimate)

    assert estimate.notes == [HOST_AGENT_ESTIMATE_NOTE]

    cloud_estimate = SimpleNamespace(notes=[])
    append_inference_estimate_note(_config(profile="cloud", acknowledged=False), cloud_estimate)
    assert cloud_estimate.notes == []


def test_estimate_note_defaults_to_disabled_for_legacy_config_stub() -> None:
    estimate = SimpleNamespace(notes=[])

    append_inference_estimate_note(SimpleNamespace(inference_profile="cloud"), estimate)

    assert estimate.notes == []


def test_json_metadata_discloses_uncapped_host_cost() -> None:
    metadata = inference_estimate_metadata(_config())

    assert metadata == {
        "profile": "hybrid",
        "host_agent": {
            "enabled": True,
            "runner": "codex_cli",
            "billing_mode": "potentially_metered",
            "billing_acknowledged": True,
            "promotion_status": "experimental_eval_pending",
            "eligible_stages": ["fast.source_relevance"],
            "cost_included_in_estimate": False,
            "covered_by_budget": False,
        },
    }


def test_json_metadata_uses_not_applicable_cost_fields_when_host_is_disabled() -> None:
    metadata = inference_estimate_metadata(_config(profile="cloud", acknowledged=False))

    assert metadata["host_agent"] == {
        "enabled": False,
        "runner": None,
        "billing_mode": "unknown",
        "billing_acknowledged": False,
        "promotion_status": None,
        "eligible_stages": [],
        "cost_included_in_estimate": None,
        "covered_by_budget": None,
    }
