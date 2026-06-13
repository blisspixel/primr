"""The ``generate-vendor`` command handler.

Extracted from ``cli.py`` to keep that file under its size ceiling. Behavior is
unchanged from the inline version: generate cached vendor AI-research documents
for one platform or all of them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from primr.utils.console import console

if TYPE_CHECKING:
    from primr.core.cli import CLIConfig


def run_generate_vendor(config: CLIConfig) -> int:
    """Generate cached vendor AI-research documents (one platform or all)."""
    from primr.core.vendor_research import generate_vendor_research_sync

    console.banner("Vendor AI Research Generation")

    if config.generate_vendor == "all":
        vendors = ["azure", "aws", "gcp", "agnostic"]
    else:
        vendors = [config.generate_vendor] if config.generate_vendor else []

    for vendor in vendors:
        console.step(f"Generating {vendor.upper()} research")
        result = generate_vendor_research_sync(vendor)
        if result:
            console.ok(f"Saved: {result}")
        else:
            console.error(f"Failed to generate {vendor} research")

    return 0
