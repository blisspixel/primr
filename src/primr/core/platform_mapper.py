"""
Platform mapper: maps recon fingerprint slugs to platform values.

Pure function module — no side effects, no I/O.
"""

__all__ = ["DEFAULT_PLATFORM_FALLBACK", "map_platforms"]

DEFAULT_PLATFORM_FALLBACK: tuple[str, ...] = ("azure", "private")

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
        Returns the Microsoft + private cloud/NVIDIA fallback when no strong
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
