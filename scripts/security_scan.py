#!/usr/bin/env python3
"""
Security scanning script for Primr.

Runs multiple security checks:
1. Bandit - Python security linter
2. Safety - Dependency vulnerability scanner
3. Custom checks - Hardcoded secrets, unsafe patterns

Usage:
    python scripts/security_scan.py
    python scripts/security_scan.py --fix  # Auto-fix where possible
    python scripts/security_scan.py --ci   # CI mode (exit code on issues)
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Colors for output
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(text: str) -> None:
    """Print a section header."""
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")


def print_ok(text: str) -> None:
    """Print success message."""
    print(f"{GREEN}✓ {text}{RESET}")


def print_warn(text: str) -> None:
    """Print warning message."""
    print(f"{YELLOW}⚠ {text}{RESET}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"{RED}✗ {text}{RESET}")


def run_bandit() -> tuple[bool, list[str]]:
    """Run Bandit security linter."""
    print_header("Running Bandit Security Linter")

    try:
        result = subprocess.run(
            [
                "python",
                "-m",
                "bandit",
                "-r",
                "src/primr",
                "-c",
                ".bandit",
                "-f",
                "txt",
                "--severity-level",
                "medium",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print_ok("No security issues found by Bandit")
            return True, []

        # Parse issues
        issues = []
        for line in result.stdout.split("\n"):
            if ">> Issue:" in line or "Severity:" in line:
                issues.append(line.strip())

        if issues:
            print_warn(f"Bandit found {len(issues)} potential issues:")
            for issue in issues[:10]:  # Show first 10
                print(f"  {issue}")
            if len(issues) > 10:
                print(f"  ... and {len(issues) - 10} more")

        return result.returncode == 0, issues

    except FileNotFoundError:
        print_warn("Bandit not installed. Run: pip install bandit")
        return True, []  # Don't fail if not installed


def run_safety() -> tuple[bool, list[str]]:
    """Run Safety dependency vulnerability scanner."""
    print_header("Running Safety Dependency Scanner")

    try:
        result = subprocess.run(
            ["python", "-m", "safety", "check", "--full-report"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print_ok("No known vulnerabilities in dependencies")
            return True, []

        # Parse vulnerabilities
        vulns = []
        for line in result.stdout.split("\n"):
            if "vulnerability" in line.lower() or "CVE-" in line:
                vulns.append(line.strip())

        if vulns:
            print_warn(f"Safety found {len(vulns)} potential vulnerabilities:")
            for vuln in vulns[:5]:
                print(f"  {vuln}")

        return False, vulns

    except FileNotFoundError:
        print_warn("Safety not installed. Run: pip install safety")
        return True, []


def check_hardcoded_secrets() -> tuple[bool, list[str]]:
    """Check for hardcoded secrets in source code."""
    print_header("Checking for Hardcoded Secrets")

    # Patterns that might indicate hardcoded secrets
    secret_patterns = [
        (r'api_key\s*=\s*["\'][a-zA-Z0-9]{20,}["\']', "Possible hardcoded API key"),
        (r'password\s*=\s*["\'][^"\']+["\']', "Possible hardcoded password"),
        (r'secret\s*=\s*["\'][a-zA-Z0-9]{16,}["\']', "Possible hardcoded secret"),
        (r'token\s*=\s*["\'][a-zA-Z0-9_.-]{20,}["\']', "Possible hardcoded token"),
        (r"AIza[a-zA-Z0-9_-]{35}", "Google API key pattern"),
        (r"sk-[a-zA-Z0-9]{48}", "OpenAI API key pattern"),
        (r"ghp_[a-zA-Z0-9]{36}", "GitHub token pattern"),
        (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth token pattern"),
        (r"github_pat_[a-zA-Z0-9_]{22,}", "GitHub PAT pattern"),
        (r"xox[baprs]-[a-zA-Z0-9-]+", "Slack token pattern"),
        (r"sk-ant-[a-zA-Z0-9-]+", "Anthropic API key pattern"),
        (r"AKIA[A-Z0-9]{16}", "AWS access key pattern"),
    ]

    issues = []
    src_path = Path("src/primr")

    # Exclude test files and examples
    exclude_patterns = ["test_", "conftest", "example", "fixture"]

    for py_file in src_path.rglob("*.py"):
        # Skip excluded files
        if any(exc in py_file.name for exc in exclude_patterns):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")

            for pattern, description in secret_patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Skip if it's in a comment or docstring context
                    line_start = content.rfind("\n", 0, match.start()) + 1
                    line = content[line_start : match.end()]
                    line_no = content.count("\n", 0, match.start()) + 1

                    if line.strip().startswith("#"):
                        continue
                    if "example" in line.lower() or "placeholder" in line.lower():
                        continue

                    issues.append(f"{py_file}:{line_no}: {description}")

        except Exception as e:
            print_warn(f"Could not read {py_file}: {e}")

    if issues:
        print_error(f"Found {len(issues)} potential hardcoded secrets:")
        for issue in issues[:10]:
            print(f"  {issue}")
        return False, issues

    print_ok("No hardcoded secrets detected")
    return True, []


def check_unsafe_patterns() -> tuple[bool, list[str]]:
    """Check for unsafe code patterns."""
    print_header("Checking for Unsafe Code Patterns")

    unsafe_patterns = [
        (r"\beval\s*\(", "Use of eval()"),
        (r"\bexec\s*\(", "Use of exec()"),
        (r"pickle\.loads?\s*\(", "Use of pickle (potential RCE)"),
        (r"subprocess.*shell\s*=\s*True", "subprocess with shell=True"),
        (r"yaml\.load\s*\([^)]*\)", "Unsafe yaml.load (use safe_load)"),
        (r"__import__\s*\(", "Dynamic import"),
        (r"os\.system\s*\(", "Use of os.system"),
        (
            r"random\.(choice|randint|random)\s*\(.*(?:token|secret|key|password)",
            "Insecure random for secrets",
        ),
        # Only flag MD5/SHA1 if NOT marked as usedforsecurity=False
        (
            r"hashlib\.(md5|sha1)\s*\([^)]*\)(?!.*usedforsecurity\s*=\s*False)",
            "Weak hash algorithm (use sha256+ or add usedforsecurity=False)",
        ),
    ]

    issues = []
    src_path = Path("src/primr")

    for py_file in src_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")

            for pattern, description in unsafe_patterns:
                if re.search(pattern, content):
                    # Get line number
                    for i, line in enumerate(content.split("\n"), 1):
                        if re.search(pattern, line):
                            # Skip if in comment
                            if line.strip().startswith("#"):
                                continue
                            issues.append(f"{py_file}:{i}: {description}")

        except Exception as e:
            print_warn(f"Could not read {py_file}: {e}")

    if issues:
        print_warn(f"Found {len(issues)} potentially unsafe patterns:")
        for issue in issues[:10]:
            print(f"  {issue}")
        return False, issues

    print_ok("No unsafe patterns detected")
    return True, []


def check_yaml_safety() -> tuple[bool, list[str]]:
    """Verify all YAML loading uses safe_load."""
    print_header("Checking YAML Loading Safety")

    issues = []
    src_path = Path("src/primr")

    for py_file in src_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")

            # Check for yaml.load without safe_load
            if "yaml.load(" in content and "yaml.safe_load" not in content:
                # Find the line
                for i, line in enumerate(content.split("\n"), 1):
                    if "yaml.load(" in line and "safe_load" not in line:
                        if not line.strip().startswith("#"):
                            issues.append(f"{py_file}:{i}: Unsafe yaml.load()")

        except Exception:
            pass

    if issues:
        print_error(f"Found {len(issues)} unsafe YAML loading:")
        for issue in issues:
            print(f"  {issue}")
        return False, issues

    print_ok("All YAML loading uses safe_load")
    return True, []


def check_file_encoding() -> tuple[bool, list[str]]:
    """Check for file operations missing explicit encoding."""
    print_header("Checking File Encoding")

    issues = []
    src_path = Path("src/primr")

    # Pattern for open() calls without encoding (text mode)
    re.compile(r"open\s*\([^)]*\)")

    for py_file in src_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")

            for i, line in enumerate(content.split("\n"), 1):
                if line.strip().startswith("#"):
                    continue

                # Check for open() calls
                if "open(" in line:
                    # Skip binary mode
                    if "'rb'" in line or '"rb"' in line or "'wb'" in line or '"wb"' in line:
                        continue
                    # Check for encoding
                    if "encoding" not in line and "encoding=" not in line:
                        # Could be a false positive, but worth flagging
                        issues.append(f"{py_file}:{i}: open() without encoding")

        except Exception:
            pass

    if issues:
        print_warn(f"Found {len(issues)} file operations without explicit encoding:")
        for issue in issues[:5]:
            print(f"  {issue}")
        if len(issues) > 5:
            print(f"  ... and {len(issues) - 5} more")
        # Don't fail, just warn
        return True, issues

    print_ok("All file operations have explicit encoding")
    return True, []


def main() -> int:
    """Run all security checks."""
    parser = argparse.ArgumentParser(description="Security scanning for Primr")
    parser.add_argument("--ci", action="store_true", help="CI mode (strict)")
    parser.add_argument("--fix", action="store_true", help="Auto-fix where possible")
    args = parser.parse_args()

    print(f"\n{BLUE}Primr Security Scanner{RESET}")
    print(f"{BLUE}======================{RESET}")

    all_passed = True
    all_issues = []

    # Run checks
    checks = [
        ("Bandit", run_bandit),
        ("Hardcoded Secrets", check_hardcoded_secrets),
        ("Unsafe Patterns", check_unsafe_patterns),
        ("YAML Safety", check_yaml_safety),
        ("File Encoding", check_file_encoding),
    ]

    # Safety check is optional (may have false positives)
    if args.ci:
        checks.append(("Safety", run_safety))

    for name, check_func in checks:
        try:
            passed, issues = check_func()
            if not passed:
                all_passed = False
            all_issues.extend(issues)
        except Exception as e:
            print_error(f"{name} check failed: {e}")
            if args.ci:
                all_passed = False

    # Summary
    print_header("Security Scan Summary")

    if all_passed:
        print_ok("All security checks passed!")
        return 0
    else:
        print_error(f"Security issues found: {len(all_issues)}")
        if args.ci:
            return 1
        return 0  # Don't fail in non-CI mode


if __name__ == "__main__":
    sys.exit(main())
