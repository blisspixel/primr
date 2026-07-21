"""Security contracts for optional vendor strategy context snapshots."""

from pathlib import Path

import pytest

from primr.core.strategy_context import (
    read_stable_vendor_context_block,
    stable_vendor_context_snapshots,
)


def test_regular_vendor_inputs_preserve_order_and_cleanup(tmp_path: Path):
    first = tmp_path / "first.md"
    second = tmp_path / "second.txt"
    first.write_bytes(b"first body")
    second.write_bytes(b"second body")
    snapshot_paths: list[Path] = []

    with stable_vendor_context_snapshots([str(first), str(second)]) as snapshots:
        assert [item.source_path for item in snapshots] == [
            str(first.resolve()),
            str(second.resolve()),
        ]
        snapshot_paths = [Path(item.snapshot_path) for item in snapshots]
        assert [path.read_bytes() for path in snapshot_paths] == [b"first body", b"second body"]
        assert all(path.stat().st_nlink == 1 for path in snapshot_paths)

    assert all(not path.exists() for path in snapshot_paths)


@pytest.mark.parametrize("link_kind", ["symbolic", "hard"])
def test_linked_vendor_input_is_rejected(tmp_path: Path, link_kind: str):
    source = tmp_path / "source.md"
    source.write_text("MUST_NOT_EGRESS", encoding="utf-8")
    linked = tmp_path / "linked.md"
    try:
        if link_kind == "symbolic":
            linked.symlink_to(source)
        else:
            linked.hardlink_to(source)
    except OSError:
        pytest.skip(f"{link_kind} links are unavailable on this filesystem")

    with stable_vendor_context_snapshots([str(linked)]) as snapshots:
        assert snapshots == ()
    assert (
        read_stable_vendor_context_block(
            linked,
            header="Vendor research",
            context_kind="vendor_specific",
        )
        is None
    )


def test_oversized_vendor_input_is_rejected_without_path_disclosure(tmp_path: Path, caplog):
    source = tmp_path / "private-vendor-cache.md"
    source.write_bytes(b"x" * 101)

    with stable_vendor_context_snapshots([str(source)], max_bytes=100) as snapshots:
        assert snapshots == ()

    assert source.name not in caplog.text
    assert str(tmp_path) not in caplog.text


def test_snapshot_cleanup_runs_when_consumer_raises(tmp_path: Path):
    source = tmp_path / "vendor.md"
    source.write_text("vendor body", encoding="utf-8")
    snapshot_path: Path | None = None

    def consume() -> None:
        nonlocal snapshot_path
        with stable_vendor_context_snapshots([str(source)]) as snapshots:
            snapshot_path = Path(snapshots[0].snapshot_path)
            raise RuntimeError("consumer failed")

    with pytest.raises(RuntimeError, match="consumer failed"):
        consume()

    assert snapshot_path is not None
    assert not snapshot_path.exists()
