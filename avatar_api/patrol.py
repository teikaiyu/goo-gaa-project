"""The browser Lumo looks through: a headless Chromium logged in as the owner's (test) SNS accounts.

No Google calls here. Gemini Computer Use decides WHAT to do (gemini.py); this file only does it.
Read-only by design: the model cannot type (excluded in gemini.py), and it may not leave the SNS sites.
"""
import os
from urllib.parse import urlparse

VIEWPORT = {"width": 1280, "height": 800}

# Where Lumo starts and what it should look at. Kept small on purpose: one quick look when the focus
# session ends, not a busy loop for the whole session.
SERVICES = {
    "instagram": ("https://www.instagram.com/",
                  "Open the stories of the accounts I follow (the circles at the top) and go through up "
                  "to 8 of them, one by one. Skip ads (marked 広告 or Sponsored) right away."),
    "x": ("https://x.com/home",
          "Read the top 10 posts of the home timeline, scrolling down as needed."),
    "youtube": ("https://www.youtube.com/",
                "Look at the top videos on the home feed, scrolling down once."),
}
ALLOWED_HOSTS = ("instagram.com", "x.com", "twitter.com", "youtube.com", "google.com")


def session_file() -> str:
    # Mounted from Secret Manager on Cloud Run (made by scripts/save_sns_session.py).
    return os.environ.get("SNS_SESSION_FILE", "/secrets/sns-session.json")


def allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def _xy(args: dict) -> tuple[float, float]:
    # The model speaks in a 0-999 grid; Playwright wants pixels.
    return args["x"] / 1000 * VIEWPORT["width"], args["y"] / 1000 * VIEWPORT["height"]


class Browser:
    def __init__(self, page):
        self.page = page

    def do(self, name: str, args: dict) -> None:
        """Run one Computer Use action. Unknown or off-site actions are skipped, never guessed."""
        p, mouse = self.page, self.page.mouse
        if name in ("click", "double_click"):
            mouse.click(*_xy(args), click_count=2 if name == "double_click" else 1)
        elif name == "move":
            mouse.move(*_xy(args))
        elif name == "scroll":
            if "x" in args:
                mouse.move(*_xy(args))
            n = args.get("magnitude_in_pixels", 600)
            mouse.wheel(*{"up": (0, -n), "right": (n, 0), "left": (-n, 0)}.get(args.get("direction"), (0, n)))
        elif name == "press_key":
            p.keyboard.press(args["key"])
        elif name == "navigate":
            if allowed(args["url"]):
                p.goto(args["url"])
        elif name == "go_back":
            p.go_back()
        elif name == "go_forward":
            p.go_forward()
        elif name == "wait":
            p.wait_for_timeout(min(float(args.get("seconds", 2)), 5) * 1000)
        # take_screenshot / open_web_browser: nothing to do, a screenshot is sent after every step anyway.
        p.wait_for_timeout(800)  # let the page settle before the next screenshot
        if not allowed(p.url):  # a click led off the SNS sites: come straight back
            p.go_back()

    def screenshot(self) -> bytes:
        return self.page.screenshot(type="png")


def open_browser(pw, service: str):
    """-> (browser, Browser) on the service's start page, logged in with the saved session."""
    # Without the automation marks, as when the session was saved (scripts/save_sns_session.py).
    browser = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"],
                                 ignore_default_args=["--enable-automation"])
    ctx = browser.new_context(storage_state=session_file(), viewport=VIEWPORT, locale="ja-JP")
    page = ctx.new_page()
    page.goto(SERVICES[service][0], wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    return browser, Browser(page)
