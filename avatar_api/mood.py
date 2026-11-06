"""The product's "personality curve": how long on social media -> how the avatar feels.

Pure functions only (no Google, no network), so this is the part you own,
tune freely, and unit-test in milliseconds.
"""
from enum import Enum


class Mood(str, Enum):
    HAPPY = "happy"
    UNEASY = "uneasy"
    GRUMPY = "grumpy"
    ANGRY = "angry"


# (upper bound in MINUTES, mood). The first bound the user is under wins.
# Tune these numbers to change the avatar's patience.
THRESHOLDS: list[tuple[float, Mood]] = [
    (15, Mood.HAPPY),
    (45, Mood.UNEASY),
    (90, Mood.GRUMPY),
]


def decide_mood(social_seconds: float) -> Mood:
    minutes = max(0.0, social_seconds) / 60
    for limit, mood in THRESHOLDS:
        if minutes < limit:
            return mood
    return Mood.ANGRY  # at or above the last bound


# Shown when Gemini is unreachable, so the avatar never goes silent.
FALLBACK_LINES: dict[Mood, tuple[str, str]] = {
    Mood.HAPPY: ("いい調子！この調子でいこう。", "次にやりたいことを1つ決めてみよう。"),
    Mood.UNEASY: ("ちょっと長くなってきたかも…。", "スマホを置いて、水を一杯飲んでこよう。"),
    Mood.GRUMPY: ("むっ…もうだいぶ見てるよ。", "5分だけ、やりたかったことに手をつけてみよう。"),
    Mood.ANGRY: ("いいかげんにして！時間がもったいないよ！", "いまアプリを閉じて、立ち上がって少し歩こう。"),
}
