"""
Property-based tests for Context Map (CLAUDE.md).

This module validates the correctness properties of the Context Map
using the Hypothesis library. Each test corresponds to a formal
property from the design document.

Properties tested:
- Property 5: Context Map Token Budget

Validates: Requirements 1.5
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# =============================================================================
# TOKEN COUNTING UTILITIES
# =============================================================================


def count_tokens_simple(text: str) -> int:
    """
    Simple token counter approximation.

    Uses a conservative estimate: ~4 characters per token for English text.
    This is a reasonable approximation for GPT-style tokenizers.

    For more accurate counting, use tiktoken or similar, but this
    provides a good upper bound for validation.
    """
    # Remove markdown formatting that doesn't contribute to semantic tokens
    # but keep the text content
    cleaned = text.strip()

    # Approximate: 1 token per ~4 characters (conservative for English)
    # This tends to overcount, which is safer for budget validation
    char_based = len(cleaned) / 4

    # Also count by whitespace-separated words as a cross-check
    # Most tokenizers produce ~1.3 tokens per word on average
    words = len(cleaned.split())
    word_based = words * 1.3

    # Return the higher estimate (more conservative)
    return int(max(char_based, word_based))


def extract_quick_start_section(content: str) -> str:
    """
    Extract the Quick Start section from CLAUDE.md.

    The Quick Start section is defined as everything from the
    "## Quick Start" header until the next "---" horizontal rule
    or "## " header.
    """
    # Find Quick Start section
    quick_start_match = re.search(
        r"## Quick Start.*?\n(.*?)(?=\n---|\n## [^#])", content, re.DOTALL | re.IGNORECASE
    )

    if quick_start_match:
        return quick_start_match.group(0)

    # Fallback: try to find just the header and content until next section
    lines = content.split("\n")
    in_quick_start = False
    quick_start_lines = []

    for line in lines:
        if "## Quick Start" in line:
            in_quick_start = True
            quick_start_lines.append(line)
        elif in_quick_start:
            if line.startswith("## ") or line.strip() == "---":
                break
            quick_start_lines.append(line)

    return "\n".join(quick_start_lines)


# =============================================================================
# PROPERTY 5: Context Map Token Budget
# =============================================================================


# Feature: agentic-architecture, Property 5: Context Map Token Budget
def test_context_map_token_budget():
    """
    Quick Start section stays within token budget.

    For any generated CLAUDE.md context map, the quick-start section
    should contain fewer than 2000 tokens when measured by a standard
    tokenizer.

    Validates: Requirements 1.5
    """
    claude_md_path = Path("CLAUDE.md")

    # Skip if CLAUDE.md doesn't exist yet
    if not claude_md_path.exists():
        pytest.skip("CLAUDE.md not present (gitignored; tests run when a local copy exists)")

    content = claude_md_path.read_text(encoding="utf-8")
    quick_start = extract_quick_start_section(content)

    # Verify we found the section
    assert quick_start, "Could not find Quick Start section in CLAUDE.md"
    assert "Quick Start" in quick_start, "Extracted section doesn't contain Quick Start header"

    # Count tokens
    token_count = count_tokens_simple(quick_start)

    # Property: Quick Start should be < 2000 tokens
    # Design doc says < 500 tokens for the summary, but we allow up to 2000
    # for the full Quick Start section including code examples
    max_tokens = 2000

    assert token_count < max_tokens, (
        f"Quick Start section exceeds token budget: "
        f"{token_count} tokens (max: {max_tokens})\n"
        f"Section length: {len(quick_start)} characters"
    )


def test_context_map_structure():
    """
    CLAUDE.md contains all required sections.

    Validates the structural requirements of the context map.
    """
    claude_md_path = Path("CLAUDE.md")

    if not claude_md_path.exists():
        pytest.skip("CLAUDE.md not present (gitignored; tests run when a local copy exists)")

    content = claude_md_path.read_text(encoding="utf-8")

    # Required sections per design doc
    required_sections = [
        "Quick Start",
        "Architecture Pointers",
        "Verification Commands",
        "Negative Constraints",
    ]

    for section in required_sections:
        assert section in content, f"Missing required section: {section}"


def test_context_map_negative_constraints():
    """
    CLAUDE.md contains critical negative constraints.

    Validates that the context map includes the key "what NOT to do"
    guidance for agents.
    """
    claude_md_path = Path("CLAUDE.md")

    if not claude_md_path.exists():
        pytest.skip("CLAUDE.md not present (gitignored; tests run when a local copy exists)")

    content = claude_md_path.read_text(encoding="utf-8")

    # Critical constraints that must be documented
    critical_constraints = [
        "NEVER",  # Should have NEVER statements
        "cost",  # Cost awareness
        "single-job",  # Single job model
        "SSRF",  # Security constraint
    ]

    for constraint in critical_constraints:
        assert constraint.lower() in content.lower(), (
            f"Missing critical constraint documentation: {constraint}"
        )


def test_context_map_verification_commands():
    """
    CLAUDE.md contains runnable verification commands.

    Validates that the context map includes commands agents can use
    to verify system state.
    """
    claude_md_path = Path("CLAUDE.md")

    if not claude_md_path.exists():
        pytest.skip("CLAUDE.md not present (gitignored; tests run when a local copy exists)")

    content = claude_md_path.read_text(encoding="utf-8")

    # Required verification commands
    required_commands = [
        "primr doctor",  # System health
        "pytest",  # Test runner
    ]

    for cmd in required_commands:
        assert cmd in content, f"Missing verification command: {cmd}"


def test_context_map_progressive_disclosure():
    """
    CLAUDE.md uses progressive disclosure for detailed content.

    Validates that detailed sections are wrapped in collapsible
    elements to keep the main document scannable.
    """
    claude_md_path = Path("CLAUDE.md")

    if not claude_md_path.exists():
        pytest.skip("CLAUDE.md not present (gitignored; tests run when a local copy exists)")

    content = claude_md_path.read_text(encoding="utf-8")

    # Should have collapsible sections (HTML details/summary)
    assert "<details>" in content, "Missing progressive disclosure: no <details> elements found"
    assert "<summary>" in content, "Missing progressive disclosure: no <summary> elements found"

    # Count collapsible sections - should have at least 3
    details_count = content.count("<details>")
    assert details_count >= 3, f"Expected at least 3 collapsible sections, found {details_count}"


# =============================================================================
# PROPERTY-BASED TESTS FOR TOKEN BUDGET VARIATIONS
# =============================================================================


@given(
    extra_content=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), max_codepoint=127),
        min_size=0,
        max_size=100,
    )
)
@settings(max_examples=10, deadline=None)
def test_token_counter_consistency(extra_content: str):
    """
    Token counter produces consistent results.

    Property: For any text, the token count should be:
    1. Non-negative
    2. Proportional to text length
    3. Deterministic (same input = same output)
    """
    # Count twice to verify determinism
    count1 = count_tokens_simple(extra_content)
    count2 = count_tokens_simple(extra_content)

    assert count1 == count2, "Token counter should be deterministic"
    assert count1 >= 0, "Token count should be non-negative"

    # Rough proportionality check (only for non-whitespace content)
    stripped = extra_content.strip()
    if len(stripped) > 0:
        # Should be at least 1 token per 10 characters (very conservative)
        assert count1 >= len(stripped) / 10


def test_quick_start_extraction_robustness():
    """
    Quick Start extraction handles various markdown formats.
    """
    # Test with standard format
    standard = """# Title

## Quick Start

Some content here.

### Subsection

More content.

---

## Next Section
"""
    result = extract_quick_start_section(standard)
    assert "Quick Start" in result
    assert "Some content" in result
    assert "Next Section" not in result

    # Test with no separator
    no_sep = """# Title

## Quick Start

Content.

## Architecture
"""
    result = extract_quick_start_section(no_sep)
    assert "Quick Start" in result
    assert "Architecture" not in result
