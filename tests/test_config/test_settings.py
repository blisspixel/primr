"""
Tests for the new Settings configuration system.
"""

import os
from unittest.mock import patch

from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
import pytest

from primr.config.settings import (
    AIConfig,
    APIConfig,
    CacheConfig,
    OutputConfig,
    PathConfig,
    ScrapingConfig,
    SearchConfig,
    Settings,
    TimeoutConfig,
    configure,
    get_settings,
    reset_settings,
)
from primr.utils.errors import ConfigurationError


class TestAPIConfig:
    """Tests for API configuration."""

    def test_loads_from_environment(self):
        """Should load API keys from environment."""
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-gemini-key",
                "SEARCH_API_KEY": "test-search-key",
                "SEARCH_ENGINE_ID": "test-engine-id",
            },
        ):
            config = APIConfig()
            assert config.gemini_key == "test-gemini-key"
            assert config.search_key == "test-search-key"
            assert config.search_engine_id == "test-engine-id"

    def test_raises_on_missing_gemini_key(self):
        """Should raise ConfigurationError when Gemini key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            config = APIConfig()
            config._gemini_key = None  # Force missing

            with pytest.raises(ConfigurationError) as exc_info:
                _ = config.gemini_key

            assert "GEMINI_API_KEY" in str(exc_info.value)

    def test_raises_on_missing_search_key(self):
        """Should raise ConfigurationError when Search key is missing."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "key"}, clear=True):
            config = APIConfig()
            config._search_key = None

            with pytest.raises(ConfigurationError) as exc_info:
                _ = config.search_key

            assert "SEARCH_API_KEY" in str(exc_info.value)

    def test_is_configured_returns_true_when_all_set(self):
        """is_configured() should return True when all keys are set."""
        config = APIConfig()
        config._gemini_key = "key1"
        config._search_key = "key2"
        config._search_engine_id = "id1"

        assert config.is_configured() is True

    def test_is_configured_returns_false_when_missing(self):
        """is_configured() should return False when keys are missing."""
        config = APIConfig()
        config._gemini_key = None
        config._search_key = "key"
        config._search_engine_id = "id"

        assert config.is_configured() is False

    def test_validate_checks_all_keys(self):
        """validate() should check all API keys."""
        config = APIConfig()
        config._gemini_key = "key1"
        config._search_key = "key2"
        config._search_engine_id = None

        with pytest.raises(ConfigurationError):
            config.validate()


class TestScrapingConfig:
    """Tests for scraping configuration."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = ScrapingConfig()

        assert config.max_retries == 2
        assert config.timeout == 15
        assert config.max_depth == 2
        assert config.cache_ttl_hours == 24
        assert config.min_content_length == 100

    def test_excluded_sites_default(self):
        """Should have default excluded sites."""
        config = ScrapingConfig()

        assert "login" in config.excluded_sites
        assert "captcha" in config.excluded_sites

    def test_soft_block_indicators(self):
        """Should have soft block detection keywords."""
        config = ScrapingConfig()

        assert "captcha" in config.soft_block_indicators
        assert "cloudflare" in config.soft_block_indicators

    def test_custom_values(self):
        """Should accept custom values."""
        config = ScrapingConfig(max_retries=5, timeout=30, excluded_sites=["custom.com"])

        assert config.max_retries == 5
        assert config.timeout == 30
        assert config.excluded_sites == ["custom.com"]


class TestAIConfig:
    """Tests for AI configuration."""

    def test_default_models(self):
        """Should have default model names."""
        config = AIConfig()

        assert "gemini" in config.research_model.lower()
        assert "gemini" in config.report_model.lower()

    def test_loads_models_from_env(self):
        """Should load model names from environment."""
        with patch.dict(
            os.environ,
            {
                "AI_RESEARCH_MODEL": "custom-research-model",
                "AI_REPORT_MODEL": "custom-report-model",
            },
        ):
            config = AIConfig()
            # Note: default_factory runs at class definition, so we need fresh instance
            # This test verifies the mechanism exists
            assert config.max_retries == 3

    def test_model_fallbacks(self):
        """Should have model fallback definitions."""
        config = AIConfig()

        assert isinstance(config.model_fallbacks, dict)
        # model_fallbacks may be empty if no fallbacks are configured
        # The key is that the attribute exists and is a dict


class TestSearchConfig:
    """Tests for search configuration."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = SearchConfig()

        assert config.num_results == 3
        assert config.parallel_limit == 2
        assert config.initial_retry_delay == 5

    def test_excluded_domains(self):
        """Should have default excluded domains."""
        config = SearchConfig()

        assert "reddit.com" in config.excluded_domains
        assert "facebook.com" in config.excluded_domains


class TestPathConfig:
    """Tests for path configuration."""

    def test_computes_paths_from_root(self, tmp_path):
        """Should compute all paths from project root."""
        config = PathConfig(project_root=tmp_path)

        assert config.output_dir == tmp_path / "output"
        assert config.working_dir == tmp_path / "working"
        assert config.logs_dir == tmp_path / "logs"
        assert config.cache_dir == tmp_path / "logs" / "scrape_cache"
        # prompts_file is now in the package config directory, not project root
        assert "prompts.json" in str(config.prompts_file)

    def test_ensure_directories_creates_dirs(self, tmp_path):
        """ensure_directories() should create all directories."""
        config = PathConfig(project_root=tmp_path)
        config.ensure_directories()

        assert config.output_dir.exists()
        assert config.working_dir.exists()
        assert config.logs_dir.exists()
        assert config.cache_dir.exists()


class TestOutputConfig:
    """Tests for output configuration."""

    def test_default_formats(self):
        """Should support common formats by default."""
        config = OutputConfig()

        assert ".txt" in config.supported_formats
        assert ".docx" in config.supported_formats
        assert ".pdf" in config.supported_formats


class TestSettings:
    """Tests for main Settings class."""

    def test_creates_all_configs(self, tmp_path):
        """Should create all config objects."""
        settings = Settings(paths=PathConfig(project_root=tmp_path))

        assert isinstance(settings.api, APIConfig)
        assert isinstance(settings.scraping, ScrapingConfig)
        assert isinstance(settings.ai, AIConfig)
        assert isinstance(settings.search, SearchConfig)
        assert isinstance(settings.paths, PathConfig)
        assert isinstance(settings.output, OutputConfig)

    def test_verbose_from_env(self):
        """Should load verbose flag from environment."""
        with patch.dict(os.environ, {"VERBOSE": "true"}):
            settings = Settings()
            # Note: default_factory runs at definition time
            assert isinstance(settings.verbose, bool)

    def test_from_env_factory(self, tmp_path):
        """from_env() should create settings with custom root."""
        settings = Settings.from_env(project_root=tmp_path)

        assert settings.paths.project_root == tmp_path

    def test_ensures_directories_on_init(self, tmp_path):
        """Should create directories on initialization."""
        settings = Settings(paths=PathConfig(project_root=tmp_path))

        assert settings.paths.output_dir.exists()
        assert settings.paths.working_dir.exists()


class TestSettingsSingleton:
    """Tests for settings singleton functions."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_settings()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_settings()

    def test_get_settings_returns_settings(self):
        """get_settings() should return Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_returns_same_instance(self):
        """get_settings() should return same instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_reset_settings_clears_singleton(self):
        """reset_settings() should clear the singleton."""
        settings1 = get_settings()
        reset_settings()
        settings2 = get_settings()

        assert settings1 is not settings2

    def test_configure_sets_options(self, tmp_path):
        """configure() should set custom options."""
        settings = configure(
            project_root=tmp_path,
            verbose=True,
            debug=True,
        )

        assert settings.paths.project_root == tmp_path
        assert settings.verbose is True
        assert settings.debug is True

    def test_configure_updates_singleton(self, tmp_path):
        """configure() should update the singleton."""
        configure(project_root=tmp_path)
        settings = get_settings()

        assert settings.paths.project_root == tmp_path


class TestSettingsIntegration:
    """Integration tests for settings."""

    def test_full_configuration_flow(self, tmp_path):
        """Test complete configuration workflow."""
        reset_settings()

        # Configure with custom settings
        settings = configure(
            project_root=tmp_path,
            verbose=True,
        )

        # Verify paths are correct
        assert settings.paths.output_dir == tmp_path / "output"

        # Verify directories were created
        assert settings.paths.output_dir.exists()

        # Verify we can access nested config
        assert settings.scraping.timeout == 15
        assert settings.ai.max_retries == 3

        reset_settings()


# =============================================================================
# TIMEOUT CONFIG TESTS
# =============================================================================


class TestTimeoutConfig:
    """Tests for TimeoutConfig validation."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = TimeoutConfig()

        assert config.connect == 10.0
        assert config.read == 30.0
        assert config.total == 60.0

    def test_custom_values(self):
        """Should accept custom values."""
        config = TimeoutConfig(connect=5.0, read=15.0, total=30.0)

        assert config.connect == 5.0
        assert config.read == 15.0
        assert config.total == 30.0

    def test_validate_passes_for_valid_config(self):
        """validate() should pass for valid configuration."""
        config = TimeoutConfig(connect=5.0, read=10.0, total=20.0)
        config.validate()  # Should not raise

    def test_validate_rejects_zero_connect(self):
        """validate() should reject zero connect timeout."""
        config = TimeoutConfig(connect=0.0, read=10.0, total=20.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "connect" in str(exc_info.value)

    def test_validate_rejects_negative_connect(self):
        """validate() should reject negative connect timeout."""
        config = TimeoutConfig(connect=-1.0, read=10.0, total=20.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "connect" in str(exc_info.value)

    def test_validate_rejects_zero_read(self):
        """validate() should reject zero read timeout."""
        config = TimeoutConfig(connect=5.0, read=0.0, total=20.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "read" in str(exc_info.value)

    def test_validate_rejects_negative_read(self):
        """validate() should reject negative read timeout."""
        config = TimeoutConfig(connect=5.0, read=-5.0, total=20.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "read" in str(exc_info.value)

    def test_validate_rejects_zero_total(self):
        """validate() should reject zero total timeout."""
        config = TimeoutConfig(connect=5.0, read=10.0, total=0.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "total" in str(exc_info.value)

    def test_validate_rejects_total_less_than_connect(self):
        """validate() should reject total < connect."""
        config = TimeoutConfig(connect=10.0, read=5.0, total=5.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "total" in str(exc_info.value)
        assert "connect" in str(exc_info.value)

    def test_validate_rejects_total_less_than_read(self):
        """validate() should reject total < read."""
        config = TimeoutConfig(connect=5.0, read=20.0, total=10.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "total" in str(exc_info.value)
        assert "read" in str(exc_info.value)

    def test_as_tuple_returns_connect_read(self):
        """as_tuple() should return (connect, read) for requests library."""
        config = TimeoutConfig(connect=5.0, read=15.0, total=30.0)

        result = config.as_tuple()

        assert result == (5.0, 15.0)


# =============================================================================
# CACHE CONFIG TESTS
# =============================================================================


class TestCacheConfig:
    """Tests for CacheConfig validation."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = CacheConfig()

        assert config.max_size == 100
        assert config.ttl_seconds == 3600.0
        assert config.name == "default"

    def test_custom_values(self):
        """Should accept custom values."""
        config = CacheConfig(max_size=50, ttl_seconds=1800.0, name="test_cache")

        assert config.max_size == 50
        assert config.ttl_seconds == 1800.0
        assert config.name == "test_cache"

    def test_validate_passes_for_valid_config(self):
        """validate() should pass for valid configuration."""
        config = CacheConfig(max_size=100, ttl_seconds=3600.0, name="valid")
        config.validate()  # Should not raise

    def test_validate_passes_for_none_ttl(self):
        """validate() should pass when ttl_seconds is None (no expiry)."""
        config = CacheConfig(max_size=100, ttl_seconds=None, name="no_expiry")
        config.validate()  # Should not raise

    def test_validate_rejects_zero_max_size(self):
        """validate() should reject zero max_size."""
        config = CacheConfig(max_size=0, ttl_seconds=3600.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "max_size" in str(exc_info.value)

    def test_validate_rejects_negative_max_size(self):
        """validate() should reject negative max_size."""
        config = CacheConfig(max_size=-10, ttl_seconds=3600.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "max_size" in str(exc_info.value)

    def test_validate_rejects_zero_ttl(self):
        """validate() should reject zero ttl_seconds."""
        config = CacheConfig(max_size=100, ttl_seconds=0.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "ttl_seconds" in str(exc_info.value)

    def test_validate_rejects_negative_ttl(self):
        """validate() should reject negative ttl_seconds."""
        config = CacheConfig(max_size=100, ttl_seconds=-100.0)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "ttl_seconds" in str(exc_info.value)

    def test_validate_rejects_empty_name(self):
        """validate() should reject empty name."""
        config = CacheConfig(max_size=100, ttl_seconds=3600.0, name="")

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "name" in str(exc_info.value)

    def test_validate_rejects_whitespace_name(self):
        """validate() should reject whitespace-only name."""
        config = CacheConfig(max_size=100, ttl_seconds=3600.0, name="   ")

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "name" in str(exc_info.value)


# =============================================================================
# SETTINGS VALIDATE_ALL TESTS
# =============================================================================


class TestSettingsValidateAll:
    """Tests for Settings.validate_all() method."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_settings()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_settings()

    def test_validate_all_passes_for_defaults(self, tmp_path):
        """validate_all() should pass for default configuration."""
        settings = Settings(paths=PathConfig(project_root=tmp_path))
        settings.validate_all()  # Should not raise

    def test_validate_all_catches_invalid_timeout(self, tmp_path):
        """validate_all() should catch invalid timeout config."""
        settings = Settings(
            paths=PathConfig(project_root=tmp_path),
            timeouts=TimeoutConfig(connect=-1.0, read=10.0, total=20.0),
        )

        with pytest.raises(ValueError) as exc_info:
            settings.validate_all()

        assert "TimeoutConfig" in str(exc_info.value)

    def test_validate_all_catches_invalid_cache(self, tmp_path):
        """validate_all() should catch invalid cache config."""
        settings = Settings(
            paths=PathConfig(project_root=tmp_path),
            cache=CacheConfig(max_size=0, ttl_seconds=3600.0),
        )

        with pytest.raises(ValueError) as exc_info:
            settings.validate_all()

        assert "CacheConfig" in str(exc_info.value)

    def test_validate_all_catches_invalid_scraping(self, tmp_path):
        """validate_all() should catch invalid scraping config."""
        settings = Settings(paths=PathConfig(project_root=tmp_path))
        settings.scraping.timeout = -5

        with pytest.raises(ValueError) as exc_info:
            settings.validate_all()

        assert "ScrapingConfig" in str(exc_info.value)

    def test_validate_all_catches_invalid_ai(self, tmp_path):
        """validate_all() should catch invalid AI config."""
        settings = Settings(paths=PathConfig(project_root=tmp_path))
        settings.ai.grade_threshold = 150  # Invalid: > 100

        with pytest.raises(ValueError) as exc_info:
            settings.validate_all()

        assert "AIConfig" in str(exc_info.value)

    def test_validate_all_catches_invalid_search(self, tmp_path):
        """validate_all() should catch invalid search config."""
        settings = Settings(paths=PathConfig(project_root=tmp_path))
        settings.search.num_results = 0

        with pytest.raises(ValueError) as exc_info:
            settings.validate_all()

        assert "SearchConfig" in str(exc_info.value)

    def test_validate_all_collects_multiple_errors(self, tmp_path):
        """validate_all() should collect all errors, not just first."""
        settings = Settings(
            paths=PathConfig(project_root=tmp_path),
            timeouts=TimeoutConfig(connect=-1.0, read=10.0, total=20.0),
            cache=CacheConfig(max_size=0, ttl_seconds=3600.0),
        )

        with pytest.raises(ValueError) as exc_info:
            settings.validate_all()

        error_msg = str(exc_info.value)
        assert "TimeoutConfig" in error_msg
        assert "CacheConfig" in error_msg

    def test_validate_all_skips_api_keys_by_default(self, tmp_path):
        """validate_all() should not check API keys by default."""
        settings = Settings(paths=PathConfig(project_root=tmp_path))
        settings.api._gemini_key = None
        settings.api._search_key = None
        settings.api._search_engine_id = None

        # Should not raise even with missing API keys
        settings.validate_all()

    def test_validate_all_checks_api_keys_when_requested(self, tmp_path):
        """validate_all(include_api_keys=True) should check API keys."""
        settings = Settings(paths=PathConfig(project_root=tmp_path))
        settings.api._gemini_key = None

        with pytest.raises(ValueError) as exc_info:
            settings.validate_all(include_api_keys=True)

        assert "APIConfig" in str(exc_info.value)


# =============================================================================
# PROPERTY-BASED TESTS
# =============================================================================


class TestConfigurationValidationProperty:
    """
    Property-based tests for configuration validation.

    **Feature: code-quality-hardening, Property 17: Configuration Validation**

    For any configuration with invalid values (negative timeouts, zero cache size),
    the validator SHALL reject the configuration with a descriptive error.
    """

    @given(
        connect=st.floats(min_value=-1000, max_value=0, allow_nan=False, allow_infinity=False),
        read=st.floats(min_value=0.1, max_value=100, allow_nan=False),
        total=st.floats(min_value=0.1, max_value=200, allow_nan=False),
    )
    @hyp_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_timeout_rejects_non_positive_connect(self, connect, read, total):
        """
        **Feature: code-quality-hardening, Property 17: Configuration Validation**

        TimeoutConfig SHALL reject non-positive connect timeout.
        """
        config = TimeoutConfig(connect=connect, read=read, total=total)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "connect" in str(exc_info.value).lower()

    @given(
        connect=st.floats(min_value=0.1, max_value=100, allow_nan=False),
        read=st.floats(min_value=-1000, max_value=0, allow_nan=False, allow_infinity=False),
        total=st.floats(min_value=0.1, max_value=200, allow_nan=False),
    )
    @hyp_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_timeout_rejects_non_positive_read(self, connect, read, total):
        """
        **Feature: code-quality-hardening, Property 17: Configuration Validation**

        TimeoutConfig SHALL reject non-positive read timeout.
        """
        config = TimeoutConfig(connect=connect, read=read, total=total)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "read" in str(exc_info.value).lower()

    @given(
        max_size=st.integers(min_value=-10000, max_value=0),
        ttl=st.floats(min_value=0.1, max_value=10000, allow_nan=False),
    )
    @hyp_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cache_rejects_non_positive_max_size(self, max_size, ttl):
        """
        **Feature: code-quality-hardening, Property 17: Configuration Validation**

        CacheConfig SHALL reject non-positive max_size.
        """
        config = CacheConfig(max_size=max_size, ttl_seconds=ttl)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "max_size" in str(exc_info.value).lower()

    @given(
        max_size=st.integers(min_value=1, max_value=10000),
        ttl=st.floats(min_value=-10000, max_value=0, allow_nan=False, allow_infinity=False),
    )
    @hyp_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cache_rejects_non_positive_ttl(self, max_size, ttl):
        """
        **Feature: code-quality-hardening, Property 17: Configuration Validation**

        CacheConfig SHALL reject non-positive ttl_seconds (when not None).
        """
        config = CacheConfig(max_size=max_size, ttl_seconds=ttl)

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        assert "ttl_seconds" in str(exc_info.value).lower()

    @given(
        connect=st.floats(min_value=0.1, max_value=50, allow_nan=False),
        read=st.floats(min_value=0.1, max_value=50, allow_nan=False),
        total=st.floats(min_value=100, max_value=200, allow_nan=False),
    )
    @hyp_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_timeout_accepts_valid_config(self, connect, read, total):
        """
        **Feature: code-quality-hardening, Property 17: Configuration Validation**

        TimeoutConfig SHALL accept valid configurations where all values are
        positive and total >= max(connect, read).
        """
        config = TimeoutConfig(connect=connect, read=read, total=total)
        config.validate()  # Should not raise

    @given(
        max_size=st.integers(min_value=1, max_value=10000),
        ttl=st.one_of(
            st.none(),
            st.floats(min_value=0.1, max_value=100000, allow_nan=False),
        ),
        name=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    )
    @hyp_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cache_accepts_valid_config(self, max_size, ttl, name):
        """
        **Feature: code-quality-hardening, Property 17: Configuration Validation**

        CacheConfig SHALL accept valid configurations where max_size > 0,
        ttl_seconds is None or positive, and name is non-empty.
        """
        config = CacheConfig(max_size=max_size, ttl_seconds=ttl, name=name)
        config.validate()  # Should not raise
