"""All Google calls live here, behind one small class.

Auth: on Cloud Run the service account is picked up automatically
(Application Default Credentials) -> there is NO API key anywhere in this repo.
"""
import os

from google import genai
from google.genai import types
from pydantic import BaseModel

from mood import Mood
from schemas import AvatarRequest

# Model IDs change often and Google's docs disagree between pages -> configurable, not hard-coded.
# Verified against the real project on 2026-11-06: gemini-2.5-flash answers 404 everywhere (retired),
# and the Gemini 3.x Flash models work from the "global" location (only 3.5 also from asia-northeast1).
TEXT_MODEL = os.environ.get("TEXT_MODEL", "gemini-3.5-flash")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gemini-3.1-flash-image")  # available in global / us-central1
LOCATION = os.environ.get("VERTEX_LOCATION", "global")

_LOOK = {
    Mood.HAPPY: "smiling happily, eyes sparkling",
    Mood.UNEASY: "slightly worried, sweat drop, uneasy eyebrows",
    Mood.GRUMPY: "pouting and annoyed, arms crossed, half-closed eyes",
    Mood.ANGRY: "very angry, red face, steam from the head",
}


class Line(BaseModel):
    message: str  # what the avatar says
    action: str   # one small, concrete thing to do instead


class AvatarGenerator:
    def __init__(self, client: genai.Client | None = None) -> None:
        self._client_or_none = client
        self._images: dict[Mood, tuple[bytes, str]] = {}  # one picture per mood, reused

    @property
    def _client(self) -> genai.Client:
        # Built on first USE, not at startup: a missing project/credentials then raises inside
        # the caller's try/except and degrades to fallback lines, instead of a 500 on every request.
        if self._client_or_none is None:
            self._client_or_none = genai.Client(
                vertexai=True,
                project=os.environ["GOOGLE_CLOUD_PROJECT"],
                location=LOCATION,
                # timeout (ms): a slow Google call must not hold the desktop app hostage.
                http_options=types.HttpOptions(timeout=20_000),
            )
        return self._client_or_none

    def message(self, mood: Mood, req: AvatarRequest) -> Line:
        minutes = round(req.social_seconds / 60)
        prompt = (
            "You are a small desktop companion avatar. Reply in Japanese, in character, "
            "short and kind (no scolding, no medical advice).\n"
            f"Your mood: {mood.value}. The user has spent {minutes} minutes on social media"
            + (f", and it is {req.local_hour}:00 now" if req.local_hour is not None else "")
            + (f". Their goal: {req.goal}" if req.goal else "")
            + ".\nGive: message (max 40 chars) and action (one small concrete step, max 40 chars)."
        )
        resp = self._client.models.generate_content(
            model=TEXT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Line,     # Gemini must answer in this exact shape
                temperature=0.8,
            ),
        )
        if not isinstance(resp.parsed, Line):
            raise ValueError("Gemini returned an unexpected shape")
        return resp.parsed

    def image(self, mood: Mood) -> tuple[bytes, str] | None:
        if mood in self._images:  # cache hit: no cost, no waiting
            return self._images[mood]
        resp = self._client.models.generate_content(
            model=IMAGE_MODEL,
            contents=(
                "A cute round blob mascot character, flat vector illustration, plain light "
                f"background, centered, square. Expression: {_LOOK[mood]}."
            ),
            # These image models require TEXT alongside IMAGE (image-only is not supported).
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        for part in resp.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                self._images[mood] = (part.inline_data.data, part.inline_data.mime_type or "image/png")
                return self._images[mood]
        return None
