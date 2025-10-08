import asyncio
import os
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from pymediainfo import MediaInfo


class MediaInfoCache:
    """Async-safe in-memory LRU cache for media info.

        - Stores parsed MediaInfo objects returned by `MediaInfo.parse(path)`.
        - max_items: maximum number of entries in the cache. When exceeded, the
          least-recently-used entry is evicted.
        - ttl_seconds: optional TTL (time-to-live) per entry. When set, entries
          older than ttl_seconds are considered expired and will be re-parsed.

        Note: the cached objects are in-process only and are not JSON serializable
        automatically. If you need a serializable representation for HTTP responses
        use the helper `get_or_parse_data(path)` which calls `to_data()` on the
        MediaInfo object when available.

        Concurrency: uses an asyncio.Lock to prevent concurrent writes/evictions
        within the same process. If you call parse of the same file from many
        concurrent tasks, they'll be deduplicated and serialized by the inflight
        future mechanism.

    Usage:
        Use the singleton from any
        module by importing it:

                from app.utils.mediainfo import mediainfo_cache
                info = await mediainfo_cache.get_or_parse(path)

        Key points:
        - The cache is async-only: public APIs are awaitable (e.g. ``get_or_parse``).
            If you need to call them from synchronous code, create and run an event
            loop explicitly (for example, ``asyncio.run(mediainfo_cache.get_or_parse(path))``).
        - The cache is process-local (in-memory). For multi-process deployments
            (multiple workers) use a shared store such as Redis if cross-worker
            sharing is required.
    """

    def __init__(self, max_items: int = 1024, ttl_seconds: int | None = None):
        if max_items <= 0:
            raise ValueError("max_items must be > 0")
        self.max_items = int(max_items)
        self.ttl_seconds = int(ttl_seconds) if ttl_seconds is not None else None
        # OrderedDict[key -> (value, timestamp)] where timestamp = time.time()
        self._cache = OrderedDict[str, tuple[Any, float]]()
        self._lock = asyncio.Lock()
        # track in-flight parsing tasks per cache key to de-dupe concurrent parses
        self._inflight: dict[str, asyncio.Future] = {}

    async def get(self, key: str) -> Any:
        """Return cached value (MediaInfo object) or None if absent/expired."""
        async with self._lock:
            item = self._cache.get(key)
            if item is None:
                return
            value, ts = item
            if self.ttl_seconds is not None and (time.time() - ts) > self.ttl_seconds:
                # expired
                del self._cache[key]
                return
            # mark as recently used
            self._cache.move_to_end(key)
            return value

    async def set(self, key: str, value: Any) -> None:
        """Set value (MediaInfo object) in the cache, evicting LRU if necessary."""
        async with self._lock:
            now = time.time()
            if key in self._cache:
                # replace and move to end
                self._cache[key] = (value, now)
                self._cache.move_to_end(key)
                return
            self._cache[key] = (value, now)
            # evict oldest while above capacity
            while len(self._cache) > self.max_items:
                self._cache.popitem(last=False)

    def _make_cache_key(self, path: str) -> str:
        """Create a stable cache key for a file using path + size + mtime_ns.

        This detects file replacements/edits without hashing the whole file.
        If stat fails, falls back to the raw path string.
        """
        try:
            st = os.stat(path)
            # Use size and mtime_ns for strong, cheap fingerprinting
            return f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}"
        except Exception:
            # Can't stat (file missing or permission) — use path as key so we
            # still cache the parsing result if parsing succeeds.
            return os.path.abspath(path)

    async def get_or_parse(self, path: str) -> Any:
        """Return cached MediaInfo object for `path`, parsing and caching if needed.

        The returned object is the raw MediaInfo instance from `pymediainfo`.
        Use `get_or_parse_data` to obtain a serializable dict.
        """
        key = self._make_cache_key(path)

        # Fast path: cached value
        cached = await self.get(key)
        if cached is not None:
            return cached

        loop = asyncio.get_running_loop()

        # Deduplicate concurrent parses for the same key using an inflight future.
        # We'll create a future and register it under the key while parsing.
        async with self._lock:
            # Re-check cache inside lock to avoid races
            cached = self._cache.get(key)
            if cached is not None:
                value, ts = cached
                if self.ttl_seconds is None or (time.time() - ts) <= self.ttl_seconds:
                    self._cache.move_to_end(key)
                    return value

            existing = self._inflight.get(key)
            if existing is not None:
                fut = existing
                we_created_future = False
                # someone else is parsing — we'll await their future
            else:
                fut = loop.create_future()
                self._inflight[key] = fut
                we_created_future = True

        # If another task created the inflight future, wait for it. If we
        # created the future ourselves, we should proceed to parse and then
        # set the future's result; awaiting our own future would deadlock.
        if not we_created_future:
            if not fut.done():
                try:
                    result = await fut
                    return result
                except Exception:
                    # other task failed — fall through and parse locally
                    pass

        # We are responsible for parsing (either we created the future or
        # the existing one raised). Parse in executor and fulfill the future.
        try:
            parsed = await loop.run_in_executor(None, self._parse_media_info_sync, path)
            await self.set(key, parsed)
            # fulfill the future so other waiters get the result
            try:
                fut.set_result(parsed)
            except Exception:
                # future might be done by another path; ignore
                pass
            return parsed
        except Exception as exc:
            # propagate error to waiting tasks
            try:
                fut.set_exception(exc)
            except Exception:
                pass
            raise
        finally:
            async with self._lock:
                # cleanup
                self._inflight.pop(key, None)

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._cache.clear()

    @staticmethod
    def _parse_media_info_sync(path: str) -> Any:
        """Synchronous parsing helper used via run_in_executor.

        Returns the MediaInfo object from `pymediainfo`. If pymediainfo is not
        available, raises RuntimeError.
        """
        return MediaInfo.parse(path, legacy_stream_display=True)


async def get_or_parse_mediainfo_async(
    cache: MediaInfoCache, path: str
) -> MediaInfo | None:
    """Convenience helper: returns cached MediaInfo object for the given path."""
    return await cache.get_or_parse(path)


async def safe_get_mediainfo_async(path: Path) -> MediaInfo:
    """Helper to safely get MediaInfo object with a fallback."""
    str_path = str(path)
    try:
        # try to get from cache
        return await mediainfo_cache.get_or_parse(str_path)
    except Exception:
        # fallback to direct parsing if cache or pymediainfo isn't available
        return MediaInfo.parse(str_path, legacy_stream_display=True)


__all__ = (
    "MediaInfoCache",
    "mediainfo_cache",
    "get_or_parse_mediainfo_async",
    "safe_get_mediainfo_async",
)


mediainfo_cache: MediaInfoCache = MediaInfoCache(max_items=30, ttl_seconds=3600)
