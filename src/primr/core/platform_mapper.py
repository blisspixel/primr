"""
Platform mapper: maps recon fingerprint slugs to platform values.

Pure function module — no side effects, no I/O.
"""

__all__ = ["map_platforms"]

# Slug-to-platform mapping rules
_PLATFORM_SLUG_MAP: dict[str, str] = {
    "aws-route53": "aws",
    "aws-cloudfront": "aws",
    "aws-ses": "aws",
    "aws-acm": "aws",
    "azure-dns": "azure",
    "azure-cdn": "azure",
    "azure-appservice": "azure",
    "azure-tm": "azure",
    "microsoft365": "azure",
    "gcp-dns": "gcp",
    "google-workspace": "gcp",
    "google-trust": "gcp",
}


def map_platforms(slugs: tuple[str, ...] | list[str] | set[str]) -> tuple[str, ...]:
    """Map fingerprint slugs to platform values, ordered by detection count.

    Pure function: no side effects, no I/O.

    Args:
        slugs: Sequence of fingerprint slug strings from TenantInfo.slugs

    Returns:
        Tuple of platform strings ordered by match count (descending).
        Returns ("agnostic",) if no infrastructure slugs match.
    """
    counts: dict[str, int] = {}
    for slug in slugs:
        platform = _PLATFORM_SLUG_MAP.get(slug)
        if platform:
            counts[platform] = counts.get(platform, 0) + 1

    if not counts:
        return ("agnostic",)

    # Sort by count descending, then alphabetically for stability
    sorted_platforms = sorted(counts.keys(), key=lambda p: (-counts[p], p))
    return tuple(sorted_platforms)
