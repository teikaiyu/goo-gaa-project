"""Pure measurement logic: accumulate seconds spent on social media.

Design choices (each is something you can explain to the judges):
  - time.monotonic() is injected via `now`: it never jumps when the user changes
    the system clock or NTP adjusts it, unlike time.time().
  - We charge the elapsed interval to the *previous* sample's state, because
    that is what the user was doing during the interval.
  - If the gap between two samples is huge (Mac slept, process was suspended),
    we drop it instead of counting 8 hours of sleep as doom-scrolling.
"""


class UsageTracker:
    def __init__(self, max_gap: float = 5.0) -> None:
        self._max_gap = max_gap
        self._last_time: float | None = None
        self._last_social = False
        self.social_seconds = 0.0
        self.total_seconds = 0.0

    def update(self, is_social: bool, now: float) -> None:
        if self._last_time is not None:
            delta = now - self._last_time
            if 0 <= delta <= self._max_gap:  # ignore sleep gaps / negative deltas
                self.total_seconds += delta
                if self._last_social:
                    self.social_seconds += delta
        self._last_time = now
        self._last_social = is_social
