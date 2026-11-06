import base64
import json
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from goo_gaa.avatar_client import AvatarConfig, AvatarFeed, fetch_avatar

USAGE = lambda: {"social_seconds": 3000.0, "total_seconds": 4000.0}  # noqa: E731
PNG = b"\x89PNGfake"


def reply(mood="grumpy", with_image=False, **extra):
    r = {"mood": mood, "message": f"msg-{mood}", "action": "do x", "source": "gemini",
         "image_base64": base64.b64encode(PNG).decode() if with_image else None,
         "image_mime": "image/png" if with_image else None}
    r.update(extra)
    return r


def run_feed(fetch, cycles_sec=0.25, refresh=0.02):
    feed = AvatarFeed(USAGE, fetch, refresh_sec=refresh)
    feed.start()
    time.sleep(cycles_sec)
    feed.stop()
    return feed


# ---------- config ----------
def test_config_is_none_when_not_configured():
    with patch.dict("os.environ", {"AVATAR_API_URL": "", "AVATAR_API_TOKEN": ""}):
        assert AvatarConfig.from_env() is None


def test_config_refuses_plain_http_to_a_remote_host():
    with patch.dict("os.environ", {"AVATAR_API_URL": "http://example.com", "AVATAR_API_TOKEN": "t"}):
        try:
            AvatarConfig.from_env()
            assert False, "should have refused"
        except ValueError:
            pass
    with patch.dict("os.environ", {"AVATAR_API_URL": "http://127.0.0.1:8099/", "AVATAR_API_TOKEN": "t"}):
        assert AvatarConfig.from_env().url == "http://127.0.0.1:8099"  # local testing is fine, slash trimmed


def test_token_never_appears_in_repr():
    cfg = AvatarConfig("https://x.example", "SUPER-SECRET")
    assert "SUPER-SECRET" not in repr(cfg) and "SUPER-SECRET" not in str(cfg)


def test_refresh_interval_has_a_floor():
    env = {"AVATAR_API_URL": "https://x.example", "AVATAR_API_TOKEN": "t", "AVATAR_REFRESH_SEC": "0.1"}
    with patch.dict("os.environ", env):
        assert AvatarConfig.from_env().refresh_sec >= 5.0  # a typo must not hammer the API


# ---------- feed logic ----------
def test_picture_is_fetched_once_per_mood_not_every_cycle():
    calls = []

    def fetch(social, total, include_image):
        calls.append(include_image)
        return reply(with_image=include_image)

    feed = run_feed(fetch)
    assert len(calls) > 4                    # it polled several times...
    assert calls.count(True) == 1            # ...but asked for the picture exactly once
    assert feed.image_data_url("grumpy") == "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert feed.state() == {"mood": "grumpy", "message": "msg-grumpy", "action": "do x", "source": "gemini"}


def test_state_never_carries_the_picture():
    feed = run_feed(lambda s, t, i: reply(with_image=i))
    assert "image_base64" not in feed.state()  # the UI polls state() every second; keep it tiny


def test_new_mood_triggers_one_more_picture_fetch():
    moods = iter(["happy"] * 3 + ["angry"] * 100)
    seen = []

    def fetch(social, total, include_image):
        mood = seen[-1] if include_image else next(moods)  # the with-picture call repeats the mood
        if not include_image:
            seen.append(mood)
        return reply(mood, with_image=include_image)

    feed = run_feed(fetch, cycles_sec=0.4)
    assert feed.image_data_url("happy") and feed.image_data_url("angry")


def test_missing_picture_is_remembered_and_not_asked_again():
    calls = []

    def fetch(social, total, include_image):
        calls.append(include_image)
        return reply(with_image=False)  # the server has no picture for this mood

    feed = run_feed(fetch)
    assert calls.count(True) == 1           # asked once, learned there is none
    assert feed.image_data_url("grumpy") is None
    assert feed.state()["message"] == "msg-grumpy"  # text still works without a picture


def test_failure_keeps_the_last_good_reply_and_recovers(capsys):
    n = {"i": 0}

    def fetch(social, total, include_image):
        n["i"] += 1
        if n["i"] in (3, 4, 5):
            raise urllib.error.URLError("network down")
        return reply(with_image=include_image)

    feed = run_feed(fetch, cycles_sec=0.4)
    assert feed.state() is not None          # never blanked by the outage
    err = capsys.readouterr().err
    assert err.count("[warn] avatar API unavailable") == 1  # one line for the whole outage, not per retry
    assert "network down" not in err         # only the error TYPE is logged


def test_state_is_none_until_the_first_success():
    def always_fail(social, total, include_image):
        raise TimeoutError()

    assert run_feed(always_fail, cycles_sec=0.1).state() is None


def test_http_error_code_is_reported(capsys):
    def unauthorized(social, total, include_image):
        raise urllib.error.HTTPError("https://x", 401, "Unauthorized", {}, None)

    run_feed(unauthorized, cycles_sec=0.1)
    assert "(HTTP 401)" in capsys.readouterr().err  # tells "wrong token" apart from "server down"


def test_stop_does_not_wait_for_a_slow_network_call():
    feed = AvatarFeed(USAGE, lambda s, t, i: time.sleep(5) or reply(), refresh_sec=60)
    feed.start()
    time.sleep(0.1)  # the thread is now stuck inside the 5s "network call"
    t = time.monotonic()
    feed.stop()
    assert time.monotonic() - t < 0.6


# ---------- what actually goes over the wire ----------
class _Capture(BaseHTTPRequestHandler):
    seen: dict = {}

    def do_POST(self):
        _Capture.seen = {
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "body": json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
        }
        code = 401 if self.headers.get("Authorization") != "Bearer good" else 200
        payload = json.dumps(reply()).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):  # keep test output quiet
        pass


def _server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Capture)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_request_contains_only_aggregates_and_the_bearer_token():
    srv, url = _server()
    try:
        r = fetch_avatar(AvatarConfig(url, "good"), 3000.0, 4000.0, include_image=False)
    finally:
        srv.shutdown()
    seen = _Capture.seen
    assert seen["path"] == "/avatar" and seen["auth"] == "Bearer good"
    # Privacy contract: nothing but these four numbers/flags may ever be sent.
    assert set(seen["body"]) == {"social_seconds", "total_seconds", "local_hour", "include_image"}
    assert 0 <= seen["body"]["local_hour"] <= 23 and seen["body"]["include_image"] is False
    assert r["mood"] == "grumpy"


def test_seconds_are_clamped_to_what_the_server_accepts():
    srv, url = _server()
    try:
        fetch_avatar(AvatarConfig(url, "good"), 200_000.0, 300_000.0, include_image=False)
    finally:
        srv.shutdown()
    assert _Capture.seen["body"]["social_seconds"] == 86_400  # a >24h session would be HTTP 422 otherwise


def test_wrong_token_raises_http_401():
    srv, url = _server()
    try:
        try:
            fetch_avatar(AvatarConfig(url, "bad"), 1.0, 2.0, include_image=False)
            assert False, "should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 401
    finally:
        srv.shutdown()
