import json
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import Response as RawResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from starlette.background import BackgroundTask

from . import accounts, pricing, providers, records, storage, wallets
from .availability import generation_enabled, worker_enabled
from .db import (
    Asset,
    Audit,
    Job,
    Ledger,
    LoginSession,
    Membership,
    Model,
    PasswordReset,
    Project,
    RateLimit,
    Session,
    User,
    engine,
    now,
)
from .downloads import byte_range, chunks
from .media import MAX_BYTES, inspect_media
from .model_choices import PRICING, configured_choices, select_choice
from .runtime_checks import configuration_checks, require_durable_runtime
from .security import (
    hash_token,
    password_hash,
    sign_asset,
    valid_signature,
    verify_password,
)
from .titles import suggest_title
from .trials import lock_sqlite_write, trial_enabled, trial_limit_code
from .voice_choices import VOCALS, VOICE_OPTIONS, VOICES

STUDIOS = ("image", "text", "voice", "music", "video", "minidrama")
LOCALES = ("ht", "en", "fr", "pt-BR", "es", "ar", "zh-Hans", "id", "sw")
FREE_BETA = os.environ.get("HAYTILE_FREE_BETA") == "1"
COOKIE = "haytile_session"
PRODUCTION = os.environ.get("HAYTILE_ENV") == "production"


def aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def fail(code, status=400):
    raise HTTPException(status, detail=code)


def limit(key, maximum, seconds):
    if os.environ.get("HAYTILE_RATE_LIMIT_PROVIDER") == "firestore":
        from . import firestore_limits

        try:
            firestore_limits.consume(key, maximum, seconds)
        except firestore_limits.LimitExceeded:
            fail("RATE_LIMIT", 429)
        except firestore_limits.LimitUnavailable:
            fail("RATE_LIMIT_UNAVAILABLE", 503)
        return
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sq_insert

    with Session.begin() as db:
        lock_sqlite_write(db)
        insert = pg_insert if engine.dialect.name == "postgresql" else sq_insert
        db.execute(
            insert(RateLimit)
            .values(key=key, count=0, reset_at=now() + timedelta(seconds=seconds))
            .on_conflict_do_nothing()
        )
        row = db.scalar(select(RateLimit).where(RateLimit.key == key).with_for_update())
        if aware(row.reset_at) <= now():
            row.count = 0
            row.reset_at = now() + timedelta(seconds=seconds)
        if row.count >= maximum:
            fail("RATE_LIMIT", 429)
        row.count += 1


def current(request: Request):
    bearer = request.headers.get("authorization", "")
    token = bearer[7:] if bearer.startswith("Bearer ") else request.cookies.get(COOKIE, "")
    if not token:
        fail("AUTH_REQUIRED", 401)
    if accounts.enabled():
        data = accounts.resolve(hash_token(token))
        if not data:
            fail("SESSION_EXPIRED", 401)
        projected = accounts.hydrate(data)
        records.sync_user(projected.id)
        with Session() as db:
            return db.get(User, projected.id)
    with Session() as db:
        session = db.get(LoginSession, hash_token(token))
        if not session or aware(session.expires_at) <= now():
            fail("SESSION_EXPIRED", 401)
        user = db.get(User, session.user_id)
        if not user:
            fail("AUTH_REQUIRED", 401)
        return user


def admin(user=Depends(current)):
    if user.role != "admin":
        fail("ADMIN_REQUIRED", 403)
    return user


def user_json(u):
    result = {
        k: getattr(u, k) for k in ("id", "email", "name", "locale", "role", "balance", "reserved")
    }
    if wallets.enabled():
        result.update(wallets.snapshot(u.id))
        return result
    with Session() as db:
        membership = db.get(Membership, u.id)
        result["plan"] = (
            membership.plan if membership and aware(membership.expires_at) > now() else "free"
        )
        result["plan_expires_at"] = membership.expires_at if membership else None
    return result


def asset_json(a):
    return {
        k: getattr(a, k) for k in ("id", "title", "mime", "size", "text", "job_id", "created_at")
    }


def job_json(j):
    return {
        k: getattr(j, k)
        for k in (
            "id",
            "title",
            "studio",
            "prompt",
            "params",
            "status",
            "progress",
            "error",
            "credits",
            "attempt",
            "created_at",
            "updated_at",
        )
    }


def session_response(user, response, account=None):
    raw = secrets.token_urlsafe(32)
    if accounts.enabled():
        if not account or not accounts.session(account, hash_token(raw), now() + timedelta(days=7)):
            fail("LOGIN_INVALID", 401)
    else:
        with Session.begin() as db:
            db.add(
                LoginSession(
                    token_hash=hash_token(raw),
                    user_id=user.id,
                    expires_at=now() + timedelta(days=7),
                )
            )
    response.set_cookie(
        COOKIE,
        raw,
        max_age=604800,
        httponly=True,
        secure=PRODUCTION,
        samesite="strict",
        path="/",
    )
    return {"user": user_json(user), "token": raw}


@asynccontextmanager
async def lifespan(app):
    if os.environ.get("HAYTILE_ACCOUNT_PROVIDER", "sql") not in ("sql", "firestore"):
        raise RuntimeError("Invalid account provider")
    require_durable_runtime(engine.dialect.name)
    storage.validate_configuration()
    with engine.connect() as connection:
        connection.execute(select(1))
    if accounts.enabled():
        accounts.read("accounts", "_readiness")
        if os.environ.get("HAYTILE_ACCOUNT_IMPORT_LOCAL") == "1":
            accounts.migrate_local()
    yield


app = FastAPI(title="HAYTILE AI", version="0.1.0", lifespan=lifespan)


@app.exception_handler(accounts.Unavailable)
async def account_store_unavailable(request, exc):
    return RawResponse(
        json.dumps({"detail": "ACCOUNT_STORE_UNAVAILABLE"}),
        status_code=503,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(records.DuplicateJob)
async def duplicate_job(request, exc):
    stored = accounts.read("jobs", exc.job_id)
    if not stored or stored[0].get("user_id") != exc.user_id:
        return RawResponse(
            '{"detail":"ACCOUNT_STORE_UNAVAILABLE"}',
            status_code=503,
            media_type="application/json",
        )
    from fastapi.encoders import jsonable_encoder

    return RawResponse(
        json.dumps(jsonable_encoder(job_json(Job(**records.unpack(stored[0]))))),
        status_code=202,
        media_type="application/json",
    )


@app.middleware("http")
async def security_headers(request, call_next):
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and request.cookies.get(COOKIE)
        and not request.headers.get("authorization", "").startswith("Bearer ")
    ):
        if request.headers.get("origin") != os.environ.get(
            "HAYTILE_PUBLIC_ORIGIN", "http://localhost:3000"
        ):
            return RawResponse(
                json.dumps({"detail": "ORIGIN_INVALID"}),
                status_code=403,
                media_type="application/json",
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/v1/runtime")
def runtime_settings():
    with Session() as db:
        configured = bool(os.environ.get("HAYTILE_GEMINI_API_KEY")) and bool(
            db.scalar(select(Model.studio).where(Model.enabled.is_(True)).limit(1))
        )
    return {
        "api_release": "personal-chat-v8",
        "source_revision": os.environ.get("RENDER_GIT_COMMIT", ""),
        "credit_store": "firestore" if wallets.enabled() else "sql",
        "metadata_store": "firestore" if records.enabled() else "sql",
        "images_paid": pricing.paid_images(),
        "chat_available": configured and generation_enabled() and worker_enabled(),
        "free_beta": FREE_BETA,
        "temporary_storage": FREE_BETA and not storage.is_remote(),
        "temporary_database": engine.dialect.name == "sqlite",
        "account_store": "firestore" if accounts.enabled() else "sql",
        "temporary_accounts": engine.dialect.name == "sqlite" and not accounts.enabled(),
        "media_delivery": "firebase_direct" if storage.backend() == "firebase" else "api_stream",
        "rate_limit_store": os.environ.get("HAYTILE_RATE_LIMIT_PROVIDER", "local"),
        "generation_paused": not generation_enabled(),
        "background_processing_enabled": worker_enabled(),
        "provider_generation_disabled": not generation_enabled()
        or not worker_enabled()
        or not configured
        or (FREE_BETA and engine.dialect.name != "postgresql" and not trial_enabled()),
        "trial_ai": trial_enabled(),
        "trial_max_episode_seconds": int(os.environ.get("HAYTILE_TRIAL_MAX_EPISODE_SECONDS", "180"))
        if trial_enabled()
        else 180,
        "trial_max_video_seconds": int(os.environ.get("HAYTILE_TRIAL_MAX_VIDEO_SECONDS", "180"))
        if trial_enabled()
        else 180,
    }


@app.get("/v1/health")
def health():
    with Session() as db:
        db.execute(select(1))
    return {
        "status": "ok",
        "database": engine.dialect.name,
        "storage": storage.backend() if storage.is_remote() else "private-local",
    }


class Register(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=200)
    name: str = Field(min_length=1, max_length=80)
    locale: str = "ht"


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


@app.post("/v1/auth/register", status_code=201)
def register(body: Register, request: Request, response: Response):
    limit("register:" + request.client.host, 10, 3600)
    if not body.name.strip():
        fail("NAME_INVALID")
    email = body.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        fail("EMAIL_INVALID")
    if body.locale not in LOCALES:
        fail("LOCALE_INVALID")
    if accounts.enabled():
        try:
            data = accounts.create(
                email, password_hash(body.password), body.name.strip(), body.locale
            )
        except accounts.DuplicateEmail:
            fail("EMAIL_UNAVAILABLE", 409)
        return session_response(accounts.hydrate(data), response, account=data)
    user = User(
        email=email,
        name=body.name.strip(),
        password=password_hash(body.password),
        locale=body.locale,
    )
    try:
        with Session.begin() as db:
            db.add(user)
            db.flush()
    except IntegrityError:
        fail("EMAIL_UNAVAILABLE", 409)
    return session_response(user, response)


@app.post("/v1/auth/login")
def login(body: Login, request: Request, response: Response):
    limit("login:" + request.client.host, 30, 900)
    if accounts.enabled():
        data = accounts.by_email(body.email.strip().lower())
        if not data:
            password_hash(body.password)
            fail("LOGIN_INVALID", 401)
        if not verify_password(body.password, data["password"]):
            fail("LOGIN_INVALID", 401)
        return session_response(accounts.hydrate(data), response, account=data)
    with Session() as db:
        user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user:
        password_hash(body.password)
        fail("LOGIN_INVALID", 401)
    if not verify_password(body.password, user.password):
        fail("LOGIN_INVALID", 401)
    return session_response(user, response)


@app.post("/v1/auth/logout")
def logout(request: Request, response: Response, user=Depends(current)):
    bearer = request.headers.get("authorization", "")
    raw = bearer[7:] if bearer.startswith("Bearer ") else request.cookies.get(COOKIE, "")
    if accounts.enabled():
        accounts.logout(hash_token(raw))
    else:
        with Session.begin() as db:
            db.execute(delete(LoginSession).where(LoginSession.token_hash == hash_token(raw)))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/v1/me")
def me(user=Depends(current)):
    return user_json(user)


class Preferences(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    locale: str


@app.patch("/v1/me")
def preferences(body: Preferences, user=Depends(current)):
    if not body.name.strip():
        fail("NAME_INVALID")
    if body.locale not in LOCALES:
        fail("LOCALE_INVALID")
    if accounts.enabled():
        data = accounts.change(user.id, {"name": body.name.strip(), "locale": body.locale})
        return user_json(accounts.hydrate(data))
    with Session.begin() as db:
        row = db.get(User, user.id)
        row.name = body.name.strip()
        row.locale = body.locale
        return user_json(row)


class DeleteAccount(BaseModel):
    password: str


@app.delete("/v1/me")
def delete_account(body: DeleteAccount, response: Response, user=Depends(current)):
    if not verify_password(body.password, user.password):
        fail("LOGIN_INVALID", 401)
    from .billing import cancel_for_user

    cancel_for_user(user.id)
    with Session() as db:
        cleanup_keys = [
            key
            for row in db.scalars(
                select(Project).where(
                    Project.user_id == user.id,
                    Project.document["kind"].as_string() == "chat_cleanup",
                )
            )
            for key in row.document.get("keys", [])
        ]
    for key in cleanup_keys:
        storage.delete(key)
    if accounts.enabled():
        accounts.remove(user.id)
        records.purge_user(user.id)
    with Session.begin() as db:
        row = db.scalar(select(User).where(User.id == user.id).with_for_update())
        for key in db.scalars(select(Asset.key).where(Asset.user_id == user.id)):
            storage.delete(key)
        for table in (Asset, Ledger, Job, LoginSession, PasswordReset, Project):
            db.execute(delete(table).where(table.user_id == user.id))
        db.delete(row)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/v1/me/export")
def export_account(user=Depends(current)):
    with Session() as db:
        return {
            "profile": user_json(user),
            "projects": [
                {
                    "id": p.id,
                    "title": p.title,
                    "document": p.document,
                    "version": p.version,
                }
                for p in db.scalars(select(Project).where(Project.user_id == user.id))
            ],
            "jobs": [job_json(x) for x in db.scalars(select(Job).where(Job.user_id == user.id))],
            "assets": [
                asset_json(x) for x in db.scalars(select(Asset).where(Asset.user_id == user.id))
            ],
            "ledger": wallets.history(user.id)
            if wallets.enabled()
            else [
                {"amount": x.amount, "kind": x.kind, "created_at": x.created_at}
                for x in db.scalars(select(Ledger).where(Ledger.user_id == user.id))
            ],
        }


@app.get("/v1/models")
def models():
    with Session() as db:
        rows = {m.studio: m for m in db.scalars(select(Model))}
        choices = {s: configured_choices(db, s) for s in STUDIOS}
    present = (
        generation_enabled()
        and worker_enabled()
        and bool(os.environ.get("HAYTILE_GEMINI_API_KEY"))
        and not (FREE_BETA and engine.dialect.name != "postgresql" and not trial_enabled())
    )
    return [
        {
            "studio": s,
            "available": bool(
                present
                and rows.get(s)
                and any(c.model_id == rows[s].model_id and c.enabled for c in choices[s])
            ),
            "episode_available": bool(
                present
                and rows.get(s)
                and rows[s].enabled
                and all(rows.get(kind) and rows[kind].enabled for kind in ("image", "video"))
            )
            if s == "minidrama"
            else False,
            "model_id": rows[s].model_id
            if s in rows
            else (choices[s][0].model_id if choices[s] else None),
            "options": [
                {
                    "model_id": choice.model_id,
                    "label": choice.label,
                    "credits": choice.credits,
                    "available": bool(present and choice.enabled),
                    "episode_available": bool(
                        present
                        and choice.enabled
                        and s == "minidrama"
                        and all(
                            rows.get(kind) and rows[kind].enabled for kind in ("image", "video")
                        )
                    ),
                    "pricing_url": PRICING,
                    "unavailable_reason": choice.unavailable_reason,
                    "terms_url": choice.terms_url,
                }
                for choice in choices[s]
            ],
            "credits": next(
                (c.credits for c in choices[s] if s in rows and c.model_id == rows[s].model_id),
                0,
            ),
            "terms_url": rows[s].terms_url if s in rows else None,
            "reason": "AI_SERVICE_PAUSED"
            if not generation_enabled() or not worker_enabled()
            else None
            if present and rows.get(s) and rows[s].enabled
            else "PROVIDER_SETUP_REQUIRED",
        }
        for s in STUDIOS
    ]


@app.get("/v1/voices")
def voice_options():
    return {
        "voices": list(VOICES),
        "voice_options": list(VOICE_OPTIONS),
        "source": "https://ai.google.dev/gemini-api/docs/speech-generation#voices",
    }


class Generate(BaseModel):
    studio: Literal["image", "text", "voice", "music", "video", "minidrama"]
    title: str = Field(default="", max_length=120)
    prompt: str = Field(min_length=1, max_length=12000)
    idempotency_key: str = Field(min_length=8, max_length=80)
    params: dict = Field(default_factory=dict)
    confirmed_credits: int = Field(ge=0)
    model_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,120}$")


class QuoteRequest(BaseModel):
    studio: Literal["image", "text", "voice", "music", "video", "minidrama"]
    model_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,120}$")
    prompt: str = Field(min_length=1, max_length=12000)
    params: dict = Field(default_factory=dict)


@app.post("/v1/quotes")
def quote_generation(body: QuoteRequest, user=Depends(current)):
    if len(json.dumps(body.params)) > 20000 or any(str(k).startswith("_") for k in body.params):
        fail("PARAMS_INVALID")
    if body.studio in ("video", "minidrama") and "duration" in body.params:
        duration = body.params["duration"]
        if type(duration) is not int or not 8 <= duration <= 180:
            fail("VIDEO_DURATION_INVALID")
    limit("quotes:" + user.id, 120, 60)
    with Session() as db:
        model = (
            select_choice(db, body.studio, body.model_id)
            if body.model_id
            else db.get(Model, body.studio)
        )
        if not model or not model.enabled:
            fail("MODEL_NOT_APPROVED", 409)
        config = None
        video_credits = 0
        if body.studio == "minidrama" and body.params.get("mode") == "episode":
            video = (
                select_choice(db, "video", body.params["video_model_id"])
                if body.params.get("video_model_id")
                else db.get(Model, "video")
            )
            image = db.get(Model, "image")
            if not video or not video.enabled or not image or not image.enabled:
                fail("PROVIDER_SETUP_REQUIRED", 409)
            config = {
                "text": model.model_id,
                "image": image.model_id,
                "video": video.model_id,
            }
            video_credits = video.credits
        return pricing.quote(
            body.studio,
            model.model_id,
            body.prompt,
            body.params,
            model.credits,
            render_config=config,
            video_credits=video_credits,
        )


@app.post("/v1/jobs", status_code=202)
def generate(body: Generate, user=Depends(current)):
    if not generation_enabled() or not worker_enabled():
        fail("AI_SERVICE_PAUSED", 503)
    if FREE_BETA and engine.dialect.name != "postgresql" and not trial_enabled():
        fail("FREE_BETA_AI_DISABLED", 503)
    if not body.prompt.strip():
        fail("CONTENT_REQUIRED")
    resolved_title = body.title.strip() or suggest_title(body.prompt, body.studio.capitalize())
    if any(str(key).startswith("_") for key in body.params):
        fail("PARAMS_INVALID")
    if "model_id" in body.params:
        fail("MODEL_CHOICE_INVALID")
    selected = None
    if body.model_id:
        with Session() as db:
            selected = select_choice(db, body.studio, body.model_id)
        if not selected or not selected.enabled:
            fail("MODEL_NOT_APPROVED", 409)
    if len(json.dumps(body.params)) > 20000:
        fail("PARAMS_TOO_LARGE")
    if body.params.get("aspect", "1:1") not in ("1:1", "16:9", "9:16", "4:3", "3:4"):
        fail("ASPECT_INVALID")
    if body.studio == "video":
        duration = body.params.get("duration", 8)
        if type(duration) is not int or not 8 <= duration <= 180:
            fail("VIDEO_DURATION_INVALID")
        if body.params.get("aspect", "16:9") not in ("16:9", "9:16"):
            fail("VIDEO_ASPECT_INVALID")
    episode = body.studio == "minidrama" and body.params.get("mode") == "episode"
    if episode:
        duration = body.params.get("duration", 16)
        if type(duration) is not int or not 8 <= duration <= 180:
            fail("VIDEO_DURATION_INVALID")
        if body.params.get("aspect", "16:9") not in ("16:9", "9:16"):
            fail("VIDEO_ASPECT_INVALID")
    if wallets.enabled() and wallets.snapshot(user.id).get("billing_hold"):
        fail("BILLING_REVIEW_REQUIRED", 403)
    if body.params.get("live_voice") is not None:
        fail("LIVE_PROTOCOL")
    if body.studio == "voice" and body.params.get("voice_name", "Kore") not in VOICES:
        fail("VOICE_INVALID")
    if body.studio == "music" and body.params.get("vocal_style", "auto") not in VOCALS:
        fail("VOCAL_STYLE_INVALID")
    if body.studio == "music" and body.params.get("preserve_lyrics"):
        fail("EXACT_LYRICS_VERIFICATION_PENDING", 409)
    is_chat = body.studio == "text" and body.params.get("chat") is True
    limit(
        "generation-chat-global" if is_chat else "generation-global",
        int(os.environ.get("HAYTILE_DAILY_CHAT_LIMIT", "50"))
        if is_chat
        else int(os.environ.get("HAYTILE_DAILY_JOB_LIMIT", "100")),
        86400,
    )
    if is_chat:
        limit("chat-daily:" + user.id, int(os.environ.get("HAYTILE_CHAT_PER_DAY", "20")), 86400)
    limit("generation:" + user.id, 30, 3600)
    if selected and selected.catalog_check:
        try:
            catalog = providers.discover()
        except providers.ProviderError as exc:
            fail(str(exc), 503)
        if not any(item["name"] == "models/" + selected.model_id for item in catalog):
            fail("MODEL_NOT_IN_ACCOUNT", 409)
    with Session.begin() as db:
        lock_sqlite_write(db)
        owner = db.scalar(select(User).where(User.id == user.id).with_for_update())
        old = db.scalar(
            select(Job).where(Job.user_id == user.id, Job.idempotency_key == body.idempotency_key)
        )
        if old:
            if (
                old.studio != body.studio
                or old.prompt != body.prompt
                or old.params.get("input_params") != body.params
                or old.params.get("requested_model_id") != body.model_id
            ):
                fail("IDEMPOTENCY_CONFLICT", 409)
            return job_json(old)
        if body.params.get("chat_audio") is not None:
            if body.studio != "voice" or body.params.get("chat_audio") is not True:
                fail("CHAT_INVALID")
            from .chat import validate_audio

            validate_audio(db, user.id, body.params, body.prompt)
        chat_contents = None
        if body.params.get("chat") is not None:
            if body.studio != "text" or body.params.get("chat") is not True:
                fail("CHAT_INVALID")
            from .chat import context

            chat_contents = context(db, user.id, body.params)
        model = (
            select_choice(db, body.studio, body.model_id)
            if body.model_id
            else db.get(Model, body.studio)
        )
        if not model or not model.enabled or not os.environ.get("HAYTILE_GEMINI_API_KEY"):
            fail("PROVIDER_SETUP_REQUIRED", 503)
        render_config = None
        if episode:
            image_model = db.get(Model, "image")
            video_model = (
                select_choice(db, "video", body.params["video_model_id"])
                if body.params.get("video_model_id")
                else db.get(Model, "video")
            )
            if (
                not image_model
                or not video_model
                or not image_model.enabled
                or not video_model.enabled
            ):
                fail("PROVIDER_SETUP_REQUIRED", 503)
            render_config = {
                "text": model.model_id,
                "image": image_model.model_id,
                "video": video_model.model_id,
            }
        quoted = pricing.quote(
            body.studio,
            model.model_id,
            body.prompt,
            body.params,
            model.credits,
            render_config=render_config,
            video_credits=video_model.credits if episode else 0,
        )
        credits = quoted["credits"]
        trial_error = trial_limit_code(db, user.id, body.studio, body.params, credits)
        if trial_error:
            fail(
                trial_error,
                409 if trial_error == "PERSISTENT_POSTGRES_REQUIRED" else 429,
            )
        if credits != body.confirmed_credits:
            fail("PRICE_CHANGED", 409)
        if owner.balance - owner.reserved < credits:
            fail("INSUFFICIENT_CREDITS", 402)
        pending = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.user_id == user.id,
                Job.status.in_(["queued", "processing", "quality_check"]),
            )
        )
        if pending >= 3:
            fail("TOO_MANY_JOBS", 429)
        if body.studio == "image":
            count = db.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.user_id == user.id,
                    Job.studio == "image",
                    Job.created_at >= now() - timedelta(days=1),
                )
            )
            if count >= int(os.environ.get("HAYTILE_FREE_IMAGES_PER_DAY", "8")):
                fail("FREE_IMAGE_LIMIT", 429)
        if body.params.get("reference_asset_id"):
            ref = db.get(Asset, body.params["reference_asset_id"])
            if not ref or ref.user_id != user.id or not ref.mime.startswith("image/"):
                fail("REFERENCE_INVALID")
        if body.params.get("voice_session_id"):
            if (
                body.studio != "voice"
                or body.params.get("chat_audio") is not True
                or body.model_id != body.params.get("session_model_id")
            ):
                fail("VOICE_SESSION_SETTINGS_CHANGED", 409)
            from .voice_budget import reserve

            reserve(db, user.id, body.params, credits, body.prompt)
        owner.reserved += credits
        job = Job(
            user_id=user.id,
            studio=body.studio,
            title=resolved_title,
            prompt=body.prompt,
            idempotency_key=body.idempotency_key,
            credits=credits,
            params={
                "input_params": body.params,
                "model_id": model.model_id,
                "requested_model_id": body.model_id,
                "provider": model.provider,
                "render_config": render_config,
                "pricing_quote": quoted,
                **({"chat_contents": chat_contents} if chat_contents is not None else {}),
            },
        )
        db.add(job)
        db.flush()
        if credits:
            db.add(
                Ledger(
                    user_id=user.id,
                    job_id=job.id,
                    amount=0,
                    kind="reserve",
                    dedup_key=job.id + ":reserve:1",
                )
            )
        result = job_json(job)
    wake_worker()
    return result


def wake_worker():
    if os.environ.get("REDIS_URL"):
        try:
            from redis import Redis

            Redis.from_url(os.environ["REDIS_URL"], socket_timeout=1).lpush("haytile:wake", "job")
        except Exception:
            pass


@app.get("/v1/jobs")
def jobs(user=Depends(current)):
    with Session() as db:
        return [
            job_json(j)
            for j in db.scalars(
                select(Job)
                .where(
                    Job.user_id == user.id,
                    Job.params["input_params"]["chat"].as_boolean().is_not(True),
                    Job.params["input_params"]["chat_audio"].as_boolean().is_not(True),
                )
                .order_by(Job.created_at.desc())
                .limit(100)
            )
        ]


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, user=Depends(current)):
    with Session() as db:
        job = db.scalar(select(Job).where(Job.id == job_id, Job.user_id == user.id))
        if not job:
            fail("NOT_FOUND", 404)
        return job_json(job)


@app.post("/v1/chat/welcome")
def chat_welcome(user=Depends(current)):
    """Claim the once-per-account introduction without an AI generation call."""
    with Session() as db:
        returning = (
            db.scalar(
                select(Job.id)
                .where(
                    Job.user_id == user.id,
                    Job.studio == "text",
                    Job.params["input_params"]["chat"].as_boolean().is_(True),
                )
                .limit(1)
            )
            is not None
        )
    if accounts.enabled():
        for _ in range(5):
            found = accounts.read("accounts", user.id)
            if not found:
                fail("ACCOUNT_UNAVAILABLE", 503)
            data, version = found
            if data.get("chat_introduced"):
                return {"introduce": False}
            try:
                accounts.commit(
                    [
                        accounts.update_write(
                            "accounts", user.id, {**data, "chat_introduced": True}, version=version
                        )
                    ]
                )
                return {"introduce": not returning}
            except accounts.Conflict:
                continue
        fail("ACCOUNT_UNAVAILABLE", 503)
    from uuid import NAMESPACE_URL, uuid5

    from sqlalchemy.exc import IntegrityError

    from .db import Project

    marker = str(uuid5(NAMESPACE_URL, "haytile:chat-welcome:" + user.id))
    try:
        with Session.begin() as db:
            if db.get(Project, marker):
                return {"introduce": False}
            db.add(
                Project(
                    id=marker,
                    user_id=user.id,
                    title="Chat welcome",
                    document={"kind": "chat_welcome"},
                )
            )
        return {"introduce": not returning}
    except IntegrityError:
        return {"introduce": False}


@app.get("/v1/chat/conversations")
def chat_conversations(user=Depends(current)):
    with Session() as db:
        rows = db.scalars(
            select(Job)
            .where(
                Job.user_id == user.id,
                Job.studio == "text",
                Job.params["input_params"]["chat"].as_boolean().is_(True),
            )
            .order_by(Job.created_at.desc())
            .limit(500)
        )
        result = {}
        for job in rows:
            cid = job.params["input_params"].get("conversation_id")
            if cid and cid not in result:
                result[cid] = {"id": cid, "title": job.title}
            elif cid:
                result[cid]["title"] = job.title
        return list(result.values())[:50]


@app.get("/v1/chat/conversations/{conversation_id}")
def chat_messages(conversation_id: str, user=Depends(current)):
    with Session() as db:
        rows = list(
            db.scalars(
                select(Job)
                .where(
                    Job.user_id == user.id,
                    Job.studio == "text",
                    Job.params["input_params"]["chat"].as_boolean().is_(True),
                    Job.params["input_params"]["conversation_id"].as_string() == conversation_id,
                )
                .order_by(Job.created_at.desc())
                .limit(100)
            )
        )
        rows.reverse()
        outputs = (
            {
                asset.job_id: asset.text
                for asset in db.scalars(
                    select(Asset).where(
                        Asset.user_id == user.id,
                        Asset.job_id.in_([j.id for j in rows]),
                        Asset.mime == "text/plain",
                    )
                )
            }
            if rows
            else {}
        )
        audio = {}
        for item in db.scalars(
            select(Job)
            .where(
                Job.user_id == user.id,
                Job.studio == "voice",
                Job.params["input_params"]["chat_audio"].as_boolean().is_(True),
                Job.params["input_params"]["conversation_id"].as_string() == conversation_id,
            )
            .order_by(Job.created_at.desc())
            .limit(100)
        ):
            audio.setdefault(item.params["input_params"].get("parent_message_id"), job_json(item))
        return [
            {
                **job_json(j),
                "reply": outputs.get(j.id) if j.status == "completed" else None,
                "audio": audio.get(j.id),
            }
            for j in rows
        ]


@app.post("/v1/jobs/{job_id}/retry")
def retry(job_id: str, user=Depends(current)):
    if wallets.enabled() and wallets.snapshot(user.id).get("billing_hold"):
        fail("BILLING_REVIEW_REQUIRED", 403)
    if not worker_enabled():
        fail("BACKGROUND_PROCESSING_PAUSED", 503)
    with Session.begin() as db:
        lock_sqlite_write(db)
        owner = db.scalar(select(User).where(User.id == user.id).with_for_update())
        job = db.scalar(
            select(Job).where(Job.id == job_id, Job.user_id == user.id).with_for_update()
        )
        if not job:
            fail("NOT_FOUND", 404)
        if job.studio != "assembly" and not generation_enabled():
            fail("AI_SERVICE_PAUSED", 503)
        if job.status != "failed":
            fail("JOB_NOT_FAILED", 409)
        if job.error == "WORKER_INTERRUPTED_RECONCILE":
            operation = job.params.get("remote_operation")
            can_resume = operation and (
                job.studio in ("music", "voice")
                or (
                    job.studio == "video"
                    and job.params.get("input_params", {}).get("duration", 8) <= 10
                )
            )
            if not can_resume:
                fail("MANUAL_RECONCILIATION_REQUIRED", 409)
            job.params = {**job.params, "resume_operation_id": operation["id"]}
        trial_error = trial_limit_code(
            db, user.id, job.studio, job.params.get("input_params", {}), job.credits
        )
        if trial_error:
            fail(trial_error, 429)
        if job.attempt >= 3:
            fail("RETRY_LIMIT", 409)
        if owner.balance - owner.reserved < job.credits:
            fail("INSUFFICIENT_CREDITS", 402)
        if job.params.get("input_params", {}).get("voice_session_id"):
            from .voice_budget import reserve

            reserve(db, user.id, job.params["input_params"], job.credits, job.prompt)
        owner.reserved += job.credits
        job.status = "queued"
        job.error = None
        job.progress = 0
        job.attempt += 1
        result = job_json(job)
    wake_worker()
    return result


def asset_ready(db, asset):
    if not asset or not asset.job_id:
        return bool(asset)
    job = db.get(Job, asset.job_id)
    return bool(job and (job.credits == 0 or job.status == "completed"))


@app.get("/v1/assets")
def assets(user=Depends(current)):
    with Session() as db:
        return [
            asset_json(a)
            for a in db.scalars(
                select(Asset)
                .where(Asset.user_id == user.id)
                .where(
                    Asset.job_id.is_(None)
                    | Asset.job_id.in_(
                        select(Job.id).where(
                            (Job.credits == 0) | (Job.status == "completed"),
                            Job.params["input_params"]["chat"].as_boolean().is_not(True),
                            Job.params["input_params"]["chat_audio"].as_boolean().is_not(True),
                        )
                    )
                )
                .order_by(Asset.created_at.desc())
                .limit(200)
            )
        ]


class SaveText(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=100000)


@app.post("/v1/assets/text", status_code=201)
def save_text(body: SaveText, user=Depends(current)):
    limit("save:" + user.id, 100, 3600)
    data = body.text.encode()
    key = storage.put(data, "text/plain")
    try:
        with Session.begin() as db:
            asset = Asset(
                user_id=user.id,
                title=body.title,
                mime="text/plain",
                key=key,
                size=len(data),
                text=body.text,
            )
            db.add(asset)
            db.flush()
            return asset_json(asset)
    except accounts.Unavailable:
        raise
    except Exception:
        storage.delete(key)
        raise


@app.post("/v1/assets/upload", status_code=201)
async def upload(file: UploadFile = File(...), user=Depends(current)):
    limit("upload:" + user.id, 30, 3600)
    data = await file.read(MAX_BYTES + 1)
    try:
        mime, text = inspect_media(data, file.content_type or "")
    except Exception:
        fail("FILE_INVALID_OR_TOO_LARGE")
    key = storage.put(data, mime)
    try:
        with Session.begin() as db:
            asset = Asset(
                user_id=user.id,
                title=(file.filename or "Upload")[:120],
                mime=mime,
                key=key,
                size=len(data),
                text=text,
            )
            db.add(asset)
            db.flush()
            return asset_json(asset)
    except accounts.Unavailable:
        raise
    except Exception:
        storage.delete(key)
        raise


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@app.patch("/v1/assets/{asset_id}")
def rename(asset_id: str, body: Rename, user=Depends(current)):
    title = body.title.strip()
    if not title:
        fail("CONTENT_REQUIRED")
    with Session.begin() as db:
        lock_sqlite_write(db)
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.user_id == user.id))
        if not asset:
            fail("NOT_FOUND", 404)
        previous_title = asset.title
        asset.title = title
        if asset.job_id:
            job = db.get(Job, asset.job_id)
            if (
                job
                and job.user_id == user.id
                and (
                    job.params.get("result_asset_id") == asset.id
                    or not job.params.get("result_asset_id")
                    and not previous_title.startswith(("[Reference] ", "[Scene] "))
                )
            ):
                job.title = title
        return asset_json(asset)


@app.patch("/v1/jobs/{job_id}")
def rename_job(job_id: str, body: Rename, user=Depends(current)):
    title = body.title.strip()
    if not title:
        fail("CONTENT_REQUIRED")
    with Session.begin() as db:
        lock_sqlite_write(db)
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        job = db.scalar(
            select(Job).where(Job.id == job_id, Job.user_id == user.id).with_for_update()
        )
        if not job:
            fail("NOT_FOUND", 404)
        job.title = title
        for asset in db.scalars(
            select(Asset).where(Asset.job_id == job.id, Asset.user_id == user.id)
        ):
            if (
                job.params.get("result_asset_id") == asset.id
                or not job.params.get("result_asset_id")
                and not asset.title.startswith(("[Reference] ", "[Scene] "))
            ):
                asset.title = title
        db.flush()
        return job_json(job)


@app.delete("/v1/assets/{asset_id}")
def remove_asset(asset_id: str, user=Depends(current)):
    with Session.begin() as db:
        asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.user_id == user.id))
        if not asset:
            fail("NOT_FOUND", 404)
        storage.delete(asset.key)
        db.delete(asset)
    return {"ok": True}


@app.get("/v1/assets/{asset_id}/link")
def download_link(asset_id: str, user=Depends(current)):
    with Session() as db:
        asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.user_id == user.id))
        if not asset or not asset_ready(db, asset):
            fail("NOT_FOUND", 404)
    expires = int(time.time()) + 300
    result = {
        "path": f"/v1/files/{asset_id}?expires={expires}&signature={sign_asset(asset_id, expires)}",
        "expires": expires,
    }
    if storage.backend() == "firebase":
        from .firebase_storage import signed_urls

        ext = {"text/plain": "txt", "audio/mpeg": "mp3"}.get(asset.mime, asset.mime.split("/")[-1])
        result.update(signed_urls(asset.key, asset.mime, asset.title + "." + ext))
    return result


@app.get("/v1/files/{asset_id}")
@app.head("/v1/files/{asset_id}")
def download(asset_id: str, expires: int, signature: str, request: Request):
    if not valid_signature(asset_id, expires, signature):
        fail("LINK_EXPIRED", 403)
    if records.enabled():
        stored = accounts.read("assets", asset_id)
        if not stored or stored[0].get("deleted"):
            fail("NOT_FOUND", 404)
        owner = accounts.get(stored[0]["user_id"])
        if not owner:
            fail("NOT_FOUND", 404)
        accounts.hydrate(owner)
        records.sync_user(owner["id"])
    with Session() as db:
        asset = db.get(Asset, asset_id)
        if not asset or not asset_ready(db, asset):
            fail("NOT_FOUND", 404)
    ext = {
        "text/plain": "txt",
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
        "audio/wav": "wav",
        "audio/mpeg": "mp3",
        "audio/ogg": "ogg",
        "video/mp4": "mp4",
    }.get(asset.mime, "bin")
    # Without validators an If-Range request must receive the full representation.
    requested_range = None if request.headers.get("if-range") else request.headers.get("range")
    try:
        start, end = byte_range(requested_range, asset.size)
    except ValueError:
        return RawResponse(status_code=416, headers={"Content-Range": f"bytes */{asset.size}"})
    length = end - start + 1
    response_headers = {
        "Content-Disposition": f'inline; filename="haytile-{asset.id}.{ext}"',
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }
    status = 206 if requested_range else 200
    if requested_range:
        response_headers["Content-Range"] = f"bytes {start}-{end}/{asset.size}"
    if request.method == "HEAD" or not length:
        return RawResponse(status_code=status, media_type=asset.mime, headers=response_headers)
    try:
        reader = storage.open_range(asset.key, start, end)
    except FileNotFoundError:
        fail("NOT_FOUND", 404)
    return StreamingResponse(
        chunks(reader, length),
        status_code=status,
        media_type=asset.mime,
        headers=response_headers,
        background=BackgroundTask(reader.close),
    )


@app.get("/v1/wallet")
def wallet(user=Depends(current)):
    if wallets.enabled():
        return {**wallets.snapshot(user.id), "transactions": wallets.history(user.id)}
    with Session() as db:
        owner = db.get(User, user.id)
        ledger = list(
            db.scalars(
                select(Ledger)
                .where(Ledger.user_id == user.id)
                .order_by(Ledger.created_at.desc())
                .limit(100)
            )
        )
        return {
            "balance": owner.balance,
            "reserved": owner.reserved,
            "transactions": [
                {
                    "id": x.id,
                    "amount": x.amount,
                    "kind": x.kind,
                    "created_at": x.created_at,
                }
                for x in ledger
            ],
        }


@app.get("/v1/admin/operations")
def operations(user=Depends(admin)):
    with Session() as db:
        counts = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
        oldest = db.scalar(select(func.min(Job.created_at)).where(Job.status == "queued"))
        expired = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status.in_(["processing", "quality_check"]), Job.lease_until < now())
        )
        return {
            "configuration_checks": configuration_checks(os.environ, engine.dialect.name),
            "temporary_database": engine.dialect.name == "sqlite",
            "temporary_media": FREE_BETA and not storage.is_remote(),
            "jobs_by_status": counts,
            "oldest_queued_seconds": max(0, int((now() - aware(oldest)).total_seconds()))
            if oldest
            else 0,
            "expired_job_leases": expired,
            "stored_media_bytes": db.scalar(select(func.coalesce(func.sum(Asset.size), 0))),
            "note": "Configuration checks do not verify backups, bucket policies, billing, stores or product completeness.",
        }


@app.get("/v1/admin/overview")
def overview(user=Depends(admin)):
    durable_total = accounts.directory()[1] if accounts.enabled() else None
    durable_audit = accounts.audit() if accounts.enabled() else []
    with Session() as db:
        return {
            "credit_store": "firestore" if wallets.enabled() else "sql",
            "durable_finances": wallets.enabled() or engine.dialect.name == "postgresql",
            "users": durable_total
            if durable_total is not None
            else db.scalar(select(func.count()).select_from(User)),
            "jobs": db.scalar(select(func.count()).select_from(Job)),
            "failed": db.scalar(
                select(func.count()).select_from(Job).where(Job.status == "failed")
            ),
            "models": [
                {
                    "studio": m.studio,
                    "model_id": m.model_id,
                    "enabled": m.enabled,
                    "credits": m.credits,
                    "price_source": m.price_source,
                }
                for m in db.scalars(select(Model))
            ],
            "audit": durable_audit
            + [
                {"action": x.action, "details": x.details, "created_at": x.created_at}
                for x in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(30))
            ],
        }


@app.get("/v1/admin/discover")
def discovery(user=Depends(admin)):
    try:
        return providers.discover()
    except providers.ProviderError as exc:
        fail(str(exc), 503)


class ModelSettings(BaseModel):
    studio: Literal["image", "text", "voice", "music", "video", "minidrama"]
    model_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,120}$")
    enabled: bool
    credits: int = Field(ge=0, le=100000)
    price_source: str = Field(min_length=10, max_length=500)
    operator_billing_ack: bool


@app.put("/v1/admin/models")
def model_settings(body: ModelSettings, user=Depends(admin)):
    if body.enabled and FREE_BETA and engine.dialect.name != "postgresql" and not trial_enabled():
        fail("FREE_BETA_AI_DISABLED", 409)
    if body.credits and engine.dialect.name != "postgresql" and not records.enabled():
        fail("PERSISTENT_POSTGRES_REQUIRED", 409)
    if body.studio == "image" and body.credits != 0 and not pricing.paid_images():
        fail("BASIC_IMAGES_MUST_BE_FREE")
    if body.studio == "text" and body.credits != 0:
        fail("TEXT_MUST_BE_FREE")
    if body.enabled and not body.operator_billing_ack:
        fail("OPERATOR_BILLING_ACK_REQUIRED")
    if not body.price_source.startswith("https://"):
        fail("PRICE_SOURCE_INVALID")
    if body.enabled:
        try:
            catalog = providers.discover()
        except providers.ProviderError as exc:
            fail(str(exc), 503)
        if not any(m["name"] == "models/" + body.model_id for m in catalog):
            fail("MODEL_NOT_IN_ACCOUNT")
    with Session.begin() as db:
        model = db.get(Model, body.studio)
        if not model:
            model = Model(
                studio=body.studio,
                model_id=body.model_id,
                price_source=body.price_source,
            )
            db.add(model)
        model.model_id = body.model_id
        model.enabled = body.enabled
        model.credits = body.credits
        model.price_source = body.price_source
        model.verified_at = now()
        db.add(
            Audit(
                actor_id=user.id,
                action="model.configure",
                details={
                    "studio": body.studio,
                    "model_id": body.model_id,
                    "enabled": body.enabled,
                    "credits": body.credits,
                },
            )
        )
    return {"ok": True}


class Grant(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    amount: int = Field(gt=0, le=100000)
    idempotency_key: str = Field(min_length=8, max_length=80)


@app.post("/v1/admin/credits")
def grant(body: Grant, user=Depends(admin)):
    if wallets.enabled():
        return wallets.grant(body.email, body.amount, user.id, body.idempotency_key)
    if engine.dialect.name != "postgresql":
        fail("PERSISTENT_POSTGRES_REQUIRED", 409)
    with Session.begin() as db:
        owner = db.scalar(
            select(User).where(User.email == body.email.lower().strip()).with_for_update()
        )
        if not owner:
            fail("NOT_FOUND", 404)
        key = "grant:" + user.id + ":" + body.idempotency_key
        old = db.scalar(select(Ledger).where(Ledger.dedup_key == key))
        if old:
            if old.user_id != owner.id or old.amount != body.amount:
                fail("IDEMPOTENCY_CONFLICT", 409)
            return {"ok": True}
        owner.balance += body.amount
        db.add(Ledger(user_id=owner.id, amount=body.amount, kind="admin_grant", dedup_key=key))
        db.add(
            Audit(
                actor_id=user.id,
                action="credits.grant",
                details={"user_id": owner.id, "amount": body.amount},
            )
        )
    return {"ok": True}


from .reset import router as reset_router  # noqa: E402 — routes load after shared auth helpers

app.include_router(reset_router)

from .projects import router as project_router  # noqa: E402 — shares core auth helpers

app.include_router(project_router)

from .voice_sessions import router as voice_router  # noqa: E402

app.include_router(voice_router)

from .chat_management import router as chat_management_router  # noqa: E402

app.include_router(chat_management_router)


@app.get("/v1/admin/users")
def admin_users(search: str = "", offset: int = 0, user=Depends(admin)):
    if len(search) > 254 or not 0 <= offset <= 1000000:
        fail("INVALID_SEARCH")
    if accounts.enabled():
        if offset > 10000:
            fail("INVALID_SEARCH")
        rows, total = accounts.directory(search, offset)
        # Remote directory does not fabricate cached wallet balances.
        return {
            "users": [
                {
                    **{k: a[k] for k in ("id", "email", "name", "locale", "role")},
                    **wallets.snapshot(a["id"]),
                }
                for a in rows
            ],
            "total": total,
            "offset": offset,
            "wallets_available": True,
        }
    with Session() as db:
        query = select(User)
        if search.strip():
            query = query.where(
                User.email.icontains(search.strip(), autoescape=True)
                | User.name.icontains(search.strip(), autoescape=True)
            )
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(
            query.order_by(User.created_at.desc(), User.id).offset(offset).limit(25)
        ).all()
        return {"users": [user_json(u) for u in rows], "total": total, "offset": offset}


class PlanAssignment(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    plan: Literal["free", "creator", "pro"]
    days: int = Field(ge=1, le=366)
    credits: int = Field(ge=0, le=100000)
    reason: str = Field(min_length=3, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=80)


@app.post("/v1/admin/plans")
def assign_plan(body: PlanAssignment, user=Depends(admin)):
    if body.plan == "free" and body.credits:
        fail("FREE_PLAN_CREDITS_INVALID")
    if wallets.enabled():
        return wallets.grant(
            body.email,
            body.credits,
            user.id,
            body.idempotency_key,
            plan=body.plan,
            days=body.days,
            reason=body.reason,
        )
    # No monetary entitlements on Render's disposable SQLite filesystem.
    if engine.dialect.name != "postgresql":
        fail("PERSISTENT_POSTGRES_REQUIRED", 409)
    if body.plan == "free" and body.credits:
        fail("FREE_PLAN_CREDITS_INVALID")
    with Session.begin() as db:
        owner = db.scalar(
            select(User).where(User.email == body.email.strip().lower()).with_for_update()
        )
        if not owner:
            fail("NOT_FOUND", 404)
        key = "plan:" + user.id + ":" + body.idempotency_key
        payload = {
            "user_id": owner.id,
            "plan": body.plan,
            "days": body.days,
            "credits": body.credits,
            "reason": body.reason,
        }
        old = db.scalar(select(Ledger).where(Ledger.dedup_key == key))
        if old:
            audit = db.get(Audit, old.id)
            if not audit or audit.details != payload:
                fail("IDEMPOTENCY_CONFLICT", 409)
            return {"ok": True}
        membership = db.get(Membership, owner.id)
        if not membership:
            membership = Membership(user_id=owner.id)
            db.add(membership)
        membership.plan = body.plan
        membership.expires_at = now() + timedelta(days=body.days)
        membership.updated_at = now()
        owner.balance += body.credits
        from .db import uid

        receipt = uid()
        db.add(
            Ledger(
                id=receipt,
                user_id=owner.id,
                amount=body.credits,
                kind="admin_plan",
                dedup_key=key,
            )
        )
        db.add(Audit(id=receipt, actor_id=user.id, action="plan.assign", details=payload))
    return {"ok": True}


class AdminActivation(BaseModel):
    code: str = Field(min_length=32, max_length=200)


@app.post("/v1/admin/activate")
def activate_admin(body: AdminActivation, request: Request, user=Depends(current)):
    limit("admin-activate-user:" + user.id, 5, 3600)
    limit("admin-activate-ip:" + request.client.host, 10, 3600)
    expected = os.environ.get("HAYTILE_ADMIN_ACTIVATION_CODE", "")
    email = os.environ.get("HAYTILE_ADMIN_EMAIL", "").strip().lower()
    if (
        len(expected) < 32
        or not email
        or user.email != email
        or not secrets.compare_digest(body.code.encode(), expected.encode())
    ):
        fail("ADMIN_ACTIVATION_DENIED", 403)
    if accounts.enabled():
        accounts.hydrate(accounts.change(user.id, {"role": "admin"}, actor=user.id))
        return {"ok": True}
    with Session.begin() as db:
        lock_sqlite_write(db)
        owner = db.scalar(select(User).where(User.id == user.id).with_for_update())
        if not owner or owner.email != email:
            fail("ADMIN_ACTIVATION_DENIED", 403)
        if owner.role != "admin":
            owner.role = "admin"
            db.add(
                Audit(
                    actor_id=owner.id,
                    action="admin.activate",
                    details={"user_id": owner.id},
                )
            )
    return {"ok": True}


from .live_voice import router as live_voice_router  # noqa: E402

app.include_router(live_voice_router)

from .billing import router as billing_router  # noqa: E402

app.include_router(billing_router)

from .web_gateway import install as install_web_gateway  # noqa: E402

install_web_gateway(app)
