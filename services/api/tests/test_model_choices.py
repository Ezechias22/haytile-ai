import json

from haytile import providers, worker
from haytile.db import Model, Session

from .conftest import register
from .test_core import configure, fund, job_request


def options(monkeypatch):
    monkeypatch.setenv("HAYTILE_OPERATOR_BILLING_ACK", "1")
    monkeypatch.setenv(
        "HAYTILE_MODEL_CHOICES",
        json.dumps(
            [
                {
                    "studio": "text",
                    "model_id": "alternate-fixture",
                    "label": "Alternate fixture",
                    "credits": 7,
                    "enabled": True,
                },
            ]
        ),
    )


def test_choice_uses_server_price_and_selected_provider_model(client, monkeypatch):
    options(monkeypatch)
    configure(monkeypatch)
    monkeypatch.setattr(
        providers, "discover", lambda: [{"name": "models/alternate-fixture"}]
    )
    calls = []

    def generate(studio, model_id, prompt, params):
        calls.append(model_id)
        return b"Explicit provider fixture result", "text/plain"

    monkeypatch.setattr(providers, "generate", generate)
    user, headers = register(client)
    fund(user["id"], 20)
    body = {**job_request(credits=7), "model_id": "alternate-fixture"}
    rejected = client.post(
        "/v1/jobs", headers=headers, json={**body, "confirmed_credits": 0}
    )
    assert rejected.status_code == 409 and rejected.json()["detail"] == "PRICE_CHANGED"
    accepted = client.post("/v1/jobs", headers=headers, json=body)
    assert accepted.status_code == 202
    assert accepted.json()["params"]["model_id"] == "alternate-fixture"
    assert worker.run_once()
    assert calls == ["alternate-fixture"]
    assert client.get("/v1/wallet", headers=headers).json()["balance"] == 13
    replay = client.post("/v1/jobs", headers=headers, json=body)
    assert replay.status_code == 202 and replay.json()["id"] == accepted.json()["id"]
    changed = client.post(
        "/v1/jobs", headers=headers, json={**body, "model_id": "test-fixture"}
    )
    assert (
        changed.status_code == 409
        and changed.json()["detail"] == "IDEMPOTENCY_CONFLICT"
    )


def test_unknown_and_cross_studio_model_choices_never_call_provider(
    client, monkeypatch
):
    options(monkeypatch)
    configure(monkeypatch)
    monkeypatch.setattr(
        providers,
        "discover",
        lambda: (_ for _ in ()).throw(
            AssertionError("Unapproved model triggered discovery")
        ),
    )
    _, headers = register(client)
    for model in ["not-approved", "alternate-fixture"]:
        body = {**job_request(studio="image", credits=0), "model_id": model}
        r = client.post("/v1/jobs", headers=headers, json=body)
        assert r.status_code == 409 and r.json()["detail"] == "MODEL_NOT_APPROVED"
    assert client.get("/v1/jobs", headers=headers).json() == []


def test_choices_can_be_browsed_while_generation_is_paused(client, monkeypatch):
    options(monkeypatch)
    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "0")
    result = next(m for m in client.get("/v1/models").json() if m["studio"] == "text")
    assert result["options"][0]["model_id"] == "alternate-fixture"
    assert not result["options"][0]["available"]
    assert result["options"][0]["credits"] == 7


def test_disabling_studio_also_disables_its_alternative_models(client, monkeypatch):
    options(monkeypatch)
    configure(monkeypatch)
    with Session.begin() as db:
        db.get(Model, "text").enabled = False
    _, headers = register(client)
    body = {**job_request(credits=7), "model_id": "alternate-fixture"}
    result = client.post("/v1/jobs", headers=headers, json=body)
    assert result.status_code == 409 and result.json()["detail"] == "MODEL_NOT_APPROVED"
