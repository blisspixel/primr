"""
Platform mapper: maps recon fingerprint slugs to platform values.

Pure function module with no side effects or I/O.
"""

__all__ = [
    "DEFAULT_PLATFORM_FALLBACK",
    "map_platforms",
    "restore_strategy_platforms",
    "select_strategy_platforms",
]

DEFAULT_PLATFORM_FALLBACK: tuple[str, ...] = ("agnostic",)

# Slug-to-platform mapping rules.
#
# Keep this deliberately limited to strong infrastructure signals. Productivity
# and certificate/email signals such as microsoft365, google-workspace,
# google-trust, aws-ses, or aws-acm are valuable recon context, but they are not
# enough to declare a primary cloud provider for strategy generation.
_PLATFORM_SLUG_MAP: dict[str, str] = {
    "aws-route53": "aws",
    "aws-cloudfront": "aws",
    "azure-dns": "azure",
    "azure-cdn": "azure",
    "azure-appservice": "azure",
    "azure-tm": "azure",
    "gcp-dns": "gcp",
}


def map_platforms(slugs: tuple[str, ...] | list[str] | set[str]) -> tuple[str, ...]:
    """Map fingerprint slugs to platform values, ordered by detection count.

    Pure function: no side effects, no I/O.

    Args:
        slugs: Sequence of fingerprint slug strings from TenantInfo.slugs

    Returns:
        Tuple of platform strings ordered by match count (descending).
        Returns one vendor-neutral strategy target when no strong
        infrastructure slugs match.
    """
    counts: dict[str, int] = {}
    for slug in slugs:
        platform = _PLATFORM_SLUG_MAP.get(slug)
        if platform:
            counts[platform] = counts.get(platform, 0) + 1

    if not counts:
        return DEFAULT_PLATFORM_FALLBACK

    # Sort by count descending, then alphabetically for stability
    sorted_platforms = sorted(counts.keys(), key=lambda p: (-counts[p], p))
    return tuple(sorted_platforms)


def select_strategy_platforms(
    detected_platforms: tuple[str, ...],
    explicit_platforms: tuple[str, ...] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...], str, str]:
    """Resolve one integrated default while preserving explicit fan-out.

    Returns the strategy targets, strong recon signals, source label, and a
    user-facing explanation. This keeps policy branches out of orchestration.
    """
    detected_platforms = detected_platforms or DEFAULT_PLATFORM_FALLBACK
    explicit_platforms = explicit_platforms or None
    strong_signals = detected_platforms != DEFAULT_PLATFORM_FALLBACK
    observed = detected_platforms if strong_signals else ()
    if explicit_platforms is not None:
        if observed and set(observed) != set(explicit_platforms):
            message = (
                f"Recon: observed {', '.join(observed)}; using explicit platform selection "
                f"{', '.join(explicit_platforms)}"
            )
        else:
            message = f"Recon: using explicit platform selection {', '.join(explicit_platforms)}"
        return explicit_platforms, observed, "explicit", message
    if not strong_signals:
        return (
            DEFAULT_PLATFORM_FALLBACK,
            (),
            "default_agnostic",
            "Recon: no strong infrastructure platform signal; using one vendor-neutral AI Strategy",
        )
    if len(detected_platforms) > 1:
        return (
            DEFAULT_PLATFORM_FALLBACK,
            detected_platforms,
            "recon_multiple_integrated",
            f"Recon: observed multiple infrastructure ecosystems ({', '.join(detected_platforms)}); "
            "using one integrated vendor-neutral AI Strategy",
        )
    return (
        detected_platforms,
        detected_platforms,
        "recon_single",
        f"Recon: selected platform from strong signal: {detected_platforms[0]}",
    )


def restore_strategy_platforms(
    platforms: tuple[str, ...],
    source: str,
    explicit_platforms: bool,
    existing_state: object,
) -> tuple[tuple[str, ...], str]:
    """Preserve a resumed run's prior automatic selection until recon succeeds."""
    if explicit_platforms or not isinstance(existing_state, dict):
        return platforms, source
    stored = existing_state.get("cloud_vendors")
    valid = {"agnostic", "aws", "azure", "gcp", "private"}
    if (
        not isinstance(stored, list)
        or not stored
        or any(not isinstance(item, str) or item not in valid for item in stored)
    ):
        return platforms, source
    stored_source = existing_state.get("strategy_platform_source")
    resumed_source = (
        stored_source if isinstance(stored_source, str) and stored_source else "resumed"
    )
    return tuple(dict.fromkeys(item for item in stored if isinstance(item, str))), resumed_source
