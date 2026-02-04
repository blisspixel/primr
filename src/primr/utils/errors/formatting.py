"""
Error formatting utilities.

This module provides utilities for formatting errors for user display
and extracting guidance from exceptions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from primr.utils.errors.base import CATEGORY_GUIDANCE, EXCEPTION_TYPE_GUIDANCE

if TYPE_CHECKING:
    from primr.utils.errors.typed import PrimrError


def format_error_for_user(error: Exception, verbose: bool = False) -> str:
    """
    Format an error for user display.

    Args:
        error: The exception to format
        verbose: If True, include debug details

    Returns:
        Formatted error string suitable for console output
    """
    # Import here to avoid circular imports
    from primr.utils.errors.typed import PrimrError

    if isinstance(error, PrimrError):
        if verbose:
            return error.debug_message()
        return error.user_message()

    # For non-PrimrError exceptions, provide generic formatting
    error_type = type(error).__name__
    message = str(error)

    if verbose:
        return f"[error] {error_type}: {message}"
    return message


def get_error_guidance(error: Exception) -> str | None:
    """
    Get actionable guidance for an error.

    Args:
        error: The exception to get guidance for

    Returns:
        Guidance string or None if no guidance available
    """
    # Import here to avoid circular imports
    from primr.utils.errors.typed import PrimrError

    # For typed errors, return the guidance attribute if set
    if isinstance(error, PrimrError):
        if error.guidance:
            return error.guidance
        # Fall back to category-based guidance
        return CATEGORY_GUIDANCE.get(error.category)

    # Common error type guidance
    return EXCEPTION_TYPE_GUIDANCE.get(type(error).__name__)


def is_recoverable_error(error: Exception) -> bool:
    """
    Check if an error is recoverable (can be retried).

    Args:
        error: The exception to check

    Returns:
        True if the error is recoverable
    """
    # Import here to avoid circular imports
    from primr.utils.errors.typed import PrimrError

    if isinstance(error, PrimrError):
        return error.recoverable

    # Common recoverable error types
    recoverable_types = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    return isinstance(error, recoverable_types)
