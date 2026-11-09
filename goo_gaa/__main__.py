"""CLI front-end: print the Monitor's state once per second (debug / headless use)."""
import signal
import threading

from goo_gaa.monitor import Monitor
from goo_gaa.watcher_macos import get_snapshot, warm_up


def main() -> None:
    stop = threading.Event()
    # Graceful shutdown: Ctrl+C / kill sets a flag instead of killing us mid-update.
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    monitor = Monitor(sample=get_snapshot, warm_up=warm_up)
    monitor.start()
    while not stop.wait(1.0):
        s = monitor.state()
        print(f"\rsocial: {s['social_seconds']:6.0f}s / total: {s['total_seconds']:6.0f}s", end="")
    monitor.stop()
    print("\nbye")


if __name__ == "__main__":
    main()
