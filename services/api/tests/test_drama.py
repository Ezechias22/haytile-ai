import io
import json

from PIL import Image

from haytile import providers, worker
from haytile.db import Model, Session

from .conftest import register
from .test_video import clip


def test_episode_pipeline_produces_real_final_media_and_editable_continuity(
    client, monkeypatch, tmp_path
):
    monkeypatch.setenv("HAYTILE_GEMINI_API_KEY", "fixture-not-a-real-key")
    with Session.begin() as db:
        for studio in ["minidrama", "image", "video"]:
            db.add(
                Model(
                    studio=studio,
                    model_id="fixture-" + studio,
                    enabled=True,
                    credits=0,
                    price_source="https://example.test",
                )
            )
    _, headers = register(client)
    png = io.BytesIO()
    Image.new("RGB", (20, 20), "blue").save(png, "PNG")
    blue = clip(tmp_path / "blue.mp4", "blue", 8)
    red = clip(tmp_path / "red.mp4", "red", 8)
    plan = {
        "title": "Two scenes",
        "continuity": "Same garden, blue shirt",
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
                "title": "First",
                "description": "In the garden",
                "dialogue": "Bonjou!",
                "characters": ["Mika"],
            },
            {
                "title": "Second",
                "description": "Same garden, camera turns",
                "dialogue": "Mwen la.",
                "characters": ["Mika"],
            },
        ],
    }
    calls = []

    def generate(studio, model, prompt, params):
        calls.append((studio, prompt, params))
        if studio == "text":
            return json.dumps(plan).encode(), "text/plain"
        if studio == "image":
            return png.getvalue(), "image/png"
        assert len(params["_reference_images"]) == 1
        return (
            blue if len([x for x in calls if x[0] == "video"]) == 1 else red
        ), "video/mp4"

    monkeypatch.setattr(providers, "generate", generate)
    request = {
        "studio": "minidrama",
        "title": "My episode",
        "prompt": "Yon ti istwa",
        "params": {
            "mode": "episode",
            "duration": 16,
            "aspect": "16:9",
            "language": "ht",
        },
        "confirmed_credits": 0,
        "idempotency_key": "episode-pipeline-001",
    }
    response = client.post("/v1/jobs", json=request, headers=headers)
    assert response.status_code == 202, response.text
    assert worker.run_once()
    jobs = client.get("/v1/jobs", headers=headers).json()
    assert jobs[0]["status"] == "completed", jobs
    projects = client.get("/v1/projects", headers=headers).json()
    doc = projects[0]["document"]
    assert doc["characters"][0]["reference_asset_id"]
    assert (
        doc["scenes"][0]["dialogue"] == "Bonjou!"
        and doc["scenes"][1]["dialogue"] == "Mwen la."
    )
    assert all(s["asset_id"] for s in doc["scenes"])
    assert doc["final_asset_id"]
    assets = client.get("/v1/assets", headers=headers).json()
    final = next(x for x in assets if x["id"] == doc["final_asset_id"])
    assert final["mime"] == "video/mp4"
    assert [c[0] for c in calls] == ["text", "image", "video", "video"]
    link = client.get("/v1/assets/" + final["id"] + "/link", headers=headers).json()[
        "path"
    ]
    response = client.get(link)
    assert response.status_code == 200 and len(response.content) > 1000
