"""
Tests for the StrategyModuleRegistry.

Includes property tests for strategy discovery and data source filtering.
"""

from pathlib import Path

import yaml

from primr.prompts.registry import (
    StrategyModuleRegistry,
    get_registry,
    list_strategies,
)
from primr.prompts.schema import DataSource, StrategyModule


class TestStrategyModuleRegistry:
    """Tests for StrategyModuleRegistry class."""

    def test_discover_returns_list(self):
        """Should return a list of strategy modules."""
        registry = StrategyModuleRegistry()
        strategies = registry.discover()
        assert isinstance(strategies, list)

    def test_discover_finds_ai_strategy(self):
        """Should discover the AI strategy module."""
        registry = StrategyModuleRegistry()
        strategies = registry.discover()
        names = [s.name for s in strategies]
        assert "ai" in names

    def test_discover_finds_placeholder_strategies(self):
        """Should discover placeholder strategy modules."""
        registry = StrategyModuleRegistry()
        strategies = registry.discover()
        names = [s.name for s in strategies]
        assert "cloud_migration" in names
        assert "data" in names or "data_strategy" in names

    def test_get_returns_strategy_module(self):
        """Should return a StrategyModule for valid name."""
        registry = StrategyModuleRegistry()
        strategy = registry.get("ai")
        assert strategy is not None
        assert isinstance(strategy, StrategyModule)
        assert strategy.name == "ai"

    def test_get_returns_none_for_invalid(self):
        """Should return None for invalid strategy name."""
        registry = StrategyModuleRegistry()
        strategy = registry.get("nonexistent_strategy_xyz")
        assert strategy is None

    def test_list_names_returns_sorted_list(self):
        """Should return a sorted list of strategy names."""
        registry = StrategyModuleRegistry()
        names = registry.list_names()
        assert isinstance(names, list)
        assert names == sorted(names)
        assert "ai" in names

    def test_reload_clears_cache(self):
        """Should clear cache and rediscover modules."""
        registry = StrategyModuleRegistry()

        # First discovery
        strategies1 = registry.discover()

        # Reload
        strategies2 = registry.reload()

        # Should have same strategies
        assert len(strategies1) == len(strategies2)

    def test_get_context_files_returns_paths(self):
        """Should return list of paths for context files."""
        registry = StrategyModuleRegistry()
        files = registry.get_context_files("ai", vendor="azure")
        assert isinstance(files, list)
        # All returned paths should exist
        for path in files:
            assert path.exists()

    def test_get_context_files_filters_by_vendor(self):
        """Should filter context files by vendor."""
        registry = StrategyModuleRegistry()

        azure_files = registry.get_context_files("ai", vendor="azure")
        aws_files = registry.get_context_files("ai", vendor="aws")

        # Azure and AWS files should be different
        azure_names = [f.name for f in azure_files]
        aws_names = [f.name for f in aws_files]

        # At least one file should be vendor-specific
        if azure_files and aws_files:
            assert azure_names != aws_names or len(azure_files) != len(aws_files)


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_registry_returns_singleton(self):
        """Should return the same registry instance."""
        registry1 = get_registry()
        registry2 = get_registry()
        assert registry1 is registry2

    def test_list_strategies_returns_names(self):
        """Should return list of strategy names."""
        names = list_strategies()
        assert isinstance(names, list)
        assert "ai" in names


class TestStrategyDiscoveryProperties:
    """Property tests for strategy module discovery (Property 9)."""

    def test_all_discovered_strategies_have_required_fields(self):
        """All discovered strategies should have required fields."""
        registry = StrategyModuleRegistry()
        strategies = registry.discover()

        for strategy in strategies:
            assert strategy.name, "Strategy missing name"
            assert strategy.display_name, f"Strategy {strategy.name} missing display_name"
            assert strategy.config_path.exists(), f"Strategy {strategy.name} config not found"

    def test_discovered_strategies_are_unique(self):
        """All discovered strategy names should be unique."""
        registry = StrategyModuleRegistry()
        strategies = registry.discover()
        names = [s.name for s in strategies]
        assert len(names) == len(set(names)), "Duplicate strategy names found"

    def test_strategy_configs_are_valid_yaml(self):
        """All strategy config files should be valid YAML."""
        registry = StrategyModuleRegistry()
        strategies = registry.discover()

        for strategy in strategies:
            with open(strategy.config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict), f"Strategy {strategy.name} config is not a dict"
            assert "meta" in data, f"Strategy {strategy.name} missing meta section"


class TestDataSourceVendorFilteringProperties:
    """Property tests for data source vendor filtering (Property 19)."""

    def test_vendor_specific_sources_filtered_correctly(self):
        """Vendor-specific data sources should only match their vendor."""
        ds_azure = DataSource(
            name="azure_research",
            path="docs/azure.txt",
            vendor="azure",
        )
        ds_aws = DataSource(
            name="aws_research",
            path="docs/aws.txt",
            vendor="aws",
        )
        ds_agnostic = DataSource(
            name="agnostic_research",
            path="docs/agnostic.txt",
            vendor=None,
        )

        # Azure source matches azure only
        assert ds_azure.matches_vendor("azure")
        assert not ds_azure.matches_vendor("aws")
        assert not ds_azure.matches_vendor("gcp")

        # AWS source matches aws only
        assert ds_aws.matches_vendor("aws")
        assert not ds_aws.matches_vendor("azure")

        # Agnostic source matches all vendors
        assert ds_agnostic.matches_vendor("azure")
        assert ds_agnostic.matches_vendor("aws")
        assert ds_agnostic.matches_vendor("gcp")
        assert ds_agnostic.matches_vendor(None)

    def test_case_insensitive_vendor_matching(self):
        """Vendor matching should be case-insensitive."""
        ds = DataSource(
            name="test",
            path="test.txt",
            vendor="Azure",
        )

        assert ds.matches_vendor("azure")
        assert ds.matches_vendor("AZURE")
        assert ds.matches_vendor("Azure")

    def test_ai_strategy_has_vendor_data_sources(self):
        """AI strategy should have vendor-specific data sources."""
        registry = StrategyModuleRegistry()
        strategy = registry.get("ai")

        assert strategy is not None
        assert len(strategy.data_sources) > 0

        # Should have sources for multiple vendors
        vendors = [ds.vendor for ds in strategy.data_sources if ds.vendor]
        assert "azure" in vendors
        assert "aws" in vendors
        assert "gcp" in vendors


class TestDataSourcePathResolution:
    """Tests for data source path resolution."""

    def test_resolve_path_relative_to_base(self):
        """Should resolve path relative to base directory."""
        ds = DataSource(
            name="test",
            path="docs/test.txt",
        )
        base = Path("/project")
        resolved = ds.resolve_path(base)
        assert resolved == Path("/project/docs/test.txt")

    def test_exists_checks_resolved_path(self, tmp_path):
        """Should check if resolved path exists."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        ds = DataSource(
            name="test",
            path="test.txt",
        )

        assert ds.exists(tmp_path)
        assert not ds.exists(tmp_path / "nonexistent")
