"""Multi-provider image generation for Cowork plugin icons.

Provider fallback chain (highest quality first):
    1. Grok image generation (xAI)         — uses XAI_API_KEY
    2. Gemini Imagen                       — uses GEMINI_API_KEY
    3. OpenAI image generation (DALL-E)    — uses OPENAI_API_KEY
    4. Programmatic Pillow gradient+shape  — icons.build_color_icon
    5. Solid PNG                           — icons._write_png_solid (final fallback)

Each provider runs behind a try/except so any combination of missing or
flaky providers degrades gracefully. The result is always two PNG byte
strings: a 192x192 color icon and a 32x32 outline icon.

Provider abstraction is intentionally a peer of `primr.ai.providers.Provider`
so adding Microsoft Foundry, AWS Bedrock, Anthropic (when image gen lands),
and others is a localized change — no caller updates needed.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from primr.skill_pack import icons

logger = logging.getLogger(__name__)

MAX_PROVIDER_IMAGE_BYTES = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------


@dataclass
class ImageRequest:
    """A single image-generation request."""

    company_name: str
    style_prompt: str  # e.g. "minimalist brand mark for a fintech startup"
    width: int
    height: int


class ImageGenerationProvider(ABC):
    """A pluggable image-generation backend.

    Each concrete provider should:
      - declare a `name` (used for logging)
      - declare `is_available()` (key-presence check, no network call)
      - implement `generate(request) -> bytes` returning PNG bytes
    """

    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def generate(self, request: ImageRequest) -> bytes: ...


# ---------------------------------------------------------------------------
# Concrete providers
# ---------------------------------------------------------------------------


class GrokImageProvider(ImageGenerationProvider):
    """xAI Grok Imagine image generation.

    API reference: https://docs.x.ai/developers/model-capabilities/imagine

    Endpoint: POST https://api.x.ai/v1/images/generations
    Model:    grok-imagine-image-quality
    Response: {"data": [{"url": "..."} or {"b64_json": "..."}]}

    We default to URL response and fetch the bytes (smaller round trips
    for the JSON envelope; Pillow resize happens client-side either way).
    """

    name = "grok-imagine"

    def is_available(self) -> bool:
        return bool(os.environ.get("XAI_API_KEY"))

    def generate(self, request: ImageRequest) -> bytes:
        import httpx

        api_key = os.environ.get("XAI_API_KEY")
        if not api_key:
            raise RuntimeError("XAI_API_KEY not set")

        prompt = self._build_prompt(request)
        endpoint = "https://api.x.ai/v1/images/generations"
        payload = {
            "model": "grok-imagine-image-quality",
            "prompt": prompt,
        }
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        entries = data.get("data") or []
        if not entries:
            raise RuntimeError(f"Grok Imagine returned no data entries: {data!r}")
        first = entries[0]

        # Prefer base64 when present (avoids a second round trip), else fetch URL.
        b64 = first.get("b64_json") or first.get("base64")
        if b64:
            import base64

            png_bytes = base64.b64decode(b64)
        else:
            url_value = first.get("url")
            if not url_value:
                raise RuntimeError(f"Grok Imagine response missing url/base64: {first!r}")
            png_bytes = _fetch_provider_image_url(url_value)

        return _resize_to(png_bytes, request.width, request.height)

    @staticmethod
    def _build_prompt(request: ImageRequest) -> str:
        return (
            f"Brand mark icon for an organization called "
            f"{request.company_name!r}. "
            f"{request.style_prompt}. "
            "Square composition, centered, minimal, abstract — no text, "
            "no letters, no numbers, no logos of other companies, no people. "
            "Solid background, single clear shape or mark, flat or subtly "
            "gradient. Avoid photorealism. Style: modern enterprise app icon "
            "suitable for a Microsoft 365 Copilot or Claude plugin tile."
        )


class GeminiImageProvider(ImageGenerationProvider):
    """Google Gemini image generation via the modern generate_content API.

    Reference: https://ai.google.dev/gemini-api/docs/image-generation

    Uses `client.models.generate_content(model='gemini-3.1-flash-image-preview',
    config=GenerateContentConfig(response_modalities=['TEXT','IMAGE'], ...))`.
    Image bytes are extracted from response.parts via part.as_image() (PIL
    Image), saved to PNG bytes, then resized client-side.

    Falls back gracefully if the installed google-genai is too old to
    expose response_modalities — the fallback chain handles it.
    """

    name = "gemini-image"

    def is_available(self) -> bool:
        return bool(os.environ.get("GEMINI_API_KEY"))

    def generate(self, request: ImageRequest) -> bytes:
        from primr.ai.llm import _get_client  # type: ignore[attr-defined]

        client = _get_client()
        prompt = self._build_prompt(request)

        # Newer google-genai exposes response_modalities and an image_size
        # config on the image-preview model. Older SDKs raise on the kwargs.
        try:
            from google.genai import types  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("google-genai not installed") from exc

        try:
            config = types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            )
        except TypeError as exc:
            raise RuntimeError(
                "google-genai too old: GenerateContentConfig lacks "
                "response_modalities. Upgrade google-genai."
            ) from exc

        response = client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=prompt,
            config=config,
        )

        # Extract image bytes. The current SDK exposes either response.parts
        # with .as_image(), or candidate parts with inline_data.data bytes.
        # We try the modern path first.
        png_bytes: bytes | None = None
        parts = getattr(response, "parts", None)
        if parts is None:
            # Fall back to candidates[0].content.parts (older surface).
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                content = getattr(candidates[0], "content", None)
                parts = getattr(content, "parts", None) if content else None

        if parts:
            for part in parts:
                as_image = getattr(part, "as_image", None)
                if callable(as_image):
                    img = as_image()
                    if img is not None and hasattr(img, "save"):
                        import io

                        buf = io.BytesIO()
                        img.save(buf, format="PNG")  # type: ignore[attr-defined]
                        png_bytes = buf.getvalue()
                        break
                inline = getattr(part, "inline_data", None)
                if inline is not None and getattr(inline, "data", None):
                    raw = inline.data
                    png_bytes = raw if isinstance(raw, bytes) else bytes(raw)
                    break

        if png_bytes is None:
            raise RuntimeError("Gemini image response contained no image part")

        return _resize_to(png_bytes, request.width, request.height)

    @staticmethod
    def _build_prompt(request: ImageRequest) -> str:
        return (
            f"A minimalist brand mark icon for {request.company_name!r}. "
            f"{request.style_prompt}. "
            "Centered, square, no text, no letters, no numbers, no logos. "
            "Abstract geometric form, flat or subtly gradient, solid "
            "background. Modern enterprise app tile suitable for a "
            "Microsoft Copilot or Claude plugin."
        )


class OpenAIImageProvider(ImageGenerationProvider):
    """OpenAI image generation (gpt-image-1 / DALL-E successor).

    Uses OPENAI_API_KEY. Lazily imports the SDK so primr installs without
    pulling openai unless this path runs.
    """

    name = "openai-image"

    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def generate(self, request: ImageRequest) -> bytes:
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("openai SDK not installed; pip install openai") from exc

        client = OpenAI()
        prompt = self._build_prompt(request)
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            n=1,
            size="1024x1024",
        )
        data = result.data
        if not data:
            raise RuntimeError("OpenAI returned no image data")
        b64 = data[0].b64_json
        if not b64:
            raise RuntimeError("OpenAI returned image with empty b64 payload")
        import base64

        png_bytes = base64.b64decode(b64)
        return _resize_to(png_bytes, request.width, request.height)

    @staticmethod
    def _build_prompt(request: ImageRequest) -> str:
        return (
            f"A minimalist brand mark for {request.company_name!r}. "
            f"{request.style_prompt}. "
            "Centered, square, no text or letters, abstract geometric, "
            "modern enterprise app tile."
        )


# Future providers — wire when SDKs mature:
# class FoundryImageProvider(...):  # Microsoft AI Foundry image models
# class BedrockImageProvider(...):  # AWS Bedrock (Titan Image, Stable Diffusion)
# class AnthropicImageProvider(...):  # Claude image generation (when available)


# ---------------------------------------------------------------------------
# Resize helper
# ---------------------------------------------------------------------------


def _resize_to(png_bytes: bytes, width: int, height: int) -> bytes:
    """Resize a PNG to target dimensions. No-op if Pillow is unavailable.

    Pillow is the only dep that can resize binary PNG; without it we return
    the source bytes unchanged. The Cowork manifest spec is forgiving about
    exact pixel dimensions for placeholders, but real submissions need
    correct sizes — that gates upgrading Pillow from optional to required.
    """
    if not icons.pillow_available():
        return png_bytes
    try:
        import io

        from PIL import Image  # type: ignore[import-not-found]

        with Image.open(io.BytesIO(png_bytes)) as src:
            rgb = src.convert("RGB")
            # Pillow 9.1+ moved resampling enums under Image.Resampling;
            # fall back to the legacy constant if the new path is missing.
            resample = getattr(getattr(Image, "Resampling", None), "LANCZOS", None)
            if resample is None:
                resample = getattr(Image, "LANCZOS", 1)  # 1 = LANCZOS in legacy Pillow
            resized = rgb.resize((width, height), resample)
            buf = io.BytesIO()
            resized.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
    except Exception as exc:
        logger.warning("Image resize failed (returning unscaled): %s", exc)
        return png_bytes


def _fetch_provider_image_url(url_value: str, timeout: float = 120.0) -> bytes:
    """Fetch provider-hosted image bytes with SSRF redirect validation."""
    import httpx

    from primr.utils.security import is_safe_url, validate_final_url_after_redirect

    is_safe, reason = is_safe_url(url_value)
    if not is_safe:
        raise RuntimeError(f"Image provider returned unsafe URL: {reason}")

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url_value)
        response.raise_for_status()
        final_url = str(response.url)

    final_safe, redirect_reason = validate_final_url_after_redirect(final_url)
    if not final_safe:
        raise RuntimeError(f"Image provider URL redirected to unsafe location: {redirect_reason}")

    content = response.content
    if len(content) > MAX_PROVIDER_IMAGE_BYTES:
        raise RuntimeError(
            f"Image provider response exceeded {MAX_PROVIDER_IMAGE_BYTES} byte limit"
        )
    return content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_PROVIDER_CHAIN: list[type[ImageGenerationProvider]] = [
    GrokImageProvider,
    GeminiImageProvider,
    OpenAIImageProvider,
]


def generate_icons(
    company_name: str,
    company_description: str | None = None,
    *,
    disable_remote: bool = False,
) -> tuple[bytes, bytes]:
    """Produce (color_icon_192, outline_icon_32) for the given company.

    Tries each remote provider in order; on the first one that returns
    bytes successfully, uses that for the color icon and synthesizes the
    outline icon from the programmatic path (32x32 isn't worth an LLM
    image call — and the programmatic outline matches existing Cowork
    examples in shape).

    Args:
        company_name: Display name for the company.
        company_description: Optional one-line description that improves
            prompt quality (e.g. "a logistics SaaS company").
        disable_remote: If True, skip every remote provider and go
            straight to the programmatic path. Used for offline tests
            and cost-sensitive runs.
    """
    style = company_description or "modern enterprise software"
    request = ImageRequest(
        company_name=company_name,
        style_prompt=style,
        width=192,
        height=192,
    )

    if not disable_remote:
        for provider_cls in _PROVIDER_CHAIN:
            provider = provider_cls()
            if not provider.is_available():
                logger.info("Image provider %s unavailable (no key)", provider.name)
                continue
            try:
                logger.info("Generating icon via %s", provider.name)
                color_bytes = provider.generate(request)
                outline_bytes = icons.build_outline_icon(company_name)
                return color_bytes, outline_bytes
            except Exception as exc:
                logger.warning(
                    "Image provider %s failed (%s); falling through chain",
                    provider.name,
                    exc,
                )
                continue

    # All remote providers exhausted (or disabled) — use the programmatic path.
    logger.info("Falling back to programmatic icon generation")
    return icons.build_color_icon(company_name), icons.build_outline_icon(company_name)


__all__ = [
    "GeminiImageProvider",
    "GrokImageProvider",
    "ImageGenerationProvider",
    "ImageRequest",
    "OpenAIImageProvider",
    "generate_icons",
]
