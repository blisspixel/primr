from __future__ import annotations

from datetime import UTC, datetime
from urllib.error import HTTPError

from primr.ai.provider_availability import AvailabilityState, availability_decision
from primr.ai.provider_availability_collectors import (
    LOCAL_OPENAI_COMPATIBLE_PROVIDER,
    collect_env_provider_availability,
    collect_local_openai_compatible_availability,
    collect_provider_availability_snapshots,
)
from primr.ai.providers.registry import ProviderEntry

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def _entry(
    *,
    name: str = "openai",
    api_key_env: str = "OPENAI_API_KEY",
    api_key_default: str | None = None,
) -> ProviderEntry:
    return ProviderEntry(
        name=name,
        api_key_env=api_key_env,
        api_key_default=api_key_default,
        description=f"{name.title()} provider (utility)",
        roles=("utility",),
    )


def test_env_provider_snapshot_records_configuration_without_secret_value() -> None:
    secret = "test-key-value-that-must-not-leak"

    snapshot = collect_env_provider_availability(
        _entry(),
        env={"OPENAI_API_KEY": secret},
        now=NOW,
    )

    assert snapshot.ok is True
    assert snapshot.error is None
    assert snapshot.provider == "openai"
    assert snapshot.metadata["configured"] is True
    assert snapshot.metadata["credential_source"] == "env"
    assert snapshot.metadata["api_key_env"] == "OPENAI_API_KEY"
    assert secret not in str(snapshot)
    assert secret not in str(snapshot.metadata)


def test_env_provider_snapshot_marks_missing_key_without_network_probe() -> None:
    snapshot = collect_env_provider_availability(_entry(), env={}, now=NOW)

    assert snapshot.ok is False
    assert snapshot.error == "missing_api_key"
    assert snapshot.metadata["configured"] is False
    assert snapshot.metadata["quota_source"] == "not_collected"


def test_env_provider_snapshot_supports_provider_default_without_secret_material() -> None:
    default_value = "provider-default-token"
    snapshot = collect_env_provider_availability(
        _entry(name="demo", api_key_env="DEMO_API_KEY", api_key_default=default_value),
        env={},
        now=NOW,
    )

    assert snapshot.ok is True
    assert snapshot.metadata["credential_source"] == "provider_default"
    assert default_value not in str(snapshot.metadata)


def test_local_openai_compatible_snapshot_is_available_for_any_chat_model() -> None:
    seen: list[str | None] = []

    def list_models(base_url: str | None) -> list[str]:
        seen.append(base_url)
        return ["custom-local-model:latest", "nomic-embed-text:latest"]

    snapshot = collect_local_openai_compatible_availability(
        base_url="http://gpu-box:8080",
        list_models_fn=list_models,
        now=NOW,
    )

    assert snapshot.provider == LOCAL_OPENAI_COMPATIBLE_PROVIDER
    assert snapshot.ok is True
    assert availability_decision(snapshot, NOW).available is True
    assert snapshot.metadata["model_count"] == 2
    assert snapshot.metadata["chat_model_available"] is True
    assert snapshot.metadata["endpoint_source"] == "argument"
    assert seen == ["http://gpu-box:8080/v1"]
    assert "gpu-box" not in str(snapshot.metadata)
    assert "custom-local-model" not in str(snapshot.metadata)


def test_local_openai_compatible_snapshot_rejects_embed_only_endpoint() -> None:
    snapshot = collect_local_openai_compatible_availability(
        env={"LOCAL_LLM_BASE_URL": "http://personal-box:1234"},
        list_models_fn=lambda base_url: ["nomic-embed-text:latest", "bge-m3:latest"],
        now=NOW,
    )

    assert snapshot.ok is False
    assert snapshot.error == "local_openai_compatible_unavailable"
    assert snapshot.metadata["model_count"] == 2
    assert snapshot.metadata["chat_model_available"] is False
    assert snapshot.metadata["endpoint_source"] == "LOCAL_LLM_BASE_URL"
    assert "personal-box" not in str(snapshot)


def test_local_openai_compatible_probe_failure_fails_open_without_endpoint_leak() -> None:
    def explode(base_url: str | None) -> list[str]:
        raise ConnectionError(f"cannot reach {base_url}")

    snapshot = collect_local_openai_compatible_availability(
        env={"OLLAMA_BASE_URL": "http://workstation:11434"},
        list_models_fn=explode,
        now=NOW,
    )

    assert snapshot.ok is False
    assert snapshot.error == "local_openai_compatible_probe_failed"
    assert snapshot.metadata["endpoint_source"] == "OLLAMA_BASE_URL"
    assert "workstation" not in str(snapshot)


def test_local_openai_compatible_busy_snapshot_has_bounded_retry_metadata() -> None:
    def busy(base_url: str | None) -> list[str]:
        raise HTTPError(
            str(base_url),
            503,
            "busy at operator-host.example.invalid",
            {"Retry-After": "240"},
            None,
        )

    snapshot = collect_local_openai_compatible_availability(
        env={"LOCAL_LLM_BASE_URL": "http://operator-host.example.invalid:1234"},
        list_models_fn=busy,
        now=NOW,
    )
    decision = availability_decision(snapshot, NOW)

    assert snapshot.ok is False
    assert snapshot.state is AvailabilityState.BUSY
    assert snapshot.error == "local_openai_compatible_busy"
    assert snapshot.metadata["capacity_state"] == "busy"
    assert snapshot.metadata["capacity_reason"] == "local_capacity_http_503_busy"
    assert snapshot.metadata["retryable"] is True
    assert snapshot.metadata["status_code"] == 503
    assert decision.retry_after_seconds == 240
    assert "operator-host" not in str(snapshot)


def test_collect_provider_availability_snapshots_is_generic_and_secret_safe() -> None:
    snapshots = collect_provider_availability_snapshots(
        entries=(
            _entry(name="openai", api_key_env="OPENAI_API_KEY"),
            _entry(name="anthropic", api_key_env="ANTHROPIC_API_KEY"),
            _entry(name="ollama", api_key_env="OLLAMA_API_KEY", api_key_default="ollama"),
        ),
        env={
            "OPENAI_API_KEY": "test-openai-key-value",
            "LOCAL_LLM_BASE_URL": "http://desk:9999",
        },
        local_list_models_fn=lambda base_url: ["qwen3:14b"],
        now=NOW,
    )

    by_provider = {snapshot.provider: snapshot for snapshot in snapshots}

    assert set(by_provider) == {"openai", "anthropic", LOCAL_OPENAI_COMPATIBLE_PROVIDER}
    assert by_provider["openai"].ok is True
    assert by_provider["anthropic"].ok is False
    assert by_provider[LOCAL_OPENAI_COMPATIBLE_PROVIDER].ok is True
    assert "test-openai-key-value" not in str(snapshots)
    assert "desk" not in str(snapshots)
