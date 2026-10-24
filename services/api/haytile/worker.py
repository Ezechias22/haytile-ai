"""Durable PostgreSQL queue. Redis is an optional wakeup accelerator.
Interrupted external work requires reconciliation before resubmission."""

import base64
import logging
import math
import os
import time
from datetime import timedelta

from sqlalchemy import select

from . import providers, storage
from .db import Asset, Job, Ledger, Project, Session, User, now
from .media import inspect_media
from .trials import lock_sqlite_write

log = logging.getLogger("haytile.worker")


def finalize_failure(job_id, code):
    with Session.begin() as db:
        snapshot = db.get(Job, job_id)
        if not snapshot:
            return
        owner = db.scalar(
            select(User).where(User.id == snapshot.user_id).with_for_update()
        )
        job = db.scalar(
            select(Job)
            .where(Job.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not job or job.status in ("completed", "failed"):
            return
        if owner and job.credits:
            owner.reserved -= job.credits
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
    with Session() as db:
        expired = list(
            db.scalars(
                select(Job.id).where(
                    Job.status.in_(["processing", "quality_check"]),
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
            .order_by(Job.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        job.status = "processing"
        job.progress = 15
        job.lease_until = now() + timedelta(hours=2)
        job_id = job.id
        params = dict(job.params.get("input_params", {}))
        model = job.params.get("model_id", "")

    def record_operation(identifier):
        with Session.begin() as state:
            row = state.get(Job, job_id)
            if row and row.status == "processing":
                row.params = {
                    **row.params,
                    "remote_operation": {
                        "id": identifier,
                        "studio": job.studio,
                        "model_id": model,
                    },
                }

    params["_operation_callback"] = record_operation
    if job.params.get("resume_operation_id"):
        params["_resume_operation_id"] = job.params["resume_operation_id"]
    key = None
    try:
        ref_id = params.get("reference_asset_id")
        if ref_id:
            with Session() as db:
                ref = db.get(Asset, ref_id)
            if not ref or ref.user_id != job.user_id:
                raise providers.ProviderError("REFERENCE_INVALID")
            params["_reference_data"] = base64.b64encode(storage.get(ref.key)).decode()
            params["_reference_mime"] = ref.mime
        prompt = job.prompt
        language = params.get("language", "ht")
        if job.studio == "minidrama":
            prompt = (
                "Create a short drama script with title, characters, numbered scenes, exact dialogue and continuity notes. Output language: "
                + language
                + "\n"
                + prompt
            )
        elif job.studio == "text":
            prompt = "Output language: " + language + "\n" + prompt
        if job.studio == "music":
            prompt = "Requested song language: " + language + "\n" + prompt
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
                    clips.append(storage.get(asset.key))
            data = assemble(
                clips,
                params["duration"],
                params.get("aspect", "16:9"),
                clip_durations=params.get("clip_durations"),
            )
            mime = "video/mp4"
        elif job.studio == "video":
            from .video import assemble

            duration = params.get("duration", 8)
            clips = []
            count = math.ceil(duration / 10)
            for index in range(count):
                with Session() as db:
                    if not db.get(User, job.user_id):
                        return True
                scene = f"{prompt}\nScene {index + 1} of {count}. Generate 10 seconds. Maintain the same characters, clothes, environment, lighting and camera continuity. Include natural synchronized audio. Single continuous shot."
                clip, _ = providers.generate("video", model, scene, params)
                clips.append(clip)
                with Session.begin() as db:
                    row = db.get(Job, job_id)
                    if not row or row.status != "processing":
                        return True
                    row.progress = 15 + int(55 * (index + 1) / count)
            data = assemble(clips, duration, params.get("aspect", "16:9"))
            mime = "video/mp4"
        else:
            data, mime = providers.generate(job.studio, model, prompt, params)
        with Session.begin() as db:
            row = db.get(Job, job_id)
            if not row or row.status != "processing":
                return True
            row.status = "quality_check"
            row.progress = 80
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
        mime, text = inspect_media(data, mime, max_bytes=256 * 1024 * 1024)
        key = storage.put(data, mime)
        with Session.begin() as db:
            owner = db.scalar(
                select(User).where(User.id == job.user_id).with_for_update()
            )
            row = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if not owner or not row or row.status != "quality_check":
                storage.delete(key)
                return True
            output_asset = Asset(
                user_id=job.user_id,
                job_id=job_id,
                title=job.title,
                mime=mime,
                key=key,
                size=len(data),
                text=text,
            )
            db.add(output_asset)
            db.flush()
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
            row.status = "completed"
            row.progress = 100
            row.lease_until = None
    except Exception as exc:
        if key:
            storage.delete(key)
        code = (
            str(exc)
            if isinstance(exc, providers.ProviderError)
            else "MEDIA_OR_STORAGE_FAILED"
        )
        if code in (
            "PROVIDER_NETWORK_OR_RESPONSE",
            "MEDIA_OR_STORAGE_FAILED",
            "PROVIDER_OPERATION_PENDING",
            "PROVIDER_MEDIA_DOWNLOAD_FAILED",
        ) or code.startswith("PROVIDER_HTTP_5"):
            code = "WORKER_INTERRUPTED_RECONCILE"
        log.warning("job_failed id=%s code=%s", job_id, code)
        finalize_failure(job_id, code)
    return True


def main():
    logging.basicConfig(level=logging.INFO)
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
