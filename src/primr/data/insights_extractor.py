"""
Insight extraction and synthesis from search and scraped data.
"""

import time
from typing import Any

from google import genai

from primr.config.config import GEMINI_API_KEY, MAX_RETRIES
from primr.config.env import load_primr_env
from primr.config.models import PrimrModels
from primr.utils.logging_config import get_logger

load_primr_env()

logger = get_logger("insights")

# Configure Google AI client
_client = genai.Client(api_key=GEMINI_API_KEY)


def generate_ai_response(prompt, retries=MAX_RETRIES, min_length=200):
    """Ensures we get a complete AI response."""
    attempt = 0
    response_text = ""

    while attempt < retries:
        try:
            response = _client.models.generate_content(
                model=PrimrModels.FAST_MODEL, contents=prompt
            )

            if not response or not hasattr(response, "text"):
                raise ValueError("AI response is invalid or missing text attribute.")

            response_text = response.text.strip()

            if response_text and len(response_text) >= min_length:
                return response_text

        except Exception as e:
            logger.warning(f"AI response failed: {e}", exc_info=True)

        attempt += 1
        if attempt < retries:
            time.sleep(5)

    return "[ERROR] AI response generation failed after multiple attempts."


def extract_insights(search_results, scraped_content):
    """
    Processes web search results, extracts key insights from each source,
    and synthesizes them into structured summaries.
    """
    if not isinstance(search_results, dict) or not search_results:
        return "[ERROR] No insights available."

    insights_summary = "**## Extracted Key Insights**\n\n"
    structured_insights: dict[str, Any] = {}

    for topic, sources in search_results.items():
        logger.debug(f"Analyzing sources for: {topic}")
        insights_summary += f"### {topic}\n"

        if not isinstance(sources, list) or not sources:
            insights_summary += "- [ERROR] No valid sources found.\n\n"
            continue

        valid_sources = [s for s in sources if isinstance(s, dict) and "url" in s and "title" in s]
        if not valid_sources:
            insights_summary += "- [ERROR] No usable sources retrieved.\n\n"
            continue

        combined_summaries = ""

        for source in valid_sources:
            url = source["url"]
            title = source["title"]
            raw_text = scraped_content.get(url, "")

            if not isinstance(raw_text, str) or len(raw_text) < 50:
                continue

            ai_prompt = f"""
            Extract **detailed and structured insights** from this company research source.
            Provide **financial trends, executive statements, product strategies**, and **competitive positioning**.

            **Title:** {title}
            **Source:** {url}
            **Extracted Content:** {raw_text[:2000]}

            - Use **detailed bullet points**.
            - Include **metrics, financial figures, and executive statements if available**.
            - Avoid **generic statements—be specific**.
            - Provide **real-world examples** of the company's market position.
            - Include **potential risks, challenges, and strategic opportunities**.
            """

            summary = generate_ai_response(ai_prompt)

            if topic not in structured_insights:
                structured_insights[topic] = []

            structured_insights[topic].append({"source": title, "url": url, "insights": summary})

            combined_summaries += f"- **{title}** ({url}): {summary}\n"

        insights_summary += f"**Summarized Insights Per Source:**\n{combined_summaries}\n\n"

    return insights_summary
