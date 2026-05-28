"""Lightweight loader for skill_pack/*.yaml prompts.

Separate from primr.prompts.loader because that loader is sized for the
report-writing pipeline (sections, epistemic rules, multi-part composition).
Skill pack prompts are simpler: a system_prompt + a user_prompt_template
with named placeholders. Keeping a small dedicated loader makes the
prompt structure easy to read and test.
"""

from __future__ import annotations

import functools
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "skill_pack"


@dataclass
class SkillPackPrompt:
    """A loaded skill_pack prompt."""

    name: str
    version: str
    phase: str
    system_prompt: str
    user_prompt_template: str

    def render(self, **kwargs: object) -> str:
        """Substitute placeholders in the user prompt template."""
        return self.user_prompt_template.format(**kwargs)


@functools.lru_cache(maxsize=8)
def load_skill_pack_prompt(name: str) -> SkillPackPrompt:
    """Load a prompt by name (filename without .yaml extension)."""
    path = PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"skill_pack prompt not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    meta = data.get("meta", {})
    return SkillPackPrompt(
        name=meta.get("name", name),
        version=str(meta.get("version", "1.0.0")),
        phase=str(meta.get("phase", "?")),
        system_prompt=data["system_prompt"].rstrip(),
        user_prompt_template=data["user_prompt_template"].rstrip(),
    )


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

# LLMs sometimes wrap JSON in ```json fences despite explicit instructions.
# This regex strips a single leading + trailing fence pair if present.
_FENCE_PATTERN = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def extract_json(text: str) -> dict:
    """Extract a JSON object from an LLM response.

    Strips markdown code fences if present, then locates the outermost
    `{ ... }` span and parses it. Raises ValueError if no valid JSON is
    recoverable.
    """
    text = text.strip()

    # Strip a wrapping ```json ... ``` fence if present.
    m = _FENCE_PATTERN.match(text)
    if m:
        text = m.group(1).strip()

    # If the text is exactly JSON, parse directly.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Otherwise locate the outermost {...} span.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in LLM response (first 200 chars: {text[:200]!r})")
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse JSON from LLM response: {exc} "
            f"(candidate first 200 chars: {candidate[:200]!r})"
        ) from exc


__all__ = ["SkillPackPrompt", "extract_json", "load_skill_pack_prompt"]
