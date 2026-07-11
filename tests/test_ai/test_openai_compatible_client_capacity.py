"""Execution-time local capacity behavior for the lightweight chat client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.openai_compatible_client import chat_completion
from primr.ai.provider_availability import LocalCapacityBusyError


def test_chat_completion_raises_structured_busy_error_after_short_retries() -> None:
    error = RuntimeError("capacity response from private endpoint")
    error.status_code = 503  # type: ignore[attr-defined]
    client = MagicMock()
    client.chat.completions.create.side_effect = error
    fake_openai = SimpleNamespace(OpenAI=MagicMock(return_value=client))

    with (
        patch.dict("sys.modules", {"openai": fake_openai}),
        patch("primr.ai.openai_compatible_client.time.sleep") as sleep_mock,
        pytest.raises(LocalCapacityBusyError) as caught,
    ):
        chat_completion(
            "Summarize this evidence",
            model="local-model",
            retries=1,
            capacity_retry_attempt=1,
        )

    assert client.chat.completions.create.call_count == 2
    sleep_mock.assert_called_once()
    assert sleep_mock.call_args.args[0] <= 24.0
    assert caught.value.retry_after_seconds == 7_200
    assert caught.value.as_metadata()["state"] == "busy"
    assert "private endpoint" not in str(caught.value)
