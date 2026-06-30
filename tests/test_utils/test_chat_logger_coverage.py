"""Coverage tests for primr.utils.chat_logger.

Exercises the log/read round-trip, the corrupt-file recovery branches, the
missing-session warning path, and the save-failure error path. The module's
``CHAT_LOG_DIR`` is monkeypatched to ``tmp_path`` so nothing touches the real
logs directory.
"""

from __future__ import annotations

import json
import logging

import pytest

from primr.utils import chat_logger
from tests.secret_fixtures import fake_xai_api_key


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_logger, "CHAT_LOG_DIR", tmp_path)
    return tmp_path


class TestLogChatInteraction:
    def test_creates_new_log_file(self, log_dir):
        chat_logger.log_chat_interaction("hi", "hello", session_id="s1")
        path = log_dir / "s1.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["prompt"] == "hi"
        assert data[0]["response"] == "hello"
        assert "timestamp" in data[0]

    def test_appends_to_existing_file(self, log_dir):
        chat_logger.log_chat_interaction("q1", "a1", session_id="s2")
        chat_logger.log_chat_interaction("q2", "a2", session_id="s2")
        data = json.loads((log_dir / "s2.json").read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[1]["prompt"] == "q2"

    def test_default_session_id(self, log_dir):
        chat_logger.log_chat_interaction("p", "r")
        assert (log_dir / "general.json").exists()

    def test_corrupt_existing_file_starts_fresh(self, log_dir, caplog):
        path = log_dir / "bad.json"
        path.write_text("{ not valid json", encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            chat_logger.log_chat_interaction("p", "r", session_id="bad")
        assert "Corrupt chat log" in caplog.text
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1

    def test_save_failure_logs_error(self, log_dir, caplog, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(chat_logger, "open", boom, raising=False)
        # No file exists, so the read branch is skipped and the write fails.
        with caplog.at_level(logging.ERROR):
            chat_logger.log_chat_interaction("p", "r", session_id="fail")
        assert "Failed to save chat log" in caplog.text

    def test_secrets_are_redacted_before_persist(self, log_dir):
        """API keys in prompt/response are masked before hitting disk."""
        secret = fake_xai_api_key()
        chat_logger.log_chat_interaction(
            f"call provider with {secret}", f"done using {secret}", session_id="sec"
        )
        raw = (log_dir / "sec.json").read_text(encoding="utf-8")
        assert secret not in raw
        assert "[XAI_API_KEY]" in raw

    def test_atomic_write_leaves_no_tmp_file(self, log_dir):
        chat_logger.log_chat_interaction("p", "r", session_id="atomic")
        assert (log_dir / "atomic.json").exists()
        assert not list(log_dir.glob("*.tmp"))

    def test_persistent_lock_falls_back_to_direct_write(self, log_dir, caplog, monkeypatch):
        """A persistent lock that defeats atomic_replace must not drop the entry:
        the logger falls back to a direct overwrite and still records it."""

        def always_locked(src, dst, **kwargs):
            raise PermissionError("WinError 32: file in use")

        monkeypatch.setattr(chat_logger, "atomic_replace", always_locked)
        with caplog.at_level(logging.WARNING):
            chat_logger.log_chat_interaction("p", "r", session_id="locked")

        assert "falling back to direct overwrite" in caplog.text
        data = json.loads((log_dir / "locked.json").read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["prompt"] == "p"
        assert not list(log_dir.glob("*.tmp"))


class TestReadChatLogs:
    def test_reads_existing_logs(self, log_dir):
        chat_logger.log_chat_interaction("p", "r", session_id="readme")
        logs = chat_logger.read_chat_logs(session_id="readme")
        assert isinstance(logs, list)
        assert logs[0]["prompt"] == "p"

    def test_missing_session_returns_empty_with_warning(self, log_dir, capsys):
        logs = chat_logger.read_chat_logs(session_id="nope")
        assert logs == []
        assert "No logs found" in capsys.readouterr().out

    def test_corrupt_file_returns_empty_with_error(self, log_dir, capsys):
        (log_dir / "corrupt.json").write_text("][", encoding="utf-8")
        logs = chat_logger.read_chat_logs(session_id="corrupt")
        assert logs == []
        assert "Corrupt chat log file" in capsys.readouterr().out


class TestGetLogFilePath:
    def test_returns_timestamped_path(self, log_dir):
        path = chat_logger.get_log_file_path()
        assert path.parent == log_dir
        assert path.name.startswith("chat_log_")
        assert path.suffix == ".json"
