"""Background worker: the avatar researches each new memo while the user does something else.

Same shape as AvatarFeed (daemon thread + Event.wait for a graceful stop). It wakes up when a memo
is added (wake()) or every `retry_sec`, and researches whatever is still `pending` in the store.
A failed call leaves the memo pending, so it is retried on the next cycle: no memo is ever lost.

Privacy: the memo text is sent to the Cloud Run API - but only text the user chose to write, and only
for research. No window titles, URLs or app names are ever involved.
"""
import json
import sys
import threading
import urllib.request
from typing import Callable

from goo_gaa.avatar_client import AvatarConfig
from goo_gaa.notes import NoteStore

_TIMEOUT_SEC = 40  # Gemini with search can be slower than a plain reply; the server caps at 20s + retry


def fetch_research(config: AvatarConfig, note: str) -> dict:
    req = urllib.request.Request(
        f"{config.url}/research", data=json.dumps({"note": note}).encode(), method="POST",
        headers={"content-type": "application/json", "Authorization": f"Bearer {config.token}"},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
        return json.load(resp)


class NoteResearcher:
    def __init__(self, store: NoteStore, fetch: Callable[[str], dict], retry_sec: float = 60.0) -> None:
        self._store = store
        self._fetch = fetch
        self._retry_sec = retry_sec
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._warned = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="note-research", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 0.2) -> None:
        self._stop.set()
        self._wake.set()  # unblock the wait so the thread can see the stop flag
        if self._thread:
            self._thread.join(timeout=timeout)

    def wake(self) -> None:
        """A new memo arrived: research it now instead of waiting for the next cycle."""
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.research_pending()
            self._wake.wait(self._retry_sec)  # returns early on wake() or stop()
            self._wake.clear()

    def research_pending(self) -> None:
        for note in self._store.pending():
            if self._stop.is_set():
                return
            try:
                reply = self._fetch(note["text"])
                if reply.get("source") == "gemini" and reply.get("summary"):
                    self._store.set_research(note["id"], reply["summary"], reply.get("next_step", ""))
                    self._warned = False
                # source == "fallback": Google had trouble; stay pending, retry next cycle
            except Exception as e:  # network down, wrong token, quota...: keep the memo, retry later
                self._warn(e)
                return  # the same trouble would hit every memo: wait for the next cycle

    def _warn(self, e: Exception) -> None:
        if self._warned:
            return
        self._warned = True
        code = getattr(e, "code", None)
        print(f"[warn] note research unavailable: {type(e).__name__}" + (f" (HTTP {code})" if code else ""),
              file=sys.stderr)
