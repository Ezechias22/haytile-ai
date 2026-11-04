"""Firestore metadata and wallet settlement; SQL remains a replaceable projection.

Remote writes happen once immediately before SQL commit. A CAS claim commits
before any provider call. Completion, output metadata and debit share one commit.
"""

import hashlib
import json
import os
import threading
from datetime import datetime, timezone

from sqlalchemy import event, inspect, select

from . import accounts as store
from . import wallets
from .db import Asset, Job, Project, Session, User, now
from .security import hash_token
from .trials import lock_sqlite_write

TYPES = {Job: "jobs", Asset: "assets", Project: "projects"}
CLASSES = {v: k for k, v in TYPES.items()}
FIELDS = {cls: [c.key for c in inspect(cls).columns if c.key != "remote_version"] for cls in TYPES}
DATE_FIELDS = {"created_at", "updated_at", "lease_until"}
_sync_lock = threading.RLock()
_cursors = {}


class WriteUncertain(store.Unavailable):
    """Do not delete an uploaded object or resubmit a provider call on this error."""


class DuplicateJob(Exception):
    def __init__(self, job_id, user_id):
        self.job_id, self.user_id = job_id, user_id


def enabled():
    return store.enabled()


def serial(data):
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: (
            value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        ).isoformat(),
    )


def payload(obj):
    return {key: getattr(obj, key) for key in FIELDS[type(obj)]}


def unpack(doc):
    try:
        data = json.loads(doc["payload"])
        for key in DATE_FIELDS:
            if data.get(key):
                data[key] = datetime.fromisoformat(data[key].replace("Z", "+00:00"))
        return data
    except (ValueError, TypeError, KeyError):
        raise store.Unavailable() from None


def fingerprint(data):
    params = data.get("params", {})
    core = {
        "studio": data["studio"],
        "prompt": data["prompt"],
        "input": params.get(
            "input_params",
            {
                k: params[k]
                for k in (
                    "clip_ids",
                    "clip_durations",
                    "duration",
                    "aspect",
                    "project_id",
                    "scene_id",
                )
                if k in params
            },
        ),
        "model_id": params.get("model_id"),
        "requested_model_id": params.get("requested_model_id"),
    }
    return hashlib.sha256(serial(core).encode()).hexdigest()


def document(data, kind, token=""):
    stamp = now().isoformat()
    result = {
        "user_id": data["user_id"],
        "payload": serial(data),
        "sync_key": data["user_id"] + "_" + stamp + "_" + data["id"],
        "sort_key": data["user_id"] + "_" + data["created_at"].isoformat() + "_" + data["id"],
        "write_token": token,
    }
    if kind == "projects" and data.get("document", {}).get("kind") == "chat_cleanup":
        result["state_key"] = (
            os.environ.get("HAYTILE_QUEUE_NAMESPACE", "main")
            + ":cleanup_"
            + stamp
            + "_"
            + data["id"]
        )
    if kind == "jobs":
        result["state_key"] = (
            os.environ.get("HAYTILE_QUEUE_NAMESPACE", "main")
            + ":"
            + (
                (
                    "queued_" + stamp
                    if data["status"] == "queued"
                    else "active_" + data["lease_until"].isoformat()
                    if data["status"] in ("processing", "quality_check") and data.get("lease_until")
                    else "terminal_" + stamp
                )
                + "_"
                + data["id"]
            )
        )
    return result


def scan(kind, field, lower, upper, limit=200):
    response = store.request(
        "POST",
        "/documents:runQuery",
        json={
            "structuredQuery": {
                "from": [{"collectionId": "haytile_" + kind}],
                "where": {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": [
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": field},
                                    "op": "GREATER_THAN",
                                    "value": {"stringValue": lower},
                                }
                            },
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": field},
                                    "op": "LESS_THAN",
                                    "value": {"stringValue": upper},
                                }
                            },
                        ],
                    }
                },
                "orderBy": [{"field": {"fieldPath": field}, "direction": "ASCENDING"}],
                "limit": limit,
            }
        },
    )
    if response.status_code != 200:
        raise store.Unavailable()
    return [
        (
            x["document"]["name"].rsplit("/", 1)[1],
            store.decode(x["document"]),
            x["document"]["updateTime"],
        )
        for x in response.json()
        if "document" in x
    ]


def sync_user(user_id):
    """Bounded delta queries; never write a SQL cache back as a new authority."""
    if not enabled():
        return
    with _sync_lock, Session.begin() as db:
        db.info["remote_projection"] = True
        lock_sqlite_write(db)
        user = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if not user:
            raise store.Unavailable()
        bank = wallets.snapshot(user_id)
        user.balance, user.reserved = bank["balance"], bank["reserved"]
        for kind in ("jobs", "assets", "projects"):
            cursor = _cursors.get((user_id, kind), user_id + "_")
            while True:
                batch = scan(kind, "sync_key", cursor, user_id + "_\uf8ff")
                for record_id, doc, version in batch:
                    cls = CLASSES[kind]
                    obj = db.get(cls, record_id)
                    if doc.get("deleted") == 1:
                        if obj:
                            db.delete(obj)
                    elif obj is None or obj.remote_version != version:
                        data = unpack(doc)
                        if data["user_id"] != user_id or data["id"] != record_id:
                            raise store.Unavailable()
                        if obj is None:
                            obj = cls(**data)
                            db.add(obj)
                        else:
                            for key, value in data.items():
                                setattr(obj, key, value)
                        obj.remote_version = version
                    cursor = doc["sync_key"]
                db.flush()
                if len(batch) < 200:
                    break
            # Advance only after the local transaction succeeds below.
            db.info.setdefault("sync_cursors", {})[(user_id, kind)] = cursor
        cursors = dict(db.info.get("sync_cursors", {}))
    _cursors.update(cursors)
    if len(_cursors) > 3072:
        _cursors.clear()


def pull_work():
    owners = set()
    candidates = set()
    namespace = os.environ.get("HAYTILE_QUEUE_NAMESPACE", "main") + ":"
    for lower, upper in (
        (namespace + "queued_", namespace + "queued_\uf8ff"),
        (namespace + "active_", namespace + "active_" + now().isoformat()),
    ):
        for job_id, doc, _ in scan("jobs", "state_key", lower, upper, limit=20):
            owners.add(doc["user_id"])
            candidates.add(job_id)
    for user_id in owners:
        account = store.get(user_id)
        if account:
            store.hydrate(account)
            sync_user(user_id)
    return candidates


def capture(db, flush_context, instances):
    if not enabled() or db.info.get("remote_projection") or db.info.get("remote_writing"):
        return
    pending = db.info.setdefault("remote_pending", {})
    for obj in list(db.new) + list(db.dirty) + list(db.deleted):
        if type(obj) not in TYPES:
            continue
        state = inspect(obj)
        changed = {key for key in FIELDS[type(obj)] if state.attrs[key].history.has_changes()}
        fresh, deleted = obj in db.new, obj in db.deleted
        if not fresh and not deleted and not changed:
            continue
        entry = pending.setdefault(
            id(obj), {"obj": obj, "new": fresh, "fields": set(), "deleted": deleted}
        )
        entry["fields"].update(changed)
        entry["deleted"] = deleted


def before_commit(db):
    if not enabled() or db.info.get("remote_projection") or db.info.get("remote_writing"):
        return
    db.flush()
    pending = list(db.info.pop("remote_pending", {}).values())
    if not pending:
        return
    db.info["remote_writing"] = True
    token = hash_token(str(now().timestamp()) + ":" + str(id(db)))
    try:
        for attempt in range(8):
            writes, versions, banks, confirmations = [], [], {}, []
            for entry in pending:
                obj = entry["obj"]
                kind = TYPES[type(obj)]
                data = payload(obj)
                old = store.read(kind, obj.id)
                previous = unpack(old[0]) if old and not old[0].get("deleted") else None
                confirmations.append((kind, obj.id))
                if entry["deleted"]:
                    tombstone = {
                        "user_id": obj.user_id,
                        "deleted": 1,
                        "sync_key": obj.user_id + "_" + now().isoformat() + "_" + obj.id,
                        "write_token": token,
                    }
                    writes.append(
                        store.update_write(
                            kind,
                            obj.id,
                            tombstone,
                            version=old[1] if old else None,
                            create=not bool(old),
                        )
                    )
                    continue
                if not entry["new"]:
                    if not previous:
                        raise WriteUncertain()
                    if kind == "projects" and obj.remote_version != old[1]:
                        raise WriteUncertain()
                    data = {**previous, **{key: data[key] for key in entry["fields"]}}
                if kind == "jobs":
                    data["updated_at"] = now()
                    old_status = previous["status"] if previous else None
                    new_status = data["status"]
                    if old_status in ("completed", "failed") and new_status not in (
                        old_status,
                        "queued",
                    ):
                        raise WriteUncertain()
                    if (
                        old_status != "queued"
                        and new_status == "processing"
                        and "status" in entry["fields"]
                    ):
                        raise WriteUncertain()
                    if previous and previous["credits"] != data["credits"]:
                        raise WriteUncertain()
                    if not previous:
                        key = hash_token(obj.user_id + ":" + data["idempotency_key"])
                        existing = store.read("job_keys", key)
                        fp = fingerprint(data)
                        if existing:
                            if existing[0]["fingerprint"] != fp:
                                from fastapi import HTTPException

                                raise HTTPException(409, detail="IDEMPOTENCY_CONFLICT")
                            raise DuplicateJob(existing[0]["job_id"], obj.user_id)
                        writes.append(
                            store.update_write(
                                "job_keys",
                                key,
                                {
                                    "user_id": obj.user_id,
                                    "job_id": obj.id,
                                    "fingerprint": fp,
                                },
                                create=True,
                            )
                        )
                    credit = data["credits"]
                    reserve = new_status == "queued" and old_status in (None, "failed")
                    debit = new_status == "completed" and old_status in (
                        "processing",
                        "quality_check",
                    )
                    release = new_status == "failed" and old_status in (
                        "queued",
                        "processing",
                        "quality_check",
                    )
                    if credit and (reserve or debit or release):
                        if obj.user_id not in banks:
                            found = store.read("wallets", obj.user_id)
                            banks[obj.user_id] = [
                                wallets.validate(found[0]) if found else wallets.base(),
                                found[1] if found else None,
                            ]
                        bank, _ = banks[obj.user_id]
                        if reserve:
                            if bank.get("billing_hold"):
                                from fastapi import HTTPException

                                raise HTTPException(403, detail="BILLING_REVIEW_REQUIRED")
                            if bank["balance"] - bank["reserved"] < credit:
                                from fastapi import HTTPException

                                raise HTTPException(402, detail="INSUFFICIENT_CREDITS")
                            bank["reserved"] += credit
                        else:
                            if bank["reserved"] < credit:
                                raise WriteUncertain()
                            bank["reserved"] -= credit
                            if debit:
                                bank["balance"] -= credit
                        bank["updated_at"] = now()
                        event_kind = "reserve" if reserve else "debit" if debit else "release"
                        event_id = hash_token(
                            obj.id + ":" + event_kind + ":" + str(data["attempt"])
                        )
                        event_data = {
                            "user_id": obj.user_id,
                            "actor_id": obj.user_id,
                            "job_id": obj.id,
                            "amount": -credit if debit else 0,
                            "kind": event_kind,
                            "created_at": now(),
                            "fingerprint": fingerprint(data),
                            "ledger_key": obj.user_id + "_" + now().isoformat() + "_" + event_id,
                        }
                        writes.append(
                            store.update_write("wallet_events", event_id, event_data, create=True)
                        )
                for key, value in data.items():
                    setattr(obj, key, value)
                versions.append((obj, len(writes), kind))
                writes.append(
                    store.update_write(
                        kind,
                        obj.id,
                        document(data, kind, token),
                        version=old[1] if old else None,
                        create=not bool(old),
                    )
                )
            for user_id in {entry["obj"].user_id for entry in pending}:
                account = store.read("accounts", user_id)
                if not account or account[0].get("status") != "active":
                    raise WriteUncertain()
                writes.append(
                    store.update_write("accounts", user_id, account[0], version=account[1])
                )
            for user_id, (bank, version) in banks.items():
                writes.append(
                    store.update_write(
                        "wallets",
                        user_id,
                        bank,
                        version=version,
                        create=not bool(version),
                    )
                )
            try:
                result = store.commit(writes)
            except store.Conflict:
                continue
            except store.Unavailable:
                try:
                    if not all(
                        (found := store.read(kind, record_id))
                        and found[0].get("write_token") == token
                        for kind, record_id in confirmations
                    ):
                        raise WriteUncertain()
                    result = {}
                except store.Unavailable:
                    raise WriteUncertain() from None
            db.info["remote_committed"] = True
            results = (result or {}).get("writeResults", [])
            for obj, index, kind in versions:
                obj.remote_version = (
                    results[index].get("updateTime")
                    if index < len(results)
                    else store.read(kind, obj.id)[1]
                )
            db.flush()
            return
        raise WriteUncertain()
    finally:
        db.info.pop("remote_writing", None)


def clear_pending(db):
    db.info.pop("remote_pending", None)
    db.info.pop("remote_writing", None)
    if db.info.pop("remote_committed", False):
        raise WriteUncertain()


def after_commit(db):
    db.info.pop("remote_committed", None)


def purge_user(user_id):
    for kind in ("assets", "jobs", "projects"):
        while True:
            batch = scan(kind, "sort_key", user_id + "_", user_id + "_\uf8ff")
            if not batch:
                break
            store.commit(
                [store.delete_write(kind, key, version=version) for key, _, version in batch]
            )
    for key in list(_cursors):
        if key[0] == user_id:
            del _cursors[key]


event.listen(Session.class_, "before_flush", capture)
event.listen(Session.class_, "before_commit", before_commit)
event.listen(Session.class_, "after_rollback", clear_pending)

event.listen(Session.class_, "after_commit", after_commit)
