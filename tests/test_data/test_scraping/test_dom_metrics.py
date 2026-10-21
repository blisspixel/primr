"""Differential scoring and bounded traversal for untrusted nested HTML."""

from html import escape

import pytest
from bs4 import BeautifulSoup, Tag
from hypothesis import given
from hypothesis import strategies as st

from primr.data.scraping.content import _find_content_rich_element, extract_main_content
from primr.data.scraping.dom_metrics import link_density, structured_score, subtree_metrics
from primr.data.scraping.structured_content import extract_structured_content, find_main_content


def reference_score(element):
    text_len = len(element.get_text(strip=True))
    if text_len < 100:
        return 0
    score = text_len + len(element.find_all("p")) * 50 + len(element.find_all(["ul", "ol"])) * 30
    score += len(element.find_all(["h1", "h2", "h3", "h4"])) * 40
    score -= (
        len(element.find_all("a")) * 5
        + len(element.find_all("button")) * 20
        + len(element.find_all("form")) * 50
    )
    density = sum(len(a.get_text(strip=True)) for a in element.find_all("a")) / text_len
    score *= 0.3 if density > 0.5 else 0.6 if density > 0.3 else 1
    classes = " ".join(element.get("class", []) or []).lower()
    if any(word in classes for word in ("nav", "menu", "sidebar", "footer", "header")):
        score *= 0.2
    return max(0, score)


leaf = st.text(alphabet="abc xyz\n\t<>&", min_size=1, max_size=200).map(escape)
html_trees = st.recursive(
    leaf,
    lambda child: st.tuples(
        st.sampled_from(["div", "p", "a", "ul", "li", "h2", "button", "form", "section"]),
        st.lists(child, min_size=1, max_size=4),
    ).map(lambda pair: f"<{pair[0]}>" + "".join(pair[1]) + f"</{pair[0]}>"),
    max_leaves=20,
)


@given(html_trees)
def test_metrics_match_existing_text_counts_and_scores(html):
    soup = BeautifulSoup(html, "html.parser")
    metrics = subtree_metrics(soup)
    for element in soup.find_all(True):
        item = metrics[id(element)]
        assert item.text_length == len(element.get_text(strip=True))
        assert item.paragraphs == len(element.find_all("p"))
        assert item.link_text_length == sum(
            len(a.get_text(strip=True)) for a in element.find_all("a")
        )
        assert link_density(item) == item.link_text_length / max(item.text_length, 1)
        assert structured_score(element, item) == reference_score(element)


@pytest.mark.parametrize("selector", [_find_content_rich_element, find_main_content])
def test_bulk_scoring_does_not_rescan_nested_descendant_text(monkeypatch, selector):
    soup = BeautifulSoup("<div>" * 100 + "x" * 250 + "</div>" * 100, "html.parser")

    def forbidden(*args, **kwargs):
        raise AssertionError("Bulk scoring must use the single metrics pass")

    monkeypatch.setattr(Tag, "get_text", forbidden)
    assert selector(soup) is soup.div


def test_deep_document_is_rejected_before_pruning_or_scoring():
    raw = ("<div>" * 10_000 + "x" * 250 + "</div>" * 10_000).encode()
    assert extract_main_content(raw) == ""
    structured = extract_structured_content(raw, "https://example.com")
    assert structured.text == ""
    assert "structure_budget_exceeded" in structured.quality.flags


def test_node_budget_rejects_wide_markup(monkeypatch):
    monkeypatch.setattr("primr.data.scraping.dom_metrics.MAX_DOM_NODES", 25)
    assert extract_main_content(b"<div>" + b"<p>hello</p>" * 50 + b"</div>") == ""


def test_comments_and_scripts_do_not_change_text_scoring():
    soup = BeautifulSoup(
        "<div><!--comment--><script>hidden</script><p>visible</p></div>", "html.parser"
    )
    assert subtree_metrics(soup)[id(soup.div)].text_length == len("visible")
