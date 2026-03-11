"""
Mode Equivalence Tests

Validates that scrape mode and full mode produce identical corpus outputs.
This is a critical correctness property: modes are stopping points in a single pipeline,
NOT separate implementations.

Property 4 from design.md:
*For any* website, running scrape mode and running full mode SHALL produce:
- Identical `_raw_scrapes/` folder contents
- Identical `scraped_content.txt` (corpus)
- Identical `_external_links.txt` contents
"""

import filecmp
import os
from typing import NamedTuple


class DiffResult(NamedTuple):
    """Result of comparing two scrape output folders."""

    identical: bool
    raw_scrapes_match: bool
    corpus_match: bool
    external_links_match: bool
    differences: list[str]


def diff_scrape_outputs(folder_scrape: str, folder_full: str) -> DiffResult:
    """
    Compare scrape outputs from two folders (e.g., scrape mode vs full mode).

    Compares:
    - _raw_scrapes/ folder contents
    - scraped_content.txt (corpus)
    - _external_links.txt

    Args:
        folder_scrape: Path to scrape mode output folder
        folder_full: Path to full mode output folder

    Returns:
        DiffResult with comparison details
    """
    differences = []

    # Compare _raw_scrapes/ folders
    raw_scrape_path = os.path.join(folder_scrape, "_raw_scrapes")
    raw_full_path = os.path.join(folder_full, "_raw_scrapes")

    raw_scrapes_match = True
    if os.path.exists(raw_scrape_path) and os.path.exists(raw_full_path):
        # Compare file lists
        scrape_files = set(os.listdir(raw_scrape_path))
        full_files = set(os.listdir(raw_full_path))

        if scrape_files != full_files:
            raw_scrapes_match = False
            only_in_scrape = scrape_files - full_files
            only_in_full = full_files - scrape_files
            if only_in_scrape:
                differences.append(f"_raw_scrapes/ only in scrape: {only_in_scrape}")
            if only_in_full:
                differences.append(f"_raw_scrapes/ only in full: {only_in_full}")
        else:
            # Compare file contents
            for filename in scrape_files:
                scrape_file = os.path.join(raw_scrape_path, filename)
                full_file = os.path.join(raw_full_path, filename)
                if not filecmp.cmp(scrape_file, full_file, shallow=False):
                    raw_scrapes_match = False
                    differences.append(f"_raw_scrapes/{filename} differs")
    elif os.path.exists(raw_scrape_path) != os.path.exists(raw_full_path):
        raw_scrapes_match = False
        differences.append("_raw_scrapes/ exists in one folder but not the other")

    # Compare scraped_content.txt
    corpus_scrape = os.path.join(folder_scrape, "scraped_content.txt")
    corpus_full = os.path.join(folder_full, "scraped_content.txt")

    corpus_match = True
    if os.path.exists(corpus_scrape) and os.path.exists(corpus_full):
        if not filecmp.cmp(corpus_scrape, corpus_full, shallow=False):
            corpus_match = False
            differences.append("scraped_content.txt differs")
    elif os.path.exists(corpus_scrape) != os.path.exists(corpus_full):
        corpus_match = False
        differences.append("scraped_content.txt exists in one folder but not the other")

    # Compare _external_links.txt
    ext_scrape = os.path.join(folder_scrape, "_external_links.txt")
    ext_full = os.path.join(folder_full, "_external_links.txt")

    external_links_match = True
    if os.path.exists(ext_scrape) and os.path.exists(ext_full):
        if not filecmp.cmp(ext_scrape, ext_full, shallow=False):
            external_links_match = False
            differences.append("_external_links.txt differs")
    elif os.path.exists(ext_scrape) != os.path.exists(ext_full):
        external_links_match = False
        differences.append("_external_links.txt exists in one folder but not the other")

    identical = raw_scrapes_match and corpus_match and external_links_match

    return DiffResult(
        identical=identical,
        raw_scrapes_match=raw_scrapes_match,
        corpus_match=corpus_match,
        external_links_match=external_links_match,
        differences=differences,
    )


def print_diff_report(result: DiffResult) -> None:
    """Print a human-readable diff report."""
    print("\n=== Mode Equivalence Report ===")
    print(f"Overall: {'PASS ✓' if result.identical else 'FAIL ✗'}")
    print(f"  _raw_scrapes/: {'✓' if result.raw_scrapes_match else '✗'}")
    print(f"  scraped_content.txt: {'✓' if result.corpus_match else '✗'}")
    print(f"  _external_links.txt: {'✓' if result.external_links_match else '✗'}")

    if result.differences:
        print("\nDifferences:")
        for diff in result.differences:
            print(f"  - {diff}")


# =============================================================================
# Tests
# =============================================================================


class TestDiffScrapeOutputs:
    """Tests for the diff_scrape_outputs function."""

    def test_identical_folders_return_true(self, tmp_path):
        """Identical folders should return identical=True."""
        # Create two identical folder structures
        folder1 = tmp_path / "folder1"
        folder2 = tmp_path / "folder2"

        for folder in [folder1, folder2]:
            folder.mkdir()
            (folder / "_raw_scrapes").mkdir()
            (folder / "_raw_scrapes" / "homepage.txt").write_text(
                "URL: https://example.com\nContent here"
            )
            (folder / "scraped_content.txt").write_text("Combined corpus content")
            (folder / "_external_links.txt").write_text(
                "# External links\nhttps://linkedin.com/company/example"
            )

        result = diff_scrape_outputs(str(folder1), str(folder2))

        assert result.identical
        assert result.raw_scrapes_match
        assert result.corpus_match
        assert result.external_links_match
        assert len(result.differences) == 0

    def test_different_corpus_returns_false(self, tmp_path):
        """Different corpus content should return identical=False."""
        folder1 = tmp_path / "folder1"
        folder2 = tmp_path / "folder2"

        for folder in [folder1, folder2]:
            folder.mkdir()

        (folder1 / "scraped_content.txt").write_text("Content A")
        (folder2 / "scraped_content.txt").write_text("Content B")

        result = diff_scrape_outputs(str(folder1), str(folder2))

        assert not result.identical
        assert not result.corpus_match
        assert "scraped_content.txt differs" in result.differences

    def test_missing_raw_scrapes_detected(self, tmp_path):
        """Missing _raw_scrapes folder should be detected."""
        folder1 = tmp_path / "folder1"
        folder2 = tmp_path / "folder2"

        folder1.mkdir()
        folder2.mkdir()
        (folder1 / "_raw_scrapes").mkdir()

        result = diff_scrape_outputs(str(folder1), str(folder2))

        assert not result.identical
        assert not result.raw_scrapes_match

    def test_different_raw_scrape_files_detected(self, tmp_path):
        """Different files in _raw_scrapes should be detected."""
        folder1 = tmp_path / "folder1"
        folder2 = tmp_path / "folder2"

        for folder in [folder1, folder2]:
            folder.mkdir()
            (folder / "_raw_scrapes").mkdir()

        (folder1 / "_raw_scrapes" / "homepage.txt").write_text("Content A")
        (folder2 / "_raw_scrapes" / "homepage.txt").write_text("Content B")

        result = diff_scrape_outputs(str(folder1), str(folder2))

        assert not result.identical
        assert not result.raw_scrapes_match
        assert any("homepage.txt differs" in d for d in result.differences)
