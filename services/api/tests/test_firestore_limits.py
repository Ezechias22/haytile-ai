from datetime import datetime, timedelta, timezone

import httpx
import pytest

from haytile import firestore_limits


def test_concurrent_counter_conflict_is_reread_and_never_over_admits(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "fixture-project")
    monkeypatch.setenv("FIREBASE_DATABASE_ID", "default")
    calls = []
    responses = iter(
        [
            httpx.Response(404),
            httpx.Response(409, json={"error": {"status": "ALREADY_EXISTS"}}),
            httpx.Response(
                200,
                json={
                    "updateTime": "version-two",
                    "fields": {
                        "count": {"integerValue": "1"},
                        "reset_at": {
                            "timestampValue": (
                                datetime.now(timezone.utc) + timedelta(minutes=1)
                            ).isoformat()
                        },
                    },
                },
            ),
        ]
    )

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return next(responses)

    monkeypatch.setattr(firestore_limits, "request", request)
    with pytest.raises(firestore_limits.LimitExceeded):
        firestore_limits.consume("private-user-fixture", 1, 60)
    assert [x[0] for x in calls] == ["GET", "PATCH", "GET"]
    assert "private-user-fixture" not in calls[0][1]
    assert "/databases/default/" in calls[0][1]
    assert calls[1][2]["params"] == {"currentDocument.exists": "false"}
    assert set(calls[1][2]["json"]["fields"]) == {"count", "reset_at"}


def test_firestore_outage_fails_closed_without_local_quota_fallback(
    client, monkeypatch
):
    monkeypatch.setenv("HAYTILE_RATE_LIMIT_PROVIDER", "firestore")

    def unavailable(*args):
        raise firestore_limits.LimitUnavailable()

    monkeypatch.setattr(firestore_limits, "consume", unavailable)
    r = client.post(
        "/v1/auth/register",
        json={
            "email": "blocked@example.test",
            "password": "long-password-for-fixture",
            "name": "Blocked",
            "locale": "ht",
        },
    )
    assert r.status_code == 503 and r.json()["detail"] == "RATE_LIMIT_UNAVAILABLE"
