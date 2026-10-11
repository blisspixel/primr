"""Coverage-guided fuzz target for the CLI's non-network URL parser."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from primr.utils.validators import InputValidationError, validate_url


class NetworkAccessAttempt(BaseException):
    """Escape broad parser exception handlers when the audit hook fires."""


def assert_url_contract(text: str) -> None:
    """Accept documented validation errors; check every accepted URL."""
    try:
        validated = validate_url(text)
    except InputValidationError:
        return

    assert validated == text.strip(), "Validation changed URL content"
    parsed = urlparse(validated)
    assert parsed.scheme in {"http", "https"}, "Accepted unsupported scheme"
    assert parsed.netloc, "Accepted missing authority"
    assert parsed.hostname, "Accepted missing hostname"
    assert parsed.username is None, "Accepted username"
    assert parsed.password is None, "Accepted password"
    # urllib checks invalid/range-exceeding ports lazily. A validator that
    # forgets this check must fail here rather than defer failure to HTTP.
    port = parsed.port
    assert port is None or 0 <= port <= 65535, "Accepted invalid port"
    assert validate_url(validated) == validated, "Validation is not idempotent"


def fuzz_one_input(data: bytes) -> None:
    """Exercise raw and authority-shaped inputs, including invalid UTF-8."""
    text = data.decode("utf-8", errors="surrogateescape")
    assert_url_contract(text)
    # Preserve arbitrary input while also reaching authority/port parsing
    # without requiring mutations to rediscover the scheme on every input.
    assert_url_contract("https://" + text)


def forbid_network(event: str, _args: tuple[object, ...]) -> None:
    """Keep a future parser regression from making network requests."""
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname"}:
        raise NetworkAccessAttempt(f"URL parsing attempted network access: {event}")


def main() -> None:
    # Atheris is a CI-only tool, so ordinary regression tests need no native
    # fuzz-engine dependency. Instrument the actual production validator and
    # both harness functions, keeping unrelated package imports out of coverage.
    import atheris

    atheris.instrument_func(validate_url)
    atheris.instrument_func(assert_url_contract)
    atheris.instrument_func(fuzz_one_input)
    sys.addaudithook(forbid_network)
    atheris.Setup(sys.argv, fuzz_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
