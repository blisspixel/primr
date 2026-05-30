"""Unit tests for small pure helpers in primr.core.research_agent.

These cover format_tier_stats, _validate_scrape_quality, ensure_valid_url,
save_section_output, validate_context_files, _extract_domain, _a_or_an,
generate_prompt, create_working_folder, and consolidate_working_folder —
all of which are testable without spinning up the full pipeline.
"""

from __future__ import annotations

import pytest

from primr.core.research_agent import (
    _a_or_an,
    _extract_domain,
    _validate_scrape_quality,
    consolidate_working_folder,
    create_working_folder,
    ensure_valid_url,
    format_tier_stats,
    generate_prompt,
    save_section_output,
    validate_context_files,
)

# ---------------------------------------------------------------------------
# format_tier_stats
# ---------------------------------------------------------------------------


class TestFormatTierStats:
    def test_sorts_by_count_descending(self):
        stats = {"playwright": 3, "httpx": 7, "requests": 2}
        result = format_tier_stats(stats)
        # Output ordering: highest count first -> httpx, playwright, requests
        parts = result.split(", ")
        assert parts[0].startswith("7 ")
        assert parts[1].startswith("3 ")
        assert parts[2].startswith("2 ")

    def test_uses_display_names(self):
        stats = {"vision": 1, "drissionpage_stealth": 2}
        result = format_tier_stats(stats)
        assert "AI vision" in result
        assert "stealth browser" in result

    def test_falls_back_to_raw_name_for_unknown_tier(self):
        result = format_tier_stats({"weird_tier": 5})
        assert "weird_tier" in result

    def test_empty_dict(self):
        assert format_tier_stats({}) == ""

    def test_single_tier(self):
        assert format_tier_stats({"requests": 10}) == "10 HTTP"


# ---------------------------------------------------------------------------
# _validate_scrape_quality
# ---------------------------------------------------------------------------


class TestValidateScrapeQuality:
    def test_passes_with_sufficient_pages_and_chars(self):
        corpus = {f"url{i}": "x" * 1000 for i in range(10)}
        ok, _ = _validate_scrape_quality(corpus, min_pages=5, min_chars=100)
        assert ok is True

    def test_fails_with_too_few_pages(self):
        corpus = {"url1": "x" * 100000}
        ok, reason = _validate_scrape_quality(corpus, min_pages=5, min_chars=100)
        assert ok is False
        assert "1 pages" in reason

    def test_fails_with_too_few_chars(self):
        corpus = {f"url{i}": "x" * 5 for i in range(20)}
        ok, reason = _validate_scrape_quality(corpus, min_pages=5, min_chars=1000)
        assert ok is False
        assert "chars" in reason

    def test_handles_none_values_safely(self):
        # An entry value of None should be treated as empty without crashing.
        corpus = {"url1": "x" * 1000, "url2": None}
        ok, _ = _validate_scrape_quality(corpus, min_pages=2, min_chars=500)
        assert ok is True

    def test_empty_corpus(self):
        ok, reason = _validate_scrape_quality({}, min_pages=1, min_chars=1)
        assert ok is False
        assert "0 pages" in reason


# ---------------------------------------------------------------------------
# ensure_valid_url
# ---------------------------------------------------------------------------


class TestEnsureValidUrl:
    def test_none_returns_none(self):
        assert ensure_valid_url(None) is None

    def test_empty_returns_none(self):
        assert ensure_valid_url("") is None

    def test_https_preserved(self):
        assert ensure_valid_url("https://acme.example") == "https://acme.example"

    def test_http_preserved(self):
        assert ensure_valid_url("http://acme.example") == "http://acme.example"

    def test_bare_domain_gets_https(self):
        assert ensure_valid_url("acme.example") == "https://acme.example"

    def test_strips_whitespace(self):
        assert ensure_valid_url("  https://x.example  ") == "https://x.example"


# ---------------------------------------------------------------------------
# save_section_output
# ---------------------------------------------------------------------------


class TestSaveSectionOutput:
    def test_writes_content_to_section_file(self, tmp_path):
        save_section_output(str(tmp_path), "exec_summary", "the body")
        out = tmp_path / "exec_summary.txt"
        assert out.exists()
        assert out.read_text(encoding="utf-8") == "the body"

    def test_swallows_oserror(self, tmp_path, caplog):
        # Write to a non-existent folder — should log but not raise.
        bogus = tmp_path / "does" / "not" / "exist"
        # No raise expected; the function logs and returns.
        save_section_output(str(bogus), "x", "body")
        assert not (bogus / "x.txt").exists()


# ---------------------------------------------------------------------------
# validate_context_files
# ---------------------------------------------------------------------------


class TestValidateContextFiles:
    def test_supported_extensions(self, tmp_path):
        files = []
        for ext in (".txt", ".pdf", ".md", ".json", ".csv"):
            p = tmp_path / f"file{ext}"
            p.write_text("x", encoding="utf-8")
            files.append(str(p))
        valid, invalid, warnings = validate_context_files(files)
        assert len(valid) == 5
        assert invalid == []

    def test_missing_file_marked_invalid(self, tmp_path):
        files = [str(tmp_path / "nonexistent.txt")]
        valid, invalid, _ = validate_context_files(files)
        assert valid == []
        assert invalid[0][0] == files[0]
        assert "not found" in invalid[0][1]

    def test_word_doc_marked_invalid_with_tip(self, tmp_path):
        p = tmp_path / "report.docx"
        p.write_text("x", encoding="utf-8")
        valid, invalid, warnings = validate_context_files([str(p)])
        assert valid == []
        assert any("Word" in reason for _, reason in invalid)
        assert any("Use the" in w for w in warnings)

    def test_excel_marked_invalid(self, tmp_path):
        p = tmp_path / "data.xlsx"
        p.write_text("x", encoding="utf-8")
        valid, invalid, _ = validate_context_files([str(p)])
        assert valid == []
        assert any("Excel" in reason for _, reason in invalid)

    def test_unknown_extension_marked_invalid(self, tmp_path):
        p = tmp_path / "data.xyz"
        p.write_text("x", encoding="utf-8")
        valid, invalid, _ = validate_context_files([str(p)])
        assert valid == []
        assert any(".xyz" in reason for _, reason in invalid)


# ---------------------------------------------------------------------------
# _extract_domain
# ---------------------------------------------------------------------------


class TestExtractDomain:
    def test_https_url(self):
        assert _extract_domain("https://acme.example/path") == "acme.example"

    def test_bare_domain(self):
        # No scheme — urlparse puts everything in path; the helper splits on /.
        assert _extract_domain("acme.example/path") == "acme.example"

    def test_invalid_returns_none(self):
        # Empty string should return None.
        assert _extract_domain("") is None


# ---------------------------------------------------------------------------
# _a_or_an
# ---------------------------------------------------------------------------


class TestAOrAn:
    @pytest.mark.parametrize("word", ["apple", "Orange", "Idea", "umbrella", "Elephant"])
    def test_vowel_words_get_an(self, word):
        assert _a_or_an(word) == "an"

    @pytest.mark.parametrize("word", ["dog", "Cat", "wolf"])
    def test_consonant_words_get_a(self, word):
        assert _a_or_an(word) == "a"

    def test_empty_string_gets_a(self):
        assert _a_or_an("") == "a"


# ---------------------------------------------------------------------------
# generate_prompt
# ---------------------------------------------------------------------------


class TestGeneratePrompt:
    def test_raises_when_template_missing(self):
        with pytest.raises(ValueError, match="not found"):
            generate_prompt("bogus_template_name_xyz")

    def test_formats_template_with_kwargs(self):
        # Pick a real template that exists in the prompts catalog.
        # initial_company_overview uses many kwargs; we provide all of them.
        result = generate_prompt(
            "initial_company_overview",
            company_name="Acme",
            company_website="https://acme.example",
            industry="Tech",
            detailed_products_services="N/A",
            unique_selling_proposition="N/A",
            mission_vision="N/A",
            company_history="N/A",
            key_achievements="N/A",
            target_audience="N/A",
            financial_overview="N/A",
            business_drivers_and_kpis="N/A",
            business_outcomes="N/A",
            scraped_website_summary="N/A",
        )
        assert "Acme" in result


# ---------------------------------------------------------------------------
# create_working_folder
# ---------------------------------------------------------------------------


class TestCreateWorkingFolder:
    def test_creates_company_subfolder(self, tmp_path, monkeypatch):
        monkeypatch.setattr("primr.core.research_agent.WORKING_DIR", str(tmp_path))
        folder = create_working_folder("Acme Corp", "https://acme.example")
        assert "Acme_Corp" in folder
        assert (tmp_path / "Acme_Corp").exists()

    def test_uses_website_when_no_company_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr("primr.core.research_agent.WORKING_DIR", str(tmp_path))
        folder = create_working_folder("", "https://acme.example")
        # Falls back to domain-derived name
        assert "acme_example" in folder

    def test_default_when_no_input(self, tmp_path, monkeypatch):
        monkeypatch.setattr("primr.core.research_agent.WORKING_DIR", str(tmp_path))
        folder = create_working_folder("", "")
        assert "Unknown_Company" in folder

    def test_reuse_incomplete_picks_failed_run(self, tmp_path, monkeypatch):
        import json

        monkeypatch.setattr("primr.core.research_agent.WORKING_DIR", str(tmp_path))
        # Set up a failed prior run.
        prior = tmp_path / "Acme_Corp" / "2026-02-25_1200"
        prior.mkdir(parents=True)
        (prior / "_run_state.json").write_text(json.dumps({"status": "failed"}), encoding="utf-8")

        folder = create_working_folder("Acme Corp", None, reuse_incomplete=True)
        assert str(prior) == folder

    def test_reuse_incomplete_ignores_completed_runs(self, tmp_path, monkeypatch):
        import json

        monkeypatch.setattr("primr.core.research_agent.WORKING_DIR", str(tmp_path))
        prior = tmp_path / "Acme_Corp" / "2026-02-25_1200"
        prior.mkdir(parents=True)
        (prior / "_run_state.json").write_text(
            json.dumps({"status": "completed"}), encoding="utf-8"
        )
        folder = create_working_folder("Acme Corp", None, reuse_incomplete=True)
        # Should NOT reuse — creates a fresh timestamped folder.
        assert folder != str(prior)


# ---------------------------------------------------------------------------
# consolidate_working_folder
# ---------------------------------------------------------------------------


class TestConsolidateWorkingFolder:
    def test_aggregates_txt_files_into_one(self, tmp_path):
        (tmp_path / "Acme_Corp").mkdir()
        folder = tmp_path / "Acme_Corp"
        (folder / "exec_summary.txt").write_text("execsumbody", encoding="utf-8")
        (folder / "swot.txt").write_text("swotbody", encoding="utf-8")
        out_path = consolidate_working_folder(str(folder))
        with open(out_path, encoding="utf-8") as f:
            body = f.read()
        assert "execsumbody" in body
        assert "swotbody" in body
        assert "Research Context: Acme Corp" in body

    def test_raises_when_folder_missing(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            consolidate_working_folder(str(tmp_path / "does_not_exist"))

    def test_raises_when_no_txt_files(self, tmp_path):
        (tmp_path / "empty").mkdir()
        with pytest.raises(ValueError, match=r"No \.txt files"):
            consolidate_working_folder(str(tmp_path / "empty"))

    def test_uses_parent_for_timestamped_leaf(self, tmp_path):
        parent = tmp_path / "Acme_Corp"
        leaf = parent / "2026-03-04_1530"
        leaf.mkdir(parents=True)
        (leaf / "x.txt").write_text("body", encoding="utf-8")
        out_path = consolidate_working_folder(str(leaf))
        with open(out_path, encoding="utf-8") as f:
            body = f.read()
        # Company name should come from "Acme_Corp" (parent), not from the leaf.
        assert "Research Context: Acme Corp" in body
