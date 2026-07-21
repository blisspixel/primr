"""Tests for provider-key requirements at the CLI command boundary."""

from types import SimpleNamespace

from primr.core.cli_validation_policy import should_include_api_keys


def test_vendor_research_dry_run_is_keyless():
    config = SimpleNamespace(command="generate-vendor", dry_run_requested=True)
    assert should_include_api_keys(config) is False


def test_vendor_research_execution_uses_its_specific_structured_preflight():
    config = SimpleNamespace(command="generate-vendor", dry_run_requested=False)
    assert should_include_api_keys(config) is False


def test_research_execution_still_requires_provider_configuration():
    config = SimpleNamespace(command="research", dry_run_requested=False)
    assert should_include_api_keys(config) is True
