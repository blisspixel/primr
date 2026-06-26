"""Small helpers for strategy-generation orchestration."""

from __future__ import annotations


def count_strategy_phases(strategies: list[str], platforms: tuple[str, ...]) -> int:
    """Return the number of strategy-generation phase banners needed."""

    return sum(len(platforms) if strategy == "ai" else 1 for strategy in strategies)


def strategy_vendors(strategy_name: str, platforms: tuple[str, ...]) -> list[str]:
    """Return vendor loop values for one strategy name."""

    return list(platforms) if strategy_name == "ai" else ["agnostic"]


def strategy_display_labels(
    strategy_name: str, vendor: str, platforms: tuple[str, ...]
) -> tuple[str, str]:
    """Return display strategy name and vendor suffix for progress output."""

    from primr.prompts.registry import get_registry

    strategy_module = get_registry().get(strategy_name)
    display_name = (
        strategy_module.display_name if strategy_module else strategy_name.replace("_", " ").title()
    )
    vendor_label = f" ({vendor.upper()})" if strategy_name == "ai" and len(platforms) > 1 else ""
    return display_name, vendor_label


def record_strategy_completion(
    *,
    strategy_paths: dict[str, str],
    strategy_name: str,
    vendor: str,
    platforms: tuple[str, ...],
    output_path: str,
    folder_path: str,
    display_strategy_name: str,
    vendor_label: str,
) -> None:
    """Record a generated strategy path and append the completion event."""

    from primr.core.run_state_io import _append_run_event
    from primr.utils.console import console

    key = f"ai_{vendor}" if strategy_name == "ai" and len(platforms) > 1 else strategy_name
    strategy_paths[key] = output_path
    console.phase_complete(f"{display_strategy_name}{vendor_label} Analysis")
    _append_run_event(
        folder_path,
        "strategy_generation",
        "completed",
        f"{display_strategy_name}{vendor_label} completed",
        output=output_path,
    )
