"""
Content summarization using AI.
"""

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from primr.ai.llm import llm
from primr.config.config import MAX_RETRIES
from primr.utils.formatting import deduplicate_content, get_deduplication_stats
from primr.utils.logging_config import get_logger

load_dotenv()

logger = get_logger("summarize")

# Load AI prompt templates from package config directory
PROMPTS_FILE = Path(__file__).parent.parent / "config" / "prompts.json"
with open(PROMPTS_FILE, encoding="utf-8") as f:
    PROMPTS = json.load(f)


def generate_prompt(template_name, **kwargs):
    """Loads a prompt from prompts.json and formats it with dynamic values."""
    if template_name not in PROMPTS:
        raise ValueError(f"Prompt '{template_name}' not found")
    return PROMPTS[template_name].format(**kwargs)


def summarize_scraped_content(company_name, company_website, scraped_data, folder_path, on_progress=None):
    """Summarizes key insights from scraped website data.

    Args:
        company_name: Name of the company
        company_website: Company website URL
        scraped_data: Dict mapping URL to raw text content
        folder_path: Path to save output files
        on_progress: Optional callback(current, total, url) for progress updates
    """
    summary_filename = os.path.join(folder_path, "scraped_website_summary.txt")

    with open(summary_filename, "w", encoding="utf-8") as f:
        f.write(f"## Website Insights for {company_name}\n\n")

    all_summaries = []
    total = len(scraped_data)

    for i, (website_source, raw_text) in enumerate(scraped_data.items()):
        logger.debug(f"Processing: {website_source}")

        # Report progress
        if on_progress:
            on_progress(i + 1, total, website_source)

        if not raw_text.strip():
            formatted_summary = f"### Source: {website_source}\nNo meaningful content found.\n"
        else:
            # Deduplicate content to reduce token usage
            deduped_text = deduplicate_content(raw_text)
            stats = get_deduplication_stats(raw_text, deduped_text)
            if stats["line_reduction_percent"] > 5:
                logger.debug(
                    f"Deduplication: {stats['lines_removed']} lines removed "
                    f"({stats['line_reduction_percent']}% reduction)"
                )

            summary_prompt = generate_prompt(
                "scraped_website_summary",
                company_name=company_name,
                company_website=company_website or "N/A",
                website_source=website_source
            )

            summarized_text = summarize_with_retries(summary_prompt + "\n\n" + deduped_text)

            if not summarized_text.strip():
                formatted_summary = f"### Source: {website_source}\nNo meaningful content found.\n"
            else:
                formatted_summary = f"### Source: {website_source}\n{summarized_text}\n"

        with open(summary_filename, "a", encoding="utf-8") as f:
            f.write(formatted_summary + "\n")

        all_summaries.append(formatted_summary)

    logger.debug(f"Insights saved to: {summary_filename}")
    return "\n".join(all_summaries)


def summarize_with_retries(content, retries=MAX_RETRIES, min_length=200):
    """Attempts AI summarization multiple times until valid output is received."""
    attempt = 0
    response_text = ""

    while attempt < retries:
        try:
            # Use Flash model for scraping summaries (cheap, fast)
            response = llm(content, model_type="scraping", thinking_level="low", streaming=False)
            response_text = response.strip()

            if response_text and len(response_text) >= min_length:
                return response_text

        except Exception as e:
            logger.warning(f"AI summarization failed: {e}")

        attempt += 1
        if attempt < retries:
            time.sleep(5)

    return "[ERROR] AI summarization failed after multiple attempts."
