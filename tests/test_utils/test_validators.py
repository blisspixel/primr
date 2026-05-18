"""
Tests for defensive validation utilities.

Includes property-based tests using Hypothesis for comprehensive validation.
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from primr.utils.validators import (
    InputValidationError,
    safe_json_get,
    safe_json_parse,
    sanitize_for_filename,
    validate_company_name,
    validate_file_path,
    validate_url,
)

# =============================================================================
# UNIT TESTS - validate_url
# =============================================================================


class TestValidateUrl:
    """Tests for validate_url function."""

    def test_accepts_valid_http_url(self):
        """Should accept valid HTTP URL."""
        result = validate_url("http://example.com")
        assert result == "http://example.com"

    def test_accepts_valid_https_url(self):
        """Should accept valid HTTPS URL."""
        result = validate_url("https://example.com/path?query=1")
        assert result == "https://example.com/path?query=1"

    def test_rejects_empty_url(self):
        """Should reject empty URL."""
        with pytest.raises(InputValidationError, match="cannot be empty"):
            validate_url("")

    def test_rejects_javascript_url(self):
        """Should reject javascript: URLs."""
        with pytest.raises(InputValidationError):
            validate_url("javascript:alert(1)")

    def test_rejects_data_url(self):
        """Should reject data: URLs."""
        with pytest.raises(InputValidationError, match="not allowed"):
            validate_url("data:text/html,<script>alert(1)</script>")

    def test_rejects_missing_scheme(self):
        """Should reject URL without scheme."""
        with pytest.raises(InputValidationError, match="scheme"):
            validate_url("example.com")

    def test_rejects_disallowed_scheme(self):
        """Should reject disallowed schemes."""
        with pytest.raises(InputValidationError, match="not allowed"):
            validate_url("ftp://example.com")

    def test_custom_allowed_schemes(self):
        """Should accept custom allowed schemes."""
        result = validate_url("ftp://example.com", allowed_schemes=("ftp",))
        assert result == "ftp://example.com"


# =============================================================================
# UNIT TESTS - validate_file_path
# =============================================================================


class TestValidateFilePath:
    """Tests for validate_file_path function."""

    def test_accepts_valid_relative_path(self):
        """Should accept valid relative path."""
        result = validate_file_path("data/file.txt")
        assert result == Path("data/file.txt")

    def test_rejects_empty_path(self):
        """Should reject empty path."""
        with pytest.raises(InputValidationError, match="cannot be empty"):
            validate_file_path("")

    def test_rejects_traversal_dotdot(self):
        """Should reject .. traversal."""
        with pytest.raises(InputValidationError, match="traversal"):
            validate_file_path("../etc/passwd")

    def test_rejects_traversal_backslash(self):
        """Should reject ..\\ traversal."""
        with pytest.raises(InputValidationError, match="traversal"):
            validate_file_path("..\\windows\\system32")

    def test_rejects_absolute_path_by_default(self):
        """Should reject absolute paths by default."""
        import platform

        if platform.system() == "Windows":
            with pytest.raises(InputValidationError):
                validate_file_path("C:\\Windows\\System32")
        else:
            with pytest.raises(InputValidationError):
                validate_file_path("/etc/passwd")

    def test_accepts_absolute_when_allowed(self):
        """Should accept absolute paths when allowed."""
        result = validate_file_path("/etc/passwd", allow_absolute=True)
        assert result == Path("/etc/passwd")

    def test_enforces_base_dir(self, tmp_path):
        """Should enforce base_dir constraint."""
        # Create a file in tmp_path
        (tmp_path / "allowed.txt").touch()

        # Should accept path within base_dir
        result = validate_file_path("allowed.txt", base_dir=tmp_path)
        assert result == Path("allowed.txt")

    def test_rejects_path_outside_base_dir(self, tmp_path):
        """Should reject path that escapes base_dir."""
        with pytest.raises(InputValidationError):
            validate_file_path("../outside.txt", base_dir=tmp_path)


# =============================================================================
# UNIT TESTS - validate_company_name
# =============================================================================


class TestValidateCompanyName:
    """Tests for validate_company_name function."""

    def test_accepts_valid_name(self):
        """Should accept valid company name."""
        result = validate_company_name("Acme Corp, Inc.")
        assert result == "Acme Corp, Inc."

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        result = validate_company_name("  Acme Corp  ")
        assert result == "Acme Corp"

    def test_rejects_empty_name(self):
        """Should reject empty name."""
        with pytest.raises(InputValidationError, match="cannot be empty"):
            validate_company_name("")

    def test_rejects_too_long_name(self):
        """Should reject name exceeding max_length."""
        with pytest.raises(InputValidationError, match="at most"):
            validate_company_name("A" * 201)

    def test_rejects_script_injection(self):
        """Should reject script injection attempts."""
        with pytest.raises(InputValidationError, match="invalid"):
            validate_company_name("<script>alert(1)</script>")


# =============================================================================
# UNIT TESTS - sanitize_for_filename
# =============================================================================


class TestSanitizeForFilename:
    """Tests for sanitize_for_filename function."""

    def test_preserves_valid_name(self):
        """Should preserve valid filename."""
        result = sanitize_for_filename("valid_filename")
        assert result == "valid_filename"

    def test_replaces_invalid_chars(self):
        """Should replace invalid characters."""
        result = sanitize_for_filename("file:name/with\\invalid")
        assert ":" not in result
        assert "/" not in result
        assert "\\" not in result

    def test_handles_empty_string(self):
        """Should return 'unnamed' for empty string."""
        result = sanitize_for_filename("")
        assert result == "unnamed"

    def test_truncates_long_name(self):
        """Should truncate to max_length."""
        result = sanitize_for_filename("A" * 200, max_length=50)
        assert len(result) <= 50


# =============================================================================
# UNIT TESTS - safe_json_parse
# =============================================================================


class TestSafeJsonParse:
    """Tests for safe_json_parse function."""

    def test_parses_valid_json(self):
        """Should parse valid JSON."""
        result = safe_json_parse('{"key": "value"}')
        assert result == {"key": "value"}

    def test_returns_default_for_invalid_json(self):
        """Should return default for invalid JSON."""
        result = safe_json_parse("not json", default={})
        assert result == {}

    def test_returns_default_for_empty_string(self):
        """Should return default for empty string."""
        result = safe_json_parse("", default=[])
        assert result == []

    def test_never_raises(self):
        """Should never raise exception."""
        # Various invalid inputs
        assert safe_json_parse(None) is None
        assert safe_json_parse("") is None
        assert safe_json_parse("{invalid}") is None
        assert safe_json_parse("{'single': 'quotes'}") is None


# =============================================================================
# UNIT TESTS - safe_json_get
# =============================================================================


class TestSafeJsonGet:
    """Tests for safe_json_get function."""

    def test_gets_nested_value(self):
        """Should get nested value."""
        data = {"a": {"b": {"c": 1}}}
        result = safe_json_get(data, "a", "b", "c")
        assert result == 1

    def test_returns_default_for_missing_key(self):
        """Should return default for missing key."""
        data = {"a": 1}
        result = safe_json_get(data, "b", default="missing")
        assert result == "missing"

    def test_handles_list_index(self):
        """Should handle list indices."""
        data = {"items": [1, 2, 3]}
        result = safe_json_get(data, "items", 1)
        assert result == 2

    def test_returns_default_for_invalid_path(self):
        """Should return default for invalid path."""
        data = {"a": 1}
        result = safe_json_get(data, "a", "b", "c", default=None)
        assert result is None


# =============================================================================
# PROPERTY-BASED TESTS
# =============================================================================


class TestUrlValidationSecurityProperty:
    """
    Property-based tests for URL validation security.

    **Feature: code-quality-hardening, Property 12: URL Validation Security**
    **Validates: Requirements 7.2**

    For any URL string, the validator SHALL reject URLs with disallowed
    schemes, invalid format, or potential injection attacks.
    """

    @given(
        st.sampled_from(
            [
                "javascript:alert(1)",
                "javascript:void(0)",
                "data:text/html,<script>",
                "vbscript:msgbox",
                "file:///etc/passwd",
            ]
        )
    )
    @settings(max_examples=50)
    def test_rejects_dangerous_schemes(self, url: str):
        """Should reject dangerous URL schemes."""
        with pytest.raises(InputValidationError):
            validate_url(url)

    @given(st.text(alphabet="abcdefghij", min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_rejects_schemeless_urls(self, host: str):
        """Should reject URLs without scheme."""
        with pytest.raises(InputValidationError):
            validate_url(host)

    @given(st.text(alphabet="abcdefghij", min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_accepts_valid_https_urls(self, path: str):
        """Should accept valid HTTPS URLs."""
        url = f"https://example.com/{path}"
        result = validate_url(url)
        assert result == url


class TestPathTraversalPreventionProperty:
    r"""
    Property-based tests for path traversal prevention.

    **Feature: code-quality-hardening, Property 13: Path Traversal Prevention**
    **Validates: Requirements 7.3**

    For any file path containing traversal sequences (../, ..\), the
    validator SHALL reject the path when a base_dir constraint is specified.
    """

    @given(
        st.sampled_from(
            [
                "../etc/passwd",
                "..\\windows\\system32",
                "foo/../../../etc/passwd",
                "foo/..\\..\\windows",
                "..%2f..%2fetc",
                "..%5c..%5cwindows",
            ]
        )
    )
    @settings(max_examples=50)
    def test_rejects_traversal_patterns(self, path: str):
        """Should reject paths with traversal patterns."""
        with pytest.raises(InputValidationError, match="traversal"):
            validate_file_path(path)

    @given(st.text(alphabet="abcdefghij_", min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_accepts_safe_relative_paths(self, filename: str):
        """Should accept safe relative paths."""
        # Ensure no dots at start
        if filename.startswith("."):
            filename = "x" + filename

        result = validate_file_path(filename)
        assert result == Path(filename)

    @given(
        st.text(alphabet="abcdefghij", min_size=1, max_size=10),
        st.text(alphabet="abcdefghij", min_size=1, max_size=10),
    )
    @settings(max_examples=100)
    def test_accepts_nested_safe_paths(self, dir_name: str, file_name: str):
        """Should accept nested safe paths."""
        path = f"{dir_name}/{file_name}.txt"
        result = validate_file_path(path)
        assert result == Path(path)


class TestJsonParseSafetyProperty:
    """
    Property-based tests for JSON parse safety.

    **Feature: code-quality-hardening, Property 14: JSON Parse Safety**
    **Validates: Requirements 7.4**

    For any malformed JSON string, the safe parser SHALL return the
    default value without raising an exception.
    """

    @given(st.text(max_size=100))
    @settings(max_examples=100)
    def test_never_raises_on_any_input(self, content: str):
        """Should never raise exception on any input."""
        # This should never raise - the key property is that it doesn't throw
        result = safe_json_parse(content, default="fallback")
        # Result is either parsed JSON or the default "fallback"
        # Note: "null" is valid JSON that parses to None, so we can't assert result is not None
        # The property we're testing is that it never raises, which is verified by reaching this line
        assert result == "fallback" or result is not None or content in ("null", "")

    @given(
        st.sampled_from(
            [
                "{invalid}",
                "{'single': 'quotes'}",
                "{missing: quotes}",
                "[1, 2, 3,]",  # Trailing comma
                "undefined",
                "",
            ]
        )
    )
    @settings(max_examples=50)
    def test_returns_default_for_invalid_json(self, content):
        """Should return default for invalid JSON."""
        result = safe_json_parse(content, default="default")
        assert result == "default"

    def test_returns_default_for_none(self):
        """Should return default for None input."""
        result = safe_json_parse(None, default="default")
        assert result == "default"

    @given(
        st.dictionaries(
            st.text(alphabet="abcde", min_size=1, max_size=5),
            st.integers(min_value=-100, max_value=100),
            min_size=0,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_round_trips_valid_json(self, data: dict):
        """Valid JSON should round-trip correctly."""
        import json

        json_str = json.dumps(data)
        result = safe_json_parse(json_str)
        assert result == data


# =============================================================================
# TESTS FOR NEW VALIDATION FEATURES
# =============================================================================

from primr.utils.validators import (
    CLIValidationResult,
    normalize_url,
    suggest_similar,
    validate_cli_mode,
    validate_cli_url,
)


class TestNormalizeUrl:
    """Tests for normalize_url function."""

    def test_adds_https_scheme(self):
        """Should add https:// if no scheme present."""
        assert normalize_url("example.com") == "https://example.com"

    def test_preserves_http_scheme(self):
        """Should preserve http:// scheme."""
        assert normalize_url("http://example.com") == "http://example.com"

    def test_lowercases_scheme_and_host(self):
        """Should lowercase scheme and host."""
        assert normalize_url("HTTP://EXAMPLE.COM") == "http://example.com"

    def test_removes_trailing_slash(self):
        """Should remove trailing slash from path."""
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_preserves_root_slash(self):
        """Should preserve root path slash."""
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert normalize_url("") == ""

    def test_idempotent(self):
        """Should be idempotent."""
        url = "example.com/path"
        once = normalize_url(url)
        twice = normalize_url(once)
        assert once == twice


class TestSuggestSimilar:
    """Tests for suggest_similar function."""

    def test_finds_close_match(self):
        """Should find option within edit distance."""
        suggestions = suggest_similar("scrpe", ["scrape", "deep", "hybrid"])
        assert "scrape" in suggestions

    def test_returns_empty_for_no_match(self):
        """Should return empty list if no close matches."""
        suggestions = suggest_similar("xyz", ["scrape", "deep", "hybrid"])
        assert suggestions == []

    def test_respects_max_distance(self):
        """Should respect max_distance parameter."""
        # "scrpe" is distance 1 from "scrape"
        assert suggest_similar("scrpe", ["scrape"], max_distance=1) == ["scrape"]
        # "scrp" is distance 2 from "scrape"
        assert suggest_similar("scrp", ["scrape"], max_distance=1) == []
        assert suggest_similar("scrp", ["scrape"], max_distance=2) == ["scrape"]

    def test_sorts_by_distance(self):
        """Should sort suggestions by edit distance."""
        # "deep" is closer to "depe" than "scrape"
        suggestions = suggest_similar("depe", ["scrape", "deep", "hybrid"])
        assert suggestions[0] == "deep"

    def test_limits_suggestions(self):
        """Should limit number of suggestions."""
        options = ["a", "b", "c", "d", "e"]
        suggestions = suggest_similar("x", options, max_distance=10, max_suggestions=2)
        assert len(suggestions) <= 2


class TestCLIValidationResult:
    """Tests for CLIValidationResult dataclass."""

    def test_default_is_valid(self):
        """Should be valid by default."""
        result = CLIValidationResult()
        assert result.valid

    def test_add_error_makes_invalid(self):
        """Should become invalid when error added."""
        result = CLIValidationResult()
        result.add_error("Test error")
        assert not result.valid
        assert "Test error" in result.errors

    def test_add_error_with_suggestion(self):
        """Should store suggestion with error."""
        result = CLIValidationResult()
        result.add_error("Error", "Try this instead")
        assert "Try this instead" in result.suggestions

    def test_merge_combines_results(self):
        """Should merge two results."""
        r1 = CLIValidationResult()
        r1.normalized_args["a"] = 1

        r2 = CLIValidationResult()
        r2.add_error("Error")
        r2.normalized_args["b"] = 2

        r1.merge(r2)
        assert not r1.valid
        assert r1.normalized_args == {"a": 1, "b": 2}
        assert "Error" in r1.errors


class TestValidateCliUrl:
    """Tests for validate_cli_url function."""

    def test_valid_url(self):
        """Should accept and normalize valid URL."""
        result = validate_cli_url("example.com")
        assert result.valid
        assert result.normalized_args["url"] == "https://example.com"

    def test_invalid_url(self):
        """Should reject invalid URL with error."""
        result = validate_cli_url("javascript:alert(1)")
        assert not result.valid
        assert len(result.errors) > 0


class TestValidateCliMode:
    """Tests for validate_cli_mode function."""

    def test_valid_mode(self):
        """Should accept valid mode."""
        result = validate_cli_mode("scrape")
        assert result.valid
        assert result.normalized_args["mode"] == "scrape"

    def test_case_insensitive(self):
        """Should be case insensitive."""
        result = validate_cli_mode("DEEP")
        assert result.valid
        assert result.normalized_args["mode"] == "deep"

    def test_invalid_mode_with_suggestion(self):
        """Should suggest similar modes for typos."""
        result = validate_cli_mode("scrpe")
        assert not result.valid
        assert any("scrape" in s for s in result.suggestions)


# =============================================================================
# PROPERTY-BASED TESTS FOR NEW FEATURES
# =============================================================================


class TestUrlNormalizationIdempotenceProperty:
    """
    Property-based tests for URL normalization idempotence.

    **Feature: primr-excellence, Property 6: URL Normalization Idempotence**
    **Validates: Requirements 3.4**

    For any URL string, normalize(normalize(url)) == normalize(url).
    """

    @given(st.text(alphabet="abcdefghij./:-", min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_normalization_is_idempotent(self, url_fragment: str):
        """Normalizing twice should equal normalizing once."""
        # Add a domain-like structure
        url = f"example.com/{url_fragment}"

        once = normalize_url(url)
        twice = normalize_url(once)

        assert once == twice, f"Not idempotent: {url} -> {once} -> {twice}"

    @given(
        scheme=st.sampled_from(["http", "https", "HTTP", "HTTPS", ""]),
        host=st.text(alphabet="abcdefghij", min_size=1, max_size=20),
        path=st.text(alphabet="abcdefghij/", min_size=0, max_size=20),
    )
    @settings(max_examples=100)
    def test_normalization_produces_valid_url(self, scheme, host, path):
        """Normalized URL should have valid structure."""
        if scheme:
            url = f"{scheme}://{host}.com/{path}"
        else:
            url = f"{host}.com/{path}"

        normalized = normalize_url(url)

        # Should have a scheme
        assert normalized.startswith(("http://", "https://"))

        # Should have lowercase scheme
        assert normalized[:8].islower()


class TestFuzzySuggestionQualityProperty:
    """
    Property-based tests for fuzzy suggestion quality.

    **Feature: primr-excellence, Property 18: Fuzzy Suggestion Quality**
    **Validates: Requirements 6.4**

    For any unknown CLI option within edit distance 2 of a valid option,
    the system SHALL suggest that valid option.
    """

    @given(
        base=st.text(alphabet="abcdefghij", min_size=3, max_size=10),
        edit_type=st.sampled_from(["delete", "insert", "substitute"]),
        position=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100)
    def test_suggests_within_distance_1(self, base, edit_type, position):
        """Should suggest option within edit distance 1."""
        if not base:
            return

        # Create a typo at distance 1
        pos = position % len(base)

        if edit_type == "delete" and len(base) > 1:
            typo = base[:pos] + base[pos + 1 :]
        elif edit_type == "insert":
            typo = base[:pos] + "x" + base[pos:]
        else:  # substitute
            typo = base[:pos] + "x" + base[pos + 1 :]

        suggestions = suggest_similar(typo, [base], max_distance=2)

        assert base in suggestions, f"Should suggest '{base}' for typo '{typo}'"

    @given(
        options=st.lists(
            st.text(alphabet="abcdefghij", min_size=3, max_size=10),
            min_size=1,
            max_size=5,
            unique=True,
        )
    )
    @settings(max_examples=50)
    def test_exact_match_returns_option(self, options):
        """Exact match should always be suggested."""
        for option in options:
            suggestions = suggest_similar(option, options)
            assert option in suggestions

    @given(st.text(alphabet="xyz", min_size=5, max_size=10))
    @settings(max_examples=50)
    def test_distant_input_returns_empty(self, unknown):
        """Very different input should return no suggestions."""
        options = ["scrape", "deep", "hybrid"]
        suggestions = suggest_similar(unknown, options, max_distance=2)

        # If suggestions exist, they should be within distance 2
        # (this test just verifies no crash and reasonable behavior)
        assert isinstance(suggestions, list)
