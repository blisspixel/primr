"""Structural body-quality checks for generated Agent Skills.

The validator owns ship/no-ship decisions. This module only owns the small
set of structural markers that keep generated skills from becoming thin role
templates with headings but no usable workflow guidance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BodyQualityMarker:
    label: str
    pattern: re.Pattern[str]
    message: str


QUALITY_MARKERS: tuple[BodyQualityMarker, ...] = (
    BodyQualityMarker(
        "intake checklist",
        re.compile(r"\b(?:first ask|intake|inputs? needed|clarify)\b", re.IGNORECASE),
        "include an intake or elicitation step for missing inputs",
    ),
    BodyQualityMarker(
        "scope guardrail",
        re.compile(r"\bscope guardrail\s*:", re.IGNORECASE),
        "include an explicit 'Scope guardrail:' line",
    ),
    BodyQualityMarker(
        "human checkpoint",
        re.compile(r"\bhuman checkpoint\s*:", re.IGNORECASE),
        "include an explicit 'Human checkpoint:' line",
    ),
    BodyQualityMarker(
        "worked example input",
        re.compile(r"\bexample input\s*:", re.IGNORECASE),
        "include 'Example input:' in the Output Format section",
    ),
    BodyQualityMarker(
        "worked example output",
        re.compile(r"\bexample output\s*:", re.IGNORECASE),
        "include 'Example output:' in the Output Format section",
    ),
)


def missing_quality_markers(body: str) -> list[str]:
    """Return required quality markers absent from a skill body."""
    return [marker.label for marker in QUALITY_MARKERS if not marker.pattern.search(body)]


def quality_marker_guidance(labels: list[str]) -> str:
    """Return compact repair guidance for missing quality-marker labels."""
    guidance = {marker.label: marker.message for marker in QUALITY_MARKERS}
    return " ".join(guidance[label] for label in labels if label in guidance)


__all__ = ["missing_quality_markers", "quality_marker_guidance"]
