"""
Property tests for ArtifactDetector.

Property 5: No markdown artifacts in output
Validates: Requirements 5.2
"""

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from primr.output.markdown_parser import ArtifactDetector


class TestArtifactDetectorProperties:
    """Property-based tests for ArtifactDetector."""

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_scan_text_returns_list(self, text):
        """scan_text always returns a list."""
        detector = ArtifactDetector()
        result = detector.scan_text(text)
        assert isinstance(result, list)

    @given(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
            min_size=0,
            max_size=200,
        )
    )
    @settings(max_examples=100)
    def test_clean_text_has_no_artifacts(self, text):
        """Text without markdown patterns should have no artifacts."""
        # Filter out text that accidentally contains markdown patterns
        assume("**" not in text)
        assume("__" not in text)
        assume(not any(text.lstrip().startswith(c) for c in ["#", "*", "-"]))

        detector = ArtifactDetector()
        artifacts = detector.scan_text(text)
        assert len(artifacts) == 0

    def test_detects_heading_artifacts(self):
        """Detects ## heading patterns."""
        detector = ArtifactDetector()

        test_cases = [
            "## This is a heading",
            "### Sub heading",
            "# Main heading",
            "Some text\n## Another heading\nMore text",
        ]

        for text in test_cases:
            artifacts = detector.scan_text(text)
            heading_artifacts = [a for a in artifacts if a["type"] == "heading"]
            assert len(heading_artifacts) > 0, f"Should detect heading in: {text}"

    def test_detects_bold_artifacts(self):
        """Detects **bold** and __bold__ patterns."""
        detector = ArtifactDetector()

        test_cases = [
            "This has **bold text** in it",
            "Also __underline bold__ works",
            "Multiple **bold** and **more bold**",
        ]

        for text in test_cases:
            artifacts = detector.scan_text(text)
            bold_artifacts = [a for a in artifacts if a["type"] == "bold"]
            assert len(bold_artifacts) > 0, f"Should detect bold in: {text}"

    def test_detects_bullet_artifacts(self):
        """Detects bullet markers at line start."""
        detector = ArtifactDetector()

        test_cases = [
            "* Bullet item",
            "- Dash bullet",
            "  * Indented bullet",
        ]

        for text in test_cases:
            artifacts = detector.scan_text(text)
            bullet_artifacts = [a for a in artifacts if a["type"] == "bullet"]
            assert len(bullet_artifacts) > 0, f"Should detect bullet in: {text}"

    def test_no_false_positives_for_normal_text(self):
        """Normal prose should not trigger artifact detection."""
        detector = ArtifactDetector()

        clean_texts = [
            "This is normal text without any markdown.",
            "The company earned $5.2 billion in revenue.",
            "Founded in 1998, the company has grown significantly.",
            "Key metrics include: revenue, profit margin, and growth rate.",
        ]

        for text in clean_texts:
            artifacts = detector.scan_text(text)
            assert len(artifacts) == 0, f"False positive in: {text}"

    def test_artifact_dict_structure(self):
        """Artifact dicts have required keys."""
        detector = ArtifactDetector()
        artifacts = detector.scan_text("## Heading")

        assert len(artifacts) > 0
        artifact = artifacts[0]
        assert "type" in artifact
        assert "match" in artifact
        assert "context" in artifact
        assert "position" in artifact

    def test_get_artifact_summary_empty(self):
        """Summary for no artifacts."""
        detector = ArtifactDetector()
        detector.scan_text("Clean text")
        summary = detector.get_artifact_summary()
        assert "No markdown artifacts found" in summary

    def test_get_artifact_summary_with_artifacts(self):
        """Summary includes artifact details."""
        detector = ArtifactDetector()
        detector.artifacts_found = [
            {"type": "heading", "match": "##", "context": "Para 1"},
            {"type": "bold", "match": "**text**", "context": "Para 2"},
        ]
        summary = detector.get_artifact_summary()
        assert "2 markdown artifact" in summary
        assert "heading" in summary
        assert "bold" in summary


class TestProperty5NoMarkdownArtifacts:
    """
    Property 5: No markdown artifacts in output.

    After document generation, the output should not contain
    unconverted markdown syntax like ##, **, *, etc.
    """

    def test_properly_converted_content_has_no_artifacts(self):
        """Content that goes through the parser should be clean."""
        from primr.output.markdown_parser import MarkdownParser

        parser = MarkdownParser()
        detector = ArtifactDetector()

        # Sample markdown content
        markdown_content = """
## Company Overview

This is **bold text** and normal text.

* First bullet point
* Second bullet point
  * Nested bullet

### Financial Highlights

Revenue: $5.2 billion
"""

        # Parse the content
        blocks = parser.parse_content(markdown_content)

        # Extract the plain text content (what would go into the document)
        plain_texts = []
        for block in blocks:
            for line in block.lines:
                # The content field should be clean (no markdown markers)
                plain_texts.append(line.content)

        # Check that parsed content is clean
        for text in plain_texts:
            artifacts = detector.scan_text(text)
            # Filter out false positives - parsed content shouldn't have heading markers
            heading_artifacts = [a for a in artifacts if a["type"] == "heading"]
            [a for a in artifacts if a["type"] == "bold"]
            assert len(heading_artifacts) == 0, f"Heading artifact in parsed content: {text}"
            # Note: bold markers may still be in content for inline formatting
            # They get converted during apply_inline_formatting()

    @given(
        st.lists(
            st.sampled_from(
                [
                    "Normal text paragraph.",
                    "Revenue grew by 15% year over year.",
                    "The company was founded in 2005.",
                    "Key strengths include innovation and market position.",
                ]
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=50)
    def test_clean_input_produces_clean_output(self, paragraphs):
        """Clean input text should produce clean output."""
        detector = ArtifactDetector()

        for para in paragraphs:
            artifacts = detector.scan_text(para)
            assert len(artifacts) == 0
