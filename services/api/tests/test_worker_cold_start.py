"""Run a real first job in a fresh worker process, without pre-importing FastAPI."""

import os
import subprocess
import sys
import textwrap

from haytile import providers, worker
from haytile.db import Job, Session

from .conftest import register
from .test_core import configure, job_request


def test_first_chat_runs_in_a_fresh_standalone_worker(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": "sqlite:///" + str(tmp_path / "projection.db"),
            "HAYTILE_DATA_DIR": str(tmp_path / "data"),
            "HAYTILE_ACCOUNT_PROVIDER": "sql",
            "STORAGE_PROVIDER": "local",
            "HAYTILE_GENERATION_ENABLED": "1",
            "HAYTILE_WORKER_ENABLED": "1",
            "HAYTILE_GEMINI_API_KEY": "offline-cold-worker-key",
            "PYTHONPATH": os.path.abspath("services/api"),
        }
    )
    code = textwrap.dedent("""
        import sys
        from haytile import worker,providers
        from haytile.db import Base,engine,Session,User,Job,Asset
        from sqlalchemy import select
        assert 'haytile.main' not in sys.modules
        Base.metadata.create_all(engine)
        with Session.begin() as db:
            user=User(email='cold-worker@example.test',password='offline',name='Cold worker',locale='en',balance=0)
            db.add(user);db.flush()
            job=Job(user_id=user.id,studio='text',title='First request',prompt='Hello',credits=0,idempotency_key='cold-worker-request',params={'model_id':'cold-worker-model','chat_contents':[],'input_params':{'chat':True,'conversation_id':'cold-worker-conversation'}})
            db.add(job);db.flush();identifier=job.id
        calls=[]
        def transport(method,path,payload=None,**kwargs):
            assert method=='POST' and path.endswith(':generateContent')
            calls.append(path)
            return {'candidates':[{'content':{'parts':[{'text':'Standalone worker reply.'}]}}]}
        providers.request=transport
        assert worker.run_once()
        with Session() as db:
            job=db.get(Job,identifier)
            assert job.status=='completed', (job.status,job.error,job.params.get('failure_exception'))
            assert db.scalar(select(Asset).where(Asset.job_id==identifier)).text=='Standalone worker reply.'
        assert len(calls)==1
        assert 'haytile.main' not in sys.modules, 'Worker must not import API routes to read location'
    """)
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def test_preparation_import_failure_and_legacy_retry_never_duplicate_provider_call(
    client, monkeypatch
):
    from haytile import location_state

    configure(monkeypatch, "text")
    _, auth = register(client)
    calls = []

    def transport(*args, **kwargs):
        calls.append(True)
        return {
            "candidates": [
                {"content": {"parts": [{"text": "Reply after fixing worker initialization."}]}}
            ]
        }

    monkeypatch.setattr(providers, "request", transport)
    original = location_state.preference

    def broken(*args, **kwargs):
        raise ImportError("Offline initialization regression")

    monkeypatch.setattr(location_state, "preference", broken)
    body = {
        **job_request("text", 0),
        "params": {"chat": True, "conversation_id": "preparation-retry-conversation"},
    }
    response = client.post("/v1/jobs", headers=auth, json=body)
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    assert worker.run_once()
    failed = client.get("/v1/jobs/" + identifier, headers=auth).json()
    assert failed["error"] == "WORKER_PREPARATION_FAILED"
    assert failed["retry_mode"] == "retry" and calls == []
    assert failed["params"]["failure_phase"] == "preparing"
    # Existing affected jobs retain their original error for audit, but are safely retryable.
    with Session.begin() as db:
        db.get(Job, identifier).error = "WORKER_INTERRUPTED_RECONCILE"
        db.get(Job, identifier).attempt = 3
    assert client.get("/v1/jobs/" + identifier, headers=auth).json()["retry_mode"] == "retry"
    monkeypatch.setattr(location_state, "preference", original)
    assert client.post("/v1/jobs/" + identifier + "/retry", headers=auth).status_code == 200
    assert worker.run_once()
    assert client.get("/v1/jobs/" + identifier, headers=auth).json()["status"] == "completed"
    assert len(calls) == 1
