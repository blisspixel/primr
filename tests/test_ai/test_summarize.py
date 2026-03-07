from unittest.mock import patch

from primr.ai.summarize import summarize_scraped_content


def _make_scraped_data(count: int) -> dict[str, str]:
    return {
        f"https://example.com/page-{i}": f"Page {i} content with facts, dates, and product details."
        for i in range(count)
    }


def test_summarize_scraped_content_small_uses_per_page_min_length(tmp_path):
    scraped_data = _make_scraped_data(2)

    with patch("primr.ai.summarize.summarize_with_retries", return_value="facts") as mock_sum:
        summarize_scraped_content("Acme", "https://example.com", scraped_data, str(tmp_path))

    assert mock_sum.call_count == 2
    for call in mock_sum.call_args_list:
        assert call.kwargs["min_length"] == 80


def test_summarize_scraped_content_large_uses_batched_calls(tmp_path):
    scraped_data = _make_scraped_data(20)

    def _response(prompt: str, retries=3, min_length=200):
        if "Create a compact synthesis" in prompt:
            return "## Cross-Page Synthesis\n- Synthesized"
        return "### Source: https://example.com/page\n- fact"

    with patch("primr.ai.summarize.summarize_with_retries", side_effect=_response) as mock_sum:
        summarize_scraped_content("Acme", "https://example.com", scraped_data, str(tmp_path))

    # 20 pages -> 3 batches (8, 8, 4) + 1 synthesis call
    assert mock_sum.call_count == 4
    min_lengths = [call.kwargs["min_length"] for call in mock_sum.call_args_list]
    assert min_lengths == [240, 240, 240, 500]
