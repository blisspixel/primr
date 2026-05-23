"""Coverage tests for primr.output.content_pattern_detector.ContentPatternDetector."""

from __future__ import annotations

from primr.output.content_pattern_detector import ContentPatternDetector


def _det():
    return ContentPatternDetector()


# --------------------------------------------------------------------------- #
# detect_sub_headings
# --------------------------------------------------------------------------- #
def test_detect_sub_headings_text_before_bullet():
    det = _det()
    content = "Capabilities\n- one\n- two\n"
    subs = det.detect_sub_headings(content)
    assert (0, "Capabilities") in subs


def test_detect_sub_headings_skips_bullets_and_headings():
    det = _det()
    content = "# Heading\n* a bullet line\nplain text with no bullets after\n"
    subs = det.detect_sub_headings(content)
    # Heading and bullet lines never qualify; trailing plain text has no bullet after.
    assert subs == []


def test_detect_sub_headings_blank_lines_between():
    det = _det()
    content = "Section Title\n\n- bullet item\n"
    subs = det.detect_sub_headings(content)
    assert (0, "Section Title") in subs


# --------------------------------------------------------------------------- #
# detect_inline_headers
# --------------------------------------------------------------------------- #
def test_detect_inline_headers_match():
    det = _det()
    assert det.detect_inline_headers("Revenue: $5M") == ("Revenue", "$5M")


def test_detect_inline_headers_url_excluded():
    det = _det()
    assert det.detect_inline_headers("Https: example") is None


def test_detect_inline_headers_no_match():
    det = _det()
    assert det.detect_inline_headers("just a plain line") is None


# --------------------------------------------------------------------------- #
# extract_metrics
# --------------------------------------------------------------------------- #
def test_extract_metrics_revenue_founded_ticker():
    det = _det()
    content = (
        "Annual Revenue: $42M\n"
        "Founded: 1999\n"
        "NASDAQ: ACME\n"
        "Headquarters: Anytown, CA\n"
        "Net Profit Margin: 12.5%\n"
    )
    metrics = det.extract_metrics(content)
    assert metrics["revenue"].startswith("42")
    assert metrics["founded"] == "1999"
    assert metrics["ticker"] == "ACME"
    assert "Anytown" in metrics["headquarters"]
    assert metrics["profit_margin"] == "12.5%"


def test_extract_metrics_employees_largest_meaningful():
    det = _det()
    content = "We have over 1,200 employees and approximately 3,500 employees worldwide."
    metrics = det.extract_metrics(content)
    assert metrics["employees"] == "3,500"


def test_extract_metrics_employees_ignores_small_numbers():
    det = _det()
    content = "Only 3 employees in this office."
    metrics = det.extract_metrics(content)
    assert "employees" not in metrics


def test_extract_metrics_empty_content():
    det = _det()
    assert det.extract_metrics("") == {}


# --------------------------------------------------------------------------- #
# extract_financial_figures
# --------------------------------------------------------------------------- #
def test_extract_financial_figures():
    det = _det()
    figs = det.extract_financial_figures("Revenue of $480M grew 15% year over year.")
    assert "$480M" in figs
    assert "15%" in figs


def test_extract_financial_figures_none():
    det = _det()
    assert det.extract_financial_figures("no money here") == []


# --------------------------------------------------------------------------- #
# detect_risk_keywords / detect_opportunity_keywords
# --------------------------------------------------------------------------- #
def test_detect_risk_keywords_true():
    det = _det()
    assert det.detect_risk_keywords("There is significant regulatory risk.") is True


def test_detect_risk_keywords_false():
    det = _det()
    assert det.detect_risk_keywords("All systems nominal and stable.") is False


def test_detect_opportunity_keywords_true():
    det = _det()
    assert det.detect_opportunity_keywords("Strong growth and expansion potential.") is True


def test_detect_opportunity_keywords_false():
    det = _det()
    assert det.detect_opportunity_keywords("Nothing notable to report.") is False
