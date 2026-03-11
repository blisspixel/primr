"""
Tests for the sentiment analysis module.
"""

import pytest

from primr.data.sentiment import (
    ContentSentiment,
    Sentiment,
    SentimentAnalyzer,
    SentimentResult,
    Tone,
    ToneResult,
    analyze_content,
    analyze_sentiment,
    analyze_tone,
    get_sentiment_analyzer,
    get_sentiment_summary,
    reset_sentiment_analyzer,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    reset_sentiment_analyzer()
    yield
    reset_sentiment_analyzer()


@pytest.fixture
def analyzer():
    """Create a fresh analyzer."""
    return SentimentAnalyzer()


# =============================================================================
# SENTIMENT RESULT TESTS
# =============================================================================


class TestSentimentResult:
    """Tests for SentimentResult dataclass."""

    def test_is_positive_true(self):
        """Test is_positive for positive sentiment."""
        result = SentimentResult(
            sentiment=Sentiment.POSITIVE,
            score=0.5,
            confidence=0.8,
        )
        assert result.is_positive is True
        assert result.is_negative is False

    def test_is_positive_very_positive(self):
        """Test is_positive for very positive sentiment."""
        result = SentimentResult(
            sentiment=Sentiment.VERY_POSITIVE,
            score=0.9,
            confidence=0.9,
        )
        assert result.is_positive is True

    def test_is_negative_true(self):
        """Test is_negative for negative sentiment."""
        result = SentimentResult(
            sentiment=Sentiment.NEGATIVE,
            score=-0.5,
            confidence=0.8,
        )
        assert result.is_negative is True
        assert result.is_positive is False

    def test_neutral_neither(self):
        """Test neutral is neither positive nor negative."""
        result = SentimentResult(
            sentiment=Sentiment.NEUTRAL,
            score=0.0,
            confidence=0.5,
        )
        assert result.is_positive is False
        assert result.is_negative is False


# =============================================================================
# BASIC SENTIMENT TESTS
# =============================================================================


class TestBasicSentiment:
    """Tests for basic sentiment analysis."""

    def test_positive_text(self, analyzer):
        """Test positive text detection."""
        text = "The company reported excellent growth and strong profits."
        result = analyzer.analyze_sentiment(text)

        assert result.is_positive
        assert result.score > 0
        assert len(result.positive_words) > 0

    def test_negative_text(self, analyzer):
        """Test negative text detection."""
        text = "The company faced terrible losses and declining sales."
        result = analyzer.analyze_sentiment(text)

        assert result.is_negative
        assert result.score < 0
        assert len(result.negative_words) > 0

    def test_neutral_text(self, analyzer):
        """Test neutral text detection."""
        text = "The company is located in New York City."
        result = analyzer.analyze_sentiment(text)

        assert result.sentiment == Sentiment.NEUTRAL
        assert abs(result.score) < 0.3

    def test_very_positive_text(self, analyzer):
        """Test very positive text detection."""
        text = "Outstanding performance with exceptional results and phenomenal growth."
        result = analyzer.analyze_sentiment(text)

        assert result.sentiment == Sentiment.VERY_POSITIVE
        assert result.score >= 0.6

    def test_very_negative_text(self, analyzer):
        """Test very negative text detection."""
        text = "Catastrophic failure led to devastating losses and a major crisis."
        result = analyzer.analyze_sentiment(text)

        assert result.sentiment == Sentiment.VERY_NEGATIVE
        assert result.score <= -0.6


# =============================================================================
# NEGATION TESTS
# =============================================================================


class TestNegation:
    """Tests for negation handling."""

    def test_negation_flips_positive(self, analyzer):
        """Test negation flips positive words."""
        text = "The results were not good."
        result = analyzer.analyze_sentiment(text)

        # "good" should be counted as negative due to "not"
        assert result.score <= 0

    def test_negation_flips_negative(self, analyzer):
        """Test negation flips negative words."""
        text = "There were no problems with the product."
        result = analyzer.analyze_sentiment(text)

        # "problems" should be counted as positive due to "no"
        assert result.score >= 0

    def test_double_negation(self, analyzer):
        """Test handling of complex negation."""
        text = "The company never fails to deliver quality."
        result = analyzer.analyze_sentiment(text)

        # Should still be somewhat positive
        assert "quality" in result.positive_words or result.score >= 0


# =============================================================================
# TONE ANALYSIS TESTS
# =============================================================================


class TestToneAnalysis:
    """Tests for tone analysis."""

    def test_formal_tone(self, analyzer):
        """Test formal tone detection."""
        text = "Pursuant to the agreement, the company shall hereby provide services."
        result = analyzer.analyze_tone(text)

        assert result.primary_tone == Tone.FORMAL

    def test_promotional_tone(self, analyzer):
        """Test promotional tone detection."""
        text = "Our revolutionary product is the best in class, offering exclusive features."
        result = analyzer.analyze_tone(text)

        assert result.primary_tone == Tone.PROMOTIONAL

    def test_technical_tone(self, analyzer):
        """Test technical tone detection."""
        text = "The platform architecture uses a scalable infrastructure with API integration."
        result = analyzer.analyze_tone(text)

        assert result.primary_tone == Tone.TECHNICAL

    def test_urgent_tone(self, analyzer):
        """Test urgent tone detection."""
        text = "This is urgent! We need immediate action before the deadline today."
        result = analyzer.analyze_tone(text)

        assert result.primary_tone == Tone.URGENT

    def test_confident_tone(self, analyzer):
        """Test confident tone detection."""
        text = "We are confident in our strong position and excellent team."
        result = analyzer.analyze_tone(text)

        assert result.primary_tone == Tone.CONFIDENT

    def test_neutral_tone(self, analyzer):
        """Test neutral tone detection."""
        text = "The meeting will be held on Tuesday at 3pm."
        result = analyzer.analyze_tone(text)

        assert result.primary_tone == Tone.NEUTRAL

    def test_secondary_tones(self, analyzer):
        """Test secondary tone detection."""
        text = (
            "Our revolutionary platform uses cutting-edge infrastructure for scalable deployment."
        )
        result = analyzer.analyze_tone(text)

        # Should have both promotional and technical tones
        all_tones = [result.primary_tone, *result.secondary_tones]
        assert Tone.PROMOTIONAL in all_tones or Tone.TECHNICAL in all_tones


# =============================================================================
# ENTITY SENTIMENT TESTS
# =============================================================================


class TestEntitySentiment:
    """Tests for entity-level sentiment."""

    def test_company_entity_extraction(self, analyzer):
        """Test company entity extraction."""
        text = "Acme Corp reported strong earnings this quarter."
        result = analyzer.extract_entity_sentiments(text)

        company_entities = [e for e in result if e.entity_type == "company"]
        assert len(company_entities) >= 1

    def test_person_entity_extraction(self, analyzer):
        """Test person entity extraction."""
        text = "CEO John Smith announced excellent quarterly results."
        result = analyzer.extract_entity_sentiments(text)

        person_entities = [e for e in result if e.entity_type == "person"]
        assert len(person_entities) >= 1

    def test_entity_sentiment_positive(self, analyzer):
        """Test entity sentiment is captured."""
        text = "Acme Inc reported outstanding growth and excellent profits."
        result = analyzer.extract_entity_sentiments(text)

        if result:
            assert result[0].sentiment in (Sentiment.POSITIVE, Sentiment.VERY_POSITIVE)


# =============================================================================
# SENTENCE ANALYSIS TESTS
# =============================================================================


class TestSentenceAnalysis:
    """Tests for sentence-level analysis."""

    def test_sentence_splitting(self, analyzer):
        """Test sentences are split correctly."""
        text = "First sentence. Second sentence! Third sentence?"
        results = analyzer.analyze_sentences(text)

        assert len(results) == 3

    def test_sentence_sentiment(self, analyzer):
        """Test each sentence gets sentiment."""
        text = "The company is doing great. However, there are some problems."
        results = analyzer.analyze_sentences(text)

        assert len(results) == 2
        # First should be positive, second negative
        assert results[0][1].score > results[1][1].score

    def test_short_sentences_skipped(self, analyzer):
        """Test very short sentences are skipped."""
        text = "OK. This is a longer sentence with more content."
        results = analyzer.analyze_sentences(text)

        # "OK." should be skipped
        assert len(results) == 1


# =============================================================================
# COMPLETE ANALYSIS TESTS
# =============================================================================


class TestCompleteAnalysis:
    """Tests for complete content analysis."""

    def test_analyze_returns_all_components(self, analyzer):
        """Test analyze returns all components."""
        text = "Acme Corp reported excellent growth. CEO John Smith is optimistic."
        result = analyzer.analyze(text)

        assert isinstance(result, ContentSentiment)
        assert result.overall is not None
        assert result.tone is not None
        assert isinstance(result.entities, list)
        assert isinstance(result.sentence_sentiments, list)

    def test_sentiment_summary(self, analyzer):
        """Test sentiment summary generation."""
        text = "The company achieved great success with innovative products."
        summary = analyzer.get_sentiment_summary(text)

        assert "overall_sentiment" in summary
        assert "overall_score" in summary
        assert "confidence" in summary
        assert "tone" in summary
        assert "positive_words" in summary
        assert "negative_words" in summary
        assert "sentence_breakdown" in summary


# =============================================================================
# SINGLETON TESTS
# =============================================================================


class TestSingleton:
    """Tests for singleton access."""

    def test_get_analyzer_returns_same(self):
        """Test get_sentiment_analyzer returns same instance."""
        a1 = get_sentiment_analyzer()
        a2 = get_sentiment_analyzer()
        assert a1 is a2

    def test_reset_analyzer(self):
        """Test reset creates new instance."""
        a1 = get_sentiment_analyzer()
        reset_sentiment_analyzer()
        a2 = get_sentiment_analyzer()
        assert a1 is not a2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_analyze_sentiment_function(self):
        """Test analyze_sentiment convenience function."""
        result = analyze_sentiment("Great product with excellent features.")
        assert isinstance(result, SentimentResult)
        assert result.is_positive

    def test_analyze_tone_function(self):
        """Test analyze_tone convenience function."""
        result = analyze_tone("Pursuant to the agreement, we shall proceed.")
        assert isinstance(result, ToneResult)
        assert result.primary_tone == Tone.FORMAL

    def test_analyze_content_function(self):
        """Test analyze_content convenience function."""
        result = analyze_content("The company is doing well.")
        assert isinstance(result, ContentSentiment)

    def test_get_sentiment_summary_function(self):
        """Test get_sentiment_summary convenience function."""
        summary = get_sentiment_summary("Excellent results this quarter.")
        assert isinstance(summary, dict)
        assert "overall_sentiment" in summary


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_text(self, analyzer):
        """Test empty text handling."""
        result = analyzer.analyze_sentiment("")
        assert result.sentiment == Sentiment.NEUTRAL
        assert result.score == 0.0

    def test_single_word(self, analyzer):
        """Test single word handling."""
        result = analyzer.analyze_sentiment("excellent")
        assert result.is_positive

    def test_mixed_sentiment(self, analyzer):
        """Test mixed sentiment text."""
        text = "The product has excellent features but terrible customer service."
        result = analyzer.analyze_sentiment(text)

        # Should have both positive and negative words
        assert len(result.positive_words) > 0
        assert len(result.negative_words) > 0

    def test_special_characters(self, analyzer):
        """Test text with special characters."""
        text = "Great!!! Amazing!!! #awesome @company"
        result = analyzer.analyze_sentiment(text)
        assert result.is_positive

    def test_numbers_in_text(self, analyzer):
        """Test text with numbers."""
        text = "Revenue grew 50% with strong Q4 2024 results."
        result = analyzer.analyze_sentiment(text)
        assert "strong" in result.positive_words


# =============================================================================
# CONFIDENCE TESTS
# =============================================================================


class TestConfidence:
    """Tests for confidence scoring."""

    def test_high_confidence_many_words(self, analyzer):
        """Test high confidence with many sentiment words."""
        text = "Excellent outstanding amazing great wonderful fantastic superb brilliant."
        result = analyzer.analyze_sentiment(text)

        assert result.confidence >= 0.8

    def test_low_confidence_few_words(self, analyzer):
        """Test low confidence with few sentiment words."""
        text = "The meeting is scheduled for tomorrow."
        result = analyzer.analyze_sentiment(text)

        assert result.confidence < 0.5
