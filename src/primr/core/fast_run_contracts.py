"""Typed callbacks supplied by the research composition root to leaf stages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ReportTransform(Protocol):
    def __call__(
        self,
        company_name: str,
        website: str | None,
        report_content: str,
        source_urls: list[str],
        model: str | None = None,
    ) -> str: ...


class AIPrompt(Protocol):
    def __call__(
        self, company_name: str, platform: str, discovery_notes_content: str | None = None
    ) -> str: ...


class YamlPrompt(Protocol):
    def __call__(
        self,
        strategy_config: dict[str, Any],
        company_name: str,
        discovery_notes_content: str | None = None,
    ) -> str: ...


class StrategyEnrichment(Protocol):
    def __call__(
        self,
        strategy_content: str,
        company_name: str,
        vendor: str,
        label: str,
        source_urls: list[str],
        source_urls_seen: set[str],
        analysis_workbook: str,
        website: str | None,
        grok_reasoning: str | None = None,
        grok_writing: str | None = None,
    ) -> str: ...


class StrategyPreparation(Protocol):
    def __call__(
        self,
        strategy_content: str,
        company_name: str,
        vendor: str,
        strategy_label: str,
        source_urls: list[str],
        model: str | None = None,
    ) -> tuple[str, dict[str, int | float | bool], list[str]]: ...


class StrategySave(Protocol):
    def __call__(
        self,
        strategy_content: str,
        company_name: str,
        platform: str,
        strategy_label: str = "AI_Strategy",
        output_dir: str | Path | None = None,
        diagnostics_dir: str | Path | None = None,
        write_txt: bool = True,
    ) -> str | None: ...


@dataclass(frozen=True)
class StrategyServices:
    build_ai_prompt: AIPrompt
    build_yaml_prompt: YamlPrompt
    session_cost: Callable[[], float]
    enrich: StrategyEnrichment
    prepare: StrategyPreparation
    save: StrategySave
