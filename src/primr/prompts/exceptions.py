"""
Custom exceptions for the prompt architecture.

These exceptions provide clear error messages when prompt configuration
loading or validation fails, helping users diagnose and fix issues.
"""


class PromptConfigError(Exception):
    """Base exception for prompt configuration errors."""

    pass


class PromptConfigNotFoundError(PromptConfigError):
    """
    Raised when a prompt configuration file cannot be found.

    Attributes:
        prompt_name: Name of the prompt that was requested
        searched_paths: List of paths that were searched
        available_prompts: List of available prompt names
    """

    def __init__(
        self,
        prompt_name: str,
        searched_paths: list[str] | None = None,
        available_prompts: list[str] | None = None,
    ):
        self.prompt_name = prompt_name
        self.searched_paths = searched_paths or []
        self.available_prompts = available_prompts or []

        # Build helpful error message
        msg = f"Prompt configuration not found: '{prompt_name}'"

        if self.searched_paths:
            msg += f"\nSearched in: {', '.join(self.searched_paths)}"

        if self.available_prompts:
            msg += f"\nAvailable prompts: {', '.join(self.available_prompts)}"

        super().__init__(msg)


class PromptConfigValidationError(PromptConfigError):
    """
    Raised when a prompt configuration fails schema validation.

    Attributes:
        config_path: Path to the invalid configuration file
        errors: List of validation error messages
        field_name: Optional specific field that failed validation
    """

    def __init__(
        self,
        config_path: str,
        errors: list[str],
        field_name: str | None = None,
    ):
        self.config_path = config_path
        self.errors = errors
        self.field_name = field_name

        # Build helpful error message
        msg = f"Invalid prompt configuration: {config_path}"

        if field_name:
            msg += f"\nField: {field_name}"

        if errors:
            msg += "\nErrors:"
            for error in errors:
                msg += f"\n  - {error}"

        super().__init__(msg)


class StrategyModuleNotFoundError(PromptConfigError):
    """
    Raised when a strategy module cannot be found.

    Attributes:
        strategy_name: Name of the strategy that was requested
        available_strategies: List of available strategy names
    """

    def __init__(
        self,
        strategy_name: str,
        available_strategies: list[str] | None = None,
    ):
        self.strategy_name = strategy_name
        self.available_strategies = available_strategies or []

        msg = f"Strategy module not found: '{strategy_name}'"

        if self.available_strategies:
            msg += f"\nAvailable strategies: {', '.join(self.available_strategies)}"

        super().__init__(msg)


class DataSourceNotFoundError(PromptConfigError):
    """
    Raised when a required data source file cannot be found.

    Attributes:
        data_source_name: Name of the data source
        expected_path: Path where the file was expected
        strategy_name: Name of the strategy that requires this data source
    """

    def __init__(
        self,
        data_source_name: str,
        expected_path: str,
        strategy_name: str | None = None,
    ):
        self.data_source_name = data_source_name
        self.expected_path = expected_path
        self.strategy_name = strategy_name

        msg = f"Required data source not found: '{data_source_name}'"
        msg += f"\nExpected at: {expected_path}"

        if strategy_name:
            msg += f"\nRequired by strategy: {strategy_name}"

        super().__init__(msg)
