"""Native PDF extraction owns its page, output and process lifetime limits."""

import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import fitz
import pytest

from primr.data import pdf_extraction
from primr.data.scraping.content import extract_text_from_pdf


def pdf_with_shared_pages(count, text="Ordinary company evidence for ExampleCo."):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), text)
        contents = document.xref_get_key(page.xref, "Contents")[1]
        resources = document.xref_get_key(page.xref, "Resources")[1]
        for _ in range(count - 1):
            page = document.new_page()
            document.xref_set_key(page.xref, "Contents", contents)
            document.xref_set_key(page.xref, "Resources", resources)
        return document.tobytes(garbage=4, deflate=True)


def test_real_pdf_child_extracts_ordinary_text():
    result = extract_text_from_pdf(pdf_with_shared_pages(2))
    assert result.count("Ordinary company evidence for ExampleCo.") == 2
    assert "truncated" not in result


def test_small_pdf_repeated_content_is_bounded_by_page_budget():
    body = pdf_with_shared_pages(pdf_extraction.MAX_PDF_PAGES + 5)
    assert len(body) < 100_000
    result = extract_text_from_pdf(body)
    assert result.count("Ordinary company evidence for ExampleCo.") == pdf_extraction.MAX_PDF_PAGES
    assert "truncated at its page/text budget" in result
    assert len(result) <= pdf_extraction.MAX_PDF_TEXT_CHARS


def test_worker_text_budget_is_enforced_during_accumulation(monkeypatch):
    monkeypatch.setattr(pdf_extraction, "MAX_PDF_TEXT_CHARS", 128)
    text = pdf_extraction._extract_in_process(pdf_with_shared_pages(10))
    assert len(text) <= 128
    assert "truncated at its page/text budget" in text


def test_timeout_kills_reaps_and_does_not_forward_provider_keys(monkeypatch):
    process = MagicMock()
    process.__enter__.return_value = process
    process.communicate.side_effect = [subprocess.TimeoutExpired("pdf", 0.1), (b"", None)]
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-pdf-boundary-test")
    popen = MagicMock(return_value=process)
    monkeypatch.setattr(pdf_extraction.subprocess, "Popen", popen)
    assert extract_text_from_pdf(b"%PDF-test") is None
    process.kill.assert_called_once()
    assert process.communicate.call_count == 2
    assert "GEMINI_API_KEY" not in popen.call_args.kwargs["env"]
    assert popen.call_args.args[0][1] == "-I"


def test_real_timeout_leaves_no_running_pdf_child(monkeypatch):
    original = pdf_extraction.subprocess.Popen
    children = []

    def launch(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(pdf_extraction.subprocess, "Popen", launch)
    monkeypatch.setattr(pdf_extraction, "PDF_TIMEOUT_SECONDS", 0.001)
    assert extract_text_from_pdf(pdf_with_shared_pages(2)) is None
    assert len(children) == 1
    assert children[0].poll() is not None


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_cancellation_kills_and_reaps_before_propagating(monkeypatch, interruption):
    process = MagicMock()
    process.__enter__.return_value = process
    process.communicate.side_effect = [interruption(), (b"", None)]
    monkeypatch.setattr(pdf_extraction.subprocess, "Popen", lambda *a, **k: process)
    with pytest.raises(interruption):
        extract_text_from_pdf(b"%PDF-test")
    process.kill.assert_called_once()
    assert process.communicate.call_count == 2


@pytest.mark.parametrize("returncode,output", [(1, b"partial"), (-11, b""), (0, b"\xff")])
def test_child_failure_or_invalid_output_fails_closed(monkeypatch, returncode, output):
    process = MagicMock()
    process.__enter__.return_value = process
    process.communicate.return_value = output, None
    process.returncode = returncode
    monkeypatch.setattr(pdf_extraction.subprocess, "Popen", lambda *a, **k: process)
    assert extract_text_from_pdf(b"%PDF-test") is None


@pytest.mark.parametrize("body", [b"", b"not PDF", b"%PDF-malformed"])
def test_empty_invalid_and_corrupt_documents_remain_graceful(body):
    assert extract_text_from_pdf(body) is None


@pytest.mark.parametrize("platform,baseline", [("linux", 0), ("darwin", 8 * 1024**3)])
def test_native_limits_account_for_darwin_startup_mappings(monkeypatch, platform, baseline):
    limits = MagicMock()
    limits.RLIMIT_AS = 5
    limits.RLIMIT_CPU = 0
    limits.RLIM_INFINITY = -1
    limits.getrlimit.return_value = (-1, -1)
    memory = SimpleNamespace(
        Process=lambda: SimpleNamespace(memory_info=lambda: SimpleNamespace(vms=baseline))
    )
    monkeypatch.setitem(sys.modules, "resource", limits)
    monkeypatch.setitem(sys.modules, "psutil", memory)
    monkeypatch.setattr(sys, "platform", platform)
    pdf_extraction._install_limits()
    assert limits.setrlimit.call_args_list[0].args == (
        5,
        (baseline + pdf_extraction.PDF_MEMORY_BYTES,) * 2,
    )
    assert limits.setrlimit.call_args_list[1].args == (0, (12, 12))


def test_stricter_inherited_memory_limit_is_never_relaxed(monkeypatch):
    limits = MagicMock()
    limits.RLIMIT_AS = 5
    limits.RLIMIT_CPU = 0
    limits.RLIM_INFINITY = -1
    limits.getrlimit.return_value = (128 * 1024**2, 256 * 1024**2)
    monkeypatch.setitem(sys.modules, "resource", limits)
    monkeypatch.setattr(sys, "platform", "linux")
    pdf_extraction._install_limits()
    assert limits.setrlimit.call_args_list[0].args == (5, (128 * 1024**2,) * 2)


def test_worker_refuses_parsing_if_resource_limits_cannot_be_installed(monkeypatch):
    def fail():
        raise OSError("unsupported resource boundary")

    parser = MagicMock()
    monkeypatch.setattr(pdf_extraction, "_install_limits", fail)
    monkeypatch.setattr(pdf_extraction, "_extract_in_process", parser)
    assert pdf_extraction._worker() == 1
    parser.assert_not_called()
