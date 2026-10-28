"""Writer section-envelope recovery at the section-parsing boundary (#263).

Valid envelopes parse cleanly, safely recoverable envelope errors are
repaired, and truncated or ambiguous output is flagged without dropping or
inventing text. Ambiguous output keeps its raw tags so the ship gate withholds
the polished DOCX.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hypothesis import given
from hypothesis import strategies as st

from primr.core.fast_mode_helpers import _parse_batch_sections
from primr.core.report_cleanup import _clean_fast_report_output
from primr.core.section_parsing import (
    ENVELOPE_AMBIGUOUS,
    ENVELOPE_OUTSIDE_TEXT,
    ENVELOPE_RECOVERED,
    ENVELOPE_TRUNCATED,
    _extract_generated_section_blocks,
    _parse_single_section,
    most_severe_envelope_issue,
    prefer_section_retry,
    section_retry_instruction,
    section_retry_reason,
)
from primr.output.artifact_validation import _validate_output_markdown
from primr.output.markdown_parser import ArtifactDetector
from primr.qa.report_analyzer import count_section_envelope_markers

BODY = "The company builds widgets."


@dataclass
class _Section:
    name: str
    id: str = "section"


EXEC = _Section("Executive Summary")

SINGLE_CASES = [
    (f"<section><title>Executive Summary</title><body>{BODY}</body></section>", None),
    (f"<section><title>Executive Summary</title> {BODY}</section>", ENVELOPE_RECOVERED),
    (f"<section><title>Executive Summary</title><body>{BODY}</section>", ENVELOPE_RECOVERED),
    (f"<section><title>Executive Summary</title> {BODY}</body></section>", ENVELOPE_RECOVERED),
    (f"<section><title>Executive Summary</title><body>{BODY}", ENVELOPE_TRUNCATED),
    (f"<section><title>Executive Summary</title><body>{BODY}</body>", ENVELOPE_RECOVERED),
    (f"<section><title>Executive Summary</title><body>{BODY} </bo", ENVELOPE_TRUNCATED),
    (
        f"<section><title>Executive Summary</title><body># Executive Summary\n\n{BODY}"
        "</body></section>",
        None,
    ),
    (
        f"<section><title>Executive Summary</title><body>**Executive Summary**\n{BODY}"
        "</body></section>",
        None,
    ),
    (
        f"## Executive Summary\n\n<section><title>Executive Summary</title> {BODY}</section>",
        ENVELOPE_RECOVERED,
    ),
    (f"## Executive Summary\n\n{BODY}", None),
]


def _rendered(section) -> str:
    return _clean_fast_report_output(section.to_markdown())


@pytest.mark.parametrize(("content", "issue"), SINGLE_CASES)
def test_single_path_renders_one_heading_then_prose(content, issue):
    section = _parse_single_section(content, EXEC)
    rendered = _rendered(section)

    assert section.envelope_issue == issue
    assert rendered.startswith(f"## Executive Summary\n\n{BODY}")
    assert rendered.count("Executive Summary") == 1
    assert count_section_envelope_markers(rendered) == 0
    assert _validate_output_markdown(rendered)["issues"] == []


def test_batch_path_recovers_each_envelope_and_mixed_markdown():
    content = (
        "<section><title>Executive Summary</title><body>Summary body.</body></section>\n"
        "<section><title>Market</title> Market body.</section>\n\n"
        "## Competition\n\nCompetition body.\n\n"
        "<section><title>Risks</title><body>Risk body."
    )
    sections = _parse_batch_sections(
        content, [_Section("Executive Summary"), _Section("Market"), _Section("Competition")]
    )

    assert [s.title for s in sections] == ["Executive Summary", "Market", "Competition", "Risks"]
    assert [s.envelope_issue for s in sections] == [
        None,
        ENVELOPE_RECOVERED,
        None,
        ENVELOPE_TRUNCATED,
    ]
    for section, body in zip(
        sections, ["Summary body.", "Market body.", "Competition body.", "Risk body."], strict=True
    ):
        assert section.content.startswith(body)
        assert "<" not in section.content


def test_ambiguous_envelope_is_kept_verbatim_and_blocks_the_docx():
    content = (
        "<section><title>Executive Summary</title><body>Lead <title>x</title> tail</body></section>"
    )
    section = _parse_single_section(content, EXEC)
    rendered = _rendered(section)

    assert section.envelope_issue == ENVELOPE_AMBIGUOUS
    assert "Lead" in rendered
    assert "tail" in rendered
    assert count_section_envelope_markers(rendered) > 0
    validation = _validate_output_markdown(rendered)
    assert validation["passed"] is False
    assert any(issue.startswith("section_envelope_markup") for issue in validation["issues"])


def test_envelope_without_title_is_ambiguous_not_guessed():
    _, blocks = _extract_generated_section_blocks(f"<section><body>{BODY}</body></section>")
    assert blocks[0].issue == ENVELOPE_AMBIGUOUS
    assert blocks[0].body.startswith("<section>")


def test_text_after_a_closed_envelope_is_kept_with_that_section():
    content = f"<section><title>Executive Summary</title><body>{BODY}</body></section>\n\nMore."
    section = _parse_single_section(content, EXEC)
    assert section.envelope_issue == ENVELOPE_OUTSIDE_TEXT
    assert section.content.startswith(f"{BODY}\n\nMore.")


def test_ship_gate_and_docx_detector_see_envelope_tags():
    leaked = f"## Executive Summary\n\n<section><title>Executive Summary</title> {BODY}</section>"
    assert count_section_envelope_markers(leaked) == 3
    assert _validate_output_markdown(leaked)["passed"] is False
    artifacts = ArtifactDetector().scan_text(leaked)
    assert sum(a["type"] == "section_envelope" for a in artifacts) == 3


@pytest.mark.parametrize(
    "prose",
    [
        "The section on titles covers the body of evidence.",
        "The homepage <title> tag reads Acme, and the <body> element is light.",
        "The homepage `<title>Acme</title>` tag is short.",
        "Markup sample:\n\n```html\n<section><title>x</title></section>\n```\n\nEnd.",
    ],
)
def test_prose_and_code_mentioning_tags_are_not_flagged(prose):
    assert count_section_envelope_markers(prose) == 0
    assert _validate_output_markdown(f"## Overview\n\n{prose}")["issues"] == []
    content = f"<section><title>Executive Summary</title><body>{prose}</body></section>"
    assert _parse_single_section(content, EXEC).envelope_issue is None


def test_references_block_is_cut_but_later_blocks_survive():
    content = (
        f"## Executive Summary\n\n{BODY}\n\n## Sources\n\n[1] https://acme.example\n\n"
        "## Key Risks\n\nRisk text."
    )
    section = _parse_single_section(content, EXEC)
    assert "### Key Risks\n\nRisk text." in section.content
    assert "acme.example" not in section.content


def test_heading_repeating_a_closed_envelope_continues_that_section():
    content = (
        f"<section><title>Executive Summary</title><body>{BODY}</body></section>\n\n"
        "## Executive Summary\n\nMore detail."
    )
    _, blocks = _extract_generated_section_blocks(content)
    assert len(blocks) == 1
    assert blocks[0].body == f"{BODY}\n\nMore detail."
    assert _rendered(_parse_single_section(content, EXEC)).count("Executive Summary") == 1


def test_many_envelopes_parse_in_linear_time():
    import time

    content = "<section><title>T</title>x</section>y" * 4000
    started = time.perf_counter()
    _, blocks = _extract_generated_section_blocks(content)
    assert len(blocks) == 1  # same-title blocks merge into one continuing section
    assert time.perf_counter() - started < 2.0


class TestRetryPolicy:
    def test_needs_review_envelope_triggers_an_envelope_retry(self):
        truncated = _parse_single_section(
            f"<section><title>Executive Summary</title><body>{BODY}", EXEC
        )
        assert section_retry_reason(truncated, 1) == "returned a truncated section envelope"
        assert "complete section envelope" in section_retry_instruction(truncated, 1)

    def test_recovered_envelope_does_not_retry_on_its_own(self):
        recovered = _parse_single_section(
            f"<section><title>Executive Summary</title> {BODY}</section>", EXEC
        )
        assert section_retry_reason(recovered, 1) is None

    def test_thin_section_keeps_the_word_count_retry(self):
        thin = _parse_single_section(f"## Executive Summary\n\n{BODY}", EXEC)
        assert section_retry_reason(thin, 1000).startswith("too thin")
        assert "minimum target is 1000 words" in section_retry_instruction(thin, 1000)

    def test_envelope_retry_keeps_the_word_target_when_also_thin(self):
        truncated = _parse_single_section(
            f"<section><title>Executive Summary</title><body>{BODY}", EXEC
        )
        instruction = section_retry_instruction(truncated, 1000)
        assert "complete section envelope" in instruction
        assert "minimum target is 1000 words" in instruction

    def test_truncated_beats_a_longer_ambiguous_retry(self):
        truncated = _parse_single_section(
            f"<section><title>Executive Summary</title><body>{BODY}", EXEC
        )
        ambiguous = _parse_single_section(
            "<section><title>Executive Summary</title><body>"
            + "word " * 50
            + "<section></body></section>",
            EXEC,
        )
        assert ambiguous.envelope_issue == ENVELOPE_AMBIGUOUS
        assert prefer_section_retry(truncated, ambiguous) is False

    def test_retry_that_fixes_the_envelope_wins_even_when_shorter(self):
        first = _parse_single_section(
            "<section><title>Executive Summary</title><body>" + "word " * 50, EXEC
        )
        retry = _parse_single_section(f"## Executive Summary\n\n{BODY}", EXEC)
        assert prefer_section_retry(first, retry) is True
        assert prefer_section_retry(retry, first) is False

    def test_most_severe_issue_wins(self):
        assert most_severe_envelope_issue(None, ENVELOPE_RECOVERED, ENVELOPE_TRUNCATED) == (
            ENVELOPE_TRUNCATED
        )
        assert most_severe_envelope_issue(None, None) is None


_PROSE = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Zs"), whitelist_characters=".,;:'-"
    ),
    min_size=1,
    max_size=200,
).filter(lambda text: text.strip())


@given(
    prose=_PROSE,
    body_open=st.booleans(),
    body_close=st.booleans(),
    section_close=st.booleans(),
)
def test_recovery_never_drops_or_invents_prose(prose, body_open, body_close, section_close):
    content = (
        "<section><title>Executive Summary</title>"
        + ("<body>" if body_open else " ")
        + prose
        + ("</body>" if body_close else "")
        + ("</section>" if section_close else "")
    )
    _, blocks = _extract_generated_section_blocks(content)

    assert len(blocks) == 1
    assert blocks[0].title == "Executive Summary"
    assert blocks[0].body == prose.strip()
    expected = (
        None
        if body_open and body_close and section_close
        else ENVELOPE_RECOVERED
        if section_close or body_close
        else ENVELOPE_TRUNCATED
    )
    assert blocks[0].issue == expected


@pytest.mark.parametrize(
    ("issue", "expected"),
    [
        (ENVELOPE_TRUNCATED, "writer output was truncated; review before sending"),
        (ENVELOPE_AMBIGUOUS, "kept verbatim and Word output withheld"),
        (ENVELOPE_RECOVERED, None),
        (None, None),
    ],
)
def test_operator_sees_envelope_review_warnings(monkeypatch, issue, expected):
    from primr.core import fast_run_sections

    warnings: list[str] = []
    monkeypatch.setattr(fast_run_sections.console, "warn", warnings.append)
    section = _parse_single_section(f"## Executive Summary\n\n{BODY}", EXEC)
    section.envelope_issue = issue
    fast_run_sections._warn_envelope_review(section)
    if expected is None:
        assert warnings == []
    else:
        assert len(warnings) == 1
        assert expected in warnings[0]


@pytest.mark.parametrize(("issue", "cohered"), [(ENVELOPE_AMBIGUOUS, False), (None, True)])
def test_coherence_pass_never_rewrites_an_ambiguous_envelope(monkeypatch, issue, cohered):
    from primr.core import fast_run_sections

    monkeypatch.setattr(fast_run_sections.console, "warn", lambda _msg: None)
    section = _parse_single_section(f"## Executive Summary\n\n{BODY}", EXEC)
    section.envelope_issue = issue
    result = fast_run_sections._cohere_unless_ambiguous(
        [section], "original", lambda content: content + " cohered"
    )
    assert result == ("original cohered" if cohered else "original")


def test_prose_before_a_differently_titled_heading_keeps_that_heading():
    content = "Intro prose.\n\n## Market Position\n\nPosition text.\n\n## Risks\n\nRisk text."
    section = _parse_single_section(content, EXEC)
    assert section.content.startswith(
        "Intro prose.\n\n### Market Position\n\nPosition text.\n\n### Risks\n\nRisk text."
    )


def test_prose_before_the_expected_heading_is_not_duplicated():
    content = f"Intro prose.\n\n## Executive Summary\n\n{BODY}"
    section = _parse_single_section(content, EXEC)
    assert section.content.startswith(f"Intro prose.\n\n{BODY}")
