"""/research: memo in -> background + next step out. No Google, no network."""
import pytest
from fastapi.testclient import TestClient

import main
from gemini import Research


class OkGen:
    def research(self, note):
        return Research(summary=f"about {note}", next_step="read more")


class BrokenGen:
    def research(self, note):
        raise TimeoutError("google is down")


def client(gen) -> TestClient:
    main.app.dependency_overrides[main.get_generator] = lambda: gen
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)


def test_returns_summary_and_next_step():
    r = client(OkGen()).post("/research", json={"note": "量子コンピュータ"})
    assert r.status_code == 200
    assert r.json() == {"summary": "about 量子コンピュータ", "next_step": "read more", "source": "gemini"}


def test_google_failure_degrades_to_fallback_not_an_error():
    r = client(BrokenGen()).post("/research", json={"note": "x"})
    assert r.status_code == 200
    assert r.json() == {"summary": "", "next_step": "", "source": "fallback"}


def test_rejects_empty_and_oversized_notes():
    c = client(OkGen())
    assert c.post("/research", json={"note": ""}).status_code == 422
    assert c.post("/research", json={"note": "a" * 301}).status_code == 422


def test_requires_the_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "s3cret")
    c = client(OkGen())
    assert c.post("/research", json={"note": "x"}).status_code == 401
    ok = c.post("/research", json={"note": "x"}, headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_the_memo_text_is_never_logged(capsys):
    client(BrokenGen()).post("/research", json={"note": "my-private-memo"})
    err = capsys.readouterr().err
    assert "research failed" in err and "my-private-memo" not in err
