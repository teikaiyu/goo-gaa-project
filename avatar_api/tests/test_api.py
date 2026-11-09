"""No Google, no network: a fake generator stands in for Gemini."""
import base64
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

import main
from gemini import Line
from mood import Mood, decide_mood


class FakeGen:
    def message(self, mood, req):
        return Line(message=f"hi-{mood.value}", action="do x")

    def image(self, mood):
        return b"PNGDATA", "image/png"


class BrokenGen:
    def message(self, mood, req):
        raise TimeoutError("google is down")

    def image(self, mood):
        raise TimeoutError("google is down")


def client(gen) -> TestClient:
    main.app.dependency_overrides[main.get_generator] = lambda: gen
    return TestClient(main.app)


BODY = {"social_seconds": 3000, "total_seconds": 4000}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("ENABLE_IMAGE_GENERATION", raising=False)
    # Every test starts with an EMPTY images dir, never the real repo-root images/.
    monkeypatch.setenv("IMAGES_DIR", str(tmp_path))


def test_mood_boundaries():
    assert decide_mood(0) == Mood.HAPPY
    assert decide_mood(15 * 60 - 1) == Mood.HAPPY
    assert decide_mood(15 * 60) == Mood.UNEASY   # boundary belongs to the next mood
    assert decide_mood(90 * 60) == Mood.ANGRY
    assert decide_mood(-5) == Mood.HAPPY         # negative never breaks it


def test_happy_path_returns_gemini_text():
    r = client(FakeGen()).post("/avatar", json=BODY).json()
    assert r["mood"] == "grumpy" and r["source"] == "gemini"


def test_returns_the_designers_image_for_the_mood(tmp_path):
    (tmp_path / "grumpy.png").write_bytes(b"GRUMPY")
    (tmp_path / "happy.png").write_bytes(b"HAPPY")
    r = client(FakeGen()).post("/avatar", json=BODY).json()  # 3000s -> grumpy
    assert base64.b64decode(r["image_base64"]) == b"GRUMPY"
    assert (r["image_mime"], r["image_source"]) == ("image/png", "file")


def test_lumo_files_are_mapped_to_moods(tmp_path):
    for name in ("happy", "disappointed", "annoyed", "angry", "calm", "smile", "cheering"):
        (tmp_path / f"Lumo_{name}.png").write_bytes(name.encode())
    c = client(FakeGen())
    expected = {60: b"happy", 1800: b"disappointed", 3000: b"annoyed", 7000: b"angry"}
    for secs, want in expected.items():
        r = c.post("/avatar", json={"social_seconds": secs, "total_seconds": 9000}).json()
        assert base64.b64decode(r["image_base64"]) == want, secs


def test_mapped_name_beats_plain_mood_name(tmp_path):
    (tmp_path / "grumpy.png").write_bytes(b"PLAIN")
    (tmp_path / "Lumo_annoyed.png").write_bytes(b"LUMO")
    r = client(FakeGen()).post("/avatar", json=BODY).json()
    assert base64.b64decode(r["image_base64"]) == b"LUMO"


def test_lumo_name_case_does_not_matter(tmp_path):
    (tmp_path / "LUMO_Annoyed.PNG").write_bytes(b"CASE")
    r = client(FakeGen()).post("/avatar", json=BODY).json()
    assert base64.b64decode(r["image_base64"]) == b"CASE"


def test_unmapped_expressions_are_not_served(tmp_path):
    # calm / smile / cheering exist but belong to no mood yet, so they must never be returned.
    for name in ("calm", "smile", "cheering"):
        (tmp_path / f"Lumo_{name}.png").write_bytes(b"X")
    assert client(FakeGen()).post("/avatar", json=BODY).json()["image_base64"] is None


def test_repo_images_cover_every_mood(monkeypatch):
    # Guards the real hand-off: if the designer renames or removes a file, this fails HERE
    # instead of the API silently returning no picture in production.
    from images import load_image
    monkeypatch.delenv("IMAGES_DIR")  # use the real repo-root images/
    for mood in Mood:
        found = load_image(mood)
        assert found is not None, f"images/ has no picture for mood '{mood.value}'"
        assert found[0][:4] == b"\x89PNG"


def test_other_moods_pick_their_own_files(tmp_path):
    (tmp_path / "happy.webp").write_bytes(b"HAPPY")
    r = client(FakeGen()).post("/avatar", json={"social_seconds": 60, "total_seconds": 60}).json()
    assert base64.b64decode(r["image_base64"]) == b"HAPPY" and r["image_mime"] == "image/webp"


def test_filename_case_does_not_matter(tmp_path):
    # macOS would find "Grumpy.PNG" via "grumpy.png"; Linux (Cloud Run) would not.
    (tmp_path / "Grumpy.PNG").write_bytes(b"CASE")
    r = client(FakeGen()).post("/avatar", json=BODY).json()
    assert base64.b64decode(r["image_base64"]) == b"CASE"


def test_missing_image_is_not_an_error():
    res = client(FakeGen()).post("/avatar", json=BODY)
    assert res.status_code == 200
    assert res.json()["image_base64"] is None and res.json()["image_source"] is None


def test_unrelated_files_are_never_served(tmp_path):
    (tmp_path / "grumpy.txt").write_bytes(b"SECRET")   # wrong extension
    (tmp_path / "grumpy_notes.png").write_bytes(b"X")  # not exactly <mood>.<ext>
    assert client(FakeGen()).post("/avatar", json=BODY).json()["image_base64"] is None


def test_generation_is_opt_in(monkeypatch):
    c = client(FakeGen())
    assert c.post("/avatar", json=BODY).json()["image_base64"] is None  # off by default
    monkeypatch.setenv("ENABLE_IMAGE_GENERATION", "1")
    r = c.post("/avatar", json=BODY).json()
    assert base64.b64decode(r["image_base64"]) == b"PNGDATA" and r["image_source"] == "generated"


def test_file_beats_generation(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_IMAGE_GENERATION", "1")
    (tmp_path / "grumpy.png").write_bytes(b"FILE")
    r = client(FakeGen()).post("/avatar", json=BODY).json()
    assert base64.b64decode(r["image_base64"]) == b"FILE" and r["image_source"] == "file"


def test_google_down_still_returns_a_reply():
    res = client(BrokenGen()).post("/avatar", json=BODY)
    assert res.status_code == 200
    r = res.json()
    assert r["source"] == "fallback" and r["message"] and r["image_base64"] is None


def test_unconfigured_google_degrades_instead_of_500(monkeypatch):
    # Regression: the REAL generator with no GOOGLE_CLOUD_PROJECT used to return HTTP 500.
    from gemini import AvatarGenerator
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    res = client(AvatarGenerator()).post("/avatar", json=BODY)
    assert res.status_code == 200 and res.json()["source"] == "fallback"


def test_include_image_false_skips_picture():
    r = client(FakeGen()).post("/avatar", json={**BODY, "include_image": False}).json()
    assert r["image_base64"] is None


def test_rejects_bad_input():
    assert client(FakeGen()).post("/avatar", json={"social_seconds": -1, "total_seconds": 1}).status_code == 422


def test_token_is_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "s3cret")
    c = client(FakeGen())
    assert c.post("/avatar", json=BODY).status_code == 401
    assert c.post("/avatar", json=BODY, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.post("/avatar", json=BODY, headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_refuses_to_run_open_on_cloud_run(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "avatar-api")  # looks like Cloud Run, but no token set
    assert client(FakeGen()).post("/avatar", json=BODY).status_code == 503


def test_extension_zip_is_the_repo_extension_without_tests(monkeypatch):
    monkeypatch.delenv("EXTENSION_DIR", raising=False)  # the real lumo_extension/ of the repo
    monkeypatch.setenv("API_TOKEN", "s3cret")  # public even when the API is locked
    r = client(FakeGen()).get("/lumo_extension.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert {"manifest.json", "background.js", "bridge.js", "rules.js"} <= set(names)  # at the top, not in a folder
    assert not [n for n in names if "test" in n or n.endswith(".py")]


def test_extension_zip_missing_is_404(monkeypatch, tmp_path):
    monkeypatch.setenv("EXTENSION_DIR", str(tmp_path / "nope"))
    assert client(FakeGen()).get("/lumo_extension.zip").status_code == 404
