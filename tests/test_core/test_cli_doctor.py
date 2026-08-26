"""Unit tests for primr.core.cli_doctor.

Focused tests on each of the `_check_*` helpers plus the `run_doctor`
orchestrator. These cover the API-key checker, provider/availability
report, dependency check, filesystem write probe, API connectivity,
and Gemini orphaned-resource scanner.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.ai.provider_availability import (
    AvailabilityState,
    ProviderQuotaSnapshot,
    QuotaWindow,
)
from primr.ai.provider_availability_collectors import LOCAL_OPENAI_COMPATIBLE_PROVIDER
from primr.core import cli_doctor
from primr.core.cli_doctor import (
    _check_api_connectivity,
    _check_api_keys,
    _check_dependencies,
    _check_filesystem,
    _check_gemini_resources,
    _check_provider_availability,
    _check_providers,
    _show_file_locations,
    run_doctor,
)

# ---------------------------------------------------------------------------
# _check_api_keys
# ---------------------------------------------------------------------------


class TestCheckApiKeys:
    def test_passes_with_valid_ai_prefix_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        with patch("ddgs.DDGS") as ddgs_mock:
            ddgs_mock.return_value.text.return_value = [{"title": "x"}]
            all_passed, warnings = _check_api_keys(True, 0)
        assert all_passed is True

    def test_warns_for_non_ai_prefix(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "xxx" * 10)
        monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        with patch("ddgs.DDGS") as ddgs_mock:
            ddgs_mock.return_value.text.return_value = [{"title": "x"}]
            all_passed, warnings = _check_api_keys(True, 0)
        # Non-AI prefix is a warning but still passes
        assert all_passed is True
        assert warnings >= 1

    def test_keyless_install_is_ready_without_warning(self, monkeypatch, capsys):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")

        with patch("ddgs.DDGS") as ddgs_mock:
            ddgs_mock.return_value.text.return_value = [{"title": "x"}]
            all_passed, warnings = _check_api_keys(True, 0)
        output = capsys.readouterr().out
        assert all_passed is True
        assert warnings == 0
        assert "Keyless ready" in output
        assert "primr prep" in output
        assert "primr recon" in output
        assert "Provider-backed research needs a cloud LLM key" in output

    @pytest.mark.parametrize(
        "env_name",
        ["XAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
    )
    def test_passes_with_non_gemini_cloud_provider_key(self, monkeypatch, env_name):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv(env_name, "provider-key-" + "x" * 20)
        monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")

        with patch("ddgs.DDGS") as ddgs_mock:
            ddgs_mock.return_value.text.return_value = [{"title": "x"}]
            all_passed, _ = _check_api_keys(True, 0)
        assert all_passed is True

    def test_google_search_provider_requires_keys(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "google")
        monkeypatch.delenv("SEARCH_API_KEY", raising=False)
        monkeypatch.delenv("SEARCH_ENGINE_ID", raising=False)

        all_passed, _ = _check_api_keys(True, 0)
        assert all_passed is False

    def test_google_search_api_success(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "google")
        monkeypatch.setenv("SEARCH_API_KEY", "x" * 30)
        monkeypatch.setenv("SEARCH_ENGINE_ID", "y" * 30)

        with patch("requests.get") as get_mock:
            get_mock.return_value = MagicMock(status_code=200)
            all_passed, _ = _check_api_keys(True, 0)
        assert all_passed is True

    def test_google_search_api_403_fails(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "google")
        monkeypatch.setenv("SEARCH_API_KEY", "x" * 30)
        monkeypatch.setenv("SEARCH_ENGINE_ID", "y" * 30)

        with patch("requests.get") as get_mock:
            get_mock.return_value = MagicMock(status_code=403)
            all_passed, _ = _check_api_keys(True, 0)
        assert all_passed is False

    def test_ddg_failure_marks_failed(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        with patch("ddgs.DDGS") as ddgs_mock:
            ddgs_mock.return_value.text.side_effect = RuntimeError("net down")
            all_passed, _ = _check_api_keys(True, 0)
        assert all_passed is False


# ---------------------------------------------------------------------------
# _check_providers
# ---------------------------------------------------------------------------


class TestCheckProviders:
    @staticmethod
    def _entry(name="grok", env="XAI_API_KEY", default=None):
        from types import SimpleNamespace

        return SimpleNamespace(
            name=name,
            description=f"{name} provider",
            roles=["reasoning"],
            api_key_env=env,
            api_key_default=default,
        )

    def test_no_providers_increments_warning(self):
        with patch("primr.ai.providers.KNOWN_PROVIDERS", []):
            assert _check_providers(0) == 1

    def test_usable_provider_adds_no_warning(self, monkeypatch):
        # Key set AND SDK importable -> counts as usable, no warning added.
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        usable = MagicMock()
        usable.is_available.return_value = True
        with (
            patch("primr.ai.providers.KNOWN_PROVIDERS", [self._entry()]),
            patch("primr.ai.providers.build_provider", return_value=usable),
        ):
            assert _check_providers(2) == 2

    def test_key_set_but_sdk_missing_warns(self, monkeypatch):
        # The exact trap: key configured but the provider can't be built/used.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        unusable = MagicMock()
        unusable.is_available.return_value = False
        entry = self._entry(name="anthropic", env="ANTHROPIC_API_KEY")
        with (
            patch("primr.ai.providers.KNOWN_PROVIDERS", [entry]),
            patch("primr.ai.providers.build_provider", return_value=unusable),
        ):
            # One warning for the unusable provider, plus one for zero usable.
            assert _check_providers(0) == 2

    def test_unset_provider_is_informational_not_a_warning(self, monkeypatch):
        # No key -> informational line, but still zero usable -> single error bump.
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        with patch("primr.ai.providers.KNOWN_PROVIDERS", [self._entry()]):
            assert _check_providers(0) == 1


# ---------------------------------------------------------------------------
# _check_provider_availability
# ---------------------------------------------------------------------------


class TestCheckProviderAvailability:
    def test_provider_availability_outputs_sanitized_summary(self):
        snapshots = (
            ProviderQuotaSnapshot(
                provider="openai",
                display_name="OpenAI GPT",
                ok=True,
                metadata={
                    "api_key_env": "OPENAI_API_KEY",
                    "configured": True,
                    "quota_source": "not_collected",
                },
            ),
            ProviderQuotaSnapshot(
                provider="anthropic",
                display_name="Anthropic Claude",
                ok=False,
                error="missing_api_key",
                metadata={
                    "api_key_env": "ANTHROPIC_API_KEY",
                    "configured": False,
                    "quota_source": "not_collected",
                },
            ),
            ProviderQuotaSnapshot(
                provider=LOCAL_OPENAI_COMPATIBLE_PROVIDER,
                display_name="Local OpenAI-compatible",
                ok=True,
                windows=(QuotaWindow("local_service", used_percent=0),),
                metadata={
                    "endpoint_source": "LOCAL_LLM_BASE_URL",
                    "model_names": ("custom-model-name",),
                    "model_count": 2,
                    "quota_source": "local_probe",
                },
            ),
        )
        console = MagicMock()

        with (
            patch(
                "primr.core.cli_doctor.collect_provider_availability_snapshots",
                return_value=snapshots,
            ),
            patch("primr.core.cli_doctor.console", console),
        ):
            assert _check_provider_availability(3) == 3

        output = str(console.mock_calls)
        assert "OpenAI GPT: configured" in output
        assert "Anthropic Claude: not configured" in output
        assert "Local OpenAI-compatible: available" in output
        assert "ANTHROPIC_API_KEY" in output
        assert "custom-model-name" not in output
        assert "operator-host" not in output
        console.warn.assert_not_called()

    def test_configured_unavailable_provider_warns_without_raw_endpoint(self):
        snapshots = (
            ProviderQuotaSnapshot(
                provider="xai",
                display_name="xAI Grok",
                ok=False,
                error="cannot reach http://operator-host.example.invalid:9999/quota",
                metadata={
                    "configured": True,
                    "quota_source": "http://operator-host.example.invalid:9999/quota",
                },
            ),
        )
        console = MagicMock()

        with (
            patch(
                "primr.core.cli_doctor.collect_provider_availability_snapshots",
                return_value=snapshots,
            ),
            patch("primr.core.cli_doctor.console", console),
        ):
            assert _check_provider_availability(0) == 1

        output = str(console.mock_calls)
        assert "availability_error" in output
        assert "operator-host" not in output
        console.warn.assert_called_once()

    def test_busy_local_capacity_warns_with_bounded_retry_guidance(self):
        snapshots = (
            ProviderQuotaSnapshot(
                provider=LOCAL_OPENAI_COMPATIBLE_PROVIDER,
                display_name="Local OpenAI-compatible",
                ok=False,
                error="local_openai_compatible_busy",
                state=AvailabilityState.BUSY,
                retry_after_seconds=1_800,
                metadata={
                    "endpoint_source": "LOCAL_LLM_BASE_URL",
                    "model_count": 1,
                    "quota_source": "local_probe",
                },
            ),
        )
        console = MagicMock()

        with (
            patch(
                "primr.core.cli_doctor.collect_provider_availability_snapshots",
                return_value=snapshots,
            ),
            patch("primr.core.cli_doctor.console", console),
        ):
            assert _check_provider_availability(0) == 1

        output = str(console.mock_calls)
        assert "busy" in output
        assert "retry after 1800s" in output
        console.warn.assert_called_once()

    def test_collector_failure_warns_with_safe_error(self):
        console = MagicMock()

        with (
            patch(
                "primr.core.cli_doctor.collect_provider_availability_snapshots",
                side_effect=RuntimeError("failed at http://operator-host.example.invalid:9999"),
            ),
            patch("primr.core.cli_doctor.console", console),
        ):
            assert _check_provider_availability(2) == 3

        output = str(console.mock_calls)
        assert "availability_error" in output
        assert "operator-host" not in output

    def test_malformed_snapshot_metadata_does_not_crash_or_leak(self):
        snapshots = (
            ProviderQuotaSnapshot(
                provider=LOCAL_OPENAI_COMPATIBLE_PROVIDER,
                display_name="operator-host.example.invalid",
                ok=True,
                windows=(QuotaWindow("local_service", used_percent=0),),
                metadata={
                    "endpoint_source": "http://operator-host.example.invalid:9999/v1",
                    "model_count": "not-a-number",
                    "quota_source": "local_probe",
                },
            ),
            ProviderQuotaSnapshot(
                provider="anthropic",
                display_name="operator-host.example.invalid",
                ok=False,
                error="missing_api_key",
                metadata={
                    "api_key_env": "http://operator-host.example.invalid/key",
                    "configured": False,
                    "quota_source": "not_collected",
                },
            ),
        )
        console = MagicMock()

        with (
            patch(
                "primr.core.cli_doctor.collect_provider_availability_snapshots",
                return_value=snapshots,
            ),
            patch("primr.core.cli_doctor.console", console),
        ):
            assert _check_provider_availability(0) == 0

        output = str(console.mock_calls)
        assert "local_openai_compatible: available (0 local model(s), $0 API runtime)" in output
        assert "anthropic: not configured (provider key unset)" in output
        assert "operator-host" not in output
        console.warn.assert_not_called()


# ---------------------------------------------------------------------------
# _check_dependencies
# ---------------------------------------------------------------------------


class TestCheckDependencies:
    def test_playwright_available(self):
        with patch("playwright.sync_api.sync_playwright") as pw_mock:
            pw_mock.return_value.__enter__.return_value = MagicMock()
            pw_mock.return_value.__exit__.return_value = None
            assert _check_dependencies(0) == 0

    def test_playwright_failure_increments_warning(self):
        with patch(
            "playwright.sync_api.sync_playwright",
            side_effect=ImportError("no playwright"),
        ):
            assert _check_dependencies(0) == 1


# ---------------------------------------------------------------------------
# _check_filesystem
# ---------------------------------------------------------------------------


class TestCheckFilesystem:
    def test_writes_succeed_for_writable_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_doctor, "OUTPUT_DIR", str(tmp_path / "out"))
        monkeypatch.setattr(cli_doctor, "WORKING_DIR", str(tmp_path / "work"))
        monkeypatch.setattr(cli_doctor, "LOGS_DIR", str(tmp_path / "logs"))
        all_passed, warnings = _check_filesystem(True, 0)
        assert all_passed is True

    def test_output_write_failure(self, monkeypatch):
        monkeypatch.setattr(cli_doctor, "OUTPUT_DIR", "C:/nonexistent/forbidden/dir")
        monkeypatch.setattr(cli_doctor, "WORKING_DIR", "C:/nonexistent/forbidden/dir2")
        monkeypatch.setattr(cli_doctor, "LOGS_DIR", "C:/nonexistent/forbidden/dir3")
        # Force os.makedirs to fail
        with patch("os.makedirs", side_effect=PermissionError("denied")):
            all_passed, _ = _check_filesystem(True, 0)
        assert all_passed is False


class TestFileLocations:
    def test_shows_user_data_and_research_memory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRIMR_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("PRIMR_DATA_DIR", str(tmp_path / "data"))
        console = MagicMock()
        monkeypatch.setattr(cli_doctor, "console", console)

        _show_file_locations()

        lines = [call.args[0] for call in console.info.call_args_list]
        joined = "\n".join(lines)
        assert "User data (durable):" in joined
        assert "Research memory:" in joined
        assert str(tmp_path / "data" / "research_memory") in joined


# ---------------------------------------------------------------------------
# _check_api_connectivity
# ---------------------------------------------------------------------------


class TestCheckApiConnectivity:
    def test_no_key_is_zero_spend_and_does_not_add_warning(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        all_passed, warnings = _check_api_connectivity(True, 0)
        assert all_passed is True
        assert warnings == 0

    def test_configured_key_never_creates_client_or_generates(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x" * 30)
        fake_module = MagicMock()
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake_module)}),
            patch("google.genai", fake_module, create=True),
        ):
            all_passed, warnings = _check_api_connectivity(True, 0)
        assert all_passed is True
        assert warnings == 0
        fake_module.Client.assert_not_called()


# ---------------------------------------------------------------------------
# _check_gemini_resources
# ---------------------------------------------------------------------------


class TestCheckGeminiResources:
    def test_no_key_skips_without_warning(self, monkeypatch, capsys):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        all_passed, warnings = _check_gemini_resources(True, 0)
        assert all_passed is True
        assert warnings == 0
        assert "Skipping Gemini resource check" in capsys.readouterr().out

    def test_no_orphans(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x" * 30)
        fake_module = MagicMock()
        client = MagicMock()
        client.caches.list.return_value = []
        client.file_search_stores.list.return_value = []
        fake_module.Client.return_value = client
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake_module)}),
            patch("google.genai", fake_module, create=True),
        ):
            all_passed, warnings = _check_gemini_resources(True, 0)
        assert warnings == 0

    def test_orphaned_caches_warn(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x" * 30)
        fake_module = MagicMock()
        client = MagicMock()
        client.caches.list.return_value = [MagicMock()]
        client.file_search_stores.list.return_value = []
        fake_module.Client.return_value = client
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake_module)}),
            patch("google.genai", fake_module, create=True),
        ):
            all_passed, warnings = _check_gemini_resources(True, 0)
        assert warnings == 1

    def test_orphaned_stores_warn(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x" * 30)
        fake_module = MagicMock()
        client = MagicMock()
        client.caches.list.return_value = []
        client.file_search_stores.list.return_value = [MagicMock(), MagicMock()]
        fake_module.Client.return_value = client
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake_module)}),
            patch("google.genai", fake_module, create=True),
        ):
            all_passed, warnings = _check_gemini_resources(True, 0)
        assert warnings == 1

    def test_cache_inventory_failure_is_visible(self, monkeypatch, capsys):
        monkeypatch.setenv("GEMINI_API_KEY", "x" * 30)
        fake_module = MagicMock()
        client = MagicMock()
        client.caches.list.side_effect = RuntimeError("inventory unavailable")
        client.file_search_stores.list.return_value = []
        fake_module.Client.return_value = client
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake_module)}),
            patch("google.genai", fake_module, create=True),
        ):
            all_passed, warnings = _check_gemini_resources(True, 0)

        assert all_passed is True
        assert warnings == 1
        assert "cache inventory could not be verified" in capsys.readouterr().out

    def test_store_inventory_failure_is_visible(self, monkeypatch, capsys):
        monkeypatch.setenv("GEMINI_API_KEY", "x" * 30)
        fake_module = MagicMock()
        client = MagicMock()
        client.caches.list.return_value = []
        client.file_search_stores.list.side_effect = RuntimeError("inventory unavailable")
        fake_module.Client.return_value = client
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake_module)}),
            patch("google.genai", fake_module, create=True),
        ):
            all_passed, warnings = _check_gemini_resources(True, 0)

        assert all_passed is True
        assert warnings == 1
        assert "store inventory could not be verified" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# run_doctor (orchestration)
# ---------------------------------------------------------------------------


class TestRunDoctor:
    def _stub_all_checks(self, monkeypatch, *, all_passed=True, warnings=0):
        for name in (
            "_check_api_keys",
            "_check_filesystem",
            "_check_api_connectivity",
            "_check_gemini_resources",
        ):
            monkeypatch.setattr(cli_doctor, name, lambda ap, wc: (ap and all_passed, wc + warnings))
        monkeypatch.setattr(cli_doctor, "_check_providers", lambda wc: wc + warnings)
        monkeypatch.setattr(
            cli_doctor,
            "_check_provider_availability",
            lambda wc: wc + warnings,
        )
        monkeypatch.setattr(cli_doctor, "_check_dependencies", lambda wc: wc + warnings)
        monkeypatch.setattr(cli_doctor, "_check_key_shadowing", lambda wc: wc + warnings)

    def test_all_pass_returns_zero(self, monkeypatch):
        self._stub_all_checks(monkeypatch, all_passed=True, warnings=0)
        assert run_doctor(fix=False) == 0

    def test_python_311_returns_one(self, monkeypatch):
        self._stub_all_checks(monkeypatch, all_passed=True, warnings=0)

        class _VI(tuple):
            major = 3
            minor = 11
            micro = 9

        monkeypatch.setattr("sys.version_info", _VI((3, 11, 9, "final", 0)))

        assert run_doctor(fix=False) == 1

    def test_failures_return_one(self, monkeypatch):
        self._stub_all_checks(monkeypatch, all_passed=False, warnings=0)
        assert run_doctor(fix=False) == 1

    def test_warnings_only_returns_zero(self, monkeypatch):
        self._stub_all_checks(monkeypatch, all_passed=True, warnings=1)
        assert run_doctor(fix=False) == 0

    def test_fix_mode_dispatches_to_init_flow(self, monkeypatch):
        self._stub_all_checks(monkeypatch, all_passed=False, warnings=0)
        monkeypatch.setattr(cli_doctor, "can_prompt_for_input", lambda: False)
        with patch("primr.core.cli_init._run_init_flow", return_value=99) as init_mock:
            result = run_doctor(fix=True)
        init_mock.assert_called_once_with(
            non_interactive=True,
            assume_yes=False,
            skip_browsers=False,
            run_doctor_after=True,
            doctor_runner=run_doctor,
        )
        assert result == 99

    def test_fix_mode_with_clean_state_returns_zero(self, monkeypatch):
        self._stub_all_checks(monkeypatch, all_passed=True, warnings=0)
        with patch("primr.core.cli_init._run_init_flow") as init_mock:
            result = run_doctor(fix=True)
        init_mock.assert_not_called()
        assert result == 0


class TestCheckApiKeysEdgeCases:
    def test_google_search_api_400_fails(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "google")
        monkeypatch.setenv("SEARCH_API_KEY", "x" * 30)
        monkeypatch.setenv("SEARCH_ENGINE_ID", "y" * 30)
        with patch("requests.get") as get_mock:
            response = MagicMock(status_code=400)
            response.json.return_value = {"error": {"message": "bad request"}}
            get_mock.return_value = response
            all_passed, _ = _check_api_keys(True, 0)
        assert all_passed is False

    def test_google_search_api_500_fails(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "google")
        monkeypatch.setenv("SEARCH_API_KEY", "x" * 30)
        monkeypatch.setenv("SEARCH_ENGINE_ID", "y" * 30)
        with patch("requests.get") as get_mock:
            get_mock.return_value = MagicMock(status_code=500)
            all_passed, _ = _check_api_keys(True, 0)
        assert all_passed is False

    def test_google_search_api_timeout(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "google")
        monkeypatch.setenv("SEARCH_API_KEY", "x" * 30)
        monkeypatch.setenv("SEARCH_ENGINE_ID", "y" * 30)
        import requests as real_requests

        with patch(
            "requests.get",
            side_effect=real_requests.exceptions.Timeout("timed out"),
        ):
            all_passed, _ = _check_api_keys(True, 0)
        assert all_passed is False

    def test_google_search_missing_engine_id_fails(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "google")
        monkeypatch.setenv("SEARCH_API_KEY", "x" * 30)
        monkeypatch.delenv("SEARCH_ENGINE_ID", raising=False)
        all_passed, _ = _check_api_keys(True, 0)
        assert all_passed is False

    def test_ddg_empty_results_warns(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
        with patch("ddgs.DDGS") as ddgs_mock:
            ddgs_mock.return_value.text.return_value = []
            all_passed, warnings = _check_api_keys(True, 0)
        assert all_passed is True
        assert warnings >= 1

    def test_xai_key_configured(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("XAI_API_KEY", "y" * 30)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
        with patch("ddgs.DDGS") as ddgs_mock:
            ddgs_mock.return_value.text.return_value = [{"title": "x"}]
            all_passed, _ = _check_api_keys(True, 0)
        assert all_passed is True


@pytest.mark.parametrize("warnings", [0, 1, 5])
def test_check_api_keys_preserves_warnings_count(monkeypatch, warnings):
    monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
    monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with patch("ddgs.DDGS") as ddgs_mock:
        ddgs_mock.return_value.text.return_value = [{"title": "x"}]
        _, result_warnings = _check_api_keys(True, warnings)
    # warnings should only stay the same or increase
    assert result_warnings >= warnings
