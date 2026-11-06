"""Desktop widget: a small always-on-top window showing time spent on social media.

Run:  python -m goo_gaa.app

Threads:
  main thread  -> pywebview / Cocoa event loop (macOS requires the GUI here)
  "monitor"    -> Monitor polling loop (see monitor.py)
  "avatar-feed"-> asks the Cloud Run API for the avatar's mood/words/picture (see avatar_client.py)
The page pulls state through Api.get_state(); Python never builds JS strings.

Avatar API settings come from the environment / a .env file (never from code):
  AVATAR_API_URL, AVATAR_API_TOKEN, optional AVATAR_REFRESH_SEC (see .env.example).
Without them the widget still works and just shows the timer.
"""
import sys
from pathlib import Path

import webview  # pywebview: renders HTML in macOS's native WKWebView
from dotenv import load_dotenv

from goo_gaa.avatar_client import AvatarConfig, AvatarFeed, fetch_avatar
from goo_gaa.monitor import Monitor
from goo_gaa.watcher_macos import get_snapshot, warm_up

WEB_DIR = Path(__file__).parent / "web"


class Api:
    """Everything the page may call. Public methods here == the JS-visible surface."""

    def __init__(self, monitor: Monitor, feed: AvatarFeed | None = None) -> None:
        self._monitor = monitor  # leading underscore: not exposed to JS
        self._feed = feed
        self._window: webview.Window | None = None

    def get_state(self) -> dict:
        """{social_seconds, total_seconds, avatar}. `avatar` is None until the cloud has answered
        (or always, when it is not configured) and never contains the picture itself."""
        state = dict(self._monitor.state())
        state["avatar"] = self._feed.state() if self._feed else None
        return state

    def get_avatar_image(self, mood: str) -> str | None:
        """The picture for a mood as a data: URL. The page asks once per mood, not every second."""
        return self._feed.image_data_url(mood) if self._feed else None

    def quit(self) -> None:
        if self._window:
            self._window.destroy()


def _make_feed(monitor: Monitor) -> AvatarFeed | None:
    try:
        config = AvatarConfig.from_env()
    except ValueError as e:
        print(f"[warn] avatar disabled: {e}", file=sys.stderr)
        return None
    if config is None:
        print("[info] avatar disabled: set AVATAR_API_URL and AVATAR_API_TOKEN in .env to enable it",
              file=sys.stderr)
        return None
    return AvatarFeed(
        get_usage=monitor.state,
        fetch=lambda social, total, include_image: fetch_avatar(config, social, total, include_image),
        refresh_sec=config.refresh_sec,
    )


def main() -> None:
    load_dotenv()  # reads .env into the environment if present (it is gitignored: it holds the token)
    monitor = Monitor(sample=get_snapshot, warm_up=warm_up)
    monitor.start()
    feed = _make_feed(monitor)
    if feed:
        feed.start()

    api = Api(monitor, feed)
    api._window = webview.create_window(
        "goo-gaa",
        str(WEB_DIR / "index.html"),
        js_api=api,
        width=240,
        height=330,  # room for the avatar picture and its speech line
        frameless=True,     # no title bar: it should feel like a resident companion
        on_top=True,        # stay visible above other apps
        transparent=True,   # let the rounded card float with no window rectangle
        easy_drag=True,     # drag anywhere on the card to move it
        resizable=False,
    )
    try:
        webview.start()     # blocks until the window closes
    finally:
        if feed:
            feed.stop()
        monitor.stop()      # always stop the threads, even on error (Graceful Shutdown)


if __name__ == "__main__":
    main()
