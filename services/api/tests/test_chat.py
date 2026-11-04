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
