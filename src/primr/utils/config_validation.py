"""
Unified Configuration Validation with Pydantic.

This module provides a centralized configuration validation system that:
- Validates all configuration at startup with clear error messages
- Supports environment variables, .env files, and YAML configs
- Provides JSON Schema export for documentation
- Handles configuration migration between versions

**Feature: code-quality-improvements**

Usage:
    from primr.utils.config_validation import (
        PrimrConfig,
        load_config,
        validate_config,
        export_schema,
    )

    # Load and validate configuration
    config = load_config()

    # Or validate explicitly
    errors = validate_config()
    if errors:
        print("Configuration errors:", errors)

    # Export JSON Schema for documentation
    schema = export_schema()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from primr.config.env import load_primr_env

logger = logging.getLogger(__name__)

# Load environment variables
load_primr_env()


# =============================================================================
# VALIDATION ERROR TYPES
# =============================================================================


@dataclass
class ConfigError:
    """A single configuration error."""

    field: str
    message: str
    value: Any = None
    suggestion: str | None = None

    def __str__(self) -> str:
        msg = f"{self.field}: {self.message}"
        if self.value is not None:
            msg += f" (got: {self.value!r})"
        if self.suggestion:
            msg += f"\n  Suggestion: {self.suggestion}"
        return msg


@dataclass
class ConfigValidationResult:
    """Result of configuration validation."""

    valid: bool
    errors: list[ConfigError] = field(default_factory=list)
    warnings: list[ConfigError] = field(default_factory=list)

    def __str__(self) -> str:
        if self.valid and not self.warnings:
            return "Configuration valid"

        parts = []
        if self.errors:
            parts.append(f"Errors ({len(self.errors)}):")
            for e in self.errors:
                parts.append(f"  - {e}")
        if self.warnings:
            parts.append(f"Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                parts.append(f"  - {w}")
        return "\n".join(parts)


# =============================================================================
# CONFIGURATION MODELS (Pydantic-style validation without Pydantic dependency)
# =============================================================================


@dataclass
class APIKeysConfig:
    """API keys configuration with lazy validation."""

    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    xai_api_key: str | None = field(default_factory=lambda: os.getenv("XAI_API_KEY"))
    search_api_key: str | None = field(default_factory=lambda: os.getenv("SEARCH_API_KEY"))
    search_engine_id: str | None = field(default_factory=lambda: os.getenv("SEARCH_ENGINE_ID"))

    def validate(self) -> list[ConfigError]:
        """Validate API keys are present."""
        errors = []

        if not self.gemini_api_key and not self.xai_api_key:
            errors.append(
                ConfigError(
                    field="GEMINI_API_KEY/XAI_API_KEY",
                    message="No model provider key set",
                    suggestion=(
                        "Run 'primr init' for guided setup (paste keys, no .env editing), "
                        "or 'primr keys set gemini' / 'primr keys set xai' to add one directly"
                    ),
                )
            )

        if self.gemini_api_key and len(self.gemini_api_key) < 10:
            errors.append(
                ConfigError(
                    field="GEMINI_API_KEY",
                    message="API key appears too short",
                    value=f"{self.gemini_api_key[:4]}...",
                    suggestion="Check that the full API key is provided",
                )
            )

        if self.xai_api_key and len(self.xai_api_key) < 10:
            errors.append(
                ConfigError(
                    field="XAI_API_KEY",
                    message="API key appears too short",
                    value=f"{self.xai_api_key[:4]}...",
                    suggestion="Check that the full API key is provided",
                )
            )

        return errors

    def get_warnings(self) -> list[ConfigError]:
        """Get warnings for optional but recommended keys."""
        warnings = []

        if not self.xai_api_key:
            warnings.append(
                ConfigError(
                    field="XAI_API_KEY",
                    message="Recommended key not set (Grok standard pipeline disabled)",
                    suggestion="Run 'primr keys set xai'",
                )
            )

        if not self.gemini_api_key:
            warnings.append(
                ConfigError(
                    field="GEMINI_API_KEY",
                    message="Gemini-backed premium and scrape summary stages disabled",
                    suggestion="Run 'primr keys set gemini'",
                )
            )

        if not self.search_api_key:
            warnings.append(
                ConfigError(
                    field="SEARCH_API_KEY",
                    message="Optional key not set (Google Search disabled)",
                    suggestion="Add SEARCH_API_KEY for external source validation",
                )
            )

        if not self.search_engine_id:
            warnings.append(
                ConfigError(
                    field="SEARCH_ENGINE_ID",
                    message="Optional key not set (Google Search disabled)",
                    suggestion="Add SEARCH_ENGINE_ID for external source validation",
                )
            )

        return warnings


@dataclass
class TimeoutsConfig:
    """Timeout configuration with validation."""

    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    total_timeout: float = 60.0
    scrape_timeout: float = 45.0
    ai_timeout: float = 120.0

    def validate(self) -> list[ConfigError]:
        """Validate timeout values."""
        errors = []

        for name, value in [
            ("connect_timeout", self.connect_timeout),
            ("read_timeout", self.read_timeout),
            ("total_timeout", self.total_timeout),
            ("scrape_timeout", self.scrape_timeout),
            ("ai_timeout", self.ai_timeout),
        ]:
            if value <= 0:
                errors.append(
                    ConfigError(field=name, message="Timeout must be positive", value=value)
                )
            elif value > 600:
                errors.append(
                    ConfigError(
                        field=name,
                        message="Timeout exceeds maximum (600s)",
                        value=value,
                        suggestion="Use a timeout <= 600 seconds",
                    )
                )

        if self.total_timeout < self.connect_timeout:
            errors.append(
                ConfigError(
                    field="total_timeout",
                    message="Must be >= connect_timeout",
                    value=self.total_timeout,
                )
            )

        return errors


@dataclass
class RetryConfig:
    """Retry configuration with validation."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter_factor: float = 0.1

    def validate(self) -> list[ConfigError]:
        """Validate retry configuration."""
        errors = []

        if self.max_retries < 0:
            errors.append(
                ConfigError(
                    field="max_retries", message="Must be non-negative", value=self.max_retries
                )
            )
        elif self.max_retries > 10:
            errors.append(
                ConfigError(
                    field="max_retries",
                    message="Exceeds maximum (10)",
                    value=self.max_retries,
                    suggestion="Use max_retries <= 10 to avoid excessive delays",
                )
            )

        if self.base_delay <= 0:
            errors.append(
                ConfigError(field="base_delay", message="Must be positive", value=self.base_delay)
            )

        if self.max_delay <= 0:
            errors.append(
                ConfigError(field="max_delay", message="Must be positive", value=self.max_delay)
            )

        if self.exponential_base <= 1:
            errors.append(
                ConfigError(
                    field="exponential_base", message="Must be > 1", value=self.exponential_base
                )
            )

        if not 0 <= self.jitter_factor <= 1:
            errors.append(
                ConfigError(
                    field="jitter_factor",
                    message="Must be between 0 and 1",
                    value=self.jitter_factor,
                )
            )

        return errors


@dataclass
class ScrapingConfig:
    """Scraping configuration with validation."""

    max_pages: int = 100
    max_depth: int = 2
    min_content_length: int = 100
    enable_vision: bool = True
    circuit_breaker_threshold: int = 5

    def validate(self) -> list[ConfigError]:
        """Validate scraping configuration."""
        errors = []

        if self.max_pages <= 0:
            errors.append(
                ConfigError(field="max_pages", message="Must be positive", value=self.max_pages)
            )
        elif self.max_pages > 500:
            errors.append(
                ConfigError(
                    field="max_pages",
                    message="Exceeds recommended maximum (500)",
                    value=self.max_pages,
                    suggestion="Large page counts increase cost and time significantly",
                )
            )

        if self.max_depth < 0:
            errors.append(
                ConfigError(field="max_depth", message="Must be non-negative", value=self.max_depth)
            )

        if self.min_content_length < 0:
            errors.append(
                ConfigError(
                    field="min_content_length",
                    message="Must be non-negative",
                    value=self.min_content_length,
                )
            )

        if self.circuit_breaker_threshold < 1:
            errors.append(
                ConfigError(
                    field="circuit_breaker_threshold",
                    message="Must be at least 1",
                    value=self.circuit_breaker_threshold,
                )
            )

        return errors


@dataclass
class AIConfig:
    """AI model configuration with validation."""

    fast_model: str = "gemini-2.0-flash"
    reasoning_model: str = "gemini-2.5-pro-preview-06-05"
    temperature: float = 1.0
    thinking_level: Literal["low", "high"] = "high"
    grade_threshold: int = 70

    def validate(self) -> list[ConfigError]:
        """Validate AI configuration."""
        errors = []

        if not self.fast_model or not self.fast_model.strip():
            errors.append(ConfigError(field="fast_model", message="Model name cannot be empty"))

        if not self.reasoning_model or not self.reasoning_model.strip():
            errors.append(
                ConfigError(field="reasoning_model", message="Model name cannot be empty")
            )

        if not 0.0 <= self.temperature <= 2.0:
            errors.append(
                ConfigError(
                    field="temperature",
                    message="Must be between 0.0 and 2.0",
                    value=self.temperature,
                )
            )

        if self.thinking_level not in ("low", "high"):
            errors.append(
                ConfigError(
                    field="thinking_level",
                    message="Must be 'low' or 'high'",
                    value=self.thinking_level,
                )
            )

        if not 0 <= self.grade_threshold <= 100:
            errors.append(
                ConfigError(
                    field="grade_threshold",
                    message="Must be between 0 and 100",
                    value=self.grade_threshold,
                )
            )

        return errors


@dataclass
class PathsConfig:
    """Path configuration with validation."""

    project_root: Path = field(default_factory=Path.cwd)
    output_dir: Path = field(init=False)
    working_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)

    def __post_init__(self):
        self.output_dir = self.project_root / "output"
        self.working_dir = self.project_root / "working"
        self.logs_dir = self.project_root / "logs"

    def validate(self) -> list[ConfigError]:
        """Validate paths are writable."""
        errors = []

        for name, path in [
            ("output_dir", self.output_dir),
            ("working_dir", self.working_dir),
            ("logs_dir", self.logs_dir),
        ]:
            # Try to create directory
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(
                    ConfigError(
                        field=name, message=f"Cannot create directory: {e}", value=str(path)
                    )
                )
                continue

            # Test write permission with a symlink-safe probe. The prior
            # implementation wrote to a predictable .primr_write_test path
            # via Path.write_text, which followed any pre-existing symlink
            # and clobbered the target file.
            from primr.utils.fs_safety import check_dir_writable

            ok, why = check_dir_writable(path)
            if not ok:
                errors.append(
                    ConfigError(
                        field=name,
                        message=f"Directory not writable: {why}",
                        value=str(path),
                    )
                )

        return errors


# =============================================================================
# MAIN CONFIGURATION CLASS
# =============================================================================


@dataclass
class PrimrConfig:
    """
    Main Primr configuration container.

    Aggregates all configuration sections and provides unified validation.

    Example:
        config = PrimrConfig()
        result = config.validate()
        if not result.valid:
            print(result)
            sys.exit(1)
    """

    api_keys: APIKeysConfig = field(default_factory=APIKeysConfig)
    timeouts: TimeoutsConfig = field(default_factory=TimeoutsConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    # Schema version for migration support
    schema_version: str = "1.0.0"

    def validate(self, include_api_keys: bool = True) -> ConfigValidationResult:
        """
        Validate all configuration.

        Args:
            include_api_keys: If True, validate API keys are present

        Returns:
            ConfigValidationResult with errors and warnings
        """
        errors: list[ConfigError] = []
        warnings: list[ConfigError] = []

        # Validate each section
        if include_api_keys:
            errors.extend(self.api_keys.validate())
            warnings.extend(self.api_keys.get_warnings())

        errors.extend(self.timeouts.validate())
        errors.extend(self.retry.validate())
        errors.extend(self.scraping.validate())
        errors.extend(self.ai.validate())
        errors.extend(self.paths.validate())

        return ConfigValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def to_dict(self) -> dict[str, Any]:
        """Export configuration as dictionary (excluding secrets)."""
        return {
            "schema_version": self.schema_version,
            "timeouts": {
                "connect_timeout": self.timeouts.connect_timeout,
                "read_timeout": self.timeouts.read_timeout,
                "total_timeout": self.timeouts.total_timeout,
                "scrape_timeout": self.timeouts.scrape_timeout,
                "ai_timeout": self.timeouts.ai_timeout,
            },
            "retry": {
                "max_retries": self.retry.max_retries,
                "base_delay": self.retry.base_delay,
                "max_delay": self.retry.max_delay,
                "exponential_base": self.retry.exponential_base,
                "jitter_factor": self.retry.jitter_factor,
            },
            "scraping": {
                "max_pages": self.scraping.max_pages,
                "max_depth": self.scraping.max_depth,
                "min_content_length": self.scraping.min_content_length,
                "enable_vision": self.scraping.enable_vision,
                "circuit_breaker_threshold": self.scraping.circuit_breaker_threshold,
            },
            "ai": {
                "fast_model": self.ai.fast_model,
                "reasoning_model": self.ai.reasoning_model,
                "temperature": self.ai.temperature,
                "thinking_level": self.ai.thinking_level,
                "grade_threshold": self.ai.grade_threshold,
            },
            "paths": {
                "output_dir": str(self.paths.output_dir),
                "working_dir": str(self.paths.working_dir),
                "logs_dir": str(self.paths.logs_dir),
            },
            "api_keys_configured": {
                "gemini": bool(self.api_keys.gemini_api_key),
                "xai": bool(self.api_keys.xai_api_key),
                "search": bool(self.api_keys.search_api_key),
                "search_engine": bool(self.api_keys.search_engine_id),
            },
        }


# =============================================================================
# MODULE-LEVEL FUNCTIONS
# =============================================================================

_config: PrimrConfig | None = None


def load_config(project_root: Path | None = None) -> PrimrConfig:
    """
    Load and cache configuration.

    Args:
        project_root: Override project root path

    Returns:
        PrimrConfig instance
    """
    global _config

    if _config is None or project_root is not None:
        paths = PathsConfig(project_root=project_root) if project_root else PathsConfig()
        _config = PrimrConfig(paths=paths)

    return _config


def validate_config(include_api_keys: bool = True) -> ConfigValidationResult:
    """
    Validate current configuration.

    Args:
        include_api_keys: If True, validate API keys are present

    Returns:
        ConfigValidationResult with errors and warnings
    """
    config = load_config()
    return config.validate(include_api_keys=include_api_keys)


def require_valid_config(include_api_keys: bool = True) -> PrimrConfig:
    """
    Require valid configuration, raising if invalid.

    Args:
        include_api_keys: If True, validate API keys are present

    Returns:
        Valid PrimrConfig instance

    Raises:
        ValueError: If configuration is invalid
    """
    config = load_config()
    result = config.validate(include_api_keys=include_api_keys)

    if not result.valid:
        raise ValueError(f"Configuration validation failed:\n{result}")

    return config


def reset_config() -> None:
    """Reset configuration cache (useful for testing)."""
    global _config
    _config = None


def export_schema() -> dict[str, Any]:
    """
    Export configuration schema as JSON Schema.

    Returns:
        JSON Schema dictionary
    """
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "PrimrConfig",
        "description": "Primr configuration schema",
        "type": "object",
        "properties": {
            "schema_version": {
                "type": "string",
                "description": "Configuration schema version",
                "default": "1.0.0",
            },
            "timeouts": {
                "type": "object",
                "properties": {
                    "connect_timeout": {"type": "number", "minimum": 0, "default": 10.0},
                    "read_timeout": {"type": "number", "minimum": 0, "default": 30.0},
                    "total_timeout": {"type": "number", "minimum": 0, "default": 60.0},
                    "scrape_timeout": {"type": "number", "minimum": 0, "default": 45.0},
                    "ai_timeout": {"type": "number", "minimum": 0, "default": 120.0},
                },
            },
            "retry": {
                "type": "object",
                "properties": {
                    "max_retries": {"type": "integer", "minimum": 0, "maximum": 10, "default": 3},
                    "base_delay": {"type": "number", "minimum": 0, "default": 1.0},
                    "max_delay": {"type": "number", "minimum": 0, "default": 60.0},
                    "exponential_base": {"type": "number", "minimum": 1, "default": 2.0},
                    "jitter_factor": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.1},
                },
            },
            "scraping": {
                "type": "object",
                "properties": {
                    "max_pages": {"type": "integer", "minimum": 1, "default": 100},
                    "max_depth": {"type": "integer", "minimum": 0, "default": 2},
                    "min_content_length": {"type": "integer", "minimum": 0, "default": 100},
                    "enable_vision": {"type": "boolean", "default": True},
                    "circuit_breaker_threshold": {"type": "integer", "minimum": 1, "default": 5},
                },
            },
            "ai": {
                "type": "object",
                "properties": {
                    "fast_model": {"type": "string", "default": "gemini-2.0-flash"},
                    "reasoning_model": {
                        "type": "string",
                        "default": "gemini-2.5-pro-preview-06-05",
                    },
                    "temperature": {"type": "number", "minimum": 0, "maximum": 2, "default": 1.0},
                    "thinking_level": {
                        "type": "string",
                        "enum": ["low", "high"],
                        "default": "high",
                    },
                    "grade_threshold": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "default": 80,
                    },
                },
            },
        },
        "required": ["schema_version"],
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "AIConfig",
    # Config sections
    "APIKeysConfig",
    # Error types
    "ConfigError",
    "ConfigValidationResult",
    "PathsConfig",
    # Main config
    "PrimrConfig",
    "RetryConfig",
    "ScrapingConfig",
    "TimeoutsConfig",
    "export_schema",
    # Functions
    "load_config",
    "require_valid_config",
    "reset_config",
    "validate_config",
]
