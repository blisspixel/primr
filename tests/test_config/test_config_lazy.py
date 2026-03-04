"""
Property tests for lazy API key validation.

**Feature: research-agent-decomposition, Property 2: Lazy API key validation**
**Validates: Requirements 3.2**
"""

import sys
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestLazyAPIKeyValidation:
    """
    **Feature: research-agent-decomposition, Property 2: Lazy API key validation**
    **Validates: Requirements 3.2**

    Property: For any access to an API key property when the key is not configured,
    the System SHALL raise ConfigurationError. For any access when the key is
    configured, the System SHALL return the key value.
    """

    @given(st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=('Cs',))))
    @settings(max_examples=50, deadline=None)
    def test_gemini_key_returned_when_configured(self, key: str):
        """When Gemini API key is configured, accessor returns it."""
        assume(key.strip())  # Non-empty after stripping

        import primr.config.config as config_module
        original = config_module._gemini_api_key

        try:
            config_module._gemini_api_key = key
            assert config_module.get_gemini_api_key() == key
        finally:
            config_module._gemini_api_key = original

    def test_gemini_key_raises_when_missing(self):
        """When Gemini API key is not configured, accessor raises ConfigurationError."""
        import primr.config.config as config_module

        # Save original value
        original = config_module._gemini_api_key

        try:
            # Set to None to simulate missing key
            config_module._gemini_api_key = None

            from primr.config.config import ConfigurationError

            with pytest.raises(ConfigurationError) as exc_info:
                config_module.get_gemini_api_key()

            assert "GEMINI_API_KEY" in str(exc_info.value)
            assert exc_info.value.guidance is not None
        finally:
            # Restore original value
            config_module._gemini_api_key = original

    @given(st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=('Cs',))))
    @settings(max_examples=50, deadline=None)
    def test_search_key_returned_when_configured(self, key: str):
        """When Search API key is configured, accessor returns it."""
        assume(key.strip())

        import primr.config.config as config_module
        original = config_module._search_api_key

        try:
            config_module._search_api_key = key
            assert config_module.get_search_api_key() == key
        finally:
            config_module._search_api_key = original

    def test_search_key_raises_when_missing(self):
        """When Search API key is not configured, accessor raises ConfigurationError."""
        import primr.config.config as config_module

        original = config_module._search_api_key

        try:
            config_module._search_api_key = None

            from primr.config.config import ConfigurationError

            with pytest.raises(ConfigurationError) as exc_info:
                config_module.get_search_api_key()

            assert "SEARCH_API_KEY" in str(exc_info.value)
        finally:
            config_module._search_api_key = original

    @given(st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=('Cs',))))
    @settings(max_examples=50, deadline=None)
    def test_search_engine_id_returned_when_configured(self, engine_id: str):
        """When Search Engine ID is configured, accessor returns it."""
        assume(engine_id.strip())

        import primr.config.config as config_module
        original = config_module._search_engine_id

        try:
            config_module._search_engine_id = engine_id
            assert config_module.get_search_engine_id() == engine_id
        finally:
            config_module._search_engine_id = original

    def test_search_engine_id_raises_when_missing(self):
        """When Search Engine ID is not configured, accessor raises ConfigurationError."""
        import primr.config.config as config_module

        original = config_module._search_engine_id

        try:
            config_module._search_engine_id = None

            from primr.config.config import ConfigurationError

            with pytest.raises(ConfigurationError) as exc_info:
                config_module.get_search_engine_id()

            assert "SEARCH_ENGINE_ID" in str(exc_info.value)
        finally:
            config_module._search_engine_id = original


class TestConfigValidation:
    """Tests for explicit configuration validation."""

    def test_validate_config_returns_valid_when_all_keys_set(self):
        """validate_config returns valid=True when required keys are set."""
        import primr.config.config as config_module

        # Save originals
        orig_gemini = config_module._gemini_api_key

        try:
            config_module._gemini_api_key = "test_key"

            result = config_module.validate_config()
            assert result.valid is True
            assert len(result.errors) == 0
        finally:
            config_module._gemini_api_key = orig_gemini

    def test_validate_config_returns_invalid_when_gemini_key_missing(self):
        """validate_config returns valid=False when GEMINI_API_KEY is missing."""
        import primr.config.config as config_module

        orig_gemini = config_module._gemini_api_key

        try:
            config_module._gemini_api_key = None

            result = config_module.validate_config()
            assert result.valid is False
            assert any("GEMINI_API_KEY" in err for err in result.errors)
        finally:
            config_module._gemini_api_key = orig_gemini

    def test_require_valid_config_raises_when_invalid(self):
        """require_valid_config raises ConfigurationError when config is invalid."""
        import primr.config.config as config_module
        from primr.config.config import ConfigurationError

        orig_gemini = config_module._gemini_api_key

        try:
            config_module._gemini_api_key = None

            with pytest.raises(ConfigurationError):
                config_module.require_valid_config()
        finally:
            config_module._gemini_api_key = orig_gemini

    def test_require_valid_config_passes_when_valid(self):
        """require_valid_config does not raise when config is valid."""
        import primr.config.config as config_module

        orig_gemini = config_module._gemini_api_key

        try:
            config_module._gemini_api_key = "test_key"

            # Should not raise
            config_module.require_valid_config()
        finally:
            config_module._gemini_api_key = orig_gemini


class TestModuleImportWithoutAPIKeys:
    """
    **Feature: research-agent-decomposition, Property 1: Module import compatibility**
    **Validates: Requirements 3.1, 3.3**

    Tests that config module can be imported without API keys configured.
    """

    def test_config_imports_without_api_keys(self):
        """Config module should import successfully even without API keys."""
        import importlib

        import primr.config.config as config_module

        # Save originals
        orig_gemini = config_module._gemini_api_key
        orig_search = config_module._search_api_key
        orig_engine = config_module._search_engine_id

        try:
            # Clear all keys
            config_module._gemini_api_key = None
            config_module._search_api_key = None
            config_module._search_engine_id = None

            # Reload should succeed without raising
            importlib.reload(config_module)

            # Module should be importable
            assert config_module is not None
        finally:
            # Restore originals
            config_module._gemini_api_key = orig_gemini
            config_module._search_api_key = orig_search
            config_module._search_engine_id = orig_engine

    def test_backward_compatible_constants_accessible(self):
        """Backward compatible constants should still be accessible."""
        from primr.config.config import (
            LOGS_DIR,
            MAX_RETRIES,
            NUM_SEARCH_RESULTS,
            OUTPUT_DIR,
            PARALLEL_SEARCH_LIMIT,
            PROJECT_ROOT,
            WORKING_DIR,
        )

        # These should all be accessible
        assert NUM_SEARCH_RESULTS == 10
        assert PARALLEL_SEARCH_LIMIT == 2
        assert MAX_RETRIES == 3
        assert OUTPUT_DIR is not None
        assert WORKING_DIR is not None
        assert LOGS_DIR is not None
        assert PROJECT_ROOT is not None
