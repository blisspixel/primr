"""Coverage tests for primr.output.executive_summary_generator.ExecutiveSummaryGenerator."""

from __future__ import annotations

from primr.output.executive_summary_generator import ExecutiveSummaryGenerator


# --------------------------------------------------------------------------- #
# generate (top-level)
# --------------------------------------------------------------------------- #
def test_generate_full_summary():
    sections = {
        "unique_selling_proposition": (
            "The company is a leading provider of cloud tools. "
            "It generated $480M in revenue with strong growth potential."
        ),
        "financial_overview": "Annual Revenue: $480M. Profit margin improved to 15%.",
        "strategic_recommendations": (
            "There is regulatory risk in the market. The company should expand carefully."
        ),
        "industry_insights": (
            "The industry faces stiff competition and uncertainty about future demand patterns."
        ),
        "company_name": "Acme",
        "industry": "technology",
    }
    gen = ExecutiveSummaryGenerator(sections)
    summary = gen.generate()
    assert summary.narrative
    assert isinstance(summary.key_takeaways, list)
    assert isinstance(summary.risk_factors, list)
    assert summary.one_liner


def test_generate_empty_sections():
    gen = ExecutiveSummaryGenerator({})
    summary = gen.generate()
    assert summary.narrative == ""
    assert summary.key_takeaways == []
    assert summary.risk_factors == []
    # one_liner falls back to generic phrasing.
    assert "specialized services" in summary.one_liner


# --------------------------------------------------------------------------- #
# extract_key_insights
# --------------------------------------------------------------------------- #
def test_extract_key_insights_financial():
    sections = {
        "financial_overview": (
            "Revenue reached $50M last year. The team grew significantly. "
            "Net income margin hit 20% which is strong."
        )
    }
    gen = ExecutiveSummaryGenerator(sections)
    insights = gen.extract_key_insights()
    assert any("$50M" in i or "50M" in i for i in insights)


def test_extract_key_insights_skips_missing_sections():
    gen = ExecutiveSummaryGenerator({"other_section": "irrelevant"})
    assert gen.extract_key_insights() == []


def test_extract_key_insights_respects_max():
    # Build many financial sentences to exceed MAX_TAKEAWAYS.
    sentences = " ".join(
        f"In year {2000 + i} revenue rose to ${10 + i}M showing strong growth potential."
        for i in range(20)
    )
    gen = ExecutiveSummaryGenerator({"financial_overview": sentences})
    insights = gen.extract_key_insights()
    assert len(insights) <= ExecutiveSummaryGenerator.MAX_TAKEAWAYS


# --------------------------------------------------------------------------- #
# extract_risk_factors
# --------------------------------------------------------------------------- #
def test_extract_risk_factors():
    sections = {
        "strategic_recommendations": (
            "There is a regulatory risk. Competition is a real threat to margins."
        )
    }
    gen = ExecutiveSummaryGenerator(sections)
    risks = gen.extract_risk_factors()
    assert risks
    assert any("risk" in r.lower() or "threat" in r.lower() for r in risks)


def test_extract_risk_factors_none():
    gen = ExecutiveSummaryGenerator({"strategic_recommendations": "All looks positive and stable."})
    assert gen.extract_risk_factors() == []


# --------------------------------------------------------------------------- #
# _generate_one_liner
# --------------------------------------------------------------------------- #
def test_one_liner_with_all_parts():
    sections = {
        "company_name": "Acme",
        "industry": "fintech",
        "unique_selling_proposition": "Acme is a leading pioneer of payment rails.",
        "financial_overview": "Annual Revenue: $99M reported this year.",
    }
    gen = ExecutiveSummaryGenerator(sections)
    one_liner = gen._generate_one_liner()
    assert one_liner.startswith("Acme")
    assert "fintech" in one_liner
    assert one_liner.endswith(".")


def test_one_liner_fallback_when_no_extra_parts():
    gen = ExecutiveSummaryGenerator({"company_name": "SoloCo"})
    one_liner = gen._generate_one_liner()
    assert "SoloCo provides specialized services" in one_liner


# --------------------------------------------------------------------------- #
# internal helpers
# --------------------------------------------------------------------------- #
def test_split_into_sentences():
    gen = ExecutiveSummaryGenerator({})
    out = gen._split_into_sentences("One. Two! Three?")
    assert out == ["One.", "Two!", "Three?"]


def test_is_insight_worthy_short_false():
    gen = ExecutiveSummaryGenerator({})
    assert gen._is_insight_worthy("Too short.") is False


def test_is_insight_worthy_with_number():
    gen = ExecutiveSummaryGenerator({})
    assert (
        gen._is_insight_worthy("This particular product line earned 5 million dollars overall.")
        is True
    )


def test_clean_sentence_strips_markdown():
    gen = ExecutiveSummaryGenerator({})
    out = gen._clean_sentence("**bold** and __under__ and *ital*")
    assert "**" not in out
    assert "__" not in out


def test_clean_sentence_truncates_long_text():
    gen = ExecutiveSummaryGenerator({})
    # No period in first 500 chars -> hard truncate with ellipsis.
    long_text = "x" * 600
    out = gen._clean_sentence(long_text)
    assert out.endswith("...")
    assert len(out) <= 500


def test_clean_sentence_truncates_at_period():
    gen = ExecutiveSummaryGenerator({})
    long_text = ("a" * 300) + ". " + ("b" * 300)
    out = gen._clean_sentence(long_text)
    assert out.endswith(".")


def test_extract_first_paragraph_skips_short_and_headers():
    gen = ExecutiveSummaryGenerator({})
    content = "# Header\n\nshort\n\n" + ("This is a substantial paragraph. " * 5)
    out = gen._extract_first_paragraph(content)
    assert out
    assert not out.startswith("#")


def test_extract_first_paragraph_empty():
    gen = ExecutiveSummaryGenerator({})
    assert gen._extract_first_paragraph("# only header\n\nshort") == ""


def test_extract_key_differentiator_phrase():
    gen = ExecutiveSummaryGenerator({})
    out = gen._extract_key_differentiator("We are the leading provider of widgets.")
    assert out
    assert out == out.lower()


def test_extract_key_differentiator_fallback_first_sentence():
    gen = ExecutiveSummaryGenerator({})
    out = gen._extract_key_differentiator("We do many ordinary things. And more things.")
    assert out
    assert out == out.lower()


def test_extract_key_differentiator_empty():
    gen = ExecutiveSummaryGenerator({})
    assert gen._extract_key_differentiator("") == ""


def test_extract_key_differentiator_long_phrase_truncated():
    gen = ExecutiveSummaryGenerator({})
    long_unique = "We are a unique " + ("word " * 50)
    out = gen._extract_key_differentiator(long_unique)
    assert out.endswith("...")
