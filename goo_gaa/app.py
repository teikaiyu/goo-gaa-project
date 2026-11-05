"""Desktop widget: a small always-on-top window showing time spent on social media.

Run:  python -m goo_gaa.app

Threads:
  main thread  -> pywebview / Cocoa event loop (macOS requires the GUI here)
  "monitor"    -> Monitor polling loop (see monitor.py)
The page pulls state through Api.get_state(); Python never builds JS strings.
"""
from pathlib import Path

import webview  # pywebview: renders HTML in macOS's native WKWebView

from goo_gaa.monitor import Monitor
from goo_gaa.watcher_macos import get_snapshot, warm_up

WEB_DIR = Path(__file__).parent / "web"


class Api:
    """Everything the page may call. Public methods here == the JS-visible surface."""

    def __init__(self, monitor: Monitor) -> None:
        self._monitor = monitor  # leading underscore: not exposed to JS
        self._window: webview.Window | None = None

    def get_state(self) -> dict[str, float]:
        return self._monitor.state()

    def quit(self) -> None:
        if self._window:
            self._window.destroy()


def main() -> None:
    monitor = Monitor(sample=get_snapshot, warm_up=warm_up)
    monitor.start()

    api = Api(monitor)
    api._window = webview.create_window(
        "goo-gaa",
        str(WEB_DIR / "index.html"),
        js_api=api,
        width=240,
        height=250,
        frameless=True,     # no title bar: it should feel like a resident companion
        on_top=True,        # stay visible above other apps
        transparent=True,   # let the rounded card float with no window rectangle
        easy_drag=True,     # drag anywhere on the card to move it
        resizable=False,
    )
    try:
        webview.start()     # blocks until the window closes
    finally:
        monitor.stop()      # always stop the thread, even on error (Graceful Shutdown)


if __name__ == "__main__":
    main()
