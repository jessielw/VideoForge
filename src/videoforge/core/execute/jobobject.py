"""Tie tool processes to this process's life (Windows): when VideoForge goes, however it goes, they go too.

Each tool starts suspended, joins one Job Object with KILL_ON_JOB_CLOSE, then resumes, so the children it
starts (DeeZy's ffmpeg/DEE/truehdd) are in the job from the start. The job's handle stays open for the
process's lifetime; Windows closes it on exit or crash and ends everything in the job.
Elsewhere this is a no-op (in Docker the container stopping ends everything anyway).

A ToolJob is one tool's own job, nested in that one: its process and every child it starts, so a pause
suspends them all and a priority reaches them all (execute/control.py).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import subprocess
import threading

log = logging.getLogger(__name__)

# Popen creationflag for tools that adopt() takes over.
SUSPENDED = getattr(subprocess, "CREATE_SUSPENDED", 0x4) if os.name == "nt" else 0

# Priority classes (SetPriorityClass's).
IDLE, BELOW_NORMAL, NORMAL, ABOVE_NORMAL, HIGH = 0x40, 0x4000, 0x20, 0x8000, 0x80

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_LIMIT_PRIORITY_CLASS = 0x20
_JobObjectBasicProcessIdList = 3
_JobObjectExtendedLimitInformation = 9
_PROCESS_SET_INFORMATION = 0x0200
_PROCESS_SUSPEND_RESUME = 0x0800
_MAX_PIDS = 256

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
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _PidList(ctypes.Structure):
    _fields_ = [
        ("NumberOfAssignedProcesses", wintypes.DWORD),
        ("NumberOfProcessIdsInList", wintypes.DWORD),
        ("ProcessIdList", ctypes.c_size_t * _MAX_PIDS),
    ]


if os.name == "nt":
    # Own instances, so argtypes set here don't clash with other ctypes users of kernel32.
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    _kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.SetPriorityClass.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _ntdll = ctypes.WinDLL("ntdll")
    # Popen keeps no thread handle, so suspend and resume whole processes (undocumented, stable since NT).
    _ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    _ntdll.NtResumeProcess.restype = ctypes.c_long
    _ntdll.NtSuspendProcess.argtypes = [wintypes.HANDLE]
    _ntdll.NtSuspendProcess.restype = ctypes.c_long


def _get_job() -> int | None:
    global _job, _failed
    with _lock:
        if _job is None and not _failed:
            job = _kernel32.CreateJobObjectW(None, None)
            limits = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if job and _kernel32.SetInformationJobObject(
                job, _JobObjectExtendedLimitInformation, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                _job = job
            else:
                log.warning(
                    "Couldn't create a job object (error %d); tools may outlive VideoForge", ctypes.get_last_error()
                )
                if job:
                    _kernel32.CloseHandle(job)
                _failed = True
        return _job


def _name(proc: subprocess.Popen) -> object:
    return proc.args[0] if isinstance(proc.args, list) else proc.args


def _join(proc: subprocess.Popen) -> None:
    job = _get_job()
    if job is not None and not _kernel32.AssignProcessToJobObject(job, int(proc._handle)):  # type: ignore[attr-defined]
        log.warning(
            "Couldn't add %s to the job object (error %d); it may outlive VideoForge",
            _name(proc),
            ctypes.get_last_error(),
        )


def _resume(proc: subprocess.Popen) -> None:
    status = _ntdll.NtResumeProcess(int(proc._handle))  # type: ignore[attr-defined]
    if status < 0:
        proc.kill()
        raise OSError(f"Couldn't resume {proc.args!r} (NTSTATUS {status & 0xFFFFFFFF:#x})")


def adopt(proc: subprocess.Popen) -> None:
    """Put a tool started with SUSPENDED in the job, then let it run. Always resumes it."""
    if os.name != "nt":
        return
    try:
        _join(proc)
    finally:
        _resume(proc)


class ToolJob:
    """A tool started with SUSPENDED, put in the job and in a job of its own nested in it, which its children
    join too. start() lets it run; suspend() and resume() pause and go on with all of them; set_priority()
    gives them a priority class. Without its own job (one couldn't be made) these reach the tool alone.
    Windows only; one thread at a time (control.py's lock)."""

    def __init__(self, proc: subprocess.Popen) -> None:
        self.proc = proc
        self._suspended: list[int] = []  # handles of the processes suspend() suspended, for resume()
        self._job: int | None = None
        try:
            _join(proc)
            job = _kernel32.CreateJobObjectW(None, None)
            if job and _kernel32.AssignProcessToJobObject(job, int(proc._handle)):  # type: ignore[attr-defined]
                self._job = job
            else:
                log.warning("Couldn't give %s a job of its own (error %d)", _name(proc), ctypes.get_last_error())
                if job:
                    _kernel32.CloseHandle(job)
        except BaseException:
            _resume(proc)
            raise

    def start(self) -> None:
        """Let the tool run: it started suspended (still suspended after, if suspend() came first)."""
        _resume(self.proc)

    def _pids(self) -> list[int]:
        pids = _PidList()
        if self._job is None or not _kernel32.QueryInformationJobObject(
            self._job, _JobObjectBasicProcessIdList, ctypes.byref(pids), ctypes.sizeof(pids), None
        ):
            return [self.proc.pid]
        return list(pids.ProcessIdList[: pids.NumberOfProcessIdsInList])

    def suspend(self) -> None:
        """Suspend the tool and its children; again until no new one turns up (a child its parent started
        just before the parent was suspended)."""
        seen: set[int] = set()
        while todo := [pid for pid in self._pids() if pid not in seen]:
            for pid in todo:
                seen.add(pid)
                handle = _kernel32.OpenProcess(_PROCESS_SUSPEND_RESUME, False, pid)
                if not handle:
                    continue  # it just ended
                if _ntdll.NtSuspendProcess(handle) < 0:
                    _kernel32.CloseHandle(handle)
                else:
                    self._suspended.append(handle)

    def resume(self) -> None:
        for handle in self._suspended:
            _ntdll.NtResumeProcess(handle)
            _kernel32.CloseHandle(handle)
        self._suspended.clear()

    def set_priority(self, priority_class: int) -> None:
        """Idle and below normal go in as its job's limit, which children started later get too. Above that a
        limit needs a privilege (SeIncreaseBasePriorityPrivilege), so each process gets the class itself, and
        children started later don't."""
        limit = priority_class in (IDLE, BELOW_NORMAL) and self._job is not None
        if self._job is not None:
            limits = _ExtendedLimits()  # no limit: SetPriorityClass works again
            if limit:
                limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_PRIORITY_CLASS
                limits.BasicLimitInformation.PriorityClass = priority_class
            if not _kernel32.SetInformationJobObject(
                self._job, _JobObjectExtendedLimitInformation, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                log.warning("Couldn't set %s's priority (error %d)", _name(self.proc), ctypes.get_last_error())
                limit = False
        if limit:
            return
        for pid in self._pids():
            handle = _kernel32.OpenProcess(_PROCESS_SET_INFORMATION, False, pid)
            if handle:
                if not _kernel32.SetPriorityClass(handle, priority_class):
                    log.warning("Couldn't set process %d's priority (error %d)", pid, ctypes.get_last_error())
                _kernel32.CloseHandle(handle)

    def close(self) -> None:
        """Once the tool has ended (or been killed): its handles go."""
        for handle in self._suspended:
            _kernel32.CloseHandle(handle)
        self._suspended.clear()
        if self._job is not None:
            _kernel32.CloseHandle(self._job)
            self._job = None
