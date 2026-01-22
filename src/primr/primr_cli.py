#!/usr/bin/env python
"""
Primr - AI-Powered Company Research

Usage (if not pip installed):
    python primr_cli.py "Tesla" https://tesla.com
    python primr_cli.py doctor

Recommended (after pip install -e .):
    primr "Tesla" https://tesla.com
    primr doctor
"""

import sys
from pathlib import Path

# Add src to path for package imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from primr.core.research_agent import main

if __name__ == "__main__":
    main()
