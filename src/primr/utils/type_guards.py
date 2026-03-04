"""
Runtime type validation utilities.

This module provides type guards for validating values at runtime,
particularly useful for validating external API responses and
ensuring type safety at system boundaries.

Example:
    from primr.utils.type_guards import (
        validate_type,
        validate_api_response,
        ValidationResult,
        ValidationError,
    )

    # Validate a value matches expected type
    result = validate_type(data, dict, "response")

    # Validate API response with detailed results
    result = validate_api_response_safe(response, schema)
    if result.is_valid:
        process(result.value)
    else:
        for error in result.errors:
            print(f"{error.field}: {error.message}")
"""

import types
from collections.abc import Callable
from dataclasses import dataclass, field, is_dataclass
from dataclasses import fields as dataclass_fields
from typing import (
    Any,
    Generic,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

T = TypeVar("T")


# =============================================================================
# VALIDATION RESULT TYPES
# =============================================================================


@dataclass
class ValidationError:
    """
    Structured validation error with detailed context.

    Attributes:
        field: Field name where validation failed (dot-notation for nested)
        expected: Description of expected type or value
        actual: Description of actual type or value received
        message: Human-readable error message
        suggestion: Optional suggestion for fixing the error
    """

    field: str
    expected: str
    actual: str
    message: str = ""
    suggestion: str | None = None

    def __post_init__(self) -> None:
        if not self.message:
            self.message = f"Expected {self.expected}, got {self.actual}"

    def __str__(self) -> str:
        base = f"Field '{self.field}': {self.message}"
        if self.suggestion:
            base += f" ({self.suggestion})"
        return base


@dataclass
class ValidationResult(Generic[T]):
    """
    Result of validation with detailed error information.

    This provides a non-throwing alternative to validate_type for cases
    where you want to collect all errors rather than fail on the first.

    Attributes:
        value: The validated value if successful, None otherwise
        errors: List of validation errors encountered
        warnings: List of non-fatal warnings

    Example:
        result = validate_config_safe(config)
        if result.is_valid:
            use_config(result.value)
        else:
            for error in result.errors:
                print(error)
    """

    value: T | None = None
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0

    @property
    def is_invalid(self) -> bool:
        """Check if validation failed (has errors)."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def unwrap(self) -> T:
        """
        Get the value, raising if invalid.

        Raises:
            TypeValidationError: If validation failed
        """
        if self.is_invalid:
            error = self.errors[0]
            raise TypeValidationError(
                expected=error.expected,
                actual=error.actual,
                field=error.field
            )
        return self.value  # type: ignore[return-value]

    def unwrap_or(self, default: T) -> T:
        """Get the value or return default if invalid."""
        if self.is_invalid:
            return default
        return self.value  # type: ignore[return-value]

    @classmethod
    def ok(cls, value: T) -> "ValidationResult[T]":
        """Create a successful validation result."""
        return cls(value=value)

    @classmethod
    def err(
        cls,
        field: str,
        expected: str,
        actual: str,
        message: str = "",
        suggestion: str | None = None
    ) -> "ValidationResult[T]":
        """Create a failed validation result with a single error."""
        error = ValidationError(
            field=field,
            expected=expected,
            actual=actual,
            message=message,
            suggestion=suggestion
        )
        return cls(errors=[error])

    def add_error(
        self,
        field: str,
        expected: str,
        actual: str,
        message: str = "",
        suggestion: str | None = None
    ) -> "ValidationResult[T]":
        """Add an error to this result (mutates and returns self)."""
        self.errors.append(ValidationError(
            field=field,
            expected=expected,
            actual=actual,
            message=message,
            suggestion=suggestion
        ))
        return self

    def add_warning(self, message: str) -> "ValidationResult[T]":
        """Add a warning to this result (mutates and returns self)."""
        self.warnings.append(message)
        return self


# =============================================================================
# API RESPONSE SCHEMA
# =============================================================================


@dataclass
class APIResponseSchema:
    """
    Schema for validating API responses.

    Attributes:
        required_fields: Fields that must be present
        field_types: Expected types for fields
        validators: Custom validation functions per field
        nested_schemas: Schemas for nested objects
    """

    required_fields: list[str] = field(default_factory=list)
    field_types: dict[str, type] = field(default_factory=dict)
    validators: dict[str, Callable[[Any], bool]] = field(default_factory=dict)
    nested_schemas: dict[str, "APIResponseSchema"] = field(default_factory=dict)


class TypeValidationError(ValueError):
    """
    Raised when runtime type validation fails.

    Attributes:
        expected: String description of expected type
        actual: String description of actual type received
        field: Optional field name where validation failed
    """

    def __init__(
        self,
        expected: str,
        actual: str,
        field: str | None = None
    ):
        self.expected = expected
        self.actual = actual
        self.field = field
        msg = f"Expected {expected}, got {actual}"
        if field:
            msg = f"Field '{field}': {msg}"
        super().__init__(msg)


def _get_type_name(t: Any) -> str:
    """Get human-readable name for a type."""
    if t is type(None):
        return "None"
    if hasattr(t, "__name__"):
        return str(t.__name__)
    origin = get_origin(t)
    if origin is not None:
        args = get_args(t)
        if args:
            arg_names = ", ".join(_get_type_name(a) for a in args)
            origin_name = str(getattr(origin, "__name__", str(origin)))
            return f"{origin_name}[{arg_names}]"
        return str(getattr(origin, "__name__", str(origin)))
    return str(t)


def _check_type(value: Any, expected_type: type) -> bool:
    """
    Check if value matches expected type, handling generics.

    Supports: primitives, Optional, List, Dict, Union, dataclasses.
    """
    # Handle None type
    if expected_type is type(None):
        return value is None

    # Get origin for generic types (List, Dict, Optional, Union)
    origin = get_origin(expected_type)

    # Handle Optional[X] which is Union[X, None], and PEP 604 X | None
    if origin is Union or isinstance(expected_type, types.UnionType):
        args = get_args(expected_type)
        return any(_check_type(value, arg) for arg in args)

    # Handle List[X]
    if origin is list:
        if not isinstance(value, list):
            return False
        args = get_args(expected_type)
        if args:
            item_type = args[0]
            return all(_check_type(item, item_type) for item in value)
        return True

    # Handle Dict[K, V]
    if origin is dict:
        if not isinstance(value, dict):
            return False
        args = get_args(expected_type)
        if args and len(args) == 2:
            key_type, val_type = args
            return all(
                _check_type(k, key_type) and _check_type(v, val_type)
                for k, v in value.items()
            )
        return True

    # Handle dataclasses
    if is_dataclass(expected_type) and not isinstance(expected_type, type):
        # expected_type is a dataclass instance, not a class
        return False
    if is_dataclass(expected_type):
        return isinstance(value, expected_type)

    # Handle regular types
    if origin is not None:
        # Generic type without special handling - check against origin
        return isinstance(value, origin)

    return isinstance(value, expected_type)


def validate_type(
    value: Any,
    expected_type: type[T],
    field_name: str | None = None
) -> T:
    """
    Validate that value matches expected type at runtime.

    Handles Optional, List, Dict, Union, and dataclass types.

    Args:
        value: Value to validate
        expected_type: Expected type (can be generic like List[str])
        field_name: Optional field name for error messages

    Returns:
        The value if valid (unchanged)

    Raises:
        TypeValidationError: If type doesn't match

    Example:
        >>> validate_type("hello", str)
        'hello'
        >>> validate_type([1, 2, 3], List[int])
        [1, 2, 3]
        >>> validate_type(None, Optional[str])
        None
        >>> validate_type(123, str)  # raises TypeValidationError
    """
    if _check_type(value, expected_type):
        return value  # type: ignore[no-any-return]

    raise TypeValidationError(
        expected=_get_type_name(expected_type),
        actual=type(value).__name__,
        field=field_name
    )


def validate_dataclass(instance: Any, cls: type[T]) -> T:
    """
    Validate all fields of a dataclass instance match their type hints.

    Args:
        instance: Dataclass instance to validate
        cls: Expected dataclass type

    Returns:
        The instance if valid

    Raises:
        TypeValidationError: If instance is wrong type or any field is invalid

    Example:
        >>> from dataclasses import dataclass
        >>> @dataclass
        ... class User:
        ...     name: str
        ...     age: int
        >>> user = User(name="Alice", age=30)
        >>> validate_dataclass(user, User)
        User(name='Alice', age=30)
    """
    if not is_dataclass(cls):
        raise TypeValidationError(
            expected="dataclass type",
            actual=type(cls).__name__,
            field="cls"
        )

    if not isinstance(instance, cls):
        raise TypeValidationError(
            expected=cls.__name__,
            actual=type(instance).__name__
        )

    # Validate each field
    type_hints = {}
    try:
        # Get type hints from the class
        import typing
        type_hints = typing.get_type_hints(cls)
    except Exception:
        # Fall back to field annotations if get_type_hints fails
        pass

    for dc_field in dataclass_fields(cls):
        field_value = getattr(instance, dc_field.name)
        field_type = type_hints.get(dc_field.name, dc_field.type)

        # Skip if type is a string (forward reference we can't resolve)
        if isinstance(field_type, str):
            continue

        try:
            validate_type(field_value, field_type, dc_field.name)
        except TypeValidationError as e:
            raise TypeValidationError(
                expected=e.expected,
                actual=e.actual,
                field=f"{cls.__name__}.{e.field or field.name}"
            ) from e

    return instance


def validate_api_response(
    response: Any,
    required_fields: list[str],
    field_types: dict[str, type] | None = None
) -> dict:
    """
    Validate API response has required fields and optionally check types.

    Args:
        response: API response (should be a dict)
        required_fields: List of field names that must be present
        field_types: Optional dict mapping field names to expected types

    Returns:
        The response dict if valid

    Raises:
        TypeValidationError: If response is not a dict, missing fields,
            or field types don't match

    Example:
        >>> response = {"id": 123, "name": "test", "status": "ok"}
        >>> validate_api_response(response, ["id", "name"])
        {'id': 123, 'name': 'test', 'status': 'ok'}
        >>> validate_api_response(response, ["id"], {"id": int})
        {'id': 123, 'name': 'test', 'status': 'ok'}
    """
    # Check response is a dict
    if not isinstance(response, dict):
        raise TypeValidationError(
            expected="dict",
            actual=type(response).__name__,
            field="response"
        )

    # Check required fields exist
    missing = [f for f in required_fields if f not in response]
    if missing:
        raise TypeValidationError(
            expected=f"fields {missing}",
            actual="missing",
            field="response"
        )

    # Validate field types if specified
    if field_types:
        for field_name, expected_type in field_types.items():
            if field_name in response:
                validate_type(response[field_name], expected_type, field_name)

    return response


def is_valid_type(value: Any, expected_type: type) -> bool:
    """
    Check if value matches expected type without raising.

    Convenience function for conditional checks.

    Args:
        value: Value to check
        expected_type: Expected type

    Returns:
        True if value matches type, False otherwise

    Example:
        >>> is_valid_type("hello", str)
        True
        >>> is_valid_type(123, str)
        False
    """
    return _check_type(value, expected_type)


# =============================================================================
# SAFE VALIDATION (NON-THROWING)
# =============================================================================


def validate_type_safe(
    value: Any,
    expected_type: type[T],
    field_name: str = "value"
) -> ValidationResult[T]:
    """
    Validate type without raising, returning ValidationResult.

    Args:
        value: Value to validate
        expected_type: Expected type
        field_name: Field name for error messages

    Returns:
        ValidationResult with value if valid, or errors if invalid

    Example:
        >>> result = validate_type_safe("hello", str)
        >>> result.is_valid
        True
        >>> result = validate_type_safe(123, str, "name")
        >>> result.is_valid
        False
        >>> result.errors[0].field
        'name'
    """
    if _check_type(value, expected_type):
        return ValidationResult.ok(value)

    return ValidationResult.err(
        field=field_name,
        expected=_get_type_name(expected_type),
        actual=type(value).__name__
    )


def validate_api_response_safe(
    response: Any,
    schema: APIResponseSchema,
    prefix: str = ""
) -> ValidationResult[dict[str, Any]]:
    """
    Validate API response against schema, collecting all errors.

    Unlike validate_api_response which raises on first error, this
    collects all validation errors for comprehensive feedback.

    Args:
        response: API response to validate
        schema: Schema defining expected structure
        prefix: Field prefix for nested validation

    Returns:
        ValidationResult with validated dict or all errors

    Example:
        >>> schema = APIResponseSchema(
        ...     required_fields=["id", "name"],
        ...     field_types={"id": int, "name": str}
        ... )
        >>> result = validate_api_response_safe({"id": 1, "name": "test"}, schema)
        >>> result.is_valid
        True
    """
    result: ValidationResult[dict[str, Any]] = ValidationResult()

    def field_path(name: str) -> str:
        return f"{prefix}.{name}" if prefix else name

    # Check response is a dict
    if not isinstance(response, dict):
        return ValidationResult.err(
            field=prefix or "response",
            expected="dict",
            actual=type(response).__name__,
            suggestion="API response must be a JSON object"
        )

    # Check required fields
    for field_name in schema.required_fields:
        if field_name not in response:
            result.add_error(
                field=field_path(field_name),
                expected="present",
                actual="missing",
                message=f"Required field '{field_name}' is missing"
            )

    # Check field types
    for field_name, expected_type in schema.field_types.items():
        if field_name in response:
            value = response[field_name]
            if not _check_type(value, expected_type):
                result.add_error(
                    field=field_path(field_name),
                    expected=_get_type_name(expected_type),
                    actual=type(value).__name__
                )

    # Run custom validators
    for field_name, validator in schema.validators.items():
        if field_name in response:
            try:
                if not validator(response[field_name]):
                    result.add_error(
                        field=field_path(field_name),
                        expected="valid value",
                        actual=str(response[field_name])[:50],
                        message=f"Custom validation failed for '{field_name}'"
                    )
            except Exception as e:
                result.add_error(
                    field=field_path(field_name),
                    expected="valid value",
                    actual="error",
                    message=f"Validator raised: {e}"
                )

    # Validate nested schemas
    for field_name, nested_schema in schema.nested_schemas.items():
        if field_name in response:
            nested_result = validate_api_response_safe(
                response[field_name],
                nested_schema,
                prefix=field_path(field_name)
            )
            result.errors.extend(nested_result.errors)
            result.warnings.extend(nested_result.warnings)

    # Set value if valid
    if result.is_valid:
        result.value = response

    return result


def validate_in_range(
    value: int | float,
    min_val: int | float | None = None,
    max_val: int | float | None = None,
    field_name: str = "value"
) -> ValidationResult[int | float]:
    """
    Validate a numeric value is within a range.

    Args:
        value: Value to validate
        min_val: Minimum allowed value (inclusive), None for no minimum
        max_val: Maximum allowed value (inclusive), None for no maximum
        field_name: Field name for error messages

    Returns:
        ValidationResult with value if valid

    Example:
        >>> validate_in_range(5, 0, 10).is_valid
        True
        >>> validate_in_range(-1, 0, 10).is_valid
        False
    """
    if not isinstance(value, int | float):
        return ValidationResult.err(
            field=field_name,
            expected="number",
            actual=type(value).__name__
        )

    if min_val is not None and value < min_val:
        return ValidationResult.err(
            field=field_name,
            expected=f">= {min_val}",
            actual=str(value),
            suggestion=f"Value must be at least {min_val}"
        )

    if max_val is not None and value > max_val:
        return ValidationResult.err(
            field=field_name,
            expected=f"<= {max_val}",
            actual=str(value),
            suggestion=f"Value must be at most {max_val}"
        )

    return ValidationResult.ok(value)


def validate_non_empty_string(
    value: Any,
    field_name: str = "value"
) -> ValidationResult[str]:
    """
    Validate value is a non-empty string.

    Args:
        value: Value to validate
        field_name: Field name for error messages

    Returns:
        ValidationResult with string if valid

    Example:
        >>> validate_non_empty_string("hello").is_valid
        True
        >>> validate_non_empty_string("").is_valid
        False
    """
    if not isinstance(value, str):
        return ValidationResult.err(
            field=field_name,
            expected="string",
            actual=type(value).__name__
        )

    if not value.strip():
        return ValidationResult.err(
            field=field_name,
            expected="non-empty string",
            actual="empty string",
            suggestion="Provide a non-empty value"
        )

    return ValidationResult.ok(value)



# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================


@dataclass
class ConfigSchema:
    """
    Schema for validating configuration dictionaries.

    Attributes:
        required_keys: Keys that must be present
        optional_keys: Keys with default values if missing
        type_hints: Expected types for keys
        validators: Custom validation functions per key
        ranges: Numeric range constraints (key -> (min, max))

    Example:
        schema = ConfigSchema(
            required_keys=["api_key"],
            optional_keys={"timeout": 30, "retries": 3},
            type_hints={"api_key": str, "timeout": int},
            ranges={"timeout": (1, 300), "retries": (0, 10)}
        )
        result = validate_config(config, schema)
    """

    required_keys: list[str] = field(default_factory=list)
    optional_keys: dict[str, Any] = field(default_factory=dict)
    type_hints: dict[str, type] = field(default_factory=dict)
    validators: dict[str, Callable[[Any], bool]] = field(default_factory=dict)
    ranges: dict[str, tuple[int | float | None, int | float | None]] = field(
        default_factory=dict
    )


def validate_config(
    config: dict[str, Any],
    schema: ConfigSchema,
    prefix: str = ""
) -> ValidationResult[dict[str, Any]]:
    """
    Validate configuration dictionary against schema.

    Collects all validation errors for comprehensive feedback.
    Applies defaults for missing optional keys.

    Args:
        config: Configuration dictionary to validate
        schema: Schema defining expected structure
        prefix: Field prefix for nested validation

    Returns:
        ValidationResult with validated config (with defaults applied) or errors

    Example:
        >>> schema = ConfigSchema(
        ...     required_keys=["name"],
        ...     optional_keys={"count": 10},
        ...     type_hints={"name": str, "count": int},
        ...     ranges={"count": (1, 100)}
        ... )
        >>> result = validate_config({"name": "test"}, schema)
        >>> result.is_valid
        True
        >>> result.value["count"]  # Default applied
        10
    """
    result: ValidationResult[dict[str, Any]] = ValidationResult()
    validated_config: dict[str, Any] = {}

    def field_path(name: str) -> str:
        return f"{prefix}.{name}" if prefix else name

    # Check config is a dict
    if not isinstance(config, dict):
        return ValidationResult.err(
            field=prefix or "config",
            expected="dict",
            actual=type(config).__name__,
            suggestion="Configuration must be a dictionary"
        )

    # Check required keys
    for key in schema.required_keys:
        if key not in config:
            result.add_error(
                field=field_path(key),
                expected="present",
                actual="missing",
                message=f"Required configuration key '{key}' is missing"
            )
        else:
            validated_config[key] = config[key]

    # Apply defaults for optional keys
    for key, default in schema.optional_keys.items():
        if key in config:
            validated_config[key] = config[key]
        else:
            validated_config[key] = default
            result.add_warning(f"Using default value for '{key}': {default}")

    # Copy any extra keys not in schema
    for key in config:
        if key not in validated_config:
            validated_config[key] = config[key]

    # Check types
    for key, expected_type in schema.type_hints.items():
        if key in validated_config:
            value = validated_config[key]
            if not _check_type(value, expected_type):
                result.add_error(
                    field=field_path(key),
                    expected=_get_type_name(expected_type),
                    actual=type(value).__name__
                )

    # Check ranges
    for key, (min_val, max_val) in schema.ranges.items():
        if key in validated_config:
            value = validated_config[key]
            if isinstance(value, int | float):
                if min_val is not None and value < min_val:
                    result.add_error(
                        field=field_path(key),
                        expected=f">= {min_val}",
                        actual=str(value),
                        suggestion=f"Value must be at least {min_val}"
                    )
                if max_val is not None and value > max_val:
                    result.add_error(
                        field=field_path(key),
                        expected=f"<= {max_val}",
                        actual=str(value),
                        suggestion=f"Value must be at most {max_val}"
                    )

    # Run custom validators
    for key, validator in schema.validators.items():
        if key in validated_config:
            try:
                if not validator(validated_config[key]):
                    result.add_error(
                        field=field_path(key),
                        expected="valid value",
                        actual=str(validated_config[key])[:50],
                        message=f"Custom validation failed for '{key}'"
                    )
            except Exception as e:
                result.add_error(
                    field=field_path(key),
                    expected="valid value",
                    actual="error",
                    message=f"Validator raised: {e}"
                )

    # Set value if valid
    if result.is_valid:
        result.value = validated_config

    return result


def validate_api_key_format(key: str, key_name: str = "api_key") -> ValidationResult[str]:
    """
    Validate API key has expected format.

    Args:
        key: API key to validate
        key_name: Name for error messages

    Returns:
        ValidationResult with key if valid

    Example:
        >>> result = validate_api_key_format("AIza...", "GEMINI_API_KEY")
        >>> result.is_valid
        True
    """
    if not isinstance(key, str):
        return ValidationResult.err(
            field=key_name,
            expected="string",
            actual=type(key).__name__
        )

    if not key.strip():
        return ValidationResult.err(
            field=key_name,
            expected="non-empty API key",
            actual="empty string",
            suggestion=f"Set {key_name} in your .env file or environment"
        )

    # Basic format checks (not exhaustive, just sanity checks)
    if len(key) < 10:
        return ValidationResult.err(
            field=key_name,
            expected="API key (10+ characters)",
            actual=f"string of length {len(key)}",
            suggestion="API keys are typically longer. Check for truncation."
        )

    if " " in key:
        return ValidationResult.err(
            field=key_name,
            expected="API key without spaces",
            actual="string with spaces",
            suggestion="Remove any spaces from the API key"
        )

    return ValidationResult.ok(key)
