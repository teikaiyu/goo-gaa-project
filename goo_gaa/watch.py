"""One "watch SNS for me" session: the avatar keeps looking while the user is away, then says how it went.

Life of a session (one background thread):
  start(topics)  -> looks right away, then again every `refresh_sec`; each look adds NEW things it saw
                    (state()["items"], newest first) and its spoken line (state()["report"]).
  finish()       -> the user pressed "back": after the look in progress, ask the cloud for a recap
                    ("how was it?") built from what was seen, then show it for `recap_show_sec`.
  stop()         -> throw everything away (no recap).

Why a thread: every cloud call takes many seconds; the page polls state() once a second and must never wait.

Why a session counter (`_gen`): the user may press "back" and "watch" again while an old request is still
in flight. A reply is stored only if its number is still current, so a stale answer can never overwrite a
newer session (same idea as `_wanted` in avatar.js).

If the recap call fails, we write a plain recap ourselves from the same items - the user always gets one.
Privacy: only the user's short memos (topics) and the titles/gists the cloud itself returned go out.
"""
import json
import sys
import threading
import time
import urllib.request
from typing import Callable

from goo_gaa.avatar_client import AvatarConfig

_TIMEOUT_SEC = 45  # search-grounded answers are slow; the server gives up on Google after ~20 s + its own work
MAX_ITEMS = 8      # the widget is small; also what we send back for the recap (server cap is 10)

OFFLINE_REPORT = "ネットにつながらなくて、見に行けなかった…"
FAILED_REPORT = "うまく見られなかったみたい。もう一度やってみるね"
STARTING_REPORT = "SNS見てくるね…"
RECAPPING_REPORT = "どうだったか、まとめるね…"


def _post(config: AvatarConfig, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{config.url}{path}", data=json.dumps(payload).encode(), method="POST",
        headers={"content-type": "application/json", "Authorization": f"Bearer {config.token}"},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
        return json.load(resp)


def fetch_watch(config: AvatarConfig, topics: list[str]) -> dict:
    return _post(config, "/watch", {"topics": topics})


def fetch_recap(config: AvatarConfig, items: list[dict], minutes: float) -> dict:
    return _post(config, "/recap", {"items": items, "minutes": minutes})


def local_recap(items: list[dict], minutes: float) -> str:
    """Plain recap used when the cloud cannot write one (or there is no cloud)."""
    if not items:
        return "今回は、見つけられたものがなかったよ"
    return f"{max(1, round(minutes))}分で{len(items)}件見たよ。いちばん気になったのは「{items[0]['title']}」"


def _idle() -> dict:
    return {"status": "idle", "report": "", "items": [], "recap": "", "trouble": False}


class WatchSession:
    """state(): {status: idle|watching|recapping|recap, report, items[{title,gist}], recap, trouble}"""

    def __init__(self, fetch: Callable[[list[str]], dict] | None,
                 recap: Callable[[list[dict], float], dict] | None = None,
                 refresh_sec: float = 180.0, recap_show_sec: float = 60.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._fetch = fetch  # None = the cloud is not configured (offline)
        self._recap = recap
        self._refresh_sec = refresh_sec
        self._recap_show_sec = recap_show_sec
        self._clock = clock
        self._lock = threading.Lock()
        self._gen = 0
        self._finish_evt = threading.Event()
        self._recap_until = 0.0
        self._state = _idle()

    # ---------- reading ----------
    def state(self) -> dict:
        with self._lock:
            if self._state["status"] == "recap" and self._clock() >= self._recap_until:
                self._state = _idle()  # the recap has been on screen long enough
            return {**self._state, "items": [dict(i) for i in self._state["items"]]}

    # ---------- control ----------
    def start(self, topics: list[str]) -> None:
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._finish_evt.set()  # wake an old thread so it sees it is stale and exits
            self._finish_evt = evt = threading.Event()
            self._state = {**_idle(), "status": "watching", "report": STARTING_REPORT}
        threading.Thread(target=self._run, args=(gen, evt, list(topics), self._clock()),
                         name="watch", daemon=True).start()

    def finish(self) -> None:
        """The user is back: wrap up with a recap. No-op unless a watch is in progress."""
        with self._lock:
            if self._state["status"] != "watching":
                return
            self._state = {**self._state, "status": "recapping", "report": RECAPPING_REPORT}
            self._finish_evt.set()

    def stop(self) -> None:
        """Forget the session without a recap; any reply still in flight is ignored."""
        with self._lock:
            self._gen += 1
            self._finish_evt.set()
            self._state = _idle()

    # ---------- the thread ----------
    def _run(self, gen: int, evt: threading.Event, topics: list[str], t0: float) -> None:
        if self._fetch is None:  # offline: nothing to look at, but "back" still gets an answer
            self._update(gen, report=OFFLINE_REPORT, trouble=True)
        else:
            while True:
                self._look(gen, topics)
                if evt.wait(self._refresh_sec):  # returns True the moment finish()/stop()/start() fires
                    break
        with self._lock:
            if gen != self._gen:
                return  # stopped or replaced: no recap
        if self._fetch is None:
            evt.wait()  # offline: sit still until "back" (the thread is a daemon; stop() also wakes it)
            with self._lock:
                if gen != self._gen:
                    return
        self._wrap_up(gen, (self._clock() - t0) / 60)

    def _look(self, gen: int, topics: list[str]) -> None:
        try:
            reply = self._fetch(topics)
            if reply.get("source") != "gemini" or not reply.get("report"):
                raise ValueError("server fallback")  # Google had trouble: say so, never make something up
            seen = [{"title": str(i["title"]), "gist": str(i["gist"])} for i in reply.get("items", [])]
            with self._lock:
                if gen != self._gen:
                    return
                known = {i["title"] for i in self._state["items"]}
                fresh = [i for i in seen if i["title"] not in known]
                self._state = {**self._state, "items": (fresh + self._state["items"])[:MAX_ITEMS],
                               "report": reply["report"] if self._state["status"] == "watching" else self._state["report"],
                               "trouble": False}
        except Exception as e:
            code = getattr(e, "code", None)
            print(f"[warn] watch failed: {type(e).__name__}" + (f" (HTTP {code})" if code else ""), file=sys.stderr)
            with self._lock:
                if gen == self._gen:
                    no_items = not self._state["items"]
                    self._state = {**self._state, "trouble": True,
                                   "report": FAILED_REPORT if no_items and self._state["status"] == "watching"
                                   else self._state["report"]}

    def _wrap_up(self, gen: int, minutes: float) -> None:
        with self._lock:
            if gen != self._gen:
                return
            items = [dict(i) for i in self._state["items"]]
        text = ""
        if items and self._recap is not None:
            try:
                reply = self._recap(items, minutes)
                if reply.get("source") == "gemini" and reply.get("recap"):
                    text = reply["recap"]
            except Exception as e:
                code = getattr(e, "code", None)
                print(f"[warn] recap failed: {type(e).__name__}" + (f" (HTTP {code})" if code else ""), file=sys.stderr)
        if not text:
            text = OFFLINE_REPORT if (self._fetch is None) else local_recap(items, minutes)
        with self._lock:
            if gen != self._gen:
                return
            self._recap_until = self._clock() + self._recap_show_sec
            self._state = {**self._state, "status": "recap", "recap": text, "report": ""}

    def _update(self, gen: int, **fields) -> None:
        with self._lock:
            if gen == self._gen:
                self._state = {**self._state, **fields}
