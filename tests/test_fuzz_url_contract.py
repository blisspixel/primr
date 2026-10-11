"""Deterministic URL-parser seeds and negative controls for its fuzz oracle."""

from pathlib import Path

import pytest

from primr.utils.validators import InputValidationError, validate_url
from tests.fuzz import url_fuzzer

CORPUS = Path(__file__).parent / "fuzz" / "corpus" / "url"
VALID_SEEDS = {"https", "ipv6", "mixed-case", "unicode-host"}
SEEDS = sorted(path.name for path in CORPUS.iterdir())


@pytest.mark.parametrize("name", SEEDS)
def test_url_regression_seed(name: str) -> None:
    data = (CORPUS / name).read_bytes()
    text = data.decode("utf-8", errors="surrogateescape")
    if name in VALID_SEEDS:
        assert validate_url(text) == text.strip()
    else:
        with pytest.raises(InputValidationError):
            validate_url(text)
    url_fuzzer.fuzz_one_input(data)


def test_empty_and_non_utf8_inputs_reach_parser() -> None:
    url_fuzzer.fuzz_one_input(b"")
    url_fuzzer.fuzz_one_input(b"https://acme.example/\xff\x00")


@pytest.mark.parametrize(
    ("text", "error", "message"),
    [
        ("file://acme.example", AssertionError, "unsupported scheme"),
        ("https:///path", AssertionError, "missing authority"),
        ("https://:443", AssertionError, "missing hostname"),
        ("https://user:password@acme.example", AssertionError, "username"),
        ("https://acme.example:65536", ValueError, "Port out of range"),
        ("https://acme.example:invalid", ValueError, "Port could not be cast"),
    ],
)
def test_oracle_detects_permissive_validator(monkeypatch, text, error, message) -> None:
    # These controls fail the real oracle if the validator starts accepting
    # malformed inputs. They do not substitute for running the actual engine.
    monkeypatch.setattr(url_fuzzer, "validate_url", lambda value: value)
    with pytest.raises(error, match=message):
        url_fuzzer.assert_url_contract(text)


def test_network_guard_rejects_dns_and_connections() -> None:
    for event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname"):
        with pytest.raises(url_fuzzer.NetworkAccessAttempt, match="network access"):
            url_fuzzer.forbid_network(event, ())
    url_fuzzer.forbid_network("open", ())


def test_network_attempt_escapes_parser_exception_handling(monkeypatch) -> None:
    def catches_parser_errors(_text: str) -> str:
        try:
            url_fuzzer.forbid_network("socket.getaddrinfo", ())
        except Exception as error:
            raise InputValidationError("url", str(error)) from error
        return "https://acme.example"

    monkeypatch.setattr(url_fuzzer, "validate_url", catches_parser_errors)
    with pytest.raises(url_fuzzer.NetworkAccessAttempt, match="network access"):
        url_fuzzer.assert_url_contract("https://acme.example")
