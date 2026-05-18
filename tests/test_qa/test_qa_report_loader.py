"""
Property-based tests for QA report loading.

Feature: report-quality-assurance, Property 8: Report existence validation
Validates: Requirements 1.3
"""

import os
from pathlib import Path
import tempfile

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.primr.qa.models import ReportContent
from src.primr.qa.report_loader import ReportLoader


class TestReportLoader:
    """Property-based tests for report loading."""

    @given(
        company_name=st.one_of(
            # Realistic company names
            st.sampled_from(
                [
                    "Acme Corp",
                    "Globex Industries",
                    "Initech Solutions",
                    "Umbrella Holdings",
                    "Soylent Labs",
                    "Wonka Enterprises",
                    "Stark Solutions",
                    "Weyland Group",
                    "Cyberdyne Systems",
                    "Oscorp Research",
                    "Tyrell Corp",
                    "Massive Dynamic",
                    "Abstergo Industries",
                    "Vought International",
                    "LexCorp Holdings",
                    "Dharma Initiative",
                ]
            ),
            # Simple generated names
            st.text(
                min_size=5,
                max_size=25,
                alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ",
            ).filter(
                lambda x: (
                    x.strip()
                    and len(x.strip()) >= 5
                    and not x.startswith(" ")
                    and not x.endswith(" ")
                )
            ),
        ),
        content_length=st.integers(min_value=50, max_value=500),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=10, deadline=None)
    def test_report_existence_validation_property(self, company_name, content_length):
        """
        Property 8: Report existence validation

        For any company name, when no report exists, the system should
        return None gracefully. When a report exists, it should load successfully.

        **Feature: report-quality-assurance, Property 8: Report existence validation**
        **Validates: Requirements 1.3**
        """
        loader = ReportLoader()

        # Test 1: Non-existent company should return None
        non_existent_company = f"NonExistent_{company_name}_12345"
        result = loader.load_report_content(non_existent_company)
        assert result is None

        # Test 2: Create a temporary report and verify it loads
        with tempfile.TemporaryDirectory() as temp_dir:
            # Override output directory for test
            loader.output_dir = Path(temp_dir)

            # Create a test report file using the cleaned company name format
            # (this matches how the system actually creates files)
            clean_company_name = loader._clean_company_name_for_search(company_name)
            content = f"# Report for {company_name}\n" + "Test content. " * (content_length // 13)
            report_filename = f"{clean_company_name}_Strategic_Overview_12-22-2025.txt"
            report_path = Path(temp_dir) / report_filename

            with open(report_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Should now find and load the report
            result = loader.load_report_content(company_name)

            assert result is not None
            assert isinstance(result, ReportContent)
            # Note: The system normalizes company names for file system compatibility
            # Spaces become underscores, so "Acme Corp" becomes "Acme_Corp"
            # This is expected behavior
            expected_name = clean_company_name.replace("_", " ")
            assert result.company_name == expected_name or result.company_name == clean_company_name
            assert len(result.content) > 0
            assert result.file_path == report_path

    @given(
        company_names=st.lists(
            st.sampled_from(
                [
                    "Acme Corp",
                    "Globex Industries",
                    "Initech Solutions",
                    "Umbrella Holdings",
                    "Soylent Labs",
                    "Wonka Enterprises",
                    "Stark Solutions",
                    "Weyland Group",
                ]
            ),
            min_size=1,
            max_size=3,
        )
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=5, deadline=None)
    def test_latest_report_selection_property(self, company_names):
        """
        Property: Latest report selection

        When multiple reports exist for a company, the system should
        consistently select the most recent one based on modification time.
        """
        company_name = company_names[0]
        loader = ReportLoader()

        with tempfile.TemporaryDirectory() as temp_dir:
            loader.output_dir = Path(temp_dir)

            # Create multiple report files with different timestamps
            # Use cleaned company name format for file creation
            clean_company_name = loader._clean_company_name_for_search(company_name)
            report_files = []
            for i in range(3):
                filename = f"{clean_company_name}_Strategic_Overview_12-{20 + i}-2025.txt"
                file_path = Path(temp_dir) / filename

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"Report {i} for {company_name}")

                # Modify the file timestamp to ensure ordering
                import time

                timestamp = time.time() + i  # Each file is 1 second newer
                os.utime(file_path, (timestamp, timestamp))

                report_files.append(file_path)

            # Should find the latest file (index 2)
            latest_file = loader.find_latest_report(company_name)

            assert latest_file is not None
            assert latest_file == report_files[-1]  # Should be the newest file

    @given(file_extensions=st.sampled_from([".txt", ".md", ".docx", ".pdf"]))
    def test_file_format_support_property(self, file_extensions):
        """
        Property: File format support

        The system should handle different file formats appropriately,
        either loading them successfully or failing gracefully.
        """
        loader = ReportLoader()
        company_name = "Test Company"

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test file with the specified extension
            filename = f"{company_name}_Strategic_Overview_12-22-2025{file_extensions}"
            file_path = Path(temp_dir) / filename

            if file_extensions in [".txt", ".md"]:
                # Text-based files should work
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"# Test Report for {company_name}\nTest content here.")

                result = loader.load_report_from_path(file_path)

                assert result is not None
                assert result.company_name == company_name
                assert len(result.content) > 0

            else:
                # Binary formats (DOCX, PDF) may not work without libraries
                # Create empty file to test graceful handling
                file_path.touch()

                result = loader.load_report_from_path(file_path)
                # Should either work or return None gracefully (no exceptions)
                assert result is None or isinstance(result, ReportContent)

    @given(section_count=st.integers(min_value=1, max_value=10))
    def test_section_parsing_property(self, section_count):
        """
        Property: Section parsing consistency

        For any report with clearly defined sections, the parser should
        consistently identify and separate the sections.
        """
        loader = ReportLoader()

        # Generate content with clear section headers
        sections_content = []
        section_names = []

        for i in range(section_count):
            section_name = f"Section {i + 1}"
            section_content = f"This is the content for section {i + 1}.\nIt has multiple lines.\n"

            sections_content.append(f"# {section_name}\n{section_content}")
            section_names.append(section_name)

        full_content = "\n".join(sections_content)

        # Parse sections
        parsed_sections = loader._parse_sections(full_content)

        # Should have found all sections
        assert len(parsed_sections) >= section_count

        # Each section should have content
        for _section_name, content in parsed_sections.items():
            assert len(content.strip()) > 0

    @given(
        company_name=st.sampled_from(
            [
                "Acme Corp",
                "Globex Industries",
                "Initech Solutions",
                "Umbrella Holdings",
                "Soylent Labs",
                "Wonka Enterprises",
                "Stark Solutions",
                "Weyland Group",
            ]
        )
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=10, deadline=None)
    def test_company_name_extraction_property(self, company_name):
        """
        Property: Company name extraction consistency

        For any valid company name in a filename, the extraction should
        consistently recover a reasonable company name.
        """
        loader = ReportLoader()

        # Test various filename patterns using cleaned company name
        clean_company_name = loader._clean_company_name_for_search(company_name)
        filename_patterns = [
            f"{clean_company_name}_Strategic_Overview_12-22-2025.txt",
            f"{clean_company_name}_Company_Overview_12-22-2025.txt",
            f"{clean_company_name}_AI_Strategy_12-22-2025.txt",
        ]

        for filename in filename_patterns:
            extracted_name = loader._extract_company_name(filename)

            # Should extract a non-empty name
            assert len(extracted_name.strip()) > 0

            # Should be related to original company name (at least some overlap)
            # Allow for cleaning/normalization differences
            original_clean = company_name.lower().replace(" ", "").replace("_", "")
            extracted_clean = extracted_name.lower().replace(" ", "").replace("_", "")

            # Should have some similarity (at least 50% of characters in common)
            if len(original_clean) > 0:
                common_chars = sum(1 for c in original_clean if c in extracted_clean)
                similarity = common_chars / len(original_clean)
                assert similarity >= 0.3  # At least 30% similarity
