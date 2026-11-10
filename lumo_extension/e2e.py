"""End-to-end check of the Lumo extension, which carries the Lumo app inside it, in Playwright's Chromium (headless).

    start -> open youtube.com -> Lumo's Shield -> "やっぱやめとく" closes the tab
                                               -> "開く" lets that tab through
          -> finish -> youtube.com opens normally

First, on the web app (Cloud Run / localhost): without the extension, home asks for it and its guide downloads
lumo_extension.zip. Then only that zip is installed and everything runs on the extension's own Lumo page
(chrome-extension://…/app/index.html): home says the extension is running, the patrol, the Shield, the report.
An app the user did not pick (Instagram) is left alone. The report calls the API on Cloud Run without a key, so
it shows Lumo's fallback words; that is enough to see the flow end.

No real SNS and no Google sign-in: youtube.com / instagram.com answer with a stub page, and the build has no
OAuth client ID, so Lumo starts without YouTube access.

Run from the repo root, after `(cd lumo_app && flutter build web)` and `lumo_extension/build.sh`:
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


def without_extension(pw) -> Path:
    """A Chrome without Lumo: home asks for the extension, and its guide hands out the zip. -> the unzipped folder."""
    ctx = chromium(pw)
    app = ctx.new_page()
    app.goto(APP)
    accessible(app).get_by_role("button", name=re.compile("拡張機能を入れてね")).click()
    with app.expect_download(timeout=15000) as dl:
        app.get_by_role("button", name="lumo_extension.zip をダウンロード").click()
    folder = Path(tempfile.mkdtemp()) / "lumo_extension"
    with zipfile.ZipFile(dl.value.path()) as z:
        z.extractall(folder)
    check("without it, home leads to a guide that downloads the extension",
          dl.value.suggested_filename == "lumo_extension.zip" and (folder / "manifest.json").is_file())
    ctx.close()
    return folder


def main():
    version = json.loads((EXT / "manifest.json").read_text())["version"]
    with server(), sync_playwright() as pw:
        ext = without_extension(pw)  # the rest runs on what users download, not on this repo folder
        ctx = chromium(pw, f"--disable-extensions-except={ext}", f"--load-extension={ext}")
        ctx.route(SNS, lambda r: r.fulfill(content_type="text/html", body="<title>SNS (stub)</title>"))
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
        time.sleep(1)  # let onInstalled finish first

        # From here on no server is needed: the app is the extension's own page (what its toolbar button opens).
        app = ctx.new_page()
        app.goto(sw.url.replace("background.js", "app/index.html"))
        app.evaluate("() => localStorage.setItem('flutter.watched', JSON.stringify(['youtube']))")
        app.reload()
        accessible(app)
        check("the extension's own Lumo page runs", app.evaluate("() => document.documentElement.dataset.lumoExtension")
              == version)
        # A list section reaches the accessibility tree as one group labelled with all of its rows.
        app.get_by_label(re.compile("拡張機能が動いています")).wait_for(timeout=15000)
        check("home says the extension is running", True)

        app.get_by_role("button", name="始める").click()
        app.get_by_role("button", name="完了して Lumo を呼び戻す").wait_for()
        check("始める starts the patrol", True)

        other = ctx.new_page()
        go(other, "https://www.instagram.com/")
        check("an app not picked (Instagram) opens normally", stays(other, r"^https://www\.instagram\.com/"))

        tab = ctx.new_page()
        go(tab, "https://www.youtube.com/")
        tab.wait_for_url(re.compile(r"/app/index\.html\?shield=youtube$"), timeout=15000)
        check("youtube.com -> Lumo's Shield (inside the extension)", True)
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
        app.get_by_role("button", name="次のタスクに進む").wait_for(timeout=60000)
        check("完了 shows Lumo's report", True)
        after = ctx.new_page()
        go(after, "https://www.youtube.com/")
        check("after the patrol, youtube.com opens normally", stays(after, r"^https://www\.youtube\.com/$"))
        ctx.close()


if __name__ == "__main__":
    main()
