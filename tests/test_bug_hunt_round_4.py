"""Regression tests for bug-hunt round 4 (hardening).

Each class pins a defect so it cannot silently return.
"""

from __future__ import annotations

from primr.config.env import env_float, env_int
from primr.mcp_server.security import URLValidator
from primr.utils.security import is_safe_url, mask_sensitive_data


class TestMcpSsrfUsesSharedGuard:
    def test_ipv4_mapped_loopback_blocked(self) -> None:
        result = URLValidator().validate("http://[::ffff:127.0.0.1]/")
        assert result.valid is False
        assert result.error_type == "ssrf_blocked"

    def test_example_https_still_allowed(self) -> None:
        result = URLValidator().validate("https://example.com")
        assert result.valid is True

    def test_nat64_embedded_loopback_blocked(self) -> None:
        ok, _reason = is_safe_url("http://[64:ff9b::7f00:1]/")
        assert ok is False
        result = URLValidator().validate("http://[64:ff9b::a9fe:a9fe]/latest/meta-data/")
        assert result.valid is False
        assert result.error_type == "ssrf_blocked"


class TestAnthropicKeyRedactionLabel:
    def test_anthropic_key_not_labelled_openai(self) -> None:
        key = "sk-ant-" + "A" * 40
        masked = mask_sensitive_data(f"leaked {key}")
        assert key not in masked
        assert "[ANTHROPIC_API_KEY]" in masked
        assert "[OPENAI_API_KEY]" not in masked


class TestEnvParseFallback:
    def test_garbage_int_falls_back(self, monkeypatch) -> None:
        monkeypatch.setenv("MAX_EXTERNAL_SEARCH_QUERIES", "not-a-number")
        assert env_int("MAX_EXTERNAL_SEARCH_QUERIES", 5) == 5

    def test_empty_int_falls_back(self, monkeypatch) -> None:
        monkeypatch.setenv("MAX_EXTERNAL_SEARCH_QUERIES", "  ")
        assert env_int("MAX_EXTERNAL_SEARCH_QUERIES", 5) == 5

    def test_valid_int(self, monkeypatch) -> None:
        monkeypatch.setenv("MAX_EXTERNAL_SEARCH_QUERIES", "12")
        assert env_int("MAX_EXTERNAL_SEARCH_QUERIES", 5) == 12

    def test_nan_float_falls_back(self, monkeypatch) -> None:
        monkeypatch.setenv("SCRAPE_PILOT_MIN_SUCCESS_RATE", "nan")
        assert env_float("SCRAPE_PILOT_MIN_SUCCESS_RATE", 0.70) == 0.70


class TestBannerDurationGarbage:
    def test_invalid_duration_falls_back(self, monkeypatch) -> None:
        from primr.utils import banner as banner_mod

        monkeypatch.setenv("PRIMR_BANNER_DURATION_MS", "nope")
        monkeypatch.setattr(banner_mod, "should_show_banner", lambda *a, **k: True)
        monkeypatch.setattr(banner_mod, "resolve_banner_mode", lambda *a, **k: "animated")
        monkeypatch.setattr(
            banner_mod,
            "detect_banner_context",
            lambda: banner_mod.BannerContext(
                is_tty=True,
                supports_color=True,
                supports_unicode=True,
                supports_cursor=True,
            ),
        )
        captured: dict[str, int] = {}

        def fake_render(_ctx, duration_ms: int = 1500) -> None:
            captured["duration_ms"] = duration_ms

        monkeypatch.setattr(banner_mod, "render_animated_banner", fake_render)
        assert banner_mod.maybe_show_startup_banner() is True
        assert captured["duration_ms"] == 1500
