"""Windows Job Object ownership for one-job worker process trees.

The MCP server creates a named Job Object before it starts a worker and keeps
the sole long-lived handle.  The worker opens that object during its bootstrap,
attaches itself, and immediately closes its copy.  Descendants then inherit the
job, and ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` ensures a controller crash does
not leave browser or provider helper processes behind.

This module is import-safe on every supported platform.  Calls fail clearly on
non-Windows hosts or Python builds without ``ctypes.WinDLL``.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import sys
from typing import Any

JOB_OBJECT_ASSIGN_PROCESS = 0x0001
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
ERROR_ALREADY_EXISTS = 183
DEFAULT_TERMINATION_EXIT_CODE = 130

__all__ = ["WindowsJobObject", "attach_current_process", "create_worker_job"]


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _require_job_name(name: str) -> None:
    if not name:
        raise ValueError("Windows Job Object name must not be empty")
    if "\x00" in name:
        raise ValueError("Windows Job Object name must not contain NUL bytes")


def _load_kernel32() -> Any:
    if sys.platform != "win32":
        raise OSError("Windows Job Objects are only available on Windows")

    factory = getattr(ctypes, "WinDLL", None)
    if factory is None:
        raise OSError("Windows Job Objects require ctypes.WinDLL, which is unavailable")
    try:
        kernel32 = factory("kernel32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        raise OSError("Unable to load kernel32 for Windows Job Object support") from exc
    _configure_kernel32(kernel32)
    return kernel32


def _configure_kernel32(kernel32: Any) -> None:
    """Declare every Win32 function signature used by this module."""
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE

    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL

    kernel32.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenJobObjectW.restype = wintypes.HANDLE

    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE

    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    kernel32.SetLastError.argtypes = [wintypes.DWORD]
    kernel32.SetLastError.restype = None

    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD


def _handle_value(handle: object) -> int:
    value = getattr(handle, "value", handle)
    if not isinstance(value, int) or value == 0:
        raise OSError("Windows returned an invalid Job Object handle")
    return value


def _windows_error(kernel32: Any, operation: str) -> OSError:
    error_code = int(kernel32.GetLastError())
    formatter = getattr(ctypes, "FormatError", None)
    detail = ""
    if formatter is not None and error_code:
        try:
            detail = str(formatter(error_code)).strip()
        except (AttributeError, OSError, ValueError):
            detail = ""
    suffix = detail or f"Windows error {error_code}"
    return OSError(error_code, f"{operation} failed: {suffix}")


def _close_raw_handle(kernel32: Any, handle: int) -> None:
    if not kernel32.CloseHandle(handle):
        raise _windows_error(kernel32, "CloseHandle")


class WindowsJobObject:
    """Owner for a configured Windows Job Object handle."""

    __slots__ = ("_handle", "_kernel32", "name")

    def __init__(self, *, name: str, kernel32: Any, handle: int) -> None:
        self.name = name
        self._kernel32 = kernel32
        self._handle: int | None = handle

    @property
    def closed(self) -> bool:
        return self._handle is None

    def terminate(self, exit_code: int = DEFAULT_TERMINATION_EXIT_CODE) -> None:
        """Immediately terminate every process associated with this job."""
        if self._handle is None:
            raise OSError("Cannot terminate a closed Windows Job Object")
        if not 0 <= exit_code <= 0xFFFFFFFF:
            raise ValueError("Windows Job Object exit code must fit in an unsigned 32-bit value")
        if not self._kernel32.TerminateJobObject(self._handle, exit_code):
            raise _windows_error(self._kernel32, "TerminateJobObject")

    def close(self) -> None:
        """Close the owner handle; repeated calls are safe."""
        if self._handle is None:
            return
        handle = self._handle
        _close_raw_handle(self._kernel32, handle)
        self._handle = None

    def __enter__(self) -> WindowsJobObject:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


def create_worker_job(name: str) -> WindowsJobObject:
    """Create and configure a uniquely named worker Job Object.

    Existing names fail closed.  Reusing one could let an unrelated worker
    join the same termination boundary.
    """
    _require_job_name(name)
    kernel32 = _load_kernel32()

    kernel32.SetLastError(0)
    raw_handle = kernel32.CreateJobObjectW(None, name)
    if not raw_handle:
        raise _windows_error(kernel32, "CreateJobObjectW")
    handle = _handle_value(raw_handle)

    create_error = int(kernel32.GetLastError())
    if create_error == ERROR_ALREADY_EXISTS:
        try:
            _close_raw_handle(kernel32, handle)
        finally:
            raise OSError(
                ERROR_ALREADY_EXISTS,
                f"Windows worker Job Object already exists: {name!r}",
            )

    limits = _JobObjectExtendedLimitInformation()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    configured = kernel32.SetInformationJobObject(
        handle,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    )
    if not configured:
        configure_error = _windows_error(kernel32, "SetInformationJobObject")
        try:
            _close_raw_handle(kernel32, handle)
        except OSError as close_error:
            configure_error.add_note(str(close_error))
        raise configure_error

    return WindowsJobObject(name=name, kernel32=kernel32, handle=handle)


def attach_current_process(name: str) -> None:
    """Attach the calling worker to an existing named Job Object.

    The temporary handle is always closed.  The controller must retain its
    owner handle for the worker lifetime.
    """
    _require_job_name(name)
    kernel32 = _load_kernel32()

    raw_handle = kernel32.OpenJobObjectW(JOB_OBJECT_ASSIGN_PROCESS, False, name)
    if not raw_handle:
        raise _windows_error(kernel32, "OpenJobObjectW")
    handle = _handle_value(raw_handle)

    primary_error: OSError | None = None
    try:
        current_process = kernel32.GetCurrentProcess()
        if not current_process:
            raise _windows_error(kernel32, "GetCurrentProcess")
        if not kernel32.AssignProcessToJobObject(handle, current_process):
            raise _windows_error(kernel32, "AssignProcessToJobObject")
    except OSError as exc:
        primary_error = exc

    try:
        _close_raw_handle(kernel32, handle)
    except OSError as close_error:
        if primary_error is not None:
            primary_error.add_note(str(close_error))
        else:
            raise

    if primary_error is not None:
        raise primary_error
