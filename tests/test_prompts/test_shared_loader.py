"""
Tests for the shared component loader.

Includes property-based tests using Hypothesis for comprehensive validation.
"""

import tempfile
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, strategies as st

from primr.prompts.schema import SharedComponents
from primr.prompts.shared_loader import (
    SharedComponentLoader,
    get_shared_loader,
    load_shared_components,
)


class TestSharedComponentLoader:
    """Tests for SharedComponentLoader class."""

    def test_load_returns_shared_components(self):
        """Loading should return a SharedComponents instance."""
        loader = SharedComponentLoader()
        components = loader.load()
        assert isinstance(components, SharedComponents)

    def test_load_epistemic_rules(self):
        """Should load epistemic rules from YAML."""
        loader = SharedComponentLoader()
        components = loader.load()
        assert len(components.epistemic_rules) > 0
        assert "fact_inference_hypothesis" in components.epistemic_rules

    def test_load_formatting_rules(self):
        """Should load formatting rules from YAML."""
        loader = SharedComponentLoader()
        components = loader.load()
        assert len(components.formatting_rules) > 0
        assert "paragraphs" in components.formatting_rules

    def test_load_personas(self):
        """Should load personas from YAML."""
        loader = SharedComponentLoader()
        components = loader.load()
        assert len(components.personas) > 0
        assert "senior_consultant" in components.personas

    def test_caching(self):
        """Should cache loaded components."""
        loader = SharedComponentLoader()
        components1 = loader.load()
        components2 = loader.load()
        assert components1 is components2

    def test_reload_clears_cache(self):
        """Reload should clear cache and load fresh."""
        loader = SharedComponentLoader()
        components1 = loader.load()
        components2 = loader.reload()
        # After reload, should be a new instance
        assert components1 is not components2

    def test_missing_directory_returns_empty(self):
        """Should return empty components for missing directory."""
        loader = SharedComponentLoader(Path("/nonexistent/path"))
        components = loader.load()
        # Returns empty (no personas, rules, etc.) rather than raising
        assert len(components.personas) == 0

    def test_get_persona_default(self):
        """Should return default persona when none specified."""
        loader = SharedComponentLoader()
        components = loader.load()
        persona = components.get_persona()
        assert len(persona) > 0
        assert "consultant" in persona.lower()

    def test_get_persona_by_name(self):
        """Should return specific persona by name."""
        loader = SharedComponentLoader()
        components = loader.load()
        persona = components.get_persona("ai_strategist")
        assert len(persona) > 0
        assert "AI" in persona or "ai" in persona.lower()


class TestSharedComponentLoaderWithTempDir:
    """Tests using temporary directories for isolation."""

    def test_load_from_custom_directory(self):
        """Should load from custom directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            shared_dir = Path(tmpdir)

            # Create minimal YAML files
            epistemic = {"rules": {"test_rule": "Test rule content"}}
            formatting = {"rules": {"test_format": "Test format content"}}
            personas = {
                "default": "test_persona",
                "personas": {"test_persona": "Test persona content"},
            }

            (shared_dir / "epistemic_rules.yaml").write_text(
                yaml.dump(epistemic), encoding="utf-8"
            )
            (shared_dir / "formatting.yaml").write_text(
                yaml.dump(formatting), encoding="utf-8"
            )
            (shared_dir / "personas.yaml").write_text(
                yaml.dump(personas), encoding="utf-8"
            )

            loader = SharedComponentLoader(shared_dir)
            components = loader.load()

            assert "test_rule" in components.epistemic_rules
            assert "test_format" in components.formatting_rules
            assert "test_persona" in components.personas

    def test_handles_empty_yaml(self):
        """Should handle empty YAML files gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            shared_dir = Path(tmpdir)

            # Create empty YAML files
            (shared_dir / "epistemic_rules.yaml").write_text("", encoding="utf-8")
            (shared_dir / "formatting.yaml").write_text("", encoding="utf-8")
            (shared_dir / "personas.yaml").write_text("", encoding="utf-8")

            loader = SharedComponentLoader(shared_dir)
            components = loader.load()

            # Should return empty but valid components
            assert isinstance(components, SharedComponents)
            assert len(components.epistemic_rules) == 0

    def test_handles_missing_optional_files(self):
        """Should handle missing optional files gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            shared_dir = Path(tmpdir)

            # Create only epistemic rules, skip others
            epistemic = {"rules": {"test_rule": "Test rule content"}}
            (shared_dir / "epistemic_rules.yaml").write_text(
                yaml.dump(epistemic), encoding="utf-8"
            )

            loader = SharedComponentLoader(shared_dir)
            components = loader.load()

            # Should load what exists
            assert "test_rule" in components.epistemic_rules
            # Others should be empty
            assert len(components.formatting_rules) == 0
            assert len(components.personas) == 0


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_shared_loader_singleton(self):
        """get_shared_loader should return singleton."""
        loader1 = get_shared_loader()
        loader2 = get_shared_loader()
        assert loader1 is loader2

    def test_load_shared_components(self):
        """load_shared_components should return components."""
        components = load_shared_components()
        assert isinstance(components, SharedComponents)


# =============================================================================
# Property-Based Tests
# =============================================================================


class TestSharedComponentLoaderProperties:
    """
    Property-based tests for SharedComponentLoader.

    **Feature: deep-research-prompt-architecture, Property 2: Shared Component Inclusion**
    **Validates: Requirements 2.1, 7.1, 7.2, 7.3, 7.4**
    """

    @given(
        rule_names=st.lists(
            st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True),
            min_size=1,
            max_size=5,
            unique=True,
        ),
        rule_contents=st.lists(
            st.text(min_size=1, max_size=100),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=50)
    def test_epistemic_rules_loaded_correctly(
        self, rule_names: list[str], rule_contents: list[str]
    ):
        """
        Property: For any valid epistemic rules YAML, all rules should be loaded.

        **Feature: deep-research-prompt-architecture, Property 2: Shared Component Inclusion**
        **Validates: Requirements 2.1, 7.1, 7.2, 7.3, 7.4**
        """
        # Ensure same length
        min_len = min(len(rule_names), len(rule_contents))
        rule_names = rule_names[:min_len]
        rule_contents = rule_contents[:min_len]

        # Build rules dict
        rules = dict(zip(rule_names, rule_contents))

        if not rules:
            return  # Skip if no valid rules

        with tempfile.TemporaryDirectory() as tmpdir:
            shared_dir = Path(tmpdir)
            epistemic = {"rules": rules}
            (shared_dir / "epistemic_rules.yaml").write_text(
                yaml.dump(epistemic), encoding="utf-8"
            )

            loader = SharedComponentLoader(shared_dir)
            components = loader.load()

            # Property: All rules should be loaded
            for name in rules:
                assert name in components.epistemic_rules
                assert components.epistemic_rules[name] == rules[name]


class TestFormattingRulesProperties:
    """
    Property-based tests for formatting rules loading.

    **Feature: deep-research-prompt-architecture, Property 3: Formatting Rules Inclusion**
    **Validates: Requirements 2.2, 8.1, 8.2, 8.3, 8.4, 8.5**
    """

    @given(
        rule_names=st.lists(
            st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True),
            min_size=1,
            max_size=5,
            unique=True,
        ),
        rule_contents=st.lists(
            st.text(min_size=1, max_size=100),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=50)
    def test_formatting_rules_loaded_correctly(
        self, rule_names: list[str], rule_contents: list[str]
    ):
        """
        Property: For any valid formatting rules YAML, all rules should be loaded.

        **Feature: deep-research-prompt-architecture, Property 3: Formatting Rules Inclusion**
        **Validates: Requirements 2.2, 8.1, 8.2, 8.3, 8.4, 8.5**
        """
        # Ensure same length
        min_len = min(len(rule_names), len(rule_contents))
        rule_names = rule_names[:min_len]
        rule_contents = rule_contents[:min_len]

        # Build rules dict
        rules = dict(zip(rule_names, rule_contents))

        if not rules:
            return  # Skip if no valid rules

        with tempfile.TemporaryDirectory() as tmpdir:
            shared_dir = Path(tmpdir)
            formatting = {"rules": rules}
            (shared_dir / "formatting.yaml").write_text(
                yaml.dump(formatting), encoding="utf-8"
            )

            loader = SharedComponentLoader(shared_dir)
            components = loader.load()

            # Property: All rules should be loaded
            for name in rules:
                assert name in components.formatting_rules
                assert components.formatting_rules[name] == rules[name]

    def test_required_formatting_rules_present(self):
        """
        Property: The default shared components should include all required formatting rules.

        **Feature: deep-research-prompt-architecture, Property 3: Formatting Rules Inclusion**
        **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**
        """
        loader = SharedComponentLoader()
        components = loader.load()

        # Required formatting rules per requirements
        required_rules = [
            "paragraphs",
            "bullets",
            "bullet_depth",
            "no_dashes",
            "citations",
            "tables",
        ]

        for rule in required_rules:
            assert rule in components.formatting_rules, f"Missing required rule: {rule}"
