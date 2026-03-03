"""
Tests for security utilities.

Tests for:
- Constant-time comparison
- Secret hashing and verification
- Sensitive data masking
- Security audit logging
- Input sanitization
"""

import pytest

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


class TestSecureCompare:
    """Tests for constant-time comparison."""

    def test_equal_strings(self):
        """Equal strings return True."""
        assert secure_compare("secret123", "secret123") is True

    def test_unequal_strings(self):
        """Unequal strings return False."""
        assert secure_compare("secret123", "secret456") is False

    def test_equal_bytes(self):
        """Equal bytes return True."""
        assert secure_compare(b"secret", b"secret") is True

    def test_unequal_bytes(self):
        """Unequal bytes return False."""
        assert secure_compare(b"secret", b"other") is False

    def test_mixed_string_bytes(self):
        """Mixed string and bytes comparison works."""
        assert secure_compare("secret", b"secret") is True
        assert secure_compare(b"secret", "secret") is True

    def test_empty_strings(self):
        """Empty strings compare correctly."""
        assert secure_compare("", "") is True
        assert secure_compare("", "x") is False

    def test_different_lengths(self):
        """Different length strings return False."""
        assert secure_compare("short", "longer_string") is False


class TestHashSecret:
    """Tests for secret hashing."""

    def test_hash_produces_output(self):
        """Hashing produces non-empty output."""
        result = hash_secret("my_secret")
        assert result
        assert "$" in result  # salt$hash format

    def test_hash_is_deterministic_with_salt(self):
        """Same secret and salt produce same hash."""
        salt = "fixed_salt_12345678901234567890"
        hash1 = hash_secret("secret", salt=salt)
        hash2 = hash_secret("secret", salt=salt)
        assert hash1 == hash2

    def test_hash_differs_without_salt(self):
        """Different calls without salt produce different hashes."""
        hash1 = hash_secret("secret")
        hash2 = hash_secret("secret")
        # Different salts mean different hashes
        assert hash1 != hash2

    def test_different_secrets_different_hashes(self):
        """Different secrets produce different hashes."""
        salt = "fixed_salt_12345678901234567890"
        hash1 = hash_secret("secret1", salt=salt)
        hash2 = hash_secret("secret2", salt=salt)
        assert hash1 != hash2


class TestVerifyHashedSecret:
    """Tests for secret verification."""

    def test_verify_correct_secret(self):
        """Correct secret verifies successfully."""
        hashed = hash_secret("my_secret")
        assert verify_hashed_secret("my_secret", hashed) is True

    def test_verify_wrong_secret(self):
        """Wrong secret fails verification."""
        hashed = hash_secret("my_secret")
        assert verify_hashed_secret("wrong_secret", hashed) is False

    def test_verify_invalid_hash_format(self):
        """Invalid hash format returns False."""
        assert verify_hashed_secret("secret", "invalid_no_dollar") is False

    def test_verify_empty_secret(self):
        """Empty secret can be hashed and verified."""
        hashed = hash_secret("")
        assert verify_hashed_secret("", hashed) is True
        assert verify_hashed_secret("x", hashed) is False


class TestMaskSensitiveData:
    """Tests for sensitive data masking."""

    def test_mask_api_key(self):
        """API keys are masked."""
        text = 'api_key = "sk-1234567890abcdefghijklmnop"'
        result = mask_sensitive_data(text)
        assert "sk-1234567890" not in result
        assert "[REDACTED]" in result or "[OPENAI_API_KEY]" in result

    def test_mask_password(self):
        """Passwords are masked."""
        text = 'password = "supersecret123"'
        result = mask_sensitive_data(text)
        assert "supersecret123" not in result
        assert "[REDACTED]" in result

    def test_mask_bearer_token(self):
        """Bearer tokens are masked."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = mask_sensitive_data(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result

    def test_mask_google_api_key(self):
        """Google API keys are masked."""
        text = "key=AIzaSyA1234567890abcdefghijklmnopqrstuv"
        result = mask_sensitive_data(text)
        assert "AIzaSyA1234567890" not in result

    def test_preserve_non_sensitive(self):
        """Non-sensitive data is preserved."""
        text = "mode=full, company=Acme Corp"
        result = mask_sensitive_data(text)
        assert "mode=full" in result
        assert "company=Acme Corp" in result

    def test_empty_string(self):
        """Empty string returns empty."""
        assert mask_sensitive_data("") == ""


class TestMaskDictValues:
    """Tests for dictionary value masking."""

    def test_mask_api_key_in_dict(self):
        """API key values are masked."""
        data = {"api_key": "secret123", "mode": "full"}
        result = mask_dict_values(data)
        assert result["api_key"] == "[REDACTED]"
        assert result["mode"] == "full"

    def test_mask_nested_dict(self):
        """Nested dictionaries are masked."""
        data = {
            "config": {
                "api_key": "secret",
                "timeout": 30
            }
        }
        result = mask_dict_values(data)
        assert result["config"]["api_key"] == "[REDACTED]"
        assert result["config"]["timeout"] == 30

    def test_mask_various_key_formats(self):
        """Various key formats are masked."""
        data = {
            "api_key": "secret1",
            "apiKey": "secret2",  # Not in default list (camelCase)
            "token": "secret3",
            "password": "secret4",
        }
        result = mask_dict_values(data)
        assert result["api_key"] == "[REDACTED]"
        assert result["token"] == "[REDACTED]"
        assert result["password"] == "[REDACTED]"

    def test_custom_sensitive_keys(self):
        """Custom sensitive keys can be specified."""
        data = {"custom_secret": "value", "normal": "data"}
        result = mask_dict_values(data, sensitive_keys={"custom_secret"})
        assert result["custom_secret"] == "[REDACTED]"
        assert result["normal"] == "data"


class TestSanitizeLogInput:
    """Tests for log input sanitization."""

    def test_remove_control_characters(self):
        """Control characters are removed."""
        text = "Hello\x00World\x1f"
        result = sanitize_log_input(text)
        assert "\x00" not in result
        assert "\x1f" not in result
        assert "HelloWorld" in result

    def test_truncate_long_input(self):
        """Long input is truncated."""
        text = "x" * 500
        result = sanitize_log_input(text, max_length=100)
        assert len(result) < 150  # 100 + truncation message
        assert "[truncated]" in result

    def test_mask_sensitive_in_input(self):
        """Sensitive data in input is masked."""
        text = "api_key=sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890ab"
        result = sanitize_log_input(text)
        assert "sk-1234567890" not in result

    def test_preserve_newlines_tabs(self):
        """Newlines and tabs are preserved."""
        text = "line1\nline2\ttabbed"
        result = sanitize_log_input(text)
        assert "\n" in result
        assert "\t" in result


class TestGenerateSecureToken:
    """Tests for secure token generation."""

    def test_generates_hex_string(self):
        """Token is a hex string."""
        token = generate_secure_token(16)
        assert all(c in "0123456789abcdef" for c in token)

    def test_correct_length(self):
        """Token has correct length (2x bytes for hex)."""
        token = generate_secure_token(16)
        assert len(token) == 32

    def test_unique_tokens(self):
        """Each call generates unique token."""
        tokens = [generate_secure_token() for _ in range(100)]
        assert len(set(tokens)) == 100


class TestGenerateSecureId:
    """Tests for secure ID generation."""

    def test_generates_id(self):
        """ID is generated."""
        id_ = generate_secure_id()
        assert id_
        assert len(id_) > 10

    def test_with_prefix(self):
        """Prefix is included."""
        id_ = generate_secure_id("job")
        assert id_.startswith("job_")

    def test_unique_ids(self):
        """Each call generates unique ID."""
        ids = [generate_secure_id("test") for _ in range(100)]
        assert len(set(ids)) == 100


class TestGetSecretFromEnv:
    """Tests for environment secret retrieval."""

    def test_get_existing_secret(self, monkeypatch):
        """Existing secret is retrieved."""
        monkeypatch.setenv("TEST_SECRET", "my_secret_value")
        result = get_secret_from_env("TEST_SECRET")
        assert result == "my_secret_value"

    def test_missing_required_secret(self, monkeypatch):
        """Missing required secret raises error."""
        monkeypatch.delenv("MISSING_SECRET", raising=False)
        with pytest.raises(ValueError, match="not found"):
            get_secret_from_env("MISSING_SECRET", required=True)

    def test_missing_optional_secret(self, monkeypatch):
        """Missing optional secret returns None."""
        monkeypatch.delenv("MISSING_SECRET", raising=False)
        result = get_secret_from_env("MISSING_SECRET", required=False)
        assert result is None

    def test_short_secret_required(self, monkeypatch):
        """Short required secret raises error."""
        monkeypatch.setenv("SHORT_SECRET", "abc")
        with pytest.raises(ValueError, match="too short"):
            get_secret_from_env("SHORT_SECRET", required=True, min_length=10)

    def test_strips_whitespace(self, monkeypatch):
        """Whitespace is stripped from secret."""
        monkeypatch.setenv("PADDED_SECRET", "  secret_value  ")
        result = get_secret_from_env("PADDED_SECRET")
        assert result == "secret_value"


class TestSecurityAuditLogger:
    """Tests for security audit logger."""

    def test_log_auth_success(self, caplog):
        """Auth success is logged."""
        import logging
        audit = SecurityAuditLogger("test")

        with caplog.at_level(logging.INFO):
            audit.log_auth_success(user_id="user123", method="jwt")

        assert "AUTH_SUCCESS" in caplog.text
        assert "user123" in caplog.text

    def test_log_auth_failure(self, caplog):
        """Auth failure is logged."""
        import logging
        audit = SecurityAuditLogger("test")

        with caplog.at_level(logging.WARNING):
            audit.log_auth_failure(reason="invalid_token", ip="192.168.1.1")

        assert "AUTH_FAILURE" in caplog.text
        assert "invalid_token" in caplog.text

    def test_log_security_violation(self, caplog):
        """Security violation is logged."""
        import logging
        audit = SecurityAuditLogger("test")

        with caplog.at_level(logging.ERROR):
            audit.log_security_violation(
                violation_type="ssrf_attempt",
                details="Attempted access to 169.254.169.254"
            )

        assert "SECURITY_VIOLATION" in caplog.text
        assert "ssrf_attempt" in caplog.text

    def test_log_rate_limit(self, caplog):
        """Rate limit is logged."""
        import logging
        audit = SecurityAuditLogger("test")

        with caplog.at_level(logging.WARNING):
            audit.log_rate_limit(user_id="user123", endpoint="/api/research", limit=10)

        assert "RATE_LIMIT" in caplog.text
        assert "user123" in caplog.text
