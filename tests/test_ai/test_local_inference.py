"""Tests for local-inference detection and judge-model selection.

The contract under test is the "anyone's setup" rule: detection enumerates
what the user actually has, absence is the silent default (never an error),
and selection works with whatever is installed — including nothing.
"""

from urllib.error import HTTPError

import pytest

from primr.ai.local_inference import (
    clear_probe_cache,
    is_local_inference_available,
    list_local_models,
    pick_local_judge_model,
    probe_local_capacity,
)
from primr.ai.provider_availability import AvailabilityState


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_probe_cache()
    yield
    clear_probe_cache()


def _tags(*names: str):
    return {"data": [{"id": name} for name in names]}


class TestDetection:
    def test_lists_models_from_openai_endpoint(self):
        seen = {}

        def fake_fetch(url, timeout):
            seen["url"] = url
            return _tags("modela:7b", "modelb:30b")

        models = list_local_models("http://localhost:11434", fetch_json_fn=fake_fetch)
        assert models == ["modela:7b", "modelb:30b"]
        assert seen["url"].endswith("/v1/models")

    def test_connection_failure_means_no_models_not_error(self):
        def explode(url, timeout):
            raise ConnectionError("refused")

        assert list_local_models("http://localhost:11434", fetch_json_fn=explode) == []

    def test_malformed_payload_fails_open(self):
        assert (
            list_local_models(
                "http://localhost:11434", fetch_json_fn=lambda u, t: {"unexpected": 1}
            )
            == []
        )

    def test_probe_result_cached_per_process(self):
        calls = []

        def counting_fetch(url, timeout):
            calls.append(url)
            return _tags("m:7b")

        list_local_models("http://localhost:11434", fetch_json_fn=counting_fetch)
        list_local_models("http://localhost:11434", fetch_json_fn=counting_fetch)
        assert len(calls) == 1

    def test_cache_can_be_bypassed(self):
        calls = []

        def counting_fetch(url, timeout):
            calls.append(url)
            return _tags("m:7b")

        list_local_models("http://x:1234", fetch_json_fn=counting_fetch, use_cache=False)
        list_local_models("http://x:1234", fetch_json_fn=counting_fetch, use_cache=False)
        assert len(calls) == 2

    def test_busy_probe_is_not_cached_and_preserves_retry_after(self):
        calls = []

        def busy_fetch(url, timeout):
            calls.append(url)
            raise HTTPError(url, 503, "busy", {"Retry-After": "120"}, None)

        first = probe_local_capacity("http://x:1234", fetch_json_fn=busy_fetch)
        second = probe_local_capacity("http://x:1234", fetch_json_fn=busy_fetch)

        assert first.state is AvailabilityState.BUSY
        assert first.reason == "local_capacity_http_503_busy"
        assert first.retry_after_seconds == 120
        assert first.status_code == 503
        assert second.state is AvailabilityState.BUSY
        assert len(calls) == 2

    def test_timeout_busy_guidance_backs_off_by_caller_attempt(self):
        def timeout_fetch(url, timeout):
            raise TimeoutError("local endpoint did not answer")

        probe = probe_local_capacity(
            "http://x:1234",
            fetch_json_fn=timeout_fetch,
            attempt=2,
        )

        assert probe.state is AvailabilityState.BUSY
        assert probe.reason == "local_capacity_timeout_busy"
        assert probe.retry_after_seconds == 21_600

    def test_connection_refusal_is_unavailable_without_retry_guidance(self):
        def unavailable_fetch(url, timeout):
            raise ConnectionRefusedError("refused")

        probe = probe_local_capacity("http://x:1234", fetch_json_fn=unavailable_fetch)

        assert probe.state is AvailabilityState.UNAVAILABLE
        assert probe.retry_after_seconds is None

    def test_env_chain_resolves_base_url(self, monkeypatch):
        monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://gpu-box:8080")
        seen = {}

        def fake_fetch(url, timeout):
            seen["url"] = url
            return _tags("m:7b")

        list_local_models(None, fetch_json_fn=fake_fetch)
        assert seen["url"] == "http://gpu-box:8080/v1/models"

    def test_availability_helper(self):
        assert is_local_inference_available is not None
        clear_probe_cache()
        # No fetch injection here would hit the network; use list via cache.
        # Seed the cache through the injectable path instead:
        list_local_models("http://seeded:1", fetch_json_fn=lambda u, t: _tags("m:7b"))
        assert list_local_models("http://seeded:1") == ["m:7b"]


class TestJudgeModelSelection:
    def test_prefers_known_family_over_install_order(self):
        installed = ["mystery-model:13b", "qwen2.5:14b", "llama3:8b"]
        assert pick_local_judge_model(installed) == "qwen2.5:14b"

    def test_family_preference_order(self):
        # qwen3 outranks llama3 regardless of list order.
        assert pick_local_judge_model(["llama3:70b", "qwen3:30b"]) == "qwen3:30b"

    def test_reasoning_family_ranked_last(self):
        assert pick_local_judge_model(["deepseek-r1:32b", "gemma3:27b"]) == "gemma3:27b"

    def test_unknown_family_still_usable_as_fallback(self):
        assert pick_local_judge_model(["totally-custom:42b"]) == "totally-custom:42b"

    def test_non_chat_models_excluded(self):
        assert pick_local_judge_model(["nomic-embed-text:latest", "bge-m3:567m"]) is None

    def test_empty_install_returns_none(self):
        assert pick_local_judge_model([]) is None
