"""Offline duration guidance; this is an estimate, never an audio-length guarantee."""

import math
import re


def target_seconds(prompt, model):
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
    tempo = 160 if re.search(r"\b(rap|hip-hop|hip hop)\b", prompt, re.I) else 105
    if tempo != 160 and re.search(r"\b(slow|ballad|lent|dousman|lento)\b", prompt, re.I):
        tempo = 75
    return min(300, max(30, math.ceil((words / tempo * 60 + 20) / 15) * 15))
