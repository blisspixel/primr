"""
Sentiment analysis for company research content.

This module provides:
- Text sentiment classification (positive/negative/neutral)
- Tone detection (formal, casual, promotional, etc.)
- Entity-level sentiment extraction
- Aggregated sentiment scoring
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from primr.utils.logging_config import get_logger

logger = get_logger("data.sentiment")


class Sentiment(Enum):
    """Sentiment classification."""

    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class Tone(Enum):
    """Text tone classification."""

    FORMAL = "formal"
    CASUAL = "casual"
    PROMOTIONAL = "promotional"
    TECHNICAL = "technical"
    NEUTRAL = "neutral"
    URGENT = "urgent"
    CONFIDENT = "confident"


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""

    sentiment: Sentiment
    score: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    positive_words: list[str] = field(default_factory=list)
    negative_words: list[str] = field(default_factory=list)

    @property
    def is_positive(self) -> bool:
        """Whether sentiment is positive."""
        return self.sentiment in (Sentiment.POSITIVE, Sentiment.VERY_POSITIVE)

    @property
    def is_negative(self) -> bool:
        """Whether sentiment is negative."""
        return self.sentiment in (Sentiment.NEGATIVE, Sentiment.VERY_NEGATIVE)


@dataclass
class ToneResult:
    """Result of tone analysis."""

    primary_tone: Tone
    secondary_tones: list[Tone] = field(default_factory=list)
    confidence: float = 0.0
    indicators: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class EntitySentiment:
    """Sentiment associated with a specific entity."""

    entity: str
    entity_type: str  # "company", "person", "product", etc.
    sentiment: Sentiment
    score: float
    context: str = ""  # Surrounding text


@dataclass
class ContentSentiment:
    """Complete sentiment analysis of content."""

    overall: SentimentResult
    tone: ToneResult
    entities: list[EntitySentiment] = field(default_factory=list)
    sentence_sentiments: list[tuple[str, SentimentResult]] = field(default_factory=list)


class SentimentAnalyzer:
    """
    Analyzes sentiment and tone in text content.

    Example:
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("The company reported excellent growth.")
        print(f"Sentiment: {result.overall.sentiment}")
        print(f"Tone: {result.tone.primary_tone}")
    """

    # Positive word lists by intensity
    VERY_POSITIVE_WORDS = {
        "excellent", "outstanding", "exceptional", "remarkable", "extraordinary",
        "phenomenal", "incredible", "amazing", "fantastic", "superb", "brilliant",
        "revolutionary", "groundbreaking", "transformative", "unprecedented",
    }

    POSITIVE_WORDS = {
        "good", "great", "strong", "positive", "successful", "growth", "profit",
        "increase", "improve", "innovative", "leading", "best", "top", "premier",
        "efficient", "effective", "reliable", "trusted", "quality", "value",
        "opportunity", "advantage", "benefit", "achieve", "accomplish", "win",
        "expand", "progress", "advance", "enhance", "optimize", "streamline",
        "robust", "solid", "stable", "healthy", "thriving", "flourishing",
    }

    NEGATIVE_WORDS = {
        "bad", "poor", "weak", "negative", "loss", "decline", "decrease",
        "problem", "issue", "concern", "risk", "threat", "challenge", "difficult",
        "fail", "failure", "struggle", "trouble", "worry", "uncertain",
        "slow", "delay", "setback", "obstacle", "barrier", "limitation",
        "expensive", "costly", "overpriced", "disappointing", "inadequate",
    }

    VERY_NEGATIVE_WORDS = {
        "terrible", "awful", "horrible", "disastrous", "catastrophic", "crisis",
        "collapse", "crash", "bankrupt", "fraud", "scandal", "lawsuit", "violation",
        "devastating", "critical", "severe", "alarming", "dangerous", "toxic",
    }

    # Tone indicators
    FORMAL_INDICATORS = {
        "pursuant", "hereby", "whereas", "therefore", "accordingly", "furthermore",
        "notwithstanding", "aforementioned", "herein", "thereto", "shall",
    }

    PROMOTIONAL_INDICATORS = {
        "best", "leading", "premier", "top", "exclusive", "limited", "special",
        "amazing", "incredible", "revolutionary", "game-changing", "world-class",
        "unmatched", "unparalleled", "cutting-edge", "state-of-the-art",
    }

    TECHNICAL_INDICATORS = {
        "algorithm", "infrastructure", "implementation", "architecture", "protocol",
        "framework", "integration", "optimization", "scalability", "deployment",
        "api", "sdk", "platform", "system", "module", "component", "interface",
    }

    URGENT_INDICATORS = {
        "urgent", "immediate", "critical", "asap", "now", "today", "deadline",
        "emergency", "priority", "important", "essential", "must", "required",
    }

    # Negation words that flip sentiment
    NEGATION_WORDS = {
        "not", "no", "never", "neither", "nobody", "nothing", "nowhere",
        "hardly", "barely", "scarcely", "without", "lack", "lacking",
        "don't", "doesn't", "didn't", "won't", "wouldn't", "couldn't",
        "shouldn't", "isn't", "aren't", "wasn't", "weren't", "haven't",
    }

    # Intensifiers
    INTENSIFIERS = {
        "very", "extremely", "highly", "incredibly", "exceptionally",
        "remarkably", "significantly", "substantially", "considerably",
    }

    def __init__(self):
        """Initialize the sentiment analyzer."""
        logger.debug("SentimentAnalyzer initialized")

    def analyze(self, text: str) -> ContentSentiment:
        """
        Perform complete sentiment analysis on text.

        Args:
            text: Text to analyze

        Returns:
            ContentSentiment with overall, tone, and entity sentiments
        """
        overall = self.analyze_sentiment(text)
        tone = self.analyze_tone(text)
        entities = self.extract_entity_sentiments(text)
        sentences = self.analyze_sentences(text)

        return ContentSentiment(
            overall=overall,
            tone=tone,
            entities=entities,
            sentence_sentiments=sentences,
        )

    def analyze_sentiment(self, text: str) -> SentimentResult:
        """
        Analyze overall sentiment of text.

        Args:
            text: Text to analyze

        Returns:
            SentimentResult with classification and score
        """
        text_lower = text.lower()
        words = self._tokenize(text_lower)

        # Count sentiment words
        very_pos = []
        pos = []
        neg = []
        very_neg = []

        # Check for negation context
        negation_window = 3  # Words after negation to flip
        negated_indices = set()

        for i, word in enumerate(words):
            if word in self.NEGATION_WORDS:
                for j in range(i + 1, min(i + negation_window + 1, len(words))):
                    negated_indices.add(j)

        for i, word in enumerate(words):
            is_negated = i in negated_indices

            if word in self.VERY_POSITIVE_WORDS:
                if is_negated:
                    neg.append(word)
                else:
                    very_pos.append(word)
            elif word in self.POSITIVE_WORDS:
                if is_negated:
                    neg.append(word)
                else:
                    pos.append(word)
            elif word in self.VERY_NEGATIVE_WORDS:
                if is_negated:
                    pos.append(word)
                else:
                    very_neg.append(word)
            elif word in self.NEGATIVE_WORDS:
                if is_negated:
                    pos.append(word)
                else:
                    neg.append(word)

        # Calculate score
        positive_score = len(very_pos) * 2 + len(pos)
        negative_score = len(very_neg) * 2 + len(neg)
        total_sentiment_words = positive_score + negative_score

        if total_sentiment_words == 0:
            score = 0.0
            confidence = 0.3
        else:
            score = (positive_score - negative_score) / total_sentiment_words
            confidence = min(total_sentiment_words / 10, 1.0)

        # Determine sentiment level
        if score >= 0.6:
            sentiment = Sentiment.VERY_POSITIVE
        elif score >= 0.2:
            sentiment = Sentiment.POSITIVE
        elif score <= -0.6:
            sentiment = Sentiment.VERY_NEGATIVE
        elif score <= -0.2:
            sentiment = Sentiment.NEGATIVE
        else:
            sentiment = Sentiment.NEUTRAL

        return SentimentResult(
            sentiment=sentiment,
            score=score,
            confidence=confidence,
            positive_words=very_pos + pos,
            negative_words=very_neg + neg,
        )

    def analyze_tone(self, text: str) -> ToneResult:
        """
        Analyze the tone of text.

        Args:
            text: Text to analyze

        Returns:
            ToneResult with primary and secondary tones
        """
        text_lower = text.lower()
        words = set(self._tokenize(text_lower))

        # Count indicators for each tone
        tone_scores: dict[Tone, tuple[int, list[str]]] = {}

        formal_matches = words & self.FORMAL_INDICATORS
        if formal_matches:
            tone_scores[Tone.FORMAL] = (len(formal_matches), list(formal_matches))

        promo_matches = words & self.PROMOTIONAL_INDICATORS
        if promo_matches:
            tone_scores[Tone.PROMOTIONAL] = (len(promo_matches), list(promo_matches))

        tech_matches = words & self.TECHNICAL_INDICATORS
        if tech_matches:
            tone_scores[Tone.TECHNICAL] = (len(tech_matches), list(tech_matches))

        urgent_matches = words & self.URGENT_INDICATORS
        if urgent_matches:
            tone_scores[Tone.URGENT] = (len(urgent_matches), list(urgent_matches))

        # Check for confident tone (first person + positive)
        if re.search(r'\b(we|our|us)\b', text_lower):
            confident_words = words & (self.POSITIVE_WORDS | self.VERY_POSITIVE_WORDS)
            if confident_words:
                tone_scores[Tone.CONFIDENT] = (len(confident_words), list(confident_words))

        if not tone_scores:
            return ToneResult(
                primary_tone=Tone.NEUTRAL,
                confidence=0.5,
            )

        # Sort by score
        sorted_tones = sorted(tone_scores.items(), key=lambda x: x[1][0], reverse=True)

        primary = sorted_tones[0][0]
        secondary = [t[0] for t in sorted_tones[1:3]]

        indicators = {t.value: words for t, (_, words) in tone_scores.items()}

        # Calculate confidence based on indicator count
        total_indicators = sum(score for score, _ in tone_scores.values())
        confidence = min(total_indicators / 5, 1.0)

        return ToneResult(
            primary_tone=primary,
            secondary_tones=secondary,
            confidence=confidence,
            indicators=indicators,
        )

    def extract_entity_sentiments(self, text: str) -> list[EntitySentiment]:
        """
        Extract sentiment associated with specific entities.

        Args:
            text: Text to analyze

        Returns:
            List of EntitySentiment for detected entities
        """
        entities = []
        sentences = self._split_sentences(text)

        for sentence in sentences:
            # Find company mentions
            company_patterns = [
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Inc|Corp|LLC|Ltd)',
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:reported|announced|said)',
            ]

            for pattern in company_patterns:
                matches = re.findall(pattern, sentence)
                for match in matches:
                    sentiment = self.analyze_sentiment(sentence)
                    entities.append(EntitySentiment(
                        entity=match,
                        entity_type="company",
                        sentiment=sentiment.sentiment,
                        score=sentiment.score,
                        context=sentence[:100],
                    ))

            # Find person mentions (CEO, CFO, etc.)
            person_patterns = [
                r'(?:CEO|CFO|CTO|President|Chairman)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
                r'([A-Z][a-z]+\s+[A-Z][a-z]+),?\s+(?:CEO|CFO|CTO|President)',
            ]

            for pattern in person_patterns:
                matches = re.findall(pattern, sentence)
                for match in matches:
                    sentiment = self.analyze_sentiment(sentence)
                    entities.append(EntitySentiment(
                        entity=match,
                        entity_type="person",
                        sentiment=sentiment.sentiment,
                        score=sentiment.score,
                        context=sentence[:100],
                    ))

        return entities

    def analyze_sentences(self, text: str) -> list[tuple[str, SentimentResult]]:
        """
        Analyze sentiment of individual sentences.

        Args:
            text: Text to analyze

        Returns:
            List of (sentence, SentimentResult) tuples
        """
        sentences = self._split_sentences(text)
        results = []

        for sentence in sentences:
            if len(sentence.strip()) > 10:  # Skip very short sentences
                sentiment = self.analyze_sentiment(sentence)
                results.append((sentence, sentiment))

        return results

    def get_sentiment_summary(self, text: str) -> dict[str, Any]:
        """
        Get a summary of sentiment analysis.

        Args:
            text: Text to analyze

        Returns:
            Dictionary with sentiment summary
        """
        result = self.analyze(text)

        # Count sentence sentiments
        pos_sentences = sum(1 for _, s in result.sentence_sentiments if s.is_positive)
        neg_sentences = sum(1 for _, s in result.sentence_sentiments if s.is_negative)
        neutral_sentences = len(result.sentence_sentiments) - pos_sentences - neg_sentences

        return {
            "overall_sentiment": result.overall.sentiment.value,
            "overall_score": round(result.overall.score, 2),
            "confidence": round(result.overall.confidence, 2),
            "tone": result.tone.primary_tone.value,
            "positive_words": result.overall.positive_words[:10],
            "negative_words": result.overall.negative_words[:10],
            "sentence_breakdown": {
                "positive": pos_sentences,
                "negative": neg_sentences,
                "neutral": neutral_sentences,
            },
            "entity_count": len(result.entities),
        }

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words."""
        # Simple word tokenization
        return re.findall(r'\b[a-z]+\b', text.lower())

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Simple sentence splitting
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]



# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_analyzer: SentimentAnalyzer | None = None


def get_sentiment_analyzer() -> SentimentAnalyzer:
    """
    Get the global sentiment analyzer instance.

    Returns:
        SentimentAnalyzer instance
    """
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentAnalyzer()
    return _analyzer


def reset_sentiment_analyzer() -> None:
    """Reset the global analyzer (useful for testing)."""
    global _analyzer
    _analyzer = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def analyze_sentiment(text: str) -> SentimentResult:
    """
    Analyze sentiment of text.

    Args:
        text: Text to analyze

    Returns:
        SentimentResult with classification and score
    """
    return get_sentiment_analyzer().analyze_sentiment(text)


def analyze_tone(text: str) -> ToneResult:
    """
    Analyze tone of text.

    Args:
        text: Text to analyze

    Returns:
        ToneResult with primary and secondary tones
    """
    return get_sentiment_analyzer().analyze_tone(text)


def analyze_content(text: str) -> ContentSentiment:
    """
    Perform complete sentiment analysis.

    Args:
        text: Text to analyze

    Returns:
        ContentSentiment with all analysis results
    """
    return get_sentiment_analyzer().analyze(text)


def get_sentiment_summary(text: str) -> dict[str, Any]:
    """
    Get a summary of sentiment analysis.

    Args:
        text: Text to analyze

    Returns:
        Dictionary with sentiment summary
    """
    return get_sentiment_analyzer().get_sentiment_summary(text)
