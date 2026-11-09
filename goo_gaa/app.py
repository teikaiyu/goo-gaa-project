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
import os
import sys
import traceback
from pathlib import Path

import webview  # pywebview: renders HTML in macOS's native WKWebView
from dotenv import load_dotenv

from goo_gaa.avatar_client import AvatarConfig, AvatarFeed, fetch_avatar
from goo_gaa.local_avatar import local_image_data_url
from goo_gaa.monitor import Monitor
from goo_gaa.notes import NoteStore
from goo_gaa.notes_research import NoteResearcher, fetch_research
from goo_gaa.watch import WatchSession, fetch_recap, fetch_watch
from goo_gaa.watcher_macos import get_snapshot, warm_up

WEB_DIR = Path(__file__).parent / "web"


class Api:
    """Everything the page may call. Public methods here == the JS-visible surface."""

    def __init__(self, monitor: Monitor, feed: AvatarFeed | None = None,
                 notes: NoteStore | None = None, researcher: NoteResearcher | None = None,
                 watch: WatchSession | None = None) -> None:
        self._monitor = monitor  # leading underscore: not exposed to JS
        self._watch = watch or WatchSession(None)  # None fetch = offline: reports that it could not look
        self._feed = feed
        self._notes = notes or NoteStore()
        self._researcher = researcher
        self._watching = False
        self._window: webview.Window | None = None

    def get_state(self) -> dict:
        """{social_seconds, total_seconds, avatar, watching}. `avatar` is None until the cloud has
        answered (or always, when it is not configured) and never contains the picture itself."""
        state = dict(self._monitor.state())
        state["avatar"] = self._feed.state() if self._feed else None
        state["watching"] = self._watching
        state["watch"] = self._watch.state()  # {status, report, items}: what the avatar saw
        return state

    # ---------- memos ----------
    def list_notes(self) -> list[dict]:
        """Newest first: {id, text, created_at, research: None | {summary, next_step}}."""
        return self._notes.all()

    def add_note(self, text: str) -> dict | None:
        """Save a memo and let the avatar start researching it. None = blank text, nothing saved."""
        note = self._notes.add(text)
        if note and self._researcher:
            self._researcher.wake()
        return note

    def delete_note(self, note_id: str) -> None:
        self._notes.delete(note_id)

    # ---------- "watch SNS for me" ----------
    def set_watching(self, on: bool) -> bool:
        """The user hands SNS over to the avatar (True) or takes it back (False).

        Handing over starts a WatchSession: the cloud looks at what is being talked about (guided by the
        user's memos), keeps looking while the user is away, and get_state()["watch"] carries what it saw.
        Taking it back makes the avatar tell how it went (the "recap" in get_state()["watch"])."""
        self._watching = bool(on)
        if self._watching:
            topics = [n["text"] for n in self._notes.all()[:5]]  # newest 5 memos
            self._watch.start(topics)
        else:
            self._watch.finish()  # "back": the avatar now tells how it went (shown via get_state()["watch"])
        return self._watching

    def get_avatar_image(self, mood: str) -> str | None:
        """The picture for a mood as a data: URL. The page asks once per mood, not every second.

        Order: the cloud's picture first (it is the designer's current art for that mood); otherwise the
        one that ships with the app (see local_avatar.py), so the avatar shows at startup, offline, or
        when the server has no picture for this mood. None = nothing at all: keep the placeholder.
        """
        from_cloud = self._feed.image_data_url(mood) if self._feed else None
        return from_cloud or local_image_data_url(mood)

    def quit(self) -> None:
        if self._window:
            self._window.destroy()


def _load_config() -> AvatarConfig | None:
    try:
        config = AvatarConfig.from_env()
    except ValueError as e:
        print(f"[warn] avatar disabled: {e}", file=sys.stderr)
        return None
    if config is None:
        print("[info] avatar disabled: set AVATAR_API_URL and AVATAR_API_TOKEN in .env to enable it",
              file=sys.stderr)
    return config


def _env_seconds(name: str, default: float, floor: float) -> float:
    """A number of seconds from the environment; a typo falls back to the default, and the floor stops
    a tiny value from hammering the (billed, rate-limited) cloud."""
    try:
        return max(floor, float(os.environ.get(name, default)))
    except ValueError:
        return default


def _make_feed(monitor: Monitor, config: AvatarConfig | None) -> AvatarFeed | None:
    if config is None:
        return None
    return AvatarFeed(
        get_usage=monitor.state,
        fetch=lambda social, total, include_image: fetch_avatar(config, social, total, include_image),
        refresh_sec=config.refresh_sec,
    )


def _make_researcher(notes: NoteStore, config: AvatarConfig | None) -> NoteResearcher | None:
    if config is None:
        return None  # memos still work offline; they just stay "not researched yet"
    return NoteResearcher(notes, fetch=lambda text: fetch_research(config, text))


def _exit_now(code: int = 0) -> None:
    """Leave the process right away, after our own cleanup has finished.

    Why not just return from main()? pywebview delivers the result of every JS -> Python call
    (get_state(), quit() ...) by running evaluate_js on a NON-daemon thread. If the window is already
    gone - and the x button's own quit() call is exactly that case - the thread waits forever for a
    page that no longer exists, and Python's normal exit waits for it ("closing the window hangs the
    app and Ctrl+C does nothing"; reproduced, the stuck threads were pywebview's `_call` threads).
    Our own threads are daemons and hold nothing that needs flushing, so there is nothing to wait for.
    """
    sys.stdout.flush()  # os._exit skips the normal flush
    sys.stderr.flush()
    os._exit(code)


def main() -> None:
    load_dotenv()  # reads .env into the environment if present (it is gitignored: it holds the token)
    monitor = Monitor(sample=get_snapshot, warm_up=warm_up)
    monitor.start()
    config = _load_config()
    feed = _make_feed(monitor, config)
    if feed:
        feed.start()
    notes = NoteStore()
    researcher = _make_researcher(notes, config)
    if researcher:
        researcher.start()  # also researches memos left over from the last session

    watch = WatchSession(
        (lambda topics: fetch_watch(config, topics)) if config else None,
        recap=(lambda items, minutes: fetch_recap(config, items, minutes)) if config else None,
        refresh_sec=_env_seconds("WATCH_REFRESH_SEC", 180.0, floor=30.0),
    )
    api = Api(monitor, feed, notes, researcher, watch)
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
    code = 0
    try:
        webview.start()     # blocks until the window closes
    except BaseException:   # includes KeyboardInterrupt; report it, then still clean up and exit
        traceback.print_exc()
        code = 1
    finally:
        if researcher:
            researcher.stop()
        if feed:
            feed.stop()
        monitor.stop()      # always stop the threads, even on error (Graceful Shutdown)
    _exit_now(code)


if __name__ == "__main__":
    main()
