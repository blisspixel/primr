from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.skill_pack.image_generation import (
    MAX_PROVIDER_IMAGE_BYTES,
    _fetch_provider_image_url,
)


def _response(url: str, content: bytes = b"png") -> MagicMock:
    response = MagicMock()
    response.url = url
    response.content = content
    response.raise_for_status = MagicMock()
    return response


def _client_for(response: MagicMock) -> MagicMock:
    client = MagicMock()
    client.get.return_value = response
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    return client


def test_fetch_provider_image_url_blocks_unsafe_initial_url() -> None:
    with (
        patch(
            "primr.utils.security.is_safe_url",
            return_value=(False, "Private/reserved IP addresses are blocked"),
        ),
        pytest.raises(RuntimeError, match="unsafe URL"),
    ):
        _fetch_provider_image_url("http://169.254.169.254/latest/meta-data")


def test_fetch_provider_image_url_validates_final_redirect() -> None:
    client = _client_for(_response("http://169.254.169.254/latest/meta-data"))

    with (
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.utils.security.validate_final_url_after_redirect",
            return_value=(False, "Cloud metadata endpoints are blocked"),
        ),
        patch("httpx.Client", return_value=client) as client_ctor,
        pytest.raises(RuntimeError, match="redirected to unsafe"),
    ):
        _fetch_provider_image_url("https://cdn.example/generated.png")

    client_ctor.assert_called_once_with(timeout=120.0, follow_redirects=True)


def test_fetch_provider_image_url_returns_checked_bytes() -> None:
    client = _client_for(_response("https://cdn.example/generated.png", b"png-bytes"))

    with (
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.utils.security.validate_final_url_after_redirect",
            return_value=(True, None),
        ),
        patch("httpx.Client", return_value=client),
    ):
        assert _fetch_provider_image_url("https://cdn.example/generated.png") == b"png-bytes"


def test_fetch_provider_image_url_rejects_oversized_response() -> None:
    client = _client_for(_response("https://cdn.example/generated.png", b"x" * 32))

    with (
        patch("primr.skill_pack.image_generation.MAX_PROVIDER_IMAGE_BYTES", 31),
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.utils.security.validate_final_url_after_redirect",
            return_value=(True, None),
        ),
        patch("httpx.Client", return_value=client),
        pytest.raises(RuntimeError, match="exceeded"),
    ):
        _fetch_provider_image_url("https://cdn.example/generated.png")


def test_max_provider_image_bytes_is_bounded() -> None:
    assert MAX_PROVIDER_IMAGE_BYTES <= 5 * 1024 * 1024
