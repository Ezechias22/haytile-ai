"""Private, idempotent deletion outbox; no AI provider calls or wallet changes."""

import logging
import os

from sqlalchemy import select

from . import accounts, records, storage
from .db import Project, Session

log = logging.getLogger("haytile.cleanup")


def clean_user(user_id):
    with Session() as db:
        tasks = list(
            db.scalars(
                select(Project)
                .where(
                    Project.user_id == user_id,
                    Project.document["kind"].as_string() == "chat_cleanup",
                )
                .limit(20)
            )
        )
    complete = True
    for task in tasks:
        try:
            for key in task.document.get("keys", []):
                storage.delete(key)
            with Session.begin() as db:
                row = db.get(Project, task.id)
                if row and row.user_id == user_id:
                    db.delete(row)
        except Exception:
            log.warning("private_media_cleanup_pending")
            complete = False
    with Session() as db:
        pending = db.scalar(
            select(Project.id)
            .where(
                Project.user_id == user_id, Project.document["kind"].as_string() == "chat_cleanup"
            )
            .limit(1)
        )
    return complete and pending is None


def run_once():
    if records.enabled():
        namespace = os.environ.get("HAYTILE_QUEUE_NAMESPACE", "main") + ":cleanup_"
        docs = records.scan("projects", "state_key", namespace, namespace + "\uf8ff", limit=20)
        for user_id in {doc["user_id"] for _, doc, _ in docs}:
            account = accounts.get(user_id)
            if account:
                accounts.hydrate(account)
                records.sync_user(user_id)
    with Session() as db:
        owners = set(
            db.scalars(
                select(Project.user_id)
                .where(Project.document["kind"].as_string() == "chat_cleanup")
                .limit(20)
            )
        )
    for owner in owners:
        clean_user(owner)
    return bool(owners)
