"""/recap: what was seen + minutes in -> how it went. No Google, no network."""
import pytest
from fastapi.testclient import TestClient

import main
from gemini import Recap

BODY = {"items": [{"title": "量子の新チップ", "gist": "誤り訂正が前進"}], "minutes": 12}


class OkGen:
    def __init__(self):
        self.seen = None

    def recap(self, items, minutes):
        self.seen = (items, minutes)
        return Recap(recap="面白かったよ")


class BrokenGen:
    def recap(self, items, minutes):
        raise TimeoutError("google is down")


def client(gen) -> TestClient:
    main.app.dependency_overrides[main.get_generator] = lambda: gen
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)


def test_returns_a_recap_written_from_the_items():
    gen = OkGen()
    r = client(gen).post("/recap", json=BODY)
    assert r.json() == {"recap": "面白かったよ", "source": "gemini"}
    assert gen.seen == ([("量子の新チップ", "誤り訂正が前進")], 12)


def test_google_failure_degrades_to_fallback():
    r = client(BrokenGen()).post("/recap", json=BODY)
    assert r.status_code == 200 and r.json() == {"recap": "", "source": "fallback"}


def test_input_limits():
    c = client(OkGen())
    assert c.post("/recap", json={**BODY, "minutes": -1}).status_code == 422
    assert c.post("/recap", json={**BODY, "minutes": 2000}).status_code == 422
    too_many = {"items": [{"title": "a", "gist": "b"}] * 11, "minutes": 1}
    assert c.post("/recap", json=too_many).status_code == 422


def test_long_texts_are_trimmed():
    gen = OkGen()
    client(gen).post("/recap", json={"items": [{"title": "t" * 99, "gist": "g" * 99}], "minutes": 1})
    assert gen.seen[0] == [("t" * 30, "g" * 60)]


def test_requires_the_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "s3cret")
    c = client(OkGen())
    assert c.post("/recap", json=BODY).status_code == 401
    assert c.post("/recap", json=BODY, headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_items_are_never_logged(capsys):
    client(BrokenGen()).post("/recap", json={"items": [{"title": "secret-title", "gist": "x"}], "minutes": 1})
    err = capsys.readouterr().err
    assert "recap failed" in err and "secret-title" not in err
