"""Deterministic fallback titles, without an AI call."""

import re


def suggest_title(prompt, fallback):
    lines = [
        re.sub(r"^[#*`\s]+|[*`\s]+$", "", x.strip())
        for x in prompt.splitlines()
        if x.strip()
    ]
    explicit = next(
        (
            m.group(1)
            for x in lines
            if (
                m := re.match(
                    r"^(?:tit|titre|title|título|titulo|عنوان|标题|judul|kichwa)\s*[:：]\s*(.+)$",
                    x,
                    re.I,
                )
            )
        ),
        None,
    )
    raw = (
        (
            explicit
            or next((x for x in lines if not re.fullmatch(r"\[.*\]", x)), fallback)
        )
        .strip('"“”«» ')
        .strip()
    )
    if len(raw) <= 76:
        return raw or fallback
    short = raw[:73]
    return (short[: short.rfind(" ")] if short.rfind(" ") > 40 else short) + "…"
