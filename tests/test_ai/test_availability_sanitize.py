"""Tests for the shared provider-availability sanitizers.

These pin the invariant that routing metadata and `primr doctor` output can
never carry a secret, raw endpoint, hostname/IP, account id, or control
sequence, no matter what an upstream collector puts in a snapshot. Each case
below is a verified adversarial input from the availability-bridge security
review.
"""

from primr.ai.availability_sanitize import (
    safe_code,
    safe_code_or,
    safe_count,
    safe_display_label,
    safe_env_label,
)


class TestSafeCode:
    def test_clean_code_passes_lowercased(self):
        assert safe_code("Not_Collected") == "not_collected"
        assert safe_code("missing_api_key") == "missing_api_key"

    def test_empty_is_none(self):
        assert safe_code("") is None
        assert safe_code(None) is None

    def test_url_collapses(self):
        assert safe_code("http://operator-host.example:9999/v1") == "availability_error"

    def test_overlong_collapses(self):
        assert safe_code("a" * 81) == "availability_error"

    def test_unicode_homoglyph_does_not_survive(self):
        # `.isalnum()` is Unicode-wide; the sanitizer must be ASCII-only so a
        # homoglyph hostname or accented host detail cannot pass.
        assert safe_code("café_naive_hostname") == "availability_error"
        assert safe_code("хост") == "availability_error"  # Cyrillic "host"
        assert safe_code("ｈｏｓｔ") == "availability_error"  # fullwidth "host"

    def test_control_sequences_collapse(self):
        assert safe_code("ok\x1b[31mred") == "availability_error"
        assert safe_code("a\nb") == "availability_error"


class TestSafeCodeOr:
    def test_none_uses_fallback(self):
        assert safe_code_or(None, "unknown") == "unknown"

    def test_invalid_uses_fallback(self):
        assert safe_code_or("http://host/x", "unknown") == "availability_error"

    def test_non_string_is_stringified_then_sanitized(self):
        assert safe_code_or(123, "unknown") == "123"


class TestSafeCount:
    def test_clamps_huge_values(self):
        assert safe_count(10**50) == 100_000

    def test_normal_value(self):
        assert safe_count(7) == 7

    def test_bool_is_zero(self):
        assert safe_count(True) == 0

    def test_non_numeric_is_zero(self):
        assert safe_count([1, 2]) == 0
        assert safe_count(None) == 0
        assert safe_count(float("inf")) == 0
        assert safe_count(float("nan")) == 0

    def test_negative_is_zero(self):
        assert safe_count(-5) == 0


class TestSafeDisplayLabel:
    def test_clean_label_passes(self):
        assert (
            safe_display_label("Local OpenAI-compatible", "fallback") == "Local OpenAI-compatible"
        )

    def test_url_or_path_falls_back(self):
        assert safe_display_label("https://host/x", "fb") == "fb"
        assert safe_display_label("user@host", "fb") == "fb"

    def test_dotted_host_falls_back_even_with_spaces(self):
        # The bypass: a space disabled the old dotted-host guard.
        assert safe_display_label("internal box 10.0.0.5 host", "fb") == "fb"
        assert safe_display_label("example.com", "fb") == "fb"

    def test_trailing_period_is_allowed(self):
        # A trailing period is not a dotted host, so a legit name survives.
        assert safe_display_label("Acme Inc.", "fb") == "Acme Inc."

    def test_non_printable_falls_back(self):
        assert safe_display_label("ok\x1b[31m", "fb") == "fb"

    def test_empty_uses_fallback(self):
        assert safe_display_label("", "fb") == "fb"
        assert safe_display_label(None, "fb") == "fb"


class TestSafeEnvLabel:
    def test_clean_env_name_passes(self):
        assert safe_env_label("OPENAI_API_KEY") == "OPENAI_API_KEY"

    def test_url_falls_back(self):
        assert safe_env_label("http://operator-host.example/key") == "provider key"

    def test_non_string_falls_back(self):
        assert safe_env_label(None) == "provider key"
        assert safe_env_label(123) == "provider key"

    def test_lowercase_or_symbols_fall_back(self):
        assert safe_env_label("api-key") == "provider key"
