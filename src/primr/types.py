"""
Type definitions for the primr package.

This module provides:
- TypedDict definitions for structured data
- Protocol definitions for dependency injection
- Type aliases for common patterns
- Enums for constrained values

Usage:
    from primr.types import (
        ScrapedContent,
        SearchResult,
        ReportSection,
        AIModelType,
    )
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Generic, Protocol, TypedDict, TypeVar, runtime_checkable

# =============================================================================
# TYPE ALIASES
# =============================================================================

# URL and path types
URL = str
FilePath = str | Path

# Content types
HTMLContent = str
TextContent = str
JSONContent = dict[str, Any]

# Callback types
ProgressCallback = Callable[[int, int, str], None]
ErrorCallback = Callable[[Exception, str], None]


# =============================================================================
# ENUMS
# =============================================================================


class AIModelType(str, Enum):
    """AI model types for different tasks."""

    RESEARCH = "research"
    REPORT = "report"

    def __str__(self) -> str:
        return self.value


class ThinkingLevel(str, Enum):
    """AI thinking depth levels."""

    LOW = "low"
    HIGH = "high"

    def __str__(self) -> str:
        return self.value


class ScrapeTier(str, Enum):
    """Scraping method tiers in order of complexity."""

    REQUESTS = "requests"
    HTTPX = "httpx"
    PLAYWRIGHT = "playwright"
    PLAYWRIGHT_AGGRESSIVE = "playwright_aggressive"
    VISION = "vision"
    CACHE = "cache"

    def __str__(self) -> str:
        return self.value


class OutputFormat(str, Enum):
    """Supported output formats."""

    TXT = "txt"
    DOCX = "docx"
    PDF = "pdf"
    HTML = "html"
    JSON = "json"

    def __str__(self) -> str:
        return self.value


class LogLevel(str, Enum):
    """Logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def __str__(self) -> str:
        return self.value


# =============================================================================
# TYPED DICTS - Structured data shapes
# =============================================================================


class SearchResult(TypedDict):
    """A single search result from Google or other search engines."""

    title: str
    url: str
    snippet: str


class SearchResultWithScore(TypedDict):
    """Search result with relevance scoring."""

    title: str
    url: str
    snippet: str
    score: float
    source: str


class ScrapedPage(TypedDict):
    """Result of scraping a single page."""

    url: str
    content: str
    tier: str
    timestamp: str
    word_count: int


class ScrapedContent(TypedDict, total=False):
    """Collection of scraped content from multiple sources."""

    # Keys are URLs, values are content
    # Using total=False since keys are dynamic


class LinkInfo(TypedDict):
    """Information about a discovered link."""

    url: str
    text: str
    relevance: float


class CacheMetadata(TypedDict):
    """Metadata for cached content."""

    url: str
    timestamp: str
    size: int
    tier: str | None


class GradeResult(TypedDict):
    """Result of grading a report section."""

    score: float
    needs_research: bool
    feedback: str
    suggestions: list[str]


class ReportSection(TypedDict):
    """A section of the research report."""

    name: str
    key: str
    content: str
    grade: float | None
    word_count: int


class CompanyInfo(TypedDict, total=False):
    """Basic company information."""

    name: str
    website: str | None
    industry: str | None
    description: str | None


class ResearchContext(TypedDict):
    """Context passed through the research pipeline."""

    company_name: str
    website: str | None
    industry: str | None
    folder_path: str
    overview: str
    summarized_insights: str
    value_theory: str


class AIRequestConfig(TypedDict, total=False):
    """Configuration for an AI request."""

    model_type: str
    temperature: float
    thinking_level: str
    max_retries: int
    timeout: float


class ScrapeConfig(TypedDict, total=False):
    """Configuration for scraping operations."""

    max_pages: int
    max_depth: int
    timeout: int
    use_vision: bool
    respect_robots: bool


# =============================================================================
# PROTOCOLS - Interfaces for dependency injection
# =============================================================================


@runtime_checkable
class AIClientProtocol(Protocol):
    """Protocol for AI client implementations."""

    def generate(
        self,
        prompt: str,
        model_type: str = "research",
        temperature: float = 1.0,
        thinking_level: str = "high",
        **kwargs: Any,
    ) -> str:
        """Generate content from a prompt."""
        ...

    def generate_fast(self, prompt: str, model_type: str = "research") -> str:
        """Fast generation with minimal thinking."""
        ...


@runtime_checkable
class ScraperProtocol(Protocol):
    """Protocol for web scraper implementations."""

    def scrape(self, url: str, **kwargs: Any) -> str | None:
        """Scrape content from a URL."""
        ...

    def scrape_multiple(self, urls: list[str], **kwargs: Any) -> dict[str, str]:
        """Scrape content from multiple URLs."""
        ...


@runtime_checkable
class SearchProtocol(Protocol):
    """Protocol for search implementations."""

    def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Execute a search query."""
        ...


@runtime_checkable
class CacheProtocol(Protocol):
    """Protocol for cache implementations."""

    def get(self, key: str) -> str | None:
        """Get cached content."""
        ...

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Set cached content."""
        ...

    def delete(self, key: str) -> None:
        """Delete cached content."""
        ...

    def clear(self) -> None:
        """Clear all cached content."""
        ...


@runtime_checkable
class LoggerProtocol(Protocol):
    """Protocol for logger implementations."""

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log debug message."""
        ...

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log info message."""
        ...

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log warning message."""
        ...

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log error message."""
        ...


@runtime_checkable
class ConsoleProtocol(Protocol):
    """Protocol for console output implementations."""

    def text(self, msg: str) -> None:
        """Print plain text."""
        ...

    def step(self, msg: str) -> None:
        """Print a step indicator."""
        ...

    def ok(self, msg: str) -> None:
        """Print success message."""
        ...

    def warn(self, msg: str) -> None:
        """Print warning message."""
        ...

    def error(self, msg: str) -> None:
        """Print error message."""
        ...


# =============================================================================
# GENERIC TYPES
# =============================================================================

T = TypeVar("T")
E = TypeVar("E", bound=Exception)


@dataclass
class Result(Generic[T]):
    """
    A result type that can be either success or failure.

    Usage:
        result = Result.ok(data)
        result = Result.err(error)

        if result.is_ok:
            print(result.value)
        else:
            print(result.error)
    """

    _value: T | None = None
    _error: Exception | None = None

    @property
    def is_ok(self) -> bool:
        """Check if result is successful."""
        return self._error is None

    @property
    def is_err(self) -> bool:
        """Check if result is an error."""
        return self._error is not None

    @property
    def value(self) -> T:
        """Get the success value. Raises if error."""
        if self._error is not None:
            raise self._error
        return self._value  # type: ignore

    @property
    def error(self) -> Exception | None:
        """Get the error if present."""
        return self._error

    def unwrap_or(self, default: T) -> T:
        """Get value or return default if error."""
        if self._error is not None:
            return default
        return self._value  # type: ignore

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        """Create a success result."""
        return cls(_value=value)

    @classmethod
    def err(cls, error: Exception) -> "Result[T]":
        """Create an error result."""
        return cls(_error=error)


# =============================================================================
# TYPE GUARDS
# =============================================================================


def is_valid_url(value: Any) -> bool:
    """Type guard to check if value is a valid URL string."""
    if not isinstance(value, str):
        return False
    return value.startswith(("http://", "https://"))


def is_search_result(value: Any) -> bool:
    """Type guard to check if value is a SearchResult."""
    if not isinstance(value, dict):
        return False
    return all(k in value for k in ("title", "url", "snippet"))


def is_scraped_page(value: Any) -> bool:
    """Type guard to check if value is a ScrapedPage."""
    if not isinstance(value, dict):
        return False
    return all(k in value for k in ("url", "content", "tier"))


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Type aliases
    "URL",
    # Protocols
    "AIClientProtocol",
    # Enums
    "AIModelType",
    "AIRequestConfig",
    "CacheMetadata",
    "CacheProtocol",
    "CompanyInfo",
    "ConsoleProtocol",
    "ErrorCallback",
    "FilePath",
    "GradeResult",
    "HTMLContent",
    "JSONContent",
    "LinkInfo",
    "LogLevel",
    "LoggerProtocol",
    "OutputFormat",
    "ProgressCallback",
    "ReportSection",
    "ResearchContext",
    # Generic types
    "Result",
    "ScrapeConfig",
    "ScrapeTier",
    "ScrapedContent",
    "ScrapedPage",
    "ScraperProtocol",
    "SearchProtocol",
    # TypedDicts
    "SearchResult",
    "SearchResultWithScore",
    "TextContent",
    "ThinkingLevel",
    "is_scraped_page",
    "is_search_result",
    # Type guards
    "is_valid_url",
]
