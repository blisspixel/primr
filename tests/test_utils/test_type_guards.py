"""
Tests for type guard utilities.

Includes property-based tests using Hypothesis for comprehensive validation.
"""

from dataclasses import dataclass

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
import pytest

from primr.utils.type_guards import (
    TypeValidationError,
    is_valid_type,
    validate_api_response,
    validate_dataclass,
    validate_type,
)

# =============================================================================
# TEST DATA CLASSES
# =============================================================================


@dataclass
class SimpleUser:
    """Simple dataclass for testing."""

    name: str
    age: int


@dataclass
class UserWithOptional:
    """Dataclass with optional field."""

    name: str
    email: str | None = None


@dataclass
class NestedData:
    """Dataclass with nested types."""

    items: list[str]
    metadata: dict[str, int]


# =============================================================================
# UNIT TESTS - TypeValidationError
# =============================================================================


class TestTypeValidationError:
    """Tests for TypeValidationError exception."""

    def test_basic_error(self):
        """Should format basic error message."""
        error = TypeValidationError(expected="str", actual="int")
        assert "Expected str" in str(error)
        assert "got int" in str(error)

    def test_error_with_field(self):
        """Should include field name in message."""
        error = TypeValidationError(expected="str", actual="int", field="name")
        assert "Field 'name'" in str(error)
        assert "Expected str" in str(error)

    def test_error_attributes(self):
        """Should store attributes correctly."""
        error = TypeValidationError(expected="str", actual="int", field="test")
        assert error.expected == "str"
        assert error.actual == "int"
        assert error.field == "test"


# =============================================================================
# UNIT TESTS - validate_type
# =============================================================================


class TestValidateType:
    """Tests for validate_type function."""

    def test_validates_str(self):
        """Should accept valid string."""
        result = validate_type("hello", str)
        assert result == "hello"

    def test_validates_int(self):
        """Should accept valid int."""
        result = validate_type(42, int)
        assert result == 42

    def test_validates_float(self):
        """Should accept valid float."""
        result = validate_type(3.14, float)
        assert result == 3.14

    def test_validates_bool(self):
        """Should accept valid bool."""
        result = validate_type(True, bool)
        assert result is True

    def test_validates_none(self):
        """Should accept None for NoneType."""
        result = validate_type(None, type(None))
        assert result is None

    def test_rejects_wrong_type(self):
        """Should reject value of wrong type."""
        with pytest.raises(TypeValidationError) as exc_info:
            validate_type(123, str)
        assert "Expected str" in str(exc_info.value)
        assert "got int" in str(exc_info.value)

    def test_includes_field_name_in_error(self):
        """Should include field name in error."""
        with pytest.raises(TypeValidationError) as exc_info:
            validate_type(123, str, field_name="username")
        assert "Field 'username'" in str(exc_info.value)


class TestValidateTypeOptional:
    """Tests for Optional type validation."""

    def test_accepts_value_for_optional(self):
        """Should accept non-None value for Optional."""
        result = validate_type("hello", str | None)
        assert result == "hello"

    def test_accepts_none_for_optional(self):
        """Should accept None for Optional."""
        result = validate_type(None, str | None)
        assert result is None

    def test_rejects_wrong_type_for_optional(self):
        """Should reject wrong type even for Optional."""
        with pytest.raises(TypeValidationError):
            validate_type(123, str | None)


class TestValidateTypeList:
    """Tests for List type validation."""

    def test_accepts_valid_list(self):
        """Should accept list with correct item types."""
        result = validate_type(["a", "b", "c"], list[str])
        assert result == ["a", "b", "c"]

    def test_accepts_empty_list(self):
        """Should accept empty list."""
        result = validate_type([], list[str])
        assert result == []

    def test_rejects_non_list(self):
        """Should reject non-list value."""
        with pytest.raises(TypeValidationError):
            validate_type("not a list", list[str])

    def test_rejects_list_with_wrong_item_type(self):
        """Should reject list with wrong item types."""
        with pytest.raises(TypeValidationError):
            validate_type([1, 2, 3], list[str])


class TestValidateTypeDict:
    """Tests for Dict type validation."""

    def test_accepts_valid_dict(self):
        """Should accept dict with correct types."""
        result = validate_type({"a": 1, "b": 2}, dict[str, int])
        assert result == {"a": 1, "b": 2}

    def test_accepts_empty_dict(self):
        """Should accept empty dict."""
        result = validate_type({}, dict[str, int])
        assert result == {}

    def test_rejects_non_dict(self):
        """Should reject non-dict value."""
        with pytest.raises(TypeValidationError):
            validate_type([1, 2], dict[str, int])

    def test_rejects_dict_with_wrong_key_type(self):
        """Should reject dict with wrong key types."""
        with pytest.raises(TypeValidationError):
            validate_type({1: "a", 2: "b"}, dict[str, str])

    def test_rejects_dict_with_wrong_value_type(self):
        """Should reject dict with wrong value types."""
        with pytest.raises(TypeValidationError):
            validate_type({"a": "1", "b": "2"}, dict[str, int])


class TestValidateTypeUnion:
    """Tests for Union type validation."""

    def test_accepts_first_union_type(self):
        """Should accept value matching first type in Union."""
        result = validate_type("hello", str | int)
        assert result == "hello"

    def test_accepts_second_union_type(self):
        """Should accept value matching second type in Union."""
        result = validate_type(42, str | int)
        assert result == 42

    def test_rejects_non_union_type(self):
        """Should reject value not matching any Union type."""
        with pytest.raises(TypeValidationError):
            validate_type(3.14, str | int)


# =============================================================================
# UNIT TESTS - validate_dataclass
# =============================================================================


class TestValidateDataclass:
    """Tests for validate_dataclass function."""

    def test_accepts_valid_dataclass(self):
        """Should accept valid dataclass instance."""
        user = SimpleUser(name="Alice", age=30)
        result = validate_dataclass(user, SimpleUser)
        assert result is user

    def test_rejects_wrong_instance_type(self):
        """Should reject instance of wrong dataclass."""
        user = SimpleUser(name="Alice", age=30)
        with pytest.raises(TypeValidationError):
            validate_dataclass(user, UserWithOptional)

    def test_rejects_non_dataclass_type(self):
        """Should reject non-dataclass type argument."""
        with pytest.raises(TypeValidationError):
            validate_dataclass({"name": "Alice"}, dict)

    def test_validates_optional_fields(self):
        """Should accept dataclass with optional fields."""
        user = UserWithOptional(name="Alice", email=None)
        result = validate_dataclass(user, UserWithOptional)
        assert result is user

    def test_validates_nested_types(self):
        """Should validate nested collection types."""
        data = NestedData(items=["a", "b"], metadata={"x": 1})
        result = validate_dataclass(data, NestedData)
        assert result is data


# =============================================================================
# UNIT TESTS - validate_api_response
# =============================================================================


class TestValidateApiResponse:
    """Tests for validate_api_response function."""

    def test_accepts_valid_response(self):
        """Should accept response with all required fields."""
        response = {"id": 123, "name": "test", "status": "ok"}
        result = validate_api_response(response, ["id", "name"])
        assert result == response

    def test_rejects_non_dict(self):
        """Should reject non-dict response."""
        with pytest.raises(TypeValidationError) as exc_info:
            validate_api_response("not a dict", ["id"])
        assert "Expected dict" in str(exc_info.value)

    def test_rejects_missing_field(self):
        """Should reject response missing required field."""
        response = {"id": 123}
        with pytest.raises(TypeValidationError) as exc_info:
            validate_api_response(response, ["id", "name"])
        assert "missing" in str(exc_info.value).lower()

    def test_validates_field_types(self):
        """Should validate field types when specified."""
        response = {"id": 123, "name": "test"}
        result = validate_api_response(
            response, ["id", "name"], field_types={"id": int, "name": str}
        )
        assert result == response

    def test_rejects_wrong_field_type(self):
        """Should reject field with wrong type."""
        response = {"id": "not-an-int", "name": "test"}
        with pytest.raises(TypeValidationError):
            validate_api_response(response, ["id"], field_types={"id": int})

    def test_allows_extra_fields(self):
        """Should allow fields not in required list."""
        response = {"id": 123, "name": "test", "extra": "data"}
        result = validate_api_response(response, ["id"])
        assert result == response


# =============================================================================
# UNIT TESTS - is_valid_type
# =============================================================================


class TestIsValidType:
    """Tests for is_valid_type function."""

    def test_returns_true_for_valid(self):
        """Should return True for matching type."""
        assert is_valid_type("hello", str) is True
        assert is_valid_type(42, int) is True
        assert is_valid_type([1, 2], list[int]) is True

    def test_returns_false_for_invalid(self):
        """Should return False for non-matching type."""
        assert is_valid_type(123, str) is False
        assert is_valid_type("hello", int) is False
        assert is_valid_type([1, 2], list[str]) is False

    def test_does_not_raise(self):
        """Should never raise exception."""
        # These would raise with validate_type, but is_valid_type returns False
        assert is_valid_type(None, str) is False
        assert is_valid_type({"a": 1}, list[int]) is False


# =============================================================================
# PROPERTY-BASED TESTS
# =============================================================================


class TestTypeValidatorCorrectnessProperty:
    """
    Property-based tests for type validator correctness.

    **Feature: code-quality-hardening, Property 1: Type Validator Correctness**
    **Validates: Requirements 1.1, 1.2**

    For any value and expected type, the type validator SHALL accept values
    that match the type and reject values that don't match.
    """

    @given(st.text())
    @settings(max_examples=100)
    def test_str_values_accepted_as_str(self, value: str):
        """Any string should be accepted as str type."""
        result = validate_type(value, str)
        assert result == value
        assert is_valid_type(value, str) is True

    @given(st.integers())
    @settings(max_examples=100)
    def test_int_values_accepted_as_int(self, value: int):
        """Any integer should be accepted as int type."""
        # Note: bool is subclass of int in Python, so we exclude bools
        if isinstance(value, bool):
            return
        result = validate_type(value, int)
        assert result == value
        assert is_valid_type(value, int) is True

    @given(st.floats(allow_nan=False))
    @settings(max_examples=100)
    def test_float_values_accepted_as_float(self, value: float):
        """Any float should be accepted as float type."""
        result = validate_type(value, float)
        assert result == value
        assert is_valid_type(value, float) is True

    @given(st.booleans())
    @settings(max_examples=100)
    def test_bool_values_accepted_as_bool(self, value: bool):
        """Any boolean should be accepted as bool type."""
        result = validate_type(value, bool)
        assert result == value
        assert is_valid_type(value, bool) is True

    @given(st.lists(st.text()))
    @settings(max_examples=100)
    def test_list_str_values_accepted(self, value: list[str]):
        """Any list of strings should be accepted as List[str]."""
        result = validate_type(value, list[str])
        assert result == value
        assert is_valid_type(value, list[str]) is True

    @given(st.lists(st.integers()))
    @settings(max_examples=100)
    def test_list_int_values_accepted(self, value: list[int]):
        """Any list of integers should be accepted as List[int]."""
        result = validate_type(value, list[int])
        assert result == value
        assert is_valid_type(value, list[int]) is True

    @given(st.dictionaries(st.text(), st.integers()))
    @settings(max_examples=100)
    def test_dict_str_int_values_accepted(self, value: dict[str, int]):
        """Any dict[str, int] should be accepted as Dict[str, int]."""
        result = validate_type(value, dict[str, int])
        assert result == value
        assert is_valid_type(value, dict[str, int]) is True

    @given(st.one_of(st.text(), st.none()))
    @settings(max_examples=100)
    def test_optional_str_values_accepted(self, value: str | None):
        """Any str or None should be accepted as Optional[str]."""
        result = validate_type(value, str | None)
        assert result == value
        assert is_valid_type(value, str | None) is True

    @given(st.integers())
    @settings(max_examples=100)
    def test_int_rejected_as_str(self, value: int):
        """Integers should be rejected when str is expected."""
        # Skip bools since they're technically ints
        if isinstance(value, bool):
            return
        assert is_valid_type(value, str) is False
        with pytest.raises(TypeValidationError):
            validate_type(value, str)

    @given(st.text().filter(lambda x: x.strip() != "" and not x.isdigit()))
    @settings(max_examples=100)
    def test_str_rejected_as_int(self, value: str):
        """Non-numeric strings should be rejected when int is expected."""
        assert is_valid_type(value, int) is False
        with pytest.raises(TypeValidationError):
            validate_type(value, int)

    @given(st.lists(st.text()))
    @settings(max_examples=100)
    def test_list_str_rejected_as_list_int(self, value: list[str]):
        """List[str] should be rejected when List[int] is expected (if non-empty)."""
        if len(value) == 0:
            # Empty list is valid for any List type
            return
        if all(s.isdigit() or s == "" for s in value):
            # Skip if all strings happen to be digit-only
            return
        assert is_valid_type(value, list[int]) is False


class TestApiResponseValidationProperty:
    """
    Property-based tests for API response validation.

    **Feature: code-quality-hardening, Property 2: API Response Validation**
    **Validates: Requirements 1.5**

    For any API response dict and list of required fields, the validator SHALL
    accept responses containing all required fields and reject responses
    missing any required field.
    """

    @given(
        st.dictionaries(
            st.text(alphabet="abcdefghij", min_size=1, max_size=5),
            st.integers(min_value=-100, max_value=100),
            min_size=0,
            max_size=5,
        )
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_response_with_all_required_fields_accepted(self, response: dict[str, int]):
        """Response containing all required fields should be accepted."""
        # Use keys from response as required fields (guaranteed to exist)
        required_fields = list(response.keys())[:3]  # Take up to 3 keys

        if not required_fields:
            # Empty required fields should always pass
            result = validate_api_response(response, [])
            assert result == response
        else:
            result = validate_api_response(response, required_fields)
            assert result == response

    @given(
        st.dictionaries(
            st.text(alphabet="abcde", min_size=1, max_size=3),
            st.integers(min_value=-100, max_value=100),
            min_size=0,
            max_size=5,
        ),
        st.lists(
            st.text(alphabet="fghij", min_size=1, max_size=3), min_size=1, max_size=3, unique=True
        ),
    )
    @settings(max_examples=100)
    def test_response_missing_required_field_rejected(
        self, response: dict[str, int], required_fields: list[str]
    ):
        """Response missing any required field should be rejected."""
        # Required fields use different alphabet, so they won't be in response
        # This guarantees missing fields
        with pytest.raises(TypeValidationError):
            validate_api_response(response, required_fields)

    @given(st.text(max_size=20))
    @settings(max_examples=100)
    def test_non_dict_response_rejected(self, value: str):
        """Non-dict responses should always be rejected."""
        with pytest.raises(TypeValidationError) as exc_info:
            validate_api_response(value, ["any_field"])
        assert "dict" in str(exc_info.value).lower()

    @given(
        st.dictionaries(
            st.text(alphabet="abcde", min_size=1, max_size=5),
            st.text(alphabet="xyz", min_size=1, max_size=5),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_field_type_validation(self, response: dict[str, str]):
        """Field type validation should reject wrong types."""
        # Pick first field and expect it to be int (but it's str)
        field_name = next(iter(response.keys()))

        with pytest.raises(TypeValidationError):
            validate_api_response(response, [field_name], field_types={field_name: int})

    @given(
        st.dictionaries(
            st.text(alphabet="abcde", min_size=1, max_size=5),
            st.integers(min_value=-100, max_value=100),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_correct_field_type_accepted(self, response: dict[str, int]):
        """Correct field types should be accepted."""
        # Pick first field and expect it to be int (which it is)
        field_name = next(iter(response.keys()))

        result = validate_api_response(response, [field_name], field_types={field_name: int})
        assert result == response


# =============================================================================
# TESTS FOR NEW VALIDATION RESULT TYPES
# =============================================================================

from primr.utils.type_guards import (
    APIResponseSchema,
    ValidationResult,
    validate_api_response_safe,
    validate_in_range,
    validate_non_empty_string,
    validate_type_safe,
)
from primr.utils.type_guards import (
    ValidationError as VError,
)


class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_basic_error_creation(self):
        """Should create error with required fields."""
        error = VError(field="name", expected="str", actual="int")
        assert error.field == "name"
        assert error.expected == "str"
        assert error.actual == "int"
        assert "Expected str, got int" in error.message

    def test_custom_message(self):
        """Should use custom message when provided."""
        error = VError(
            field="age", expected="positive int", actual="-5", message="Age must be positive"
        )
        assert error.message == "Age must be positive"

    def test_suggestion(self):
        """Should include suggestion in string representation."""
        error = VError(
            field="email",
            expected="valid email",
            actual="not-an-email",
            suggestion="Use format: user@domain.com",
        )
        assert "user@domain.com" in str(error)

    def test_str_representation(self):
        """Should format nicely as string."""
        error = VError(field="test", expected="str", actual="int")
        assert "Field 'test'" in str(error)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_ok_result(self):
        """Should create successful result."""
        result = ValidationResult.ok("hello")
        assert result.is_valid
        assert not result.is_invalid
        assert result.value == "hello"
        assert len(result.errors) == 0

    def test_err_result(self):
        """Should create failed result."""
        result = ValidationResult.err(field="name", expected="str", actual="int")
        assert result.is_invalid
        assert not result.is_valid
        assert result.value is None
        assert len(result.errors) == 1

    def test_unwrap_success(self):
        """Should unwrap successful result."""
        result = ValidationResult.ok(42)
        assert result.unwrap() == 42

    def test_unwrap_failure(self):
        """Should raise on unwrap of failed result."""
        result = ValidationResult.err("field", "str", "int")
        with pytest.raises(TypeValidationError):
            result.unwrap()

    def test_unwrap_or_success(self):
        """Should return value for successful result."""
        result = ValidationResult.ok("hello")
        assert result.unwrap_or("default") == "hello"

    def test_unwrap_or_failure(self):
        """Should return default for failed result."""
        result = ValidationResult.err("field", "str", "int")
        assert result.unwrap_or("default") == "default"

    def test_add_error(self):
        """Should accumulate errors."""
        result: ValidationResult[dict] = ValidationResult()
        result.add_error("field1", "str", "int")
        result.add_error("field2", "list", "dict")
        assert len(result.errors) == 2
        assert result.is_invalid

    def test_add_warning(self):
        """Should accumulate warnings."""
        result = ValidationResult.ok("value")
        result.add_warning("This is deprecated")
        assert result.is_valid  # Warnings don't make it invalid
        assert result.has_warnings
        assert len(result.warnings) == 1


class TestValidateTypeSafe:
    """Tests for validate_type_safe function."""

    def test_valid_type_returns_ok(self):
        """Should return ok result for valid type."""
        result = validate_type_safe("hello", str)
        assert result.is_valid
        assert result.value == "hello"

    def test_invalid_type_returns_err(self):
        """Should return err result for invalid type."""
        result = validate_type_safe(123, str, "name")
        assert result.is_invalid
        assert result.errors[0].field == "name"
        assert result.errors[0].expected == "str"
        assert result.errors[0].actual == "int"


class TestAPIResponseSchema:
    """Tests for APIResponseSchema and validate_api_response_safe."""

    def test_valid_response(self):
        """Should accept valid response."""
        schema = APIResponseSchema(
            required_fields=["id", "name"], field_types={"id": int, "name": str}
        )
        response = {"id": 1, "name": "test", "extra": "allowed"}
        result = validate_api_response_safe(response, schema)
        assert result.is_valid
        assert result.value == response

    def test_missing_required_field(self):
        """Should report missing required fields."""
        schema = APIResponseSchema(required_fields=["id", "name"])
        response = {"id": 1}
        result = validate_api_response_safe(response, schema)
        assert result.is_invalid
        assert any("name" in e.field for e in result.errors)

    def test_wrong_field_type(self):
        """Should report wrong field types."""
        schema = APIResponseSchema(required_fields=["id"], field_types={"id": int})
        response = {"id": "not-an-int"}
        result = validate_api_response_safe(response, schema)
        assert result.is_invalid
        assert result.errors[0].field == "id"

    def test_custom_validator(self):
        """Should run custom validators."""
        schema = APIResponseSchema(required_fields=["age"], validators={"age": lambda x: x >= 0})
        response = {"age": -5}
        result = validate_api_response_safe(response, schema)
        assert result.is_invalid

    def test_nested_schema(self):
        """Should validate nested schemas."""
        inner_schema = APIResponseSchema(required_fields=["city"], field_types={"city": str})
        outer_schema = APIResponseSchema(
            required_fields=["address"], nested_schemas={"address": inner_schema}
        )
        response = {"address": {"city": 123}}  # city should be str
        result = validate_api_response_safe(response, outer_schema)
        assert result.is_invalid
        assert any("city" in e.field for e in result.errors)

    def test_collects_all_errors(self):
        """Should collect all errors, not just first."""
        schema = APIResponseSchema(required_fields=["a", "b", "c"])
        response = {}  # Missing all three
        result = validate_api_response_safe(response, schema)
        assert len(result.errors) == 3

    def test_non_dict_response(self):
        """Should reject non-dict response."""
        schema = APIResponseSchema(required_fields=["id"])
        result = validate_api_response_safe("not a dict", schema)
        assert result.is_invalid
        assert "dict" in result.errors[0].expected


class TestValidateInRange:
    """Tests for validate_in_range function."""

    def test_value_in_range(self):
        """Should accept value within range."""
        result = validate_in_range(5, 0, 10)
        assert result.is_valid
        assert result.value == 5

    def test_value_below_min(self):
        """Should reject value below minimum."""
        result = validate_in_range(-1, 0, 10, "count")
        assert result.is_invalid
        assert ">= 0" in result.errors[0].expected

    def test_value_above_max(self):
        """Should reject value above maximum."""
        result = validate_in_range(15, 0, 10, "count")
        assert result.is_invalid
        assert "<= 10" in result.errors[0].expected

    def test_no_min(self):
        """Should allow any value when no minimum."""
        result = validate_in_range(-1000, None, 10)
        assert result.is_valid

    def test_no_max(self):
        """Should allow any value when no maximum."""
        result = validate_in_range(1000, 0, None)
        assert result.is_valid

    def test_non_numeric(self):
        """Should reject non-numeric values."""
        result = validate_in_range("five", 0, 10)  # type: ignore
        assert result.is_invalid


class TestValidateNonEmptyString:
    """Tests for validate_non_empty_string function."""

    def test_valid_string(self):
        """Should accept non-empty string."""
        result = validate_non_empty_string("hello")
        assert result.is_valid
        assert result.value == "hello"

    def test_empty_string(self):
        """Should reject empty string."""
        result = validate_non_empty_string("")
        assert result.is_invalid

    def test_whitespace_only(self):
        """Should reject whitespace-only string."""
        result = validate_non_empty_string("   ")
        assert result.is_invalid

    def test_non_string(self):
        """Should reject non-string values."""
        result = validate_non_empty_string(123)  # type: ignore
        assert result.is_invalid


# =============================================================================
# PROPERTY TESTS FOR NEW VALIDATION TYPES
# =============================================================================


class TestTypeGuardCorrectnessProperty:
    """
    **Feature: primr-excellence, Property 1: Type Guard Correctness**
    **Validates: Requirements 1.2, 1.3, 1.5**

    For any input value and expected type, the type guard SHALL either:
    - Return the value unchanged if it matches the type
    - Raise TypeValidationError with field, expected, and actual if it doesn't match
    """

    @given(
        st.one_of(
            st.text(),
            st.integers(),
            st.floats(allow_nan=False),
            st.booleans(),
            st.none(),
            st.lists(st.text()),
            st.dictionaries(st.text(), st.integers()),
        )
    )
    @settings(max_examples=100)
    def test_validate_type_safe_never_raises(self, value):
        """validate_type_safe should never raise, always return ValidationResult."""
        # Try validating against various types - should never raise
        for expected_type in [str, int, float, bool, list, dict]:
            result = validate_type_safe(value, expected_type)
            assert isinstance(result, ValidationResult)
            # Either valid with value, or invalid with errors
            if result.is_valid:
                assert result.value == value
            else:
                assert len(result.errors) > 0
                assert result.errors[0].field is not None
                assert result.errors[0].expected is not None
                assert result.errors[0].actual is not None

    @given(
        st.dictionaries(
            st.text(alphabet="abcdef", min_size=1, max_size=5),
            st.one_of(st.text(), st.integers(), st.none()),
            min_size=0,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_api_response_safe_collects_all_errors(self, response):
        """validate_api_response_safe should collect all errors, not fail fast."""
        # Create schema requiring fields that may or may not exist
        schema = APIResponseSchema(
            required_fields=["x", "y", "z"],  # Unlikely to all exist
            field_types={"x": int, "y": str},
        )
        result = validate_api_response_safe(response, schema)

        # Count how many required fields are actually missing
        missing_count = sum(1 for f in ["x", "y", "z"] if f not in response)

        # Should have at least that many errors (plus possible type errors)
        if missing_count > 0:
            assert result.is_invalid
            assert len(result.errors) >= missing_count

    @given(st.integers(min_value=-1000, max_value=1000))
    @settings(max_examples=100)
    def test_range_validation_correctness(self, value):
        """Range validation should correctly accept/reject based on bounds."""
        min_val, max_val = -100, 100
        result = validate_in_range(value, min_val, max_val)

        if min_val <= value <= max_val:
            assert result.is_valid
            assert result.value == value
        else:
            assert result.is_invalid
            assert len(result.errors) == 1

    @given(st.text())
    @settings(max_examples=100)
    def test_non_empty_string_correctness(self, value):
        """Non-empty string validation should correctly identify empty strings."""
        result = validate_non_empty_string(value)

        if value.strip():
            assert result.is_valid
            assert result.value == value
        else:
            assert result.is_invalid


# =============================================================================
# TESTS FOR CONFIGURATION VALIDATION
# =============================================================================

from primr.utils.type_guards import (
    ConfigSchema,
    validate_api_key_format,
    validate_config,
)


class TestConfigSchema:
    """Tests for ConfigSchema and validate_config."""

    def test_valid_config_with_required_keys(self):
        """Should accept config with all required keys."""
        schema = ConfigSchema(
            required_keys=["name", "value"], type_hints={"name": str, "value": int}
        )
        config = {"name": "test", "value": 42}
        result = validate_config(config, schema)
        assert result.is_valid
        assert result.value == config

    def test_missing_required_key(self):
        """Should reject config missing required key."""
        schema = ConfigSchema(required_keys=["name", "value"])
        config = {"name": "test"}
        result = validate_config(config, schema)
        assert result.is_invalid
        assert any("value" in e.field for e in result.errors)

    def test_applies_defaults(self):
        """Should apply defaults for missing optional keys."""
        schema = ConfigSchema(required_keys=["name"], optional_keys={"count": 10, "enabled": True})
        config = {"name": "test"}
        result = validate_config(config, schema)
        assert result.is_valid
        assert result.value["count"] == 10
        assert result.value["enabled"] is True
        assert result.has_warnings  # Should warn about defaults

    def test_type_validation(self):
        """Should validate types."""
        schema = ConfigSchema(required_keys=["count"], type_hints={"count": int})
        config = {"count": "not-an-int"}
        result = validate_config(config, schema)
        assert result.is_invalid
        assert result.errors[0].field == "count"

    def test_range_validation_min(self):
        """Should reject values below minimum."""
        schema = ConfigSchema(required_keys=["timeout"], ranges={"timeout": (1, 300)})
        config = {"timeout": 0}
        result = validate_config(config, schema)
        assert result.is_invalid
        assert ">= 1" in result.errors[0].expected

    def test_range_validation_max(self):
        """Should reject values above maximum."""
        schema = ConfigSchema(required_keys=["timeout"], ranges={"timeout": (1, 300)})
        config = {"timeout": 500}
        result = validate_config(config, schema)
        assert result.is_invalid
        assert "<= 300" in result.errors[0].expected

    def test_custom_validator(self):
        """Should run custom validators."""
        schema = ConfigSchema(required_keys=["email"], validators={"email": lambda x: "@" in x})
        config = {"email": "not-an-email"}
        result = validate_config(config, schema)
        assert result.is_invalid

    def test_collects_all_errors(self):
        """Should collect all errors, not just first."""
        schema = ConfigSchema(required_keys=["a", "b", "c"], type_hints={"a": int, "b": str})
        config = {"a": "wrong", "b": 123}  # Missing c, wrong types
        result = validate_config(config, schema)
        assert len(result.errors) >= 3  # Missing c + 2 type errors

    def test_preserves_extra_keys(self):
        """Should preserve keys not in schema."""
        schema = ConfigSchema(required_keys=["name"])
        config = {"name": "test", "extra": "data"}
        result = validate_config(config, schema)
        assert result.is_valid
        assert result.value["extra"] == "data"


class TestValidateApiKeyFormat:
    """Tests for validate_api_key_format."""

    def test_valid_key(self):
        """Should accept valid API key."""
        result = validate_api_key_format("AIzaSyD1234567890abcdef")
        assert result.is_valid

    def test_empty_key(self):
        """Should reject empty key."""
        result = validate_api_key_format("")
        assert result.is_invalid
        assert "empty" in result.errors[0].actual

    def test_whitespace_key(self):
        """Should reject whitespace-only key."""
        result = validate_api_key_format("   ")
        assert result.is_invalid

    def test_short_key(self):
        """Should reject suspiciously short key."""
        result = validate_api_key_format("abc")
        assert result.is_invalid
        assert "10+" in result.errors[0].expected

    def test_key_with_spaces(self):
        """Should reject key with spaces."""
        result = validate_api_key_format("AIza SyD 1234")
        assert result.is_invalid
        assert "spaces" in result.errors[0].expected

    def test_non_string(self):
        """Should reject non-string value."""
        result = validate_api_key_format(12345)  # type: ignore
        assert result.is_invalid


class TestConfigValidationProperty:
    """
    **Feature: primr-excellence, Property 1 (extended): Config Validation**
    **Validates: Requirements 1.3, 10.1, 10.2, 10.3**
    """

    @given(
        st.dictionaries(
            st.text(alphabet="abcdef", min_size=1, max_size=5),
            st.one_of(st.text(), st.integers(), st.booleans()),
            min_size=0,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_validate_config_never_raises(self, config):
        """validate_config should never raise, always return ValidationResult."""
        schema = ConfigSchema(
            required_keys=["x", "y"], optional_keys={"z": "default"}, type_hints={"x": str}
        )
        result = validate_config(config, schema)
        assert isinstance(result, ValidationResult)

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=100)
    def test_api_key_validation_never_raises(self, key):
        """validate_api_key_format should never raise."""
        result = validate_api_key_format(key)
        assert isinstance(result, ValidationResult)
        # Valid keys are non-empty, 10+ chars, no spaces
        if key.strip() and len(key) >= 10 and " " not in key:
            assert result.is_valid
