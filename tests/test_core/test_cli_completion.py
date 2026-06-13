"""Tests for shell completion + the extracted CLI help epilog (track E)."""

from __future__ import annotations

import argparse
import sys
import types

from primr.core.cli import _create_parser
from primr.core.cli_parser import CLI_EPILOG, enable_shell_completion


class TestCliEpilog:
    def test_create_parser_uses_extracted_epilog(self):
        assert _create_parser().epilog == CLI_EPILOG

    def test_epilog_has_key_examples(self):
        for token in ("Research Modes:", "Examples:", "primr init", "primr recon acme.com"):
            assert token in CLI_EPILOG


class TestShellCompletion:
    def test_noop_when_argcomplete_absent(self, monkeypatch):
        # Force `import argcomplete` to raise ImportError deterministically.
        monkeypatch.setitem(sys.modules, "argcomplete", None)
        # Must not raise.
        enable_shell_completion(argparse.ArgumentParser())

    def test_calls_autocomplete_when_present(self, monkeypatch):
        seen = {}
        fake = types.ModuleType("argcomplete")
        fake.autocomplete = lambda parser: seen.setdefault("parser", parser)
        monkeypatch.setitem(sys.modules, "argcomplete", fake)

        parser = argparse.ArgumentParser()
        enable_shell_completion(parser)
        assert seen["parser"] is parser


class TestArgcompleteMarker:
    def test_python_argcomplete_ok_marker_in_cli_head(self):
        # The marker must be near the top of cli.py (within the first ~1KB) for
        # the global argcomplete script to recognize primr as completion-enabled.
        from pathlib import Path

        import primr.core.cli as cli_module

        head = Path(cli_module.__file__).read_text(encoding="utf-8")[:1024]
        assert "PYTHON_ARGCOMPLETE_OK" in head
