#!/usr/bin/env python3
"""
Report Quality Analyzer for Primr
Analyzes generated reports for completeness, citations, and quality metrics.
"""

import argparse
import re
from pathlib import Path

# Writer-facing counterpart to ``scan_scaffolding_leakage``: prose guidance that
# tells the long-form writer/regeneration prompts NOT to emit the markers this
# module flags at ship time. Co-located with the scanner on purpose — every
# category ``scan_scaffolding_leakage`` detects must be named here so the upstream
# instruction and the downstream gate cannot drift. Parity is enforced by
# tests/test_qa/test_report_analyzer_deterministic.py::TestScaffoldingProhibitionParity.
SCAFFOLDING_PROHIBITION_GUIDANCE = (
    "SCAFFOLDING (never leak internal pipeline markers into the prose):\n"
    "- Do NOT reference the analysis workbook with a bracket marker such as "
    "[workbook], [Analysis Workbook], or [Analysis: ...]. Fold the analysis into the "
    "narrative as plain prose.\n"
    "- Do NOT use bracketed cross-references such as [cross-ref ...] or [see ## ...]. "
    'Refer to other sections in prose instead ("as noted in the Executive Summary").\n'
    "- Citations must be numeric only: [cite: N]. NEVER write a labeled citation such "
    "as [cite: workbook] or [cite: internal] — if you have no source number, state the "
    "claim as prose and label its confidence (Reported/Estimated/Hypothesis).\n"
    '- Write the "What to validate:" line as plain text — never bold, italic, or '
    "bulleted. **What to validate:** is a leak, not a label."
)


def scan_scaffolding_leakage(content: str) -> dict:
    """Scan a report string for leaked internal scaffolding markers.

    Pure, file-independent counterpart to
    ``ReportAnalyzer.analyze_scaffolding_leakage`` so the same detection logic
    can back both the QA scorecard and the ship-time artifact gate
    (``primr.output.artifact_validation``). Strategic reports should read as
    deliverables, not internal template machinery; this flags markers the
    writer pipeline should have stripped but didn't: bare ``[workbook]`` /
    ``[cross-ref ...]`` references, bold-wrapped ``**What to validate:**`` lines
    that survived normalization, and informal (non-numeric) ``[cite: label]``
    markers.

    A non-zero ``total_leaked`` is a shipping-artifact regression, not a
    content-quality issue.
    """
    # Cross-ref markers: colon-separated, space-separated, or bare. Inner scan
    # length-bounded (was [^\]]*) so an attacker-shaped report full of unclosed
    # "[cross-ref " markers can't drive quadratic regex work — same fix as
    # _clean_fast_report_output.
    cross_ref_count = len(
        re.findall(r"\[cross-ref(?:[\s:][^\]]{0,200})?\]", content, re.IGNORECASE)
    )

    # Workbook markers: bare, plus ":", " ", and "§" separated forms.
    workbook_count = len(re.findall(r"\[workbook(?:[\s:§][^\]]{0,200})?\]", content, re.IGNORECASE))

    # Bold-wrapped instruction-style "What to validate:" lines that survived the
    # writer-side normalization (the canonical form is plain text).
    bold_validate_count = len(
        re.findall(
            r"^\s*\*{1,2}What to validate\b[^\n]*",
            content,
            re.MULTILINE | re.IGNORECASE,
        )
    )

    # Internal cite labels that should never ship: [cite: workbook], [cite: bbb],
    # etc. Numeric cites and URL-bearing cites are fine. Inner scan is
    # length-bounded and excludes "[" (was the unbounded "[a-z]+[^\]]*") so an
    # attacker-shaped report full of unclosed "[cite: a" markers can't drive
    # quadratic regex work — same fix already applied to the cross-ref/workbook
    # patterns above.
    informal_cite_count = len(
        re.findall(r"\[cite:\s{0,10}(?!\d|https?:)[a-z][^\[\]\n]{0,100}\]", content, re.IGNORECASE)
    )

    total = cross_ref_count + workbook_count + bold_validate_count + informal_cite_count

    return {
        "cross_ref_markers": cross_ref_count,
        "workbook_markers": workbook_count,
        "bare_bold_validate": bold_validate_count,
        "informal_cite_markers": informal_cite_count,
        "total_leaked": total,
        "clean": total == 0,
    }


def scan_citation_integrity(content: str) -> dict:
    """Scan a report string for dangling inline citations.

    Citation integrity = every inline ``[cite: N]`` reference resolves to a
    source defined in the Sources/References/Citations appendix. A dangling
    citation (``[cite: 7]`` with no source 7) is a shipping-artifact integrity
    violation, not a content-quality issue — it makes the deliverable look
    broken. This is the deterministic backstop behind the upstream LLM citation
    repair, which keeps the original (possibly still-dangling) report when it
    cannot reach zero missing citations.

    Pure / file-independent counterpart used by the ship-time artifact gate
    (``primr.output.artifact_validation``). Deliberately a touch more lenient
    than ``ReportAnalyzer.analyze_citations`` on appendix-header matching
    (allows ``## Sources Consulted`` etc.) so it does not *false-block* a real
    report — a ship gate should err toward shipping, not toward withholding a
    clean deliverable.

    Returns counts plus the sorted list of unresolved citation numbers.
    """
    # Inline references, including grouped forms like "[cite: 1, 2]".
    used: set[int] = set()
    for group in re.findall(r"\[cite:\s*(\d+(?:\s*,\s*\d+)*)\]", content, re.IGNORECASE):
        for raw in group.split(","):
            raw = raw.strip()
            if raw.isdigit():
                used.add(int(raw))

    # Find the LAST Sources/References/Citations/Bibliography heading and treat
    # everything from there to the end as the appendix (lenient: allow trailing
    # words like "Sources Consulted"). Numbers defined there are "resolved".
    appendix_starts = [
        m.start()
        for m in re.finditer(
            r"^#{1,6}\s+(?:Sources|References|Citations|Bibliography)\b.*$",
            content,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    ]
    has_bibliography = bool(appendix_starts)
    defined: set[int] = set()
    if has_bibliography:
        appendix = content[appendix_starts[-1] :]
        defined = {int(n) for n in re.findall(r"\[cite:\s*(\d+)\]", appendix, re.IGNORECASE)}

    missing = sorted(used - defined)
    return {
        "inline_citations": len(used),
        "defined_citations": len(defined),
        "has_bibliography": has_bibliography,
        "missing_citations": missing,
        "missing_count": len(missing),
        "clean": len(missing) == 0,
    }


def scan_section_structure(content: str) -> dict:
    """Scan a report string for unambiguous structural defects.

    Two defect classes, both of which always indicate a broken deliverable:
    - **duplicate top-level (``##``) headings** — a merge/regeneration artifact
      that produces two sections with the same title;
    - **empty sections** — a ``##`` heading with no body content before the next
      heading or end of document (e.g. a suppressed section whose heading was
      left behind).

    Deliberately does **not** check "required sections present": that is
    report-type-dependent and heuristic (a report may cover SWOT-style content
    under a differently named heading), so it is too false-positive-prone to
    block shipping on. That signal stays in ``ReportAnalyzer.analyze_structure``
    for QA scoring. Pure / file-independent counterpart used by the ship-time
    artifact gate.

    ``total_defects`` counts extra duplicate occurrences (occurrences beyond the
    first) plus empty sections.
    """
    heading_re = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(content))
    titles = [m.group(1).strip() for m in matches]

    counts: dict[str, int] = {}
    for title in titles:
        key = title.lower()
        counts[key] = counts.get(key, 0) + 1
    duplicate_titles = sorted({t for t in titles if counts[t.lower()] > 1}, key=str.lower)
    extra_duplicate_occurrences = sum(c - 1 for c in counts.values() if c > 1)

    empty_sections: list[str] = []
    for i, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        if not content[body_start:body_end].strip():
            empty_sections.append(titles[i])

    total = extra_duplicate_occurrences + len(empty_sections)
    return {
        "duplicate_headings": duplicate_titles,
        "empty_sections": empty_sections,
        "total_defects": total,
        "clean": total == 0,
    }


class ReportAnalyzer:
    def __init__(self, report_path: str):
        self.report_path = Path(report_path)
        self.content = self._load_content()
        self.report_type = self._detect_report_type()

    def _detect_report_type(self) -> str:
        """Detect the type of report based on content and filename."""
        filename = self.report_path.name.lower()
        content_lower = self.content.lower()

        if "ai_strategy" in filename or "ai strategy" in content_lower:
            return "ai_strategy"
        elif "strategic_overview" in filename or "company overview" in content_lower:
            return "strategic_overview"
        else:
            return "unknown"

    def _load_content(self) -> str:
        """Load report content from file."""
        try:
            with open(self.report_path, encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            raise FileNotFoundError(f"Could not load report: {e}") from e

    def analyze_citations(self) -> dict:
        """Analyze citation quality and completeness."""
        # Find all citation references in text
        cite_refs = re.findall(r"\[cite:\s*(\d+(?:,\s*\d+)*)\]", self.content)
        all_cite_numbers = set()
        for ref in cite_refs:
            numbers = [int(n.strip()) for n in ref.split(",")]
            all_cite_numbers.update(numbers)

        # Check for citations section
        has_citations_section = bool(
            re.search(r"^##\s+(Citations|References|Sources)", self.content, re.MULTILINE)
        )

        # Find defined citations in bibliography section only (not the whole report)
        defined_citations = set()
        if has_citations_section:
            bib_match = re.search(
                r"^##\s+(?:Citations|References|Sources)\s*$", self.content, re.MULTILINE
            )
            if bib_match:
                bibliography_text = self.content[bib_match.start() :]
                cite_definitions = re.findall(r"\[cite:\s*(\d+)\]", bibliography_text)
                defined_citations = {int(c) for c in cite_definitions}

        # Find missing citations
        missing_citations = all_cite_numbers - defined_citations

        return {
            "total_references": len(cite_refs),
            "unique_citations": len(all_cite_numbers),
            "has_bibliography": has_citations_section,
            "defined_citations": len(defined_citations),
            "missing_citations": sorted(missing_citations),
            "citation_coverage": len(defined_citations) / len(all_cite_numbers)
            if all_cite_numbers
            else 0,
            "all_cited_numbers": sorted(all_cite_numbers),
        }

    def analyze_structure(self) -> dict:
        """Analyze report structure and completeness.

        Uses report-type-aware required section checklists:
        - strategic_overview: business-oriented sections (Executive Summary, Products, etc.)
        - ai_strategy: strategy-oriented sections (Executive Summary, Recommendations, etc.)
        - unknown: minimal common sections
        """
        # Count sections
        sections = re.findall(r"^##\s+(.+)$", self.content, re.MULTILINE)
        subsections = re.findall(r"^###\s+(.+)$", self.content, re.MULTILINE)

        # Check for duplicate section titles (case-insensitive)
        section_counts = {}
        for section in sections:
            section_lower = section.lower().strip()
            section_counts[section_lower] = section_counts.get(section_lower, 0) + 1

        duplicate_sections = {title: count for title, count in section_counts.items() if count > 1}

        # Report-type-aware required sections
        if self.report_type == "strategic_overview":
            key_sections = [
                "Executive Summary",
                "Products and Services",
                "Target Customers",
                "Competitive",
                "Financial",
                "SWOT",
                "Strategic",
            ]
        elif self.report_type == "ai_strategy":
            key_sections = [
                "Executive Summary",
                "Current State",
                "Recommendations",
                "Implementation",
                "Risk",
            ]
        else:
            key_sections = [
                "Executive Summary",
                "Key Insights",
                "Sources",
            ]

        found_sections = []
        for section in sections:
            for key in key_sections:
                if key.lower() in section.lower():
                    found_sections.append(key)
                    break

        return {
            "total_sections": len(sections),
            "total_subsections": len(subsections),
            "section_titles": sections,
            "duplicate_sections": duplicate_sections,
            "key_sections_found": found_sections,
            "key_sections_missing": [k for k in key_sections if k not in found_sections],
            "report_type": self.report_type,
        }

    def analyze_content_quality(self) -> dict:
        """Analyze content quality indicators."""
        # Word count
        word_count = len(self.content.split())

        # Page estimate (assuming ~500 words per page)
        estimated_pages = word_count / 500

        # Count hypothesis statements
        hypothesis_count = len(re.findall(r"\(Hypothesis\)", self.content, re.IGNORECASE))

        # Count confidence indicators
        confidence_indicators = {
            "confirmed": len(re.findall(r"\(Confirmed[^)]*\)", self.content, re.IGNORECASE)),
            "reported": len(re.findall(r"\(Reported[^)]*\)", self.content, re.IGNORECASE)),
            "estimated": len(re.findall(r"\(Estimated[^)]*\)", self.content, re.IGNORECASE)),
            "hypothesis": hypothesis_count,
        }

        # Check for strategic frameworks
        frameworks = {
            "SWOT": bool(re.search(r"SWOT", self.content, re.IGNORECASE)),
            "Porter": bool(re.search(r"Porter.*Five Forces", self.content, re.IGNORECASE)),
            "Value Chain": bool(re.search(r"Value Chain", self.content, re.IGNORECASE)),
        }

        return {
            "word_count": word_count,
            "estimated_pages": round(estimated_pages, 1),
            "confidence_indicators": confidence_indicators,
            "total_confidence_statements": sum(confidence_indicators.values()),
            "strategic_frameworks": frameworks,
            "frameworks_used": sum(frameworks.values()),
        }

    def analyze_urls_and_sources(self) -> dict:
        """Analyze URL references and source quality."""
        # Find all URLs
        urls = re.findall(r"https?://[^\s\)]+", self.content)

        # Derive the most-cited host as a generic "primary host" counter, since
        # the analyzer doesn't know the company's canonical domain at runtime.
        # Skip linkedin/news domains so the count reflects first-party citations
        # rather than the dominant aggregator on the page.
        from collections import Counter
        from urllib.parse import urlparse

        news_domains = ("reuters", "bloomberg", "techcrunch", "prnewswire")
        host_counts: Counter[str] = Counter()
        for url in urls:
            try:
                host = (urlparse(url).hostname or "").lower().removeprefix("www.")
            except ValueError:
                continue
            if not host or "linkedin.com" in host or any(n in host for n in news_domains):
                continue
            host_counts[host] += 1
        primary_host = host_counts.most_common(1)[0][0] if host_counts else ""
        primary_host_count = host_counts.get(primary_host, 0)

        url_categories = {
            "primary_host": primary_host_count,
            "news_sources": len(
                [u for u in urls if any(news in u.lower() for news in news_domains)]
            ),
            "linkedin": len([u for u in urls if "linkedin.com" in u.lower()]),
            "other": 0,
        }
        url_categories["other"] = len(urls) - sum(url_categories.values())

        return {
            "total_urls": len(urls),
            "unique_urls": len(set(urls)),
            "primary_host": primary_host,
            "url_categories": url_categories,
            "sample_urls": urls[:5] if urls else [],
        }

    def analyze_scaffolding_leakage(self) -> dict:
        """Detect internal scaffolding that leaked into the shipping artifact.

        Thin instance wrapper over the module-level
        :func:`scan_scaffolding_leakage`, which holds the single source of truth
        for the detection patterns (shared with the ship-time artifact gate).
        """
        return scan_scaffolding_leakage(self.content)

    def analyze_hypothesis_coverage(self) -> dict:
        """Analyze hypothesis framing quality.

        Counts explicit (Hypothesis) labels and validation phrases like
        'we hypothesize', 'to validate', 'worth validating'. Thresholds
        vary by report type.
        """
        labels = re.findall(r"\(Hypothesis\)", self.content, re.IGNORECASE)

        validation_phrases = [
            r"we hypothesize",
            r"to validate",
            r"worth validating",
            r"hypothesis to test",
            r"requires validation",
        ]
        phrase_count = 0
        for phrase in validation_phrases:
            phrase_count += len(re.findall(phrase, self.content, re.IGNORECASE))

        total_signals = len(labels) + phrase_count

        thresholds = {
            "strategic_overview": 5,
            "ai_strategy": 3,
        }
        threshold = thresholds.get(self.report_type, 2)

        return {
            "hypothesis_labels": len(labels),
            "validation_phrases": phrase_count,
            "total_signals": total_signals,
            "threshold": threshold,
            "meets_threshold": total_signals >= threshold,
        }

    def analyze_confidence_labels(self) -> dict:
        """Analyze epistemic confidence labels and hedging language.

        Counts all four epistemic labels: (Confirmed), (Reported),
        (Estimated), (Hypothesis). Also counts hedging phrases from
        epistemic_rules.yaml.
        """
        label_counts = {
            "confirmed": len(re.findall(r"\(Confirmed[^)]*\)", self.content, re.IGNORECASE)),
            "reported": len(re.findall(r"\(Reported[^)]*\)", self.content, re.IGNORECASE)),
            "estimated": len(re.findall(r"\(Estimated[^)]*\)", self.content, re.IGNORECASE)),
            "hypothesis": len(re.findall(r"\(Hypothesis\)", self.content, re.IGNORECASE)),
        }

        total_labels = sum(label_counts.values())

        # Hedging phrases from epistemic_rules.yaml
        hedging_phrases = [
            r"appears to",
            r"worth exploring",
            r"we\'d want to validate",
            r"based on available evidence",
            r"signals suggest",
        ]
        hedging_count = 0
        for phrase in hedging_phrases:
            hedging_count += len(re.findall(phrase, self.content, re.IGNORECASE))

        thresholds = {
            "strategic_overview": 8,
            "ai_strategy": 5,
        }
        threshold = thresholds.get(self.report_type, 3)

        return {
            "label_counts": label_counts,
            "total_labels": total_labels,
            "hedging_phrases": hedging_count,
            "threshold": threshold,
            "meets_threshold": total_labels >= threshold,
        }

    def analyze_section_lengths(self) -> dict:
        """Analyze per-section word counts and flag truncated sections.

        Splits content by ## headings and computes word count per section.
        Sections with fewer than 50 words are flagged as truncated.
        """
        # Split by ## headings
        parts = re.split(r"^##\s+", self.content, flags=re.MULTILINE)

        sections = []
        truncated = []

        for part in parts[1:]:  # skip preamble before first ##
            lines = part.split("\n", 1)
            title = lines[0].strip()
            body = lines[1] if len(lines) > 1 else ""
            word_count = len(body.split())

            sections.append(
                {
                    "title": title,
                    "word_count": word_count,
                }
            )

            if word_count < 50:
                truncated.append(title)

        return {
            "sections": sections,
            "truncated_sections": truncated,
            "truncated_count": len(truncated),
        }

    def analyze_citation_density(self) -> dict:
        """Analyze citation density per 1000 words.

        Counts [cite: N] and [Source: patterns. Thresholds:
        3.0 for strategic_overview, 2.0 for ai_strategy.
        """
        cite_pattern = re.findall(r"\[cite:\s*\d+", self.content)
        source_pattern = re.findall(r"\[Source:", self.content, re.IGNORECASE)

        total_citations = len(cite_pattern) + len(source_pattern)
        word_count = len(self.content.split())

        density = (total_citations / word_count * 1000) if word_count > 0 else 0.0

        thresholds = {
            "strategic_overview": 3.0,
            "ai_strategy": 2.0,
        }
        threshold = thresholds.get(self.report_type, 1.0)

        return {
            "total_citations": total_citations,
            "word_count": word_count,
            "density_per_1000_words": round(density, 2),
            "threshold": threshold,
            "meets_threshold": density >= threshold,
        }

    def generate_report(self) -> str:
        """Generate a comprehensive quality report."""
        citations = self.analyze_citations()
        structure = self.analyze_structure()
        quality = self.analyze_content_quality()
        sources = self.analyze_urls_and_sources()
        hypothesis = self.analyze_hypothesis_coverage()
        confidence = self.analyze_confidence_labels()
        section_lengths = self.analyze_section_lengths()
        citation_density = self.analyze_citation_density()
        leakage = self.analyze_scaffolding_leakage()

        key_section_total = len(structure["key_sections_found"]) + len(
            structure["key_sections_missing"]
        )

        report = f"""
# Report Quality Analysis: {self.report_path.name}

## Overall Metrics
- **File Size**: {self.report_path.stat().st_size:,} bytes
- **Word Count**: {quality["word_count"]:,} words
- **Estimated Pages**: {quality["estimated_pages"]} pages
- **Total Sections**: {structure["total_sections"]} main sections, {structure["total_subsections"]} subsections
- **Report Type**: {structure["report_type"]}

## Citation Analysis
- **Citation References**: {citations["total_references"]} references to {citations["unique_citations"]} unique citations
- **Bibliography Present**: {"Yes" if citations["has_bibliography"] else "No"}
- **Citation Coverage**: {citations["citation_coverage"]:.1%} ({citations["defined_citations"]}/{citations["unique_citations"]} citations defined)
- **Citation Density**: {citation_density["density_per_1000_words"]}/1000 words (threshold: {citation_density["threshold"]})
"""

        if citations["missing_citations"]:
            report += f"- **Missing Citations**: {citations['missing_citations']}\n"
        else:
            report += "- **All Citations Defined**\n"

        report += f"""
## Structure Analysis
- **Key Sections Found**: {len(structure["key_sections_found"])}/{key_section_total}
  - Present: {", ".join(structure["key_sections_found"])}
"""

        if structure["key_sections_missing"]:
            report += f"  - Missing: {', '.join(structure['key_sections_missing'])}\n"

        # Report duplicate sections if any
        if structure["duplicate_sections"]:
            report += "\n**WARNING: DUPLICATE SECTIONS DETECTED:**\n"
            for title, count in structure["duplicate_sections"].items():
                report += f"  - '{title}' appears {count} times\n"
            report += "\n"

        # Report truncated sections
        if section_lengths["truncated_sections"]:
            report += f"\n**WARNING: {section_lengths['truncated_count']} TRUNCATED SECTIONS (< 50 words):**\n"
            for title in section_lengths["truncated_sections"]:
                report += f"  - {title}\n"
            report += "\n"

        # Report scaffolding leakage — markers that should have been stripped
        # before shipping. Surface counts only when something leaked, so clean
        # reports stay terse.
        if not leakage["clean"]:
            report += f"\n**WARNING: {leakage['total_leaked']} SCAFFOLDING LEAKS:**\n"
            if leakage["workbook_markers"]:
                report += f"  - [workbook] markers: {leakage['workbook_markers']}\n"
            if leakage["cross_ref_markers"]:
                report += f"  - [cross-ref ...] markers: {leakage['cross_ref_markers']}\n"
            if leakage["bare_bold_validate"]:
                report += (
                    f"  - bold-wrapped 'What to validate:' lines: {leakage['bare_bold_validate']}\n"
                )
            if leakage["informal_cite_markers"]:
                report += (
                    f"  - informal [cite: label] markers: {leakage['informal_cite_markers']}\n"
                )
            report += "\n"

        report += f"""
## Content Quality
- **Strategic Frameworks**: {quality["frameworks_used"]}/3 frameworks used
  - SWOT Analysis: {"Yes" if quality["strategic_frameworks"]["SWOT"] else "No"}
  - Porter's Five Forces: {"Yes" if quality["strategic_frameworks"]["Porter"] else "No"}
  - Value Chain Analysis: {"Yes" if quality["strategic_frameworks"]["Value Chain"] else "No"}

- **Confidence Labels**: {confidence["total_labels"]} total
  - Confirmed: {confidence["label_counts"]["confirmed"]}
  - Reported: {confidence["label_counts"]["reported"]}
  - Estimated: {confidence["label_counts"]["estimated"]}
  - Hypothesis: {confidence["label_counts"]["hypothesis"]}
  - Hedging Phrases: {confidence["hedging_phrases"]}
  - Meets Threshold: {"Yes" if confidence["meets_threshold"] else "No"} (need {confidence["threshold"]})

- **Hypothesis Framing**: {hypothesis["total_signals"]} signals
  - Labels: {hypothesis["hypothesis_labels"]}, Phrases: {hypothesis["validation_phrases"]}
  - Meets Threshold: {"Yes" if hypothesis["meets_threshold"] else "No"} (need {hypothesis["threshold"]})

## Source Analysis
- **Total URLs**: {sources["total_urls"]} ({sources["unique_urls"]} unique)
- **Primary Host**: {sources.get("primary_host") or "(none detected)"}
- **Source Breakdown**:
  - Primary Host: {sources["url_categories"]["primary_host"]}
  - News Sources: {sources["url_categories"]["news_sources"]}
  - LinkedIn: {sources["url_categories"]["linkedin"]}
  - Other: {sources["url_categories"]["other"]}

## Quality Score
"""

        # Calculate overall quality score based on report type
        if self.report_type == "ai_strategy":
            score_components = {
                "Citations": min(20, citations["citation_coverage"] * 16 + 4),
                "Structure": min(20, len(structure["key_sections_found"]) * 4),
                "Frameworks": 10,
                "Confidence": min(20, quality["total_confidence_statements"] * 2),
                "Hypothesis Framing": min(15, hypothesis["total_signals"] * 3),
                "Citation Density": min(15, citation_density["density_per_1000_words"] * 5),
            }
        else:
            score_components = {
                "Citations": 20
                if citations["citation_coverage"] >= 0.9
                else int(citations["citation_coverage"] * 20),
                "Structure": min(20, len(structure["key_sections_found"]) * 3),
                "Frameworks": min(20, quality["frameworks_used"] * 7),
                "Confidence": min(20, quality["total_confidence_statements"] * 0.5),
                "Hypothesis Framing": min(10, hypothesis["total_signals"] * 2),
                "Citation Density": min(10, citation_density["density_per_1000_words"] * 3),
            }

        # Penalize duplicate sections
        if structure["duplicate_sections"]:
            duplicate_penalty = len(structure["duplicate_sections"]) * 5
            score_components["Structure"] = max(
                0, score_components["Structure"] - duplicate_penalty
            )

        # Penalize truncated sections
        if section_lengths["truncated_sections"]:
            truncation_penalty = min(10, section_lengths["truncated_count"] * 5)
            score_components["Structure"] = max(
                0, score_components["Structure"] - truncation_penalty
            )

        total_score = min(100, sum(score_components.values()))

        for component, score in score_components.items():
            report += f"- {component}: {score:.0f}\n"

        report += f"\n**Overall Quality Score: {total_score:.0f}/100**\n"

        if total_score >= 90:
            report += "**Excellent** - Professional quality report\n"
        elif total_score >= 75:
            report += "**Good** - High quality with minor improvements needed\n"
        elif total_score >= 60:
            report += "**Fair** - Acceptable but needs improvement\n"
        else:
            report += "**Poor** - Significant quality issues\n"

        return report


def main():
    parser = argparse.ArgumentParser(description="Analyze Primr report quality")
    parser.add_argument("report_path", help="Path to the report file to analyze")
    parser.add_argument("--output", "-o", help="Output file for analysis report")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    args = parser.parse_args()

    try:
        analyzer = ReportAnalyzer(args.report_path)

        if args.format == "json":
            import json

            result = {
                "citations": analyzer.analyze_citations(),
                "structure": analyzer.analyze_structure(),
                "quality": analyzer.analyze_content_quality(),
                "sources": analyzer.analyze_urls_and_sources(),
            }
            output = json.dumps(result, indent=2)
        else:
            output = analyzer.generate_report()

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Analysis saved to {args.output}")
        else:
            print(output)

    except Exception as e:
        print(f"Error analyzing report: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
