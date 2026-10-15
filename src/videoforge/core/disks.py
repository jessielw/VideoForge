"""Which physical disk a path is on, so two jobs don't read one disk at once (the index lane waits
for an encode on the same disk).

Windows: the volume's disk numbers (IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS), so two partitions of one
drive count as one; a network path counts by its server. Elsewhere: the file system's device
(`st_dev`). Anything that can't be read falls back to the volume or drive root. Looked up once per
volume.
"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path


def disks(path: Path | str) -> frozenset[str]:
    """The disks under a path (a file or folder; it needn't exist yet). Empty if unknown."""
    return _disks(str(path))


@lru_cache(maxsize=1024)  # asked every second while the index lane waits; a path stays on its disk
def _disks(path: str) -> frozenset[str]:
    if os.name == "nt":
        root = _volume_root(path)
        return _windows_disks(root) if root else frozenset()
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return frozenset({f"dev:{p.stat().st_dev}"})
    except OSError:
        return frozenset()


def _volume_root(path: str) -> str:
    import ctypes

    buf = ctypes.create_unicode_buffer(1024)
    if ctypes.windll.kernel32.GetVolumePathNameW(os.path.abspath(path), buf, len(buf)):
        return buf.value
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    return drive + "\\" if drive else ""


@lru_cache(maxsize=64)
def _windows_disks(root: str) -> frozenset[str]:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    if root.startswith("\\\\"):  # \\server\share\
        return frozenset({"net:" + root.lstrip("\\").split("\\")[0].lower()})
    if k32.GetDriveTypeW(root) == 4:  # DRIVE_REMOTE: a mapped network drive
        unc = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(unc))
        if ctypes.windll.mpr.WNetGetConnectionW(root.rstrip("\\"), unc, ctypes.byref(size)) == 0:
            return frozenset({"net:" + unc.value.lstrip("\\").split("\\")[0].lower()})
        return frozenset({"net:" + root.lower()})
    name = ctypes.create_unicode_buffer(64)
    if not k32.GetVolumeNameForVolumeMountPointW(root, name, len(name)):
        return frozenset({"vol:" + root.lower()})
    volume = name.value.rstrip("\\")  # \\?\Volume{guid}
    found = _disk_numbers(volume)
    return frozenset(f"disk:{n}" for n in found) if found else frozenset({"vol:" + volume.lower()})


def _disk_numbers(volume: str) -> list[int]:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32")  # its own function objects: the argtypes don't leak to other users
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    k32.DeviceIoControl.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    # No access rights needed for this query; share read/write, open existing.
    handle = k32.CreateFileW(volume, 0, 0x1 | 0x2, None, 3, 0, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        return []
    try:
        # VOLUME_DISK_EXTENTS: DWORD count (padded to 8), then DISK_EXTENT {DWORD disk (padded), INT64 start, INT64 length}
        out = ctypes.create_string_buffer(8 + 24 * 32)
        got = wintypes.DWORD()
        if not k32.DeviceIoControl(handle, 0x00560000, None, 0, out, len(out), ctypes.byref(got), None):
            return []
        count = int.from_bytes(out.raw[:4], "little")
        return sorted({int.from_bytes(out.raw[8 + 24 * i : 12 + 24 * i], "little") for i in range(min(count, 32))})
    finally:
        k32.CloseHandle(handle)
