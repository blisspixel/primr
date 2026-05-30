"""Coverage tests for primr.ai.async_client.

Targets the timeout/deadline path, daily-quota and timeout error branches,
retry-then-success, batch error capture, template batching, get_batch_stats,
_get_model branches, and aclose. genai is mocked; no network calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.ai.async_client import (
    AsyncAIClient,
    BatchResult,
    BatchStats,
    generate_parallel,
    get_batch_stats,
    run_parallel,
)
from primr.utils.errors import AIError


@pytest.fixture
def make_client():
    def _factory():
        with patch("primr.ai.async_client.get_settings") as mock_get:
            settings = MagicMock()
            settings.api.gemini_key = "test-key"
            settings.ai.flash_model = "flash-x"
            settings.ai.pro_model = "pro-x"
            settings.ai.max_retries = 3
            mock_get.return_value = settings
            c = AsyncAIClient(max_concurrent=2)
            return c

    return _factory


# ---------------------------------------------------------------------------
# BatchResult / BatchStats
# ---------------------------------------------------------------------------


def test_batch_result_success():
    assert BatchResult(prompt="p", response="r").success is True
    assert BatchResult(prompt="p", error=Exception()).success is False
    assert BatchResult(prompt="p").success is False


def test_batch_stats_rates():
    s = BatchStats(total=4, succeeded=2, total_duration_ms=400.0)
    assert s.success_rate == 50.0
    assert s.avg_duration_ms == 100.0


def test_batch_stats_zero_total():
    s = BatchStats()
    assert s.success_rate == 0.0
    assert s.avg_duration_ms == 0.0


def test_get_batch_stats():
    results = [
        BatchResult(prompt="a", response="ok", duration_ms=10),
        BatchResult(prompt="b", error=Exception("x"), duration_ms=20),
    ]
    stats = get_batch_stats(results)
    assert stats.total == 2
    assert stats.succeeded == 1
    assert stats.failed == 1
    assert stats.total_duration_ms == 30


# ---------------------------------------------------------------------------
# _get_model
# ---------------------------------------------------------------------------


def test_get_model_branches(make_client):
    c = make_client()
    assert c._get_model("scraping") == "flash-x"
    assert c._get_model("analysis") == "pro-x"
    assert c._get_model("unknown") == "flash-x"


# ---------------------------------------------------------------------------
# generate success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_success(make_client):
    c = make_client()
    fake = MagicMock()
    fake.models.generate_content.return_value = SimpleNamespace(text="hello")
    c._client = fake
    out = await c.generate("hi")
    assert out == "hello"


@pytest.mark.asyncio
async def test_generate_daily_quota_raises(make_client):
    c = make_client()
    fake = MagicMock()
    fake.models.generate_content.side_effect = Exception("quota")
    c._client = fake
    with (
        patch("primr.ai.async_client.is_daily_quota_exhausted", return_value=True),
        pytest.raises(AIError, match="Daily API quota exhausted"),
    ):
        await c.generate("hi")


@pytest.mark.asyncio
async def test_generate_timeout_error_raises(make_client):
    c = make_client()
    fake = MagicMock()
    fake.models.generate_content.side_effect = Exception("timed out")
    c._client = fake
    with (
        patch("primr.ai.async_client.is_daily_quota_exhausted", return_value=False),
        patch("primr.ai.async_client.is_timeout_error", return_value=True),
        pytest.raises(AIError),
    ):
        await c.generate("hi")


@pytest.mark.asyncio
async def test_generate_retries_then_succeeds(make_client):
    c = make_client()
    fake = MagicMock()
    fake.models.generate_content.side_effect = [
        Exception("503 transient"),
        SimpleNamespace(text="recovered"),
    ]
    c._client = fake
    with (
        patch("primr.ai.async_client.is_daily_quota_exhausted", return_value=False),
        patch("primr.ai.async_client.is_timeout_error", return_value=False),
        patch("primr.ai.async_client.is_rate_limit_error", return_value=True),
        patch("primr.ai.async_client.calculate_retry_delay", return_value=0),
        patch("primr.ai.async_client.asyncio.sleep", new=AsyncMock()),
    ):
        out = await c.generate("hi", max_retries=2)
    assert out == "recovered"


@pytest.mark.asyncio
async def test_generate_exhausts_retries(make_client):
    c = make_client()
    fake = MagicMock()
    fake.models.generate_content.side_effect = Exception("persistent")
    c._client = fake
    with (
        patch("primr.ai.async_client.is_daily_quota_exhausted", return_value=False),
        patch("primr.ai.async_client.is_timeout_error", return_value=False),
        patch("primr.ai.async_client.is_rate_limit_error", return_value=False),
        patch("primr.ai.async_client.calculate_retry_delay", return_value=0),
        patch("primr.ai.async_client.asyncio.sleep", new=AsyncMock()),
        pytest.raises(AIError, match="failed after"),
    ):
        await c.generate("hi", max_retries=2)


@pytest.mark.asyncio
async def test_generate_timeout_deadline(make_client):
    c = make_client()
    fake = MagicMock()
    # generate_content blocks; wait_for should raise TimeoutError.
    fake.models.generate_content.return_value = SimpleNamespace(text="late")
    c._client = fake

    async def _slow_wait_for(coro, timeout):
        # Drain the awaitable to avoid "never awaited" warnings, then time out.
        if hasattr(coro, "__await__"):
            try:
                coro.close()
            except Exception:
                pass
        raise TimeoutError("boom")

    with (
        patch("primr.ai.async_client.is_daily_quota_exhausted", return_value=False),
        patch("primr.ai.async_client.is_timeout_error", return_value=True),
        patch("primr.ai.async_client.asyncio.wait_for", new=_slow_wait_for),
        pytest.raises(AIError),
    ):
        await c.generate("hi", timeout=5.0, max_retries=1)


# ---------------------------------------------------------------------------
# generate_fast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_fast(make_client):
    c = make_client()
    captured = {}

    async def _gen(prompt, **kwargs):
        captured.update(kwargs)
        return "ok"

    c.generate = _gen  # type: ignore
    await c.generate_fast("hi")
    assert captured["thinking_level"] == "low"


# ---------------------------------------------------------------------------
# generate_batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_batch_mixed_results(make_client):
    c = make_client()

    async def _gen(prompt, **kwargs):
        if "fail" in prompt:
            raise RuntimeError("nope")
        return f"resp:{prompt}"

    c.generate = _gen  # type: ignore
    c._ensure_initialized = lambda: None  # type: ignore

    progress = []
    results = await c.generate_batch(
        ["good", "fail", "good2"], on_progress=lambda d, t: progress.append((d, t))
    )
    assert len(results) == 3
    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    assert len(successes) == 2
    assert len(failures) == 1
    assert progress[-1] == (3, 3)


@pytest.mark.asyncio
async def test_generate_batch_with_context(make_client):
    c = make_client()
    captured = []

    async def _batch(prompts, **kwargs):
        captured.extend(prompts)
        return [BatchResult(prompt=p, response="r") for p in prompts]

    c.generate_batch = _batch  # type: ignore
    c._ensure_initialized = lambda: None  # type: ignore
    await c.generate_batch_with_context([{"name": "Acme"}, {"name": "Beta"}], "Summarize {name}")
    assert captured == ["Summarize Acme", "Summarize Beta"]


# ---------------------------------------------------------------------------
# aclose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aclose_sync_close(make_client):
    c = make_client()
    fake = MagicMock()
    fake.aclose = None  # not callable
    closed = {"v": False}
    fake.close = lambda: closed.__setitem__("v", True)
    c._client = fake
    await c.aclose()
    assert closed["v"] is True
    assert c._client is None


@pytest.mark.asyncio
async def test_aclose_async_close(make_client):
    c = make_client()
    fake = MagicMock()
    aclosed = {"v": False}

    async def _aclose():
        aclosed["v"] = True

    fake.aclose = _aclose
    c._client = fake
    await c.aclose()
    assert aclosed["v"] is True


@pytest.mark.asyncio
async def test_aclose_no_client_noop(make_client):
    c = make_client()
    c._client = None
    await c.aclose()  # should not raise


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_parallel(monkeypatch):
    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def generate_batch(self, prompts, **kwargs):
            return [BatchResult(prompt=p, response="r") for p in prompts]

    monkeypatch.setattr("primr.ai.async_client.AsyncAIClient", _FakeClient)
    results = await generate_parallel(["a", "b"])
    assert len(results) == 2


def test_run_parallel(monkeypatch):
    async def _fake_generate_parallel(prompts, **kwargs):
        return [BatchResult(prompt=p, response="r") for p in prompts]

    monkeypatch.setattr("primr.ai.async_client.generate_parallel", _fake_generate_parallel)
    results = run_parallel(["a"])
    assert len(results) == 1
