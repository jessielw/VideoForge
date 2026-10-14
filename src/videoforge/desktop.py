"""`videoforge serve --window`: the web app in its own window (pywebview, the `desktop` extra).

A page in a normal browser never learns where a dropped file lives. In the window, pywebview's
drop handler gets the full paths; they go back to the page through `window.videoforgeDropped`,
and `window.videoforgeDesktop` tells the page that drops carry paths.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import uvicorn


def dropped_paths(event: dict[str, Any]) -> list[str]:
    """The full paths in a pywebview drop event (files whose path it couldn't match are left out)."""
    files = (event.get("dataTransfer") or {}).get("files") or []
    return [f["pywebviewFullPath"] for f in files if isinstance(f, dict) and f.get("pywebviewFullPath")]


def run_window(app: Any, host: str, port: int, url: str, data_dir: Path) -> int:
    try:
        import webview
        from webview.dom import DOMEventHandler
    except ImportError:
        print("The window needs pywebview: pip install videoforge[desktop] (or uv sync --extra desktop)")
        return 1

    # Open connections get 5 s to close before the app's shutdown runs (it cancels a running job: up to 10 s).
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning", timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            return 1
        thread.join(0.05)

    # Without a screen, Windows centers it across two monitors: open maximized on the primary one (at 0,0),
    # with a restore size that fits it.
    screen = next((s for s in webview.screens if s.x == 0 and s.y == 0), None)
    width, height = (1500, 950) if screen is None else (min(1500, screen.width * 9 // 10), min(950, screen.height * 9 // 10))
    window = webview.create_window("VideoForge", url, width=width, height=height, min_size=(900, 600), screen=screen,
                                   maximized=True, background_color="#1b1a18")

    def on_drop(event: dict[str, Any]) -> None:
        window.evaluate_js(f"window.videoforgeDropped?.({json.dumps(dropped_paths(event))})")

    def on_loaded() -> None:
        # Each page load gets a fresh document, so the handler is added again.
        window.dom.document.events.drop += DOMEventHandler(on_drop, prevent_default=True)
        window.evaluate_js("window.videoforgeDesktop = true; window.dispatchEvent(new Event('videoforge:desktop'))")

    window.events.loaded += on_loaded
    # Not private: the theme and layout live in the page's localStorage.
    webview.start(private_mode=False, storage_path=str(data_dir / "webview"))
    # Wait for the whole shutdown: the thread is a daemon, so leaving early would cut off the cancel of a
    # running encode (its tools left running) and the database close.
    print("Stopping VideoForge (a running job is cancelled; started again, it skips the steps it finished)...")
    server.should_exit = True
    thread.join()
    return 0
