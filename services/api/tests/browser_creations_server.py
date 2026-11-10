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
os.environ.setdefault("HAYTILE_PUBLIC_ORIGIN", "http://127.0.0.1:3010")
os.environ["HAYTILE_LIVE_VOICE_ENABLED"] = "1"

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
            balance=200,
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
with Session.begin() as db:
    db.add(User(email="billing-admin@example.test", password=password_hash("Offline-browser-password-123"), name="Billing fixture administrator", locale="en", role="admin", balance=0))
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


interrupted_prompts = set()


def fixture_generate(studio, model, prompt, params):
    if studio == "text":
        assert model == "offline-chat-model"
        time.sleep(1)
        assert "_chat_contents" in params
        if prompt == "Offline interrupted reply" and prompt not in interrupted_prompts:
            interrupted_prompts.add(prompt)
            raise providers.ProviderError("PROVIDER_NETWORK_OR_RESPONSE")
        if prompt == "Find nearby offline hospital":
            if not params.get("location"):
                params["_location_request_callback"](True)
                return b"Please authorize location to find nearby help.", "text/plain"
            params["_location_request_callback"](False)
            params["_grounding_callback"]({"searched": True, "sources": [{"url":"https://example.org/hospital", "title":"Offline hospital source"}], "search_html": '<a href="https://google.com">Search suggestions</a><script>parent.fixtureUnsafe=true</script>'})
            return b"## Nearby help\n\nNearby help found using the location you shared. [1]", "text/plain"
        return ("I am HAYTILE AI. Offline reply: " + prompt + ". Previous messages: " + str(len(params["_chat_contents"]))).encode(), "text/plain"
    if studio == "voice":
        assert model == "offline-voice-model" and params.get("chat_audio") is True and params["voice_name"] in ("Puck", "Charon", "Kore")
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

# Native Live test transport: real local WebSocket/PCM path, no Google connection.
import asyncio
import base64
import json
import math
import struct
from haytile import live_voice
live_observed = {"frames": 0, "setups": []}
class OfflineLive:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.queue.put_nowait(json.dumps({"setupComplete": {}}))
        self.frames = 0
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def send(self, raw):
        message = json.loads(raw)
        if "setup" in message:
            live_observed["setups"].append(message["setup"])
        if "audio" in message.get("realtimeInput", {}):
            self.frames += 1
            live_observed["frames"] += 1
            if self.frames in (1, 7):
                pcm = b"".join(struct.pack("<h", int(4000*math.sin(i*440*2*math.pi/24000))) for i in range(19200))
                self.queue.put_nowait(json.dumps({"serverContent": {"modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}}))
            if self.frames == 5:
                self.queue.put_nowait(json.dumps({"serverContent": {"interrupted": True}}))
    async def recv(self): return await self.queue.get()
    def __aiter__(self): return self
    async def __anext__(self): return await self.recv()
live_voice.connect = lambda *args, **kwargs: OfflineLive()
@app.get("/v1/offline/live-observed")
def offline_live_observed(): return live_observed

# The production catch-all is installed before test-only routes.
app.router.routes.insert(0, app.router.routes.pop())

# Verify the real HTTP gateway + Next proxy preserve Stripe's signed raw bytes.
os.environ['STRIPE_WEBHOOK_SECRET']='whsec_offline_transport_fixture'
from fastapi import Request
from haytile import billing
@app.post('/v1/offline/stripe-signature')
async def offline_stripe_signature(request: Request):
    raw=await request.body()
    return {'valid':billing.signature(raw,request.headers.get('stripe-signature',''))}
app.router.routes.insert(0,app.router.routes.pop())


# Failure injection is restricted to this explicit offline test server.
from haytile import location_state
original_location_preference = location_state.preference
preparation_fault = {"remaining": 0}
def fixture_location_preference(db, user_id):
    if preparation_fault["remaining"]:
        preparation_fault["remaining"] -= 1
        raise ImportError("Offline worker preparation failure")
    return original_location_preference(db, user_id)
location_state.preference = fixture_location_preference

@app.post("/v1/offline/prepare-import-failure")
def offline_prepare_import_failure():
    preparation_fault["remaining"] = 1
    return {"armed": True}
app.router.routes.insert(0,app.router.routes.pop())
