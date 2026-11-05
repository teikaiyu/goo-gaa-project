"""macOS-only: read the frontmost app and (for browsers) the active tab URL.

Background:
  - NSWorkspace.frontmostApplication() tells us which app owns keyboard focus.
    It needs NO special permission, so we ask for as little as possible by
    default. But it does not query the OS on each call: it returns a cached value
    that is only refreshed by notifications delivered through the run loop. A plain
    script has no running run loop, so we must pump it (see _pump_run_loop).
  - A browser does not expose its tab URL to other processes, so we ask it via
    AppleScript (osascript). macOS shows a one-time "Automation" permission
    prompt for each browser; if the user denies, we degrade to app-name only.
"""
import subprocess
import sys
from typing import NamedTuple

from AppKit import NSWorkspace  # provided by pyobjc-framework-Cocoa
from Foundation import NSDate, NSRunLoop

# App name -> AppleScript that returns the active tab's URL.
_URL_SCRIPTS = {
    "Google Chrome": 'tell application "Google Chrome" to get URL of active tab of front window',
    "Safari": 'tell application "Safari" to get URL of front document',
}


class Snapshot(NamedTuple):
    app_name: str | None
    url: str | None  # only set for supported browsers; window titles are never read


def _browser_url(app_name: str, timeout: float = 1.0) -> str | None:
    script = _URL_SCRIPTS.get(app_name)
    if script is None:
        return None
    try:
        # timeout: never let a hung browser freeze our polling loop.
        out = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        _warn_once(app_name, "timed out (permission prompt pending?)")
        return None
    if out.returncode != 0:
        # e.g. "-1743 Not authorized to send Apple events" = Automation denied.
        _warn_once(app_name, out.stderr.strip())
        return None
    return out.stdout.strip() or None


_warned: set[str] = set()


def _warn_once(app_name: str, reason: str) -> None:
    """Silent failure looks exactly like 'not social media', so say it once."""
    if app_name not in _warned:
        _warned.add(app_name)
        print(f"\n[warn] cannot read URL from {app_name}: {reason}", file=sys.stderr)


def warm_up() -> None:
    """Trigger the one-time Automation prompt for every running supported browser.

    The first Apple event can be slow (9.8s measured, then ~0.1s) and may wait on
    a permission dialog, so give it a long timeout once instead of the 1s poll one.
    """
    running = {a.localizedName() for a in NSWorkspace.sharedWorkspace().runningApplications()}
    for name in _URL_SCRIPTS.keys() & running:
        print(f"Checking permission for {name} (click OK if macOS asks)...")
        _browser_url(name, timeout=30.0)


def _pump_run_loop() -> None:
    """Let Cocoa deliver pending app-switch notifications, refreshing NSWorkspace.

    Without this, frontmostApplication() stays frozen at its first value for the
    whole life of the process. runUntilDate_ returns after this short window.
    """
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))


def get_snapshot() -> Snapshot:
    _pump_run_loop()
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    name = app.localizedName() if app else None
    return Snapshot(name, _browser_url(name) if name else None)
