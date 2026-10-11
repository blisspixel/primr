"""Durable usage storage and lossless migration of installed histories."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from primr.utils import usage_tracker


@pytest.fixture
def history_paths(tmp_path, monkeypatch):
    legacy = tmp_path / "old-install" / "logs" / "usage_history.json"
    legacy.parent.mkdir(parents=True)
    durable = tmp_path / "data" / "usage_history.json"
    monkeypatch.setenv("PRIMR_DATA_DIR", str(durable.parent))
    monkeypatch.setattr(usage_tracker, "LEGACY_USAGE_FILE", legacy)
    return legacy, durable


def _write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def test_default_uses_current_data_override_and_not_invocation_directory(
    history_paths, monkeypatch
):
    _legacy, durable = history_paths
    monkeypatch.chdir(durable.parent.parent)
    tracker = usage_tracker.UsageTracker()
    assert tracker.storage_path == durable
    monkeypatch.setenv("PRIMR_DATA_DIR", str(durable.parent / "other"))
    assert usage_tracker.UsageTracker().storage_path == durable.parent / "other" / durable.name


def test_default_honors_xdg_data_home(history_paths, monkeypatch):
    _legacy, durable = history_paths
    monkeypatch.delenv("PRIMR_DATA_DIR")
    monkeypatch.setattr("primr.utils.user_cache.sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(durable.parent))
    assert usage_tracker.UsageTracker().storage_path == durable.parent / "primr" / durable.name


def test_explicit_storage_path_skips_default_and_migration(history_paths, monkeypatch):
    legacy, durable = history_paths
    _write(legacy, [{"company": "LegacyCo"}])
    explicit = durable.parent.parent / "isolated.json"
    monkeypatch.setattr(
        usage_tracker, "get_usage_file", lambda: pytest.fail("Explicit path resolved the default")
    )
    tracker = usage_tracker.UsageTracker(storage_path=explicit)
    tracker.save()
    assert tracker.storage_path == explicit
    assert json.loads(explicit.read_text(encoding="utf-8")) == []
    assert not durable.exists()
    assert legacy.exists()


def test_legacy_import_preserves_cost_fields_and_survives_install_removal(history_paths):
    legacy, durable = history_paths
    records = [{"company": "ExampleCo", "total_cost": 1.23, "cached_input_tokens": 42}]
    _write(legacy, records)
    original = legacy.read_bytes()
    assert usage_tracker.UsageTracker().history == records
    assert legacy.read_bytes() == original
    assert next(durable.parent.glob("usage_history.migrated-*.json")).read_bytes() == original
    shutil.rmtree(legacy.parent.parent)
    assert usage_tracker.UsageTracker().history == records


def test_existing_history_merges_conflicting_records_and_duplicate_occurrences(history_paths):
    legacy, durable = history_paths
    first = {"timestamp": "2026-01-01", "company": "ExampleCo", "total_cost": 1.0}
    conflict = {**first, "total_cost": 2.0}
    _write(durable, [first])
    _write(legacy, [first, first, conflict])
    expected = [first, first, conflict]
    assert usage_tracker.UsageTracker().history == expected
    assert usage_tracker.UsageTracker().history == expected
    assert json.loads(durable.read_text(encoding="utf-8")) == expected


def test_migration_can_retry_after_receipt_write_failure(history_paths, monkeypatch):
    legacy, durable = history_paths
    records = [{"company": "ExampleCo", "total_cost": 1.0}]
    _write(legacy, records)
    real_write = usage_tracker.atomic_write_bytes

    def fail_receipt(path, content):
        if ".migrated-" in path.name:
            raise OSError("disk full")
        real_write(path, content)

    with monkeypatch.context() as patch:
        patch.setattr(usage_tracker, "atomic_write_bytes", fail_receipt)
        assert usage_tracker.UsageTracker().history == records
    assert usage_tracker.UsageTracker().history == records
    assert len(list(durable.parent.glob("usage_history.migrated-*.json"))) == 1


def test_failed_atomic_migration_does_not_replace_existing_history(history_paths, monkeypatch):
    legacy, durable = history_paths
    _write(legacy, [{"company": "LegacyCo"}])
    _write(durable, [{"company": "CurrentCo"}])
    before = durable.read_bytes()

    def fail_replace(*args):
        raise PermissionError("locked")

    with monkeypatch.context() as patch:
        patch.setattr("primr.utils.atomic_io.atomic_replace", fail_replace)
        assert usage_tracker.UsageTracker().history == [{"company": "CurrentCo"}]
    assert durable.read_bytes() == before
    assert not list(durable.parent.glob("*.tmp"))
    assert usage_tracker.UsageTracker().history == [
        {"company": "CurrentCo"},
        {"company": "LegacyCo"},
    ]


@pytest.mark.parametrize("content", [b"{broken", b'{"wrong":"shape"}', b"[null]", b"\xff"])
def test_malformed_legacy_bytes_are_preserved_durably(history_paths, caplog, content):
    legacy, durable = history_paths
    legacy.write_bytes(content)
    tracker = usage_tracker.UsageTracker()
    tracker.record_usage("fast", "ExampleCo", 1, 1, pipeline_cost=0.5)
    tracker.save()
    assert len(json.loads(durable.read_text(encoding="utf-8"))) == 1
    assert next(durable.parent.glob("usage_history.legacy-*.json")).read_bytes() == content
    assert legacy.read_bytes() == content
    assert "Original bytes preserved" in caplog.text


def test_malformed_durable_history_is_not_overwritten_and_can_be_repaired(history_paths, caplog):
    legacy, durable = history_paths
    records = [{"company": "LegacyCo", "total_cost": 1.0}]
    _write(legacy, records)
    durable.parent.mkdir(parents=True)
    durable.write_bytes(b"[broken")
    tracker = usage_tracker.UsageTracker()
    tracker.record_usage("fast", "ExampleCo", 1, 1, pipeline_cost=0.5)
    tracker.save()
    assert durable.read_bytes() == b"[broken"
    assert "will not be overwritten" in caplog.text
    assert (
        next(durable.parent.glob("usage_history.legacy-*.json")).read_bytes() == legacy.read_bytes()
    )
    _write(durable, records)
    tracker.save()
    assert len(json.loads(durable.read_text(encoding="utf-8"))) == 2


_history_records = st.lists(
    st.fixed_dictionaries(
        {"company": st.sampled_from(["ExampleCo", "Acme Corp"]), "total_cost": st.integers(0, 5)}
    ),
    max_size=8,
)


@given(current=_history_records, legacy=_history_records)
@settings(max_examples=30)
def test_migration_preserves_record_multiplicity_and_is_idempotent(current, legacy):
    with tempfile.TemporaryDirectory() as directory:
        old = Path(directory) / "old.json"
        durable = Path(directory) / "data" / "usage_history.json"
        _write(old, legacy)
        _write(durable, current)
        expected = Counter((row["company"], row["total_cost"]) for row in current) | Counter(
            (row["company"], row["total_cost"]) for row in legacy
        )
        usage_tracker._migrate_usage_history(old, durable)
        first = durable.read_bytes()
        observed = json.loads(first)
        assert Counter((row["company"], row["total_cost"]) for row in observed) == expected
        usage_tracker._migrate_usage_history(old, durable)
        assert durable.read_bytes() == first
        assert json.loads(old.read_text(encoding="utf-8")) == legacy


def test_installed_layout_uses_durable_history_across_reinstallation(tmp_path):
    """Run from a copied site-packages layout, then replace that installation."""
    package = Path(usage_tracker.__file__).resolve().parents[1]
    environment = tmp_path / "tool-environment"
    installed = environment / "lib" / "python3.13" / "site-packages"
    data = tmp_path / "user-data"
    script = """
import json
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from primr.utils.usage_tracker import UsageTracker
tracker = UsageTracker()
assert not tracker.storage_path.is_relative_to(Path(sys.argv[2]))
assert not tracker.storage_path.is_relative_to(Path(sys.prefix))
if sys.argv[3] == 'record':
    tracker.record_usage('fast', 'ExampleCo', 1, 1, pipeline_cost=0.75)
    tracker.save()
print(json.dumps(tracker.history))
"""
    env = {**os.environ, "PRIMR_DATA_DIR": str(data)}

    def run(action):
        return subprocess.run(
            [sys.executable, "-B", "-c", script, str(installed), str(environment), action],
            env=env,
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

    shutil.copytree(package, installed / "primr", ignore=shutil.ignore_patterns("__pycache__"))
    legacy = installed.parent / "logs" / "usage_history.json"
    _write(legacy, [{"company": "LegacyCo", "total_cost": 0.25}])
    before = json.loads(run("record").stdout)
    assert [record["company"] for record in before] == ["LegacyCo", "ExampleCo"]
    shutil.rmtree(environment)
    shutil.copytree(package, installed / "primr", ignore=shutil.ignore_patterns("__pycache__"))
    assert json.loads(run("read").stdout) == before


def test_explicit_storage_works_without_a_writable_default_data_directory(tmp_path):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("existing file", encoding="utf-8")
    explicit = tmp_path / "explicit.json"
    script = """
import sys
from pathlib import Path
from primr.utils.usage_tracker import UsageTracker
tracker = UsageTracker(storage_path=Path(sys.argv[1]))
tracker.save()
assert tracker.storage_path.read_text(encoding='utf-8') == '[]'
"""
    subprocess.run(
        [sys.executable, "-B", "-c", script, str(explicit)],
        env={**os.environ, "PRIMR_DATA_DIR": str(blocked / "data")},
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
