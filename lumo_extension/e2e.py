"""End-to-end check of the Lumo extension with the real app, in Playwright's Chromium (headless).

    start -> open youtube.com -> Lumo's Shield -> "やっぱやめとく" closes the tab
                                               -> "開く" lets that tab through
          -> finish -> youtube.com opens normally

Also checks: without the extension, home asks for it and its guide downloads lumo_extension.zip; with it, the app
sees it (home says so), the extension finds open Lumo tabs (it reloads them when installed), and an app the user
did not pick (Instagram) is left alone.

No real SNS and no Google sign-in: youtube.com / instagram.com answer with a stub page, and Google's sign-in
script is replaced by one that says "the user closed the window" (Lumo then starts without YouTube access).

Run from the repo root, after `cd lumo_app && flutter build web`:
    .venv/bin/pip install playwright && .venv/bin/playwright install chromium   # once
    .venv/bin/python lumo_extension/e2e.py [APP_URL]    # default http://localhost:8080
If nothing answers at http://localhost:8080, this starts avatar_api there (WEB_DIR=lumo_app/build/web) and stops it.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

EXT = Path(__file__).resolve().parent
REPO = EXT.parent
APP = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
SNS = re.compile(r"^https://([\w-]+\.)*(youtube|instagram)\.com/")
GOOGLE_SAYS_NO = ("window.google = {accounts: {oauth2: {initTokenClient: (c) => "
                  "({requestAccessToken: () => c.error_callback({type: 'popup_closed'})})}}};")


def up(url: str) -> bool:
    try:
        return urllib.request.urlopen(f"{url}/health", timeout=2).status == 200
    except OSError:
        return False


@contextmanager
def server():
    """The given app, or a local avatar_api started just for this run."""
    if up(APP) or APP != "http://localhost:8080":
        yield
        return
    web = REPO / "lumo_app/build/web"
    assert (web / "index.html").is_file(), "build the app first: cd lumo_app && flutter build web"
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", "8080", "--log-level", "warning"],
                            cwd=REPO / "avatar_api", env={**os.environ, "WEB_DIR": str(web)})
    try:
        for _ in range(50):
            if up(APP):
                break
            time.sleep(0.2)
        yield
    finally:
        proc.terminate()


def go(page, url):
    try:
        page.goto(url, wait_until="commit", timeout=15000)
    except Exception:
        pass  # the extension sending the tab elsewhere aborts this navigation: expected


def accessible(page):
    """Flutter draws on a canvas; its accessibility tree lets us find buttons by name like a screen reader."""
    page.wait_for_selector("flt-semantics-placeholder", state="attached", timeout=30000)
    page.evaluate("() => document.querySelector('flt-semantics-placeholder').click()")
    return page


def stays(page, pattern, seconds=2.0) -> bool:
    time.sleep(seconds)  # the extension acts within ~100 ms; nothing happening for 2 s means it let the page be
    return bool(re.search(pattern, page.url))


def check(name, ok):
    print(("ok  " if ok else "FAIL") + " " + name)
    if not ok:
        sys.exit(1)  # the with-blocks close the browser and the server


def chromium(pw, *args):
    return pw.chromium.launch_persistent_context(tempfile.mkdtemp(), channel="chromium", headless=True,
                                                 locale="ja-JP", viewport={"width": 390, "height": 844}, args=args)


def without_extension(pw):
    """A Chrome without Lumo: home asks for the extension, and its guide hands out the zip."""
    ctx = chromium(pw)
    app = ctx.new_page()
    app.goto(APP)
    accessible(app).get_by_role("button", name=re.compile("拡張機能を入れてね")).click()
    with app.expect_download(timeout=15000) as dl:
        app.get_by_role("button", name="lumo_extension.zip をダウンロード").click()
    with zipfile.ZipFile(dl.value.path()) as z:
        check("without it, home leads to a guide that downloads the extension",
              dl.value.suggested_filename == "lumo_extension.zip" and "lumo_extension/manifest.json" in z.namelist())
    ctx.close()


def main():
    version = json.loads((EXT / "manifest.json").read_text())["version"]
    with server(), sync_playwright() as pw:
        without_extension(pw)
        ctx = chromium(pw, f"--disable-extensions-except={EXT}", f"--load-extension={EXT}")
        ctx.route(SNS, lambda r: r.fulfill(content_type="text/html", body="<title>SNS (stub)</title>"))
        ctx.route("https://accounts.google.com/gsi/client*",
                  lambda r: r.fulfill(content_type="text/javascript", body=GOOGLE_SAYS_NO))
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
        time.sleep(1)  # let onInstalled finish first: it would reload the app tab opened below mid-test

        app = ctx.new_page()
        app.goto(APP)
        app.evaluate("() => localStorage.setItem('flutter.watched', JSON.stringify(['youtube']))")
        app.reload()
        accessible(app)
        check("the app sees the extension", app.evaluate("() => document.documentElement.dataset.lumoExtension")
              == version)
        # A list section reaches the accessibility tree as one group labelled with all of its rows.
        app.get_by_label(re.compile("拡張機能が動いています")).wait_for(timeout=15000)
        check("home says the extension is running", True)

        # On install the extension reloads the Lumo tabs it finds this way (background.js onInstalled).
        # shortcut: checks the lookup only; chrome.runtime.reload() drops a --load-extension extension in Playwright.
        found = sw.evaluate("chrome.tabs.query({url: chrome.runtime.getManifest().content_scripts[0].matches})"
                            ".then(ts => ts.map(t => t.url))")
        check("on install the extension would find this Lumo tab to reload it", f"{APP}/" in found)

        app.get_by_role("button", name="始める").click()
        app.get_by_role("button", name="完了して Lumo を呼び戻す").wait_for()
        check("始める starts the patrol", True)

        other = ctx.new_page()
        go(other, "https://www.instagram.com/")
        check("an app not picked (Instagram) opens normally", stays(other, r"^https://www\.instagram\.com/"))

        tab = ctx.new_page()
        go(tab, "https://www.youtube.com/")
        tab.wait_for_url(re.compile(r"\?shield=youtube$"), timeout=15000)
        check("youtube.com -> Lumo's Shield", True)
        with tab.expect_event("close", timeout=15000):
            accessible(tab).get_by_role("button", name="やっぱやめとく").click()
        check("やっぱやめとく closes the tab", tab.is_closed())

        tab = ctx.new_page()
        go(tab, "https://www.youtube.com/")
        tab.wait_for_url(re.compile(r"\?shield=youtube$"), timeout=15000)
        accessible(tab).get_by_role("button", name="開く").click()
        tab.wait_for_url(re.compile(r"^https://www\.youtube\.com/$"), timeout=15000)
        check("開く lets the tab through", True)
        go(tab, "https://www.youtube.com/watch?v=lumo")
        check("...and it stays open for this patrol", stays(tab, r"^https://www\.youtube\.com/watch"))

        app.get_by_role("button", name="完了して Lumo を呼び戻す").click()
        app.get_by_role("button", name="次のタスクに進む").wait_for(timeout=30000)
        after = ctx.new_page()
        go(after, "https://www.youtube.com/")
        check("after the patrol, youtube.com opens normally", stays(after, r"^https://www\.youtube\.com/$"))
        ctx.close()


if __name__ == "__main__":
    main()
