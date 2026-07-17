#!/usr/bin/env python3
"""
Security scanning script for Primr.

Runs multiple security checks:
1. Bandit - Python security linter
2. pip-audit - Dependency vulnerability scanner
3. Custom checks - Hardcoded secrets, unsafe patterns

Usage:
    python scripts/security_scan.py
    python scripts/security_scan.py --ci   # CI mode (exit code on issues)
"""

import argparse
import ast
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
    print(f"{GREEN}[PASS] {text}{RESET}")


def print_warn(text: str) -> None:
    """Print warning message."""
    print(f"{YELLOW}[WARN] {text}{RESET}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"{RED}[FAIL] {text}{RESET}")


def run_bandit() -> tuple[bool, list[str]]:
    """Run Bandit security linter."""
    print_header("Running Bandit Security Linter")

    try:
        result = subprocess.run(
            [
                sys.executable,
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


def run_dependency_audit() -> tuple[bool, list[str]]:
    """Run the repository's canonical pip-audit dependency gate."""
    print_header("Running pip-audit Dependency Scanner")
    result = subprocess.run(
        [sys.executable, "-m", "pip_audit"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print_ok("No known vulnerabilities in dependencies")
        return True, []

    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    findings = [line.strip() for line in output.splitlines() if line.strip()]
    if findings:
        print_error(f"pip-audit failed with {len(findings)} output line(s):")
        for finding in findings[:5]:
            print(f"  {finding}")
    else:
        print_error("pip-audit failed without diagnostic output")
    return False, findings


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
        for index, _issue in enumerate(issues[:10], start=1):
            print(f"  finding {index}")
        return False, issues

    print_ok("No hardcoded secrets detected")
    return True, []


def check_unsafe_patterns() -> tuple[bool, list[str]]:
    """Check for unsafe code patterns."""
    print_header("Checking for Unsafe Code Patterns")

    issues = []
    src_path = Path("src/primr")

    for py_file in src_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            issues.extend(_unsafe_source_issues(py_file, content))

        except Exception as e:
            print_warn(f"Could not read {py_file}: {e}")

    if issues:
        print_warn(f"Found {len(issues)} potentially unsafe patterns:")
        for issue in issues[:10]:
            print(f"  {issue}")
        return False, issues

    print_ok("No unsafe patterns detected")
    return True, []


def _unsafe_source_issues(path: Path, source: str) -> list[str]:
    """Return unsafe executable calls without matching comments or strings."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        line = exc.lineno or 1
        return [f"{path}:{line}: Python source could not be parsed"]

    issues: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        description = _unsafe_call_description(node)
        if description is not None:
            issues.append(f"{path}:{node.lineno}: {description}")
    return issues


def _unsafe_call_description(call: ast.Call) -> str | None:
    """Classify a security-sensitive call, if present."""
    name = _qualified_name(call.func)
    direct_checks = {
        "eval": "Use of eval()",
        "builtins.eval": "Use of eval()",
        "exec": "Use of exec()",
        "builtins.exec": "Use of exec()",
        "pickle.load": "Use of pickle (potential RCE)",
        "pickle.loads": "Use of pickle (potential RCE)",
        "yaml.load": "Unsafe yaml.load (use safe_load)",
        "__import__": "Dynamic import",
        "builtins.__import__": "Dynamic import",
        "os.system": "Use of os.system",
    }
    if name in direct_checks:
        return direct_checks[name]

    if name.startswith("subprocess.") and _literal_keyword(call, "shell") is True:
        return "subprocess with shell=True"

    if name in {"hashlib.md5", "hashlib.sha1"}:
        if _literal_keyword(call, "usedforsecurity") is not False:
            return "Weak hash algorithm (use sha256+ or add usedforsecurity=False)"

    if name in {"random.choice", "random.randint", "random.random"}:
        argument_text = ast.dump(ast.Tuple(elts=[*call.args, *[kw.value for kw in call.keywords]]))
        if re.search(r"token|secret|key|password", argument_text, re.IGNORECASE):
            return "Insecure random for secrets"
    return None


def _qualified_name(node: ast.expr) -> str:
    """Return a dotted name for a simple call target."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _literal_keyword(call: ast.Call, name: str) -> object:
    """Return a keyword's literal value, or a unique non-literal sentinel."""
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    return _NON_LITERAL


_NON_LITERAL = object()


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

        except (OSError, UnicodeError) as exc:
            issues.append(f"{py_file}: Could not inspect YAML usage ({type(exc).__name__})")

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

    for py_file in src_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            issues.extend(_text_open_issues(py_file, content))

        except (OSError, UnicodeError) as exc:
            issues.append(f"{py_file}: Could not inspect file encoding ({type(exc).__name__})")

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


def _text_open_issues(path: Path, source: str) -> list[str]:
    """Find built-in text-mode ``open`` calls without an explicit encoding."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        line = exc.lineno or 1
        return [f"{path}:{line}: Python source could not be parsed"]

    issues: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _qualified_name(node.func) != "open":
            continue
        mode = _open_mode(node)
        if "b" in mode or any(keyword.arg == "encoding" for keyword in node.keywords):
            continue
        issues.append(f"{path}:{node.lineno}: open() without encoding")
    return issues


def _open_mode(call: ast.Call) -> str:
    """Return the literal open mode, defaulting conservatively to text read."""
    mode_node: ast.expr | None = call.args[1] if len(call.args) > 1 else None
    for keyword in call.keywords:
        if keyword.arg == "mode":
            mode_node = keyword.value
            break
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return mode_node.value
    return "r"


def main() -> int:
    """Run all security checks."""
    parser = argparse.ArgumentParser(description="Security scanning for Primr")
    parser.add_argument("--ci", action="store_true", help="CI mode (strict)")
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

    # CI mode includes the same dependency audit used by the workflow gate.
    if args.ci:
        checks.append(("pip-audit", run_dependency_audit))

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
