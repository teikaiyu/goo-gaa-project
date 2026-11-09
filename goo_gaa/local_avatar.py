"""Avatar pictures that ship with the app: shown at startup, before (or without) the cloud.

Why this exists: the Cloud Run reply takes ~9s the first time, and never comes when the app is offline
or has no .env. Without a local picture the avatar slot would show an empty circle for that whole time.
This is the "optimistic first screen": show something certain now, replace it with the real answer later.

Only the startup picture lives here. The full mood -> file table belongs to the server
(MOOD_IMAGES in avatar_api/images.py); copying all of it would let the two drift apart.
"""
import base64
import random
from pathlib import Path
from typing import Callable

IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"

# mood -> file in images/. Keep it to the startup mood unless offline pictures for other moods are wanted.
LOCAL_IMAGES: dict[str, str] = {"happy": "Lumo_happy.png"}

# A "mood" with SEVERAL pictures: one is picked at random each time the page asks. "watching" is not a
# server mood: it is what the avatar looks like while it browses SNS for the user (the page asks for it
# once per watch session, so the picture stays the same for the whole session and changes next time).
WATCHING_MOOD = "watching"
LOCAL_IMAGE_CHOICES: dict[str, list[str]] = {
    WATCHING_MOOD: ["Lumo_phone_thick_tail.png", "Lumo_happy_phone.png"],
}

_MIME = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}


def _read_data_url(path: Path) -> str | None:
    mime = _MIME.get(path.suffix.lower())
    if mime is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def local_image_data_url(mood: str, images_dir: Path = IMAGES_DIR,
                         shuffle: Callable[[list], None] = random.shuffle) -> str | None:
    """The shipped picture for `mood` as a data: URL, or None if there is none.

    For a mood with several pictures, one is picked at random (`shuffle` is injectable so tests are
    deterministic). If the picked file is missing the next one is tried, so a renamed/removed file
    degrades to the remaining picture instead of an empty circle.

    Never raises: a missing or unreadable file must not break the widget - the page then simply keeps
    its placeholder, exactly as before this feature existed.
    """
    names = list(LOCAL_IMAGE_CHOICES.get(mood, []))
    shuffle(names)
    if mood in LOCAL_IMAGES:
        names = [LOCAL_IMAGES[mood]]
    for name in names:
        url = _read_data_url(images_dir / name)
        if url is not None:
            return url
    return None
