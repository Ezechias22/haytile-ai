# Music duration selection

Music Studio has no manual duration selector. A deterministic offline estimate
uses the supplied lyric word count, a rough singing pace (105 words/minute,
160 for rap, 75 for explicitly slow songs), and 20 seconds for musical framing.
Targets round up to 15 seconds and range from 30 to 300 seconds. Bracketed section
labels do not count; Han text receives a character-count approximation. Short
prose briefs without supplied lyrics default to a two-minute composition target.
These are transparent heuristics, not measured singing time or language guarantees.

The quote exposes music_target_seconds and the UI displays it as an estimate.
The provider prompt requests a complete arrangement and natural outro, prioritizes
all user lyrics over forcing the estimated duration, and forbids inventing,
omitting or repeating lines to fill time. One quote covers one generation; there
are no extra generations, loops, time stretching or automatic paid retries.

Lyria Clip is fixed at 30 seconds: its selector is locked, and the backend rejects
longer requests. The automatic estimate reaches five minutes only for full-song models. This
is not a guarantee of a 5-minute file. Google's current documentation describes
full songs of a couple of minutes, with duration influenced through prompts, and
does not document iterative extension. The application preserves the actual
provider output instead of padding it or discarding a paid shorter result.

Source checked 2026-11-05:
https://ai.google.dev/gemini-api/docs/music-generation
(redirects to AI Studio music-generation documentation).

Offline tests check that a 300-second target reaches the provider exactly once,
lyrics remain present, and invalid durations and long Clip requests are rejected
before provider calls. No paid Google generation was used to test song length.
A verified provider or extension capability is still needed to guarantee a
continuous five-minute song with consistent vocals and all requested lyrics.
