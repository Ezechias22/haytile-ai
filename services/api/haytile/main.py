import json
import math
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

from . import providers, storage
from .db import (
    Asset,
    Audit,
    Job,
    Ledger,
    LoginSession,
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
from .runtime_checks import configuration_checks, require_durable_runtime
from .security import (
    hash_token,
    password_hash,
    sign_asset,
    valid_signature,
    verify_password,
)
from .trials import lock_sqlite_write, trial_enabled, trial_limit_code

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
    token = (
        bearer[7:] if bearer.startswith("Bearer ") else request.cookies.get(COOKIE, "")
    )
    if not token:
        fail("AUTH_REQUIRED", 401)
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
    return {
        k: getattr(u, k)
        for k in ("id", "email", "name", "locale", "role", "balance", "reserved")
    }


def asset_json(a):
    return {
        k: getattr(a, k)
        for k in ("id", "title", "mime", "size", "text", "job_id", "created_at")
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
        )
    }


def session_response(user, response):
    raw = secrets.token_urlsafe(32)
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
    require_durable_runtime(engine.dialect.name)
    with engine.connect() as connection:
        connection.execute(select(1))
    yield


app = FastAPI(title="HAYTILE AI", version="0.1.0", lifespan=lifespan)


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
        "free_beta": FREE_BETA,
        "temporary_storage": FREE_BETA and not bool(storage.BUCKET),
        "temporary_database": engine.dialect.name == "sqlite",
        "provider_generation_disabled": not configured
        or (FREE_BETA and engine.dialect.name != "postgresql" and not trial_enabled()),
        "trial_ai": trial_enabled(),
        "trial_max_episode_seconds": int(
            os.environ.get("HAYTILE_TRIAL_MAX_EPISODE_SECONDS", "16")
        )
        if trial_enabled()
        else 180,
        "trial_max_video_seconds": int(
            os.environ.get("HAYTILE_TRIAL_MAX_VIDEO_SECONDS", "8")
        )
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
        "storage": "s3" if storage.BUCKET else "private-local",
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
    raw = (
        bearer[7:] if bearer.startswith("Bearer ") else request.cookies.get(COOKIE, "")
    )
    with Session.begin() as db:
        db.execute(
            delete(LoginSession).where(LoginSession.token_hash == hash_token(raw))
        )
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
            "jobs": [
                job_json(x)
                for x in db.scalars(select(Job).where(Job.user_id == user.id))
            ],
            "assets": [
                asset_json(x)
                for x in db.scalars(select(Asset).where(Asset.user_id == user.id))
            ],
            "ledger": [
                {"amount": x.amount, "kind": x.kind, "created_at": x.created_at}
                for x in db.scalars(select(Ledger).where(Ledger.user_id == user.id))
            ],
        }


@app.get("/v1/models")
def models():
    with Session() as db:
        rows = {m.studio: m for m in db.scalars(select(Model))}
    present = bool(os.environ.get("HAYTILE_GEMINI_API_KEY")) and not (
        FREE_BETA and engine.dialect.name != "postgresql" and not trial_enabled()
    )
    return [
        {
            "studio": s,
            "available": bool(present and rows.get(s) and rows[s].enabled),
            "episode_available": bool(
                present
                and rows.get(s)
                and rows[s].enabled
                and all(
                    rows.get(kind) and rows[kind].enabled and rows[kind].credits == 0
                    for kind in ("image", "video")
                )
                and rows[s].credits == 0
            )
            if s == "minidrama"
            else False,
            "model_id": rows[s].model_id if s in rows else None,
            "credits": 0 if s == "image" else (rows[s].credits if s in rows else 0),
            "terms_url": rows[s].terms_url if s in rows else None,
            "reason": None
            if present and rows.get(s) and rows[s].enabled
            else "PROVIDER_SETUP_REQUIRED",
        }
        for s in STUDIOS
    ]


class Generate(BaseModel):
    studio: Literal["image", "text", "voice", "music", "video", "minidrama"]
    title: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=12000)
    idempotency_key: str = Field(min_length=8, max_length=80)
    params: dict = Field(default_factory=dict)
    confirmed_credits: int = Field(ge=0)


@app.post("/v1/jobs", status_code=202)
def generate(body: Generate, user=Depends(current)):
    if FREE_BETA and engine.dialect.name != "postgresql" and not trial_enabled():
        fail("FREE_BETA_AI_DISABLED", 503)
    if not body.prompt.strip() or not body.title.strip():
        fail("CONTENT_REQUIRED")
    if any(str(key).startswith("_") for key in body.params):
        fail("PARAMS_INVALID")
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
    if body.studio == "music" and body.params.get("preserve_lyrics"):
        fail("EXACT_LYRICS_VERIFICATION_PENDING", 409)
    limit(
        "generation-global",
        int(os.environ.get("HAYTILE_DAILY_JOB_LIMIT", "100")),
        86400,
    )
    limit("generation:" + user.id, 30, 3600)
    with Session.begin() as db:
        lock_sqlite_write(db)
        owner = db.scalar(select(User).where(User.id == user.id).with_for_update())
        old = db.scalar(
            select(Job).where(
                Job.user_id == user.id, Job.idempotency_key == body.idempotency_key
            )
        )
        if old:
            if (
                old.studio != body.studio
                or old.prompt != body.prompt
                or old.params.get("input_params") != body.params
            ):
                fail("IDEMPOTENCY_CONFLICT", 409)
            return job_json(old)
        model = db.get(Model, body.studio)
        if (
            not model
            or not model.enabled
            or not os.environ.get("HAYTILE_GEMINI_API_KEY")
        ):
            fail("PROVIDER_SETUP_REQUIRED", 503)
        render_config = None
        if episode:
            image_model = db.get(Model, "image")
            video_model = db.get(Model, "video")
            if (
                not image_model
                or not video_model
                or not image_model.enabled
                or not video_model.enabled
            ):
                fail("PROVIDER_SETUP_REQUIRED", 503)
            if model.credits or image_model.credits or video_model.credits:
                fail("MINIDRAMA_CREDIT_QUOTE_PENDING", 409)
            render_config = {
                "text": model.model_id,
                "image": image_model.model_id,
                "video": video_model.model_id,
            }
        credits = (
            0
            if body.studio == "image"
            else model.credits
            * (
                math.ceil(body.params.get("duration", 8) / 10)
                if body.studio == "video"
                else 1
            )
        )
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
        owner.reserved += credits
        job = Job(
            user_id=user.id,
            studio=body.studio,
            title=body.title,
            prompt=body.prompt,
            idempotency_key=body.idempotency_key,
            credits=credits,
            params={
                "input_params": body.params,
                "model_id": model.model_id,
                "provider": model.provider,
                "render_config": render_config,
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

            Redis.from_url(os.environ["REDIS_URL"], socket_timeout=1).lpush(
                "haytile:wake", "job"
            )
        except Exception:
            pass


@app.get("/v1/jobs")
def jobs(user=Depends(current)):
    with Session() as db:
        return [
            job_json(j)
            for j in db.scalars(
                select(Job)
                .where(Job.user_id == user.id)
                .order_by(Job.created_at.desc())
                .limit(100)
            )
        ]


@app.post("/v1/jobs/{job_id}/retry")
def retry(job_id: str, user=Depends(current)):
    with Session.begin() as db:
        lock_sqlite_write(db)
        owner = db.scalar(select(User).where(User.id == user.id).with_for_update())
        job = db.scalar(
            select(Job)
            .where(Job.id == job_id, Job.user_id == user.id)
            .with_for_update()
        )
        if not job:
            fail("NOT_FOUND", 404)
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
        owner.reserved += job.credits
        job.status = "queued"
        job.error = None
        job.progress = 0
        job.attempt += 1
        result = job_json(job)
    wake_worker()
    return result


@app.get("/v1/assets")
def assets(user=Depends(current)):
    with Session() as db:
        return [
            asset_json(a)
            for a in db.scalars(
                select(Asset)
                .where(Asset.user_id == user.id)
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
    except Exception:
        storage.delete(key)
        raise


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@app.patch("/v1/assets/{asset_id}")
def rename(asset_id: str, body: Rename, user=Depends(current)):
    with Session.begin() as db:
        asset = db.scalar(
            select(Asset).where(Asset.id == asset_id, Asset.user_id == user.id)
        )
        if not asset:
            fail("NOT_FOUND", 404)
        asset.title = body.title
        return asset_json(asset)


@app.delete("/v1/assets/{asset_id}")
def remove_asset(asset_id: str, user=Depends(current)):
    with Session.begin() as db:
        asset = db.scalar(
            select(Asset).where(Asset.id == asset_id, Asset.user_id == user.id)
        )
        if not asset:
            fail("NOT_FOUND", 404)
        storage.delete(asset.key)
        db.delete(asset)
    return {"ok": True}


@app.get("/v1/assets/{asset_id}/link")
def download_link(asset_id: str, user=Depends(current)):
    with Session() as db:
        asset = db.scalar(
            select(Asset).where(Asset.id == asset_id, Asset.user_id == user.id)
        )
        if not asset:
            fail("NOT_FOUND", 404)
    expires = int(time.time()) + 300
    return {
        "path": f"/v1/files/{asset_id}?expires={expires}&signature={sign_asset(asset_id, expires)}",
        "expires": expires,
    }


@app.get("/v1/files/{asset_id}")
@app.head("/v1/files/{asset_id}")
def download(asset_id: str, expires: int, signature: str, request: Request):
    if not valid_signature(asset_id, expires, signature):
        fail("LINK_EXPIRED", 403)
    with Session() as db:
        asset = db.get(Asset, asset_id)
    if not asset:
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
    requested_range = (
        None if request.headers.get("if-range") else request.headers.get("range")
    )
    try:
        start, end = byte_range(requested_range, asset.size)
    except ValueError:
        return RawResponse(
            status_code=416, headers={"Content-Range": f"bytes */{asset.size}"}
        )
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
        return RawResponse(
            status_code=status, media_type=asset.mime, headers=response_headers
        )
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
        counts = dict(
            db.execute(select(Job.status, func.count()).group_by(Job.status)).all()
        )
        oldest = db.scalar(
            select(func.min(Job.created_at)).where(Job.status == "queued")
        )
        expired = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.status.in_(["processing", "quality_check"]), Job.lease_until < now()
            )
        )
        return {
            "configuration_checks": configuration_checks(
                os.environ, engine.dialect.name
            ),
            "temporary_database": engine.dialect.name == "sqlite",
            "temporary_media": FREE_BETA and not bool(storage.BUCKET),
            "jobs_by_status": counts,
            "oldest_queued_seconds": max(
                0, int((now() - aware(oldest)).total_seconds())
            )
            if oldest
            else 0,
            "expired_job_leases": expired,
            "stored_media_bytes": db.scalar(
                select(func.coalesce(func.sum(Asset.size), 0))
            ),
            "note": "Configuration checks do not verify backups, bucket policies, billing, stores or product completeness.",
        }


@app.get("/v1/admin/overview")
def overview(user=Depends(admin)):
    with Session() as db:
        return {
            "users": db.scalar(select(func.count()).select_from(User)),
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
            "audit": [
                {"action": x.action, "details": x.details, "created_at": x.created_at}
                for x in db.scalars(
                    select(Audit).order_by(Audit.created_at.desc()).limit(30)
                )
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
    if (
        body.enabled
        and FREE_BETA
        and engine.dialect.name != "postgresql"
        and not trial_enabled()
    ):
        fail("FREE_BETA_AI_DISABLED", 409)
    if body.credits and engine.dialect.name != "postgresql":
        fail("PERSISTENT_POSTGRES_REQUIRED", 409)
    if body.studio == "image" and body.credits != 0:
        fail("BASIC_IMAGES_MUST_BE_FREE")
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
    email: str
    amount: int = Field(gt=0, le=100000)
    idempotency_key: str = Field(min_length=8, max_length=80)


@app.post("/v1/admin/credits")
def grant(body: Grant, user=Depends(admin)):
    if engine.dialect.name != "postgresql":
        fail("PERSISTENT_POSTGRES_REQUIRED", 409)
    with Session.begin() as db:
        owner = db.scalar(
            select(User)
            .where(User.email == body.email.lower().strip())
            .with_for_update()
        )
        if not owner:
            fail("NOT_FOUND", 404)
        key = "grant:" + body.idempotency_key
        old = db.scalar(select(Ledger).where(Ledger.dedup_key == key))
        if old:
            if old.user_id != owner.id or old.amount != body.amount:
                fail("IDEMPOTENCY_CONFLICT", 409)
            return {"ok": True}
        owner.balance += body.amount
        db.add(
            Ledger(
                user_id=owner.id, amount=body.amount, kind="admin_grant", dedup_key=key
            )
        )
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
