"""
Robust JSON parser for QA responses with multiple fallback strategies.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class SimpleJSONParser:
    """
    Robust JSON parser that handles various response formats from AI models.

    Supports:
    - Markdown-wrapped JSON (```json ... ```)
    - Inline JSON objects
    - Malformed responses with regex extraction
    - Multiple fallback strategies
    """

    def __init__(self):
        """Initialize the JSON parser."""
        self.extraction_attempts = 0
        self.successful_extractions = 0

    def parse_qa_response(self, response: str) -> dict[str, Any] | None:
        """
        Parse QA response into structured data.

        Args:
            response: Raw AI response text

        Returns:
            Parsed JSON data or None if parsing fails completely
        """
        self.extraction_attempts += 1

        try:
            # Clean up the response
            response = response.strip()

            if not response:
                logger.warning("Empty response provided to JSON parser")
                return None

            # Try different extraction strategies
            json_str = self._extract_json_from_response(response)

            if not json_str:
                logger.warning("Could not extract JSON from response")
                return None

            # Parse the extracted JSON
            data = json.loads(json_str)

            # Validate the structure
            if self._validate_qa_structure(data):
                self.successful_extractions += 1
                logger.debug("Successfully parsed and validated QA response")
                return data
            else:
                logger.warning("JSON structure validation failed")
                return None

        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON: {e}")
            return None

    def extract_with_regex_fallback(self, response: str) -> dict[str, Any]:
        """
        Extract key information using regex patterns when JSON parsing fails.

        Args:
            response: Raw AI response text

        Returns:
            Dictionary with extracted information
        """
        logger.info("Using regex fallback for information extraction")

        # Initialize result structure
        result = {
            "ready_for_use": False,
            "confidence_level": "low",
            "key_strengths": [],
            "areas_for_improvement": [],
            "recommendation": "Assessment completed but response format was unclear",
        }

        # Extract ready_for_use
        ready_match = re.search(r'"ready_for_use":\s*(true|false)', response, re.IGNORECASE)
        if ready_match:
            result["ready_for_use"] = ready_match.group(1).lower() == "true"

        # Extract confidence_level
        confidence_match = re.search(
            r'"confidence_level":\s*"(high|medium|low)"', response, re.IGNORECASE
        )
        if confidence_match:
            result["confidence_level"] = confidence_match.group(1).lower()

        # Extract recommendation
        recommendation_match = re.search(r'"recommendation":\s*"([^"]+)"', response)
        if recommendation_match:
            result["recommendation"] = recommendation_match.group(1)

        # Extract key_strengths array
        strengths_match = re.search(r'"key_strengths":\s*\[(.*?)\]', response, re.DOTALL)
        if strengths_match:
            strengths_text = strengths_match.group(1)
            strength_items = re.findall(r'"([^"]+)"', strengths_text)
            result["key_strengths"] = strength_items[:5]  # Limit to 5 items

        # Extract areas_for_improvement array
        improvements_match = re.search(r'"areas_for_improvement":\s*\[(.*?)\]', response, re.DOTALL)
        if improvements_match:
            improvements_text = improvements_match.group(1)
            improvement_items = re.findall(r'"([^"]+)"', improvements_text)
            result["areas_for_improvement"] = improvement_items[:5]  # Limit to 5 items

        # Best-effort extraction for dimension scores block
        scores_match = re.search(r'"scores"\s*:\s*\{([^}]+)\}', response, re.DOTALL)
        if scores_match:
            score_pairs = re.findall(r'"(\w+)"\s*:\s*(\d+)', scores_match.group(1))
            if score_pairs:
                result["scores"] = {k: int(v) for k, v in score_pairs}

        # Fallback content analysis if arrays are empty
        if not result["key_strengths"]:
            result["key_strengths"] = self._extract_strengths_from_text(response)

        if not result["areas_for_improvement"]:
            result["areas_for_improvement"] = self._extract_improvements_from_text(response)

        return result

    def _extract_json_from_response(self, response: str) -> str | None:
        """Extract JSON string from various response formats."""

        # Strategy 1: Markdown code blocks with json language
        if "```json" in response:
            json_start = response.find("```json") + 7
            json_end = response.find("```", json_start)
            if json_end != -1:
                return response[json_start:json_end].strip()
            else:
                # Handle case where closing ``` is missing
                return response[json_start:].strip()

        # Strategy 2: Generic code blocks
        if "```" in response:
            json_start = response.find("```") + 3
            # Skip language identifier if present
            newline_pos = response.find("\n", json_start)
            if newline_pos != -1:
                json_start = newline_pos + 1

            json_end = response.find("```", json_start)
            if json_end != -1:
                potential_json = response[json_start:json_end].strip()
                if potential_json.startswith("{") and potential_json.endswith("}"):
                    return potential_json

        # Strategy 3: Find JSON object boundaries with proper brace matching
        json_start = response.find("{")
        if json_start != -1:
            brace_count = 0
            json_end = json_start

            for i, char in enumerate(response[json_start:], json_start):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break

            if brace_count == 0:
                return response[json_start:json_end]

        # Strategy 4: Look for JSON-like patterns without proper braces
        json_pattern = re.search(r'\{[^{}]*"ready_for_use"[^{}]*\}', response, re.DOTALL)
        if json_pattern:
            return json_pattern.group(0)

        return None

    def _validate_qa_structure(self, data: dict[str, Any]) -> bool:
        """
        Validate that the parsed JSON has the expected QA structure.

        Args:
            data: Parsed JSON data

        Returns:
            True if structure is valid, False otherwise
        """
        required_fields = [
            "ready_for_use",
            "confidence_level",
            "key_strengths",
            "areas_for_improvement",
            "recommendation",
        ]

        # Check all required fields are present
        for field in required_fields:
            if field not in data:
                logger.warning(f"Missing required field: {field}")
                return False

        # Validate field types and values
        if not isinstance(data["ready_for_use"], bool):
            logger.warning("ready_for_use must be boolean")
            return False

        if data["confidence_level"] not in ["high", "medium", "low"]:
            logger.warning(f"Invalid confidence_level: {data['confidence_level']}")
            return False

        if not isinstance(data["key_strengths"], list):
            logger.warning("key_strengths must be a list")
            return False

        if not isinstance(data["areas_for_improvement"], list):
            logger.warning("areas_for_improvement must be a list")
            return False

        if not isinstance(data["recommendation"], str) or not data["recommendation"].strip():
            logger.warning("recommendation must be a non-empty string")
            return False

        # Optional: validate scores if present (absence is OK — backward compat)
        if "scores" in data:
            if not isinstance(data["scores"], dict):
                logger.warning("scores must be a dict if present, ignoring")
                del data["scores"]  # Remove invalid scores so downstream gets None
            else:
                for key, val in data["scores"].items():
                    if not isinstance(val, (int, float)):
                        logger.warning(f"scores.{key} is not numeric, ignoring all scores")
                        del data["scores"]
                        break

        return True

    def _extract_strengths_from_text(self, response: str) -> list[str]:
        """Extract strengths from text using keyword analysis."""
        strengths = []
        response_lower = response.lower()

        # Look for positive indicators
        positive_patterns = [
            ("well-structured", "Report demonstrates good structural organization"),
            ("clear strategic", "Strategic analysis is clearly presented"),
            ("comprehensive analysis", "Comprehensive coverage of key topics"),
            ("good citations", "Citations are properly formatted and relevant"),
            ("actionable insights", "Provides actionable business insights"),
            ("thorough", "Thorough analysis of the subject matter"),
            ("detailed", "Detailed examination of key factors"),
            ("extensive", "Extensive research and data collection"),
        ]

        for pattern, description in positive_patterns:
            if pattern in response_lower:
                strengths.append(description)
                if len(strengths) >= 3:  # Limit to 3 strengths
                    break

        return strengths

    def _extract_improvements_from_text(self, response: str) -> list[str]:
        """Extract improvement areas from text using keyword analysis."""
        improvements = []
        response_lower = response.lower()

        # Look for improvement indicators
        improvement_patterns = [
            ("missing citations", "Some claims could benefit from additional citations"),
            ("unclear", "Certain sections could be clearer and more specific"),
            ("needs more", "Additional detail would strengthen the analysis"),
            ("insufficient", "Some areas need more comprehensive coverage"),
            ("contradictions", "Internal consistency could be improved"),
            ("inconsistent", "Consistency across sections needs attention"),
            ("gaps", "Some analytical gaps should be addressed"),
        ]

        for pattern, description in improvement_patterns:
            if pattern in response_lower:
                improvements.append(description)
                if len(improvements) >= 3:  # Limit to 3 improvements
                    break

        return improvements

    def get_parsing_stats(self) -> dict[str, Any]:
        """
        Get statistics about parsing performance.

        Returns:
            Dictionary with parsing statistics
        """
        success_rate = (
            (self.successful_extractions / self.extraction_attempts * 100)
            if self.extraction_attempts > 0
            else 0
        )

        return {
            "total_attempts": self.extraction_attempts,
            "successful_extractions": self.successful_extractions,
            "success_rate": round(success_rate, 2),
            "failed_extractions": self.extraction_attempts - self.successful_extractions,
        }

    def reset_stats(self) -> None:
        """Reset parsing statistics."""
        self.extraction_attempts = 0
        self.successful_extractions = 0
