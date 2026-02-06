"""
Primr - AI-powered company research and report generation.

This package provides tools for automated company research including:
- Web scraping and content extraction
- Google Search API integration
- AI-powered analysis and summarization
- Professional report generation (TXT, DOCX, PDF)
- REST API for research requests (optional, requires fastapi)
"""

__version__ = "1.5.1"
__author__ = "Nick Seal"

# Import core subpackages (api is lazy-loaded since it requires fastapi)
# Use relative imports for mypy compatibility
from . import ai, config, core, data, output, types, utils  # type: ignore[attr-defined]

# Main entry point
from .core.research_agent import perform_research


def __getattr__(name: str):
    """Lazy-load optional modules like api (requires fastapi)."""
    if name == "api":
        from . import api
        return api
    raise AttributeError(f"module 'primr' has no attribute {name!r}")


__all__ = [
    "__version__",
    "ai",
    "api",
    "config",
    "core",
    "data",
    "output",
    "perform_research",
    "types",
    "utils",
]
