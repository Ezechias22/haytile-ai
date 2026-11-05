import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from haytile import pricing, providers, storage, worker
from haytile.db import Asset, Model, Session
from haytile.video import probe

from .conftest import register
from .test_core import configure, job_request


def test_title_suggestion_and_rename_during_generation(client, monkeypatch):
    configure(monkeypatch, "text", 999)
    user, h = register(client)
    body = {
        **job_request("text", 0, prompt="Tit: Lakay Nan Kè Mwen\nYon istwa orijinal."),
        "title": "",
    }
    first = client.post("/v1/jobs", headers=h, json=body)
    assert first.status_code == 202 and first.json()["title"] == "Lakay Nan Kè Mwen"
    job_id = first.json()["id"]

    def generate(*args):
        changed = client.patch(
            "/v1/jobs/" + job_id, headers=h, json={"title": "Nouvo tit mwen"}
        )
        assert changed.status_code == 200
        return b"Explicit local content fixture", "text/plain"

    monkeypatch.setattr(providers, "generate", generate)
    assert worker.run_once()
    final = client.get("/v1/assets", headers=h).json()[0]
    assert final["title"] == "Nouvo tit mwen"
    _, other = register(client, "different-owner@example.test")
    assert (
        client.patch(
            "/v1/jobs/" + job_id, headers=other, json={"title": "Intruder"}
        ).status_code
        == 404
    )
    assert (
        client.patch("/v1/jobs/" + job_id, headers=h, json={"title": "   "}).status_code
        == 400
    )
    assert (
        client.patch(
            "/v1/assets/" + final["id"], headers=h, json={"title": "Tit final"}
        ).status_code
        == 200
    )
    assert client.get("/v1/jobs", headers=h).json()[0]["title"] == "Tit final"
    assert client.get("/v1/wallet", headers=h).json()["transactions"] == []
    assert client.get("/v1/wallet", headers=h).json()["balance"] == 0
    model = next(m for m in client.get("/v1/models").json() if m["studio"] == "text")
    assert model["credits"] == 0 and model["options"][0]["credits"] == 0


def test_verified_prices_scale_with_cost_duration_and_voice_size(monkeypatch):
    monkeypatch.setenv("HAYTILE_PRICING_POLICY", "verified")
    assert pricing.quote("music", "lyria-3-clip-preview", "Song", {})["credits"] == 16
    assert pricing.quote("music", "lyria-3.5", "Song", {})["credits"] == 32
    assert (
        pricing.quote("video", pricing.VIDEO, "Scene", {"duration": 8})["credits"]
        == 168
    )
    assert (
        pricing.quote("video", pricing.VIDEO, "Scene", {"duration": 180})["credits"]
        == 3864
    )
    episode = pricing.quote(
        "minidrama",
        "gemini-3.8-flash",
        "Story",
        {"mode": "episode", "duration": 180},
        render_config={"video": pricing.VIDEO},
    )
    assert episode["clip_count"] == 23 and episode["credits"] == 4202
    cheap = pricing.quote("voice", "gemini-3.8-flash-lite-tts", "a" * 1000, {})
    premium = pricing.quote("voice", "gemini-2.5-pro-preview-tts", "a" * 1000, {})
    assert premium["credits"] > cheap["credits"] > 0
    assert (
        pricing.quote("voice", "gemini-3.8-flash-lite-tts", "a" * 1001, {})["credits"]
        == cheap["credits"] * 2
    )
    assert pricing.quote("text", "gemini-3.8-flash", "Text", {}, 999)["credits"] == 0
    assert (
        pricing.quote("image", "gemini-3-pro-image", "Image", {}, 999)["credits"] == 0
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        pricing.base_credits("video", "gemini-omni-flash-preview")


def test_voice_choices_are_validated_and_reach_provider_without_generation_calls(
    client, monkeypatch
):
    assert len(client.get("/v1/voices").json()["voices"]) == 30
    captured = []

    def request(method, path, payload=None, **kwargs):
        captured.append(payload)
        return {
            "status": "completed",
            "outputs": [
                {
                    "type": "audio",
                    "mime_type": "audio/wav",
                    "data": base64.b64encode(b"explicit-wire-fixture").decode(),
                }
            ],
        }

    monkeypatch.setattr(providers, "request", request)
    data, mime = providers.generate(
        "voice",
        "gemini-3.8-flash-tts",
        "Bonjou",
        {"voice_name": "Puck", "_max_output_tokens": 4096},
    )
    assert data == b"explicit-wire-fixture"
    assert captured[0]["generation_config"]["speech_config"][0]["voice"] == "Puck"
    assert captured[0]["generation_config"]["max_output_tokens"] == 4096
    with pytest.raises(providers.ProviderError):
        providers.generate(
            "voice", "gemini-3.8-flash-tts", "Bonjou", {"voice_name": "invented"}
        )


def test_long_portrait_episode_uses_23_native_clips_and_file_upload(
    client, monkeypatch, tmp_path
):
    monkeypatch.setenv("HAYTILE_GEMINI_API_KEY", "fixture-no-real-generation")
    monkeypatch.setenv("HAYTILE_TRIAL_AI", "1")
    monkeypatch.setenv("HAYTILE_TRIAL_MAX_EPISODE_SECONDS", "180")
    with Session.begin() as db:
        for studio in ("minidrama", "video", "image"):
            db.add(
                Model(
                    studio=studio,
                    model_id="fixture-" + studio,
                    enabled=True,
                    credits=0,
                    price_source="https://example.test",
                )
            )
    _, h = register(client)
    # Encode a compatible local synthetic clip once; no provider endpoint is contacted.
    import subprocess

    native = tmp_path / "native.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=720x1280:r=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "8",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            str(native),
        ],
        check=True,
        capture_output=True,
    )
    native_bytes = native.read_bytes()
    png = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(png, "PNG")
    plan = {
        "title": "Three minute fixture",
        "continuity": "Same room and clothes",
        "characters": [
            {
                "name": "Mika",
                "appearance": "Short hair",
                "wardrobe": "Blue shirt",
                "voice": "Warm",
            }
        ],
        "scenes": [
            {
                "title": f"Scene {i + 1}",
                "description": "In the room",
                "dialogue": "Bonjou.",
                "characters": ["Mika"],
            }
            for i in range(23)
        ],
    }
    calls = []

    def generate(studio, model, prompt, params):
        calls.append(studio)
        if studio == "text":
            return json.dumps(plan).encode(), "text/plain"
        if studio == "image":
            return png.getvalue(), "image/png"
        assert studio == "video" and params["_reference_images"]
        return native_bytes, "video/mp4"

    monkeypatch.setattr(providers, "generate", generate)
    file_uploads = []
    original = storage.put_file

    def upload(path, mime):
        assert isinstance(path, Path) and path.is_file()
        file_uploads.append(path.stat().st_size)
        return original(path, mime)

    monkeypatch.setattr(storage, "put_file", upload)
    body = job_request("minidrama", 0, prompt="A fictional 3-minute story")
    body["params"] = {
        "mode": "episode",
        "duration": 180,
        "aspect": "9:16",
        "language": "ht",
    }
    result = client.post("/v1/jobs", headers=h, json=body)
    assert result.status_code == 202, result.text
    assert worker.run_once()
    job = client.get("/v1/jobs", headers=h).json()[0]
    assert job["status"] == "completed", job
    assert (
        calls.count("video") == 23
        and calls.count("text") == 1
        and len(file_uploads) == 1
    )
    with Session() as db:
        asset = db.get(Asset, job["params"]["result_asset_id"])
        path = tmp_path / "verified-final.mp4"
        path.write_bytes(storage.get(asset.key))
    info = probe(path)
    assert abs(float(info["format"]["duration"]) - 180) < 0.15
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (720, 1280)
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    project = client.get("/v1/projects", headers=h).json()[0]
    assert (
        len(project["document"]["scenes"]) == 23
        and sum(s["duration"] for s in project["document"]["scenes"]) == 180
    )
    assert (
        client.patch(
            "/v1/jobs/" + job["id"], headers=h, json={"title": "Renamed episode"}
        ).status_code
        == 200
    )
    with Session() as db:
        assert (
            db.get(Asset, job["params"]["result_asset_id"]).title == "Renamed episode"
        )
        assert db.scalar(select(Asset).where(Asset.title.like("[Reference]%")))
