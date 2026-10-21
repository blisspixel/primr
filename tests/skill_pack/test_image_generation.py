from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.skill_pack.image_generation import (
    MAX_PROVIDER_IMAGE_BYTES,
    GeminiImageProvider,
    ImageRequest,
    _fetch_provider_image_url,
    _resize_to,
    generate_icons,
)


@pytest.mark.parametrize("override", [None, "gemini-3-pro-image"])
def test_gemini_image_uses_supported_default_or_explicit_model(monkeypatch, override):
    from PIL import Image

    monkeypatch.delenv("AI_IMAGE_MODEL", raising=False)
    if override:
        monkeypatch.setenv("AI_IMAGE_MODEL", override)
    from google.genai import types

    image = Image.new("RGB", (4, 4), "navy")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        parts=[types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")]
    )
    with patch("primr.ai.llm._get_client", return_value=client):
        rendered = GeminiImageProvider().generate(ImageRequest("ExampleCo", "Simple icon", 32, 32))
    assert rendered.startswith(b"\x89PNG")
    assert client.models.generate_content.call_args.kwargs["model"] == (
        override or "gemini-nano-banana-2.1"
    )


@pytest.mark.parametrize(
    "override",
    ["gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview", "gemini-3-flash-preview"],
)
def test_gemini_image_rejects_retired_unknown_or_nonimage_route_before_sdk(monkeypatch, override):
    monkeypatch.setenv("AI_IMAGE_MODEL", override)
    with patch("primr.ai.llm._get_client") as client_factory, pytest.raises(ValueError):
        GeminiImageProvider().generate(ImageRequest("ExampleCo", "Simple icon", 32, 32))
    client_factory.assert_not_called()


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
        max_body_bytes=MAX_PROVIDER_IMAGE_BYTES,
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


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_resize_provider_image_preserves_supported_images(image_format):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "navy").save(buf, format=image_format)
    output = _resize_to(buf.getvalue(), 32, 32)
    with Image.open(io.BytesIO(output)) as result:
        assert (result.format, result.size, result.mode) == ("PNG", (32, 32), "RGB")


@pytest.mark.parametrize("image_format", ["TIFF", "GIF", "BMP", "WEBP"])
def test_resize_rejects_unrequested_decoders(image_format):
    from PIL import Image, UnidentifiedImageError

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "navy").save(buf, format=image_format)
    with pytest.raises(UnidentifiedImageError):
        _resize_to(buf.getvalue(), 32, 32)


def test_resize_rejects_corrupt_and_oversized_images(monkeypatch):
    from PIL import Image, UnidentifiedImageError

    with pytest.raises(UnidentifiedImageError):
        _resize_to(b"invalid image", 32, 32)
    monkeypatch.setattr("primr.skill_pack.image_generation.MAX_PROVIDER_IMAGE_BYTES", 8)
    with pytest.raises(ValueError, match="byte limit"):
        _resize_to(b"x" * 9, 32, 32)
    monkeypatch.setattr("primr.skill_pack.image_generation.MAX_PROVIDER_IMAGE_BYTES", 1024)
    monkeypatch.setattr("primr.skill_pack.image_generation.MAX_PROVIDER_IMAGE_PIXELS", 32)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "navy").save(buf, format="PNG")
    with pytest.raises(ValueError, match="pixel limit"):
        _resize_to(buf.getvalue(), 4, 4)


def test_resize_rejects_decompression_warning(monkeypatch):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "navy").save(buf, format="PNG")
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 32)
    with pytest.raises(Image.DecompressionBombWarning):
        _resize_to(buf.getvalue(), 4, 4)


def test_bad_remote_image_falls_back_to_valid_local_icons(monkeypatch):
    from PIL import Image

    monkeypatch.setenv("XAI_API_KEY", "fake-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with patch(
        "primr.skill_pack.image_generation.GrokImageProvider.generate",
        side_effect=lambda request: _resize_to(b"corrupt", request.width, request.height),
    ):
        color, outline = generate_icons("Acme", disable_remote=False)
    for raw, expected in [(color, (192, 192)), (outline, (32, 32))]:
        with Image.open(io.BytesIO(raw)) as icon:
            assert icon.format == "PNG"
            assert icon.size == expected
