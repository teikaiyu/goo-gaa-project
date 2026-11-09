"""The JSON contract between the desktop app and this server.

Privacy by design: the request has NO field for URLs, app names or window titles,
so they cannot be sent by accident. Only aggregates (and an optional short goal).
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from mood import Mood


class AvatarRequest(BaseModel):
    social_seconds: float = Field(ge=0, le=86_400)   # time on social media
    total_seconds: float = Field(ge=0, le=86_400)    # total tracked time
    local_hour: int | None = Field(default=None, ge=0, le=23)  # "it's 23:00" changes the tone
    goal: str | None = Field(default=None, max_length=100)     # what the user wants to do instead
    include_image: bool = True


class PatrolRequest(BaseModel):
    # The apps the user does not want to see; Lumo looks at them instead (once, when the focus session ends).
    services: list[Literal["instagram", "x", "youtube"]] = Field(min_length=1, max_length=3)

    @field_validator("services")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


class WatchItem(BaseModel):
    title: str   # what it was about (<= 30 chars)
    gist: str    # what people were saying (<= 60 chars)


class WatchResponse(BaseModel):
    report: str              # the avatar's spoken report, first person ("" when source == "fallback")
    items: list[WatchItem]   # up to 3 things it "saw"
    source: Literal["gemini", "fallback"]


class RecapRequest(BaseModel):
    # What the avatar saw while the user was away (the client sends back the items /watch gave it),
    # and for how long. The recap is written ONLY from these: nothing new is looked up.
    items: list[WatchItem] = Field(max_length=10)
    minutes: float = Field(ge=0, le=1_440)

    @field_validator("items")
    @classmethod
    def _cap_items(cls, v: list[WatchItem]) -> list[WatchItem]:
        return [WatchItem(title=i.title[:30], gist=i.gist[:60]) for i in v]


class RecapResponse(BaseModel):
    recap: str  # how it was, in the avatar's voice ("" when source == "fallback")
    source: Literal["gemini", "fallback"]


class AvatarResponse(BaseModel):
    mood: Mood
    message: str
    action: str
    image_base64: str | None = None    # None = no picture (disabled or generation failed)
    image_mime: str | None = None
    image_source: Literal["file", "generated"] | None = None  # None = no picture
    source: Literal["gemini", "fallback"]  # lets the client/demo see which path ran
