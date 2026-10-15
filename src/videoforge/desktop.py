"""`videoforge serve --window`: the web app in its own window (pywebview + pystray, the `desktop` extra).

A page in a normal browser never learns where a dropped file lives. In the window, pywebview's
drop handler gets the full paths; they go back to the page through `window.videoforgeDropped`,
and `window.videoforgeDesktop` tells the page that drops carry paths.

The service keeps running when the window is closed: closing hides it to the tray icon (Open,
Quit). Quit (asks first while a job runs) and Ctrl+C stop everything. pywebview owns the main
thread, so the server runs in a thread and the tray detached, the way Reclaimerr's desktop app does.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
from typing import Any

from PIL import Image, ImageDraw
import uvicorn

APP_ID = "VideoForge.VideoForge"


def dropped_paths(event: dict[str, Any]) -> list[str]:
    """The full paths in a pywebview drop event (files whose path it couldn't match are left out)."""
    files = (event.get("dataTransfer") or {}).get("files") or []
    return [f["pywebviewFullPath"] for f in files if isinstance(f, dict) and f.get("pywebviewFullPath")]


def app_icon(size: int = 256) -> Image.Image:
    """The favicon (a gold frame with a play triangle), drawn for the tray and the window."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 32
    d.rounded_rectangle((2 * s, 6 * s, 30 * s, 26 * s), radius=4 * s, fill="#b39770")
    d.polygon([(13 * s, 11 * s), (13 * s, 21 * s), (21 * s, 16 * s)], fill="#1c1917")
    return img


def _ask_in_front(window: Any, title: str, message: str) -> bool:
    """An OK/Cancel question owned by the app's window and brought to the front. pywebview's
    create_confirmation_dialog shows an unowned box from the calling thread (here the tray's), which
    opens behind the window."""
    if sys.platform != "win32":
        return bool(window.create_confirmation_dialog(title, message))
    import ctypes
    import ctypes.wintypes as wt
    import os

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def visit(hwnd: int, _: int) -> bool:
        pid, text = wt.DWORD(), ctypes.create_unicode_buffer(64)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        user32.GetWindowTextW(hwnd, text, 64)
        if pid.value == os.getpid() and text.value == window.title and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(visit, 0)
    mb_okcancel, mb_iconwarning, mb_setforeground, idok = 0x1, 0x30, 0x10000, 1
    return (
        user32.MessageBoxW(found[0] if found else None, message, title, mb_okcancel | mb_iconwarning | mb_setforeground)
        == idok
    )


def _on_console_stop(callback: Any) -> Any:
    """Calls `callback` on Ctrl+C / Ctrl+Break / console close (Windows), before Python's own handling runs;
    returns the handler, which must be kept alive."""
    if sys.platform != "win32":
        return None
    import ctypes

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
    def handler(event: int) -> int:
        callback()
        return 0  # not handled: pywebview's SIGINT handling ends the window loop

    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)
    return handler


def run_window(app: Any, host: str, port: int, url: str, data_dir: Path) -> int:
    try:
        import pystray
        import webview
        from webview.dom import DOMEventHandler
    except ImportError:
        print("The window needs pywebview and pystray: pip install videoforge[desktop] (or uv sync --extra desktop)")
        return 1

    # Open connections get 5 s to close before the app's shutdown runs (it cancels a running job: up to 10 s).
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning", timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            return 1
        thread.join(0.05)

    if sys.platform == "win32":
        import ctypes

        # Its own taskbar entry with the window's icon, not Python's.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    icon_path = data_dir / "videoforge.ico"
    data_dir.mkdir(parents=True, exist_ok=True)
    app_icon().save(icon_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])

    # Without a screen, Windows centers it across two monitors: open maximized on the primary one (at 0,0),
    # with a restore size that fits it.
    screen = next((s for s in webview.screens if s.x == 0 and s.y == 0), None)
    width, height = (
        (1500, 950) if screen is None else (min(1500, screen.width * 9 // 10), min(950, screen.height * 9 // 10))
    )
    window = webview.create_window(
        "VideoForge",
        url,
        width=width,
        height=height,
        min_size=(900, 600),
        screen=screen,
        maximized=True,
        background_color="#1b1a18",
    )

    quitting = threading.Event()
    state = {"minimized": False, "maximized": True, "told": False}
    tray: Any = None

    def show() -> None:
        window.show()
        if state["minimized"]:
            window.maximize() if state["maximized"] else window.restore()

    def quit_app() -> None:
        if app.state.queue.queue_state()["running"]:
            show()
            if not _ask_in_front(
                window,
                "Quit VideoForge",
                "A job is running. Stop it and quit?\n\nStarted again, it skips the steps it finished.",
            ):
                return
        quitting.set()
        window.destroy()

    def on_closing() -> bool:
        if quitting.is_set() or tray is None:
            return True
        window.hide()
        if not state["told"]:
            state["told"] = True
            tray.notify("VideoForge keeps running here. Quit from this icon.", "VideoForge")
        return False  # cancels the close

    def on_drop(event: dict[str, Any]) -> None:
        window.evaluate_js(f"window.videoforgeDropped?.({json.dumps(dropped_paths(event))})")

    def on_loaded() -> None:
        # Each page load gets a fresh document, so the handler is added again.
        window.dom.document.events.drop += DOMEventHandler(on_drop, prevent_default=True)
        window.evaluate_js("window.videoforgeDesktop = true; window.dispatchEvent(new Event('videoforge:desktop'))")

    window.events.closing += on_closing
    window.events.loaded += on_loaded
    window.events.minimized += lambda: state.update(minimized=True)
    window.events.maximized += lambda: state.update(minimized=False, maximized=True)
    window.events.restored += lambda: state.update(minimized=False, maximized=False)
    console_handler = _on_console_stop(quitting.set)  # noqa: F841  Ctrl+C quits instead of hiding; kept alive

    tray = pystray.Icon(
        "VideoForge",
        app_icon(64),
        "VideoForge",
        pystray.Menu(
            pystray.MenuItem("Open VideoForge", show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_app),
        ),
    )
    try:
        tray.run_detached()
    except Exception as ex:  # no tray (e.g. some Linux desktops): closing the window quits
        print(f"No tray icon ({ex}); closing the window quits")
        tray = None
    app.state.show_window = show  # a second `serve --window` brings this one up

    def shut_down() -> None:  # the page's Shut down (it asked already)
        quitting.set()
        window.destroy()

    app.state.shutdown = shut_down

    try:
        # Not private: the theme and layout live in the page's localStorage.
        webview.start(private_mode=False, storage_path=str(data_dir / "webview"), icon=str(icon_path))
    finally:
        if tray is not None:
            tray.stop()
    # Wait for the whole shutdown: the thread is a daemon, so leaving early would cut off the cancel of a
    # running encode (its tools left running) and the database close.
    print("Stopping VideoForge (a running job is cancelled; started again, it skips the steps it finished)...")
    server.should_exit = True
    thread.join()
    return 0
