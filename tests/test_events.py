"""The event bus: subscribers by type, in order; one that raises doesn't stop the others."""

from __future__ import annotations

import pytest

from videoforge.core.events import EventBus, IndexFinished, QueueFinished
from videoforge.core.job import JobStatus


def test_bus_delivers_by_type_in_order_and_survives_a_bad_subscriber(caplog):
    bus = EventBus()
    got: list[tuple[str, object]] = []

    def broken(_e):
        raise RuntimeError("boom")

    bus.subscribe(lambda e: got.append(("queue", e)), QueueFinished)
    bus.subscribe(broken, name="broken one")
    stop = bus.subscribe(lambda e: got.append(("all", e)))
    done = QueueFinished((JobStatus.DONE,), 3.0)
    bus.emit(done)
    assert got == [("queue", done), ("all", done)]
    assert "broken one failed on QueueFinished" in caplog.text

    got.clear()
    stop()
    stop()  # twice is harmless
    bus.emit(IndexFinished(spec=None, error="x"))  # pyright: ignore[reportArgumentType]
    assert got == []


def test_subscribe_refuses_what_isnt_an_event():
    with pytest.raises(TypeError):
        EventBus().subscribe(print, str)
