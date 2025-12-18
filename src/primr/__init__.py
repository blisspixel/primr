"""
Primr - AI-powered company research and report generation.

This package provides tools for automated company research including:
- Web scraping and content extraction
- Google Search API integration
- AI-powered analysis and summarization
- Professional report generation (TXT, DOCX, PDF)
- REST API for research requests
"""

__version__ = "1.0.0"
__author__ = "Nick Seal"

# Import subpackages to make them accessible via primr.subpackage
# Type definitions
from primr import ai, api, config, core, data, output, types, utils

# Main entry point
from primr.core.research_agent import perform_research

__all__ = [
    "ai",
    "api",
    "config",
    "core",
    "data",
    "output",
    "utils",
    "types",
    "perform_research",
    "__version__",
]
