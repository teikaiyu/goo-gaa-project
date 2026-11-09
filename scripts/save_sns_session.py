"""Log Lumo's browser into the SNS accounts once, by hand, and save that login for Cloud Run.

    .venv/bin/python scripts/save_sns_session.py            # writes ~/.lumo/sns-session.json

A real browser window opens. Log in to Instagram, X and/or YouTube yourself (2FA works as usual), then
come back here and press Enter. The file holds login cookies: it is a SECRET. It is written outside
the repo, readable only by you, and goes to Secret Manager (command printed at the end), never to git.
Use a test account: automated viewing may break the SNS terms, and the account can be suspended.
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / ".lumo" / "sns-session.json")
out.parent.mkdir(parents=True, exist_ok=True)

with sync_playwright() as pw:
    # The real Google Chrome, without the "controlled by automated software" marks: X and Google refuse
    # to log in on Playwright's own test browser.
    browser = pw.chromium.launch(
        channel="chrome", headless=False,
        args=["--disable-blink-features=AutomationControlled"], ignore_default_args=["--enable-automation"])
    ctx = browser.new_context(locale="ja-JP")
    # One tab per app Lumo can look at (lumo_app/lib/lumo.dart). Skip any you do not use.
    for url in ("https://www.instagram.com/accounts/login/", "https://x.com/login",
                "https://accounts.google.com/ServiceLogin?continue=https://www.youtube.com/"):
        ctx.new_page().goto(url)
    input("Log in on the tabs you use, then press Enter here... ")
    ctx.storage_state(path=str(out))
    browser.close()

os.chmod(out, 0o600)
print(f"saved: {out}")
print("Upload it (first time: create; later: add a new version):")
print(f"  gcloud secrets create sns-session --data-file={out} --project $GCP_PROJECT")
print(f"  gcloud secrets versions add sns-session --data-file={out} --project $GCP_PROJECT")
