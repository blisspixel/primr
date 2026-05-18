"""
Property-based tests for the Pydantic Configuration Validation system.

This module contains property tests that verify universal correctness properties
of the ConfigValidator implementation as specified in the PhD-Level Excellence spec.

**Feature: phd-level-excellence**
**Validates: Requirements 6.1-6.8**
"""

from typing import Any

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
import pytest

from primr.prompts.validation import (
    CURRENT_SCHEMA_VERSION,
    ConfigValidator,
    PromptConfigModel,
    SchemaVersion,
    SchemaVersionError,
    SectionPosition,
)

# =============================================================================
# STRATEGIES FOR GENERATING TEST DATA
# =============================================================================

# Strategy for generating valid section IDs (non-empty alphanumeric with underscores)
section_id_strategy = st.from_regex(r"[a-z][a-z0-9_]{0,29}", fullmatch=True)

# Strategy for generating valid section names
section_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")), min_size=1, max_size=50
).filter(lambda x: x.strip())

# Strategy for generating valid part numbers (1-5)
part_number_strategy = st.integers(min_value=1, max_value=5)

# Strategy for generating valid semantic versions
version_strategy = st.from_regex(r"\d{1,3}\.\d{1,3}\.\d{1,3}", fullmatch=True)

# Strategy for generating valid schema versions
schema_version_strategy = st.sampled_from([v.value for v in SchemaVersion])

# Strategy for generating invalid schema versions
invalid_schema_version_strategy = st.from_regex(r"\d+\.\d+", fullmatch=True).filter(
    lambda x: x not in [v.value for v in SchemaVersion]
)

# Strategy for generating section positions
position_strategy = st.sampled_from([p.value for p in SectionPosition])

# Strategy for generating document purposes (min 10 chars)
document_purpose_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")), min_size=10, max_size=500
).filter(lambda x: len(x.strip()) >= 10)

# Strategy for generating covers lists
covers_strategy = st.lists(
    st.text(min_size=1, max_size=100).filter(lambda x: x.strip()), min_size=0, max_size=5
)

# Strategy for generating epistemic rules
epistemic_rules_strategy = st.dictionaries(
    st.from_regex(r"[a-z_]{1,20}", fullmatch=True),
    st.text(min_size=1, max_size=200),
    min_size=0,
    max_size=5,
)

# Strategy for generating formatting rules
formatting_strategy = st.dictionaries(
    st.from_regex(r"[a-z_]{1,20}", fullmatch=True),
    st.text(min_size=1, max_size=200),
    min_size=0,
    max_size=5,
)


def generate_valid_section(
    section_id: str,
    name: str,
    part: int,
    position: str = "middle",
    covers: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a valid section dictionary."""
    return {
        "id": section_id,
        "name": name,
        "part": part,
        "purpose": "Test purpose for this section",
        "covers": covers or [],
        "depth": "Standard depth",
        "position": position,
        "subsections": [],
    }


def generate_valid_meta(
    name: str,
    version: str,
    schema_version: str | None = None,
) -> dict[str, Any]:
    """Generate a valid meta dictionary."""
    meta = {
        "name": name,
        "version": version,
        "description": "Test description",
        "expected_pages": "10-20",
    }
    if schema_version:
        meta["schema_version"] = schema_version
    return meta


def generate_valid_config(
    meta_name: str = "Test Prompt",
    meta_version: str = "1.0.0",
    schema_version: str | None = None,
    document_purpose: str = "This is a test document purpose with sufficient length.",
    sections: list[dict[str, Any]] | None = None,
    epistemic_rules: dict[str, str] | None = None,
    formatting: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Generate a valid complete configuration dictionary."""
    if sections is None:
        sections = [generate_valid_section("test_section", "Test Section", 1)]

    return {
        "meta": generate_valid_meta(meta_name, meta_version, schema_version),
        "document_purpose": document_purpose,
        "sections": sections,
        "epistemic_rules": epistemic_rules or {},
        "formatting": formatting or {},
    }


# =============================================================================
# PROPERTY 16: VALID CONFIG ACCEPTANCE
# =============================================================================


class TestValidConfigAcceptance:
    """
    **Property 16: Valid Config Acceptance**

    For any YAML configuration that conforms to the Pydantic schema (all required
    fields present with correct types), `validate_prompt_config()` SHALL return a
    valid `PromptConfigModel` without raising exceptions.

    **Validates: Requirements 6.2**
    """

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
        schema_version=schema_version_strategy,
        document_purpose=document_purpose_strategy,
        section_id=section_id_strategy,
        section_name=section_name_strategy,
        part=part_number_strategy,
        position=position_strategy,
        covers=covers_strategy,
        epistemic_rules=epistemic_rules_strategy,
        formatting=formatting_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_config_is_accepted(
        self,
        meta_name: str,
        meta_version: str,
        schema_version: str,
        document_purpose: str,
        section_id: str,
        section_name: str,
        part: int,
        position: str,
        covers: list[str],
        epistemic_rules: dict[str, str],
        formatting: dict[str, str],
    ):
        """Valid configurations should be accepted without exceptions."""
        # Feature: phd-level-excellence, Property 16: Valid Config Acceptance

        config = generate_valid_config(
            meta_name=meta_name,
            meta_version=meta_version,
            schema_version=schema_version,
            document_purpose=document_purpose,
            sections=[generate_valid_section(section_id, section_name, part, position, covers)],
            epistemic_rules=epistemic_rules,
            formatting=formatting,
        )

        validator = ConfigValidator()

        # Should not raise any exception
        result = validator.validate_prompt_config(config)

        # Should return a valid PromptConfigModel
        assert isinstance(result, PromptConfigModel)
        assert result.meta.name == meta_name
        assert result.meta.version == meta_version
        assert result.document_purpose == document_purpose
        assert len(result.sections) == 1
        assert result.sections[0].id == section_id
        assert result.sections[0].name == section_name
        assert result.sections[0].part == part

    @given(
        num_sections=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_multiple_sections_with_unique_ids_accepted(self, num_sections: int):
        """Configurations with multiple sections with unique IDs should be accepted."""
        # Feature: phd-level-excellence, Property 16: Valid Config Acceptance

        sections = [
            generate_valid_section(f"section_{i}", f"Section {i}", (i % 5) + 1)
            for i in range(num_sections)
        ]

        config = generate_valid_config(sections=sections)
        validator = ConfigValidator()

        result = validator.validate_prompt_config(config)

        assert isinstance(result, PromptConfigModel)
        assert len(result.sections) == num_sections

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_config_without_optional_fields_accepted(self, meta_name: str, meta_version: str):
        """Configurations without optional fields should be accepted."""
        # Feature: phd-level-excellence, Property 16: Valid Config Acceptance

        # Minimal valid config
        config = {
            "meta": {
                "name": meta_name,
                "version": meta_version,
            },
            "document_purpose": "This is a minimal test document purpose.",
            "sections": [
                {
                    "id": "minimal_section",
                    "name": "Minimal Section",
                    "part": 1,
                }
            ],
        }

        validator = ConfigValidator()
        result = validator.validate_prompt_config(config)

        assert isinstance(result, PromptConfigModel)
        assert result.meta.name == meta_name
        assert result.epistemic_rules == {}
        assert result.formatting == {}

    @given(schema_version=schema_version_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_all_supported_schema_versions_accepted(self, schema_version: str):
        """All supported schema versions should be accepted."""
        # Feature: phd-level-excellence, Property 16: Valid Config Acceptance

        config = generate_valid_config(schema_version=schema_version)
        validator = ConfigValidator()

        result = validator.validate_prompt_config(config)

        assert isinstance(result, PromptConfigModel)
        assert result.meta.schema_version.value == schema_version


# =============================================================================
# PROPERTY 17: INVALID CONFIG REJECTION WITH DETAILS
# =============================================================================


class TestInvalidConfigRejection:
    """
    **Property 17: Invalid Config Rejection with Details**

    For any YAML configuration with missing required fields or incorrect types,
    `validate_prompt_config()` SHALL raise a `ValidationError` with error messages
    that include the field path and expected type.

    **Validates: Requirements 6.3, 6.6, 6.7**
    """

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_meta_rejected(self, meta_name: str, meta_version: str):
        """Configurations missing the 'meta' field should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        # Error should mention the missing field
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("meta" in str(e.get("loc", ())) for e in errors)

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_document_purpose_rejected(self, meta_name: str, meta_version: str):
        """Configurations missing 'document_purpose' should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "meta": generate_valid_meta(meta_name, meta_version),
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("document_purpose" in str(e.get("loc", ())) for e in errors)

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_sections_rejected(self, meta_name: str, meta_version: str):
        """Configurations missing 'sections' should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "meta": generate_valid_meta(meta_name, meta_version),
            "document_purpose": "This is a test document purpose with sufficient length.",
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("sections" in str(e.get("loc", ())) for e in errors)

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_empty_sections_rejected(self, meta_name: str, meta_version: str):
        """Configurations with empty sections list should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "meta": generate_valid_meta(meta_name, meta_version),
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [],
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_meta_name_rejected(self, meta_name: str, meta_version: str):
        """Configurations with missing meta.name should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "meta": {
                "version": meta_version,
            },
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0
        # Should indicate the path to the missing field
        assert any("name" in str(e.get("loc", ())) for e in errors)

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_meta_version_rejected(self, meta_name: str, meta_version: str):
        """Configurations with missing meta.version should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "meta": {
                "name": meta_name,
            },
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("version" in str(e.get("loc", ())) for e in errors)

    @given(
        meta_name=section_name_strategy,
        invalid_version=st.text(min_size=1, max_size=20).filter(
            lambda x: not x.replace(".", "").isdigit() or x.count(".") != 2
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_version_format_rejected(self, meta_name: str, invalid_version: str):
        """Configurations with invalid version format should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        # Skip versions that accidentally match the pattern
        assume(
            not invalid_version
            or not all(part.isdigit() for part in invalid_version.split("."))
            or invalid_version.count(".") != 2
        )

        config = {
            "meta": {
                "name": meta_name,
                "version": invalid_version,
            },
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
        invalid_part=st.integers().filter(lambda x: x < 1 or x > 5),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_part_number_rejected(
        self, meta_name: str, meta_version: str, invalid_part: int
    ):
        """Configurations with invalid part numbers should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "meta": generate_valid_meta(meta_name, meta_version),
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [
                {
                    "id": "test_section",
                    "name": "Test Section",
                    "part": invalid_part,
                }
            ],
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_duplicate_section_ids_rejected(self, meta_name: str, meta_version: str):
        """Configurations with duplicate section IDs should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "meta": generate_valid_meta(meta_name, meta_version),
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [
                generate_valid_section("duplicate_id", "Section 1", 1),
                generate_valid_section("duplicate_id", "Section 2", 2),
            ],
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0
        # Error message should mention duplicates
        error_str = str(exc_info.value)
        assert "duplicate" in error_str.lower() or "unique" in error_str.lower()

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
        short_purpose=st.text(min_size=0, max_size=9),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_short_document_purpose_rejected(
        self, meta_name: str, meta_version: str, short_purpose: str
    ):
        """Configurations with document_purpose < 10 chars should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "meta": generate_valid_meta(meta_name, meta_version),
            "document_purpose": short_purpose,
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
        invalid_position=st.text(min_size=1, max_size=20).filter(
            lambda x: x not in [p.value for p in SectionPosition]
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_position_rejected(
        self, meta_name: str, meta_version: str, invalid_position: str
    ):
        """Configurations with invalid section positions should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "meta": generate_valid_meta(meta_name, meta_version),
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [
                {
                    "id": "test_section",
                    "name": "Test Section",
                    "part": 1,
                    "position": invalid_position,
                }
            ],
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_wrong_type_for_sections_rejected(self, meta_name: str, meta_version: str):
        """Configurations with wrong type for sections should be rejected."""
        # Feature: phd-level-excellence, Property 17: Invalid Config Rejection with Details

        config = {
            "meta": generate_valid_meta(meta_name, meta_version),
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": "not a list",  # Wrong type
        }

        validator = ConfigValidator()

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_prompt_config(config)

        errors = exc_info.value.errors()
        assert len(errors) > 0


# =============================================================================
# PROPERTY 18: SCHEMA VERSION VALIDATION
# =============================================================================


class TestSchemaVersionValidation:
    """
    **Property 18: Schema Version Validation**

    For any configuration with an unsupported `schema_version` value, the validator
    SHALL raise `SchemaVersionError` with the current supported version in the error
    message.

    **Validates: Requirements 6.4, 6.5**
    """

    @given(
        invalid_version=st.from_regex(r"\d+\.\d+", fullmatch=True).filter(
            lambda x: x not in [v.value for v in SchemaVersion]
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_unsupported_schema_version_raises_error(self, invalid_version: str):
        """Unsupported schema versions should raise SchemaVersionError."""
        # Feature: phd-level-excellence, Property 18: Schema Version Validation

        config = {
            "meta": {
                "name": "Test Prompt",
                "version": "1.0.0",
                "schema_version": invalid_version,
            },
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        with pytest.raises(SchemaVersionError) as exc_info:
            validator.check_schema_version(config)

        error = exc_info.value
        # Error should contain the current version
        assert CURRENT_SCHEMA_VERSION.value in str(error)
        # Error should contain supported versions
        assert any(v.value in str(error) for v in SchemaVersion)
        # Error should have the unsupported version stored
        assert error.unsupported_version == invalid_version

    @given(schema_version=schema_version_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_supported_schema_versions_pass_check(self, schema_version: str):
        """Supported schema versions should pass the version check."""
        # Feature: phd-level-excellence, Property 18: Schema Version Validation

        config = {
            "meta": {
                "name": "Test Prompt",
                "version": "1.0.0",
                "schema_version": schema_version,
            },
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        # Should not raise
        version, is_current = validator.check_schema_version(config)

        assert version.value == schema_version
        assert is_current == (schema_version == CURRENT_SCHEMA_VERSION.value)

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_schema_version_defaults_to_1_0(self, meta_name: str, meta_version: str):
        """Configs without schema_version should default to 1.0."""
        # Feature: phd-level-excellence, Property 18: Schema Version Validation

        config = {
            "meta": {
                "name": meta_name,
                "version": meta_version,
                # No schema_version specified
            },
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        version, is_current = validator.check_schema_version(config)

        # Should default to 1.0
        assert version == SchemaVersion.V1_0

    @given(
        invalid_version=st.text(min_size=1, max_size=10).filter(
            lambda x: not x.replace(".", "").isdigit() and x not in [v.value for v in SchemaVersion]
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_non_numeric_schema_version_raises_error(self, invalid_version: str):
        """Non-numeric schema versions should raise SchemaVersionError."""
        # Feature: phd-level-excellence, Property 18: Schema Version Validation

        config = {
            "meta": {
                "name": "Test Prompt",
                "version": "1.0.0",
                "schema_version": invalid_version,
            },
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        with pytest.raises(SchemaVersionError) as exc_info:
            validator.check_schema_version(config)

        error = exc_info.value
        assert error.unsupported_version == invalid_version
        assert error.current_version == CURRENT_SCHEMA_VERSION.value

    def test_schema_version_error_provides_migration_guidance(self):
        """SchemaVersionError should provide migration guidance."""
        # Feature: phd-level-excellence, Property 18: Schema Version Validation

        config = {
            "meta": {
                "name": "Test Prompt",
                "version": "1.0.0",
                "schema_version": "99.99",  # Definitely unsupported
            },
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        with pytest.raises(SchemaVersionError) as exc_info:
            validator.check_schema_version(config)

        error = exc_info.value
        error_str = str(error)

        # Should contain migration guidance
        assert "migration" in error_str.lower() or "supported" in error_str.lower()
        # Should list supported versions
        assert any(v.value in error_str for v in SchemaVersion)

    @given(schema_version=schema_version_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_validate_with_version_check_validates_both(self, schema_version: str):
        """validate_with_version_check should check version AND validate config."""
        # Feature: phd-level-excellence, Property 18: Schema Version Validation

        config = generate_valid_config(schema_version=schema_version)

        validator = ConfigValidator()

        # Should succeed for valid config with valid schema version
        result = validator.validate_with_version_check(config)

        assert isinstance(result, PromptConfigModel)
        assert result.meta.schema_version.value == schema_version

    def test_validate_with_version_check_rejects_invalid_version_first(self):
        """validate_with_version_check should reject invalid version before validation."""
        # Feature: phd-level-excellence, Property 18: Schema Version Validation

        # Config with invalid schema version but otherwise valid
        config = {
            "meta": {
                "name": "Test Prompt",
                "version": "1.0.0",
                "schema_version": "99.99",
            },
            "document_purpose": "This is a test document purpose with sufficient length.",
            "sections": [generate_valid_section("test", "Test", 1)],
        }

        validator = ConfigValidator()

        # Should raise SchemaVersionError, not ValidationError
        with pytest.raises(SchemaVersionError):
            validator.validate_with_version_check(config)


# =============================================================================
# JSON SCHEMA EXPORT TESTS
# =============================================================================


class TestJsonSchemaExport:
    """Tests for JSON Schema export functionality."""

    def test_export_json_schema_returns_valid_schema(self):
        """export_json_schema should return a valid JSON Schema."""
        # Feature: phd-level-excellence, Validates: Requirement 6.8

        validator = ConfigValidator()
        schema = validator.export_json_schema()

        # Should be a dictionary
        assert isinstance(schema, dict)

        # Should have standard JSON Schema fields
        assert "properties" in schema or "$defs" in schema
        assert "type" in schema
        assert schema["type"] == "object"

    def test_export_json_schema_includes_required_fields(self):
        """Exported schema should include required fields."""
        # Feature: phd-level-excellence, Validates: Requirement 6.8

        validator = ConfigValidator()
        schema = validator.export_json_schema()

        # Should have required fields listed
        assert "required" in schema
        assert "meta" in schema["required"]
        assert "document_purpose" in schema["required"]
        assert "sections" in schema["required"]

    def test_export_json_schema_includes_section_spec(self):
        """Exported schema should include section specification."""
        # Feature: phd-level-excellence, Validates: Requirement 6.8

        validator = ConfigValidator()
        schema = validator.export_json_schema()

        # Should have definitions for nested models
        defs = schema.get("$defs", {})

        # Should include SectionSpecModel definition
        assert "SectionSpecModel" in defs or any("section" in key.lower() for key in defs)
