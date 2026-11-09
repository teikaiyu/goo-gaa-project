"""Cloud Run service: POST /avatar  (user state in -> avatar mood, words, picture out).

Run locally:  uvicorn main:app --reload --port 8080
"""
import base64
import hmac
import os
import sys
import time
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from gemini import AvatarGenerator
from images import images_dir, load_image
from mood import FALLBACK_LINES, Mood, decide_mood
from schemas import (AvatarRequest, AvatarResponse, PatrolRequest, PatrolResponse, RecapRequest, RecapResponse, WatchItem,
                     WatchResponse)

app = FastAPI(title="goo-gaa avatar API")


@lru_cache
def get_generator() -> AvatarGenerator:
    return AvatarGenerator()  # created once per instance, so the picture cache survives requests


def check_token(authorization: str | None = Header(default=None)) -> None:
    """Shared-secret check so strangers cannot run up the Gemini bill."""
    expected = os.environ.get("API_TOKEN")
    if not expected:
        # K_SERVICE is set by Cloud Run. Refuse to run open on the public internet.
        if os.environ.get("K_SERVICE"):
            raise HTTPException(503, "API_TOKEN is not configured")
        return  # local development: no token needed
    # compare_digest: constant-time comparison, so response timing leaks nothing about the token.
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(401, "unauthorized")


def _warn(what: str, e: Exception) -> None:
    # Log only the error TYPE and HTTP status code: messages can echo prompts, which may hold the
    # user's goal text. The code is enough to tell 404 (model gone) from 403 (permission) from 429 (quota).
    code = getattr(e, "code", None)
    print(f"[warn] {what} failed: {type(e).__name__}" + (f" (HTTP {code})" if code else ""), file=sys.stderr)


_missing_reported: set[str] = set()


def _warn_missing_image(mood: Mood) -> None:
    """Say once per mood that its picture is not in images/ yet (instead of failing silently)."""
    if mood.value not in _missing_reported:
        _missing_reported.add(mood.value)
        print(f"[warn] no image for mood '{mood.value}' in {images_dir()}", file=sys.stderr)


# Not "/healthz": on Cloud Run that path is answered by Google's front end with its own 404 page
# (seen on the deployed service; the request never reached this app).
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/recap", response_model=RecapResponse, dependencies=[Depends(check_token)])
def recap(req: RecapRequest, gen: AvatarGenerator = Depends(get_generator)) -> RecapResponse:
    """"How was it?" after a watch. Written only from the items the client sends back. Google trouble ->
    source="fallback" (the desktop app then writes a plain summary itself). Items are never logged."""
    try:
        r = gen.recap([(i.title, i.gist) for i in req.items], req.minutes)
        return RecapResponse(recap=r.recap, source="gemini")
    except Exception as e:
        _warn("recap", e)
        return RecapResponse(recap="", source="fallback")


@app.post("/watch", response_model=WatchResponse, dependencies=[Depends(check_token)])
def watch(gen: AvatarGenerator = Depends(get_generator)) -> WatchResponse:
    """The avatar 'looks at SNS' and reports what it saw. Google trouble -> source="fallback", empty text
    (the desktop app then says it could not look)."""
    try:
        r = gen.watch()
        items = [WatchItem(title=i.title, gist=i.gist) for i in r.items[:3]]
        return WatchResponse(report=r.report, items=items, source="gemini")
    except Exception as e:
        _warn("watch", e)
        return WatchResponse(report="", items=[], source="fallback")


@app.post("/patrol", response_model=PatrolResponse, dependencies=[Depends(check_token)])
def patrol(req: PatrolRequest, gen: AvatarGenerator = Depends(get_generator)) -> PatrolResponse:
    """Lumo's patrol report from the user's YouTube subscriptions (videos fetched by the app with the user's
    own permission). Google trouble -> status="failed" (the app then lists the videos itself). Video text
    and channel names are never logged."""
    t0 = time.monotonic()
    try:
        r = gen.youtube_report([v.model_dump() for v in req.videos], req.channels, req.minutes)
    except Exception as e:
        _warn("patrol", e)
        return PatrolResponse(report="", items=[], status="failed")
    finally:
        print(f"[patrol] {len(req.videos)} videos in {time.monotonic() - t0:.1f}s", file=sys.stderr)
    items = [WatchItem(title=i.title[:30], gist=i.gist[:60]) for i in r.items[:5]]
    return PatrolResponse(report=r.report, items=items, status="ok")


@app.post("/avatar", response_model=AvatarResponse, dependencies=[Depends(check_token)])
def avatar(req: AvatarRequest, gen: AvatarGenerator = Depends(get_generator)) -> AvatarResponse:
    mood = decide_mood(req.social_seconds)  # always works: no Google involved

    try:
        line = gen.message(mood, req)
        message, action, source = line.message, line.action, "gemini"
    except Exception as e:  # any Google/network problem -> degrade, never fail the request
        _warn("message", e)
        (message, action), source = FALLBACK_LINES[mood], "fallback"

    img = image_source = None
    if req.include_image:
        img = load_image(mood)  # the designer's art in images/ always wins
        if img is not None:
            image_source = "file"
        elif os.environ.get("ENABLE_IMAGE_GENERATION") == "1":
            # Opt-in only: costs money, and the character looks different on every mood.
            try:
                img = gen.image(mood)
                image_source = "generated" if img is not None else None
            except Exception as e:
                _warn("image", e)
        else:
            _warn_missing_image(mood)

    return AvatarResponse(
        mood=mood, message=message, action=action,
        image_base64=base64.b64encode(img[0]).decode() if img else None,
        image_mime=img[1] if img else None,
        image_source=image_source,
        source=source,
    )


# Same origin as the API, so the app needs no CORS. Mounted LAST: the API routes above win.
if images_dir().is_dir():
    app.mount("/lumo", StaticFiles(directory=images_dir()), name="lumo")
if os.path.isdir(os.environ.get("WEB_DIR", "")):
    app.mount("/", StaticFiles(directory=os.environ["WEB_DIR"], html=True), name="web")
