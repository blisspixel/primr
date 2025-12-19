"""
Prompt configuration and loading.

This module provides externalized prompt configurations stored in YAML files,
making prompts reviewable, versionable, and customizable.

Usage:
    from primr.prompts import PromptComposer, PromptContext
    
    # Compose a prompt
    composer = PromptComposer()
    context = PromptContext(company_name="Acme Corp", website_url="https://acme.com")
    prompt = composer.compose("company_overview", context)
    
    # List available strategies
    from primr.prompts import get_registry
    registry = get_registry()
    for name in registry.list_names():
        print(name)
"""

# Core classes
from primr.prompts.composer import (
    ComposedPrompt,
    PromptComposer,
    get_composer,
)
from primr.prompts.schema import (
    DataSource,
    PromptConfig,
    PromptContext,
    SectionSpec,
    SharedComponents,
    StrategyModule,
)

# Registry
from primr.prompts.registry import (
    StrategyModuleRegistry,
    get_registry,
    list_strategies,
)

# Exceptions
from primr.prompts.exceptions import (
    DataSourceNotFoundError,
    PromptConfigError,
    PromptConfigNotFoundError,
    PromptConfigValidationError,
    StrategyModuleNotFoundError,
)

# Backward compatibility - legacy loader functions
from primr.prompts.loader import (
    build_ai_strategy_prompt,
    build_company_overview_prompt,
    get_available_prompts,
    load_prompt_config,
)

__all__ = [
    # Core classes
    "PromptComposer",
    "PromptContext",
    "ComposedPrompt",
    "PromptConfig",
    "SectionSpec",
    "SharedComponents",
    "DataSource",
    "StrategyModule",
    # Registry
    "StrategyModuleRegistry",
    "get_registry",
    "list_strategies",
    "get_composer",
    # Exceptions
    "PromptConfigError",
    "PromptConfigNotFoundError",
    "PromptConfigValidationError",
    "StrategyModuleNotFoundError",
    "DataSourceNotFoundError",
    # Backward compatibility
    "load_prompt_config",
    "build_company_overview_prompt",
    "build_ai_strategy_prompt",
    "get_available_prompts",
]
