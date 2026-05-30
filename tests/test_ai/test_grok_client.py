from types import SimpleNamespace

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
