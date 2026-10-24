from .conftest import register
from .test_core import configure, job_request
from haytile import main


def test_free_beta_reports_temporary_storage(client, monkeypatch):
    monkeypatch.setattr(main, "FREE_BETA", True)
    config = client.get("/v1/runtime").json()
    assert config["free_beta"] is True and config["temporary_storage"] is True


def test_free_beta_disables_provider_work_without_postgres(client, monkeypatch):
    configure(monkeypatch)
    _, headers = register(client)
    monkeypatch.setattr(main, "FREE_BETA", True)
    # Simulates the isolated temporary deployment while keeping the test DB itself PostgreSQL.
    monkeypatch.setattr(main.engine.dialect, "name", "sqlite")
    assert (
        client.post("/v1/jobs", json=job_request(), headers=headers).status_code == 503
    )
    assert not any(m["available"] for m in client.get("/v1/models").json())
