"""Background monitor: poll the foreground window and keep a UsageTracker current.

Why a class + thread (instead of the loop living in main.py)?
  - A GUI must own the main thread on macOS, so the polling loop has to move off it.
  - Any front-end (CLI, desktop widget, future avatar) just reads `state()`.
    The UI never touches OS code or the tracker directly.
  - Dependencies are injected (sample / classify / clock) so tests need no macOS.
"""
import sys
import threading
import time
from typing import Callable, Protocol

from goo_gaa.classifier import is_social
from goo_gaa.usage_tracker import UsageTracker


class _Sample(Protocol):
    app_name: str | None
    url: str | None


class Monitor:
    def __init__(
        self,
        sample: Callable[[], _Sample],
        classify: Callable[[str | None, str | None], bool] = is_social,
        clock: Callable[[], float] = time.monotonic,
        poll_sec: float = 1.0,
        warm_up: Callable[[], None] | None = None,
    ) -> None:
        self._sample = sample
        self._classify = classify
        self._clock = clock
        self._poll_sec = poll_sec
        self._warm_up = warm_up
        self._tracker = UsageTracker(max_gap=poll_sec * 5)
        self._lock = threading.Lock()  # tracker is written here, read from the UI thread
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        # daemon=True: if the app dies unexpectedly the thread cannot keep it alive.
        self._thread = threading.Thread(target=self._run, name="monitor", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 0.2) -> None:
        """Ask the thread to stop, wait only briefly, then let go.

        The thread may be stuck in a slow OS call (osascript up to 1s, or warm_up()
        up to 30s on a permission prompt) which cannot be interrupted. It is a daemon
        and holds nothing that needs flushing, so process exit safely discards it.
        Waiting longer would only make the user stare at a frozen widget after
        clicking the close button.
        """
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def state(self) -> dict[str, float]:
        """The UI contract. Only aggregates - never app names, URLs or titles (privacy)."""
        with self._lock:
            return {
                "social_seconds": self._tracker.social_seconds,
                "total_seconds": self._tracker.total_seconds,
            }

    def _run(self) -> None:
        if self._warm_up:
            self._warm_up()  # may block up to ~30s on the first permission prompt
        reported = False
        while not self._stop.wait(self._poll_sec):  # sleeps, but wakes at once on stop()
            try:
                snap = self._sample()
            except Exception as e:  # one bad sample must not kill the thread (UI would freeze)
                if not reported:
                    reported = True
                    print(f"[warn] sampling failed: {type(e).__name__}", file=sys.stderr)
                continue
            social = self._classify(snap.app_name, snap.url)
            with self._lock:
                self._tracker.update(social, self._clock())
