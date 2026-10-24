import base64
import io
import wave

import pytest

from haytile import providers


def test_video_transmits_all_character_references(monkeypatch):
    def request(method, path, payload=None, **kwargs):
        assert method == "POST" and path == "/interactions"
        assert [part["data"] for part in payload["input"][:-1]] == ["Zmlyc3Q=", "c2Vjb25k"]
        assert payload["input"][-1] == {"type": "text", "text": "Two people"}
        return {
            "status": "completed",
            "outputs": [{"type": "video", "data": "dmlkZW8=", "mime_type": "video/mp4"}],
        }

    monkeypatch.setattr(providers, "request", request)
    data, mime = providers.generate(
        "video",
        "fixture-video",
        "Two people",
        {
            "_reference_images": [
                {"data": "Zmlyc3Q=", "mime_type": "image/png"},
                {"data": "c2Vjb25k", "mime_type": "image/png"},
            ]
        },
    )
    assert data == b"video" and mime == "video/mp4"


def test_voice_real_wire_format_is_wrapped_in_playable_wav(monkeypatch):
    raw = b"\x00\x00" * 2400

    def request(method, path, payload=None, **kwargs):
        assert method == "POST" and path.endswith(":generateContent")
        assert (
            payload["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"][
                "voiceName"
            ]
            == "Kore"
        )
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "audio/L16;codec=pcm;rate=24000",
                                    "data": base64.b64encode(raw).decode(),
                                }
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(providers, "request", request)
    data, mime = providers.generate("voice", "fixture-tts", "Bonjou", {})
    assert mime == "audio/wav"
    with wave.open(io.BytesIO(data)) as audio:
        assert (
            audio.getframerate() == 24000
            and audio.getnframes() == 2400
            and audio.readframes(2400) == raw
        )


def test_async_interaction_poll_does_not_resubmit_generation(monkeypatch):
    calls = []
    recorded = []

    def request(method, path, payload=None, **kwargs):
        calls.append((method, path))
        if method == "POST":
            return {"id": "interaction-fixture", "status": "in_progress"}
        return {
            "id": "interaction-fixture",
            "status": "completed",
            "steps": [
                {
                    "type": "model_output",
                    "content": [
                        {
                            "type": "audio",
                            "mime_type": "audio/mpeg",
                            "data": base64.b64encode(b"fixture-mp3").decode(),
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(providers, "request", request)
    monkeypatch.setattr(providers.time, "sleep", lambda _: None)
    data, mime = providers.generate(
        "music", "fixture-music", "A song", {"_operation_callback": recorded.append}
    )
    assert data == b"fixture-mp3" and mime == "audio/mpeg"
    assert calls == [
        ("POST", "/interactions"),
        ("GET", "/interactions/interaction-fixture"),
    ]
    assert recorded == ["interaction-fixture"]


def test_resume_known_operation_only_reads_existing_output(monkeypatch):
    calls = []

    def request(method, path, payload=None, **kwargs):
        calls.append(method)
        return {
            "status": "completed",
            "outputs": [
                {
                    "type": "video",
                    "mime_type": "video/mp4",
                    "data": base64.b64encode(b"fixture-video").decode(),
                }
            ],
        }

    monkeypatch.setattr(providers, "request", request)
    data, mime = providers.generate(
        "video", "fixture-video", "ignored", {"_resume_operation_id": "known-operation"}
    )
    assert calls == ["GET"] and data == b"fixture-video" and mime == "video/mp4"


def test_model_media_uri_cannot_exfiltrate_provider_credentials(monkeypatch):
    monkeypatch.setattr(
        providers,
        "headers",
        lambda: (_ for _ in ()).throw(AssertionError("credential access must not occur")),
    )
    for uri in [
        "http://generativelanguage.googleapis.com/file",
        "https://evil.example/file",
        "https://user:pass@generativelanguage.googleapis.com/file",
        "https://127.0.0.1/file",
    ]:
        with pytest.raises(providers.ProviderError, match="DESTINATION_REJECTED"):
            providers.media_bytes({"uri": uri})


def test_empty_music_response_is_failed_not_reported_completed(monkeypatch):
    monkeypatch.setattr(
        providers,
        "request",
        lambda *_args, **_kwargs: {"status": "completed", "steps": []},
    )
    with pytest.raises(providers.ProviderError, match="NO_AUDIO"):
        providers.generate("music", "fixture-music", "A song", {})


def test_video_uri_polls_file_then_follows_only_safe_redirect_without_key(monkeypatch):
    import httpx

    seen = []
    states = iter(["PROCESSING", "ACTIVE"])
    monkeypatch.setattr(
        providers, "request", lambda method, path, **kwargs: {"state": next(states)}
    )
    monkeypatch.setattr(providers.time, "sleep", lambda _: None)
    monkeypatch.setattr(providers, "headers", lambda: {"x-goog-api-key": "fixture-secret"})
    original = httpx.Client

    def handler(request):
        seen.append((request.url.host, dict(request.headers)))
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(
                302,
                headers={"Location": "https://storage.googleapis.com/fixture/video.mp4"},
            )
        return httpx.Response(200, content=b"fixture-video")

    monkeypatch.setattr(
        providers.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert providers.media_bytes({"uri": "files/fixture-id"}) == b"fixture-video"
    assert seen[0][1]["x-goog-api-key"] == "fixture-secret"
    assert "x-goog-api-key" not in seen[1][1]
