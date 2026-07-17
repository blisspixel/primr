"""
Adaptive scraping with domain learning.

This module provides:
- Learning which scraping tier works for each domain
- Automatic timeout adjustment based on site behavior
- Domain-specific configuration persistence

Usage:
    scraper = AdaptiveScraper()
    content = scraper.scrape("https://example.com")
    # Automatically uses the best tier for example.com
"""

import functools
import json
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from primr.config.config import PROJECT_ROOT
from primr.utils.logging_config import get_logger

logger = get_logger("adaptive_scraper")


@dataclass
class DomainProfile:
    """Profile of scraping behavior for a domain."""

    domain: str
    preferred_tier: str = "requests"
    avg_response_time: float = 0.0
    success_rate: float = 1.0
    timeout_multiplier: float = 1.0
    last_success: str | None = None
    last_failure: str | None = None

    # Tier success counts
    tier_successes: dict[str, int] = field(default_factory=dict)
    tier_failures: dict[str, int] = field(default_factory=dict)
    tier_times: dict[str, list[float]] = field(default_factory=dict)

    # Total counts
    total_attempts: int = 0
    total_successes: int = 0

    def record_attempt(self, tier: str, success: bool, response_time: float) -> None:
        """Record a scraping attempt."""
        self.total_attempts += 1

        if success:
            self.total_successes += 1
            self.last_success = datetime.now().isoformat()
            self.tier_successes[tier] = self.tier_successes.get(tier, 0) + 1

            # Track response times
            if tier not in self.tier_times:
                self.tier_times[tier] = []
            self.tier_times[tier].append(response_time)
            # Keep only last 10 times
            self.tier_times[tier] = self.tier_times[tier][-10:]
        else:
            self.last_failure = datetime.now().isoformat()
            self.tier_failures[tier] = self.tier_failures.get(tier, 0) + 1

        # Update metrics
        self._update_metrics()

    def _update_metrics(self) -> None:
        """Update computed metrics."""
        # Success rate
        if self.total_attempts > 0:
            self.success_rate = self.total_successes / self.total_attempts

        # Find best tier
        best_tier = "requests"
        best_score: float = -1.0

        for tier in ["requests", "httpx", "playwright", "playwright_aggressive", "vision"]:
            successes = self.tier_successes.get(tier, 0)
            failures = self.tier_failures.get(tier, 0)
            total = successes + failures

            if total >= 2:  # Need at least 2 attempts
                rate = successes / total
                # Score considers success rate and speed
                avg_time = self._get_avg_time(tier)
                # Prefer faster tiers with good success rates
                score = rate * (1 / (1 + avg_time / 10))

                if score > best_score:
                    best_score = score
                    best_tier = tier

        self.preferred_tier = best_tier

        # Update average response time
        all_times = []
        for times in self.tier_times.values():
            all_times.extend(times)
        if all_times:
            self.avg_response_time = sum(all_times) / len(all_times)

        # Adjust timeout multiplier based on response times
        if self.avg_response_time > 10:
            self.timeout_multiplier = 2.0
        elif self.avg_response_time > 5:
            self.timeout_multiplier = 1.5
        else:
            self.timeout_multiplier = 1.0

    def _get_avg_time(self, tier: str) -> float:
        """Get average response time for a tier."""
        times = self.tier_times.get(tier, [])
        return sum(times) / len(times) if times else 10.0

    def get_tier_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for each tier."""
        stats = {}
        for tier in ["requests", "httpx", "playwright", "playwright_aggressive", "vision"]:
            successes = self.tier_successes.get(tier, 0)
            failures = self.tier_failures.get(tier, 0)
            total = successes + failures
            stats[tier] = {
                "attempts": total,
                "successes": successes,
                "failures": failures,
                "success_rate": successes / total if total > 0 else 0.0,
                "avg_time": self._get_avg_time(tier),
            }
        return stats


class DomainLearner:
    """
    Learns and persists domain scraping profiles.

    Tracks which scraping methods work best for each domain
    and adjusts behavior accordingly.
    """

    def __init__(self, storage_path: str | None = None):
        """
        Initialize the domain learner.

        Args:
            storage_path: Path to store domain profiles
        """
        self._storage_path = storage_path or str(
            Path(PROJECT_ROOT) / "logs" / "domain_profiles.json"
        )
        self._profiles: dict[str, DomainProfile] = {}
        self._lock = threading.Lock()

        # Load existing profiles
        self._load_profiles()

        logger.debug(f"DomainLearner initialized with {len(self._profiles)} profiles")

    def _load_profiles(self) -> None:
        """Load profiles from storage."""
        try:
            path = Path(self._storage_path)
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)

                for domain, profile_data in data.items():
                    self._profiles[domain] = DomainProfile(
                        domain=domain,
                        preferred_tier=profile_data.get("preferred_tier", "requests"),
                        avg_response_time=profile_data.get("avg_response_time", 0.0),
                        success_rate=profile_data.get("success_rate", 1.0),
                        timeout_multiplier=profile_data.get("timeout_multiplier", 1.0),
                        last_success=profile_data.get("last_success"),
                        last_failure=profile_data.get("last_failure"),
                        tier_successes=profile_data.get("tier_successes", {}),
                        tier_failures=profile_data.get("tier_failures", {}),
                        tier_times=profile_data.get("tier_times", {}),
                        total_attempts=profile_data.get("total_attempts", 0),
                        total_successes=profile_data.get("total_successes", 0),
                    )

                logger.info(f"Loaded {len(self._profiles)} domain profiles")
        except json.JSONDecodeError as e:
            logger.warning("Domain profiles file corrupted, starting fresh: %s", e)
        except Exception as e:
            logger.warning(f"Failed to load domain profiles: {e}")

    def _save_profiles(self) -> None:
        """Save profiles to storage."""
        try:
            path = Path(self._storage_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            data = {}
            for domain, profile in self._profiles.items():
                data[domain] = {
                    "preferred_tier": profile.preferred_tier,
                    "avg_response_time": profile.avg_response_time,
                    "success_rate": profile.success_rate,
                    "timeout_multiplier": profile.timeout_multiplier,
                    "last_success": profile.last_success,
                    "last_failure": profile.last_failure,
                    "tier_successes": profile.tier_successes,
                    "tier_failures": profile.tier_failures,
                    "tier_times": profile.tier_times,
                    "total_attempts": profile.total_attempts,
                    "total_successes": profile.total_successes,
                }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        except PermissionError as e:
            logger.error(
                "Failed to save domain profiles (permission denied — file may be locked): %s", e
            )
        except Exception as e:
            logger.error(
                "Failed to save domain profiles (%d profiles lost): %s",
                len(self._profiles),
                e,
            )

    def get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except ValueError:
            return "unknown"

    def get_profile(self, url: str) -> DomainProfile:
        """
        Get or create profile for a domain.

        Args:
            url: URL to get profile for

        Returns:
            DomainProfile for the domain
        """
        domain = self.get_domain(url)

        with self._lock:
            if domain not in self._profiles:
                self._profiles[domain] = DomainProfile(domain=domain)
            return self._profiles[domain]

    def record_attempt(self, url: str, tier: str, success: bool, response_time: float) -> None:
        """
        Record a scraping attempt.

        Args:
            url: URL that was scraped
            tier: Scraping tier used
            success: Whether scrape was successful
            response_time: Time taken in seconds
        """
        profile = self.get_profile(url)

        with self._lock:
            profile.record_attempt(tier, success, response_time)

            # Save periodically (every 10 attempts)
            if profile.total_attempts % 10 == 0:
                self._save_profiles()

    def get_recommended_tier(self, url: str) -> str:
        """
        Get recommended scraping tier for a URL.

        Args:
            url: URL to scrape

        Returns:
            Recommended tier name
        """
        profile = self.get_profile(url)
        return profile.preferred_tier

    def get_recommended_timeout(self, url: str, base_timeout: float = 30.0) -> float:
        """
        Get recommended timeout for a URL.

        Args:
            url: URL to scrape
            base_timeout: Base timeout in seconds

        Returns:
            Adjusted timeout in seconds
        """
        profile = self.get_profile(url)
        return base_timeout * profile.timeout_multiplier

    def get_all_profiles(self) -> dict[str, DomainProfile]:
        """Get all domain profiles."""
        with self._lock:
            return dict(self._profiles)

    def get_stats(self) -> dict[str, Any]:
        """Get overall statistics."""
        with self._lock:
            total_domains = len(self._profiles)
            total_attempts = sum(p.total_attempts for p in self._profiles.values())
            total_successes = sum(p.total_successes for p in self._profiles.values())

            tier_usage: dict[str, int] = defaultdict(int)
            for profile in self._profiles.values():
                tier_usage[profile.preferred_tier] += 1

            success_rate = total_successes / total_attempts if total_attempts > 0 else 0.0
            return {
                "total_domains": total_domains,
                "total_attempts": total_attempts,
                "total_successes": total_successes,
                "overall_success_rate": success_rate,
                "tier_preferences": dict(tier_usage),
            }

    def save(self) -> None:
        """Force save profiles to storage."""
        with self._lock:
            self._save_profiles()

    def clear(self) -> None:
        """Clear all profiles."""
        with self._lock:
            self._profiles.clear()
            self._save_profiles()


class AdaptiveScraper:
    """
    Scraper that adapts to each domain's characteristics.

    Features:
    - Learns which tier works best for each domain
    - Adjusts timeouts based on response times
    - Falls back through tiers on failure

    Example:
        scraper = AdaptiveScraper()
        content, tier = scraper.scrape("https://example.com")
    """

    def __init__(
        self,
        learner: DomainLearner | None = None,
        scrape_functions: dict[str, Callable[..., tuple[str | None, str | None]]] | None = None,
    ):
        """
        Initialize adaptive scraper.

        Args:
            learner: Optional DomainLearner instance
            scrape_functions: Optional dict of tier -> scrape function
        """
        self._learner = learner or DomainLearner()
        self._scrape_functions = scrape_functions

        logger.debug("AdaptiveScraper initialized")

    def _get_scrape_functions(self) -> dict[str, Callable[..., tuple[str | None, str | None]]]:
        """Get scrape functions, importing lazily."""
        if self._scrape_functions is not None:
            return self._scrape_functions

        # Lazy import to avoid circular dependency
        from primr.data.scrape import (
            scrape_with_httpx,
            scrape_with_playwright,
            scrape_with_playwright_aggressive,
            scrape_with_requests,
            scrape_with_vision,
        )

        return {
            "requests": scrape_with_requests,
            "httpx": scrape_with_httpx,
            "playwright": scrape_with_playwright,
            "playwright_aggressive": scrape_with_playwright_aggressive,
            "vision": scrape_with_vision,
        }

    def scrape(
        self, url: str, force_tier: str | None = None, max_tiers: int = 3
    ) -> tuple[str | None, str]:
        """
        Scrape a URL using adaptive tier selection.

        Args:
            url: URL to scrape
            force_tier: Force a specific tier (skip learning)
            max_tiers: Maximum number of tiers to try

        Returns:
            Tuple of (content, tier_used) or (None, error_message)
        """
        scrape_functions = self._get_scrape_functions()

        # Determine tier order
        if force_tier:
            tiers = [force_tier]
        else:
            recommended = self._learner.get_recommended_tier(url)
            # Start with recommended, then fall back through others
            all_tiers = ["requests", "httpx", "playwright", "playwright_aggressive", "vision"]
            tiers = [recommended] + [t for t in all_tiers if t != recommended]
            tiers = tiers[:max_tiers]

        last_error = None

        for tier in tiers:
            if tier not in scrape_functions:
                continue

            scrape_fn = scrape_functions[tier]
            timeout = self._learner.get_recommended_timeout(url)

            start_time = time.time()
            try:
                # Call scrape function
                if tier in ["playwright", "playwright_aggressive", "vision"]:
                    content, error = scrape_fn(url, timeout=int(timeout * 1000))
                else:
                    content, error = scrape_fn(url, timeout=timeout)

                response_time = time.time() - start_time

                if content:
                    # Success
                    self._learner.record_attempt(url, tier, True, response_time)
                    logger.debug(f"Scraped {url} with {tier} in {response_time:.1f}s")
                    return content, tier
                else:
                    # Soft failure
                    self._learner.record_attempt(url, tier, False, response_time)
                    last_error = error or "No content"
                    logger.debug(f"Tier {tier} failed for {url}: {last_error}")

            except Exception as e:
                response_time = time.time() - start_time
                self._learner.record_attempt(url, tier, False, response_time)
                last_error = str(e)[:100]
                logger.warning("Tier %s exception for %s: %s", tier, url, last_error)

        return None, last_error or "All tiers failed"

    def get_domain_profile(self, url: str) -> DomainProfile:
        """Get the domain profile for a URL."""
        return self._learner.get_profile(url)

    def get_stats(self) -> dict[str, Any]:
        """Get scraper statistics."""
        return self._learner.get_stats()

    def save(self) -> None:
        """Save learned profiles."""
        self._learner.save()


# =============================================================================
# SINGLETON ACCESS
# =============================================================================


@functools.lru_cache(maxsize=1)
def get_domain_learner() -> DomainLearner:
    """Get the global domain learner instance (cached singleton)."""
    return DomainLearner()


@functools.lru_cache(maxsize=1)
def get_adaptive_scraper() -> AdaptiveScraper:
    """Get the global adaptive scraper instance (cached singleton)."""
    return AdaptiveScraper(learner=get_domain_learner())


def reset_adaptive_scraper() -> None:
    """Reset the global instances (useful for testing)."""
    get_domain_learner.cache_clear()
    get_adaptive_scraper.cache_clear()


def adaptive_scrape(url: str, **kwargs: Any) -> tuple[str | None, str]:
    """Convenience function to scrape with adaptive tier selection."""
    return get_adaptive_scraper().scrape(url, **kwargs)
