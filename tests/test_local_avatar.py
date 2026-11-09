import base64

import pytest

from goo_gaa import local_avatar
from goo_gaa.local_avatar import local_image_data_url

PNG_MAGIC = b"\x89PNG"


def decode(data_url: str) -> bytes:
    return base64.b64decode(data_url.split(",", 1)[1])


# ---------- the shipped picture itself ----------
def test_happy_picture_is_read_as_a_png_data_url(tmp_path, monkeypatch):
    monkeypatch.setitem(local_avatar.LOCAL_IMAGES, "happy", "x.png")
    (tmp_path / "x.png").write_bytes(PNG_MAGIC + b"payload")
    url = local_image_data_url("happy", images_dir=tmp_path)
    assert url.startswith("data:image/png;base64,")
    assert decode(url) == PNG_MAGIC + b"payload"  # byte-for-byte what is on disk


def test_the_repo_really_ships_the_startup_picture():
    # Guards the hand-off: if the designer renames/removes the file, the startup picture would silently
    # vanish and the app would be back to an empty circle. Fails HERE instead.
    url = local_image_data_url("happy")
    assert url is not None, "images/Lumo_happy.png is missing or unreadable"
    assert decode(url)[:4] == PNG_MAGIC


# ---------- never breaks the widget ----------
def test_missing_file_returns_none_not_an_error(tmp_path):
    assert local_image_data_url("happy", images_dir=tmp_path) is None


def test_missing_directory_returns_none(tmp_path):
    assert local_image_data_url("happy", images_dir=tmp_path / "nope") is None


def test_unreadable_path_returns_none(tmp_path, monkeypatch):
    monkeypatch.setitem(local_avatar.LOCAL_IMAGES, "happy", "folder.png")
    (tmp_path / "folder.png").mkdir()  # a directory where a file is expected -> read_bytes raises OSError
    assert local_image_data_url("happy", images_dir=tmp_path) is None


def test_moods_without_a_shipped_picture_return_none():
    for mood in ("uneasy", "grumpy", "angry", "nonsense", ""):
        assert local_image_data_url(mood) is None


def test_unsupported_extension_is_refused(tmp_path, monkeypatch):
    monkeypatch.setitem(local_avatar.LOCAL_IMAGES, "happy", "secret.txt")
    (tmp_path / "secret.txt").write_text("not an image")
    assert local_image_data_url("happy", images_dir=tmp_path) is None  # only image types are ever sent


# ---------- how Api combines cloud and local ----------
webview = pytest.importorskip("webview")  # Api lives in the GUI module (imports only on the Mac)
from goo_gaa.app import Api  # noqa: E402


class FakeMonitor:
    def state(self):
        return {"social_seconds": 0.0, "total_seconds": 0.0}


class FakeFeed:
    def __init__(self, images):
        self._images = images

    def state(self):
        return None

    def image_data_url(self, mood):
        return self._images.get(mood)


def test_cloud_picture_wins_over_the_shipped_one():
    api = Api(FakeMonitor(), FakeFeed({"happy": "data:image/png;base64,CLOUD"}))
    assert api.get_avatar_image("happy") == "data:image/png;base64,CLOUD"


def test_falls_back_to_the_shipped_picture_before_the_cloud_has_answered():
    api = Api(FakeMonitor(), FakeFeed({}))  # feed exists but has no picture yet (the first ~9 seconds)
    assert api.get_avatar_image("happy") == local_image_data_url("happy")


def test_shipped_picture_is_used_when_the_avatar_is_not_configured():
    api = Api(FakeMonitor(), feed=None)  # no .env: offline mode
    assert api.get_avatar_image("happy") == local_image_data_url("happy")


def test_nothing_at_all_for_a_mood_with_no_picture_anywhere():
    assert Api(FakeMonitor(), feed=None).get_avatar_image("angry") is None
    assert Api(FakeMonitor(), FakeFeed({})).get_avatar_image("angry") is None


def test_api_serves_the_watching_picture():
    assert Api(FakeMonitor(), feed=None).get_avatar_image("watching").startswith("data:image/png;base64,")


# ---------- the "watching" look: one of two phone pictures, at random ----------
CHOICES = local_avatar.LOCAL_IMAGE_CHOICES["watching"]


def test_watching_picks_one_of_the_two_phone_pictures(tmp_path):
    for n in CHOICES:
        (tmp_path / n).write_bytes(PNG_MAGIC + n.encode())
    seen = {decode(local_image_data_url("watching", images_dir=tmp_path)) for _ in range(60)}
    assert seen == {PNG_MAGIC + n.encode() for n in CHOICES}  # both appear


def test_watching_choice_follows_the_shuffle(tmp_path):
    (tmp_path / CHOICES[0]).write_bytes(PNG_MAGIC + b"1")
    (tmp_path / CHOICES[1]).write_bytes(PNG_MAGIC + b"2")
    assert decode(local_image_data_url("watching", tmp_path, shuffle=lambda names: None)) == PNG_MAGIC + b"1"
    assert decode(local_image_data_url("watching", tmp_path, shuffle=lambda names: names.reverse())) == PNG_MAGIC + b"2"


def test_watching_uses_the_remaining_picture_if_one_file_is_gone(tmp_path):
    (tmp_path / CHOICES[1]).write_bytes(PNG_MAGIC + b"only")
    for _ in range(10):  # whichever is picked first, the existing one is found
        assert decode(local_image_data_url("watching", images_dir=tmp_path)) == PNG_MAGIC + b"only"


def test_watching_is_none_when_both_files_are_gone(tmp_path):
    assert local_image_data_url("watching", images_dir=tmp_path) is None


def test_the_repo_really_ships_both_watching_pictures():
    for n in CHOICES:
        assert (local_avatar.IMAGES_DIR / n).read_bytes()[:4] == PNG_MAGIC, f"images/{n} is missing"
