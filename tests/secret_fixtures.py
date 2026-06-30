"""Synthetic secret-like values assembled safely for tests."""

from __future__ import annotations


def fake_google_api_key() -> str:
    return "AI" + "za" + "SyA1234567890abcdefghijklmnopqrstuv"


def fake_openai_api_key() -> str:
    return "sk-" + ("a" * 48)


def fake_xai_api_key() -> str:
    return "xai-" + "abc123DEF456ghi789JKL012mno345PQR678stu"


def fake_aws_access_key_one() -> str:
    return "AKIA" + "IOSFODNN7EXAMPLE"


def fake_aws_access_key_two() -> str:
    return "AKIA" + "I44QH8DHBEXAMPLE"


def fake_private_key_header(kind: str = "") -> str:
    key_type = f"{kind} " if kind else ""
    return "-----BEGIN " + key_type + "PRIVATE KEY-----"
