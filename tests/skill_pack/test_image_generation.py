from __future__ import annotations

from unittest.mock import patch

import pytest

from primr.skill_pack.image_generation import (
    MAX_PROVIDER_IMAGE_BYTES,
    _fetch_provider_image_url,
    generate_icons,
)


def test_fetch_provider_image_url_blocks_unsafe_initial_url() -> None:
    with (
        patch(
            "primr.utils.security.is_safe_url",
            return_value=(False, "Private/reserved IP addresses are blocked"),
        ),
        pytest.raises(RuntimeError, match="unsafe URL"),
    ):
        _fetch_provider_image_url("http://169.254.169.254/latest/meta-data")


def test_fetch_provider_image_url_uses_guarded_fetch_for_redirects() -> None:
    with (
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.data.safe_http.safe_http_get",
            return_value=(None, None, None),
        ) as guarded_get,
        pytest.raises(RuntimeError, match="blocked or unreachable"),
    ):
        _fetch_provider_image_url("https://cdn.example/generated.png")

    guarded_get.assert_called_once_with(
        "https://cdn.example/generated.png",
        timeout=120.0,
        log_prefix="skill-pack-image",
    )


def test_fetch_provider_image_url_returns_checked_bytes() -> None:
    with (
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.data.safe_http.safe_http_get",
            return_value=(200, b"png-bytes", "https://cdn.example/generated.png"),
        ),
    ):
        assert _fetch_provider_image_url("https://cdn.example/generated.png") == b"png-bytes"


def test_fetch_provider_image_url_rejects_oversized_response() -> None:
    with (
        patch("primr.skill_pack.image_generation.MAX_PROVIDER_IMAGE_BYTES", 31),
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.data.safe_http.safe_http_get",
            return_value=(200, b"x" * 32, "https://cdn.example/generated.png"),
        ),
        pytest.raises(RuntimeError, match="exceeded"),
    ):
        _fetch_provider_image_url("https://cdn.example/generated.png")


def test_fetch_provider_image_url_rejects_http_errors() -> None:
    with (
        patch("primr.utils.security.is_safe_url", return_value=(True, None)),
        patch(
            "primr.data.safe_http.safe_http_get",
            return_value=(503, b"unavailable", "https://cdn.example/generated.png"),
        ),
        pytest.raises(RuntimeError, match="HTTP 503"),
    ):
        _fetch_provider_image_url("https://cdn.example/generated.png")


def test_max_provider_image_bytes_is_bounded() -> None:
    assert MAX_PROVIDER_IMAGE_BYTES <= 5 * 1024 * 1024


def test_generate_icons_default_ignores_available_xai_key(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-key")

    with patch(
        "primr.skill_pack.image_generation.GrokImageProvider.generate",
        side_effect=AssertionError("remote image provider must not run"),
    ):
        color, outline = generate_icons("Acme Corp")

    assert color.startswith(b"\x89PNG")
    assert outline.startswith(b"\x89PNG")
