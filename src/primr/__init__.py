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

# Import subpackages - these must be real imports for submodule access to work
# (e.g., from primr.output.something import ...)
# type:ignore needed because mypy doesn't recognize all subpackages
from . import agentic, ai, config, core, data, output, types, utils  # type: ignore[attr-defined]


def __getattr__(name: str):
    """Lazy-load optional modules."""
    if name == "api":
        from . import api
        return api
    if name == "perform_research":
        from .core.research_agent import perform_research
        return perform_research
    raise AttributeError(f"module 'primr' has no attribute {name!r}")


__all__ = [
    "__version__",
    "agentic",
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
