import uuid

import httpx

from haytile import providers, storage, worker
from haytile.db import Job, Session

from .conftest import register
from .test_core import configure, job_request


def start(client, auth):
    body = {
        **job_request("text", 0, key=str(uuid.uuid4()), prompt="Explain the prevention topic"),
        "params": {"chat": True, "conversation_id": str(uuid.uuid4())},
    }
    response = client.post("/v1/jobs", headers=auth, json=body)
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_saved_answer_recovers_after_storage_failure_without_second_generation(client, monkeypatch):
    configure(monkeypatch, "text")
    _, auth = register(client)
    calls = []

    def transport(method, path, payload=None, **kwargs):
        calls.append((method, path))
        return {
            "candidates": [{"content": {"parts": [{"text": "A real saved offline response."}]}}]
        }

    monkeypatch.setattr(providers, "request", transport)
    put = storage.put

    def broken(*args, **kwargs):
        raise RuntimeError("offline storage failure")

    monkeypatch.setattr(storage, "put", broken)
    identifier = start(client, auth)
    assert worker.run_once()
    failed = client.get("/v1/jobs/" + identifier, headers=auth).json()
    assert failed["error"] == "WORKER_INTERRUPTED_RECONCILE" and failed["retry_mode"] == "resume"
    assert failed["params"]["failure_phase"] == "storage"
    assert (
        "provider_response" not in failed["params"]
        and "provider_text_result" not in failed["params"]
    )
    with Session() as db:
        assert (
            db.get(Job, identifier).params["provider_text_result"]["text"]
            == "A real saved offline response."
        )
    monkeypatch.setattr(storage, "put", put)
    assert client.post("/v1/jobs/" + identifier + "/retry", headers=auth).status_code == 200
    assert worker.run_once()
    saved = client.get("/v1/jobs/" + identifier, headers=auth).json()
    assert saved["status"] == "completed" and len(calls) == 1
    with Session() as db:
        assert "provider_response" not in db.get(Job, identifier).params
    assert client.get("/v1/wallet", headers=auth).json()["reserved"] == 0


def test_unknown_text_outcome_requires_explicit_new_request(client, monkeypatch):
    configure(monkeypatch, "text")
    _, auth = register(client)
    calls = []

    def transport(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise providers.ProviderError("PROVIDER_NETWORK_OR_RESPONSE")
        return {
            "candidates": [
                {"content": {"parts": [{"text": "New response after an explicit resend."}]}}
            ]
        }

    monkeypatch.setattr(providers, "request", transport)
    identifier = start(client, auth)
    assert worker.run_once()
    failed = client.get("/v1/jobs/" + identifier, headers=auth).json()
    assert failed["retry_mode"] == "new_request"
    response = client.post("/v1/jobs/" + identifier + "/retry", headers=auth)
    assert (
        response.status_code == 409
        and response.json()["detail"] == "NEW_REQUEST_CONFIRMATION_REQUIRED"
    )
    assert len(calls) == 1
    assert (
        client.post(
            "/v1/jobs/" + identifier + "/retry", headers=auth, json={"new_request": True}
        ).status_code
        == 200
    )
    assert worker.run_once()
    assert len(calls) == 2
    assert client.get("/v1/jobs/" + identifier, headers=auth).json()["status"] == "completed"


def test_provider_rejection_keeps_reason_and_redacts_secret(monkeypatch):
    monkeypatch.setenv("HAYTILE_GEMINI_API_KEY", "AIzaPrivateExampleKey")

    def transport(self, method, url, **kwargs):
        return httpx.Response(
            400,
            json={
                "error": {
                    "status": "INVALID_ARGUMENT",
                    "message": "Prompt blocked by content policy. AIzaPrivateExampleKey",
                }
            },
        )

    monkeypatch.setattr(httpx.Client, "request", transport)
    try:
        providers.request("POST", "/interactions", {})
        assert False
    except providers.ProviderError as error:
        assert str(error) == "PROVIDER_CONTENT_REJECTED"
        assert "PrivateExampleKey" not in error.public_message
        assert error.provider_status == "INVALID_ARGUMENT"


def test_music_awareness_context_keeps_every_original_lyric(monkeypatch):
    calls = []
    lyrics = "Prevansyon, pwoteksyon, sispann vyolans.\nPa fè lòt moun soufri."

    def transport(method, path, payload=None, **kwargs):
        calls.append(payload)
        return {"status": "completed", "outputs": [{"type": "audio", "data": "YQ=="}]}

    monkeypatch.setattr(providers, "request", transport)
    providers.generate("music", "lyria-3.5", lyrics, {"vocal_style": "duet"})
    assert len(calls) == 1 and lyrics in calls[0]["input"]
    assert "without endorsing harm" in calls[0]["input"]
    assert "never silently censor" in calls[0]["input"]


def test_missing_optional_grounding_fields_do_not_fail_a_valid_reply(client, monkeypatch):
    configure(monkeypatch, "text")
    _, auth = register(client)
    responses = [
        None,
        {
            "groundingChunks": None,
            "groundingSupports": None,
            "webSearchQueries": None,
            "searchEntryPoint": None,
        },
    ]

    def transport(*args, **kwargs):
        return {
            "promptFeedback": None,
            "candidates": [
                {
                    "content": {"parts": [{"text": "Reply without web research."}]},
                    "groundingMetadata": responses.pop(0),
                }
            ],
        }

    monkeypatch.setattr(providers, "request", transport)
    for _ in range(2):
        identifier = start(client, auth)
        assert worker.run_once()
        assert client.get("/v1/jobs/" + identifier, headers=auth).json()["status"] == "completed"


def test_raw_response_is_reused_after_local_parsing_error(client, monkeypatch):
    from haytile import chat_tools

    configure(monkeypatch, "text")
    _, auth = register(client)
    calls = []

    def transport(*args, **kwargs):
        calls.append(True)
        return {"candidates": [{"content": {"parts": [{"text": "Preserved upstream reply."}]}}]}

    monkeypatch.setattr(providers, "request", transport)
    original = chat_tools.grounding

    def broken(*args, **kwargs):
        raise RuntimeError("offline parser failure")

    monkeypatch.setattr(chat_tools, "grounding", broken)
    identifier = start(client, auth)
    assert worker.run_once()
    assert client.get("/v1/jobs/" + identifier, headers=auth).json()["retry_mode"] == "resume"
    monkeypatch.setattr(chat_tools, "grounding", original)
    assert client.post("/v1/jobs/" + identifier + "/retry", headers=auth).status_code == 200
    assert worker.run_once()
    assert client.get("/v1/jobs/" + identifier, headers=auth).json()["status"] == "completed"
    assert len(calls) == 1


def test_empty_saved_reply_can_only_start_over_after_explicit_resend(client, monkeypatch):
    configure(monkeypatch, "text")
    _, auth = register(client)
    calls = []

    def transport(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            return {"candidates": []}
        return {"candidates": [{"content": {"parts": [{"text": "A new usable reply."}]}}]}

    monkeypatch.setattr(providers, "request", transport)
    identifier = start(client, auth)
    assert worker.run_once()
    assert client.get("/v1/jobs/" + identifier, headers=auth).json()["retry_mode"] == "new_request"
    assert client.post("/v1/jobs/" + identifier + "/retry", headers=auth).status_code == 409
    assert (
        client.post(
            "/v1/jobs/" + identifier + "/retry", headers=auth, json={"new_request": True}
        ).status_code
        == 200
    )
    assert worker.run_once()
    assert (
        len(calls) == 2
        and client.get("/v1/jobs/" + identifier, headers=auth).json()["status"] == "completed"
    )
