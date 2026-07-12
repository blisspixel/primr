"""Platform-independent tests for the Windows Job Object wrapper."""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from typing import Any

import pytest

from primr.mcp_server import windows_job


class _FakeFunction:
    def __init__(
        self,
        return_value: object = 1,
        side_effect: Callable[..., object] | None = None,
    ) -> None:
        self.return_value = return_value
        self.side_effect = side_effect
        self.calls: list[tuple[object, ...]] = []
        self.argtypes: list[object] | None = None
        self.restype: object = None

    def __call__(self, *args: object) -> object:
        self.calls.append(args)
        if self.side_effect is not None:
            return self.side_effect(*args)
        return self.return_value


class _FakeKernel32:
    def __init__(self) -> None:
        self.last_error = 0
        self.create_handle = 101
        self.create_error = 0

        self.SetLastError = _FakeFunction(side_effect=self._set_last_error)
        self.GetLastError = _FakeFunction(side_effect=self._get_last_error)
        self.CreateJobObjectW = _FakeFunction(side_effect=self._create_job)
        self.SetInformationJobObject = _FakeFunction(1)
        self.OpenJobObjectW = _FakeFunction(202)
        self.AssignProcessToJobObject = _FakeFunction(1)
        self.GetCurrentProcess = _FakeFunction(303)
        self.TerminateJobObject = _FakeFunction(1)
        self.CloseHandle = _FakeFunction(1)

    def _set_last_error(self, value: object) -> None:
        self.last_error = int(value)  # type: ignore[arg-type]

    def _get_last_error(self) -> int:
        return self.last_error

    def _create_job(self, _security: object, _name: object) -> int:
        self.last_error = self.create_error
        return self.create_handle


@pytest.fixture
def fake_windows(monkeypatch: pytest.MonkeyPatch) -> _FakeKernel32:
    kernel32 = _FakeKernel32()
    monkeypatch.setattr(windows_job.sys, "platform", "win32")
    monkeypatch.setattr(windows_job, "_load_kernel32", lambda: _configured(kernel32))
    return kernel32


def _configured(kernel32: _FakeKernel32) -> _FakeKernel32:
    windows_job._configure_kernel32(kernel32)
    return kernel32


def test_calls_fail_clearly_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows_job.sys, "platform", "linux")

    with pytest.raises(OSError, match="only available on Windows"):
        windows_job.create_worker_job("Local\\Primr-test")
    with pytest.raises(OSError, match="only available on Windows"):
        windows_job.attach_current_process("Local\\Primr-test")


def test_missing_windll_fails_only_when_called(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows_job.sys, "platform", "win32")
    monkeypatch.setattr(windows_job.ctypes, "WinDLL", None, raising=False)

    with pytest.raises(OSError, match=r"ctypes\.WinDLL"):
        windows_job.create_worker_job("Local\\Primr-test")


def test_create_configures_kill_on_close_and_explicit_signatures(
    fake_windows: _FakeKernel32,
) -> None:
    owner = windows_job.create_worker_job("Local\\Primr-test")

    assert owner.name == "Local\\Primr-test"
    assert owner.closed is False
    assert fake_windows.CreateJobObjectW.calls == [(None, "Local\\Primr-test")]

    set_info_call = fake_windows.SetInformationJobObject.calls[0]
    assert set_info_call[0] == 101
    assert set_info_call[1] == windows_job.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS
    info = set_info_call[2]._obj  # type: ignore[attr-defined]
    assert info.BasicLimitInformation.LimitFlags == windows_job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    assert set_info_call[3] == ctypes.sizeof(windows_job._JobObjectExtendedLimitInformation)

    assert fake_windows.CreateJobObjectW.argtypes is not None
    assert fake_windows.CreateJobObjectW.restype is windows_job.wintypes.HANDLE
    assert fake_windows.TerminateJobObject.argtypes is not None
    assert fake_windows.CloseHandle.argtypes is not None


def test_create_rejects_existing_name_and_closes_handle(
    fake_windows: _FakeKernel32,
) -> None:
    fake_windows.create_error = windows_job.ERROR_ALREADY_EXISTS

    with pytest.raises(OSError, match="already exists") as exc_info:
        windows_job.create_worker_job("Local\\Primr-duplicate")

    assert exc_info.value.errno == windows_job.ERROR_ALREADY_EXISTS
    assert fake_windows.CloseHandle.calls == [(101,)]
    assert fake_windows.SetInformationJobObject.calls == []


def test_create_configuration_failure_closes_handle(fake_windows: _FakeKernel32) -> None:
    fake_windows.SetInformationJobObject.return_value = 0
    fake_windows.last_error = 5

    with pytest.raises(OSError, match="SetInformationJobObject"):
        windows_job.create_worker_job("Local\\Primr-test")

    assert fake_windows.CloseHandle.calls == [(101,)]


def test_owner_terminates_and_close_is_idempotent(fake_windows: _FakeKernel32) -> None:
    owner = windows_job.create_worker_job("Local\\Primr-test")

    owner.terminate()
    owner.close()
    owner.close()

    assert fake_windows.TerminateJobObject.calls == [
        (101, windows_job.DEFAULT_TERMINATION_EXIT_CODE)
    ]
    assert fake_windows.CloseHandle.calls == [(101,)]
    assert owner.closed is True
    with pytest.raises(OSError, match="closed"):
        owner.terminate()


def test_owner_surfaces_terminate_and_close_failures(fake_windows: _FakeKernel32) -> None:
    owner = windows_job.create_worker_job("Local\\Primr-test")
    fake_windows.last_error = 5
    fake_windows.TerminateJobObject.return_value = 0

    with pytest.raises(OSError, match="TerminateJobObject"):
        owner.terminate()

    fake_windows.CloseHandle.return_value = 0
    with pytest.raises(OSError, match="CloseHandle"):
        owner.close()
    assert owner.closed is False


def test_attach_assigns_current_process_then_closes_temporary_handle(
    fake_windows: _FakeKernel32,
) -> None:
    windows_job.attach_current_process("Local\\Primr-test")

    assert fake_windows.OpenJobObjectW.calls == [
        (windows_job.JOB_OBJECT_ASSIGN_PROCESS, False, "Local\\Primr-test")
    ]
    assert fake_windows.GetCurrentProcess.calls == [()]
    assert fake_windows.AssignProcessToJobObject.calls == [(202, 303)]
    assert fake_windows.CloseHandle.calls == [(202,)]
    assert fake_windows.OpenJobObjectW.argtypes is not None
    assert fake_windows.AssignProcessToJobObject.argtypes is not None


def test_attach_open_failure_is_fail_closed(fake_windows: _FakeKernel32) -> None:
    fake_windows.OpenJobObjectW.return_value = 0
    fake_windows.last_error = 2

    with pytest.raises(OSError, match="OpenJobObjectW"):
        windows_job.attach_current_process("Local\\Primr-missing")

    assert fake_windows.AssignProcessToJobObject.calls == []
    assert fake_windows.CloseHandle.calls == []


def test_attach_assignment_failure_still_closes_handle(fake_windows: _FakeKernel32) -> None:
    fake_windows.AssignProcessToJobObject.return_value = 0
    fake_windows.last_error = 5

    with pytest.raises(OSError, match="AssignProcessToJobObject"):
        windows_job.attach_current_process("Local\\Primr-test")

    assert fake_windows.CloseHandle.calls == [(202,)]


@pytest.mark.parametrize("name", ["", "bad\x00name"])
def test_invalid_names_fail_before_loading_kernel32(
    name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = False

    def _unexpected_load() -> Any:
        nonlocal loaded
        loaded = True
        return _FakeKernel32()

    monkeypatch.setattr(windows_job, "_load_kernel32", _unexpected_load)

    with pytest.raises(ValueError, match="name"):
        windows_job.create_worker_job(name)
    assert loaded is False
