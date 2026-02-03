#!/usr/bin/env python3
"""
Report Quality Analyzer for Primr
Analyzes generated reports for completeness, citations, and quality metrics.
"""

import argparse
import re
from pathlib import Path


class ReportAnalyzer:
    def __init__(self, report_path: str):
        self.report_path = Path(report_path)
        self.content = self._load_content()
        self.report_type = self._detect_report_type()

    def _detect_report_type(self) -> str:
        """Detect the type of report based on content and filename."""
        filename = self.report_path.name.lower()
        content_lower = self.content.lower()

        if 'ai_strategy' in filename or 'ai strategy' in content_lower:
            return 'ai_strategy'
        elif 'strategic_overview' in filename or 'company overview' in content_lower:
            return 'strategic_overview'
        else:
            return 'unknown'

    def _load_content(self) -> str:
        """Load report content from file."""
        try:
            with open(self.report_path, encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            raise FileNotFoundError(f"Could not load report: {e}") from e

    def analyze_citations(self) -> dict:
        """Analyze citation quality and completeness."""
        # Find all citation references in text
        cite_refs = re.findall(r'\[cite:\s*(\d+(?:,\s*\d+)*)\]', self.content)
        all_cite_numbers = set()
        for ref in cite_refs:
            numbers = [int(n.strip()) for n in ref.split(',')]
            all_cite_numbers.update(numbers)

        # Check for citations section
        has_citations_section = bool(re.search(r'^##\s+(Citations|References|Sources)', self.content, re.MULTILINE))

        # Find defined citations in bibliography
        defined_citations = set()
        if has_citations_section:
            cite_definitions = re.findall(r'\[cite:\s*(\d+)\]', self.content)
            defined_citations = {int(c) for c in cite_definitions}

        # Find missing citations
        missing_citations = all_cite_numbers - defined_citations

        return {
            'total_references': len(cite_refs),
            'unique_citations': len(all_cite_numbers),
            'has_bibliography': has_citations_section,
            'defined_citations': len(defined_citations),
            'missing_citations': sorted(missing_citations),
            'citation_coverage': len(defined_citations) / len(all_cite_numbers) if all_cite_numbers else 0,
            'all_cited_numbers': sorted(all_cite_numbers)
        }

    def analyze_structure(self) -> dict:
        """Analyze report structure and completeness."""
        # Count sections
        sections = re.findall(r'^##\s+(.+)$', self.content, re.MULTILINE)
        subsections = re.findall(r'^###\s+(.+)$', self.content, re.MULTILINE)

        # Check for duplicate section titles (case-insensitive)
        section_counts = {}
        for section in sections:
            section_lower = section.lower().strip()
            section_counts[section_lower] = section_counts.get(section_lower, 0) + 1

        duplicate_sections = {title: count for title, count in section_counts.items() if count > 1}

        # Check for key strategic sections
        key_sections = [
            'Executive Summary',
            'Products and Services',
            'Target Customers',
            'Competitive',
            'Financial',
            'SWOT',
            'Strategic'
        ]

        found_sections = []
        for section in sections:
            for key in key_sections:
                if key.lower() in section.lower():
                    found_sections.append(key)
                    break

        return {
            'total_sections': len(sections),
            'total_subsections': len(subsections),
            'section_titles': sections,
            'duplicate_sections': duplicate_sections,
            'key_sections_found': found_sections,
            'key_sections_missing': [k for k in key_sections if k not in found_sections]
        }

    def analyze_content_quality(self) -> dict:
        """Analyze content quality indicators."""
        # Word count
        word_count = len(self.content.split())

        # Page estimate (assuming ~500 words per page)
        estimated_pages = word_count / 500

        # Count hypothesis statements
        hypothesis_count = len(re.findall(r'\(Hypothesis\)', self.content, re.IGNORECASE))

        # Count confidence indicators
        confidence_indicators = {
            'confirmed': len(re.findall(r'\(Confirmed[^)]*\)', self.content, re.IGNORECASE)),
            'reported': len(re.findall(r'\(Reported[^)]*\)', self.content, re.IGNORECASE)),
            'estimated': len(re.findall(r'\(Estimated[^)]*\)', self.content, re.IGNORECASE)),
            'hypothesis': hypothesis_count
        }

        # Check for strategic frameworks
        frameworks = {
            'SWOT': bool(re.search(r'SWOT', self.content, re.IGNORECASE)),
            'Porter': bool(re.search(r'Porter.*Five Forces', self.content, re.IGNORECASE)),
            'Value Chain': bool(re.search(r'Value Chain', self.content, re.IGNORECASE))
        }

        return {
            'word_count': word_count,
            'estimated_pages': round(estimated_pages, 1),
            'confidence_indicators': confidence_indicators,
            'total_confidence_statements': sum(confidence_indicators.values()),
            'strategic_frameworks': frameworks,
            'frameworks_used': sum(frameworks.values())
        }

    def analyze_urls_and_sources(self) -> dict:
        """Analyze URL references and source quality."""
        # Find all URLs
        urls = re.findall(r'https?://[^\s\)]+', self.content)

        # Categorize URLs
        url_categories = {
            'company_website': len([u for u in urls if 'mrisoftware.com' in u.lower()]),
            'news_sources': len([u for u in urls if any(news in u.lower() for news in ['reuters', 'bloomberg', 'techcrunch', 'prnewswire'])]),
            'linkedin': len([u for u in urls if 'linkedin.com' in u.lower()]),
            'other': 0
        }
        url_categories['other'] = len(urls) - sum(url_categories.values())

        return {
            'total_urls': len(urls),
            'unique_urls': len(set(urls)),
            'url_categories': url_categories,
            'sample_urls': urls[:5] if urls else []
        }

    def generate_report(self) -> str:
        """Generate a comprehensive quality report."""
        citations = self.analyze_citations()
        structure = self.analyze_structure()
        quality = self.analyze_content_quality()
        sources = self.analyze_urls_and_sources()

        report = f"""
# Report Quality Analysis: {self.report_path.name}

## Overall Metrics
- **File Size**: {self.report_path.stat().st_size:,} bytes
- **Word Count**: {quality['word_count']:,} words
- **Estimated Pages**: {quality['estimated_pages']} pages
- **Total Sections**: {structure['total_sections']} main sections, {structure['total_subsections']} subsections

## Citation Analysis
- **Citation References**: {citations['total_references']} references to {citations['unique_citations']} unique citations
- **Bibliography Present**: {'Yes' if citations['has_bibliography'] else 'No'}
- **Citation Coverage**: {citations['citation_coverage']:.1%} ({citations['defined_citations']}/{citations['unique_citations']} citations defined)
"""

        if citations['missing_citations']:
            report += f"- **Missing Citations**: {citations['missing_citations']}\n"
        else:
            report += "- **All Citations Defined**\n"

        report += f"""
## Structure Analysis
- **Key Strategic Sections Found**: {len(structure['key_sections_found'])}/7
  - Present: {', '.join(structure['key_sections_found'])}
"""

        if structure['key_sections_missing']:
            report += f"  - Missing: {', '.join(structure['key_sections_missing'])}\n"

        # Report duplicate sections if any
        if structure['duplicate_sections']:
            report += "\n**WARNING: DUPLICATE SECTIONS DETECTED:**\n"
            for title, count in structure['duplicate_sections'].items():
                report += f"  - '{title}' appears {count} times\n"
            report += "\n"

        report += f"""
## Content Quality
- **Strategic Frameworks**: {quality['frameworks_used']}/3 frameworks used
  - SWOT Analysis: {'Yes' if quality['strategic_frameworks']['SWOT'] else 'No'}
  - Porter's Five Forces: {'Yes' if quality['strategic_frameworks']['Porter'] else 'No'}
  - Value Chain Analysis: {'Yes' if quality['strategic_frameworks']['Value Chain'] else 'No'}

- **Confidence Indicators**: {quality['total_confidence_statements']} total statements
  - Confirmed: {quality['confidence_indicators']['confirmed']}
  - Reported: {quality['confidence_indicators']['reported']}
  - Estimated: {quality['confidence_indicators']['estimated']}
  - Hypothesis: {quality['confidence_indicators']['hypothesis']}

## Source Analysis
- **Total URLs**: {sources['total_urls']} ({sources['unique_urls']} unique)
- **Source Breakdown**:
  - Company Website: {sources['url_categories']['company_website']}
  - News Sources: {sources['url_categories']['news_sources']}
  - LinkedIn: {sources['url_categories']['linkedin']}
  - Other: {sources['url_categories']['other']}

## Quality Score
"""

        # Calculate overall quality score based on report type
        if self.report_type == 'ai_strategy':
            # AI Strategy reports focus more on recommendations and less on citations
            score_components = {
                'Citations': min(25, citations['citation_coverage'] * 20 + 5),  # More lenient
                'Structure': min(25, len(structure['key_sections_found']) * 2),  # Different expectations
                'Frameworks': 15,  # AI strategies don't need traditional business frameworks
                'Confidence': min(25, quality['total_confidence_statements'] * 2)  # Less emphasis on confidence statements
            }
        else:
            # Strategic Overview scoring (original logic)
            score_components = {
                'Citations': 25 if citations['citation_coverage'] >= 0.9 else int(citations['citation_coverage'] * 25),
                'Structure': min(25, len(structure['key_sections_found']) * 3.5),
                'Frameworks': quality['frameworks_used'] * 8,
                'Confidence': min(25, quality['total_confidence_statements'] * 0.5)
            }

        # Penalize duplicate sections
        if structure['duplicate_sections']:
            duplicate_penalty = len(structure['duplicate_sections']) * 5  # 5 points per duplicate
            score_components['Structure'] = max(0, score_components['Structure'] - duplicate_penalty)

        total_score = sum(score_components.values())

        for component, score in score_components.items():
            report += f"- {component}: {score:.0f}/25\n"

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
    parser = argparse.ArgumentParser(description='Analyze Primr report quality')
    parser.add_argument('report_path', help='Path to the report file to analyze')
    parser.add_argument('--output', '-o', help='Output file for analysis report')
    parser.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')

    args = parser.parse_args()

    try:
        analyzer = ReportAnalyzer(args.report_path)

        if args.format == 'json':
            import json
            result = {
                'citations': analyzer.analyze_citations(),
                'structure': analyzer.analyze_structure(),
                'quality': analyzer.analyze_content_quality(),
                'sources': analyzer.analyze_urls_and_sources()
            }
            output = json.dumps(result, indent=2)
        else:
            output = analyzer.generate_report()

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"Analysis saved to {args.output}")
        else:
            print(output)

    except Exception as e:
        print(f"Error analyzing report: {e}")
        return 1

    return 0

if __name__ == '__main__':
    exit(main())
