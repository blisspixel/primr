"""Unit tests for primr.core.run_state_io.

Direct tests on the JSON read/write/append helpers that persist per-run
state, plus the resilience-array helpers added for pipeline recovery.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
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

    def test_quarantines_corrupt_json(self, tmp_path):
        path = tmp_path / "_run_state.json"
        path.write_text("not json {", encoding="utf-8")
        loaded = _load_run_state(str(tmp_path))
        assert loaded["_recovered_from_corruption"] is True
        assert "JSONDecodeError" in loaded["_corrupt_reason"]
        assert not path.exists()
        assert (tmp_path / "_run_state.json.corrupt").exists()

    def test_quarantines_non_dict_payload(self, tmp_path):
        path = tmp_path / "_run_state.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        loaded = _load_run_state(str(tmp_path))
        assert loaded["_recovered_from_corruption"] is True
        assert loaded["_corrupt_reason"] == "not a JSON object"
        assert (tmp_path / "_run_state.json.corrupt").exists()

    def test_io_error_returns_recovery_marker(self, tmp_path):
        # A file that exists but raises on read (mocked).
        (tmp_path / "_run_state.json").write_text("{}", encoding="utf-8")
        with patch("builtins.open", side_effect=PermissionError("locked")):
            loaded = _load_run_state(str(tmp_path))
        assert loaded["_recovered_from_corruption"] is True
        assert "OSError" in loaded["_corrupt_reason"] or "locked" in loaded["_corrupt_reason"]


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
            "primr.core.run_state_io.atomic_replace",
            side_effect=PermissionError("locked"),
        ):
            _save_run_state(str(tmp_path), {"new": True})

        # Direct overwrite fallback should have replaced contents.
        assert json.loads(path.read_text()) == {"new": True}

    def test_fallback_cleans_up_temp_file(self, tmp_path):
        with patch(
            "primr.core.run_state_io.atomic_replace",
            side_effect=PermissionError("locked"),
        ):
            _save_run_state(str(tmp_path), {"x": 1})
        # No leftover *.tmp files
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == []

    def test_survives_transient_lock_via_atomic_io_seam(self, tmp_path):
        # The retry itself lives in utils.atomic_io; this pins the wiring so a
        # lock that clears within the retry budget never triggers the fallback.
        real_replace = os.replace
        calls = {"n": 0}

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("locked by sync client")
            real_replace(src, dst)

        with (
            patch("primr.utils.atomic_io.os.replace", side_effect=flaky_replace),
            patch("primr.utils.atomic_io.time.sleep"),
        ):
            _save_run_state(str(tmp_path), {"phase": "scrape"})

        assert json.loads((tmp_path / "_run_state.json").read_text()) == {"phase": "scrape"}
        assert calls["n"] == 3
        assert list(tmp_path.glob("*.tmp")) == []

    def test_each_save_uses_a_unique_temporary_path(self, tmp_path):
        temporary_paths = []

        def recording_replace(source, target):
            temporary_paths.append(source)
            os.replace(source, target)

        with patch("primr.core.run_state_io.atomic_replace", side_effect=recording_replace):
            _save_run_state(str(tmp_path), {"sequence": 1})
            _save_run_state(str(tmp_path), {"sequence": 2})

        assert len(temporary_paths) == 2
        assert temporary_paths[0] != temporary_paths[1]

    def test_serialization_failure_creates_no_temporary_file(self, tmp_path):
        with pytest.raises(TypeError):
            _save_run_state(str(tmp_path), {"not_json": object()})

        assert list(tmp_path.glob("._run_state.*.tmp")) == []


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

    def test_concurrent_recovery_appends_preserve_every_event(self, tmp_path):
        event_count = 40

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(
                pool.map(
                    lambda index: _append_recovery_event(str(tmp_path), {"index": index}),
                    range(event_count),
                )
            )

        loaded = _load_run_state(str(tmp_path))
        assert len(loaded["recovery_events"]) == event_count
        assert {event["index"] for event in loaded["recovery_events"]} == set(range(event_count))


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
