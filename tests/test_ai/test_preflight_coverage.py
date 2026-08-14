"""Coverage tests for primr.ai.preflight.

Exercises PreflightResult.summary formatting and the individual mode-aware
check helpers (API keys, YAML config, models, website, output dir) with all
external dependencies mocked. No network or real API calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.preflight import PreflightResult, PreflightValidator, run_preflight

# ---------------------------------------------------------------------------
# PreflightResult.summary
# ---------------------------------------------------------------------------


def test_summary_success():
    r = PreflightResult(success=True, estimated_duration="10m", estimated_cost="$1")
    out = r.summary()
    assert "passed" in out
    assert "10m" in out
    assert "$1" in out


def test_summary_failure_lists_errors():
    r = PreflightResult(success=False, errors=["no key"], warnings=["slow site"])
    out = r.summary()
    assert "FAILED" in out
    assert "no key" in out
    assert "slow site" in out


def test_summary_verbose_includes_checks():
    r = PreflightResult(
        success=True,
        checks={
            "gemini": {"passed": True, "status": "ok", "detail": "model X"},
            "site": {"passed": False, "status": "bad"},
        },
    )
    out = r.summary(verbose=True)
    assert "Check details" in out
    assert "gemini" in out
    assert "model X" in out
    assert "site" in out


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def validator():
    with patch("primr.ai.preflight.get_settings") as mock_get:
        settings = MagicMock()
        settings.api.gemini_key = "test-key"
        mock_get.return_value = settings
        v = PreflightValidator()
        v._settings = settings
        return v


def _noop(msg: str) -> None:
    pass


# ---------------------------------------------------------------------------
# _check_api_keys
# ---------------------------------------------------------------------------


def test_check_api_keys_missing_gemini(validator):
    validator._settings.api.gemini_key = ""
    errors, warnings, checks = [], [], {}
    validator._check_api_keys("scrape", errors, warnings, checks, _noop)
    assert any("GEMINI_API_KEY" in e for e in errors)
    assert checks["gemini_api_key"]["passed"] is False


def test_check_api_keys_duckduckgo_default(validator, monkeypatch):
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    errors, warnings, checks = [], [], {}
    validator._check_api_keys("scrape", errors, warnings, checks, _noop)
    assert checks["search_provider"]["passed"] is True
    assert not errors


def test_check_api_keys_google_missing_keys(validator, monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "google")
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_ENGINE_ID", raising=False)
    validator._settings.api.search_key = None
    validator._settings.api.search_engine_id = None
    errors, warnings, checks = [], [], {}
    validator._check_api_keys("full", errors, warnings, checks, _noop)
    assert any("SEARCH_API_KEY" in e for e in errors)
    assert any("SEARCH_ENGINE_ID" in e for e in errors)


def test_check_api_keys_google_present(validator, monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "google")
    validator._settings.api.search_key = "k"
    validator._settings.api.search_engine_id = "e"
    errors, warnings, checks = [], [], {}
    validator._check_api_keys("full", errors, warnings, checks, _noop)
    assert checks["search_api_key"]["passed"] is True
    assert checks["search_engine_id"]["passed"] is True
    assert not errors


def test_check_api_keys_deep_mode_skips_search(validator):
    errors, warnings, checks = [], [], {}
    validator._check_api_keys("deep", errors, warnings, checks, _noop)
    # deep mode doesn't check search
    assert "search_provider" not in checks


# ---------------------------------------------------------------------------
# _check_yaml_config
# ---------------------------------------------------------------------------


def test_check_yaml_config_success(validator):
    fake_config = SimpleNamespace(
        sections=list(range(21)),
        raw_config={
            "accordion_method": {
                "research_dossier_prompt": "x",
                "section_writing_prompt": "y",
            }
        },
    )
    fake_composer = MagicMock()
    fake_composer._load_config.return_value = fake_config
    with patch("primr.prompts.composer.PromptComposer", return_value=fake_composer):
        errors, warnings, checks = [], [], {}
        validator._check_yaml_config(errors, warnings, checks, _noop)
    assert checks["yaml_config"]["passed"] is True
    assert not errors


def test_check_yaml_config_missing_prompts_and_few_sections(validator):
    fake_config = SimpleNamespace(
        sections=[1, 2],
        raw_config={"accordion_method": {}},
    )
    fake_composer = MagicMock()
    fake_composer._load_config.return_value = fake_config
    with patch("primr.prompts.composer.PromptComposer", return_value=fake_composer):
        errors, warnings, checks = [], [], {}
        validator._check_yaml_config(errors, warnings, checks, _noop)
    assert any("research_dossier_prompt" in e for e in errors)
    assert any("section_writing_prompt" in e for e in errors)
    assert any("sections" in w for w in warnings)


def test_check_yaml_config_exception(validator):
    with patch("primr.prompts.composer.PromptComposer", side_effect=RuntimeError("boom")):
        errors, warnings, checks = [], [], {}
        validator._check_yaml_config(errors, warnings, checks, _noop)
    assert any("YAML configuration error" in e for e in errors)
    assert checks["yaml_config"]["passed"] is False


# ---------------------------------------------------------------------------
# _check_models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_models_no_key_returns_early(validator):
    validator._settings.api.gemini_key = ""
    errors, warnings, checks = [], [], {}
    await validator._check_models("full", errors, warnings, checks, _noop)
    assert checks == {}


@pytest.mark.asyncio
async def test_check_models_missing_google_sdk_reports_error(validator):
    def fake_import(name, *args, **kwargs):
        if name == "google":
            raise ImportError("no google SDK")
        return real_import(name, *args, **kwargs)

    real_import = __import__
    errors, warnings, checks = [], [], {}
    with patch("builtins.__import__", side_effect=fake_import):
        await validator._check_models("full", errors, warnings, checks, _noop)

    assert any("google-genai package not installed" in e for e in errors)
    assert checks["gemini_sdk"]["passed"] is False


@pytest.mark.asyncio
async def test_check_models_flash_success_deep_research_success(validator):
    fake_client = MagicMock()
    fake_client.models.get.return_value = SimpleNamespace(name="gemini")
    fake_client.interactions.create.return_value = SimpleNamespace(id="abc123def456ghi789")
    with patch("google.genai.Client", return_value=fake_client):
        errors, warnings, checks = [], [], {}
        await validator._check_models("full", errors, warnings, checks, _noop)
    assert checks["gemini_flash"]["passed"] is True
    assert checks["deep_research"]["passed"] is True
    assert not errors
    fake_client.models.generate_content.assert_not_called()


@pytest.mark.asyncio
async def test_check_models_flash_not_found(validator):
    fake_client = MagicMock()
    fake_client.models.get.side_effect = Exception("model not found")
    with patch("google.genai.Client", return_value=fake_client):
        errors, warnings, checks = [], [], {}
        await validator._check_models("scrape", errors, warnings, checks, _noop)
    assert any("not available" in e for e in errors)


@pytest.mark.asyncio
async def test_check_models_flash_quota(validator):
    fake_client = MagicMock()
    fake_client.models.get.side_effect = Exception("429 quota")
    with patch("google.genai.Client", return_value=fake_client):
        errors, warnings, checks = [], [], {}
        await validator._check_models("scrape", errors, warnings, checks, _noop)
    assert any("quota exhausted" in e for e in errors)


@pytest.mark.asyncio
async def test_check_models_flash_api_key_invalid(validator):
    fake_client = MagicMock()
    fake_client.models.get.side_effect = Exception("invalid api key")
    with patch("google.genai.Client", return_value=fake_client):
        errors, warnings, checks = [], [], {}
        await validator._check_models("scrape", errors, warnings, checks, _noop)
    assert any("invalid" in e.lower() for e in errors)


@pytest.mark.asyncio
async def test_check_models_deep_research_does_not_launch_probe(validator):
    fake_client = MagicMock()
    with patch("google.genai.Client", return_value=fake_client):
        errors, warnings, checks = [], [], {}
        await validator._check_models("deep", errors, warnings, checks, _noop)
    assert errors == []
    assert warnings == []
    assert checks["deep_research"]["status"] == "configured"
    fake_client.interactions.create.assert_not_called()


# ---------------------------------------------------------------------------
# _check_website
# ---------------------------------------------------------------------------


class _AsyncCM:
    def __init__(self, client):
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, *a):
        return False


@pytest.mark.asyncio
async def test_check_website_reachable(validator):
    with (
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.data.safe_http.async_safe_http_head",
            return_value=(200, "https://example.com", False),
        ),
    ):
        errors, warnings, checks = [], [], {}
        await validator._check_website("example.com", errors, warnings, checks, _noop)
    assert checks["website"]["passed"] is True
    assert not errors


@pytest.mark.asyncio
async def test_check_website_unsafe_redirect(validator):
    with (
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.data.safe_http.async_safe_http_head",
            return_value=(None, None, True),
        ),
    ):
        errors, warnings, checks = [], [], {}
        await validator._check_website("https://example.com", errors, warnings, checks, _noop)
    assert any("unsafe URL" in e for e in errors)
    assert checks["website"]["status"] == "unsafe_redirect"


@pytest.mark.asyncio
async def test_check_website_blocks_unsafe_initial_url_without_network(validator):
    with (
        patch(
            "primr.utils.security.is_safe_url",
            return_value=(False, "Private/reserved IP addresses are blocked"),
        ),
        patch("primr.data.safe_http.async_safe_http_head") as safe_head,
    ):
        errors, warnings, checks = [], [], {}
        await validator._check_website("http://127.0.0.1/admin", errors, warnings, checks, _noop)

    assert any("unsafe" in e.lower() for e in errors)
    assert checks["website"]["status"] == "unsafe_url"
    assert not warnings
    safe_head.assert_not_called()


@pytest.mark.asyncio
async def test_check_website_dns_failure_stays_reachability_warning(validator):
    with (
        patch("primr.utils.security.is_safe_url", return_value=(False, "DNS resolution failed")),
        patch("primr.data.safe_http.async_safe_http_head") as safe_head,
    ):
        errors, warnings, checks = [], [], {}
        await validator._check_website("https://missing.example", errors, warnings, checks, _noop)

    assert not errors
    assert any("Could not reach website" in w for w in warnings)
    assert checks["website"]["status"] == "unreachable"
    safe_head.assert_not_called()


@pytest.mark.asyncio
async def test_check_website_http_error_status_warns(validator):
    with (
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.data.safe_http.async_safe_http_head",
            return_value=(503, "https://example.com", False),
        ),
    ):
        errors, warnings, checks = [], [], {}
        await validator._check_website("https://example.com", errors, warnings, checks, _noop)
    assert any("HTTP 503" in w for w in warnings)


@pytest.mark.asyncio
async def test_check_website_unreachable(validator):
    with (
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.data.safe_http.async_safe_http_head",
            side_effect=RuntimeError("dns fail"),
        ),
    ):
        errors, warnings, checks = [], [], {}
        await validator._check_website("https://example.com", errors, warnings, checks, _noop)
    assert any("Could not reach website" in w for w in warnings)
    assert checks["website"]["status"] == "unreachable"


# ---------------------------------------------------------------------------
# _check_output_dir
# ---------------------------------------------------------------------------


def test_check_output_dir_writable(validator, tmp_path):
    with patch("primr.config.config.OUTPUT_DIR", str(tmp_path)):
        errors, warnings, checks = [], [], {}
        validator._check_output_dir(errors, warnings, checks, _noop)
    assert checks["output_dir"]["passed"] is True
    assert not errors


def test_check_output_dir_not_writable(validator):
    with patch("os.makedirs", side_effect=PermissionError("denied")):
        errors, warnings, checks = [], [], {}
        validator._check_output_dir(errors, warnings, checks, _noop)
    assert any("not writable" in e for e in errors)
    assert checks["output_dir"]["passed"] is False


# ---------------------------------------------------------------------------
# validate() orchestration + run_preflight convenience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_orchestration_scrape_mode(validator):
    progress_msgs = []

    async def _ok_models(*a, **k):
        return None

    async def _ok_playwright(*a, **k):
        return None

    with (
        patch.object(validator, "_check_api_keys"),
        patch.object(validator, "_check_yaml_config"),
        patch.object(validator, "_check_models", side_effect=_ok_models),
        patch.object(validator, "_check_playwright", side_effect=_ok_playwright),
        patch.object(validator, "_check_output_dir"),
    ):
        result = await validator.validate(mode="scrape", on_progress=progress_msgs.append)
    assert result.success is True
    assert "dry-run" in result.estimated_duration
    assert any("passed" in m for m in progress_msgs)


@pytest.mark.asyncio
async def test_validate_reports_errors(validator):
    async def _models_err(mode, errors, warnings, checks, progress):
        errors.append("boom")

    with (
        patch.object(validator, "_check_api_keys"),
        patch.object(validator, "_check_yaml_config"),
        patch.object(validator, "_check_models", side_effect=_models_err),
        patch.object(validator, "_check_output_dir"),
    ):
        result = await validator.validate(mode="deep")
    assert result.success is False
    assert "boom" in result.errors


@pytest.mark.asyncio
async def test_run_preflight_convenience(monkeypatch, capsys):
    async def _fake_validate(self, mode, website_url, on_progress):
        if on_progress:
            on_progress("hello")
        return PreflightResult(success=True)

    monkeypatch.setattr(PreflightValidator, "validate", _fake_validate)
    with patch("primr.ai.preflight.get_settings"):
        result = await run_preflight(mode="deep", verbose=True)
    assert result.success is True
    captured = capsys.readouterr()
    assert "hello" in captured.out
