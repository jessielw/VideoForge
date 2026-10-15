"""FFMS2's index with progress: the VapourSynth plugin's Source() indexes silently, so the index step
builds the index here first, through the plugin's own library (ffms2.dll exports FFMS2's C API),
printing "ffms2 index progress N%" lines. Source() then reads the finished index from its cachefile.

    python -m videoforge.core.video.ffindex <source> <cachefile>

The library is the one VapourSynth loads as the ffms2 plugin (so the index matches it). A valid index
already there is kept. A new one is written next to the cachefile and moved into place when complete,
so a cancelled run leaves none.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys

_IEH_ABORT = 0  # FFMS_IEH_ABORT: as Source() indexes
_PROGRESS = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int64, ctypes.c_int64, ctypes.c_void_p)


class _ErrorInfo(ctypes.Structure):
    _fields_ = [
        ("ErrorType", ctypes.c_int),
        ("SubType", ctypes.c_int),
        ("BufferSize", ctypes.c_int),
        ("Buffer", ctypes.c_char_p),
    ]


def plugin_path() -> str:
    """ffms2.dll as VapourSynth finds it (its plugin folders, VAPOURSYNTH_EXTRA_PLUGIN_PATH)."""
    import vapoursynth as vs

    return vs.core.ffms2.plugin_path  # pyright: ignore[reportAttributeAccessIssue]  (plugins aren't in the stubs)


def _path(p: Path) -> bytes:
    return str(p).encode("utf-8") if os.name == "nt" else os.fsencode(p)  # FFMS2 takes UTF-8 on Windows


def make_index(source: Path, cachefile: Path, dll: str | None = None, out=sys.stdout) -> None:
    lib = ctypes.CDLL(dll or plugin_path())
    lib.FFMS_CreateIndexer.restype = ctypes.c_void_p
    lib.FFMS_CreateIndexer.argtypes = [ctypes.c_char_p, ctypes.POINTER(_ErrorInfo)]
    lib.FFMS_SetProgressCallback.argtypes = [ctypes.c_void_p, _PROGRESS, ctypes.c_void_p]
    lib.FFMS_DoIndexing2.restype = ctypes.c_void_p
    lib.FFMS_DoIndexing2.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(_ErrorInfo)]
    lib.FFMS_WriteIndex.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(_ErrorInfo)]
    lib.FFMS_DestroyIndex.argtypes = [ctypes.c_void_p]
    lib.FFMS_ReadIndex.restype = ctypes.c_void_p
    lib.FFMS_ReadIndex.argtypes = [ctypes.c_char_p, ctypes.POINTER(_ErrorInfo)]
    lib.FFMS_IndexBelongsToFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(_ErrorInfo)]
    lib.FFMS_Init(0, 0)

    buf = ctypes.create_string_buffer(1024)
    err = _ErrorInfo(0, 0, len(buf), ctypes.cast(buf, ctypes.c_char_p))

    if cachefile.is_file() and (old := lib.FFMS_ReadIndex(_path(cachefile), ctypes.byref(err))):
        belongs = lib.FFMS_IndexBelongsToFile(old, _path(source), ctypes.byref(err)) == 0  # as Source() checks
        lib.FFMS_DestroyIndex(old)
        if belongs:
            out.write("ffms2 index: already there\n")
            return

    def failed(what: str) -> RuntimeError:
        return RuntimeError(f"{what}: {buf.value.decode('utf-8', 'replace') or 'unknown error'}")

    indexer = lib.FFMS_CreateIndexer(_path(source), ctypes.byref(err))
    if not indexer:
        raise failed("Can't open the source")
    last = [-1]

    def progress(current: int, total: int, _private: object) -> int:
        pct = int(current * 100 / total) if total > 0 else 0
        if pct != last[0] and pct < 100:  # 100% once it's written
            last[0] = pct
            out.write(f"ffms2 index progress {pct}%\n")
            out.flush()
        return 0  # go on (a cancel kills this process)

    callback = _PROGRESS(progress)  # kept alive for the call
    lib.FFMS_SetProgressCallback(indexer, callback, None)
    index = lib.FFMS_DoIndexing2(indexer, _IEH_ABORT, ctypes.byref(err))  # frees the indexer
    if not index:
        raise failed("Indexing failed")
    partial = cachefile.with_name(cachefile.name + ".partial")
    try:
        if lib.FFMS_WriteIndex(_path(partial), index, ctypes.byref(err)):
            raise failed("Can't write the index")
    finally:
        lib.FFMS_DestroyIndex(index)
    os.replace(partial, cachefile)
    out.write("ffms2 index progress 100%\n")


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python -m videoforge.core.video.ffindex <source> <cachefile>")
    try:
        make_index(Path(sys.argv[1]), Path(sys.argv[2]))
    except Exception as e:  # the message is the step's error
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
