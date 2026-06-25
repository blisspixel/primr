"""
Primr - AI-powered company research and report generation.

This package provides tools for automated company research including:
- Web scraping and content extraction
- Google Search API integration
- AI-powered analysis and summarization
- Professional report generation (TXT, DOCX, PDF)
- REST API for research requests (optional, requires fastapi)
"""

__version__ = "1.33.3"
__author__ = "Nick Seal"

# Subpackages are available via direct import:
#   from primr.core import something
#   from primr.output.something import Thing
#
# We use lazy loading to avoid circular import issues.


def __getattr__(name: str):
    """Lazy-load submodules."""
    import importlib

    submodules = {"agentic", "ai", "api", "config", "core", "data", "output", "types", "utils"}
    if name in submodules:
        return importlib.import_module(f".{name}", __name__)
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
