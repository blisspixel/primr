"""Cooperating usage writers preserve each other's committed records."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from primr.utils import usage_tracker


def _write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def _companies(path):
    return [record["company"] for record in json.loads(path.read_text(encoding="utf-8"))]


def test_stale_tracker_save_preserves_another_installations_migration(tmp_path):
    durable = tmp_path / "data" / "usage_history.json"
    legacy = tmp_path / "other-install" / "usage_history.json"
    _write(durable, [{"company": "CurrentCo"}])
    _write(legacy, [{"company": "LegacyCo"}])
    tracker = usage_tracker.UsageTracker(storage_path=durable)
    usage_tracker._migrate_usage_history(legacy, durable)
    tracker.record_usage("fast", "NewCo", 1, 1)
    tracker.save()
    usage_tracker._migrate_usage_history(legacy, durable)
    assert _companies(durable) == ["CurrentCo", "LegacyCo", "NewCo"]


def test_failed_save_retry_preserves_other_live_trackers_records(tmp_path, monkeypatch):
    durable = tmp_path / "usage_history.json"
    first = usage_tracker.UsageTracker(storage_path=durable)
    second = usage_tracker.UsageTracker(storage_path=durable)
    first.record_usage("fast", "FirstCo", 1, 1)
    second.record_usage("fast", "SecondCo", 1, 1)

    def fail_replace(*args):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(usage_tracker, "atomic_replace", fail_replace)
        first.save()
    assert not durable.exists()
    assert not list(tmp_path.glob("*.tmp"))
    second.save()
    first.save()
    second.save()
    first.save()
    assert _companies(durable) == ["SecondCo", "FirstCo"]


@pytest.mark.parametrize("content", [b"[broken", b'{"wrong":"shape"}', b"[null]", b"\xff"])
def test_save_rechecks_malformed_history_after_tracker_creation(tmp_path, caplog, content):
    durable = tmp_path / "usage_history.json"
    _write(durable, [{"company": "CurrentCo"}])
    tracker = usage_tracker.UsageTracker(storage_path=durable)
    tracker.record_usage("fast", "NewCo", 1, 1)
    durable.write_bytes(content)
    tracker.save()
    assert durable.read_bytes() == content
    assert "will not be overwritten" in caplog.text
    _write(durable, [{"company": "RepairedCo"}])
    tracker.save()
    tracker.save()
    assert _companies(durable) == ["RepairedCo", "NewCo"]


def test_lock_timeout_keeps_usage_retryable(tmp_path, monkeypatch, caplog):
    durable = tmp_path / "usage_history.json"
    tracker = usage_tracker.UsageTracker(storage_path=durable)
    tracker.record_usage("fast", "NewCo", 1, 1)

    def busy(*args):
        raise TimeoutError("another writer is active")

    with monkeypatch.context() as patch:
        patch.setattr(usage_tracker, "file_mutation_lock", busy)
        tracker.save()
    assert not durable.exists()
    assert "history is busy" in caplog.text
    tracker.save()
    tracker.save()
    assert _companies(durable) == ["NewCo"]


def _wait_for_file(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 10
    while not path.exists():
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            pytest.fail(f"subprocess exited before {path.name}: {stdout}{stderr}")
        if time.monotonic() >= deadline:
            pytest.fail(f"timed out waiting for {path.name}")
        time.sleep(0.01)


@pytest.mark.parametrize(
    "operations",
    [("migrate", "migrate"), ("save", "save"), ("migrate", "save"), ("save", "migrate")],
)
def test_parallel_process_mutations_preserve_committed_records(tmp_path, operations):
    durable = tmp_path / "usage_history.json"
    _write(durable, [{"company": "CurrentCo"}])
    script = """
import json
import sys
import time
from pathlib import Path
from primr.utils import usage_tracker as usage

root, operation, company = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
target = root / 'usage_history.json'
if operation == 'migrate':
    source = root / f'old-install-{company}.json'
    source.write_text(json.dumps([{'company': company}]), encoding='utf-8')
    write_name = 'atomic_write_text'
else:
    tracker = usage.UsageTracker(storage_path=target)
    tracker.record_usage('fast', company, 1, 1)
    write_name = 'atomic_replace'

if company == 'A':
    real_write = getattr(usage, write_name)
    def paused_write(*args):
        (root / 'ready').touch()
        deadline = time.monotonic() + 10
        while not (root / 'continue').exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('parent did not release first writer')
            time.sleep(0.01)
        return real_write(*args)
    setattr(usage, write_name, paused_write)
else:
    (root / 'second-started').touch()

if operation == 'migrate':
    usage._migrate_usage_history(source, target)
else:
    tracker.save()
"""
    processes = []

    def start(company, operation):
        process = subprocess.Popen(
            [sys.executable, "-B", "-c", script, str(tmp_path), operation, company],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(process)
        return process

    try:
        first = start("A", operations[0])
        _wait_for_file(tmp_path / "ready", first)
        second = start("B", operations[1])
        _wait_for_file(tmp_path / "second-started", second)
        time.sleep(0.2)
        assert second.poll() is None, "second writer bypassed the interprocess mutation lock"
        (tmp_path / "continue").touch()
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode == 0, stdout + stderr
    finally:
        (tmp_path / "continue").touch()
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
    assert _companies(durable) == ["CurrentCo", "A", "B"]
    assert len(list(tmp_path.glob("usage_history.migrated-*.json"))) == operations.count("migrate")
    for company, operation in zip(("A", "B"), operations, strict=True):
        if operation == "migrate":
            usage_tracker._migrate_usage_history(tmp_path / f"old-install-{company}.json", durable)
    assert _companies(durable) == ["CurrentCo", "A", "B"]
