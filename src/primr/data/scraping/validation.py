"""
Content validity checks (separate from soft block detection).

Runs after extraction. Validity failures do NOT trigger tier escalation.
"""

import hashlib
import re
from typing import Optional, Set

from .models import ValidationResult


# Seen templates for duplicate detection (per-run)
_seen_templates: Set[str] = set()


def clear_seen_templates() -> None:
    """Clear seen templates (for testing or new run)."""
    global _seen_templates
    _seen_templates = set()


def _compute_content_hash(text: str) -> str:
    """Compute hash of content structure for duplicate detection."""
    # Normalize whitespace
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    
    # Take structural sample (first 1000 chars)
    sample = normalized[:1000]
    
    # MD5 used for content fingerprinting, not security
    return hashlib.md5(sample.encode(), usedforsecurity=False).hexdigest()


def validate_content(extracted_text: str, url: str) -> ValidationResult:
    """
    Validate extracted content for quality.
    
    NOTE: This is separate from soft block detection.
    - Soft block = anti-bot response → triggers tier escalation
    - Invalid content = low-value page → does NOT escalate tiers
    
    Checks:
    1. Content density (ratio of main content to boilerplate)
    2. Minimum text length beyond boilerplate
    3. Duplicate template detection (same structure, different URLs)
    
    Args:
        extracted_text: Clean text extracted from page
        url: URL of the page (for logging)
    
    Returns:
        ValidationResult with validity status and metrics
    """
    if not extracted_text:
        return ValidationResult(
            valid=False,
            reason="No extracted text",
            content_density=0.0,
        )
    
    text = extracted_text.strip()
    
    # Check minimum length
    if len(text) < 100:
        return ValidationResult(
            valid=False,
            reason=f"Content too short ({len(text)} chars)",
            content_density=0.0,
        )
    
    # Calculate content density
    density = validate_content_density(text)
    
    # Check for duplicate template
    is_duplicate = detect_duplicate_template(text)
    
    # Determine validity
    if density < 0.2:
        return ValidationResult(
            valid=False,
            reason=f"Content density too low ({density:.0%})",
            content_density=density,
            is_duplicate_template=is_duplicate,
        )
    
    if is_duplicate:
        return ValidationResult(
            valid=False,
            reason="Duplicate template detected",
            content_density=density,
            is_duplicate_template=True,
        )
    
    return ValidationResult(
        valid=True,
        content_density=density,
        is_duplicate_template=False,
    )


def validate_content_density(extracted_text: str, min_density: float = 0.2) -> float:
    """
    Calculate content density (ratio of unique content to total).
    
    Higher density = more unique, valuable content.
    Lower density = more boilerplate, navigation, repetition.
    
    Args:
        extracted_text: Clean text to analyze
        min_density: Minimum acceptable density (default 0.2 = 20%)
    
    Returns:
        Density ratio (0.0 to 1.0)
    """
    if not extracted_text:
        return 0.0
    
    lines = [line.strip() for line in extracted_text.split("\n") if line.strip()]
    
    if len(lines) == 0:
        return 0.0
    
    # Count unique lines
    unique_lines = set(lines)
    
    # Calculate density
    density = len(unique_lines) / len(lines)
    
    return density


def detect_duplicate_template(extracted_text: str) -> bool:
    """
    Detect if page is a duplicate template (common in CMS).
    
    Uses structural hash of text to identify templates.
    Registers new templates for future detection.
    
    Args:
        extracted_text: Clean text to check
    
    Returns:
        True if this is a duplicate of a previously seen template
    """
    global _seen_templates
    
    if not extracted_text:
        return False
    
    content_hash = _compute_content_hash(extracted_text)
    
    if content_hash in _seen_templates:
        return True
    
    # Register this template
    _seen_templates.add(content_hash)
    return False


def is_nav_only_page(extracted_text: str) -> bool:
    """
    Check if page contains only navigation/boilerplate.
    
    Args:
        extracted_text: Clean text to check
    
    Returns:
        True if page appears to be nav-only
    """
    if not extracted_text:
        return True
    
    text = extracted_text.strip()
    
    # Very short content is likely nav-only
    if len(text) < 200:
        return True
    
    # Check for common nav-only patterns
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    
    if len(lines) < 5:
        return True
    
    # Check if most lines are very short (typical of nav)
    short_lines = sum(1 for line in lines if len(line) < 30)
    if short_lines / len(lines) > 0.8:
        return True
    
    return False


def estimate_content_quality(extracted_text: str) -> dict:
    """
    Estimate overall content quality with multiple metrics.
    
    Args:
        extracted_text: Clean text to analyze
    
    Returns:
        Dict with quality metrics
    """
    if not extracted_text:
        return {
            "length": 0,
            "line_count": 0,
            "density": 0.0,
            "avg_line_length": 0.0,
            "has_paragraphs": False,
            "quality_score": 0.0,
        }
    
    text = extracted_text.strip()
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    
    length = len(text)
    line_count = len(lines)
    density = validate_content_density(text)
    avg_line_length = length / line_count if line_count > 0 else 0
    
    # Check for paragraph-like content (lines > 100 chars)
    long_lines = sum(1 for line in lines if len(line) > 100)
    has_paragraphs = long_lines >= 3
    
    # Calculate quality score (0-100)
    # Minimum length threshold - very short content gets heavily penalized
    if length < 100:
        return {
            "length": length,
            "line_count": line_count,
            "density": density,
            "avg_line_length": avg_line_length,
            "has_paragraphs": has_paragraphs,
            "quality_score": length / 10,  # Max 10 points for <100 chars
        }
    
    score = 0.0
    
    # Length contribution (up to 30 points, scaled logarithmically)
    # 100 chars = ~6 points, 500 chars = ~18 points, 1000+ chars = 30 points
    if length >= 1000:
        score += 30
    else:
        score += (length / 1000) * 30
    
    # Density contribution (up to 30 points)
    score += density * 30
    
    # Paragraph contribution (up to 20 points)
    if has_paragraphs:
        score += 20
    elif line_count >= 5 and avg_line_length > 50:
        score += 10  # Partial credit for decent structure
    
    # Line count contribution (up to 20 points)
    score += min(line_count / 10, 20)
    
    return {
        "length": length,
        "line_count": line_count,
        "density": density,
        "avg_line_length": avg_line_length,
        "has_paragraphs": has_paragraphs,
        "quality_score": min(score, 100),
    }
