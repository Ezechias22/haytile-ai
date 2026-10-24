"""Explicit, bounded zero-credit AI trials on temporary hosting.

A free Render instance is not a free AI provider. Operator model approval and a
working server-side provider key are still mandatory. Paid user-credit operations
continue to require PostgreSQL.
"""

import os
from datetime import timedelta

from sqlalchemy import func, select

from .db import Job, now


def trial_enabled():
    return os.environ.get("HAYTILE_TRIAL_AI") == "1"


def lock_sqlite_write(db):
    if db.get_bind().dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def trial_limit_code(db, user_id, studio, params, credits):
    if db.get_bind().dialect.name != "sqlite":
        return None
    if credits:
        return "PERSISTENT_POSTGRES_REQUIRED"
    if not trial_enabled():
        return "FREE_BETA_AI_DISABLED"
    if studio == "video":
        maximum = int(os.environ.get("HAYTILE_TRIAL_MAX_VIDEO_SECONDS", "8"))
        if params.get("duration", 8) > maximum:
            return "TRIAL_VIDEO_DURATION_LIMIT"
    if studio == "minidrama" and params.get("mode") == "episode":
        maximum = int(os.environ.get("HAYTILE_TRIAL_MAX_EPISODE_SECONDS", "16"))
        if params.get("duration", 16) > maximum:
            return "TRIAL_VIDEO_DURATION_LIMIT"
    daily = int(os.environ.get("HAYTILE_TRIAL_PER_STUDIO_PER_DAY", "2"))
    attempts = db.scalar(
        select(func.coalesce(func.sum(Job.attempt), 0)).where(
            Job.user_id == user_id,
            Job.studio == studio,
            Job.created_at >= now() - timedelta(days=1),
        )
    )
    if attempts >= daily:
        return "TRIAL_STUDIO_LIMIT"
    return None
