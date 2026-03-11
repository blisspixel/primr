"""
AI-based report grading and refinement.
"""

import re
import time

from primr.ai.llm import llm
from primr.config.config import GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT, MAX_RETRIES
from primr.utils.logging_config import get_logger

logger = get_logger("grading")


def grade_report(
    section_text,
    section_name,
    company_name,
    company_website,
    draft_overview,
    scraped_insights,
    retries=MAX_RETRIES,
):
    """
    Grades a section of a business research report.
    Returns (score, needs_research, reason).
    """
    grading_prompt = f"""
    You are a business analyst grading a research report section.
    **Provide a single numerical score (0-100)** based on the quality of the section.

    **Company Information:**
    - **Company Name:** {company_name}
    - **Website:** {company_website or "No website available"}
    - **Section Name:** {section_name}

    --- SECTION TEXT ---
    {section_text}
    --- END SECTION TEXT ---

    --- SCRAPED WEBSITE INSIGHTS ---
    {scraped_insights[:500]}
    --- END SCRAPED INSIGHTS ---

    **Grading Criteria (0-100 Scale):**
    1. **Clarity & Readability** – Is the section well-structured?
    2. **Completeness** – Does it cover critical aspects?
    3. **Insight Depth** – Does it provide meaningful business insights?
    4. **Accuracy** – Does it match the company's website information?

    **Respond in this exact format:**
    ```
    Grade: X
    Reason: [Concise reason why this score was given.]
    ```
    """

    attempt = 0
    while attempt < retries:
        try:
            response = llm(grading_prompt, model_type="fast", streaming=False).strip()

            match = re.search(r"Grade:\s*(\d+)", response)
            score = int(match.group(1)) if match else None

            reason_match = re.search(r"Reason:\s*(.*)", response, re.DOTALL)
            reason = reason_match.group(1).strip() if reason_match else "No reason provided."

            if score is None or not (0 <= score <= 100):
                raise ValueError("Invalid score extracted from AI response.")

            needs_research = score < GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT
            logger.info(
                f"Graded '{section_name}': {score}/100 (refinement: {'yes' if needs_research else 'no'})"
            )

            return score, needs_research, reason

        except Exception as e:
            logger.warning(f"Grading failed for '{section_name}': {e}")
            time.sleep(2)
            attempt += 1

    logger.warning(f"Grading unavailable for '{section_name}'")
    return None, False, "Grading unavailable"
