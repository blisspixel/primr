"""Tests for validate_company_name's path-traversal rejection.

Guards the fix for the "company name path traversal in new report writers"
finding: company_name must not silently flow into filesystem paths with
'/', '\\', '..', or absolute-path components.
"""

from __future__ import annotations

import pytest

from primr.utils.validators import InputValidationError, validate_company_name


class TestPathTraversalRejection:
    @pytest.mark.parametrize(
        "name",
        [
            "../../tmp/owned",
            "../etc/passwd",
            "foo/bar",
            "foo\\bar",
            "..",
            "foo/../bar",
            "/etc/passwd",
            "C:\\Windows\\System32",
            "D:\\evil",
        ],
    )
    def test_rejects_path_separators_and_traversal(self, name: str) -> None:
        with pytest.raises(InputValidationError):
            validate_company_name(name)

    @pytest.mark.parametrize(
        "name",
        ["Acme\x00Corp", "Foo\x01Bar", "Bar\x1fBaz"],
    )
    def test_rejects_control_characters(self, name: str) -> None:
        with pytest.raises(InputValidationError):
            validate_company_name(name)


class TestLegitimateNames:
    @pytest.mark.parametrize(
        "name",
        [
            "Acme Corp",
            "Acme, Inc.",
            "Northwind Haulage Corp",
            "Realty 24",
            "A-B-C Holdings",
            "Foo & Bar",  # special chars OK as long as no path separators
        ],
    )
    def test_accepts_normal_names(self, name: str) -> None:
        assert validate_company_name(name) == name.strip()

    def test_strips_surrounding_whitespace(self) -> None:
        assert validate_company_name("  Acme Corp  ") == "Acme Corp"

    def test_rejects_empty(self) -> None:
        with pytest.raises(InputValidationError):
            validate_company_name("")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(InputValidationError):
            validate_company_name("A" * 201)
