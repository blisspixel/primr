"""Coverage tests for primr.output.chapter_config helper functions."""

from __future__ import annotations

from primr.output.chapter_config import (
    CHAPTER_CONFIG,
    get_all_section_keys,
    get_chapter_for_section,
    get_section_number,
    is_section_in_chapters,
)


def test_get_chapter_for_section_found():
    name, num = get_chapter_for_section("mission_vision")
    assert name == "Company Profile"
    assert num == 1


def test_get_chapter_for_section_not_found():
    assert get_chapter_for_section("does_not_exist") == (None, -1)


def test_get_section_number_found():
    # mission_vision is the first section of the first chapter.
    assert get_section_number("mission_vision") == "1.1"
    # company_history is second section of first chapter.
    assert get_section_number("company_history") == "1.2"


def test_get_section_number_not_found():
    assert get_section_number("nope") == ""


def test_get_all_section_keys_matches_config():
    keys = get_all_section_keys()
    # Total keys equals the sum across all chapters.
    expected = sum(len(c["sections"]) for c in CHAPTER_CONFIG.values())
    assert len(keys) == expected
    assert "mission_vision" in keys
    assert keys[0] == "mission_vision"


def test_is_section_in_chapters():
    assert is_section_in_chapters("mission_vision") is True
    assert is_section_in_chapters("not_a_real_section") is False
