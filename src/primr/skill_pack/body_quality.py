"""Structural body-quality checks for generated Agent Skills.

The validator owns ship/no-ship decisions. This module only owns the small
set of structural markers that keep generated skills from becoming thin role
templates with headings but no usable workflow guidance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REQUIRED_BODY_SECTIONS = (
    "What This Skill Does",
    "Workflow",
    "Output Format",
)


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
        "required inputs",
        re.compile(r"\brequired inputs\s*:", re.IGNORECASE),
        "include an explicit 'Required inputs:' line or list",
    ),
    BodyQualityMarker(
        "produces",
        re.compile(r"\bproduces\s*:", re.IGNORECASE),
        "include an explicit 'Produces:' line or list",
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


def section_shape_errors(body: str) -> list[str]:
    """Return structural H2-section errors for the draft-skill house format."""
    found = [
        match.group(1).strip()
        for match in re.finditer(r"^##\s+(.+?)\s*$", body, re.IGNORECASE | re.MULTILINE)
    ]
    normalized_required = {section.lower(): section for section in REQUIRED_BODY_SECTIONS}
    found_lower = [section.lower() for section in found]

    errors: list[str] = []
    missing = [section for section in REQUIRED_BODY_SECTIONS if section.lower() not in found_lower]
    if missing:
        errors.append(f"missing required H2 section(s): {', '.join(missing)}")

    unexpected = [section for section in found if section.lower() not in normalized_required]
    if unexpected:
        errors.append(
            "unexpected H2 section(s): "
            + ", ".join(unexpected)
            + "; draft skills must keep company/background/detail in the three-section format"
        )

    ordered_required = [section.lower() for section in REQUIRED_BODY_SECTIONS]
    projected = [section for section in found_lower if section in normalized_required]
    if projected != ordered_required[: len(projected)]:
        errors.append(
            "required H2 sections are out of order; use What This Skill Does, Workflow, "
            "Output Format"
        )

    return errors


__all__ = [
    "REQUIRED_BODY_SECTIONS",
    "missing_quality_markers",
    "quality_marker_guidance",
    "section_shape_errors",
]
