from datetime import timedelta
from unittest.mock import MagicMock
from haytile.db import Session, PasswordReset, now
from haytile.security import hash_token
from .conftest import register


def test_reset_requires_email_delivery_configuration(client):
    result = client.post(
        "/v1/auth/password-reset", json={"email": "anyone@example.test"}
    )
    assert result.status_code == 503


def test_one_time_reset_revokes_sessions(client):
    user, h = register(client)
    raw = "test-reset-token-long-enough-to-pass-validation"
    with Session.begin() as db:
        db.add(
            PasswordReset(
                token_hash=hash_token(raw),
                user_id=user["id"],
                expires_at=now() + timedelta(minutes=20),
            )
        )
    payload = {"token": raw, "password": "New-password-valid-123"}
    headers = {"Origin": "http://localhost:3000"}
    assert (
        client.post(
            "/v1/auth/password-reset/confirm", json=payload, headers=headers
        ).status_code
        == 200
    )
    assert client.get("/v1/me", headers=h).status_code == 401
    assert (
        client.post(
            "/v1/auth/password-reset/confirm", json=payload, headers=headers
        ).status_code
        == 400
    )
    result = client.post(
        "/v1/auth/login",
        json={"email": user["email"], "password": payload["password"]},
        headers=headers,
    )
    assert result.status_code == 200
    assert "password" not in result.json()["user"]


def test_smtp_reset_uses_verified_tls_and_never_returns_token(client, monkeypatch):
    import ssl
    import smtplib
    from unittest.mock import MagicMock

    user, h = register(client)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "support@example.test")
    transport = MagicMock()
    smtp = MagicMock()
    smtp.__enter__.return_value = transport
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: smtp)
    response = client.post(
        "/v1/auth/password-reset", json={"email": user["email"]}, headers=h
    )
    assert response.status_code == 200 and response.json() == {"ok": True}
    context = transport.starttls.call_args.kwargs["context"]
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    message = transport.send_message.call_args.args[0]
    assert "?reset=" in message.get_content()
    assert "reset=" not in response.text
