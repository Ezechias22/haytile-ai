"""Password reset over a configured SMTP transport. Never return reset tokens."""

import os
import secrets
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from .db import LoginSession, PasswordReset, Session, User, now
from .main import aware, fail, limit
from .security import hash_token, password_hash

router = APIRouter()


class ResetRequest(BaseModel):
    email: str = Field(max_length=254)


class ResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=200)
    password: str = Field(min_length=12, max_length=200)


@router.post("/v1/auth/password-reset")
def request_reset(body: ResetRequest, request: Request):
    limit("reset:" + request.client.host, 5, 900)
    host = os.environ.get("SMTP_HOST")
    sender = os.environ.get("SMTP_FROM")
    if not host or not sender:
        fail("EMAIL_DELIVERY_NOT_CONFIGURED", 503)
    with Session() as db:
        user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user:
        raw = secrets.token_urlsafe(32)
        with Session.begin() as db:
            db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
            db.add(
                PasswordReset(
                    token_hash=hash_token(raw),
                    user_id=user.id,
                    expires_at=now() + timedelta(minutes=20),
                )
            )
        message = EmailMessage()
        message["From"] = sender
        message["To"] = user.email
        message["Subject"] = "HAYTILE AI — Password reset"
        origin = os.environ.get("HAYTILE_PUBLIC_ORIGIN", "http://localhost:3000")
        message.set_content(
            "Reset your password within 20 minutes:\n"
            + origin
            + "/?reset="
            + raw
            + "\nIgnore this email if you did not request it."
        )
        try:
            with smtplib.SMTP(
                host, int(os.environ.get("SMTP_PORT", "587")), timeout=15
            ) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if os.environ.get("SMTP_USER"):
                    smtp.login(
                        os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", "")
                    )
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            fail("EMAIL_DELIVERY_FAILED", 503)
    return {"ok": True}


@router.post("/v1/auth/password-reset/confirm")
def confirm_reset(body: ResetConfirm, request: Request):
    limit("reset-confirm:" + request.client.host, 10, 900)
    with Session.begin() as db:
        reset = db.scalar(
            select(PasswordReset)
            .where(PasswordReset.token_hash == hash_token(body.token))
            .with_for_update()
        )
        if not reset or aware(reset.expires_at) <= now():
            fail("RESET_INVALID_OR_EXPIRED")
        user = db.scalar(select(User).where(User.id == reset.user_id).with_for_update())
        if not user:
            fail("RESET_INVALID_OR_EXPIRED")
        user.password = password_hash(body.password)
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        db.delete(reset)
    return {"ok": True}
