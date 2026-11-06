"""The JSON contract between the desktop app and this server.

Privacy by design: the request has NO field for URLs, app names or window titles,
so they cannot be sent by accident. Only aggregates (and an optional short goal).
"""
from typing import Literal

from pydantic import BaseModel, Field

from mood import Mood


class AvatarRequest(BaseModel):
    social_seconds: float = Field(ge=0, le=86_400)   # time on social media
    total_seconds: float = Field(ge=0, le=86_400)    # total tracked time
    local_hour: int | None = Field(default=None, ge=0, le=23)  # "it's 23:00" changes the tone
    goal: str | None = Field(default=None, max_length=100)     # what the user wants to do instead
    include_image: bool = True


class AvatarResponse(BaseModel):
    mood: Mood
    message: str
    action: str
    image_base64: str | None = None    # None = no picture (disabled or generation failed)
    image_mime: str | None = None
    image_source: Literal["file", "generated"] | None = None  # None = no picture
    source: Literal["gemini", "fallback"]  # lets the client/demo see which path ran
