"""Delete owned conversations and durably enqueue private media cleanup."""

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select

from . import chat_cleanup
from .db import Asset, Job, Project, Session, User
from .main import current, fail
from .trials import lock_sqlite_write

router = APIRouter()


@router.delete("/v1/chat/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user=Depends(current)):
    while True:
        with Session.begin() as db:
            lock_sqlite_write(db)
            db.scalar(select(User).where(User.id == user.id).with_for_update())
            query = select(Job).where(
                Job.user_id == user.id,
                Job.params["input_params"]["conversation_id"].as_string() == conversation_id,
                or_(
                    Job.params["input_params"]["chat"].as_boolean().is_(True),
                    Job.params["input_params"]["chat_audio"].as_boolean().is_(True),
                ),
            )
            if db.scalar(
                query.where(Job.status.in_(["queued", "processing", "quality_check"])).limit(1)
            ):
                fail("CHAT_STILL_PROCESSING", 409)
            jobs = list(db.scalars(query.order_by(Job.created_at.desc()).limit(100)))
            sessions = list(
                db.scalars(
                    select(Project)
                    .where(
                        Project.user_id == user.id,
                        Project.document["kind"].as_string() == "voice_session",
                        Project.document["conversation_id"].as_string() == conversation_id,
                    )
                    .limit(50)
                )
            )
            if not jobs and not sessions:
                break
            assets = (
                list(
                    db.scalars(
                        select(Asset).where(
                            Asset.user_id == user.id, Asset.job_id.in_([j.id for j in jobs])
                        )
                    )
                )
                if jobs
                else []
            )
            if assets:
                db.add(
                    Project(
                        user_id=user.id,
                        title="Private chat media cleanup",
                        document={"kind": "chat_cleanup", "keys": [a.key for a in assets]},
                    )
                )
            for row in [*assets, *jobs, *sessions]:
                db.delete(row)
        # Firestore metadata and the cleanup outbox commit before any bytes are removed.
    complete = chat_cleanup.clean_user(user.id)
    return {"ok": True, "media_cleanup_pending": not complete}
