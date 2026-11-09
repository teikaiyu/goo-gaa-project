"""The user's memos ("things that caught my eye") and what the avatar found out about them.

Stored as one small JSON file on THIS machine (the memo text only leaves it when it is sent for
research, see notes_research.py). No database: a handful of memos does not need one, and a plain file
can be read and deleted by the user.

Thread safety: the UI thread adds memos, the research thread fills in results -> one lock around all
access, and every read hands out copies so callers can never mutate the store by accident.
"""
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

MAX_NOTES = 50        # the widget is small; old memos fall off the end instead of growing forever
MAX_NOTE_CHARS = 300  # same cap as the server's /research


def default_path() -> Path:
    # Per-user app data folder on macOS; override for tests / experiments.
    override = os.environ.get("GOO_GAA_NOTES_FILE")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "goo-gaa" / "notes.json"


class NoteStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_path()
        self._lock = threading.Lock()
        self._notes: list[dict] = self._load()

    # ---------- reading ----------
    def all(self) -> list[dict]:
        """Newest first. Each: {id, text, created_at, research: None | {summary, next_step}}."""
        with self._lock:
            return [dict(n) for n in reversed(self._notes)]

    def pending(self) -> list[dict]:
        """Memos the avatar has not researched yet (oldest first: first come, first served)."""
        with self._lock:
            return [dict(n) for n in self._notes if n["research"] is None]

    # ---------- writing ----------
    def add(self, text: str) -> dict | None:
        """Add a memo. None for blank text (nothing is stored)."""
        text = " ".join(text.split())[:MAX_NOTE_CHARS]  # collapse whitespace/newlines, cap length
        if not text:
            return None
        note = {"id": uuid.uuid4().hex, "text": text, "created_at": time.time(), "research": None}
        with self._lock:
            self._notes.append(note)
            del self._notes[:-MAX_NOTES]  # keep only the newest MAX_NOTES
            self._save()
        return dict(note)

    def set_research(self, note_id: str, summary: str, next_step: str) -> None:
        with self._lock:
            for n in self._notes:
                if n["id"] == note_id:
                    n["research"] = {"summary": summary, "next_step": next_step}
                    self._save()
                    return  # a memo deleted meanwhile is simply ignored

    def delete(self, note_id: str) -> None:
        with self._lock:
            self._notes = [n for n in self._notes if n["id"] != note_id]
            self._save()

    # ---------- persistence ----------
    def _load(self) -> list[dict]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return [
                {"id": str(n["id"]), "text": str(n["text"])[:MAX_NOTE_CHARS],
                 "created_at": float(n.get("created_at", 0)), "research": n.get("research")}
                for n in data[-MAX_NOTES:]
            ]
        except (OSError, ValueError, KeyError, TypeError):
            return []  # no file yet, or a damaged one: start empty rather than crash the widget

    def _save(self) -> None:
        """Atomic write: write a temp file, then rename. A crash mid-write can never leave a
        half-written notes.json (rename is all-or-nothing on the same volume). Caller holds the lock."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._notes, f, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError:
            pass  # disk full / read-only: the memo stays in memory for this session
