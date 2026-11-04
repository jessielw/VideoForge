"""`videoforge serve --tray`: VideoForge as a tray icon that serves the app to the default browser (the `desktop`
extra, pystray). The way Reclaimerr runs: uvicorn on the main thread, the icon detached.

The icon's menu has Open (the browser tab) and Quit (asks first while a job runs). Quit, the page's Shut down
and Ctrl+C stop everything; the server's shutdown runs to the end (it cancels a running job, which stays
cancelled).
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any
import webbrowser

from PIL import Image, ImageDraw
import uvicorn

logger = logging.getLogger(__name__)


def app_icon(size: int = 256) -> Image.Image:
    """The favicon (a gold frame with a play triangle), drawn for the tray."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 32
    d.rounded_rectangle((2 * s, 6 * s, 30 * s, 26 * s), radius=4 * s, fill="#b39770")
    d.polygon([(13 * s, 11 * s), (13 * s, 21 * s), (21 * s, 16 * s)], fill="#1c1917")
    return img


def _confirm_quit() -> bool:
    """Asks before stopping a running job, in front of other windows (Windows). Elsewhere it quits without asking."""
    if sys.platform != "win32":
        return True
    import ctypes

    mb_okcancel, mb_iconwarning, mb_setforeground, mb_topmost, idok = 0x1, 0x30, 0x10000, 0x40000, 1
    return (
        ctypes.windll.user32.MessageBoxW(
            None,
            "A job is running. Stop it and quit?\n\nStarted again, it skips the steps it finished.",
            "Quit VideoForge",
            mb_okcancel | mb_iconwarning | mb_setforeground | mb_topmost,
        )
        == idok
    )


def _steady_tray_menu(tray: Any) -> None:
    """pystray's right-click menu on Windows, with what it lacks (Microsoft's KB135788): a WM_NULL posted
    after the menu, without which the next one may close or drop its click; and a log line with what the
    menu returned (a Quit that did nothing left no line at all). Left as pystray's when its internals aren't
    the expected ones."""
    if sys.platform != "win32":
        return
    import ctypes
    import ctypes.wintypes as wt

    try:
        from pystray._util import win32 as pw

        original = tray._on_notify
        handlers = tray._message_handlers
    except (ImportError, AttributeError):
        return
    kernel32 = ctypes.windll.kernel32

    def on_notify(wparam: int, lparam: int) -> int:
        if lparam != pw.WM_RBUTTONUP or not tray._menu_handle:
            return original(wparam, lparam)
        front = pw.SetForegroundWindow(tray._hwnd)  # or the menu doesn't close when clicked away from
        point = wt.POINT()
        pw.GetCursorPos(ctypes.byref(point))
        hmenu, callbacks = tray._menu_handle
        flags = pw.TPM_RIGHTALIGN | pw.TPM_BOTTOMALIGN | pw.TPM_RETURNCMD
        index = pw.TrackPopupMenuEx(hmenu, flags, point.x, point.y, tray._menu_hwnd, None)
        error = 0 if index else kernel32.GetLastError()
        pw.PostMessage(tray._hwnd, 0, 0, 0)  # WM_NULL
        logger.info("Tray: menu closed (item %s, in front %s, error %s)", index, bool(front), error)
        if index > 0:
            callbacks[index - 1](tray)
        return 0

    handlers[pw.WM_NOTIFY] = on_notify


def run_tray(app: Any, host: str, port: int, url: str, *, open_browser: bool = True) -> int:
    """Serve `app` with a tray icon until Quit, the page's Shut down or Ctrl+C. Returns the exit code."""
    try:
        import pystray
    except ImportError:
        print("The tray needs pystray: pip install videoforge[desktop] (or uv sync --extra desktop)")
        return 1

    # Open connections get 5 s to close before the app's shutdown runs (it cancels a running job: up to 10 s).
    config = uvicorn.Config(
        app, host=host, port=port, log_level="warning", log_config=None, timeout_graceful_shutdown=5
    )
    server = uvicorn.Server(config)  # log_config=None: its loggers go to the app log (applog)
    app.state.shutdown = lambda: setattr(server, "should_exit", True)  # the page's Shut down

    def open_page(*_: Any) -> None:
        webbrowser.open(url)

    def quit_app(*_: Any) -> None:
        logger.info("Tray: Quit (thread %s)", threading.current_thread().name)
        if app.state.queue.queue_state()["running"] and not _confirm_quit():
            logger.info("Tray: Quit cancelled (a job is running)")
            return
        server.should_exit = True

    tray: Any = pystray.Icon(
        "VideoForge",
        app_icon(64),
        "VideoForge",
        pystray.Menu(
            pystray.MenuItem("Open VideoForge", open_page, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_app),
        ),
    )
    _steady_tray_menu(tray)
    try:
        tray.run_detached()
    except Exception as ex:  # no tray (e.g. some Linux desktops): the page's Shut down or Ctrl+C stops it
        logger.warning("No tray icon (%s); use the page's Shut down or Ctrl+C", ex)
        print(f"No tray icon ({ex}); use the page's Shut down or Ctrl+C to stop VideoForge")
        tray = None

    if open_browser:
        threading.Timer(1.5, open_page).start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass  # uvicorn re-raises SIGINT after its graceful shutdown
    finally:
        if tray is not None:
            tray.stop()
    return 0
