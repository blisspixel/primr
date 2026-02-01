"""
Defensive programming utilities for bulletproof code.

This module provides:
- Safe dictionary access with type validation
- Null-safe operations
- Bounded numeric validation
- Safe string operations
- Resource cleanup helpers

Usage:
    from primr.utils.defensive import safe_get, safe_int, require_not_none
    
    # Safe dictionary access
    value = safe_get(data, "key", default="fallback")
    
    # Safe integer parsing
    num = safe_int(user_input, default=0, min_val=0, max_val=100)
    
    # Require non-null
    config = require_not_none(get_config(), "Configuration is required")
"""

import logging
from typing import Any, TypeVar, Callable, Optional
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')
V = TypeVar('V')


# =============================================================================
# SAFE DICTIONARY ACCESS
# =============================================================================

def safe_get(
    data: dict[str, Any] | None,
    key: str,
    default: T = None,
    expected_type: type | None = None
) -> T | Any:
    """
    Safely get a value from a dictionary with type validation.
    
    Args:
        data: Dictionary to access (can be None)
        key: Key to look up
        default: Default value if key missing or wrong type
        expected_type: If provided, validate the value is this type
        
    Returns:
        The value if found and valid, otherwise default
        
    Example:
        >>> safe_get({"a": 1}, "a", default=0)
        1
        >>> safe_get({"a": "not_int"}, "a", default=0, expected_type=int)
        0
        >>> safe_get(None, "a", default="fallback")
        'fallback'
    """
    if data is None:
        return default
    
    if not isinstance(data, dict):
        logger.warning(f"safe_get called with non-dict: {type(data)}")
        return default
    
    value = data.get(key)
    if value is None:
        return default
    
    if expected_type is not None and not isinstance(value, expected_type):
        logger.debug(f"Type mismatch for key '{key}': expected {expected_type}, got {type(value)}")
        return default
    
    return value


def safe_get_nested(
    data: dict[str, Any] | None,
    *keys: str,
    default: T = None
) -> T | Any:
    """
    Safely get a nested value from a dictionary.
    
    Args:
        data: Dictionary to access
        *keys: Sequence of keys to traverse
        default: Default value if any key is missing
        
    Returns:
        The nested value if found, otherwise default
        
    Example:
        >>> safe_get_nested({"a": {"b": {"c": 1}}}, "a", "b", "c", default=0)
        1
        >>> safe_get_nested({"a": {}}, "a", "b", "c", default=0)
        0
    """
    if data is None or not keys:
        return default
    
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    
    return current


# =============================================================================
# SAFE TYPE CONVERSIONS
# =============================================================================

def safe_int(
    value: Any,
    default: int = 0,
    min_val: int | None = None,
    max_val: int | None = None
) -> int:
    """
    Safely convert a value to int with bounds checking.
    
    Args:
        value: Value to convert
        default: Default if conversion fails
        min_val: Minimum allowed value (clamps if exceeded)
        max_val: Maximum allowed value (clamps if exceeded)
        
    Returns:
        Integer value within bounds
        
    Example:
        >>> safe_int("42")
        42
        >>> safe_int("not_a_number", default=-1)
        -1
        >>> safe_int(150, max_val=100)
        100
    """
    try:
        result = int(value)
    except (ValueError, TypeError):
        return default
    
    if min_val is not None and result < min_val:
        return min_val
    if max_val is not None and result > max_val:
        return max_val
    
    return result


def safe_float(
    value: Any,
    default: float = 0.0,
    min_val: float | None = None,
    max_val: float | None = None
) -> float:
    """
    Safely convert a value to float with bounds checking.
    
    Args:
        value: Value to convert
        default: Default if conversion fails
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        
    Returns:
        Float value within bounds
    """
    try:
        result = float(value)
    except (ValueError, TypeError):
        return default
    
    if min_val is not None and result < min_val:
        return min_val
    if max_val is not None and result > max_val:
        return max_val
    
    return result


def safe_str(value: Any, default: str = "", max_length: int | None = None) -> str:
    """
    Safely convert a value to string with length limit.
    
    Args:
        value: Value to convert
        default: Default if value is None
        max_length: Maximum string length (truncates if exceeded)
        
    Returns:
        String value, possibly truncated
    """
    if value is None:
        return default
    
    result = str(value)
    
    if max_length is not None and len(result) > max_length:
        return result[:max_length]
    
    return result


# =============================================================================
# NULL SAFETY
# =============================================================================

def require_not_none(value: T | None, message: str = "Value cannot be None") -> T:
    """
    Require a value to be non-None.
    
    Args:
        value: Value to check
        message: Error message if None
        
    Returns:
        The value if not None
        
    Raises:
        ValueError: If value is None
    """
    if value is None:
        raise ValueError(message)
    return value


def coalesce(*values: T | None) -> T | None:
    """
    Return the first non-None value.
    
    Args:
        *values: Values to check
        
    Returns:
        First non-None value, or None if all are None
        
    Example:
        >>> coalesce(None, None, "found", "ignored")
        'found'
    """
    for value in values:
        if value is not None:
            return value
    return None


def if_not_none(value: T | None, func: Callable[[T], V], default: V = None) -> V | None:
    """
    Apply a function only if value is not None.
    
    Args:
        value: Value to check
        func: Function to apply if not None
        default: Default if value is None
        
    Returns:
        Result of func(value) or default
        
    Example:
        >>> if_not_none("hello", str.upper, default="")
        'HELLO'
        >>> if_not_none(None, str.upper, default="")
        ''
    """
    if value is None:
        return default
    return func(value)


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_bounds(
    value: int | float,
    min_val: int | float | None = None,
    max_val: int | float | None = None,
    name: str = "value"
) -> None:
    """
    Validate a numeric value is within bounds.
    
    Args:
        value: Value to validate
        min_val: Minimum allowed (inclusive)
        max_val: Maximum allowed (inclusive)
        name: Name for error messages
        
    Raises:
        ValueError: If value is out of bounds
    """
    if min_val is not None and value < min_val:
        raise ValueError(f"{name} must be >= {min_val}, got {value}")
    if max_val is not None and value > max_val:
        raise ValueError(f"{name} must be <= {max_val}, got {value}")


def validate_not_empty(value: str | list | dict, name: str = "value") -> None:
    """
    Validate a value is not empty.
    
    Args:
        value: Value to validate
        name: Name for error messages
        
    Raises:
        ValueError: If value is empty
    """
    if not value:
        raise ValueError(f"{name} cannot be empty")


def validate_type(value: Any, expected_type: type, name: str = "value") -> None:
    """
    Validate a value is of expected type.
    
    Args:
        value: Value to validate
        expected_type: Expected type
        name: Name for error messages
        
    Raises:
        TypeError: If value is wrong type
    """
    if not isinstance(value, expected_type):
        raise TypeError(f"{name} must be {expected_type.__name__}, got {type(value).__name__}")


# =============================================================================
# SAFE OPERATIONS DECORATOR
# =============================================================================

def safe_operation(
    default: T = None,
    log_errors: bool = True,
    reraise: tuple[type, ...] = ()
) -> Callable:
    """
    Decorator for safe operations that catch and log exceptions.
    
    Args:
        default: Default return value on error
        log_errors: Whether to log errors
        reraise: Exception types to re-raise instead of catching
        
    Returns:
        Decorated function
        
    Example:
        @safe_operation(default=[], log_errors=True)
        def parse_items(data):
            return json.loads(data)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except reraise:
                raise
            except Exception as e:
                if log_errors:
                    logger.warning(f"{func.__name__} failed: {e}")
                return default
        return wrapper
    return decorator


# =============================================================================
# RESOURCE CLEANUP
# =============================================================================

def safe_close(resource: Any, name: str = "resource") -> bool:
    """
    Safely close a resource, logging any errors.
    
    Args:
        resource: Resource with close() method
        name: Name for logging
        
    Returns:
        True if closed successfully, False otherwise
    """
    if resource is None:
        return True
    
    try:
        if hasattr(resource, 'close'):
            resource.close()
        return True
    except Exception as e:
        logger.warning(f"Failed to close {name}: {e}")
        return False


def safe_delete(path: str, retries: int = 3, delay: float = 0.5) -> bool:
    """
    Safely delete a file with retries.
    
    Args:
        path: Path to file
        retries: Number of retry attempts
        delay: Delay between retries in seconds
        
    Returns:
        True if deleted or doesn't exist, False on failure
    """
    import os
    import time
    
    for attempt in range(retries):
        try:
            if os.path.exists(path):
                os.remove(path)
            return True
        except OSError as e:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                logger.warning(f"Failed to delete {path} after {retries} attempts: {e}")
                return False
    return False
