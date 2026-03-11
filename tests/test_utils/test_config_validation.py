"""
Tests for unified configuration validation.

**Feature: code-quality-improvements**
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from primr.utils.config_validation import (
    AIConfig,
    APIKeysConfig,
    ConfigError,
    ConfigValidationResult,
    PathsConfig,
    PrimrConfig,
    RetryConfig,
    ScrapingConfig,
    TimeoutsConfig,
    export_schema,
    load_config,
    require_valid_config,
    reset_config,
    validate_config,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_config_fixture():
    """Reset config cache before and after each test."""
    reset_config()
    yield
    reset_config()


# =============================================================================
# API KEYS CONFIG TESTS
# =============================================================================


class TestAPIKeysConfig:
    """Tests for APIKeysConfig validation."""

    def test_validates_missing_gemini_key(self):
        """Should report error for missing Gemini API key."""
        with patch.dict(os.environ, {}, clear=True):
            config = APIKeysConfig(
                gemini_api_key=None, search_api_key="test", search_engine_id="test"
            )
            errors = config.validate()

            assert len(errors) == 1
            assert "GEMINI_API_KEY" in errors[0].field

    def test_validates_short_api_key(self):
        """Should report error for suspiciously short API key."""
        config = APIKeysConfig(
            gemini_api_key="short", search_api_key="test", search_engine_id="test"
        )
        errors = config.validate()

        assert len(errors) == 1
        assert "too short" in errors[0].message

    def test_warnings_for_optional_keys(self):
        """Should report warnings for missing optional keys."""
        config = APIKeysConfig(
            gemini_api_key="valid_api_key_here", search_api_key=None, search_engine_id=None
        )
        warnings = config.get_warnings()

        assert len(warnings) == 2
        assert any("SEARCH_API_KEY" in w.field for w in warnings)
        assert any("SEARCH_ENGINE_ID" in w.field for w in warnings)

    def test_valid_config_no_errors(self):
        """Should report no errors for valid config."""
        config = APIKeysConfig(
            gemini_api_key="valid_api_key_here_long_enough",
            search_api_key="search_key",
            search_engine_id="engine_id",
        )
        errors = config.validate()

        assert len(errors) == 0


# =============================================================================
# TIMEOUTS CONFIG TESTS
# =============================================================================


class TestTimeoutsConfig:
    """Tests for TimeoutsConfig validation."""

    def test_validates_negative_timeout(self):
        """Should report error for negative timeout."""
        config = TimeoutsConfig(connect_timeout=-1)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("connect_timeout" in e.field for e in errors)

    def test_validates_excessive_timeout(self):
        """Should report error for excessive timeout."""
        config = TimeoutsConfig(ai_timeout=1000)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("ai_timeout" in e.field for e in errors)

    def test_validates_total_less_than_connect(self):
        """Should report error when total < connect."""
        config = TimeoutsConfig(connect_timeout=30, total_timeout=10)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("total_timeout" in e.field for e in errors)

    def test_valid_timeouts_no_errors(self):
        """Should report no errors for valid timeouts."""
        config = TimeoutsConfig()
        errors = config.validate()

        assert len(errors) == 0


# =============================================================================
# RETRY CONFIG TESTS
# =============================================================================


class TestRetryConfig:
    """Tests for RetryConfig validation."""

    def test_validates_negative_retries(self):
        """Should report error for negative max_retries."""
        config = RetryConfig(max_retries=-1)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("max_retries" in e.field for e in errors)

    def test_validates_excessive_retries(self):
        """Should report error for excessive max_retries."""
        config = RetryConfig(max_retries=100)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("max_retries" in e.field for e in errors)

    def test_validates_invalid_jitter(self):
        """Should report error for invalid jitter_factor."""
        config = RetryConfig(jitter_factor=2.0)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("jitter_factor" in e.field for e in errors)

    def test_validates_invalid_exponential_base(self):
        """Should report error for exponential_base <= 1."""
        config = RetryConfig(exponential_base=0.5)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("exponential_base" in e.field for e in errors)


# =============================================================================
# SCRAPING CONFIG TESTS
# =============================================================================


class TestScrapingConfig:
    """Tests for ScrapingConfig validation."""

    def test_validates_zero_max_pages(self):
        """Should report error for zero max_pages."""
        config = ScrapingConfig(max_pages=0)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("max_pages" in e.field for e in errors)

    def test_validates_excessive_max_pages(self):
        """Should report error for excessive max_pages."""
        config = ScrapingConfig(max_pages=1000)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("max_pages" in e.field for e in errors)

    def test_validates_negative_depth(self):
        """Should report error for negative max_depth."""
        config = ScrapingConfig(max_depth=-1)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("max_depth" in e.field for e in errors)


# =============================================================================
# AI CONFIG TESTS
# =============================================================================


class TestAIConfig:
    """Tests for AIConfig validation."""

    def test_validates_empty_model_name(self):
        """Should report error for empty model name."""
        config = AIConfig(fast_model="")
        errors = config.validate()

        assert len(errors) >= 1
        assert any("Model name" in e.message for e in errors)

    def test_validates_invalid_temperature(self):
        """Should report error for invalid temperature."""
        config = AIConfig(temperature=3.0)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("temperature" in e.field for e in errors)

    def test_validates_invalid_thinking_level(self):
        """Should report error for invalid thinking_level."""
        config = AIConfig(thinking_level="medium")  # type: ignore
        errors = config.validate()

        assert len(errors) >= 1
        assert any("thinking_level" in e.field for e in errors)

    def test_validates_invalid_grade_threshold(self):
        """Should report error for invalid grade_threshold."""
        config = AIConfig(grade_threshold=150)
        errors = config.validate()

        assert len(errors) >= 1
        assert any("grade_threshold" in e.field for e in errors)


# =============================================================================
# PATHS CONFIG TESTS
# =============================================================================


class TestPathsConfig:
    """Tests for PathsConfig validation."""

    def test_creates_directories(self):
        """Should create directories on validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = PathsConfig(project_root=Path(tmpdir))
            errors = config.validate()

            assert len(errors) == 0
            assert config.output_dir.exists()
            assert config.working_dir.exists()
            assert config.logs_dir.exists()

    def test_validates_unwritable_directory(self):
        """Should report error for unwritable directory."""
        # Skip this test on Windows where path validation behaves differently
        import sys

        if sys.platform == "win32":
            pytest.skip("Path validation differs on Windows")

        # Use a path that definitely doesn't exist and can't be created
        config = PathsConfig(project_root=Path("/nonexistent/path/that/cannot/exist"))
        errors = config.validate()

        # Should have errors for directories that can't be created
        assert len(errors) >= 1


# =============================================================================
# PRIMR CONFIG TESTS
# =============================================================================


class TestPrimrConfig:
    """Tests for main PrimrConfig class."""

    def test_validate_aggregates_all_errors(self):
        """Should aggregate errors from all sections."""
        config = PrimrConfig(
            api_keys=APIKeysConfig(gemini_api_key=None),
            timeouts=TimeoutsConfig(connect_timeout=-1),
            retry=RetryConfig(max_retries=-1),
        )
        result = config.validate(include_api_keys=True)

        assert not result.valid
        assert len(result.errors) >= 3

    def test_validate_without_api_keys(self):
        """Should skip API key validation when requested."""
        config = PrimrConfig(
            api_keys=APIKeysConfig(gemini_api_key=None),
        )
        result = config.validate(include_api_keys=False)

        # Should be valid if only API keys are missing
        # (assuming other defaults are valid)
        assert result.valid or all("API" not in e.field for e in result.errors)

    def test_to_dict_excludes_secrets(self):
        """Should not include API keys in to_dict output."""
        config = PrimrConfig(
            api_keys=APIKeysConfig(
                gemini_api_key="secret_key",
                search_api_key="another_secret",
            ),
        )
        data = config.to_dict()

        # Should not contain actual keys
        assert "secret_key" not in str(data)
        assert "another_secret" not in str(data)

        # Should indicate whether keys are configured
        assert "api_keys_configured" in data
        assert data["api_keys_configured"]["gemini"] is True


# =============================================================================
# MODULE FUNCTION TESTS
# =============================================================================


class TestModuleFunctions:
    """Tests for module-level functions."""

    def test_load_config_returns_config(self):
        """load_config should return a PrimrConfig instance."""
        config = load_config()
        assert isinstance(config, PrimrConfig)

    def test_load_config_caches_result(self):
        """load_config should cache the result."""
        config1 = load_config()
        config2 = load_config()
        assert config1 is config2

    def test_reset_config_clears_cache(self):
        """reset_config should clear the cache."""
        config1 = load_config()
        reset_config()
        config2 = load_config()
        assert config1 is not config2

    def test_validate_config_returns_result(self):
        """validate_config should return ConfigValidationResult."""
        result = validate_config(include_api_keys=False)
        assert isinstance(result, ConfigValidationResult)

    def test_require_valid_config_raises_on_invalid(self):
        """require_valid_config should raise on invalid config."""
        # Create invalid config
        reset_config()

        # Mock environment to have no API key
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            reset_config()
            with pytest.raises(ValueError, match="validation failed"):
                require_valid_config(include_api_keys=True)

    def test_export_schema_returns_valid_schema(self):
        """export_schema should return a valid JSON Schema."""
        schema = export_schema()

        assert "$schema" in schema
        assert "properties" in schema
        assert "timeouts" in schema["properties"]
        assert "retry" in schema["properties"]
        assert "scraping" in schema["properties"]
        assert "ai" in schema["properties"]


# =============================================================================
# CONFIG ERROR TESTS
# =============================================================================


class TestConfigError:
    """Tests for ConfigError class."""

    def test_str_includes_field_and_message(self):
        """ConfigError str should include field and message."""
        error = ConfigError(field="test_field", message="test message")
        assert "test_field" in str(error)
        assert "test message" in str(error)

    def test_str_includes_value_when_present(self):
        """ConfigError str should include value when present."""
        error = ConfigError(field="test", message="msg", value=42)
        assert "42" in str(error)

    def test_str_includes_suggestion_when_present(self):
        """ConfigError str should include suggestion when present."""
        error = ConfigError(field="test", message="msg", suggestion="try this")
        assert "try this" in str(error)


class TestConfigValidationResult:
    """Tests for ConfigValidationResult class."""

    def test_str_shows_valid_when_no_errors(self):
        """ConfigValidationResult str should show valid when no errors."""
        result = ConfigValidationResult(valid=True)
        assert "valid" in str(result).lower()

    def test_str_shows_errors_when_present(self):
        """ConfigValidationResult str should show errors when present."""
        result = ConfigValidationResult(
            valid=False, errors=[ConfigError(field="test", message="error")]
        )
        assert "error" in str(result).lower()
        assert "test" in str(result)

    def test_str_shows_warnings_when_present(self):
        """ConfigValidationResult str should show warnings when present."""
        result = ConfigValidationResult(
            valid=True, warnings=[ConfigError(field="warn", message="warning")]
        )
        assert "warning" in str(result).lower()
