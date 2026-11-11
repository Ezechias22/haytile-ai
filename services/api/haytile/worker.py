"""Durable PostgreSQL queue. Redis is an optional wakeup accelerator.
Interrupted external work requires reconciliation before resubmission."""

import base64
import json
import logging
import math
import os
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import and_, or_, select

from . import accounts, location_state, providers, records, storage, wallets
from .availability import generation_enabled, worker_enabled
from .db import Asset, Job, Ledger, Project, Session, User, now
from .downloads import chunks
from .media import inspect_media, inspect_media_path
from .trials import lock_sqlite_write

log = logging.getLogger("haytile.worker")
_next_cleanup = 0.0


def finalize_failure(job_id, code):
    with Session.begin() as db:
        snapshot = db.get(Job, job_id)
        if not snapshot:
            return
        owner = db.scalar(select(User).where(User.id == snapshot.user_id).with_for_update())
        job = db.scalar(
            select(Job)
            .where(Job.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not job or job.status in ("completed", "failed"):
            return
        if owner and job.credits:
            if records.enabled():
                bank = wallets.snapshot(owner.id)
                owner.balance, owner.reserved = bank["balance"], bank["reserved"]
            owner.reserved -= job.credits
        if job.params.get("input_params", {}).get("voice_session_id"):
            from .voice_budget import release

            release(db, job)
        job.status = "failed"
        job.error = code
        job.lease_until = None
        if job.credits:
            db.add(
                Ledger(
                    user_id=job.user_id,
                    job_id=job.id,
                    amount=0,
                    kind="release",
                    dedup_key=f"{job.id}:release:{job.attempt}",
                )
            )


def run_once():
    global _next_cleanup
    if time.monotonic() >= _next_cleanup:
        _next_cleanup = time.monotonic() + 30
        from . import chat_cleanup

        if chat_cleanup.run_once():
            return True
    if not worker_enabled():
        return False
    candidates = records.pull_work() if records.enabled() else None
    with Session() as db:
        expired = list(
            db.scalars(
                select(Job.id).where(
                    Job.id.in_(candidates) if candidates is not None else True,
                    or_(
                        Job.status.in_(["processing", "quality_check"]),
                        and_(
                            Job.status == "queued",
                            Job.params["input_params"]["live_voice"].as_boolean().is_(True),
                        ),
                    ),
                    Job.lease_until < now(),
                )
            )
        )
    for job_id in expired:
        finalize_failure(job_id, "WORKER_INTERRUPTED_RECONCILE")
    with Session.begin() as db:
        lock_sqlite_write(db)
        job = db.scalar(
            select(Job)
            .where(Job.status == "queued")
            .where(Job.params["input_params"]["live_voice"].as_boolean().is_not(True))
            .where(Job.id.in_(candidates) if candidates is not None else True)
            .where(True if generation_enabled() else Job.studio == "assembly")
            .order_by(Job.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        job.status = "processing"
        if job.params.get("input_params", {}).get("chat") is True:
            job.params = {
                k: v
                for k, v in job.params.items()
                if k not in ("chat_grounding", "chat_location_requested")
            }
        job.progress = 15
        job.lease_until = now() + timedelta(hours=2)
        job_id = job.id
        params = dict(job.params.get("input_params", {}))
        if "chat_contents" in job.params:
            params["_chat_contents"] = job.params["chat_contents"]
        model = job.params.get("model_id", "")

    def record_operation(identifier):
        with Session.begin() as state:
            row = state.get(Job, job_id)
            if row and row.status == "processing":
                if job.studio == "video" and "_scene_index" in params:
                    scenes = dict(row.params.get("video_checkpoints", {}))
                    slot = str(params["_scene_index"])
                    scenes[slot] = {
                        **scenes.get(slot, {}),
                        "operation_id": identifier,
                        "model_id": model,
                    }
                    row.params = {**row.params, "video_checkpoints": scenes}
                row.params = {
                    **row.params,
                    "remote_operation": {
                        "id": identifier,
                        "studio": job.studio,
                        "model_id": model,
                    },
                }

    if job.params.get("pricing_quote", {}).get("voice_token_limit"):
        params["_max_output_tokens"] = job.params["pricing_quote"]["voice_token_limit"]
    if job.params.get("pricing_quote", {}).get("image_size"):
        params["_image_size"] = job.params["pricing_quote"]["image_size"]
    params["_operation_callback"] = record_operation
    if job.params.get("resume_operation_id"):
        params["_resume_operation_id"] = job.params["resume_operation_id"]
    if isinstance(job.params.get("provider_response"), dict):
        params["_resume_response"] = job.params["provider_response"]
    text_checkpoint = job.params.get("provider_text_result")
    metadata = {}

    def record_response(response):
        if len(json.dumps(response, ensure_ascii=False).encode()) > 512000:
            return
        with Session.begin() as state:
            row = state.get(Job, job_id)
            if row and row.status == "processing":
                row.params = {**row.params, "provider_response": response}

    params["_response_callback"] = record_response
    phase = "preparing"
    key = None
    scratch = tempfile.TemporaryDirectory(prefix="haytile-job-")
    params["_scratch_dir"] = scratch.name
    try:
        ref_id = params.get("reference_asset_id")
        if ref_id:
            with Session() as db:
                ref = db.get(Asset, ref_id)
            if not ref or ref.user_id != job.user_id:
                raise providers.ProviderError("REFERENCE_INVALID")
            params["_reference_data"] = base64.b64encode(storage.get(ref.key)).decode()
            params["_reference_mime"] = ref.mime
        if params.get("chat") is True:
            from .chat_tools import markers, materialize

            contents = params.get("_chat_contents", []) + [
                {
                    "role": "user",
                    "parts": [{"text": job.prompt}] + markers(params.get("attachment_ids", [])),
                }
            ]
            with Session() as context_db:
                settings = location_state.preference(context_db, job.user_id)
                params["_location_consent"] = (
                    "enabled"
                    if settings["enabled"]
                    else "disabled"
                    if settings["known"]
                    else "unknown"
                )
                if "location_consent_version" in params and (
                    not settings["enabled"]
                    or params["location_consent_version"] != settings["version"]
                ):
                    params.pop("location", None)
                if not params.get("location") and settings["enabled"] and settings["position"]:
                    params["location"] = settings["position"]
                params["_chat_materialized"] = (
                    materialize(context_db, job.user_id, contents)
                    if not params.get("_resume_response") and not text_checkpoint
                    else [{"role": "user", "parts": [{"text": job.prompt}]}]
                )

            def save_grounding(value):
                if value.get("searched"):
                    metadata["chat_grounding"] = value

            params["_grounding_callback"] = save_grounding

            def save_location_request(value):
                metadata["chat_location_requested"] = value

            params["_location_request_callback"] = save_location_request
        prompt = job.prompt
        language = params.get("language", "ht")
        if job.studio == "minidrama":
            prompt = (
                "Create a short drama script with title, characters, numbered scenes, exact dialogue and continuity notes. Output language: "
                + language
                + "\n"
                + prompt
            )
        elif job.studio == "text" and not params.get("chat"):
            prompt = "Output language: " + language + "\n" + prompt
        if job.studio == "music":
            from .music import target_seconds

            params["_music_target_seconds"] = target_seconds(job.prompt, model, params)
            prompt = "Requested song language: " + language + "\n" + prompt
        phase = "provider"
        if job.studio == "minidrama" and params.get("mode") == "episode":
            from .drama import render_episode

            data, mime = render_episode(job, params, job.params["render_config"])
        elif job.studio == "assembly":
            from .video import assemble

            clips = []
            with Session() as db:
                for aid in params["clip_ids"]:
                    asset = db.get(Asset, aid)
                    if not asset or asset.user_id != job.user_id:
                        raise providers.ProviderError("SCENE_MEDIA_NOT_READY")
                    path = Path(scratch.name) / f"uploaded-{len(clips)}.mp4"
                    reader = storage.open_range(asset.key, 0, asset.size - 1)
                    with path.open("wb") as target:
                        for chunk in chunks(reader, asset.size):
                            target.write(chunk)
                    clips.append(path)
            data = assemble(
                clips,
                params["duration"],
                params.get("aspect", "16:9"),
                clip_durations=params.get("clip_durations"),
                output_path=Path(scratch.name) / "assembled-final.mp4",
            )
            mime = "video/mp4"
        elif job.studio == "video":
            from .video import assemble

            duration = params.get("duration", 8)
            clips = []
            count = math.ceil(duration / 8)
            for index in range(count):
                with Session() as db:
                    if not db.get(User, job.user_id):
                        return True
                scene = f"{prompt}\nScene {index + 1} of {count}. Generate 8 seconds. Maintain the same characters, clothes, environment, lighting and camera continuity. Include natural synchronized audio. Single continuous shot."
                from .video_checkpoints import clip as checkpoint_clip

                params["_scene_index"] = index
                path = checkpoint_clip(job_id, job.user_id, index, model, scene, params)
                clips.append(path)
                with Session.begin() as db:
                    row = db.get(Job, job_id)
                    if not row or row.status != "processing":
                        return True
                    row.progress = 15 + int(55 * (index + 1) / count)
                    row.params = {
                        **row.params,
                        "completed_scenes": index + 1,
                        "total_scenes": count,
                    }
            data = assemble(
                clips,
                duration,
                params.get("aspect", "16:9"),
                output_path=Path(scratch.name) / "video-final.mp4",
            )
            mime = "video/mp4"
        else:
            if job.studio == "text" and isinstance(text_checkpoint, dict):
                data, mime = text_checkpoint["text"].encode(), "text/plain"
            else:
                data, mime = providers.generate(job.studio, model, prompt, params)
        phase = "saving_response"
        with Session.begin() as db:
            row = db.get(Job, job_id)
            if not row or row.status != "processing":
                return True
            if job.studio == "text" and mime == "text/plain" and len(data) <= 256000:
                row.params = {
                    **row.params,
                    **metadata,
                    "provider_text_result": {"text": data.decode("utf-8")},
                }
            row.status = "quality_check"
            row.progress = 80
        phase = "quality_check"
        expected = {
            "text": "text/",
            "minidrama": "video/" if params.get("mode") == "episode" else "text/",
            "image": "image/",
            "voice": "audio/",
            "music": "audio/",
            "video": "video/",
            "assembly": "video/",
        }[job.studio]
        if not mime.startswith(expected):
            raise providers.ProviderError("PROVIDER_MEDIA_TYPE_MISMATCH")
        phase = "quality_check"
        if isinstance(data, Path):
            mime, text = inspect_media_path(data, mime, max_bytes=256 * 1024 * 1024)
            output_size = data.stat().st_size
            phase = "storage"
            key = storage.put_file(data, mime)
        else:
            mime, text = inspect_media(data, mime, max_bytes=256 * 1024 * 1024)
            output_size = len(data)
            phase = "storage"
            key = storage.put(data, mime)
        phase = "publishing"
        with Session.begin() as db:
            owner = db.scalar(select(User).where(User.id == job.user_id).with_for_update())
            row = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if not owner or not row or row.status != "quality_check":
                storage.delete(key)
                return True
            output_asset = Asset(
                user_id=job.user_id,
                job_id=job_id,
                title=row.title,
                mime=mime,
                key=key,
                size=output_size,
                text=text,
            )
            db.add(output_asset)
            db.flush()
            row.params = {**row.params, "result_asset_id": output_asset.id}
            project_id = params.get("project_id") or job.params.get("project_id")
            if project_id and params.get("scene_id"):
                project = db.scalar(
                    select(Project)
                    .where(Project.id == project_id, Project.user_id == job.user_id)
                    .with_for_update()
                )
                if project:
                    import copy

                    document = copy.deepcopy(project.document)
                    for scene in document.get("scenes", []):
                        if scene["id"] == params["scene_id"]:
                            scene["asset_id"] = output_asset.id
                    project.document = document
                    project.version += 1
            if (
                job.studio == "minidrama"
                and params.get("mode") == "episode"
                and params.get("project_id")
            ):
                project = db.get(Project, params["project_id"])
                if project:
                    project.document = {
                        **project.document,
                        "final_asset_id": output_asset.id,
                    }
                    project.version += 1
            if row.credits:
                if records.enabled():
                    bank = wallets.snapshot(owner.id)
                    owner.balance, owner.reserved = bank["balance"], bank["reserved"]
                owner.reserved -= row.credits
                owner.balance -= row.credits
                db.add(
                    Ledger(
                        user_id=job.user_id,
                        job_id=job_id,
                        amount=-row.credits,
                        kind="debit",
                        dedup_key=job_id + ":debit",
                    )
                )
            if job.studio == "video":
                from .video_checkpoints import cleanup_after_completion

                cleanup_after_completion(db, row)
            row.params = {
                key: value
                for key, value in row.params.items()
                if key not in ("provider_response", "provider_text_result")
            }
            row.status = "completed"
            row.progress = 100
            row.lease_until = None
    except accounts.Unavailable:
        # A remote commit may already have published this file. Keep it private,
        # leave the durable lease for reconciliation, and never blindly resubmit.
        log.warning("job_remote_commit_unavailable id=%s", job_id)
    except Exception as exc:
        if key:
            storage.delete(key)
        code = (
            str(exc)
            if isinstance(exc, providers.ProviderError)
            else "WORKER_PREPARATION_FAILED"
            if phase == "preparing"
            else "MEDIA_OR_STORAGE_FAILED"
        )
        try:
            with Session.begin() as state:
                row = state.get(Job, job_id)
                if row:
                    row.params = {
                        **row.params,
                        "failure_phase": phase,
                        "failure_cause": code,
                        "provider_message": getattr(exc, "public_message", None),
                        "provider_status": getattr(exc, "provider_status", None),
                        "failure_exception": type(exc).__name__,
                    }
        except Exception:
            log.warning("job_failure_metadata_unavailable id=%s", job_id)
        if code in (
            "PROVIDER_NETWORK_OR_RESPONSE",
            "MEDIA_OR_STORAGE_FAILED",
            "PROVIDER_OPERATION_PENDING",
            "PROVIDER_MEDIA_DOWNLOAD_FAILED",
        ) or code.startswith("PROVIDER_HTTP_5"):
            code = "WORKER_INTERRUPTED_RECONCILE"
        log.warning(
            "job_failed id=%s code=%s phase=%s exception=%s",
            job_id,
            code,
            phase,
            type(exc).__name__,
        )
        finalize_failure(job_id, code)
    finally:
        scratch.cleanup()
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    if not worker_enabled():
        return
    log.info("worker_ready")
    while True:
        try:
            if run_once():
                continue
            if os.environ.get("REDIS_URL"):
                from redis import Redis

                Redis.from_url(os.environ["REDIS_URL"], socket_timeout=6).brpop(
                    "haytile:wake", timeout=3
                )
            else:
                time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception:
            log.error("worker_cycle_failed")
            time.sleep(3)


if __name__ == "__main__":
    main()
