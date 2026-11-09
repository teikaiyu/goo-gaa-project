import threading
import time

from goo_gaa.watch import (FAILED_REPORT, OFFLINE_REPORT, RECAPPING_REPORT, STARTING_REPORT, WatchSession,
                           local_recap)


def wait_for(session, pred, what, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        st = session.state()
        if pred(st):
            return st
        time.sleep(0.01)
    raise AssertionError(f"never reached {what}: {session.state()}")


def status(s, name, timeout=2.0):
    return wait_for(s, lambda st: st["status"] == name, name, timeout)


def seen(*titles):
    return {"source": "gemini", "report": f"今は{titles[-1]}を見てるよ" if titles else "x",
            "items": [{"title": t, "gist": "g"} for t in titles]}


def watcher(fetch=None, recap=None, **kw):
    kw.setdefault("refresh_sec", 3600)  # tests wake the loop themselves
    return WatchSession(fetch or (lambda: seen("A")), recap, **kw)


def has_items(n):
    return lambda st: len(st["items"]) >= n


# ---------- while watching ----------
def test_starts_idle():
    assert watcher().state()["status"] == "idle"


def test_shows_what_it_is_watching():
    s = watcher(lambda: seen("A", "B"))
    s.start()
    st = wait_for(s, has_items(2), "items")
    assert st["status"] == "watching"
    assert [i["title"] for i in st["items"]] == ["A", "B"]
    assert "B" in st["report"]


def test_says_it_is_going_before_the_first_look_returns():
    release = threading.Event()
    s = watcher(lambda: release.wait(2) and seen("A"))
    s.start()
    st = s.state()
    assert st["status"] == "watching" and st["report"] == STARTING_REPORT
    release.set()


def test_keeps_looking_and_adds_only_new_things_newest_first():
    replies = iter([seen("A"), seen("A", "B"), seen("C")])
    s = watcher(lambda: next(replies), refresh_sec=0.05)
    s.start()
    st = wait_for(s, has_items(3), "three items")
    assert [i["title"] for i in st["items"]] == ["C", "B", "A"]  # A not duplicated


def test_item_list_is_capped():
    n = iter(range(100))
    s = watcher(lambda: seen(f"t{next(n)}"), refresh_sec=0.01)
    s.start()
    time.sleep(0.4)
    assert len(s.state()["items"]) == 8
    s.stop()


def test_trouble_with_nothing_seen_says_it_could_not_look(capsys):
    def boom():
        raise TimeoutError("down")
    s = watcher(boom)
    s.start()
    st = wait_for(s, lambda st: st["trouble"], "trouble")
    assert st["report"] == FAILED_REPORT and st["status"] == "watching"
    assert "watch failed" in capsys.readouterr().err


def test_server_fallback_is_trouble_never_invented():
    s = watcher(lambda: {"source": "fallback", "report": "", "items": []})
    s.start()
    st = wait_for(s, lambda st: st["trouble"], "trouble")
    assert st["items"] == []


def test_a_failed_later_look_keeps_what_was_already_seen():
    calls = iter([seen("A")])

    def fetch():
        try:
            return next(calls)
        except StopIteration:
            raise TimeoutError("down")
    s = watcher(fetch, refresh_sec=0.05)
    s.start()
    st = wait_for(s, lambda st: st["trouble"] and st["items"], "trouble after items")
    assert [i["title"] for i in st["items"]] == ["A"]
    assert st["report"] != FAILED_REPORT  # it did see something: do not claim it saw nothing


# ---------- back: how it went ----------
def test_back_gives_a_recap_from_the_cloud_using_what_was_seen():
    got = {}

    def recap(items, minutes):
        got["items"], got["minutes"] = items, minutes
        return {"source": "gemini", "recap": "面白かったよ"}
    s = watcher(lambda: seen("A", "B"), recap)
    s.start()
    wait_for(s, has_items(2), "items")
    s.finish()
    st = status(s, "recap")
    assert st["recap"] == "面白かったよ"
    assert [i["title"] for i in got["items"]] == ["A", "B"] and got["minutes"] >= 0


def test_recap_shows_summing_up_while_the_cloud_thinks():
    release = threading.Event()
    s = watcher(lambda: seen("A"), lambda i, m: release.wait(2) and {"source": "gemini", "recap": "ok"})
    s.start()
    wait_for(s, has_items(1), "items")
    s.finish()
    st = s.state()
    assert st["status"] == "recapping" and st["report"] == RECAPPING_REPORT
    release.set()
    status(s, "recap")


def test_recap_falls_back_to_a_plain_summary_when_the_cloud_fails(capsys):
    def boom(items, minutes):
        raise TimeoutError("down")
    s = watcher(lambda: seen("A", "B"), boom)
    s.start()
    wait_for(s, has_items(2), "items")
    s.finish()
    st = status(s, "recap")
    assert "2件" in st["recap"] and "「A」" in st["recap"]  # the top item of the list is the one named
    assert "recap failed" in capsys.readouterr().err


def test_recap_fallback_reply_also_uses_the_plain_summary():
    s = watcher(lambda: seen("A"), lambda i, m: {"source": "fallback", "recap": ""})
    s.start()
    wait_for(s, has_items(1), "items")
    s.finish()
    assert "「A」" in status(s, "recap")["recap"]


def test_back_with_nothing_seen_says_so_and_does_not_call_recap():
    called = []
    s = watcher(lambda: {"source": "fallback", "report": "", "items": []}, lambda i, m: called.append(1))
    s.start()
    wait_for(s, lambda st: st["trouble"], "trouble")
    s.finish()
    assert status(s, "recap")["recap"] == local_recap([], 0) and not called


def test_offline_back_says_it_could_not_look():
    s = WatchSession(None)
    s.start()
    assert wait_for(s, lambda st: st["trouble"], "offline")["report"] == OFFLINE_REPORT
    s.finish()
    assert status(s, "recap")["recap"] == OFFLINE_REPORT


def test_recap_disappears_after_a_while():
    now = [0.0]
    s = watcher(lambda: seen("A"), lambda i, m: {"source": "gemini", "recap": "ok"},
                recap_show_sec=60, clock=lambda: now[0])
    s.start()
    wait_for(s, has_items(1), "items")
    s.finish()
    status(s, "recap")
    now[0] = 59
    assert s.state()["status"] == "recap"
    now[0] = 61
    assert s.state()["status"] == "idle"


def test_finish_when_not_watching_does_nothing():
    s = watcher()
    s.finish()
    assert s.state()["status"] == "idle"


# ---------- sessions never leak into each other ----------
def test_stop_discards_everything_without_a_recap():
    called = []
    s = watcher(lambda: seen("A"), lambda i, m: called.append(1))
    s.start()
    wait_for(s, has_items(1), "items")
    s.stop()
    time.sleep(0.2)
    assert s.state()["status"] == "idle" and not called


def test_an_old_reply_cannot_overwrite_a_newer_session():
    first = threading.Event()
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) == 1:
            first.wait(2)
            return seen("OLD")
        return seen("NEW")
    s = watcher(fetch)
    s.start()
    s.start()
    wait_for(s, has_items(1), "items")
    first.set()
    time.sleep(0.2)
    assert [i["title"] for i in s.state()["items"]] == ["NEW"]


def test_state_returns_copies():
    s = watcher()
    s.start()
    wait_for(s, has_items(1), "items")
    s.state()["items"].clear()
    assert len(s.state()["items"]) == 1
