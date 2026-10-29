"""The server CLI: its settings from flags and VIDEOFORGE_* variables, and a clean exit after Uvicorn shuts down."""

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


def _serve_settings(monkeypatch, argv):
    """The ServerSettings `videoforge serve` builds, without starting the server."""
    seen = []

    def app(settings):
        seen.append(settings)
        return FastAPI()

    monkeypatch.setattr(cli, "_bring_up_running", lambda *args, **kwargs: False)
    monkeypatch.setattr("videoforge.applog.setup", lambda *args: None)
    monkeypatch.setattr("videoforge.server.app.create_app", app)
    monkeypatch.setattr(uvicorn.Server, "run", lambda self: None)
    assert cli.main(["serve", "--no-browser", *argv]) == 0
    return seen[0]


def test_serve_takes_its_settings_from_videoforge_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOFORGE_HOST", "0.0.0.0")  # noqa: S104 (a setting, not a bind)
    monkeypatch.setenv("VIDEOFORGE_PORT", "9000")
    monkeypatch.setenv("VIDEOFORGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VIDEOFORGE_ALLOW_HOST", "192.168.1.50, tower.local")
    monkeypatch.setenv("VIDEOFORGE_ALLOW_ORIGIN", "https://video.example")
    monkeypatch.setenv("VIDEOFORGE_PLUGIN_MANAGEMENT", "true")

    settings = _serve_settings(monkeypatch, [])

    assert (settings.host, settings.port, settings.data_dir) == ("0.0.0.0", 9000, tmp_path)  # noqa: S104
    assert settings.allowed_hosts == ["192.168.1.50", "tower.local"]
    assert settings.allowed_origins == ["https://video.example"]
    assert settings.can_manage_plugins


def test_serve_flags_win_over_variables_and_add_to_their_lists(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOFORGE_PORT", "9000")
    monkeypatch.setenv("VIDEOFORGE_ALLOW_HOST", "192.168.1.50")
    monkeypatch.setenv("VIDEOFORGE_PLUGIN_MANAGEMENT", "on")

    settings = _serve_settings(
        monkeypatch,
        ["--port", "9001", "--data-dir", str(tmp_path), "--allow-host", "tower.local", "--no-plugin-management"],
    )

    assert settings.port == 9001
    assert settings.allowed_hosts == ["192.168.1.50", "tower.local"]
    assert not settings.can_manage_plugins


def test_serve_refuses_an_unreadable_plugin_management_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOFORGE_PLUGIN_MANAGEMENT", "maybe")
    monkeypatch.setattr(cli, "_bring_up_running", lambda *args, **kwargs: False)

    assert cli.main(["serve", "--no-browser", "--data-dir", str(tmp_path)]) == 2
