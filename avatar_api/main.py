"""Cloud Run service: POST /avatar  (user state in -> avatar mood, words, picture out).

Run locally:  uvicorn main:app --reload --port 8080
"""
import base64
import hmac
import os
import sys
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException

from gemini import AvatarGenerator
from images import images_dir, load_image
from mood import FALLBACK_LINES, Mood, decide_mood
from schemas import (AvatarRequest, AvatarResponse, ResearchRequest, ResearchResponse,
                     RecapRequest, RecapResponse, WatchItem, WatchRequest, WatchResponse)

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


@app.post("/research", response_model=ResearchResponse, dependencies=[Depends(check_token)])
def research(req: ResearchRequest, gen: AvatarGenerator = Depends(get_generator)) -> ResearchResponse:
    """Pre-research one memo. Google trouble never fails the request: source="fallback" with empty
    text tells the desktop app "not researched yet", and it asks again later."""
    try:
        r = gen.research(req.note)
        return ResearchResponse(summary=r.summary, next_step=r.next_step, source="gemini")
    except Exception as e:
        _warn("research", e)  # error type + HTTP code only: the memo text is never logged
        return ResearchResponse(summary="", next_step="", source="fallback")


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
def watch(req: WatchRequest, gen: AvatarGenerator = Depends(get_generator)) -> WatchResponse:
    """The avatar 'looks at SNS' and reports what it saw. Google trouble -> source="fallback", empty text
    (the desktop app then says it could not look). Topics are never logged."""
    try:
        r = gen.watch(req.topics)
        items = [WatchItem(title=i.title, gist=i.gist) for i in r.items[:3]]
        return WatchResponse(report=r.report, items=items, source="gemini")
    except Exception as e:
        _warn("watch", e)
        return WatchResponse(report="", items=[], source="fallback")


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
