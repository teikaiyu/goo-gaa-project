"""/watch: the avatar's report of what it saw. No Google, no network."""
import pytest
from fastapi.testclient import TestClient

import main
from gemini import SeenItem, WatchReport


class OkGen:
    def watch(self):
        return WatchReport(report="見てきたよ", items=[SeenItem(title=f"t{i}", gist="g") for i in range(5)])


class BrokenGen:
    def watch(self):
        raise TimeoutError("google is down")


def client(gen) -> TestClient:
    main.app.dependency_overrides[main.get_generator] = lambda: gen
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)


def test_returns_report_and_at_most_three_items():
    r = client(OkGen()).post("/watch", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["report"] == "見てきたよ" and body["source"] == "gemini"
    assert len(body["items"]) == 3


def test_nothing_about_the_user_is_needed_or_read():
    # No body at all works too: the request carries no personal data.
    assert client(OkGen()).post("/watch").status_code == 200


def test_google_failure_degrades_to_fallback_never_invents_content():
    r = client(BrokenGen()).post("/watch", json={})
    assert r.status_code == 200
    assert r.json() == {"report": "", "items": [], "source": "fallback"}


def test_requires_the_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "s3cret")
    c = client(OkGen())
    assert c.post("/watch", json={}).status_code == 401
    assert c.post("/watch", json={}, headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_the_research_endpoint_is_gone():
    assert client(OkGen()).post("/research", json={"note": "x"}).status_code == 404
