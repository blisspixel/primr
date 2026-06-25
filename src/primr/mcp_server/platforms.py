"""Platform alias normalization shared by MCP tool handlers."""

from __future__ import annotations

_PLATFORM_ALIASES: dict[str, str | list[str]] = {
    "microsoft": "azure",
    "amazon": "aws",
    "google": "gcp",
    "nvidia": "private",
    "ms": ["azure", "private"],
}


def normalize_platform(value: str) -> str:
    """Resolve one platform alias to its canonical value."""
    mapped = _PLATFORM_ALIASES.get(value.lower())
    if isinstance(mapped, str):
        return mapped
    return value


def normalize_platforms(values: list[str]) -> list[str]:
    """Resolve platform aliases, expanding multi-valued aliases like ``ms``."""
    result: list[str] = []
    for value in values:
        mapped = _PLATFORM_ALIASES.get(value.lower())
        if isinstance(mapped, list):
            result.extend(mapped)
        elif isinstance(mapped, str):
            result.append(mapped)
        else:
            result.append(value)

    seen: set[str] = set()
    deduped: list[str] = []
    for item in result:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped
