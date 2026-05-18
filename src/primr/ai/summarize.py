"""
Content summarization using AI.
"""

from collections.abc import Callable
import json
import os
from pathlib import Path
import time

from primr.ai.llm import llm
from primr.config.env import load_primr_env
from primr.utils.content_sanitizer import sanitize_for_llm
from primr.utils.formatting import deduplicate_content, get_deduplication_stats
from primr.utils.logging_config import get_logger

load_primr_env()

logger = get_logger("summarize")

PROMPTS_FILE = Path(__file__).parent.parent / "config" / "prompts.json"
with open(PROMPTS_FILE, encoding="utf-8") as f:
    PROMPTS = json.load(f)

_BATCH_SUMMARY_PAGE_THRESHOLD = 12
_BATCH_MAX_PAGES = 8
_BATCH_MAX_CHARS = 28_000
_BATCH_PAGE_CHAR_LIMIT = 4_000
_PER_PAGE_MIN_LENGTH = 80
_DEFAULT_RETRIES = 3

SummaryFn = Callable[[str, int], str]


def generate_prompt(template_name, **kwargs):
    """Loads a prompt from prompts.json and formats it with dynamic values."""
    if template_name not in PROMPTS:
        raise ValueError(f"Prompt '{template_name}' not found")
    return PROMPTS[template_name].format(**kwargs)


def _prepare_page_for_summary(raw_text: str, website_source: str) -> str:
    """Deduplicate/sanitize a page and clamp size for summarization."""
    deduped_text = deduplicate_content(raw_text)
    stats = get_deduplication_stats(raw_text, deduped_text)
    if stats["line_reduction_percent"] > 5:
        logger.debug(
            f"Deduplication: {stats['lines_removed']} lines removed "
            f"({stats['line_reduction_percent']}% reduction)"
        )

    sanitized_text, sanitization_issues = sanitize_for_llm(deduped_text)
    if sanitization_issues:
        logger.info(
            f"Content sanitization: {len(sanitization_issues)} issues detected in {website_source}"
        )

    if len(sanitized_text) > _BATCH_PAGE_CHAR_LIMIT:
        return sanitized_text[:_BATCH_PAGE_CHAR_LIMIT]
    return sanitized_text


def _build_summary_batches(pages: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Pack pages into bounded-size batches to reduce LLM call count."""
    batches: list[list[tuple[str, str]]] = []
    current_batch: list[tuple[str, str]] = []
    current_chars = 0

    for page in pages:
        _, text = page
        should_flush = (
            len(current_batch) >= _BATCH_MAX_PAGES or (current_chars + len(text)) > _BATCH_MAX_CHARS
        )
        if should_flush and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0

        current_batch.append(page)
        current_chars += len(text)

    if current_batch:
        batches.append(current_batch)

    return batches


def _invoke_default_summary_model(prompt: str, _: int) -> str:
    response = llm(prompt, model_type="scraping", thinking_level="low", streaming=False)
    return response.strip()


def _summarize_with_callback(
    content: str,
    *,
    summarize_fn: SummaryFn,
    retries: int = _DEFAULT_RETRIES,
    min_length: int = 200,
) -> str:
    """Attempts summarization multiple times until valid output is received."""
    attempt = 0
    response_text = ""

    while attempt < retries:
        try:
            response_text = summarize_fn(content, min_length).strip()
            if response_text and len(response_text) >= min_length:
                return response_text
        except Exception as e:
            logger.warning(f"AI summarization failed: {e}", exc_info=True)

        attempt += 1
        if attempt < retries:
            time.sleep(5)

    if response_text:
        logger.warning(
            f"Summarization returned short response ({len(response_text)} chars), using it anyway"
        )
        return response_text
    return ""


def _summarize_page(
    company_name: str,
    company_website: str | None,
    website_source: str,
    prepared_text: str,
    *,
    summarize_fn: SummaryFn,
) -> str:
    """Summarize a single page into factual bullets."""
    summary_prompt = generate_prompt(
        "scraped_website_summary",
        company_name=company_name,
        company_website=company_website or "N/A",
        website_source=website_source,
    )
    summarized_text = _summarize_with_callback(
        summary_prompt + "\n\n" + prepared_text,
        summarize_fn=summarize_fn,
        min_length=_PER_PAGE_MIN_LENGTH,
    )

    if not summarized_text.strip():
        return f"### Source: {website_source}\nNo meaningful content found.\n"
    return f"### Source: {website_source}\n{summarized_text}\n"


def _summarize_batch(
    company_name: str,
    company_website: str | None,
    batch_pages: list[tuple[str, str]],
    *,
    summarize_fn: SummaryFn,
) -> str:
    """Summarize several pages in one call with source-separated output."""
    sources_block = "\n\n".join(f"[Source: {source}]\n{text}" for source, text in batch_pages)

    batch_prompt = f"""Extract high-signal facts about {company_name} ({company_website or "N/A"}) from these webpages.

Return one section per source using this exact header format:
### Source: <URL>

For each source section, include only:
- concrete facts from that source
- names, numbers, dates, products, customers, partnerships, certifications, leadership
- short direct quotes when present, wrapped in quotation marks

Rules:
- Stay source-faithful, do not mix facts between sources
- Do not infer beyond page evidence
- Skip generic marketing language
- Keep output dense and factual

Webpage content:
{sources_block}
"""

    return _summarize_with_callback(batch_prompt, summarize_fn=summarize_fn, min_length=240)


def _synthesize_site_insights(
    company_name: str,
    company_website: str | None,
    source_summaries: str,
    *,
    summarize_fn: SummaryFn,
) -> str:
    """Generate a single cross-page synthesis from per-source summaries."""
    synthesis_prompt = f"""You are preparing a company research brief for {company_name} ({company_website or "N/A"}).
You have already extracted source-faithful facts from many website pages.

Create a compact synthesis in this format:

## Cross-Page Synthesis
### Latest Signals
- most recent dated announcements, releases, awards, leadership moves
### Offerings and Business Model
- products/services, target customers, monetization clues
### Go-To-Market and Partnerships
- channels, partner ecosystem, integrations, customer evidence
### Strategic Risks and Constraints
- dependencies, concentration, missing disclosures, execution risks
### Open Questions To Validate
- 5-8 concrete questions for follow-up diligence

Rules:
- Use only facts in the provided summaries
- Include URL citations inline like [Source: URL] for non-obvious claims
- Prefer recency and specificity over generic statements

Source summaries:
{source_summaries}
"""
    return _summarize_with_callback(synthesis_prompt, summarize_fn=summarize_fn, min_length=500)


def summarize_scraped_content_with_callback(
    company_name,
    company_website,
    scraped_data,
    folder_path,
    *,
    summarize_fn: SummaryFn,
    on_progress: Callable[[int, int, str], None] | None = None,
    output_filename: str = "scraped_website_summary.txt",
):
    """Summarize scraped content using a caller-provided model backend."""
    summary_filename = os.path.join(folder_path, output_filename)

    with open(summary_filename, "w", encoding="utf-8") as f:
        f.write(f"## Website Insights for {company_name}\n\n")

    all_summaries: list[str] = []
    total = len(scraped_data)
    prepared_pages: list[tuple[str, str]] = []

    for i, (website_source, raw_text) in enumerate(scraped_data.items()):
        logger.debug(f"Processing: {website_source}")
        if on_progress:
            on_progress(i + 1, total, website_source)

        if not raw_text.strip():
            continue

        prepared_pages.append((website_source, _prepare_page_for_summary(raw_text, website_source)))

    if total <= _BATCH_SUMMARY_PAGE_THRESHOLD:
        for website_source, prepared_text in prepared_pages:
            formatted_summary = _summarize_page(
                company_name,
                company_website,
                website_source,
                prepared_text,
                summarize_fn=summarize_fn,
            )
            with open(summary_filename, "a", encoding="utf-8") as f:
                f.write(formatted_summary + "\n")
            all_summaries.append(formatted_summary)
    else:
        batches = _build_summary_batches(prepared_pages)
        logger.info(
            "Using batched website summarization for speed",
            extra={"pages": total, "batches": len(batches)},
        )

        for idx, batch_pages in enumerate(batches, start=1):
            batch_summary = _summarize_batch(
                company_name,
                company_website,
                batch_pages,
                summarize_fn=summarize_fn,
            )
            section = f"## Batch {idx}/{len(batches)}\n{batch_summary}\n"
            with open(summary_filename, "a", encoding="utf-8") as f:
                f.write(section + "\n")
            all_summaries.append(section)

        synthesis = _synthesize_site_insights(
            company_name,
            company_website,
            "\n\n".join(all_summaries),
            summarize_fn=summarize_fn,
        )
        if synthesis.strip():
            synthesis_section = f"{synthesis}\n"
            with open(summary_filename, "a", encoding="utf-8") as f:
                f.write(synthesis_section + "\n")
            all_summaries.append(synthesis_section)

    logger.debug(f"Insights saved to: {summary_filename}")
    return "\n".join(all_summaries)


def summarize_scraped_content(
    company_name,
    company_website,
    scraped_data,
    folder_path,
    on_progress: Callable[[int, int, str], None] | None = None,
):
    """Summarizes key insights from scraped website data."""
    return summarize_scraped_content_with_callback(
        company_name,
        company_website,
        scraped_data,
        folder_path,
        summarize_fn=_invoke_default_summary_model,
        on_progress=on_progress,
    )


def summarize_scraped_content_local(
    company_name,
    company_website,
    scraped_data,
    folder_path,
    *,
    model: str,
    base_url: str | None = None,
    api_key_env: str = "LOCAL_LLM_API_KEY",
    on_progress: Callable[[int, int, str], None] | None = None,
    output_filename: str = "scraped_website_summary.local.txt",
):
    """Summarize scraped content with a local OpenAI-compatible backend."""
    from primr.ai.openai_compatible_client import chat_completion

    def _summarize_locally(prompt: str, min_length: int) -> str:
        result = chat_completion(
            prompt,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            temperature=0.1,
            max_tokens=max(900, min_length + 300),
        )
        return result.text

    return summarize_scraped_content_with_callback(
        company_name,
        company_website,
        scraped_data,
        folder_path,
        summarize_fn=_summarize_locally,
        on_progress=on_progress,
        output_filename=output_filename,
    )


def summarize_with_retries(content, retries=_DEFAULT_RETRIES, min_length=200):
    """Attempts AI summarization multiple times until valid output is received."""
    return _summarize_with_callback(
        content,
        summarize_fn=_invoke_default_summary_model,
        retries=retries,
        min_length=min_length,
    )
