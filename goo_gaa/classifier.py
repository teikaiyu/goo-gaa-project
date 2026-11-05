"""Pure function: decide whether the foreground app / URL counts as "social media".

Why separate this from the OS code?
  - No OS dependency -> unit-testable anywhere.
  - Privacy: we only look at the app name and the URL *host*. Window titles
    (which can contain DMs, document names, etc.) are never read or stored.
"""
from urllib.parse import urlparse

# Native apps (matched against NSRunningApplication.localizedName).
SOCIAL_APPS = {"X", "Twitter", "Instagram", "TikTok", "Facebook", "Threads", "YouTube", "Discord"}

# Browser sites (matched against the URL host, incl. subdomains).
SOCIAL_DOMAINS = {
    "x.com", "twitter.com", "instagram.com", "tiktok.com",
    "facebook.com", "threads.net", "reddit.com", "youtube.com", "discord.com",
}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_social(app_name: str | None, url: str | None) -> bool:
    if app_name in SOCIAL_APPS:
        return True
    if url:
        host = _host(url)
        # "m.youtube.com" must match "youtube.com", but "notyoutube.com" must not,
        # hence the leading dot in the endswith check.
        return any(host == d or host.endswith("." + d) for d in SOCIAL_DOMAINS)
    return False
