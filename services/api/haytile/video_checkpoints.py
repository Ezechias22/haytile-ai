"""Private scene checkpoints: paid submissions are never blindly repeated."""

import hashlib
import shutil
from pathlib import Path

from . import providers, storage
from .db import Job, Model, Project, Session
from .downloads import chunks


def safe_to_resume(params):
    if params.get("incident_generation_hold"):
        return False
    if params.get("video_checkpoint_version") != 1:
        return False
    return all(
        not scene.get("submission_started") or scene.get("operation_id") or scene.get("key")
        for scene in params.get("video_checkpoints", {}).values()
    )


def clip(job_id, user_id, index, model, prompt, params):
    slot = str(index)
    with Session.begin() as db:
        row = db.get(Job, job_id)
        if not row or row.user_id != user_id or row.status != "processing":
            raise providers.ProviderError("JOB_NOT_PROCESSING")
        if row.params.get("incident_generation_hold"):
            raise providers.ProviderError("MANUAL_RECONCILIATION_REQUIRED")
        if not row.params.get("video_checkpoint_version") and row.params.get("completed_scenes"):
            raise providers.ProviderError("MANUAL_RECONCILIATION_REQUIRED")
        scenes = dict(row.params.get("video_checkpoints", {}))
        saved = dict(scenes.get(slot, {}))
        if not saved and index == 0 and params.get("_resume_operation_id"):
            saved = {
                "submission_started": True,
                "operation_id": params["_resume_operation_id"],
                "model_id": model,
            }
            scenes[slot] = saved
        if (
            saved.get("submission_started")
            and not saved.get("key")
            and not saved.get("operation_id")
        ):
            raise providers.ProviderError("MANUAL_RECONCILIATION_REQUIRED")
        if not saved.get("key") and not saved.get("operation_id"):
            configured = db.get(Model, "video")
            fal_profile = params.get("_fal_profile")
            fal_approved = model.startswith("fal-") and fal_profile and fal_profile.get("id") == model and fal_profile.get("enabled") and fal_profile.get("allow_paused_studio")
            if (not configured or not configured.enabled) and not fal_approved:
                raise providers.ProviderError("MODEL_NOT_APPROVED")
            saved = {"submission_started": True, "model_id": model}
            scenes[slot] = saved
        row.params = {**row.params, "video_checkpoint_version": 1, "video_checkpoints": scenes}
    path = Path(params["_scratch_dir"]) / f"generated-{index}.mp4"
    if saved.get("key"):
        size = saved.get("size", 0)
        if not isinstance(size, int) or not 0 < size <= providers.MAX_MEDIA_BYTES:
            raise providers.ProviderError("VIDEO_CHECKPOINT_INVALID")
        reader = storage.open_range(saved["key"], 0, size - 1)
        digest = hashlib.sha256()
        try:
            with path.open("wb") as target:
                for block in chunks(reader, size):
                    digest.update(block)
                    target.write(block)
        except (OSError, FileNotFoundError) as exc:
            raise providers.ProviderError("VIDEO_CHECKPOINT_UNAVAILABLE") from exc
        if path.stat().st_size != size or digest.hexdigest() != saved.get("sha256"):
            raise providers.ProviderError("VIDEO_CHECKPOINT_INVALID")
        return path
    call = dict(params)
    if saved.get("operation_id"):
        call["_resume_operation_id"] = saved["operation_id"]
    else:
        call.pop("_resume_operation_id", None)
    data, mime = providers.generate("video", model, prompt, call)
    if not mime.startswith("video/"):
        raise providers.ProviderError("VIDEO_STREAM_INVALID")
    if isinstance(data, Path):
        if data != path:
            shutil.copyfile(data, path)
    else:
        path.write_bytes(data)
    size = path.stat().st_size
    if not 0 < size <= providers.MAX_MEDIA_BYTES:
        raise providers.ProviderError("VIDEO_STREAM_INVALID")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    key = storage.put_file(path, mime)
    with Session.begin() as db:
        row = db.get(Job, job_id)
        if not row or row.user_id != user_id or row.status != "processing":
            # This upload has not been referenced by any metadata write.
            storage.delete(key)
            raise providers.ProviderError("JOB_NOT_PROCESSING")
        scenes = dict(row.params.get("video_checkpoints", {}))
        scenes[slot] = {
            **scenes.get(slot, {}),
            "key": key,
            "size": size,
            "sha256": digest.hexdigest(),
            "mime": mime,
        }
        row.params = {**row.params, "video_checkpoints": scenes}
    return path


def cleanup_after_completion(db, row):
    keys = [
        scene["key"]
        for scene in row.params.get("video_checkpoints", {}).values()
        if scene.get("key")
    ]
    if keys and not row.params.get("video_checkpoint_cleanup_scheduled"):
        # Same durable commit as final media and debit; the existing private-media
        # deletion outbox retries after process or SQL-cache loss.
        db.add(
            Project(
                user_id=row.user_id,
                title="Temporary video scene cleanup",
                document={"kind": "chat_cleanup", "keys": keys},
            )
        )
        row.params = {**row.params, "video_checkpoint_cleanup_scheduled": True}
