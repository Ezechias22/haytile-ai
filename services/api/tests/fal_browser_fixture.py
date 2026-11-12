"""Offline fal protocol simulator. Imported only by the isolated browser test app."""

import io
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from haytile import fal_catalog, fal_client, providers
from haytile.db import Model, Session, User
from haytile.security import password_hash
from tests.test_fal import profile as priced_profile


def install(app, normal_generate, audio):
    import os

    os.environ["FAL_KEY"] = "offline-fal-browser-no-real-key"
    os.environ["HAYTILE_OPERATOR_BILLING_ACK"] = "1"
    with Session.begin() as db:
        actor = db.scalar(select(User).where(User.email == "billing-admin@example.test")).id
        db.add(
            User(
                email="fal-browser@example.test",
                password=password_hash("Offline-browser-password-123"),
                name="Fal browser fixture",
                locale="en",
                balance=10000,
            )
        )
        db.add(
            Model(
                studio="video",
                model_id="offline-google-video-paused",
                enabled=False,
                credits=100,
                price_source="https://example.test/pricing",
            )
        )
    for original in fal_catalog.DEFAULTS:
        # Variable GPU-compute pricing remains deliberately unapproved.
        if original["endpoint_id"] == "fal-ai/birefnet":
            continue
        p = priced_profile(original["adapter"], original["studio"])
        p.update(
            {
                key: original[key]
                for key in ("id", "endpoint_id", "label", "input_schema", "constants", "fields")
            }
        )
        fal_catalog.save(p, actor)
    png = io.BytesIO()
    Image.new("RGB", (512, 512), "purple").save(png, "PNG")
    image = png.getvalue()
    folder = Path(tempfile.mkdtemp(prefix="offline-fal-video-"))
    video = folder / "video.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=blue:size=160x90:rate=16",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "8",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    operations = {}
    stats = {"submissions": [], "reads": 0}
    real_generate = providers.generate

    def generate(studio, model, prompt, params):
        if model.startswith("fal-"):
            return real_generate(studio, model, prompt, params)
        return normal_generate(studio, model, prompt, params)

    def request(method, path, payload=None, **kwargs):
        if kwargs.get("platform"):
            if path == "/models/pricing":
                identifier = kwargs["params"]["endpoint_id"]
                p = next(p for p in fal_catalog.profiles() if p["endpoint_id"] == identifier)
                if identifier == "fal-ai/birefnet":
                    return {
                        "prices": [
                            {
                                "endpoint_id": identifier,
                                "unit_price": 0.000575,
                                "unit": "compute seconds",
                                "currency": "USD",
                            }
                        ]
                    }
                return {
                    "prices": [
                        {
                            "endpoint_id": identifier,
                            "unit_price": float(p["unit_price"]),
                            "unit": p["price_unit"],
                            "currency": "USD",
                        }
                    ]
                }
            if path == "/models":
                params = kwargs.get("params", {})
                query = params.get("q", "").lower()
                identifier = params.get("endpoint_id")
                rows = [
                    p
                    for p in fal_catalog.profiles()
                    if (not identifier or p["endpoint_id"] == identifier)
                    and (not query or query in (p["label"] + " " + p["endpoint_id"]).lower())
                ]
                return {
                    "models": [
                        {
                            "endpoint_id": p["endpoint_id"],
                            "metadata": {
                                "display_name": p["label"],
                                "status": "active",
                                "category": p["studio"],
                                "description": "Offline catalog fixture",
                                "license_type": "commercial",
                            },
                            "openapi": {
                                "components": {"schemas": {"FixtureInput": p["input_schema"]}}
                            },
                        }
                        for p in rows[:25]
                    ],
                    "has_more": False,
                    "next_cursor": None,
                }
        if method == "POST":
            p = next(p for p in fal_catalog.profiles() if p["endpoint_id"] == path.lstrip("/"))
            identifier = "offline-fal-" + str(len(operations) + 1)
            operations[identifier] = {"profile": p, "payload": payload, "polls": 0}
            stats["submissions"].append({"model": p["id"], "payload": payload})
            return {"request_id": identifier}
        if method == "GET" and "/requests/" in path:
            identifier = path.split("/requests/", 1)[1].split("/")[0]
            op = operations[identifier]
            stats["reads"] += 1
            if path.endswith("/status"):
                op["polls"] += 1
                return {"status": "IN_PROGRESS" if op["polls"] == 1 else "COMPLETED"}
            p = op["profile"]
            url = "https://v3.fal.media/offline/" + identifier
            if p["adapter"] == "text":
                prompt = op["payload"].get("prompt", "")
                if "Return ONLY valid JSON" in prompt:
                    count = int(re.search(r"exactly (\d+) scenes", prompt)[1])
                    plan = {
                        "title": "Offline drama",
                        "continuity": "Daylight in a garden",
                        "characters": [
                            {
                                "name": "Maya",
                                "appearance": "young adult with brown eyes",
                                "wardrobe": "blue jacket",
                                "voice": "warm voice",
                            }
                        ],
                        "scenes": [
                            {
                                "title": "Scene " + str(i + 1),
                                "description": "Maya speaks in the garden.",
                                "dialogue": "We can help each other.",
                                "characters": ["Maya"],
                            }
                            for i in range(count)
                        ],
                    }
                    return {"output": json.dumps(plan)}
                return {"output": "Offline fal text reply. I am HAYTILE AI."}
            if p["studio"] == "video":
                return {"video": {"url": url + "/video.mp4"}}
            if p["studio"] in ("music", "voice"):
                return {"audio": {"url": url + "/audio.wav"}}
            if p["adapter"] in ("background", "upscale"):
                return {"image": {"url": url + "/image.png"}}
            return {"images": [{"url": url + "/image.png"}], "has_nsfw_concepts": [False]}
        raise AssertionError("Unexpected offline fal request " + method + " " + path)

    def media(url, destination=None):
        assert url.startswith("https://v3.fal.media/offline/")
        if url.endswith("/video.mp4"):
            if destination:
                shutil.copyfile(video, destination)
                return destination
            return video.read_bytes()
        data = image if url.endswith("/image.png") else audio
        if destination:
            destination.write_bytes(data)
            return destination
        return data

    fal_client.request = request
    fal_client.media = media
    providers.generate = generate

    @app.get("/v1/offline/fal-stats")
    def statistics():
        return stats

    app.routes.insert(0, app.routes.pop())
