"""
Property-based tests for the platform mapper module.

Tests cover:
- Property 1: Platform mapping correctness and ordering
- Property 2: Platform mapper is a pure function (idempotence)

Feature: recon-platform-integration
"""

import copy

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.core.platform_mapper import (
    _PLATFORM_SLUG_MAP,
    DEFAULT_PLATFORM_FALLBACK,
    map_platforms,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# All known slugs from the mapping
KNOWN_SLUGS = list(_PLATFORM_SLUG_MAP.keys())

# Strategy: random subsets of known slugs (with possible repeats)
known_slug_lists = st.lists(st.sampled_from(KNOWN_SLUGS), min_size=0, max_size=20)

# Strategy: random unknown slugs that are NOT in the mapping
unknown_slugs = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=30,
).filter(lambda s: s not in _PLATFORM_SLUG_MAP)

# Strategy: mixed lists of known + unknown slugs
mixed_slug_lists = st.lists(
    st.one_of(st.sampled_from(KNOWN_SLUGS), unknown_slugs),
    min_size=0,
    max_size=30,
)


# ===========================================================================
# Property 1: Platform mapping correctness and ordering
# **Validates: Requirements 4.1, 4.2, 4.3**
# ===========================================================================


class TestPlatformMappingCorrectnessAndOrdering:
    """Property 1: Platform mapping correctness and ordering."""

    @given(slugs=mixed_slug_lists)
    @settings(deadline=None, max_examples=200)
    def test_each_returned_platform_has_matching_slug(self, slugs: list[str]):
        """Each returned platform has ≥1 matching slug in the input.

        **Validates: Requirements 4.1**
        """
        result = map_platforms(slugs)
        if result == DEFAULT_PLATFORM_FALLBACK:
            return
        for platform in result:
            matching = [s for s in slugs if _PLATFORM_SLUG_MAP.get(s) == platform]
            assert len(matching) >= 1, (
                f"Platform '{platform}' has no matching slug in input {slugs}"
            )

    @given(slugs=mixed_slug_lists)
    @settings(deadline=None, max_examples=200)
    def test_ordering_by_descending_count(self, slugs: list[str]):
        """Platforms are ordered by descending match count, alphabetical tiebreak.

        **Validates: Requirements 4.2**
        """
        result = map_platforms(slugs)
        if result == DEFAULT_PLATFORM_FALLBACK:
            return

        # Compute expected counts
        counts: dict[str, int] = {}
        for slug in slugs:
            platform = _PLATFORM_SLUG_MAP.get(slug)
            if platform:
                counts[platform] = counts.get(platform, 0) + 1

        for i in range(len(result) - 1):
            count_a = counts[result[i]]
            count_b = counts[result[i + 1]]
            assert count_a >= count_b, (
                f"Ordering violated: {result[i]}({count_a}) before {result[i + 1]}({count_b})"
            )
            if count_a == count_b:
                assert result[i] < result[i + 1], (
                    f"Alphabetical tiebreak violated: '{result[i]}' should come before '{result[i + 1]}'"
                )

    @given(slugs=mixed_slug_lists)
    @settings(deadline=None, max_examples=200)
    def test_no_duplicates(self, slugs: list[str]):
        """Result contains no duplicate platform strings.

        **Validates: Requirements 4.1, 4.2**
        """
        result = map_platforms(slugs)
        assert len(result) == len(set(result)), f"Duplicates found in {result}"

    @given(slugs=st.lists(unknown_slugs, min_size=0, max_size=10))
    @settings(deadline=None, max_examples=200)
    def test_empty_or_unknown_returns_default_fallback(self, slugs: list[str]):
        """When no slugs match any platform, result is the default fallback.

        **Validates: Requirements 4.3**
        """
        result = map_platforms(slugs)
        assert result == DEFAULT_PLATFORM_FALLBACK, (
            f"Expected {DEFAULT_PLATFORM_FALLBACK} for unknown slugs, got {result}"
        )

    def test_empty_input_returns_default_fallback(self):
        """Empty input returns the default fallback.

        **Validates: Requirements 4.3**
        """
        assert map_platforms(()) == DEFAULT_PLATFORM_FALLBACK
        assert map_platforms([]) == DEFAULT_PLATFORM_FALLBACK
        assert map_platforms(set()) == DEFAULT_PLATFORM_FALLBACK

    def test_productivity_and_certificate_slugs_do_not_select_primary_cloud(self):
        """Weak SaaS/certificate signals do not override the default fallback."""
        assert (
            map_platforms(("microsoft365", "google-workspace", "google-trust", "aws-ses"))
            == DEFAULT_PLATFORM_FALLBACK
        )


# ===========================================================================
# Property 2: Platform mapper is a pure function (idempotence)
# **Validates: Requirements 4.5**
# ===========================================================================


class TestPlatformMapperPurity:
    """Property 2: Platform mapper is a pure function."""

    @given(slugs=mixed_slug_lists)
    @settings(deadline=None, max_examples=200)
    def test_idempotent_results(self, slugs: list[str]):
        """Calling map_platforms multiple times returns identical results.

        **Validates: Requirements 4.5**
        """
        result1 = map_platforms(slugs)
        result2 = map_platforms(slugs)
        result3 = map_platforms(slugs)
        assert result1 == result2 == result3, (
            f"Non-deterministic results: {result1}, {result2}, {result3}"
        )

    @given(slugs=mixed_slug_lists)
    @settings(deadline=None, max_examples=200)
    def test_input_not_modified(self, slugs: list[str]):
        """Input collection is not modified by the call.

        **Validates: Requirements 4.5**
        """
        original = copy.deepcopy(slugs)
        map_platforms(slugs)
        assert slugs == original, f"Input was modified: {original} -> {slugs}"

    @given(slugs=known_slug_lists)
    @settings(deadline=None, max_examples=200)
    def test_tuple_input_same_as_list(self, slugs: list[str]):
        """Tuple and list inputs produce the same result.

        **Validates: Requirements 4.5**
        """
        from_list = map_platforms(slugs)
        from_tuple = map_platforms(tuple(slugs))
        assert from_list == from_tuple, (
            f"Different results for list vs tuple: {from_list} vs {from_tuple}"
        )
