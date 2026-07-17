"""Regression tests for the standalone security scan command."""

from __future__ import annotations

import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from scripts import security_scan

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "security_scan.py"


def test_status_output_is_cp1252_safe() -> None:
    captured_bytes = io.BytesIO()
    captured_text = io.TextIOWrapper(captured_bytes, encoding="cp1252", write_through=True)

    with redirect_stdout(captured_text):
        security_scan.print_ok("clean")
        security_scan.print_warn("review")
        security_scan.print_error("failed")

    output = captured_bytes.getvalue().decode("cp1252")
    assert "[PASS] clean" in output
    assert "[WARN] review" in output
    assert "[FAIL] failed" in output


def test_help_does_not_advertise_unimplemented_fix_mode() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--fix" not in result.stdout


def test_unsafe_scan_only_flags_executable_calls() -> None:
    source = """
def log_phase(logger):
    logger.info("behavioral eval (with-skill vs baseline)")

def unsafe(user_input):
    return eval(user_input)
"""

    issues = security_scan._unsafe_source_issues(Path("sample.py"), source)

    assert issues == ["sample.py:6: Use of eval()"]


def test_unsafe_scan_honors_nonsecurity_hash_marker() -> None:
    source = """
import hashlib

hashlib.sha1(b"cache-key", usedforsecurity=False)
hashlib.md5(b"credential")
"""

    issues = security_scan._unsafe_source_issues(Path("sample.py"), source)

    assert issues == ["sample.py:5: Weak hash algorithm (use sha256+ or add usedforsecurity=False)"]


def test_encoding_scan_only_flags_builtin_text_open() -> None:
    source = """
from PIL import Image
import os
import urllib.request

open("missing.txt")
open("explicit.txt", "w", encoding="utf-8")
open("binary.bin", "wb")
os.open("descriptor", os.O_RDONLY)
urllib.request.urlopen("https://example.test")
Image.open("image.png")
"""

    issues = security_scan._text_open_issues(Path("sample.py"), source)

    assert issues == ["sample.py:6: open() without encoding"]


def test_dependency_audit_uses_current_interpreter(monkeypatch) -> None:
    commands: list[list[str]] = []

    def succeed(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(security_scan.subprocess, "run", succeed)

    assert security_scan.run_dependency_audit() == (True, [])
    assert commands == [[sys.executable, "-m", "pip_audit"]]
