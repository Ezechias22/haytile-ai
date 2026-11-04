"""Offline browser-only app/worker. Never import into production deployment.
No real provider transport or Firebase credentials are used.
"""

import os

os.environ["HAYTILE_GEMINI_API_KEY"] = "offline-browser-fixture-not-a-provider-key"
os.environ["HAYTILE_ACCOUNT_PROVIDER"] = "sql"
os.environ["HAYTILE_MODEL_CHOICES"] = "[]"
os.environ["HAYTILE_PRICING_POLICY"] = "operator"
os.environ["HAYTILE_PAID_IMAGES"] = "1"
os.environ["HAYTILE_GENERATION_ENABLED"] = "1"
os.environ["HAYTILE_WORKER_ENABLED"] = "1"
os.environ["HAYTILE_ENV"] = "development"
os.environ["HAYTILE_PUBLIC_ORIGIN"] = "http://127.0.0.1:3010"

import subprocess
import tempfile
import threading
import time
from pathlib import Path
from sqlalchemy import select
from haytile import providers, worker
from haytile.db import Base, Model, Session, User, engine
from haytile.security import password_hash
from haytile.main import app

assert engine.dialect.name == "postgresql" and "haytile_browser_creations_fixture" in str(engine.url)
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
with Session.begin() as db:
    db.add(
        User(
            email="creative-browser@example.test",
            password=password_hash("Offline-browser-password-123"),
            name="Creative browser fixture",
            locale="en",
            balance=50,
        )
    )
    db.add(
        Model(
            studio="music",
            model_id="offline-browser-model",
            enabled=True,
            credits=12,
            price_source="https://example.test/pricing",
        )
    )
with Session.begin() as db:
    db.add(Model(studio="text", model_id="offline-chat-model", enabled=True, credits=0, price_source="https://example.test/pricing"))
with Session.begin() as db:
    db.add(Model(studio="voice", model_id="offline-voice-model", enabled=True, credits=3, price_source="https://example.test/pricing"))
    db.add(Model(studio="image", model_id="offline-image-model", enabled=True, credits=8, price_source="https://example.test/pricing"))
with tempfile.TemporaryDirectory(prefix="offline-audio-fixture-") as folder:
    path = Path(folder) / "tone.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "1",
            "-c:a",
            "libmp3lame",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    media = path.read_bytes()


def fixture_generate(studio, model, prompt, params):
    if studio == "text":
        assert model == "offline-chat-model"
        time.sleep(1)
        assert "_chat_contents" in params
        return ("I am HAYTILE AI. Offline reply: " + prompt + ". Previous messages: " + str(len(params["_chat_contents"]))).encode(), "text/plain"
    if studio == "voice":
        assert model == "offline-voice-model" and params.get("chat_audio") is True and params["voice_name"] == "Puck"
        time.sleep(1)
        return media, "audio/mpeg"
    if studio == "image":
        import io
        from PIL import Image
        buf=io.BytesIO()
        Image.new("RGB",(64,64),"purple").save(buf,"PNG")
        return buf.getvalue(), "image/png"
    assert studio == "music" and model == "offline-browser-model"
    time.sleep(7)
    return media, "audio/mpeg"


def forbidden_transport(*args, **kwargs):
    raise AssertionError(
        "External provider HTTP requests are forbidden in the offline browser fixture"
    )


providers.generate = fixture_generate
providers.request = forbidden_transport
providers.discover = forbidden_transport


def loop():
    while True:
        worker.run_once()
        time.sleep(0.2)


threading.Thread(target=loop, daemon=True).start()
