import pytest

from haytile import providers, worker

from .conftest import register
from .test_core import configure, fund, job_request


@pytest.mark.parametrize("code", ["PROVIDER_CONTENT_REJECTED", "PROVIDER_REFUSED_OR_EMPTY"])
def test_rejected_music_does_not_retry_or_reserve_again(client, monkeypatch, code):
    configure(monkeypatch, "music", credits=12)
    user, auth = register(client)
    fund(user["id"], 100)
    calls = []

    def reject(*args, **kwargs):
        calls.append(1)
        raise providers.ProviderError(code, "Input blocked: The prompt could not be processed.")

    monkeypatch.setattr(providers, "generate", reject)
    created = client.post(
        "/v1/jobs",
        headers=auth,
        json=job_request("music", 12, prompt="An educational song for peace"),
    ).json()
    assert client.get("/v1/wallet", headers=auth).json()["reserved"] == 12
    assert worker.run_once()
    failed = client.get("/v1/jobs/" + created["id"], headers=auth).json()
    assert failed["retry_mode"] == "blocked" and failed["error"] == code
    assert failed["params"]["provider_message"].startswith("Input blocked")
    before = client.get("/v1/wallet", headers=auth).json()
    assert before["balance"] == 100 and before["reserved"] == 0
    # Both ordinary retry and an explicit new_request flag must leave this paid job unchanged.
    for body in ({}, {"new_request": True}):
        result = client.post("/v1/jobs/" + created["id"] + "/retry", headers=auth, json=body)
        assert result.status_code == 409 and result.json()["detail"] == code
    assert client.get("/v1/jobs/" + created["id"], headers=auth).json() == failed
    assert client.get("/v1/wallet", headers=auth).json() == before
    assert not worker.run_once() and calls == [1]
