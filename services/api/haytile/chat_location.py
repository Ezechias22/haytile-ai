"""Private remembered location consent and latest device-reported fix."""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .db import Project, Session, User, now
from .main import current, fail, limit
from .trials import lock_sqlite_write

router = APIRouter()


def identifier(user_id):
    return str(uuid5(NAMESPACE_URL, "haytile:location:" + user_id))


def preference(db, user_id):
    row = db.get(Project, identifier(user_id))
    if not row or row.user_id != user_id:
        return {"known": False, "enabled": False, "position": None, "version": 0}
    return {
        "known": True,
        "enabled": row.document.get("enabled") is True,
        "position": row.document.get("position"),
        "version": row.version,
    }


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(gt=0, le=100000)
    captured_at: datetime
    authorize: bool = False
    consent_version: int | None = None


@router.get("/v1/chat/location")
def read(user=Depends(current)):
    with Session() as db:
        return preference(db, user.id)


@router.patch("/v1/chat/location")
def update(body: Position, user=Depends(current)):
    if body.captured_at.tzinfo is None:
        fail("CHAT_LOCATION_INVALID")
    age = (now() - body.captured_at.astimezone(timezone.utc)).total_seconds()
    if not -60 <= age <= 300:
        fail("CHAT_LOCATION_INVALID")
    limit("location-update:" + user.id, 60, 60)
    position = body.model_dump(mode="json", exclude={"authorize", "consent_version"})
    with Session.begin() as db:
        lock_sqlite_write(db)
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        row = db.get(Project, identifier(user.id))
        if not row:
            row = Project(
                id=identifier(user.id),
                user_id=user.id,
                title="Private location preference",
                document={},
                version=1,
            )
            db.add(row)
        if not body.authorize and (
            row.document.get("enabled") is not True or body.consent_version != row.version
        ):
            fail("CHAT_LOCATION_REVOKED", 409)
        if body.authorize:
            row.version += 1
        previous = row.document.get("position") or {}
        # A delayed fix from another tab/device cannot replace a newer fix.
        if (
            previous.get("captured_at")
            and datetime.fromisoformat(previous["captured_at"].replace("Z", "+00:00"))
            > body.captured_at
        ):
            return preference(db, user.id)
        row.document = {
            "kind": "chat_location",
            "enabled": True,
            "position": position,
            "updated_at": now().isoformat(),
        }
        db.flush()
        return preference(db, user.id)


@router.delete("/v1/chat/location")
def revoke(user=Depends(current)):
    with Session.begin() as db:
        lock_sqlite_write(db)
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        row = db.get(Project, identifier(user.id))
        if not row:
            row = Project(
                id=identifier(user.id),
                user_id=user.id,
                title="Private location preference",
                document={},
                version=1,
            )
            db.add(row)
        row.version = (row.version or 0) + 1
        row.document = {
            "kind": "chat_location",
            "enabled": False,
            "position": None,
            "updated_at": now().isoformat(),
        }
        db.flush()
        return preference(db, user.id)
