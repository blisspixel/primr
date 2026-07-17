"""Execution-time local capacity behavior for the lightweight chat client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from primr.ai.openai_compatible_client import chat_completion
from primr.ai.provider_availability import LocalCapacityBusyError


def test_chat_completion_raises_structured_busy_error_after_short_retries() -> None:
    error = RuntimeError("capacity response from private endpoint")
    error.status_code = 503  # type: ignore[attr-defined]
    client = MagicMock()
    client.chat.completions.create.side_effect = error
    fake_openai = SimpleNamespace(
        DefaultHttpxClient=MagicMock(return_value=MagicMock()),
        OpenAI=MagicMock(return_value=client),
    )

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
    assert fake_openai.OpenAI.call_args.kwargs["max_retries"] == 0
    fake_openai.DefaultHttpxClient.assert_called_once_with(follow_redirects=False)
    sleep_mock.assert_called_once()
    assert sleep_mock.call_args.args[0] <= 24.0
    assert caught.value.retry_after_seconds == 7_200
    assert caught.value.as_metadata()["state"] == "busy"
    assert "private endpoint" not in str(caught.value)


def test_chat_completion_retry_budget_is_not_multiplied_by_sdk_retries() -> None:
    openai = pytest.importorskip("openai")
    openai_client = openai.OpenAI
    request_count = 0

    def fail_with_service_unavailable(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})

    with (
        httpx.Client(
            transport=httpx.MockTransport(fail_with_service_unavailable),
            follow_redirects=False,
        ) as http_client,
        patch.object(openai, "OpenAI", wraps=openai_client),
        patch.object(openai, "DefaultHttpxClient", return_value=http_client),
        patch("primr.ai.openai_compatible_client.time.sleep"),
        pytest.raises(LocalCapacityBusyError),
    ):
        chat_completion(
            "Summarize this evidence",
            model="local-model",
            base_url="https://example.test/v1",
            retries=1,
        )

    assert request_count == 2
