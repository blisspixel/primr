"""Tests for scrape trace logging."""

import json
import tempfile
from pathlib import Path

from primr.data.scraping.models import (
    Attempt,
    ErrorType,
    PageAccessAssessment,
    PageAccessState,
    ScrapeResult,
    ValidationResult,
)
from primr.data.scraping.trace import (
    TRACE_SCHEMA_VERSION,
    TraceLogger,
    read_trace_file,
)


class TestTraceLogger:
    """Tests for TraceLogger."""

    def test_creates_trace_file(self):
        """TraceLogger should create a trace file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger("TestCompany", output_dir=Path(tmpdir))

            assert logger.path.exists()
            assert logger.path.suffix == ".jsonl"

    def test_writes_header(self):
        """First line should be header with schema version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger("TestCompany", output_dir=Path(tmpdir))

            with open(logger.path) as f:
                header_line = f.readline()

            header = json.loads(header_line)
            assert header["schema_version"] == TRACE_SCHEMA_VERSION
            assert header["company"] == "TestCompany"
            assert "run_id" in header
            assert "started_at" in header

    def test_log_successful_result(self):
        """Should log successful scrape result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger("TestCompany", output_dir=Path(tmpdir))

            result = ScrapeResult(
                url="https://example.com",
                success=True,
                tier="requests",
                http_status=200,
                content_type="html",
                elapsed_ms=150.0,
                extracted_text="Some content",
                access_assessment=PageAccessAssessment(
                    state=PageAccessState.SUCCESS,
                    confidence=0.88,
                    page_kind="homepage",
                    evidence=["landmarks:main, nav"],
                ),
                attempts=[
                    Attempt(tier="requests", success=True, elapsed_ms=150.0),
                ],
            )

            logger.log(result)

            # Read back
            with open(logger.path) as f:
                lines = f.readlines()

            assert len(lines) == 2  # Header + 1 entry
            entry = json.loads(lines[1])

            assert entry["url"] == "https://example.com"
            assert entry["success_tier"] == "requests"
            assert entry["blocked"] is False
            assert entry["http_status"] == 200
            assert entry["extracted_text_length"] == len("Some content")
            assert entry["access_assessment"]["state"] == "success"
            assert entry["access_assessment"]["page_kind"] == "homepage"

    def test_log_failed_result(self):
        """Should log failed scrape result with block info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger("TestCompany", output_dir=Path(tmpdir))

            result = ScrapeResult(
                url="https://blocked.com",
                success=False,
                error="Soft block detected",
                error_type=ErrorType.SOFT_BLOCK,
                blocked_reason="Cloudflare challenge",
                attempts=[
                    Attempt(
                        tier="requests",
                        success=False,
                        error="Soft block",
                        error_type=ErrorType.SOFT_BLOCK,
                    ),
                ],
            )

            logger.log(result)

            # Read back
            with open(logger.path) as f:
                lines = f.readlines()

            entry = json.loads(lines[1])

            assert entry["blocked"] is True
            assert entry["block_type"] == "soft_block"
            assert entry["blocked_reason"] == "Cloudflare challenge"

    def test_log_with_validation_result(self):
        """Should log validation result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger("TestCompany", output_dir=Path(tmpdir))

            result = ScrapeResult(
                url="https://example.com",
                success=True,
                tier="requests",
                validation=ValidationResult(
                    valid=True,
                    content_density=0.75,
                    is_duplicate_template=False,
                    content_class="structured_short",
                    counts_as_full_page=False,
                ),
            )

            logger.log(result)

            # Read back
            with open(logger.path) as f:
                lines = f.readlines()

            entry = json.loads(lines[1])

            assert entry["validation_result"] is not None
            assert entry["validation_result"]["valid"] is True
            assert entry["validation_result"]["content_density"] == 0.75
            assert entry["validation_result"]["content_class"] == "structured_short"
            assert entry["validation_result"]["counts_as_full_page"] is False

    def test_log_multiple_attempts(self):
        """Should log all tier attempts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger("TestCompany", output_dir=Path(tmpdir))

            result = ScrapeResult(
                url="https://example.com",
                success=True,
                tier="curl_cffi",
                attempts=[
                    Attempt(tier="requests", success=False, error="Timeout"),
                    Attempt(tier="httpx", success=False, error="Soft block"),
                    Attempt(tier="curl_cffi", success=True, elapsed_ms=200.0),
                ],
            )

            logger.log(result)

            # Read back
            with open(logger.path) as f:
                lines = f.readlines()

            entry = json.loads(lines[1])

            assert len(entry["tier_attempts"]) == 3
            assert entry["tier_attempts"][0]["tier"] == "requests"
            assert entry["tier_attempts"][1]["tier"] == "httpx"
            assert entry["tier_attempts"][2]["tier"] == "curl_cffi"
            assert entry["tier_attempts"][2]["success"] is True

    def test_sanitizes_company_name(self):
        """Should sanitize company name for filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger("Test/Company\\Name", output_dir=Path(tmpdir))

            # Filename should not contain / or \
            assert "/" not in logger.path.name
            assert "\\" not in logger.path.name

    def test_get_run_id(self):
        """Should return consistent run ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger("TestCompany", output_dir=Path(tmpdir))

            run_id = logger.get_run_id()
            assert run_id == logger.run_id
            assert len(run_id) > 0


class TestReadTraceFile:
    """Tests for read_trace_file."""

    def test_read_trace_file(self):
        """Should read back header and entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger("TestCompany", output_dir=Path(tmpdir))

            # Log some results
            logger.log(ScrapeResult(url="https://example1.com", success=True, tier="requests"))
            logger.log(ScrapeResult(url="https://example2.com", success=False))

            # Read back
            header, entries = read_trace_file(logger.path)

            assert header.schema_version == TRACE_SCHEMA_VERSION
            assert header.company == "TestCompany"
            assert len(entries) == 2
            assert entries[0].url == "https://example1.com"
            assert entries[1].url == "https://example2.com"


class TestGoldenRunTrace:
    """Golden-run trace test to verify format stability."""

    def test_golden_run_trace(self):
        """
        Verify trace artifact contains correct attempt sequence.

        This is a regression test - if trace format changes, update expected.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger("GoldenTest", output_dir=Path(tmpdir))

            # Simulate a scrape with 2 failed tiers and 1 success
            result = ScrapeResult(
                url="https://example.com/test",
                success=True,
                tier="tier2",
                http_status=200,
                content_type="html",
                elapsed_ms=350.0,
                extracted_text="Test content here",
                attempts=[
                    Attempt(
                        tier="tier1",
                        success=False,
                        error="Tier 1 failed",
                        error_type=ErrorType.TIMEOUT,
                        elapsed_ms=100.0,
                    ),
                    Attempt(
                        tier="tier2",
                        success=True,
                        elapsed_ms=250.0,
                        http_status=200,
                    ),
                ],
            )

            logger.log(result)

            # Read and verify
            header, entries = read_trace_file(logger.path)

            # Verify header
            assert header.schema_version == TRACE_SCHEMA_VERSION
            assert header.company == "GoldenTest"

            # Verify entry
            assert len(entries) == 1
            entry = entries[0]

            assert entry.url == "https://example.com/test"
            assert entry.success_tier == "tier2"
            assert entry.blocked is False
            assert entry.http_status == 200
            assert entry.content_type == "html"
            assert entry.extracted_text_length == len("Test content here")

            # Verify attempt sequence
            assert len(entry.tier_attempts) == 2
            assert entry.tier_attempts[0]["tier"] == "tier1"
            assert entry.tier_attempts[0]["success"] is False
            assert entry.tier_attempts[0]["error_type"] == "timeout"
            assert entry.tier_attempts[1]["tier"] == "tier2"
            assert entry.tier_attempts[1]["success"] is True
