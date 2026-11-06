import time
from collections import namedtuple

from goo_gaa.monitor import Monitor

Snap = namedtuple("Snap", "app_name url")


def test_counts_social_time_with_fake_sample_and_clock():
    ticks = iter(range(0, 1000))
    m = Monitor(
        sample=lambda: Snap("X", None),         # always "on social media"
        clock=lambda: next(ticks) * 0.01,       # fake clock: +poll_sec per sample
        poll_sec=0.01,                          # (must stay under the sleep-gap guard)
    )
    m.start()
    time.sleep(0.2)
    m.stop()
    s = m.state()
    assert s["social_seconds"] > 0
    assert s["social_seconds"] == s["total_seconds"]
    assert set(s) == {"social_seconds", "total_seconds"}  # the UI contract


def test_failing_sample_does_not_kill_the_thread():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return Snap("X", None)

    m = Monitor(sample=flaky, poll_sec=0.01)
    m.start()
    time.sleep(0.2)
    m.stop()
    assert calls["n"] > 2  # kept polling after the exception


def test_stop_does_not_wait_for_a_stuck_os_call():
    # Regression: a thread stuck in warm_up()/osascript made stop() block (2s, then 30s worst case).
    m = Monitor(sample=lambda: Snap(None, None), warm_up=lambda: time.sleep(5), poll_sec=0.01)
    m.start()
    time.sleep(0.1)  # the thread is now inside the 5s warm_up
    t = time.monotonic()
    m.stop()
    assert time.monotonic() - t < 0.6


def test_stop_returns_promptly():
    m = Monitor(sample=lambda: Snap(None, None), poll_sec=30.0)  # long poll interval
    m.start()
    t = time.monotonic()
    m.stop()
    assert time.monotonic() - t < 1.0  # Event.wait wakes immediately
