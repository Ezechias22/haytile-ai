import os
import tempfile

# A dedicated PostgreSQL test DB exercises locking and actual relational constraints.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://haytile@127.0.0.1:5432/haytile_test"
)
os.environ["HAYTILE_DATA_DIR"] = tempfile.mkdtemp(prefix="haytile-tests-")
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from haytile.db import Base, engine, Session
from haytile.main import app


@pytest.fixture(autouse=True)
def clean_database():
    if not (
        str(engine.url).endswith("/haytile_test") or engine.dialect.name == "sqlite"
    ):
        raise RuntimeError(
            "Refusing to run destructive tests against a non-test database."
        )
    Base.metadata.create_all(engine)
    with Session.begin() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(delete(table))
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register(client, email="creator@example.test"):
    result = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "Long-test-password-123",
            "name": "Creator",
            "locale": "ht",
        },
        headers={"Origin": "http://localhost:3000"},
    )
    assert result.status_code == 201, result.text
    body = result.json()
    return body["user"], {"Authorization": "Bearer " + body["token"]}
