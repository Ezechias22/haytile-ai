"""Location state shared by API and worker, with no web application imports."""

from uuid import NAMESPACE_URL, uuid5

from .db import Project


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
