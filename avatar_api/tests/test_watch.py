"""/watch: topics in -> the avatar's report of what it saw. No Google, no network."""
import pytest
from fastapi.testclient import TestClient

import main
from gemini import SeenItem, WatchReport


class OkGen:
    def __init__(self):
        self.topics = None

    def watch(self, topics):
        self.topics = topics
        return WatchReport(report="見てきたよ", items=[SeenItem(title=f"t{i}", gist="g") for i in range(5)])


class BrokenGen:
    def watch(self, topics):
        raise TimeoutError("google is down")


def client(gen) -> TestClient:
    main.app.dependency_overrides[main.get_generator] = lambda: gen
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)


def test_returns_report_and_at_most_three_items():
    gen = OkGen()
    r = client(gen).post("/watch", json={"topics": ["量子"]})
    assert r.status_code == 200
    body = r.json()
    assert body["report"] == "見てきたよ" and body["source"] == "gemini"
    assert len(body["items"]) == 3
    assert gen.topics == ["量子"]


def test_topics_are_optional():
    assert client(OkGen()).post("/watch", json={}).status_code == 200


def test_topics_are_trimmed_capped_and_blanks_dropped():
    gen = OkGen()
    client(gen).post("/watch", json={"topics": ["  a  ", "", "x" * 500]})
    assert gen.topics == ["a", "x" * 100]


def test_too_many_topics_rejected():
    assert client(OkGen()).post("/watch", json={"topics": ["a"] * 6}).status_code == 422


def test_google_failure_degrades_to_fallback_never_invents_content():
    r = client(BrokenGen()).post("/watch", json={"topics": ["x"]})
    assert r.status_code == 200
    assert r.json() == {"report": "", "items": [], "source": "fallback"}


def test_requires_the_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "s3cret")
    c = client(OkGen())
    assert c.post("/watch", json={}).status_code == 401
    assert c.post("/watch", json={}, headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_topics_are_never_logged(capsys):
    client(BrokenGen()).post("/watch", json={"topics": ["my-private-topic"]})
    err = capsys.readouterr().err
    assert "watch failed" in err and "my-private-topic" not in err
