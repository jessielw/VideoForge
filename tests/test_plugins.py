"""Plugins: found in their folders, checked, switched off, and run on the event bus off the caller's thread."""

from __future__ import annotations

from pathlib import Path
import sys
import textwrap
import threading
import uuid

from videoforge.core.events import EventBus, IndexFinished, QueueFinished
from videoforge.core.job import JobStatus
from videoforge.plugins import API_VERSION, Plugin
from videoforge.plugins.loader import PluginHost, describe, load_plugins


def make_plugin(folder: Path, name: str, code: str, *, pid: str | None = None, module: str | None = None) -> str:
    """A plugin folder; returns its module name (unique, so tests don't share sys.modules)."""
    module = module or f"vfp_{name}_{uuid.uuid4().hex[:6]}"
    root = folder / name
    root.mkdir(parents=True)
    (root / "videoforge-plugin.toml").write_text(f'id = "{pid or name}"\nmodule = "{module}"\n', encoding="utf-8")
    (root / f"{module}.py").write_text(textwrap.dedent(code), encoding="utf-8")
    return module


GOOD = """
    from videoforge.plugins import Plugin
    seen = []
    def setup(ctx):
        (ctx.data_dir / "ready").write_text(ctx.settings.get("greeting", ""))
    def queue_done(event, ctx):
        seen.append((event.left, ctx.id))
        ctx.job_log("job1", "hello")
    def broken(event, ctx):
        raise RuntimeError("plugin bug")
    plugin = Plugin(name="Good", version="1.2", setup=setup, on_queue_finished=queue_done, on_index_finished=broken)
"""


def test_load_and_run(tmp_path, caplog):
    plugins = tmp_path / "plugins"
    module = make_plugin(plugins, "good", GOOD)
    make_plugin(plugins, "Zdupe", GOOD, pid="good")
    make_plugin(plugins, "off", GOOD)
    make_plugin(plugins, "notaplugin", "plugin = 3\n")
    make_plugin(
        plugins,
        "future",
        f"from videoforge.plugins import Plugin\nplugin = Plugin('F', api_version={API_VERSION + 1})\n",
    )
    make_plugin(plugins, "raises", "raise ImportError('needs a package')\n")
    make_plugin(plugins, "exits", "raise SystemExit(2)\n")
    (plugins / "broken").mkdir()
    (plugins / "broken" / "videoforge-plugin.toml").write_text('id = "broken"\nmodule = "a.b"\n', encoding="utf-8")
    (plugins / "not a plugin").mkdir()  # no manifest: passed over

    report = load_plugins(plugins, disabled={"off"})
    assert [p.id for p in report.loaded] == ["good"]
    assert [s.id for s in report.disabled] == ["off"]
    reasons = {Path(f.source).name: f.reason for f in report.failures}
    assert "top-level module" in reasons["broken"]
    assert "taken" in reasons["Zdupe"]
    assert "not int" in reasons["notaplugin"]
    assert "update VideoForge" in reasons["future"]
    assert reasons["raises"] == "needs a package"
    assert "exited" in reasons["exits"]

    view = describe(report, ["off"])
    assert view["loaded"][0] | {"source": ""} == {
        "id": "good",
        "name": "Good",
        "version": "1.2",
        "description": "",
        "source": "",
        "events": ["QueueFinished", "IndexFinished"],
        "enabled": True,
    }
    assert view["disabled"] == [{"id": "off", "source": str(plugins / "off"), "enabled": False}]

    bus = EventBus()
    lines: list[tuple[str, str]] = []
    host = PluginHost(
        report,
        bus,
        data_dir=tmp_path / "data",
        settings={"good": {"greeting": "hi"}},
        job_log=lambda job, line: lines.append((job, line)),
    )
    caller = threading.current_thread()
    bus.emit(IndexFinished(spec=None))  # pyright: ignore[reportArgumentType]
    bus.emit(QueueFinished((JobStatus.DONE,), 1.0, left=2))
    host.wait()
    assert (tmp_path / "data" / "good" / "ready").read_text() == "hi"
    assert sys.modules[module].seen == [(2, "good")]
    assert lines == [("job1", "hello")]
    assert "Plugin good failed on IndexFinished" in caplog.text
    assert threading.current_thread() is caller
    host.close()
    bus.emit(QueueFinished((), 1.0))  # unsubscribed
    assert sys.modules[module].seen == [(2, "good")]


def test_a_module_name_taken_elsewhere_is_refused(tmp_path):
    make_plugin(tmp_path, "json", "plugin = None\n", module="json")
    report = load_plugins(tmp_path)
    assert not report.loaded and "already loaded from somewhere else" in report.failures[0].reason


def test_vendor_folder_goes_on_the_path_after_ours(tmp_path):
    lib = f"vflib_{uuid.uuid4().hex[:6]}"
    make_plugin(
        tmp_path,
        "vend",
        f"import {lib}\nfrom videoforge.plugins import Plugin\nplugin = Plugin({lib}.NAME)\n",
    )
    (tmp_path / "vend" / "vendor").mkdir()
    (tmp_path / "vend" / "vendor" / f"{lib}.py").write_text('NAME = "vendored"\n', encoding="utf-8")
    report = load_plugins(tmp_path)
    assert [p.plugin.name for p in report.loaded] == ["vendored"]
    assert sys.path[-1] == str(tmp_path / "vend" / "vendor")


def test_hooks():
    def f(_e, _c):
        return None

    assert list(Plugin("x", on_job_finished=f).hooks()) != [] and Plugin("x").hooks() == {}


def test_the_example_plugin_loads():
    from videoforge.core.config import PROJECT_ROOT

    report = load_plugins(PROJECT_ROOT / "examples" / "plugins")
    assert [p.id for p in report.loaded] == ["library_scan"] and not report.failures
