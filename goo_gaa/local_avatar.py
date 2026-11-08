"""Avatar pictures that ship with the app: shown at startup, before (or without) the cloud.

Why this exists: the Cloud Run reply takes ~9s the first time, and never comes when the app is offline
or has no .env. Without a local picture the avatar slot would show an empty circle for that whole time.
This is the "optimistic first screen": show something certain now, replace it with the real answer later.

Only the startup picture lives here. The full mood -> file table belongs to the server
(MOOD_IMAGES in avatar_api/images.py); copying all of it would let the two drift apart.
"""
import base64
from pathlib import Path

IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"

# mood -> file in images/. Keep it to the startup mood unless offline pictures for other moods are wanted.
LOCAL_IMAGES: dict[str, str] = {"happy": "Lumo_happy.png"}

_MIME = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}


def local_image_data_url(mood: str, images_dir: Path = IMAGES_DIR) -> str | None:
    """The shipped picture for `mood` as a data: URL, or None if there is none.

    Never raises: a missing or unreadable file must not break the widget - the page then simply keeps
    its placeholder, exactly as before this feature existed.
    """
    name = LOCAL_IMAGES.get(mood)
    if name is None:
        return None
    path = images_dir / name
    mime = _MIME.get(path.suffix.lower())
    if mime is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"
