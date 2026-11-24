"""Process-local file ownership for pipeline steps and preview requests."""

from __future__ import annotations

from collections import Counter
from collections.abc import Hashable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
import threading

from videoforge.core.execute.process import Cancelled, CancelToken


class Claims:
    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.readers: Counter[Hashable] = Counter()
        self.writers: set[Hashable] = set()

    @contextmanager
    def hold(
        self, reads: Iterable[Hashable] = (), writes: Iterable[Hashable] = (), cancel: CancelToken | None = None
    ) -> Iterator[None]:
        def keys(items: Iterable[Hashable]) -> set[Hashable]:
            return {item.resolve() if isinstance(item, Path) else item for item in set(items)}

        write = keys(writes)
        read = keys(reads) - write
        with self.condition:
            while self.writers.intersection(read | write) or any(key in self.readers for key in write):
                if cancel and cancel.cancelled:
                    raise Cancelled()
                self.condition.wait(0.1 if cancel else None)
            if cancel and cancel.cancelled:
                raise Cancelled()
            self.writers.update(write)
            self.readers.update(read)
        try:
            yield
        finally:
            with self.condition:
                self.writers.difference_update(write)
                for key in read:
                    self.readers[key] -= 1
                    if not self.readers[key]:
                        del self.readers[key]
                self.condition.notify_all()


files = Claims()
producers = Claims()
# Adoption can copy a sibling's completed bytes. Its note must stay valid until that copy finishes.
finished_lock = threading.Lock()
