"""Client for the Cloud Run avatar API: the user's usage in, the avatar's mood + words + picture out.

Why a separate thread (AvatarFeed) instead of calling the API from the UI poll?
  - The UI asks for state every second; a network call can take seconds. It must never block it.
  - The mood changes rarely, so we ask every `refresh_sec` (default 60s), not every second.
  - The picture is ~350 KB as base64. We ask for it only the first time a mood appears.

Privacy: only aggregates leave this machine (seconds + hour of day). Never app names, URLs or titles.
"""
import base64
import datetime
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

_MAX_SECONDS = 86_400  # the server rejects larger values; a >24h session would otherwise get HTTP 422
_TIMEOUT_SEC = 25      # see fetch_avatar


@dataclass(frozen=True)
class AvatarConfig:
    url: str
    token: str = field(repr=False)  # repr=False: the token can never leak into a log or traceback
    refresh_sec: float = 60.0

    @classmethod
    def from_env(cls) -> "AvatarConfig | None":
        """None = not configured (the widget then runs without an avatar)."""
        url = os.environ.get("AVATAR_API_URL", "").strip().rstrip("/")
        token = os.environ.get("AVATAR_API_TOKEN", "").strip()
        if not url or not token:
            return None
        parsed = urlparse(url)
        # The token travels in a header: refuse plain http except for local testing.
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
            raise ValueError("AVATAR_API_URL must start with https:// (the token would be sent unencrypted)")
        try:
            refresh = max(5.0, float(os.environ.get("AVATAR_REFRESH_SEC", "60")))
        except ValueError:
            refresh = 60.0
        return cls(url, token, refresh)


def fetch_avatar(config: AvatarConfig, social_seconds: float, total_seconds: float,
                 include_image: bool) -> dict:
    body = json.dumps({
        "social_seconds": min(social_seconds, _MAX_SECONDS),
        "total_seconds": min(total_seconds, _MAX_SECONDS),
        "local_hour": datetime.datetime.now().hour,
        "include_image": include_image,
    }).encode()
    req = urllib.request.Request(
        f"{config.url}/avatar", data=body, method="POST",
        headers={"content-type": "application/json", "Authorization": f"Bearer {config.token}"},
    )
    # timeout: a hung server must not hang our thread forever. 10s was too short in practice: the
    # server waits on Gemini (up to its own 20s limit) before falling back, and real calls were
    # measured above 10s. A bit over the server's 20s lets it answer (even with fallback lines).
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
        return json.load(resp)


class AvatarFeed:
    """Keeps the latest avatar reply fresh in the background. Read it with state()."""

    def __init__(
        self,
        get_usage: Callable[[], dict],
        fetch: Callable[[float, float, bool], dict],
        refresh_sec: float = 60.0,
    ) -> None:
        self._get_usage = get_usage
        self._fetch = fetch
        self._refresh_sec = refresh_sec
        self._lock = threading.Lock()  # written by our thread, read by the UI thread
        self._latest: dict | None = None
        # mood -> (bytes, mime), or None when the server has no picture for that mood.
        # Storing None too is what stops us asking again for a picture that does not exist.
        self._images: dict[str, tuple[bytes, str] | None] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._warned = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="avatar-feed", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 0.2) -> None:
        # Short join on purpose (same lesson as Monitor.stop): the thread may be inside a
        # network call that cannot be interrupted, and it is a daemon with nothing to flush.
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def state(self) -> dict | None:
        """{mood, message, action, source} or None before the first successful reply. Small."""
        with self._lock:
            return dict(self._latest) if self._latest else None

    def image_data_url(self, mood: str) -> str | None:
        with self._lock:
            img = self._images.get(mood)
        if img is None:
            return None
        return f"data:{img[1]};base64,{base64.b64encode(img[0]).decode()}"

    def _run(self) -> None:
        while True:
            self._refresh_once()  # first call happens immediately, then every refresh_sec
            if self._stop.wait(self._refresh_sec):
                return

    def _refresh_once(self) -> None:
        try:
            usage = self._get_usage()
            social, total = usage["social_seconds"], usage["total_seconds"]
            reply = self._fetch(social, total, False)  # small reply: no picture
            with self._lock:
                need_picture = reply["mood"] not in self._images
            if need_picture:  # first time we see this mood: ask once more, this time with the picture
                reply = self._fetch(social, total, True)
                image = None
                if reply.get("image_base64"):
                    image = (base64.b64decode(reply["image_base64"]), reply.get("image_mime") or "image/png")
                with self._lock:
                    self._images[reply["mood"]] = image
            with self._lock:
                self._latest = {k: reply.get(k) for k in ("mood", "message", "action", "source")}
            self._warned = False  # recovered: a future outage should be reported again
        except Exception as e:  # keep the last good reply; try again next cycle
            self._warn(e)

    def _warn(self, e: Exception) -> None:
        if self._warned:
            return  # one line per outage, not one per minute
        self._warned = True
        code = getattr(e, "code", None)  # HTTPError: 401 = wrong token, 5xx = server trouble
        print(f"[warn] avatar API unavailable: {type(e).__name__}" + (f" (HTTP {code})" if code else ""),
              file=sys.stderr)
