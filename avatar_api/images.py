"""Pick the avatar picture for a mood from the images/ directory (pushed by the designer).

Which file belongs to which mood is decided by MOOD_IMAGES below (e.g. happy -> Lumo_happy.png);
a plain images/<mood>.<ext> (happy.png ...) also works as a fallback.
The mood comes from our own enum, never from user input, so there is no path to tamper with.
"""
import os
from pathlib import Path

from mood import Mood

_MIME = {
    ".png": "image/png",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
}


def images_dir() -> Path:
    # Read per call (not at import) so tests / deployments can change it via the environment.
    if env := os.environ.get("IMAGES_DIR"):
        return Path(env)
    return Path(__file__).resolve().parent.parent / "images"  # repo-root images/ when run locally


# Which of the designer's pictures (file name WITHOUT extension) shows for each mood.
# Edit this table to change the look; the files stay as the designer named them.
# Lumo_calm, Lumo_smile and Lumo_cheering are not mapped yet (future: idle, greeting, achievement).
MOOD_IMAGES: dict[Mood, str] = {
    Mood.HAPPY: "Lumo_happy",
    Mood.UNEASY: "Lumo_disappointed",
    Mood.GRUMPY: "Lumo_annoyed",
    Mood.ANGRY: "Lumo_angry",
}


def load_image(mood: Mood) -> tuple[bytes, str] | None:
    """Return (bytes, mime) for this mood, or None if no picture is available.

    Looks for the mapped name first (Lumo_happy.png), then the plain mood name (happy.png).
    """
    d = images_dir()
    if not d.is_dir():
        return None
    # Scan + compare lowercase instead of building "Lumo_happy.png": macOS ignores filename
    # case, but the Cloud Run container (Linux) does not, so "lumo_Happy.PNG" would work here
    # and silently vanish after deploy.
    files = sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in _MIME)
    for wanted in (MOOD_IMAGES[mood].lower(), mood.value):  # mapped name wins over plain name
        for path in files:
            if path.stem.lower() == wanted:
                return path.read_bytes(), _MIME[path.suffix.lower()]
    return None
