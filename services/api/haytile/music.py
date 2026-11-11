"""Offline duration guidance; this is an estimate, never an audio-length guarantee."""

import math
import re

OPTION_LIMITS = {
    "music_style": 1000,
    "music_instruments": 1000,
    "music_mood": 300,
    "music_tempo": 100,
}


def validate_options(params):
    for field, maximum in OPTION_LIMITS.items():
        value = params.get(field, "")
        if not isinstance(value, str) or len(value) > maximum:
            raise ValueError("MUSIC_DIRECTION_INVALID")


def direction_prompt(params):
    validate_options(params)
    labels = {
        "music_style": "Musical style / genre",
        "music_instruments": "Instruments / arrangement",
        "music_mood": "Mood / emotion",
        "music_tempo": "Tempo / groove",
    }
    return (
        "MUSICAL DIRECTION (instructions, not lyrics):\n"
        + "\n".join(
            label
            + ": "
            + (params.get(field, "").strip() or "Choose automatically to suit the song.")
            for field, label in labels.items()
        )
        + "\nFor unspecified choices, infer a coherent arrangement from the supplied lyrics and "
        "creative brief. Respect any directions already present in that brief. "
        "Never sing these instructions or add them to the lyrics.\n\n"
    )


def target_seconds(prompt, model, params=None):
    if model == "lyria-3-clip-preview":
        return 30
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    lyrics = "\n".join(line for line in lines if not re.fullmatch(r"\[.*\]", line))
    words = len(re.findall(r"[^\W_]+(?:['’][^\W_]+)*", lyrics, re.UNICODE))
    # Han text has no spaces. Approximate two sung characters per word-equivalent.
    han = len(re.findall(r"[\u3400-\u9fff]", lyrics))
    if han:
        words = max(words, math.ceil(han / 2))
    # A short prose description is a creative brief, not supplied song lyrics.
    if len(lines) < 4 and words < 80:
        return 120
    direction = prompt + "\n" + "\n".join((params or {}).get(field, "") for field in OPTION_LIMITS)
    tempo = 160 if re.search(r"\b(rap|hip-hop|hip hop)\b", direction, re.I) else 105
    if tempo != 160 and re.search(r"\b(slow|ballad|lent|dousman|lento)\b", direction, re.I):
        tempo = 75
    return min(300, max(30, math.ceil((words / tempo * 60 + 20) / 15) * 15))
