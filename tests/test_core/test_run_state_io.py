"""Unit tests for primr.core.run_state_io.

Direct tests on the JSON read/write/append helpers that persist per-run
state, plus the resilience-array helpers added for pipeline recovery.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from primr.core.run_state_io import (
    _append_background_abort,
    _append_model_health_event,
    _append_recovery_event,
    _append_run_event,
    _ensure_resilience_keys,
    _init_run_state_with_resilience,
    _load_run_state,
    _run_state_file,
    _save_run_state,
    _update_run_state,
)


class TestRunStateFile:
    def test_returns_path_within_folder(self, tmp_path):
        folder = str(tmp_path)
        path = _run_state_file(folder)
        assert path.endswith("_run_state.json")
        assert path.startswith(folder)


class TestLoadRunState:
    def test_returns_empty_when_missing(self, tmp_path):
        assert _load_run_state(str(tmp_path)) == {}

    def test_loads_valid_json(self, tmp_path):
        (tmp_path / "_run_state.json").write_text(
            '{"phase": "scrape", "status": "running"}', encoding="utf-8"
        )
        assert _load_run_state(str(tmp_path)) == {
            "phase": "scrape",
            "status": "running",
        }

    def test_returns_empty_on_corrupt_json(self, tmp_path):
        (tmp_path / "_run_state.json").write_text("not json {", encoding="utf-8")
        assert _load_run_state(str(tmp_path)) == {}

    def test_returns_empty_on_non_dict_payload(self, tmp_path):
        # JSON array at the top — must coerce to empty dict.
        (tmp_path / "_run_state.json").write_text("[1, 2, 3]", encoding="utf-8")
        assert _load_run_state(str(tmp_path)) == {}

    def test_returns_empty_on_io_error(self, tmp_path):
        # A file that exists but raises on read (mocked).
        (tmp_path / "_run_state.json").write_text("{}", encoding="utf-8")
        with patch("builtins.open", side_effect=PermissionError("locked")):
            assert _load_run_state(str(tmp_path)) == {}


class TestSaveRunState:
    def test_writes_json_payload(self, tmp_path):
        _save_run_state(str(tmp_path), {"phase": "scrape"})
        assert json.loads((tmp_path / "_run_state.json").read_text()) == {"phase": "scrape"}

    def test_creates_missing_folder(self, tmp_path):
        target = tmp_path / "sub" / "deeper"
        _save_run_state(str(target), {"phase": "scrape"})
        assert (target / "_run_state.json").exists()

    def test_falls_back_when_atomic_replace_denied(self, tmp_path):
        path = tmp_path / "_run_state.json"
        path.write_text('{"old": true}', encoding="utf-8")

        with patch(
            "primr.core.run_state_io.os.replace",
            side_effect=PermissionError("locked"),
        ):
            _save_run_state(str(tmp_path), {"new": True})

        # Direct overwrite fallback should have replaced contents.
        assert json.loads(path.read_text()) == {"new": True}

    def test_fallback_cleans_up_temp_file(self, tmp_path):
        with patch(
            "primr.core.run_state_io.os.replace",
            side_effect=PermissionError("locked"),
        ):
            _save_run_state(str(tmp_path), {"x": 1})
        # No leftover *.tmp files
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == []


class TestUpdateRunState:
    def test_merges_into_existing_state(self, tmp_path):
        _save_run_state(str(tmp_path), {"phase": "scrape", "count": 1})
        _update_run_state(str(tmp_path), status="done", count=5)
        loaded = _load_run_state(str(tmp_path))
        assert loaded["phase"] == "scrape"
        assert loaded["status"] == "done"
        assert loaded["count"] == 5

    def test_sets_updated_timestamp(self, tmp_path):
        _update_run_state(str(tmp_path), phase="scrape")
        loaded = _load_run_state(str(tmp_path))
        assert "updated_at" in loaded

    def test_initializes_when_state_missing(self, tmp_path):
        _update_run_state(str(tmp_path), phase="init")
        loaded = _load_run_state(str(tmp_path))
        assert loaded["phase"] == "init"


class TestAppendRunEvent:
    def test_creates_events_array(self, tmp_path):
        _append_run_event(str(tmp_path), "scrape", "started", "Beginning")
        loaded = _load_run_state(str(tmp_path))
        assert len(loaded["events"]) == 1
        assert loaded["events"][0]["phase"] == "scrape"
        assert loaded["events"][0]["status"] == "started"
        assert loaded["events"][0]["message"] == "Beginning"

    def test_extra_kwargs_recorded(self, tmp_path):
        _append_run_event(str(tmp_path), "scrape", "completed", "Done", pages=5, errors=0)
        loaded = _load_run_state(str(tmp_path))
        assert loaded["events"][0]["extra"] == {"pages": 5, "errors": 0}

    def test_no_extra_omits_extra_field(self, tmp_path):
        _append_run_event(str(tmp_path), "p", "s", "m")
        loaded = _load_run_state(str(tmp_path))
        assert "extra" not in loaded["events"][0]

    def test_caps_history_at_200(self, tmp_path):
        for i in range(250):
            _append_run_event(str(tmp_path), "p", "s", f"msg-{i}")
        loaded = _load_run_state(str(tmp_path))
        assert len(loaded["events"]) == 200
        # The newest event must be the final one written.
        assert loaded["events"][-1]["message"] == "msg-249"

    def test_recovers_when_events_field_is_not_list(self, tmp_path):
        _save_run_state(str(tmp_path), {"events": "corrupt"})
        _append_run_event(str(tmp_path), "p", "s", "m")
        loaded = _load_run_state(str(tmp_path))
        assert isinstance(loaded["events"], list)
        assert len(loaded["events"]) == 1


class TestEnsureResilienceKeys:
    def test_adds_missing_keys(self):
        state: dict = {}
        result = _ensure_resilience_keys(state)
        assert result is state
        for key in ("model_health", "recovery_events", "background_aborts"):
            assert key in result
            assert result[key] == []

    def test_preserves_existing_arrays(self):
        state = {"model_health": [{"x": 1}]}
        _ensure_resilience_keys(state)
        assert state["model_health"] == [{"x": 1}]

    def test_replaces_non_list_value(self):
        state = {"model_health": "not a list"}
        _ensure_resilience_keys(state)
        assert state["model_health"] == []


class TestAppendResilienceEvents:
    def test_append_model_health_event(self, tmp_path):
        _append_model_health_event(str(tmp_path), {"model": "grok", "status": "ok"})
        loaded = _load_run_state(str(tmp_path))
        assert loaded["model_health"] == [{"model": "grok", "status": "ok"}]

    def test_append_recovery_event(self, tmp_path):
        _append_recovery_event(str(tmp_path), {"action": "fallback"})
        loaded = _load_run_state(str(tmp_path))
        assert loaded["recovery_events"] == [{"action": "fallback"}]

    def test_append_background_abort(self, tmp_path):
        _append_background_abort(str(tmp_path), {"reason": "timeout"})
        loaded = _load_run_state(str(tmp_path))
        assert loaded["background_aborts"] == [{"reason": "timeout"}]

    @pytest.mark.parametrize(
        ("fn", "key"),
        [
            (_append_model_health_event, "model_health"),
            (_append_recovery_event, "recovery_events"),
            (_append_background_abort, "background_aborts"),
        ],
    )
    def test_appenders_cap_at_200(self, tmp_path, fn, key):
        for i in range(250):
            fn(str(tmp_path), {"i": i})
        loaded = _load_run_state(str(tmp_path))
        assert len(loaded[key]) == 200
        assert loaded[key][-1] == {"i": 249}

    def test_appenders_set_updated_at(self, tmp_path):
        _append_model_health_event(str(tmp_path), {"x": 1})
        assert "updated_at" in _load_run_state(str(tmp_path))


class TestInitRunStateWithResilience:
    def test_writes_state_with_resilience_keys(self, tmp_path):
        _init_run_state_with_resilience(str(tmp_path), {"phase": "init", "status": "running"})
        loaded = _load_run_state(str(tmp_path))
        assert loaded["phase"] == "init"
        assert loaded["status"] == "running"
        assert loaded["model_health"] == []
        assert loaded["recovery_events"] == []
        assert loaded["background_aborts"] == []

    def test_preserves_existing_resilience_data(self, tmp_path):
        base = {
            "phase": "running",
            "model_health": [{"m": "grok"}],
        }
        _init_run_state_with_resilience(str(tmp_path), base)
        loaded = _load_run_state(str(tmp_path))
        assert loaded["model_health"] == [{"m": "grok"}]
        # The other two arrays should still be added empty.
        assert loaded["recovery_events"] == []
        assert loaded["background_aborts"] == []
