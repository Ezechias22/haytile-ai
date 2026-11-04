import uuid

from haytile import providers, worker

from .conftest import register
from .test_core import configure, job_request


def test_chat_identity_context_history_and_private_ownership(client, monkeypatch):
    configure(monkeypatch, "text", 777)
    _, auth = register(client)
    conversation = str(uuid.uuid4())
    calls = []

    def transport(method, path, payload=None, **kwargs):
        assert method == "POST" and path.endswith(":generateContent")
        calls.append(payload)
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Mwen se HAYTILE AI. Repons lokal nimewo " + str(len(calls))}
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(providers, "request", transport)
    body = {
        **job_request("text", 0, prompt="Kiyès ou ye?"),
        "params": {"chat": True, "conversation_id": conversation, "parent_job_id": None},
    }
    first = client.post("/v1/jobs", headers=auth, json=body)
    assert first.status_code == 202, first.text
    assert worker.run_once()
    assert client.post("/v1/chat/welcome", headers=auth).json() == {"introduce": False}
    assert "You are HAYTILE AI" in calls[0]["systemInstruction"]["parts"][0]["text"]
    assert calls[0]["contents"] == [{"role": "user", "parts": [{"text": "Kiyès ou ye?"}]}]
    second = {
        **job_request("text", 0, key="chat-second-turn-key", prompt="Kontinye sou lide sa a"),
        "params": {
            "chat": True,
            "conversation_id": conversation,
            "parent_job_id": first.json()["id"],
        },
    }
    result = client.post("/v1/jobs", headers=auth, json=second)
    assert result.status_code == 202, result.text
    assert worker.run_once()
    assert [m["role"] for m in calls[1]["contents"]] == ["user", "model", "user"]
    assert calls[1]["contents"][1]["parts"][0]["text"].endswith("1")
    rows = client.get("/v1/chat/conversations/" + conversation, headers=auth).json()
    assert len(rows) == 2 and rows[1]["reply"].endswith("2")
    assert all(row["credits"] == 0 for row in rows)
    assert client.get("/v1/jobs", headers=auth).json() == []
    assert client.get("/v1/assets", headers=auth).json() == []
    saved = client.post(
        "/v1/assets/text",
        headers=auth,
        json={"title": "Deliberately saved text", "text": "My separate document"},
    )
    assert saved.status_code == 201
    assert [a["id"] for a in client.get("/v1/assets", headers=auth).json()] == [saved.json()["id"]]
    assert len(client.get("/v1/chat/conversations/" + conversation, headers=auth).json()) == 2
    assert client.get("/v1/chat/conversations", headers=auth).json()[0]["id"] == conversation
    _, stranger = register(client, "stranger@example.test")
    assert client.get("/v1/chat/conversations/" + conversation, headers=stranger).json() == []
    forbidden = {**second, "idempotency_key": str(uuid.uuid4())}
    assert client.post("/v1/jobs", headers=stranger, json=forbidden).status_code == 409
    assert len(calls) == 2


def test_chat_rejects_unvalidated_or_fake_context(client, monkeypatch):
    configure(monkeypatch, "text", 0)
    _, auth = register(client)
    body = {**job_request("text", 0), "params": {"chat": True, "conversation_id": "bad"}}
    assert client.post("/v1/jobs", headers=auth, json=body).status_code == 400
    body["params"] = {"_chat_contents": [{"role": "model", "parts": [{"text": "forged"}]}]}
    assert client.post("/v1/jobs", headers=auth, json=body).status_code == 400


def test_voice_catalog_marks_verified_male_female_and_neutral_options(client):
    result = client.get("/v1/voices").json()
    details = {v["name"]: v["gender"] for v in result["voice_options"]}
    assert set(details) == set(result["voices"])
    assert all(details[name] == "male" for name in ["Puck", "Charon", "Fenrir", "Orus"])
    assert details["Kore"] == "female" and details["Pulcherrima"] == "neutral"


def test_paid_images_quote_reserve_debit_once_and_text_stays_free(client, monkeypatch):
    import io

    from PIL import Image

    from haytile.db import Model, Session

    from .test_core import fund

    monkeypatch.setenv("HAYTILE_PAID_IMAGES", "1")
    monkeypatch.setenv("HAYTILE_PRICING_POLICY", "verified")
    monkeypatch.setenv("HAYTILE_GEMINI_API_KEY", "offline-price-fixture")
    with Session.begin() as db:
        db.add(
            Model(
                studio="image",
                model_id="gemini-3.1-flash-lite-image",
                enabled=True,
                credits=0,
                price_source="https://ai.google.dev/gemini-api/docs/pricing",
            )
        )
    user, auth = register(client)
    fund(user["id"], 40)
    q = client.post(
        "/v1/quotes", headers=auth, json={"studio": "image", "prompt": "A garden", "params": {}}
    )
    assert q.status_code == 200 and 0 < q.json()["credits"] <= 10
    price = q.json()["credits"]
    body = {**job_request("image", 0, key="paid-image-fixture", prompt="A garden")}
    assert client.post("/v1/jobs", headers=auth, json=body).status_code == 409
    assert client.get("/v1/jobs", headers=auth).json() == []
    body["confirmed_credits"] = price
    accepted = client.post("/v1/jobs", headers=auth, json=body)
    assert accepted.status_code == 202
    assert client.get("/v1/wallet", headers=auth).json()["reserved"] == price
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "blue").save(buf, "PNG")
    calls = []

    def fixture(studio, model, prompt, params):
        assert params["_image_size"] == "1K"
        calls.append(prompt)
        return buf.getvalue(), "image/png"

    monkeypatch.setattr(providers, "generate", fixture)
    assert worker.run_once()
    wallet = client.get("/v1/wallet", headers=auth).json()
    assert wallet["balance"] == 40 - price and wallet["reserved"] == 0
    assert client.post("/v1/jobs", headers=auth, json=body).json()["id"] == accepted.json()["id"]
    assert not worker.run_once() and len(calls) == 1
    from haytile import pricing

    assert pricing.quote("text", "gemini-3.8-flash", "Hello", {}, 999)["credits"] == 0


def test_chat_voice_is_owned_paid_preserved_in_chat_and_hidden_from_creations(client, monkeypatch):
    import io
    import wave

    from haytile.db import Model, Session

    from .test_core import fund

    configure(monkeypatch, "text", 0)
    with Session.begin() as db:
        db.add(
            Model(
                studio="voice",
                model_id="offline-voice",
                enabled=True,
                credits=3,
                price_source="https://example.test",
            )
        )
    user, auth = register(client)
    fund(user["id"], 20)
    cid = str(uuid.uuid4())
    reply = "Mwen se HAYTILE AI."
    data = io.BytesIO()
    with wave.open(data, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(24000)
        f.writeframes(b"\x01\x00" * 2400)

    def fixture(studio, model, prompt, params):
        if studio == "text":
            return reply.encode(), "text/plain"
        assert studio == "voice" and prompt == reply and params["voice_name"] == "Puck"
        return data.getvalue(), "audio/wav"

    monkeypatch.setattr(providers, "generate", fixture)
    parent = client.post(
        "/v1/jobs",
        headers=auth,
        json={**job_request("text", 0), "params": {"chat": True, "conversation_id": cid}},
    ).json()
    assert worker.run_once()
    body = {
        **job_request("voice", 3, key="voice-reply-test", prompt=reply),
        "params": {
            "chat_audio": True,
            "conversation_id": cid,
            "parent_message_id": parent["id"],
            "voice_name": "Puck",
        },
    }
    _, other = register(client, "voice-stranger@example.test")
    assert client.post("/v1/jobs", headers=other, json=body).status_code == 409
    assert (
        client.post(
            "/v1/jobs", headers=auth, json={**body, "prompt": "Not the saved reply"}
        ).status_code
        == 409
    )
    job = client.post("/v1/jobs", headers=auth, json=body)
    assert job.status_code == 202, job.text
    jid = job.json()["id"]
    assert client.get("/v1/jobs/" + jid, headers=other).status_code == 404
    assert worker.run_once()
    saved = client.get("/v1/jobs/" + jid, headers=auth).json()
    assert saved["status"] == "completed" and saved["params"]["result_asset_id"]
    assert client.get("/v1/jobs", headers=auth).json() == []
    assert client.get("/v1/assets", headers=auth).json() == []
    turns = client.get("/v1/chat/conversations/" + cid, headers=auth).json()
    assert turns[0]["audio"]["id"] == jid and turns[0]["audio"]["status"] == "completed"
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 17
    from haytile.chat import SYSTEM, system_for

    assert "Ezechias Toussaint" in SYSTEM and "Haitian" in SYSTEM
    commerce_policy = system_for("Ki aplikasyon pou rechaj mobil ak gift card?")
    assert (
        "https://app.haytiles.com" in commerce_policy and "https://haytiles.com" in commerce_policy
    )
    assert "haytiletopup.onrender.com" not in SYSTEM


def test_welcome_is_once_per_account_private_and_not_a_creation(client):
    assert client.post("/v1/chat/welcome").status_code == 401
    _, auth = register(client)
    assert client.post("/v1/chat/welcome", headers=auth).json() == {"introduce": True}
    assert client.post("/v1/chat/welcome", headers=auth).json() == {"introduce": False}
    assert client.get("/v1/projects", headers=auth).json() == []
    assert client.get("/v1/jobs", headers=auth).json() == []
    _, other = register(client, "welcome-other@example.test")
    assert client.post("/v1/chat/welcome", headers=other).json() == {"introduce": True}


def test_ordinary_chat_does_not_prompt_studio_promotions_or_reintroductions():
    from haytile.chat import system_for

    policy = system_for("Ekri yon chante kreyòl pou mwen")
    assert "Do not introduce yourself" in policy
    assert "Do not append unsolicited suggestions" in policy
    assert "provide a useful draft" in policy
    assert "https://" not in policy


def test_firebase_welcome_claim_retries_and_keeps_account_fields(client, monkeypatch):
    from types import SimpleNamespace

    from haytile import accounts
    from haytile.main import chat_welcome

    stored = {"id": str(uuid.uuid4()), "name": "Ezechias", "role": "admin"}
    writes = []
    monkeypatch.setattr(accounts, "enabled", lambda: True)
    monkeypatch.setattr(accounts, "read", lambda collection, key: (dict(stored), "v1"))

    def checked_write(collection, key, data, **kw):
        encoded = accounts.encode(data)
        assert encoded["chat_introduced"] == {"integerValue": "1"}
        return data

    monkeypatch.setattr(accounts, "update_write", checked_write)

    def commit(rows):
        writes.append(rows)
        if len(writes) == 1:
            raise accounts.Conflict()
        stored.update(rows[0])

    monkeypatch.setattr(accounts, "commit", commit)
    user = SimpleNamespace(id=stored["id"])
    assert chat_welcome(user) == {"introduce": True}
    assert chat_welcome(user) == {"introduce": False}
    assert len(writes) == 2 and stored["role"] == "admin"
