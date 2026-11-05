"""Polling loop: sample the foreground window every POLL_SEC and feed the tracker."""
import signal
import threading
import time

from goo_gaa.classifier import is_social
from goo_gaa.usage_tracker import UsageTracker
from goo_gaa.watcher_macos import get_snapshot, warm_up

POLL_SEC = 1.0  # 1s: fine enough for "minutes of doom-scrolling", cheap enough to stay Calm


def main() -> None:
    stop = threading.Event()
    # Graceful shutdown: Ctrl+C / kill sets a flag instead of killing us mid-update.
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    warm_up()
    tracker = UsageTracker(max_gap=POLL_SEC * 5)
    # Event.wait() sleeps without busy-looping AND wakes immediately on stop.
    while not stop.wait(POLL_SEC):
        snap = get_snapshot()
        tracker.update(is_social(snap.app_name, snap.url), time.monotonic())
        # Log only the aggregate - never the URL/app name (privacy).
        print(f"\rsocial: {tracker.social_seconds:6.0f}s / total: {tracker.total_seconds:6.0f}s", end="")
    print("\nbye")


if __name__ == "__main__":
    main()
