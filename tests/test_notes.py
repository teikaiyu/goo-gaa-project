import json

from goo_gaa.notes import MAX_NOTE_CHARS, MAX_NOTES, NoteStore
from goo_gaa.notes_research import NoteResearcher


def store(tmp_path):
    return NoteStore(tmp_path / "notes.json")


# ---------- NoteStore ----------
def test_add_and_list_newest_first(tmp_path):
    s = store(tmp_path)
    s.add("first")
    s.add("second")
    assert [n["text"] for n in s.all()] == ["second", "first"]


def test_blank_memo_is_not_stored(tmp_path):
    s = store(tmp_path)
    assert s.add("") is None and s.add("  \n ") is None
    assert s.all() == []


def test_whitespace_collapsed_and_length_capped(tmp_path):
    s = store(tmp_path)
    assert s.add("a\n\n  b")["text"] == "a b"
    assert len(s.add("x" * 1000)["text"]) == MAX_NOTE_CHARS


def test_survives_restart(tmp_path):
    s = store(tmp_path)
    n = s.add("remember me")
    s.set_research(n["id"], "background", "next")
    again = store(tmp_path)  # a new process reading the same file
    assert again.all()[0]["research"] == {"summary": "background", "next_step": "next"}


def test_only_the_newest_memos_are_kept(tmp_path):
    s = store(tmp_path)
    for i in range(MAX_NOTES + 5):
        s.add(f"n{i}")
    assert len(s.all()) == MAX_NOTES
    assert s.all()[0]["text"] == f"n{MAX_NOTES + 4}"


def test_delete(tmp_path):
    s = store(tmp_path)
    n = s.add("gone")
    s.delete(n["id"])
    assert s.all() == []


def test_damaged_file_starts_empty_instead_of_crashing(tmp_path):
    (tmp_path / "notes.json").write_text("{not json")
    assert store(tmp_path).all() == []
    (tmp_path / "notes.json").write_text(json.dumps([{"nope": 1}]))
    assert store(tmp_path).all() == []


def test_unwritable_location_keeps_memos_in_memory(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    s = NoteStore(blocker / "sub" / "notes.json")  # parent is a FILE: mkdir fails
    assert s.add("still works")["text"] == "still works"
    assert len(s.all()) == 1


def test_list_returns_copies(tmp_path):
    s = store(tmp_path)
    s.add("x")
    s.all()[0]["text"] = "hacked"
    assert s.all()[0]["text"] == "x"


# ---------- NoteResearcher ----------
def ok(text):
    return {"summary": f"about {text}", "next_step": "go", "source": "gemini"}


def test_researches_pending_memos(tmp_path):
    s = store(tmp_path)
    s.add("a")
    NoteResearcher(s, ok).research_pending()
    assert s.all()[0]["research"] == {"summary": "about a", "next_step": "go"}
    assert s.pending() == []


def test_fallback_reply_leaves_the_memo_pending(tmp_path):
    s = store(tmp_path)
    s.add("a")
    NoteResearcher(s, lambda t: {"summary": "", "next_step": "", "source": "fallback"}).research_pending()
    assert len(s.pending()) == 1


def test_network_error_keeps_memo_and_warns_once(tmp_path, capsys):
    s = store(tmp_path)
    s.add("a")
    s.add("b")

    def boom(text):
        raise TimeoutError("down")
    r = NoteResearcher(s, boom)
    r.research_pending()
    r.research_pending()
    assert len(s.pending()) == 2
    assert capsys.readouterr().err.count("note research unavailable") == 1


def test_a_memo_deleted_during_research_is_ignored(tmp_path):
    s = store(tmp_path)
    n = s.add("a")

    def fetch(text):
        s.delete(n["id"])  # the user deletes it while Gemini is thinking
        return ok(text)
    NoteResearcher(s, fetch).research_pending()
    assert s.all() == []


def test_stop_ends_the_thread_quickly(tmp_path):
    r = NoteResearcher(store(tmp_path), ok, retry_sec=3600)
    r.start()
    r.stop(timeout=1.0)
    assert not r._thread.is_alive()
