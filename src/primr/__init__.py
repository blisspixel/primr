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

# Import subpackages explicitly so "from primr.X.Y import Z" works
# The circular import issues have been fixed by lazy-initializing:
# - Gemini client in ai/llm.py
# - Search API check in data/search_utils.py
from . import agentic, ai, config, core, data, output, types, utils


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
