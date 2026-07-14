"""Recognize high-signal executable fragments in non-Python source syntax."""

from __future__ import annotations

import re

_RUBY_VARIABLE_ARGUMENT = r"[A-Z_][A-Z0-9_]*(?:\[[^\]\r\n]{1,100}\])?(?=\s*(?:[,;)}\]]|$))"
_RUBY_ARGUMENT = (
    r"(?:\(|[\[({\"']|%(?:i|I|q|Q|w|W|x)\s*[^A-Za-z0-9\s]|"
    r"q(?:q|w|x)?\s*[^A-Za-z0-9\s]|[$@]|" + _RUBY_VARIABLE_ARGUMENT + r")"
)
_RUBY_EXECUTION_METHOD = r"(?:exec|popen|readpipe|spawn|system)"
_RUBY_REFLECTIVE_TARGET = (
    rf"(?::{_RUBY_EXECUTION_METHOD}\b|:[\"']{_RUBY_EXECUTION_METHOD}[\"']|"
    rf"[\"']{_RUBY_EXECUTION_METHOD}[\"'])"
)
_RUBY_REFLECTIVE_VECTOR = rf"%(?:i|I)\s*[^A-Za-z0-9\s]\s*{_RUBY_EXECUTION_METHOD}\b"
_RUBY_REFLECTIVE_VALUE = rf"(?:{_RUBY_REFLECTIVE_TARGET}|{_RUBY_REFLECTIVE_VECTOR})"
_RUBY_REFLECTIVE_ARGUMENT = (
    rf"(?:\(\s*\*?\s*{_RUBY_REFLECTIVE_VALUE}|\s+\*?\s*{_RUBY_REFLECTIVE_VALUE})"
)
_RUBY_RECEIVER_CALL = (
    r"\b(?:io\s*(?:\.|&\.|::)\s*popen|"
    r"kernel\s*(?:\.|&\.|::)\s*(?:exec|spawn|system)|"
    r"process\s*(?:\.|&\.|::)\s*(?:exec|spawn)|"
    r"open3\s*(?:\.|&\.|::)\s*(?:capture2e?|capture3|popen2e?|popen3|"
    r"pipeline(?:_r|_rw|_start|_w)?)|core\s*::\s*(?:exec|readpipe|system))"
    r"\b\s*\*?\s*" + _RUBY_ARGUMENT
)
_RUBY_BARE_CALL = (
    r"(?:^|[\n;{}?:=,(\[!]|&&|\|\||"
    r"\b(?:and|do|or|print|puts|return|then)\b)\s*"
    r"(?:exec|readpipe|spawn|system)\s*\*?\s*" + _RUBY_ARGUMENT
)
_RUBY_REFLECTIVE_CALL = (
    r"\b(?:io|kernel|object|open3|process|self)\s*(?:\.|&\.|::)\s*"
    r"(?:__send__|public_send|send)\s*"
    + _RUBY_REFLECTIVE_ARGUMENT
    + r"|\b(?:__send__|public_send|send)\s*"
    + _RUBY_REFLECTIVE_ARGUMENT
    + r"|\b(?:method|public_method)\s*"
    + _RUBY_REFLECTIVE_ARGUMENT
)
_HIGH_RISK_RE = re.compile(
    r"(?:\b__import__\s*\(|\b(?:eval|exec|compile)\s*\(|\beval\s*\?\.\s*\(|"
    + _RUBY_RECEIVER_CALL
    + r"|"
    + _RUBY_BARE_CALL
    + r"|"
    + _RUBY_REFLECTIVE_CALL
    + r"|"
    r"\b(?:os|subprocess|asyncio|socket|pathlib|shutil|requests|httpx|urllib)"
    r"\s*\.\s*(?:system|popen|exec\w*|spawn\w*|getenv|open_connection|"
    r"create_subprocess\w*|run|popen|call|check_call|check_output|write_text|"
    r"write_bytes|unlink|remove|rename|replace|rmtree|connect|post|put|request|"
    r"urlopen)\s*\(|\breadpipe\s*(?:\(|[\"'])|"
    r"\bloadstring\s*(?:\(|[\"'])|(?:%x|\bqx)\s*[^A-Za-z0-9\s])",
    re.IGNORECASE,
)
_NON_PYTHON_RE = re.compile(
    r"(?:^|\n)\s*(?:(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=|"
    r"\$[A-Za-z_]\w*\s*=|(?:export\s+)?[A-Za-z_]\w*=)|"
    r"\brequire\s*\(|\$env:[A-Za-z_]\w*|\bimport\s*\(|"
    r"\bnew\s+[A-Z_$][\w$]*(?:\.[A-Z_$][\w$]*)*\s*\(|"
    r"(?:\basync\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*"
    r"(?:\{|[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+(?:\s*\(|\b)|"
    r"[A-Za-z_$][\w$]*\s*\()|"
    r"\b(?:async\s+)?function(?:\s+[A-Za-z_$][\w$]*)?\s*\([^)]*\)\s*\{|"
    r"\bclass\s+[A-Za-z_$][\w$]*(?:\s+extends\s+[A-Za-z_$][\w$]*)?\s*\{|"
    r"\bif\s*\([^)]*\)\s*(?:\{|fetch\b)|\b[A-Za-z_$][\w$]*\s*\?\.\s*\(|"
    r"(?:^|\n)\s*(?:system|os\.execute)\s+[\"']"
)
_POWERSHELL_RE = re.compile(
    r"(?:^|\n)\s*(?:Get-Content|Set-Content|Invoke-Expression|Start-Process|"
    r"Invoke-WebRequest)\b|\$env:[A-Za-z_]\w*|\bIEX\b\s*(?:\(|[\"'$])",
    re.IGNORECASE,
)
_ISOLATED_RE = re.compile(
    r"(?:^|\n)\s*(?:puts\s+[\"']|require\s+[\"']|File\.write\s+[\"']|"
    r"new\s+[a-z_$][\w$]*\(|@?echo\s+off\b|FOR\s+%[A-Za-z]\s+IN\s*\([^\r\n]*\)"
    r"\s+DO\b|%COMSPEC%\s+/(?:c|k)\b)|"
    r"(?:^|\n)\s*for\s+[A-Za-z_]\w*\s+in\s+[^\r\n]+\r?\n\s*do\b"
    r"[\s\S]{0,4096}?\r?\n\s*done\b",
    re.IGNORECASE,
)


def contains_non_python_executable_fragment(text: str) -> bool:
    """Return whether text contains a high-signal active code fragment."""
    return bool(
        _HIGH_RISK_RE.search(text) or _NON_PYTHON_RE.search(text) or _POWERSHELL_RE.search(text)
    )


def find_non_python_executable_fragment(text: str) -> str | None:
    """Return the first active non-Python fragment, if one is present."""
    for pattern in (_HIGH_RISK_RE, _NON_PYTHON_RE, _POWERSHELL_RE, _ISOLATED_RE):
        if match := pattern.search(text):
            return match.group(0)
    return None


__all__ = ["contains_non_python_executable_fragment", "find_non_python_executable_fragment"]
