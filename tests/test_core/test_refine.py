"""Tests for the QA iteration loop (primr refine, roadmap #10).

All LLM / network seams are injected, so the loop's control flow:
weak-section identification, regeneration splicing, stop conditions,
write-guard output, is tested deterministically.
"""

from __future__ import annotations

import pytest

from primr.core.refine import (
    DEFAULT_TARGET_GRADE,
    WeakSection,
    extract_source_urls,
    identify_weak_sections,
    refine_report,
    split_sections,
)


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body}\n"


def _strong_section(title: str) -> str:
    body = (
        "Solid analytical sentence with evidence. " * 40
    ) + "[cite: 1] (Confirmed)\nWhat to validate: confirm in discovery.\n"
    return _section(title, body)


def _weak_section(title: str) -> str:
    return _section(title, "Thin content with no evidence at all.")


def _sources_section() -> str:
    return _section("Sources", "1. https://example.com/a\n2. https://example.com/b")


@pytest.fixture
def report_file(tmp_path):
    def _make(content: str):
        path = tmp_path / "AcmeCo_Strategic_Overview_06-11-2026.md"
        path.write_text(content, encoding="utf-8")
        return path

    return _make


class TestSplitAndIdentify:
    def test_split_sections(self):
        content = _strong_section("Alpha") + _weak_section("Beta") + _sources_section()
        sections = split_sections(content)
        assert [t for t, _ in sections] == ["Alpha", "Beta", "Sources"]

    def test_weak_sections_ranked_and_capped(self):
        content = (
            _strong_section("Strong One")
            + _weak_section("Weak A")
            + _weak_section("Weak B")
            + _weak_section("Weak C")
            + _weak_section("Weak D")
            + _sources_section()
        )
        weak = identify_weak_sections(content, max_sections=3)
        assert len(weak) == 3
        assert all(isinstance(w, WeakSection) for w in weak)
        assert {w.title for w in weak} <= {"Weak A", "Weak B", "Weak C", "Weak D"}

    def test_strong_sections_not_flagged(self):
        weak = identify_weak_sections(_strong_section("Solid"))
        assert weak == []

    def test_sources_appendix_never_flagged(self):
        weak = identify_weak_sections(_sources_section())
        assert weak == []

    def test_skip_titles_excluded(self):
        content = _weak_section("Weak A") + _weak_section("Weak B")
        weak = identify_weak_sections(content, skip_titles={"Weak A"})
        assert [w.title for w in weak] == ["Weak B"]

    def test_reasons_recorded(self):
        weak = identify_weak_sections(_weak_section("Thin"))
        assert weak
        reasons = weak[0].reasons
        assert any("short" in r for r in reasons)
        assert "no citations" in reasons
        assert "no confidence labels" in reasons

    def test_extract_source_urls(self):
        content = _strong_section("Alpha") + _sources_section()
        urls = extract_source_urls(content)
        assert urls == ["https://example.com/a", "https://example.com/b"]


class TestRefineLoop:
    def _run(
        self,
        report_path,
        *,
        scores: list[float],
        regenerated_body: str = "",
        **kwargs,
    ):
        """Drive refine_report with scripted scores and a canned regenerator."""
        score_iter = iter(scores)
        calls = {"gather": 0, "regenerate": 0, "prune": 0}

        def fake_score(content: str) -> float:
            try:
                return next(score_iter)
            except StopIteration:
                return scores[-1]

        def fake_gather(company, website, section, working_folder) -> str:
            calls["gather"] += 1
            return "[Source: https://example.com/x]\nfresh evidence"

        def fake_regenerate(
            company, website, title, original, workbook, evidence, source_urls
        ) -> str:
            calls["regenerate"] += 1
            body = regenerated_body or (
                ("Regenerated rich content with evidence. " * 40) + "[cite: 1] (Reported)"
            )
            return f"## {title}\n{body}\n"

        kwargs.setdefault("acceptance_fn", lambda before, after, titles: True)
        result = refine_report(
            "AcmeCo",
            report_path,
            website="https://acme.example",
            score_fn=fake_score,
            gather_fn=fake_gather,
            regenerate_fn=fake_regenerate,
            prune_fn=lambda c: c,
            **kwargs,
        )
        return result, calls

    def test_already_at_target_no_work(self, report_file):
        path = report_file(_strong_section("Alpha") + _sources_section())
        result, calls = self._run(path, scores=[95.0])
        assert result.stop_reason == "target_reached"
        assert result.iterations == 0
        assert calls["regenerate"] == 0
        assert result.output_path is None

    def test_reaches_target_after_regeneration(self, report_file):
        path = report_file(_strong_section("Alpha") + _weak_section("Weak A") + _sources_section())
        result, calls = self._run(path, scores=[70.0, 92.0])
        assert result.stop_reason == "target_reached"
        assert result.iterations == 1
        assert result.sections_regenerated == ["Weak A"]
        assert calls["gather"] == 1
        assert result.final_grade == 92.0
        # Refined artifact written to the _improved sibling
        assert result.output_path is not None
        assert result.output_path.endswith("_improved.md")

    def test_no_weak_sections_stops(self, report_file):
        path = report_file(_strong_section("Alpha") + _sources_section())
        result, calls = self._run(path, scores=[70.0, 70.0])
        assert result.stop_reason == "no_weak_sections"
        assert calls["regenerate"] == 0

    def test_diminishing_returns_stops_early(self, report_file):
        # Plenty of weak sections, but the grade barely moves each iteration.
        content = (
            _weak_section("Weak A")
            + _weak_section("Weak B")
            + _weak_section("Weak C")
            + _weak_section("Weak D")
            + _weak_section("Weak E")
            + _weak_section("Weak F")
            + _sources_section()
        )
        path = report_file(content)
        # initial 70, then 70.5, 71; both iterations < 5% relative gain
        result, _ = self._run(
            path,
            scores=[70.0, 70.5, 71.0],
            max_iterations=10,
            max_sections_per_iteration=2,
            # Keep regenerated sections weak-shaped so the loop would continue
            # if not for the diminishing-returns stop.
            regenerated_body="Still thin.",
        )
        assert result.stop_reason == "diminishing_returns"
        assert result.iterations == 2

    def test_max_iterations_bound(self, report_file):
        content = (
            _weak_section("Weak A")
            + _weak_section("Weak B")
            + _weak_section("Weak C")
            + _weak_section("Weak D")
            + _sources_section()
        )
        path = report_file(content)
        # Big gains each iteration (no diminishing returns) but never reaching 90
        result, _ = self._run(
            path,
            scores=[40.0, 50.0, 62.0, 77.0],
            max_iterations=3,
            max_sections_per_iteration=1,
            regenerated_body="Still thin.",
        )
        assert result.stop_reason == "max_iterations"
        assert result.iterations == 3

    def test_in_place_overwrites_original(self, report_file):
        path = report_file(_strong_section("Alpha") + _weak_section("Weak A") + _sources_section())
        result, _ = self._run(path, scores=[70.0, 95.0], in_place=True)
        assert result.output_path == str(path)
        assert "Regenerated rich content" in path.read_text(encoding="utf-8")

    def test_regenerated_section_spliced_into_report(self, report_file):
        path = report_file(_strong_section("Alpha") + _weak_section("Weak A") + _sources_section())
        self._run(path, scores=[70.0, 95.0])
        improved = path.with_name(path.stem + "_improved" + path.suffix)
        refined = improved.read_text(encoding="utf-8")
        assert "Thin content with no evidence" not in refined
        assert "Regenerated rich content" in refined
        # Untouched sections preserved
        assert "## Alpha" in refined
        assert "## Sources" in refined

    def test_default_target_is_ninety(self):
        assert DEFAULT_TARGET_GRADE == 90.0


class TestCLIWiring:
    def test_refine_positional_routes(self):
        from primr.core.cli import Command, parse_args

        config = parse_args(["refine", "Acme Corp"])
        assert config.command == Command.REFINE
        assert config.refine_company == "Acme Corp"
        assert config.refine_target_grade == 90.0

    def test_target_grade_flag(self):
        from primr.core.cli import parse_args

        config = parse_args(["refine", "Acme Corp", "--target-grade", "85"])
        assert config.refine_target_grade == 85.0

    def test_handler_errors_without_company(self):
        from primr.core.cli import CLIConfig, Command, _handle_refine

        assert _handle_refine(CLIConfig(command=Command.REFINE)) == 1


class TestIndependentAcceptance:
    """Anti-Goodhart guard: iterations the calibration audit rejects are reverted."""

    def test_rejected_iteration_reverted_and_loop_stops(self, report_file):
        path = report_file(_strong_section("Alpha") + _weak_section("Weak A") + _sources_section())
        original_content = path.read_text(encoding="utf-8")

        helper = TestRefineLoop()
        result, _ = helper._run(
            path,
            scores=[70.0, 95.0],
            acceptance_fn=lambda before, after, titles: False,
        )

        assert result.stop_reason == "acceptance_rejected"
        assert result.acceptance_rejected is True
        assert result.sections_regenerated == []
        assert result.output_path is None
        # Original artifact untouched
        assert path.read_text(encoding="utf-8") == original_content

    def test_acceptance_receives_iteration_context(self, report_file):
        path = report_file(_strong_section("Alpha") + _weak_section("Weak A") + _sources_section())
        seen = {}

        def spy_acceptance(before, after, titles):
            seen["titles"] = list(titles)
            seen["changed"] = before != after
            return True

        helper = TestRefineLoop()
        result, _ = helper._run(path, scores=[70.0, 95.0], acceptance_fn=spy_acceptance)
        assert seen["titles"] == ["Weak A"]
        assert seen["changed"] is True
        assert result.acceptance_rejected is False

    def test_default_acceptance_passes_when_no_traceable_labels_added(self):
        from primr.core.refine import _default_acceptance

        before = "## S\nThin.\n"
        after = "## S\nBetter prose, inference only. (Hypothesis)\n"
        assert _default_acceptance(before, after, ["S"]) is True

    def test_default_acceptance_rejects_traceability_drop(self, monkeypatch):
        # Before: one traceable Confirmed claim. After: rewrite added an
        # uncited (Confirmed) claim -> no_source drags precision down.
        before = (
            "## S\nRevenue is $50M. (Confirmed) [cite: 1]\n\n## Sources\n1. https://a.example\n"
        )
        after = (
            "## S\nRevenue is $50M. (Confirmed) [cite: 1]\n"
            "Margins doubled last year. (Confirmed)\n\n## Sources\n1. https://a.example\n"
        )
        import primr.qa.label_calibration as cal

        monkeypatch.setattr(cal, "_default_fetch", lambda url: "source text")
        monkeypatch.setattr(cal, "_default_judge", lambda c, t: True)
        from primr.core.refine import _default_acceptance

        assert _default_acceptance(before, after, ["S"]) is False

    def test_default_acceptance_fail_open_on_harness_error(self, monkeypatch):
        import primr.qa.label_calibration as cal

        def boom(*a, **k):
            raise RuntimeError("harness exploded")

        monkeypatch.setattr(cal, "extract_labeled_claims", boom)
        from primr.core.refine import _default_acceptance

        before = "## S\nx (Confirmed) [cite: 1]\n\n## Sources\n1. https://a.example\n"
        assert _default_acceptance(before, before, ["S"]) is True
