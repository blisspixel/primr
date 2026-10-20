"""Lazy compatibility exports for shared utilities.

Importing a terminal helper must not initialize research logging, asynchronous
workers, or prompt-sanitizer patterns. The console export remains eager because
its public singleton shares its name with the console submodule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from primr.utils.console import Console, console, get_console, set_console

if TYPE_CHECKING:
    from primr.utils.async_utils import (
        AsyncBridge,
        configure_executor,
        ensure_async,
        ensure_sync,
        gather_with_concurrency,
        is_async_context,
        run_async,
        run_async_with_timeout,
        run_sync,
        run_sync_new_loop,
        shutdown_executor,
        sync_context,
    )
    from primr.utils.chat_logger import log_chat_interaction
    from primr.utils.config_validation import (
        ConfigError,
        ConfigValidationResult,
        PrimrConfig,
        export_schema,
        load_config,
        require_valid_config,
        reset_config,
        validate_config,
    )
    from primr.utils.content_sanitizer import (
        ContentSanitizer,
        IssueType,
        SanitizationIssue,
        SanitizationMode,
        SanitizationResult,
        fence_untrusted,
        sanitize_for_llm,
    )
    from primr.utils.errors import (
        AIError,
        AuthenticationError,
        ConfigurationError,
        ErrorContext,
        OutputError,
        PermanentError,
        PrimrConfigurationError,
        PrimrError,
        PrimrValidationError,
        QuotaError,
        ResearchError,
        RetryConfig,
        ScrapingError,
        SearchError,
        TransientError,
        TypedNetworkError,
        TypedRateLimitError,
        ValidationError,
        async_safe_callback,
        calculate_backoff_delay,
        error_context,
        retry_on_failure,
        safe_call,
    )
    from primr.utils.files import (
        ensure_parent_exists,
        get_cache_key,
        get_cache_path,
        get_company_folder,
        get_safe_path,
        sanitize_filename,
        secure_temp_dir,
        secure_temp_file,
        validate_directory_exists,
        validate_file_exists,
    )
    from primr.utils.formatting import (
        clean_content,
        format_currency,
        format_number,
        remove_em_dashes,
        remove_emojis,
    )
    from primr.utils.logging_config import LogContext, get_logger, setup_logging
    from primr.utils.observability import (
        Metrics,
        OperationContext,
        emit_metrics,
        get_correlation_id,
        operation_context,
        set_correlation_id,
        timed,
        tracked_operation,
    )
    from primr.utils.resources import (
        BoundedCache,
        CacheMetrics,
        ThreadSafeSingleton,
        managed_http_client,
        managed_temp_dir,
        managed_temp_file,
    )
    from primr.utils.retry import RetryAttempt, RetryPolicy, RetryPolicyManager
    from primr.utils.security import (
        SecurityAuditLogger,
        generate_secure_id,
        generate_secure_token,
        get_secret_from_env,
        hash_secret,
        mask_dict_values,
        mask_sensitive_data,
        sanitize_log_input,
        secure_compare,
        verify_hashed_secret,
    )
    from primr.utils.type_guards import (
        TypeValidationError,
        is_valid_type,
        validate_api_response,
        validate_dataclass,
        validate_type,
    )
    from primr.utils.validators import (
        InputValidationError,
        safe_json_get,
        safe_json_parse,
        sanitize_for_filename,
        validate_company_name,
        validate_file_path,
        validate_url,
    )

_EXPORT_GROUPS = {
    "primr.utils.async_utils": (
        "AsyncBridge",
        "configure_executor",
        "ensure_async",
        "ensure_sync",
        "gather_with_concurrency",
        "is_async_context",
        "run_async",
        "run_async_with_timeout",
        "run_sync",
        "run_sync_new_loop",
        "shutdown_executor",
        "sync_context",
    ),
    "primr.utils.chat_logger": ("log_chat_interaction",),
    "primr.utils.config_validation": (
        "ConfigError",
        "ConfigValidationResult",
        "PrimrConfig",
        "export_schema",
        "load_config",
        "require_valid_config",
        "reset_config",
        "validate_config",
    ),
    "primr.utils.content_sanitizer": (
        "ContentSanitizer",
        "IssueType",
        "SanitizationIssue",
        "SanitizationMode",
        "SanitizationResult",
        "fence_untrusted",
        "sanitize_for_llm",
    ),
    "primr.utils.errors": (
        "AIError",
        "AuthenticationError",
        "ConfigurationError",
        "ErrorContext",
        "OutputError",
        "PermanentError",
        "PrimrConfigurationError",
        "PrimrError",
        "PrimrValidationError",
        "QuotaError",
        "ResearchError",
        "RetryConfig",
        "ScrapingError",
        "SearchError",
        "TransientError",
        "TypedNetworkError",
        "TypedRateLimitError",
        "ValidationError",
        "async_safe_callback",
        "calculate_backoff_delay",
        "error_context",
        "retry_on_failure",
        "safe_call",
    ),
    "primr.utils.files": (
        "ensure_parent_exists",
        "get_cache_key",
        "get_cache_path",
        "get_company_folder",
        "get_safe_path",
        "sanitize_filename",
        "secure_temp_dir",
        "secure_temp_file",
        "validate_directory_exists",
        "validate_file_exists",
    ),
    "primr.utils.formatting": (
        "clean_content",
        "format_currency",
        "format_number",
        "remove_em_dashes",
        "remove_emojis",
    ),
    "primr.utils.logging_config": ("LogContext", "get_logger", "setup_logging"),
    "primr.utils.observability": (
        "Metrics",
        "OperationContext",
        "emit_metrics",
        "get_correlation_id",
        "operation_context",
        "set_correlation_id",
        "timed",
        "tracked_operation",
    ),
    "primr.utils.resources": (
        "BoundedCache",
        "CacheMetrics",
        "ThreadSafeSingleton",
        "managed_http_client",
        "managed_temp_dir",
        "managed_temp_file",
    ),
    "primr.utils.retry": ("RetryAttempt", "RetryPolicy", "RetryPolicyManager"),
    "primr.utils.security": (
        "SecurityAuditLogger",
        "generate_secure_id",
        "generate_secure_token",
        "get_secret_from_env",
        "hash_secret",
        "mask_dict_values",
        "mask_sensitive_data",
        "sanitize_log_input",
        "secure_compare",
        "verify_hashed_secret",
    ),
    "primr.utils.type_guards": (
        "TypeValidationError",
        "is_valid_type",
        "validate_api_response",
        "validate_dataclass",
        "validate_type",
    ),
    "primr.utils.validators": (
        "InputValidationError",
        "safe_json_get",
        "safe_json_parse",
        "sanitize_for_filename",
        "validate_company_name",
        "validate_file_path",
        "validate_url",
    ),
}
_LAZY_EXPORTS = {name: module for module, names in _EXPORT_GROUPS.items() for name in names}


def __getattr__(name: str) -> Any:
    """Resolve a public compatibility export through its owning module once."""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "AIError",
    "AsyncBridge",
    "AuthenticationError",
    "BoundedCache",
    "CacheMetrics",
    # Configuration validation
    "ConfigError",
    "ConfigValidationResult",
    "ConfigurationError",
    # Console
    "Console",
    # Content Sanitization (LLM prompt injection protection)
    "ContentSanitizer",
    "ErrorContext",
    # Validators
    "InputValidationError",
    "IssueType",
    "LogContext",
    "Metrics",
    "OperationContext",
    "OutputError",
    "PermanentError",
    "PrimrConfig",
    "PrimrConfigurationError",
    # Typed error hierarchy (preferred for new code)
    "PrimrError",
    "PrimrValidationError",
    "QuotaError",
    # Legacy errors (deprecated - use typed hierarchy)
    "ResearchError",
    "RetryAttempt",
    "RetryConfig",
    # Retry Policy Manager
    "RetryPolicy",
    "RetryPolicyManager",
    "SanitizationIssue",
    "SanitizationMode",
    "SanitizationResult",
    "ScrapingError",
    "SearchError",
    "SecurityAuditLogger",
    "ThreadSafeSingleton",
    "TransientError",
    # Type Guards
    "TypeValidationError",
    "TypedNetworkError",
    "TypedRateLimitError",
    "ValidationError",
    "async_safe_callback",
    "calculate_backoff_delay",
    # Formatting
    "clean_content",
    "configure_executor",
    "console",
    "emit_metrics",
    "ensure_async",
    "ensure_parent_exists",
    "ensure_sync",
    "error_context",
    "export_schema",
    "fence_untrusted",
    "format_currency",
    "format_number",
    "gather_with_concurrency",
    "generate_secure_id",
    "generate_secure_token",
    "get_cache_key",
    "get_cache_path",
    "get_company_folder",
    "get_console",
    # Observability
    "get_correlation_id",
    "get_logger",
    "get_safe_path",
    "get_secret_from_env",
    "hash_secret",
    "is_async_context",
    "is_valid_type",
    "load_config",
    "log_chat_interaction",
    "managed_http_client",
    "managed_temp_dir",
    # Resources
    "managed_temp_file",
    "mask_dict_values",
    "mask_sensitive_data",
    "operation_context",
    "remove_em_dashes",
    "remove_emojis",
    "require_valid_config",
    "reset_config",
    "retry_on_failure",
    "run_async",
    "run_async_with_timeout",
    # Async utilities
    "run_sync",
    "run_sync_new_loop",
    "safe_call",
    "safe_json_get",
    "safe_json_parse",
    "sanitize_filename",
    "sanitize_for_filename",
    "sanitize_for_llm",
    "sanitize_log_input",
    # Security
    "secure_compare",
    "secure_temp_dir",
    # Files
    "secure_temp_file",
    "set_console",
    "set_correlation_id",
    # Logging
    "setup_logging",
    "shutdown_executor",
    "sync_context",
    "timed",
    "tracked_operation",
    "validate_api_response",
    "validate_company_name",
    "validate_config",
    "validate_dataclass",
    "validate_directory_exists",
    "validate_file_exists",
    "validate_file_path",
    "validate_type",
    "validate_url",
    "verify_hashed_secret",
]
