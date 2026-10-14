"""Tie tool processes to this process's life (Windows): when VideoForge goes, however it goes, they go too.

Each tool starts suspended, joins one Job Object with KILL_ON_JOB_CLOSE, then resumes, so the children it
starts (DeeZy's ffmpeg/DEE/truehdd) are in the job from the start. The job's handle stays open for the
process's lifetime; Windows closes it on exit or crash and ends everything in the job.
Elsewhere this is a no-op (in Docker the container stopping ends everything anyway).
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import threading
from ctypes import wintypes

log = logging.getLogger(__name__)

# Popen creationflag for tools that adopt() takes over.
SUSPENDED = getattr(subprocess, "CREATE_SUSPENDED", 0x4) if os.name == "nt" else 0

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JobObjectExtendedLimitInformation = 9

_lock = threading.Lock()
_job: int | None = None
_failed = False


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


if os.name == "nt":
    # Own instances, so argtypes set here don't clash with other ctypes users of kernel32.
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _ntdll = ctypes.WinDLL("ntdll")
    # Popen keeps no thread handle, so resume the whole process (undocumented, stable since NT).
    _ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    _ntdll.NtResumeProcess.restype = ctypes.c_long


def _get_job() -> int | None:
    global _job, _failed
    with _lock:
        if _job is None and not _failed:
            job = _kernel32.CreateJobObjectW(None, None)
            limits = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if job and _kernel32.SetInformationJobObject(
                    job, _JobObjectExtendedLimitInformation, ctypes.byref(limits), ctypes.sizeof(limits)):
                _job = job
            else:
                log.warning("Couldn't create a job object (error %d); tools may outlive VideoForge",
                            ctypes.get_last_error())
                if job:
                    _kernel32.CloseHandle(job)
                _failed = True
        return _job


def adopt(proc: subprocess.Popen) -> None:
    """Put a tool started with SUSPENDED in the job, then let it run. Always resumes it."""
    if os.name != "nt":
        return
    handle = int(proc._handle)  # type: ignore[attr-defined]
    try:
        job = _get_job()
        if job is not None and not _kernel32.AssignProcessToJobObject(job, handle):
            log.warning("Couldn't add %s to the job object (error %d); it may outlive VideoForge",
                        proc.args[0] if isinstance(proc.args, list) else proc.args, ctypes.get_last_error())
    finally:
        status = _ntdll.NtResumeProcess(handle)
        if status < 0:
            proc.kill()
            raise OSError(f"Couldn't resume {proc.args!r} (NTSTATUS {status & 0xFFFFFFFF:#x})")
