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

# Don't import submodules at package level to avoid circular imports
# Users should import directly: from primr.core import something
# Or use: import primr.core


def __getattr__(name: str):
    """Lazy-load submodules on attribute access."""
    import importlib

    # Standard submodules
    if name in ("agentic", "ai", "api", "config", "core", "data", "output", "types", "utils"):
        return importlib.import_module(f".{name}", __name__)

    # Special exports
    if name == "perform_research":
        from .core.research_agent import perform_research
        return perform_research

    raise AttributeError(f"module 'primr' has no attribute {name!r}")


def __dir__():
    """List available submodules."""
    return [
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
