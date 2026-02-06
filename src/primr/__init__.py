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

# Lazy imports to avoid circular dependencies during test collection
# Submodules are loaded on first access via __getattr__


def __getattr__(name: str):
    """Lazy-load submodules on first access."""
    if name in ("ai", "config", "core", "data", "output", "types", "utils", "agentic"):
        import importlib
        return importlib.import_module(f".{name}", __name__)
    if name == "api":
        # api requires fastapi, load separately
        import importlib
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
