from __future__ import annotations

import hashlib
import urllib.error
from pathlib import Path

import pytest

from scripts.verify_release_artifacts import (
    check_existing_release,
    distribution_hashes,
    pypi_hashes,
    verify_release_artifacts,
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_distribution_hashes_requires_one_wheel_and_one_sdist(tmp_path: Path) -> None:
    wheel = b"wheel-content"
    sdist = b"sdist-content"
    (tmp_path / "primr-1.2.3-py3-none-any.whl").write_bytes(wheel)
    (tmp_path / "primr-1.2.3.tar.gz").write_bytes(sdist)

    assert distribution_hashes(tmp_path) == {
        "primr-1.2.3-py3-none-any.whl": _sha256(wheel),
        "primr-1.2.3.tar.gz": _sha256(sdist),
    }


@pytest.mark.parametrize(
    "filenames",
    [
        (),
        ("primr-1.2.3-py3-none-any.whl",),
        ("primr-1.2.3.tar.gz", "notes.txt"),
    ],
)
def test_distribution_hashes_rejects_incomplete_or_extra_artifacts(
    tmp_path: Path, filenames: tuple[str, ...]
) -> None:
    for filename in filenames:
        (tmp_path / filename).write_bytes(filename.encode())

    with pytest.raises(ValueError, match="exactly one wheel and one source distribution"):
        distribution_hashes(tmp_path)


def test_pypi_hashes_extracts_sha256_by_filename() -> None:
    payload = {
        "urls": [
            {"filename": "primr-1.2.3.tar.gz", "digests": {"sha256": "sdist-hash"}},
            {
                "filename": "primr-1.2.3-py3-none-any.whl",
                "digests": {"sha256": "wheel-hash"},
            },
        ]
    }

    assert pypi_hashes(payload) == {
        "primr-1.2.3-py3-none-any.whl": "wheel-hash",
        "primr-1.2.3.tar.gz": "sdist-hash",
    }


def test_verify_release_artifacts_retries_until_pypi_matches(tmp_path: Path) -> None:
    wheel_name = "primr-1.2.3-py3-none-any.whl"
    sdist_name = "primr-1.2.3.tar.gz"
    wheel = b"wheel-content"
    sdist = b"sdist-content"
    (tmp_path / wheel_name).write_bytes(wheel)
    (tmp_path / sdist_name).write_bytes(sdist)
    responses = iter(
        [
            {"urls": []},
            {
                "urls": [
                    {"filename": wheel_name, "digests": {"sha256": _sha256(wheel)}},
                    {"filename": sdist_name, "digests": {"sha256": _sha256(sdist)}},
                ]
            },
        ]
    )
    sleeps: list[float] = []

    result = verify_release_artifacts(
        package="primr",
        version="1.2.3",
        dist_dir=tmp_path,
        attempts=2,
        delay_seconds=0.25,
        fetch_payload=lambda _package, _version: next(responses),
        sleep=sleeps.append,
    )

    assert result == distribution_hashes(tmp_path)
    assert sleeps == [0.25]


def test_default_retry_window_tolerates_slow_pypi_propagation(tmp_path: Path) -> None:
    wheel_name = "primr-1.2.3-py3-none-any.whl"
    sdist_name = "primr-1.2.3.tar.gz"
    wheel = b"wheel-content"
    sdist = b"sdist-content"
    (tmp_path / wheel_name).write_bytes(wheel)
    (tmp_path / sdist_name).write_bytes(sdist)
    matching = {
        "urls": [
            {"filename": wheel_name, "digests": {"sha256": _sha256(wheel)}},
            {"filename": sdist_name, "digests": {"sha256": _sha256(sdist)}},
        ]
    }
    calls = 0
    sleeps: list[float] = []

    def delayed_payload(_package: str, _version: str):
        nonlocal calls
        calls += 1
        if calls <= 7:
            raise urllib.error.HTTPError(
                url="https://pypi.org/pypi/primr/1.2.3/json",
                code=404,
                msg="Not Found",
                hdrs=None,
                fp=None,
            )
        return matching

    result = verify_release_artifacts(
        package="primr",
        version="1.2.3",
        dist_dir=tmp_path,
        delay_seconds=10,
        fetch_payload=delayed_payload,
        sleep=sleeps.append,
    )

    assert result == distribution_hashes(tmp_path)
    assert calls == 8
    assert sleeps == [10] * 7


def test_verify_release_artifacts_fails_on_persistent_mismatch(tmp_path: Path) -> None:
    (tmp_path / "primr-1.2.3-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "primr-1.2.3.tar.gz").write_bytes(b"sdist")

    with pytest.raises(RuntimeError, match="PyPI artifacts do not match local distributions"):
        verify_release_artifacts(
            package="primr",
            version="1.2.3",
            dist_dir=tmp_path,
            attempts=1,
            delay_seconds=0,
            fetch_payload=lambda _package, _version: {"urls": []},
            sleep=lambda _seconds: None,
        )


def test_check_existing_release_allows_absent_version(tmp_path: Path) -> None:
    (tmp_path / "primr-1.2.3-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "primr-1.2.3.tar.gz").write_bytes(b"sdist")

    def missing(_package: str, _version: str):
        raise urllib.error.HTTPError(
            url="https://pypi.org/pypi/primr/1.2.3/json",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    assert (
        check_existing_release(
            package="primr",
            version="1.2.3",
            dist_dir=tmp_path,
            fetch_payload=missing,
        )
        == "absent"
    )


def test_check_existing_release_accepts_exact_match(tmp_path: Path) -> None:
    wheel_name = "primr-1.2.3-py3-none-any.whl"
    sdist_name = "primr-1.2.3.tar.gz"
    wheel = b"wheel"
    sdist = b"sdist"
    (tmp_path / wheel_name).write_bytes(wheel)
    (tmp_path / sdist_name).write_bytes(sdist)

    state = check_existing_release(
        package="primr",
        version="1.2.3",
        dist_dir=tmp_path,
        fetch_payload=lambda _package, _version: {
            "urls": [
                {"filename": wheel_name, "digests": {"sha256": _sha256(wheel)}},
                {"filename": sdist_name, "digests": {"sha256": _sha256(sdist)}},
            ]
        },
    )

    assert state == "matching"


def test_check_existing_release_rejects_partial_or_mismatched_version(tmp_path: Path) -> None:
    (tmp_path / "primr-1.2.3-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "primr-1.2.3.tar.gz").write_bytes(b"sdist")

    with pytest.raises(RuntimeError, match="Existing PyPI release does not exactly match"):
        check_existing_release(
            package="primr",
            version="1.2.3",
            dist_dir=tmp_path,
            fetch_payload=lambda _package, _version: {"urls": []},
        )
