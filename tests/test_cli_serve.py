"""The server CLI exits cleanly after Uvicorn finishes shutting down."""

from contextlib import asynccontextmanager
import signal

from fastapi import FastAPI
import pytest
import uvicorn

from videoforge import cli


@pytest.mark.parametrize("interrupt", [True, False], ids=["ctrl-c", "api-shutdown"])
def test_serve_runs_lifespan_cleanup_before_exiting(tmp_path, monkeypatch, interrupt):
    lifecycle = []
    replayed = []

    @asynccontextmanager
    async def lifespan(app):
        lifecycle.append("started")
        try:
            yield
        finally:
            lifecycle.append("stopped")

    app = FastAPI(lifespan=lifespan)

    async def stop(server):
        if interrupt:
            server.handle_exit(signal.SIGINT, None)
        else:
            app.state.shutdown()

    def replay(sig):
        # Exercise Uvicorn's signal replay without sending a signal to pytest.
        replayed.append(sig)
        assert lifecycle == ["started", "stopped"]
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_bring_up_running", lambda *args, **kwargs: False)
    monkeypatch.setattr("videoforge.applog.setup", lambda *args: None)
    monkeypatch.setattr("videoforge.server.app.create_app", lambda settings: app)
    monkeypatch.setattr(uvicorn.Server, "main_loop", stop)
    monkeypatch.setattr(signal, "raise_signal", replay)

    try:
        result = cli.main(["serve", "--no-browser", "--port", "0", "--data-dir", str(tmp_path)])
    except KeyboardInterrupt:
        pytest.fail("Ctrl+C escaped the server CLI after shutdown")

    assert result == 0
    assert lifecycle == ["started", "stopped"]
    assert replayed == ([signal.SIGINT] if interrupt else [])
