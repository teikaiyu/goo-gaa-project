"""/patrol and the browser's guard rails. No Google, no browser, no network."""
import pytest
from fastapi.testclient import TestClient

import main
import patrol
from gemini import SeenItem, WatchReport


class OkGen:
    def __init__(self):
        self.services = None

    def patrol(self, services):
        self.services = services
        return WatchReport(report="見てきたよ", items=[SeenItem(title="a" * 50, gist="g") for _ in range(8)])


class BrokenGen:
    def patrol(self, services):
        raise FileNotFoundError("/secrets/sns-session.json")


def client(gen) -> TestClient:
    main.app.dependency_overrides[main.get_generator] = lambda: gen
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)


def test_report_capped_to_five_items_and_trimmed():
    gen = OkGen()
    body = client(gen).post("/patrol", json={"services": ["instagram", "x", "instagram"]}).json()
    assert body["source"] == "gemini" and len(body["items"]) == 5
    assert len(body["items"][0]["title"]) == 30
    assert gen.services == ["instagram", "x"]  # duplicates dropped


@pytest.mark.parametrize("services", [[], ["tiktok"], ["x", "x", "x", "x"]])
def test_bad_services_rejected(services):
    assert client(OkGen()).post("/patrol", json={"services": services}).status_code == 422


def test_failure_degrades_to_fallback_never_invents_content():
    body = client(BrokenGen()).post("/patrol", json={"services": ["x"]}).json()
    assert body == {"report": "", "items": [], "source": "fallback"}


def test_token_required_when_configured(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "s3cret")
    assert client(OkGen()).post("/patrol", json={"services": ["x"]}).status_code == 401


@pytest.mark.parametrize("url,ok", [
    ("https://www.instagram.com/stories/a/", True),
    ("https://x.com/home", True),
    ("https://m.youtube.com/", True),
    ("https://evil.com/?x.com", False),
    ("https://instagram.com.evil.com/", False),
    ("https://l.instagram.com.attacker.io/", False),
])
def test_browser_stays_on_sns_sites(url, ok):
    assert patrol.allowed(url) is ok


class FakePage:
    def __init__(self):
        self.url = "https://x.com/home"
        self.went = []
        self.mouse = None

    def goto(self, url, **_):
        self.went.append(url)

    def wait_for_timeout(self, _):
        pass


def test_navigate_off_site_is_ignored():
    page = FakePage()
    patrol.Browser(page).do("navigate", {"url": "https://evil.com/"})
    assert page.went == []
