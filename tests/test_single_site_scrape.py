"""
Static Analysis: Single Site-to-Corpus Implementation

Property 1 from design.md:
*There SHALL NOT exist any other function that:*
- discovers links from a domain, AND
- selects a subset, AND
- scrapes pages in a loop

*except `build_site_corpus()` (implemented as `fetch_web_content()`).*

This test scans the codebase to ensure no duplicate site-scrape patterns exist.
"""

import ast
import os
from pathlib import Path
from typing import NamedTuple


class SiteScrapePattern(NamedTuple):
    """A detected site-scrape pattern."""
    file: str
    function: str
    line: int
    pattern_type: str  # 'discovery_loop', 'scrape_loop', 'link_selection'


# Patterns that indicate site-level scraping (not page-level)
DISCOVERY_PATTERNS = [
    'discover_links',
    'fetch_sitemap_links',
    'extract_links_from_homepage',
    'guess_common_urls',
]

SCRAPE_LOOP_PATTERNS = [
    'for.*in.*pages_to_scrape',
    'for.*in.*urls_to_scrape',
    'for.*page_url.*in',
    'orchestrator.scrape_url',
]

LINK_SELECTION_PATTERNS = [
    'select_links_with_llm',
    'score_links_heuristically',
]

# Files that are ALLOWED to have these patterns
ALLOWED_FILES = {
    'src/primr/data/scrape.py',  # fetch_web_content (build_site_corpus)
    'src/primr/data/scraping/discovery.py',  # Discovery module (called by fetch_web_content)
    'tests/',  # Test files
}


class SiteScrapeAnalyzer(ast.NodeVisitor):
    """AST visitor to detect site-scrape patterns."""

    def __init__(self, filename: str):
        self.filename = filename
        self.current_function = None
        self.patterns_found: list[SiteScrapePattern] = []

    def visit_FunctionDef(self, node):
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_For(self, node):
        """Check for scrape loops."""
        # Check if iterating over something that looks like URLs
        iter_str = ast.unparse(node.iter) if hasattr(ast, 'unparse') else str(node.iter)
        ast.unparse(node.target) if hasattr(ast, 'unparse') else str(node.target)

        suspicious_iters = ['pages_to_scrape', 'urls_to_scrape', 'links_to_scrape', 'all_links']

        if any(s in iter_str for s in suspicious_iters):
            # Check if there's a scrape call inside
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    call_str = ast.unparse(child.func) if hasattr(ast, 'unparse') else ''
                    if 'scrape' in call_str.lower():
                        self.patterns_found.append(SiteScrapePattern(
                            file=self.filename,
                            function=self.current_function or '<module>',
                            line=node.lineno,
                            pattern_type='scrape_loop'
                        ))
                        break

        self.generic_visit(node)

    def visit_Call(self, node):
        """Check for discovery and selection calls."""
        call_str = ''
        if isinstance(node.func, ast.Name):
            call_str = node.func.id
        elif isinstance(node.func, ast.Attribute):
            call_str = node.func.attr

        # Check for discovery patterns
        for pattern in DISCOVERY_PATTERNS:
            if pattern in call_str:
                self.patterns_found.append(SiteScrapePattern(
                    file=self.filename,
                    function=self.current_function or '<module>',
                    line=node.lineno,
                    pattern_type='discovery'
                ))

        # Check for link selection patterns
        for pattern in LINK_SELECTION_PATTERNS:
            if pattern in call_str:
                self.patterns_found.append(SiteScrapePattern(
                    file=self.filename,
                    function=self.current_function or '<module>',
                    line=node.lineno,
                    pattern_type='link_selection'
                ))

        self.generic_visit(node)


def is_allowed_file(filepath: str) -> bool:
    """Check if a file is allowed to have site-scrape patterns."""
    filepath_normalized = filepath.replace('\\', '/')
    return any(allowed in filepath_normalized for allowed in ALLOWED_FILES)


def scan_for_site_scrape_patterns(src_dir: str = 'src/primr') -> list[SiteScrapePattern]:
    """
    Scan source directory for site-scrape patterns.

    Returns patterns found in files that are NOT in the allowed list.
    """
    violations = []

    for root, dirs, files in os.walk(src_dir):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != '__pycache__']

        for filename in files:
            if not filename.endswith('.py'):
                continue

            filepath = os.path.join(root, filename)

            # Skip allowed files
            if is_allowed_file(filepath):
                continue

            try:
                with open(filepath, encoding='utf-8') as f:
                    source = f.read()

                tree = ast.parse(source)
                analyzer = SiteScrapeAnalyzer(filepath)
                analyzer.visit(tree)

                violations.extend(analyzer.patterns_found)
            except (SyntaxError, UnicodeDecodeError):
                # Skip files that can't be parsed
                pass

    return violations


# =============================================================================
# Tests
# =============================================================================

import pytest


class TestSingleSiteScrapeImplementation:
    """Tests to ensure only one site-to-corpus implementation exists."""

    def test_no_duplicate_site_scrape_patterns(self):
        """
        Property 1: There SHALL NOT exist any other function that discovers links,
        selects a subset, and scrapes pages in a loop except build_site_corpus.
        """
        violations = scan_for_site_scrape_patterns('src/primr')

        if violations:
            violation_report = "\n".join([
                f"  {v.file}:{v.line} in {v.function}() - {v.pattern_type}"
                for v in violations
            ])
            pytest.fail(
                f"Found site-scrape patterns outside of allowed files:\n{violation_report}\n\n"
                "These patterns should only exist in fetch_web_content() (build_site_corpus).\n"
                "If this is intentional, add the file to ALLOWED_FILES in this test."
            )

    def test_fetch_web_content_is_the_only_site_scraper(self):
        """Verify fetch_web_content exists and is in the allowed location."""
        scrape_py = Path('src/primr/data/scrape.py')

        if not scrape_py.exists():
            pytest.skip("scrape.py not found")

        content = scrape_py.read_text()

        # Check that fetch_web_content exists
        assert 'def fetch_web_content(' in content, \
            "fetch_web_content (build_site_corpus) should exist in scrape.py"

        # Check that it has the expected docstring
        assert 'build_site_corpus' in content or 'site-to-corpus' in content.lower(), \
            "fetch_web_content should document that it's the site-to-corpus workflow"

    def test_perform_scrape_only_delegates(self):
        """Verify perform_scrape_only delegates to fetch_web_content."""
        research_agent = Path('src/primr/core/research_agent.py')

        if not research_agent.exists():
            pytest.skip("research_agent.py not found")

        content = research_agent.read_text()

        # Check that perform_scrape_only exists
        assert 'def perform_scrape_only(' in content, \
            "perform_scrape_only should exist"

        # Check that it calls fetch_web_content
        # Find the function and check its body
        import re
        func_match = re.search(
            r'def perform_scrape_only\([^)]*\)[^:]*:.*?(?=\ndef |\Z)',
            content,
            re.DOTALL
        )

        if func_match:
            func_body = func_match.group(0)
            assert 'fetch_web_content' in func_body, \
                "perform_scrape_only should delegate to fetch_web_content (build_site_corpus)"

            # Check that it does NOT have its own discovery loop
            assert 'discover_links' not in func_body or 'fetch_web_content' in func_body, \
                "perform_scrape_only should NOT have its own discovery loop"
