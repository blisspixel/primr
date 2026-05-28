"""Tests for icon generation.

Smoke tests only — the icons module has two backends (Pillow gradient and
solid-PNG fallback) and either path needs to produce valid PNG bytes that
the OS can read.
"""

from __future__ import annotations

from primr.skill_pack.icons import (
    build_color_icon,
    build_outline_icon,
    pillow_available,
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_color_icon_is_valid_png():
    data = build_color_icon("Acme Corp")
    assert isinstance(data, bytes)
    assert len(data) > 100
    assert data.startswith(_PNG_SIGNATURE)


def test_outline_icon_is_valid_png():
    data = build_outline_icon("Acme Corp")
    assert isinstance(data, bytes)
    assert len(data) > 50
    assert data.startswith(_PNG_SIGNATURE)


def test_color_icon_is_deterministic_per_company():
    a = build_color_icon("Acme Corp")
    b = build_color_icon("Acme Corp")
    assert a == b


def test_color_icon_differs_by_company():
    a = build_color_icon("Acme Corp")
    b = build_color_icon("Northwind Haulage")
    assert a != b


def test_pillow_availability_is_bool():
    assert isinstance(pillow_available(), bool)
