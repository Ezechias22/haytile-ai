import pytest
from fastapi import HTTPException

from haytile import pricing, providers


def test_long_music_duration_reaches_provider_without_extra_calls(monkeypatch):
    calls = []

    def request(method, path, payload):
        calls.append((method, path, payload))
        return {
            "status": "completed",
            "outputs": [{"type": "audio", "data": "YXVkaW8=", "mime_type": "audio/mpeg"}],
        }

    monkeypatch.setattr(providers, "request", request)
    data, mime = providers.generate("music", "lyria-3.5", "My exact lyrics", {"duration": 300})
    assert data == b"audio" and mime == "audio/mpeg"
    assert len(calls) == 1
    assert "300 seconds" in calls[0][2]["input"]
    assert "My exact lyrics" in calls[0][2]["input"]
    assert "natural finished outro" in calls[0][2]["input"]


@pytest.mark.parametrize("duration", [0, 29, 301, True, "300"])
def test_music_duration_rejected_before_provider_or_quote(monkeypatch, duration):
    def unexpected(*args, **kwargs):
        pytest.fail("Provider must not be called")

    monkeypatch.setattr(providers, "request", unexpected)
    with pytest.raises(providers.ProviderError, match="MUSIC_DURATION_INVALID"):
        providers.generate("music", "lyria-3.5", "song", {"duration": duration})
    with pytest.raises(HTTPException) as exc:
        pricing.quote("music", "lyria-3.5", "song", {"duration": duration})
    assert exc.value.detail == "MUSIC_DURATION_INVALID"


def test_clip_cannot_quote_or_generate_long_song(monkeypatch):
    with pytest.raises(providers.ProviderError, match="MUSIC_CLIP_DURATION_INVALID"):
        providers.generate("music", "lyria-3-clip-preview", "song", {"duration": 300})
    with pytest.raises(HTTPException) as exc:
        pricing.quote("music", "lyria-3-clip-preview", "song", {"duration": 300})
    assert exc.value.detail == "MUSIC_CLIP_DURATION_INVALID"


def test_automatic_duration_scales_with_lyrics_and_tempo():
    from haytile.music import target_seconds

    short = "\n".join(["Nou ka rive ansanm"] * 10)
    long = "\n".join(["Nou ka rive ansanm"] * 100)
    assert target_seconds(short, "lyria-3.5") < target_seconds(long, "lyria-3.5")
    assert target_seconds(long, "lyria-3.5") == 255
    assert target_seconds(long + "\nrap", "lyria-3.5") < target_seconds(long, "lyria-3.5")
    assert target_seconds("Write a hopeful Haitian song", "lyria-3.5") == 120
    assert target_seconds(long * 3, "lyria-3.5") == 300
    assert target_seconds(long, "lyria-3-clip-preview") == 30


def test_no_selected_duration_uses_lyrics_estimate(monkeypatch):
    calls = []

    def request(method, path, payload):
        calls.append(payload)
        return {"status": "completed", "outputs": [{"type": "audio", "data": "YQ=="}]}

    monkeypatch.setattr(providers, "request", request)
    lyrics = "\n".join(["Nou ka rive ansanm"] * 100)
    providers.generate("music", "lyria-3.5", lyrics, {})
    assert len(calls) == 1
    assert "255 seconds" in calls[0]["input"]
    assert lyrics in calls[0]["input"]
    assert "Do not omit" in calls[0]["input"]


def test_music_direction_is_separate_optional_and_preserves_lyrics(monkeypatch):
    calls = []

    def request(method, path, payload):
        calls.append(payload)
        return {"status": "completed", "outputs": [{"type": "audio", "data": "YQ=="}]}

    monkeypatch.setattr(providers, "request", request)
    lyrics = "[Kouplè]\nMen nan men, ann fè yon pa.\nNou gen espwa!"
    params = {
        "music_style": "Konpa",
        "music_instruments": "Gita, bas",
        "music_mood": "Espwa",
        "music_tempo": "96 BPM",
    }
    providers.generate("music", "lyria-3.5", lyrics, params)
    prompt = calls[0]["input"]
    assert lyrics in prompt
    assert prompt.index("MUSICAL DIRECTION") < prompt.index("SONG CONTENT")
    for value in params.values():
        assert value in prompt
    assert "only invent" in prompt and "leave room to finish" in prompt
    providers.generate("music", "lyria-3.5", lyrics, {})
    assert calls[1]["input"].count("Choose automatically to suit the song.") == 4
    assert len(calls) == 2  # One request per user action; no paid extension loop.


@pytest.mark.parametrize(
    "params",
    [
        {"music_style": None},
        {"music_instruments": ["piano"]},
        {"music_mood": "x" * 301},
        {"music_tempo": 96},
        {"music_style": "x" * 1001},
    ],
)
def test_invalid_direction_rejected_without_provider_call(monkeypatch, params):
    monkeypatch.setattr(providers, "request", lambda *a, **kw: pytest.fail("No provider call"))
    with pytest.raises(providers.ProviderError, match="MUSIC_DIRECTION_INVALID"):
        providers.generate("music", "lyria-3.5", "song", params)
    with pytest.raises(HTTPException) as exc:
        pricing.quote("music", "lyria-3.5", "song", params)
    assert exc.value.detail == "MUSIC_DIRECTION_INVALID"


def test_direction_changes_estimate_without_counting_as_lyrics():
    from haytile.music import target_seconds

    lyrics = "\n".join(["Nou ka rive ansanm"] * 100)
    params = {"music_style": "rap", "music_instruments": "piano " * 150}
    assert target_seconds(lyrics, "lyria-3.5", params) == 180
    assert pricing.quote("music", "lyria-3.5", lyrics, params)["music_target_seconds"] == 180
    assert target_seconds(lyrics, "lyria-3.5", {"music_tempo": "slow"}) == 300


def test_music_uses_final_audio_block_like_google_output_audio(monkeypatch):
    import base64

    calls = []

    def request(method, path, payload):
        calls.append(payload)
        return {
            "status": "completed",
            "steps": [
                {
                    "type": "model_output",
                    "content": [{"type": "audio", "data": base64.b64encode(b"early").decode()}],
                },
                {
                    "type": "model_output",
                    "content": [
                        {"type": "text", "text": "Song structure"},
                        {
                            "type": "audio",
                            "data": base64.b64encode(b"complete final audio").decode(),
                            "mime_type": "audio/mpeg",
                        },
                    ],
                },
            ],
        }

    monkeypatch.setattr(providers, "request", request)
    data, mime = providers.generate("music", "lyria-3.5", "song", {})
    assert data == b"complete final audio" and mime == "audio/mpeg"
    assert len(calls) == 1


def test_media_validation_preserves_song_longer_than_three_minutes(tmp_path):
    import subprocess

    from haytile.media import inspect_media

    audio = tmp_path / "long-song.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=8000",
            "-t",
            "215",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "16k",
            str(audio),
        ],
        check=True,
        timeout=30,
    )
    data = audio.read_bytes()
    assert inspect_media(data, "audio/mpeg") == ("audio/mpeg", None)
    assert data == audio.read_bytes()
    # Validation decodes the full original; it does not impose a 182-second cutoff.
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(audio),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(probe.stdout) > 214


def test_no_rap_style_does_not_shorten_a_slow_ballad():
    from haytile.music import target_seconds

    lyrics = "\n".join(["Nou ka rive ansanm"] * 100)
    assert target_seconds(lyrics, "lyria-3.5", {"music_style": "Emotional ballad, 76 BPM, no rap, no rushed singing"}) == 300
    assert target_seconds(lyrics, "lyria-3.5", {"music_style": "Rap, 110 BPM"}) == 180
