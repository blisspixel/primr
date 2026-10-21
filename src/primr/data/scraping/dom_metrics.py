"""Linear subtree metrics and structural budgets for HTML extraction."""

from __future__ import annotations

from dataclasses import dataclass

from bs4 import CData, NavigableString, Tag

MAX_DOM_NODES = 100_000
MAX_DOM_DEPTH = 128


@dataclass
class SubtreeMetrics:
    text_length: int = 0
    paragraphs: int = 0
    lists: int = 0
    headings: int = 0
    links: int = 0
    buttons: int = 0
    forms: int = 0
    link_text_length: int = 0


def subtree_metrics(root: Tag) -> dict[int, SubtreeMetrics]:
    """Use object identity, never Tag's recursive hash/equality operations.

    Text lengths match get_text(strip=True): stripped individual ordinary text
    nodes, without separators or comment/script/template string subclasses.
    Tag counts and link text include descendants, excluding the tag itself.
    """
    metrics: dict[int, SubtreeMetrics] = {}
    stack: list[tuple[Tag, bool, int]] = [(root, False, 0)]
    count = 1
    while stack:
        tag, finished, depth = stack.pop()
        if not finished:
            if depth > MAX_DOM_DEPTH:
                raise ValueError("HTML structure exceeds extraction budget")
            stack.append((tag, True, depth))
            for child in reversed(tag.contents):
                count += 1
                if count > MAX_DOM_NODES:
                    raise ValueError("HTML structure exceeds extraction budget")
                if isinstance(child, Tag):
                    stack.append((child, False, depth + 1))
            continue
        result = SubtreeMetrics()
        for child in tag.contents:
            if isinstance(child, Tag):
                item = metrics[id(child)]
                result.text_length += item.text_length
                result.paragraphs += item.paragraphs + (child.name == "p")
                result.lists += item.lists + (child.name in {"ul", "ol"})
                result.headings += item.headings + (child.name in {"h1", "h2", "h3", "h4"})
                result.links += item.links + (child.name == "a")
                result.buttons += item.buttons + (child.name == "button")
                result.forms += item.forms + (child.name == "form")
                result.link_text_length += item.link_text_length
                if child.name == "a":
                    result.link_text_length += item.text_length
            elif type(child) in {NavigableString, CData}:
                result.text_length += len(str(child).strip())
        metrics[id(tag)] = result
    return metrics


def link_density(metrics: SubtreeMetrics) -> float:
    """Keep link-density arithmetic shared by both content scorers."""
    return metrics.link_text_length / max(metrics.text_length, 1)


def structured_score(element: Tag, metrics: SubtreeMetrics) -> float:
    """Preserve structured selection weights without further subtree scans."""
    if metrics.text_length < 100:
        return 0.0
    score = float(
        metrics.text_length
        + metrics.paragraphs * 50
        + metrics.lists * 30
        + metrics.headings * 40
        - metrics.links * 5
        - metrics.buttons * 20
        - metrics.forms * 50
    )
    density = link_density(metrics)
    if density > 0.5:
        score *= 0.3
    elif density > 0.3:
        score *= 0.6
    classes = " ".join(element.get("class") or []).lower()
    if any(word in classes for word in ("nav", "menu", "sidebar", "footer", "header")):
        score *= 0.2
    return max(0, score)
