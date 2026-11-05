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
