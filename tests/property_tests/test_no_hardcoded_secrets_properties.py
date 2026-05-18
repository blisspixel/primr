"""
Property Test: No Hardcoded Secrets

**Property 1: No Hardcoded Secrets**
Scan all files in deploy/** for API key patterns.

**Validates: Requirements 8.1**

This test ensures that no sensitive credentials are accidentally committed
to the deployment scripts or configuration files.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

# =============================================================================
# SECRET PATTERNS
# =============================================================================

# Patterns that indicate potential hardcoded secrets
SECRET_PATTERNS = [
    # AWS
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"aws_secret_access_key\s*=\s*['\"][^'\"]+['\"]", "AWS Secret Access Key assignment"),
    (r"['\"][A-Za-z0-9/+=]{40}['\"]", "Potential AWS Secret Key (40 char base64)"),
    # Azure
    (
        r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[^;]+",
        "Azure Storage Connection String",
    ),
    (r"['\"][A-Za-z0-9+/]{86}==['\"]", "Potential Azure Key (88 char base64)"),
    # GCP
    (r'"type"\s*:\s*"service_account"', "GCP Service Account JSON"),
    (r'"private_key"\s*:\s*"-----BEGIN', "GCP Private Key"),
    # Generic API Keys
    (r"api[_-]?key\s*[=:]\s*['\"][a-zA-Z0-9_-]{20,}['\"]", "Generic API Key assignment"),
    (r"secret[_-]?key\s*[=:]\s*['\"][a-zA-Z0-9_-]{20,}['\"]", "Generic Secret Key assignment"),
    (r"password\s*[=:]\s*['\"][^'\"]{8,}['\"]", "Hardcoded password"),
    (r"token\s*[=:]\s*['\"][a-zA-Z0-9_-]{20,}['\"]", "Hardcoded token"),
    # OpenAI / LLM Keys
    (r"sk-[a-zA-Z0-9]{48}", "OpenAI API Key"),
    (r"sk-proj-[a-zA-Z0-9_-]{48,}", "OpenAI Project API Key"),
    # Anthropic
    (r"sk-ant-[a-zA-Z0-9_-]{40,}", "Anthropic API Key"),
    # Google AI
    (r"AIza[0-9A-Za-z_-]{35}", "Google API Key"),
    # Private Keys
    (r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "Private Key"),
    (r"-----BEGIN CERTIFICATE-----", "Certificate (may contain private data)"),
]

# Files/patterns to exclude from scanning
EXCLUDE_PATTERNS = [
    r"\.pyc$",
    r"__pycache__",
    r"\.git/",
    r"\.pytest_cache/",
    r"\.hypothesis/",
    r"node_modules/",
    r"\.env\.example$",  # Example files are OK
    r"test_.*\.py$",  # Test files may have mock patterns
    r"conftest\.py$",
]

# Allowed patterns (false positives)
ALLOWED_PATTERNS = [
    r"AKIA\[0-9A-Z\]",  # Regex pattern in documentation
    r"sk-\[a-zA-Z0-9\]",  # Regex pattern in documentation
    r"example",  # Example values
    r"placeholder",
    r"your[-_]?api[-_]?key",
    r"<.*>",  # Template placeholders
    r"\$\{.*\}",  # Variable substitutions
    r"\$[A-Z_]+",  # Environment variable references
    r"os\.environ",  # Environment variable access
    r"getenv",  # Environment variable access
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_deploy_files() -> Iterator[Path]:
    """Get all files in the deploy directory."""
    deploy_dir = Path("deploy")
    if not deploy_dir.exists():
        return

    for path in deploy_dir.rglob("*"):
        if path.is_file():
            # Check exclusions
            path_str = str(path)
            if any(re.search(pattern, path_str) for pattern in EXCLUDE_PATTERNS):
                continue
            yield path


def is_allowed_match(line: str, match: str) -> bool:
    """Check if a match is an allowed false positive."""
    line_lower = line.lower()
    match_lower = match.lower()

    for pattern in ALLOWED_PATTERNS:
        if re.search(pattern, line_lower, re.IGNORECASE):
            return True
        if re.search(pattern, match_lower, re.IGNORECASE):
            return True

    return False


def scan_file_for_secrets(file_path: Path) -> list[tuple[int, str, str, str]]:
    """
    Scan a file for potential hardcoded secrets.

    Returns:
        List of (line_number, pattern_name, match, line) tuples
    """
    findings = []

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    lines = content.split("\n")

    for line_num, line in enumerate(lines, start=1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith(("#", "//")):
            continue

        for pattern, pattern_name in SECRET_PATTERNS:
            matches = re.findall(pattern, line, re.IGNORECASE)
            for match in matches:
                if not is_allowed_match(line, match if isinstance(match, str) else str(match)):
                    findings.append((line_num, pattern_name, str(match)[:50], line[:100]))

    return findings


# =============================================================================
# PROPERTY TESTS
# =============================================================================


class TestNoHardcodedSecrets:
    """
    Property 1: No Hardcoded Secrets

    Scan all files in deploy/** for API key patterns.

    **Validates: Requirements 8.1**
    """

    def test_no_aws_access_keys(self) -> None:
        """No AWS access key IDs should be hardcoded."""
        pattern = r"AKIA[0-9A-Z]{16}"

        for file_path in get_deploy_files():
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            matches = re.findall(pattern, content)
            for match in matches:
                # Check if it's in a comment or allowed context
                for line in content.split("\n"):
                    if match in line and not is_allowed_match(line, match):
                        pytest.fail(f"Potential AWS Access Key ID found in {file_path}: {match}")

    def test_no_openai_keys(self) -> None:
        """No OpenAI API keys should be hardcoded."""
        patterns = [
            r"sk-[a-zA-Z0-9]{48}",
            r"sk-proj-[a-zA-Z0-9_-]{48,}",
        ]

        for file_path in get_deploy_files():
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for pattern in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    for line in content.split("\n"):
                        if match in line and not is_allowed_match(line, match):
                            pytest.fail(
                                f"Potential OpenAI API key found in {file_path}: {match[:20]}..."
                            )

    def test_no_anthropic_keys(self) -> None:
        """No Anthropic API keys should be hardcoded."""
        pattern = r"sk-ant-[a-zA-Z0-9_-]{40,}"

        for file_path in get_deploy_files():
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            matches = re.findall(pattern, content)
            for match in matches:
                for line in content.split("\n"):
                    if match in line and not is_allowed_match(line, match):
                        pytest.fail(
                            f"Potential Anthropic API key found in {file_path}: {match[:20]}..."
                        )

    def test_no_private_keys(self) -> None:
        """No private keys should be hardcoded."""
        pattern = r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"

        for file_path in get_deploy_files():
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if re.search(pattern, content):
                pytest.fail(f"Private key found in {file_path}")

    def test_no_connection_strings(self) -> None:
        """No database/storage connection strings with credentials should be hardcoded."""
        patterns = [
            r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[^;]+",
            r"mongodb(\+srv)?://[^:]+:[^@]+@",
            r"postgres://[^:]+:[^@]+@",
            r"mysql://[^:]+:[^@]+@",
        ]

        for file_path in get_deploy_files():
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for pattern in patterns:
                if re.search(pattern, content):
                    # Check if it's in a comment or example
                    for line in content.split("\n"):
                        if re.search(pattern, line) and not is_allowed_match(line, ""):
                            pytest.fail(f"Connection string with credentials found in {file_path}")

    def test_no_hardcoded_passwords(self) -> None:
        """No hardcoded passwords should be present."""
        pattern = r"password\s*[=:]\s*['\"][^'\"]{8,}['\"]"

        for file_path in get_deploy_files():
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for line in content.split("\n"):
                if re.search(pattern, line, re.IGNORECASE):
                    if not is_allowed_match(line, ""):
                        pytest.fail(f"Hardcoded password found in {file_path}: {line[:50]}...")

    def test_comprehensive_secret_scan(self) -> None:
        """
        Comprehensive scan of all deploy files for any secret patterns.

        This is the main property test that validates no secrets are hardcoded.
        """
        all_findings: list[tuple[Path, int, str, str]] = []

        for file_path in get_deploy_files():
            findings = scan_file_for_secrets(file_path)
            for line_num, pattern_name, match, _line in findings:
                all_findings.append((file_path, line_num, pattern_name, match))

        if all_findings:
            report = "\n".join(
                f"  {path}:{line_num} - {pattern}: {match}"
                for path, line_num, pattern, match in all_findings[:10]
            )
            if len(all_findings) > 10:
                report += f"\n  ... and {len(all_findings) - 10} more"

            pytest.fail(f"Potential hardcoded secrets found:\n{report}")


class TestSecretPatternCoverage:
    """Tests to ensure our secret detection patterns are working."""

    def test_aws_key_pattern_matches(self) -> None:
        """AWS key pattern should match valid AWS access key IDs."""
        pattern = r"AKIA[0-9A-Z]{16}"

        # Should match
        assert re.search(pattern, "AKIAIOSFODNN7EXAMPLE")
        assert re.search(pattern, "AKIAI44QH8DHBEXAMPLE")

        # Should not match
        assert not re.search(pattern, "AKIA123")  # Too short
        assert not re.search(pattern, "BKIAIOSFODNN7EXAMPLE")  # Wrong prefix

    def test_openai_key_pattern_matches(self) -> None:
        """OpenAI key pattern should match valid OpenAI API keys."""
        pattern = r"sk-[a-zA-Z0-9]{48}"

        # Should match (fake key for testing)
        fake_key = "sk-" + "a" * 48
        assert re.search(pattern, fake_key)

        # Should not match
        assert not re.search(pattern, "sk-short")

    def test_private_key_pattern_matches(self) -> None:
        """Private key pattern should match PEM headers."""
        pattern = r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"

        assert re.search(pattern, "-----BEGIN PRIVATE KEY-----")
        assert re.search(pattern, "-----BEGIN RSA PRIVATE KEY-----")
        assert re.search(pattern, "-----BEGIN EC PRIVATE KEY-----")
        assert re.search(pattern, "-----BEGIN OPENSSH PRIVATE KEY-----")

        # Should not match
        assert not re.search(pattern, "-----BEGIN PUBLIC KEY-----")


class TestAllowedPatterns:
    """Tests for allowed pattern detection (false positive filtering)."""

    def test_environment_variable_references_allowed(self) -> None:
        """Environment variable references should be allowed."""
        assert is_allowed_match("api_key = $API_KEY", "$API_KEY")
        assert is_allowed_match("api_key = ${API_KEY}", "${API_KEY}")
        assert is_allowed_match("os.environ.get('API_KEY')", "os.environ")

    def test_example_values_allowed(self) -> None:
        """Example/placeholder values should be allowed."""
        assert is_allowed_match("api_key = 'your-api-key-here'", "your-api-key")
        assert is_allowed_match("api_key = '<YOUR_API_KEY>'", "<YOUR_API_KEY>")
        assert is_allowed_match("api_key = 'example-key'", "example")

    def test_regex_patterns_in_docs_allowed(self) -> None:
        """Regex patterns in documentation should be allowed."""
        assert is_allowed_match("Pattern: AKIA[0-9A-Z]{16}", "AKIA[0-9A-Z]")
        assert is_allowed_match("Pattern: sk-[a-zA-Z0-9]{48}", "sk-[a-zA-Z0-9]")
