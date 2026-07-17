from types import SimpleNamespace
from unittest.mock import MagicMock

import openai
import pytest

from primr.ai import grok_client


class _Retryable503Error(Exception):
    def __init__(
        self, message: str = "503 Service temporarily unavailable", retry_after: str | None = None
    ):
        super().__init__(message)
        headers = {"retry-after": retry_after} if retry_after is not None else {}
        self.response = SimpleNamespace(headers=headers)


class _FakeCompletions:
    def __init__(self, sequence):
        self._sequence = list(sequence)

    def create(self, **kwargs):
        item = self._sequence.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeClient:
    def __init__(self, sequence):
        self.chat = SimpleNamespace(completions=_FakeCompletions(sequence))


class _FakeResponse:
    def __init__(self, text: str):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=text))]
        self.usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7)


def test_lazy_grok_client_disables_sdk_retries(monkeypatch):
    http_client = object()
    http_factory = MagicMock(return_value=http_client)
    factory = MagicMock(return_value=object())
    monkeypatch.setattr(openai, "DefaultHttpxClient", http_factory)
    monkeypatch.setattr(openai, "OpenAI", factory)
    monkeypatch.setattr(grok_client, "_client", None)
    monkeypatch.setenv("XAI_API_KEY", "test-key")

    grok_client._get_grok_client()

    http_factory.assert_called_once_with(follow_redirects=False)
    factory.assert_called_once_with(
        api_key="test-key",
        base_url="https://api.x.ai/v1",
        max_retries=0,
        http_client=http_client,
    )


def test_retryable_classifier_includes_503():
    assert grok_client._is_retryable_grok_error(_Retryable503Error()) is True


def test_retryable_classifier_excludes_auth_errors():
    assert grok_client._is_retryable_grok_error(Exception("401 unauthorized")) is False


def test_extract_retry_after_seconds_from_headers():
    err = _Retryable503Error(retry_after="17")
    assert grok_client._extract_retry_after_seconds(err) == 17.0


def test_grok_llm_retries_on_503_then_succeeds(monkeypatch):
    from primr.ai.providers import openai_compatible

    grok_client.reset_grok_session()
    client = _FakeClient(
        [
            _Retryable503Error(),
            _FakeResponse("ok"),
        ]
    )

    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)
    monkeypatch.setattr(openai_compatible.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(openai_compatible, "_compute_backoff_delay", lambda *_args, **_kwargs: 0.0)

    out = grok_client.grok_llm("hello", retries=1)

    assert out == "ok"
    usage = grok_client.get_grok_session_usage()
    assert usage["input_tokens"] == 11
    assert usage["output_tokens"] == 7


def test_grok_llm_exhausts_retryable_errors(monkeypatch):
    from primr.ai.providers import openai_compatible

    grok_client.reset_grok_session()
    client = _FakeClient(
        [
            _Retryable503Error(),
            _Retryable503Error(),
        ]
    )

    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)
    monkeypatch.setattr(openai_compatible.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(openai_compatible, "_compute_backoff_delay", lambda *_args, **_kwargs: 0.0)

    with pytest.raises(RuntimeError, match="after 2 attempts"):
        grok_client.grok_llm("hello", retries=1)


# ---------------------------------------------------------------------------
# ContinuousReasoningSession (Step 3 migration)
# ---------------------------------------------------------------------------


def test_continuous_session_appends_user_and_assistant_turns(monkeypatch):
    grok_client.reset_grok_session()
    client = _FakeClient([_FakeResponse("workbook output")])
    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)

    session = grok_client.ContinuousReasoningSession(
        model="grok-4.3", system_prompt="you are an analyst"
    )
    out = session.send("draft the workbook")

    assert out == "workbook output"
    assert session.turns == 1
    # System prompt + user turn + assistant turn
    assert len(session.history) == 3
    assert session.history[0]["role"] == "system"
    assert session.history[1] == {"role": "user", "content": "draft the workbook"}
    assert session.history[2] == {"role": "assistant", "content": "workbook output"}


def test_continuous_session_history_persists_across_turns(monkeypatch):
    grok_client.reset_grok_session()
    client = _FakeClient(
        [
            _FakeResponse("first reply"),
            _FakeResponse("second reply"),
        ]
    )
    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)

    session = grok_client.ContinuousReasoningSession(model="grok-4.3")
    session.send("first prompt")
    session.send("second prompt")

    assert session.turns == 2
    # Two user + two assistant turns, no system prompt
    roles = [m["role"] for m in session.history]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_continuous_session_stateless_send_preserves_configuration_without_history(monkeypatch):
    captured: dict[str, object] = {}

    def fake_grok_llm(prompt: str, **kwargs: object) -> str:
        captured.update({"prompt": prompt, **kwargs})
        return "stateless output"

    monkeypatch.setattr(grok_client, "grok_llm", fake_grok_llm)
    session = grok_client.ContinuousReasoningSession(
        model="grok-4.3",
        system_prompt="persistent context",
        reasoning_effort="high",
    )

    output = session.send_stateless(
        "isolated task",
        system_prompt="eval system",
        temperature=0.2,
        max_tokens=1_500,
        retries=1,
    )

    assert output == "stateless output"
    assert captured == {
        "prompt": "isolated task",
        "system_prompt": "eval system",
        "model": "grok-4.3",
        "temperature": 0.2,
        "max_tokens": 1_500,
        "retries": 1,
        "reasoning_effort": "high",
    }
    assert session.turns == 0
    assert session.history == [{"role": "system", "content": "persistent context"}]


def test_continuous_session_rolls_back_user_turn_on_error(monkeypatch):
    """Failed call must not leave a hanging user turn in the history."""
    from primr.ai.providers import openai_compatible

    grok_client.reset_grok_session()
    client = _FakeClient([Exception("invalid request — non-retryable")])
    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)
    monkeypatch.setattr(openai_compatible.time, "sleep", lambda *_args, **_kwargs: None)

    session = grok_client.ContinuousReasoningSession(model="grok-4.3")
    with pytest.raises(RuntimeError):
        session.send("this will fail")

    # User turn rolled back — history should be empty
    assert session.history == []
    assert session.turns == 0


def test_continuous_session_records_usage_into_module_globals(monkeypatch):
    grok_client.reset_grok_session()
    client = _FakeClient([_FakeResponse("x")])
    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)

    session = grok_client.ContinuousReasoningSession(model="grok-4.3")
    session.send("x")

    usage = grok_client.get_grok_session_usage()
    # _FakeResponse reports 11 prompt + 7 completion tokens
    assert usage["input_tokens"] == 11
    assert usage["output_tokens"] == 7

    by_model = grok_client.get_grok_session_usage_by_model()
    assert by_model["grok-4.3"]["input_tokens"] == 11
    assert by_model["grok-4.3"]["output_tokens"] == 7


# ---------------------------------------------------------------------------
# Cached-input-token session tracking (cache-hit visibility)
# ---------------------------------------------------------------------------


class _FakeCachedResponse:
    """Response whose usage reports xAI-style top-level cached_tokens."""

    def __init__(self, text: str, prompt: int = 20, completion: int = 8, cached: int = 12):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=text))]
        self.usage = SimpleNamespace(
            prompt_tokens=prompt, completion_tokens=completion, cached_tokens=cached
        )


def test_grok_llm_tracks_cached_input_tokens(monkeypatch):
    grok_client.reset_grok_session()
    client = _FakeClient([_FakeCachedResponse("ok")])
    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)

    out = grok_client.grok_llm("hello")

    assert out == "ok"
    usage = grok_client.get_grok_session_usage()
    assert usage["input_tokens"] == 20
    assert usage["output_tokens"] == 8
    assert usage["cached_input_tokens"] == 12

    by_model = grok_client.get_grok_session_usage_by_model()
    (bucket,) = by_model.values()
    assert bucket["cached_input_tokens"] == 12


def test_session_usage_without_cache_reports_zero_cached(monkeypatch):
    grok_client.reset_grok_session()
    client = _FakeClient([_FakeResponse("ok")])
    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)

    grok_client.grok_llm("hello")

    usage = grok_client.get_grok_session_usage()
    assert usage["cached_input_tokens"] == 0


def test_reset_grok_session_clears_cached_counter(monkeypatch):
    grok_client.reset_grok_session()
    client = _FakeClient([_FakeCachedResponse("ok")])
    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)
    grok_client.grok_llm("hello")
    assert grok_client.get_grok_session_usage()["cached_input_tokens"] == 12

    grok_client.reset_grok_session()

    usage = grok_client.get_grok_session_usage()
    assert usage["input_tokens"] == 0
    assert usage["cached_input_tokens"] == 0


def test_continuous_session_tracks_cached_tokens(monkeypatch):
    grok_client.reset_grok_session()
    client = _FakeClient([_FakeCachedResponse("turn output")])
    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)

    session = grok_client.ContinuousReasoningSession(model="grok-4.3")
    session.send("draft")

    usage = grok_client.get_grok_session_usage()
    assert usage["cached_input_tokens"] == 12
    assert grok_client.get_grok_session_usage_by_model()["grok-4.3"]["cached_input_tokens"] == 12


def test_mirror_session_usage_tolerates_legacy_bucket_shape():
    """Buckets persisted before the cached counter existed must not KeyError."""
    grok_client.reset_grok_session()
    # Simulate an old-shape bucket (no cached_input_tokens key)
    grok_client._session_tokens_by_model["grok-4.3"] = {
        "input_tokens": 5,
        "output_tokens": 3,
    }

    grok_client._mirror_session_usage("grok-4.3", 10, 4, cached_input_tokens=6)

    bucket = grok_client.get_grok_session_usage_by_model()["grok-4.3"]
    assert bucket["input_tokens"] == 15
    assert bucket["output_tokens"] == 7
    assert bucket["cached_input_tokens"] == 6
    grok_client.reset_grok_session()


def test_mirror_session_usage_is_thread_safe():
    """Concurrent mirrors from parallel section/strategy threads lose no tokens.

    Budget checkpoints read these counters; a lost read-modify-write would
    silently understate spend (bug-hunt finding). On GIL builds of CPython
    3.12+ straight-line increments cannot be preempted mid-operation, so this
    pins the exact-total semantics rather than provoking the race; the lock
    exists for free-threaded builds and for consistent multi-field snapshots
    in the getters.
    """
    import sys
    import threading

    grok_client.reset_grok_session()
    workers, per_worker = 8, 500
    barrier = threading.Barrier(workers)

    def hammer():
        barrier.wait()
        for _ in range(per_worker):
            grok_client._mirror_session_usage("grok-4.3", 1, 2, cached_input_tokens=1)

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)
    try:
        threads = [threading.Thread(target=hammer) for _ in range(workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old_interval)

    usage = grok_client.get_grok_session_usage()
    expected = workers * per_worker
    assert usage["input_tokens"] == expected
    assert usage["output_tokens"] == 2 * expected
    assert usage["cached_input_tokens"] == expected
    bucket = grok_client.get_grok_session_usage_by_model()["grok-4.3"]
    assert bucket["input_tokens"] == expected
    grok_client.reset_grok_session()
