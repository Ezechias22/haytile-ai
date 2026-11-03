"""Durable account authority in Firestore; SQL is an expendable identity projection.

No ADC, plaintext passwords, raw session tokens, or silent local-auth fallback.
Wallets, jobs and project metadata are deliberately not mirrored by this adapter.
"""

import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from . import firestore_limits as transport
from .db import Session, User, now, uid
from .security import hash_token
from .trials import lock_sqlite_write


class Unavailable(Exception):
    pass


class Conflict(Exception):
    pass


class DuplicateEmail(Exception):
    pass


def enabled():
    return os.environ.get("HAYTILE_ACCOUNT_PROVIDER", "sql") == "firestore"


def root():
    try:
        return transport.document_url("accounts-root").split("/documents/")[0]
    except transport.LimitUnavailable:
        raise Unavailable() from None


def name(collection, key):
    if collection not in (
        "accounts",
        "wallets",
        "wallet_events",
        "account_emails",
        "sessions",
        "password_resets",
        "account_audit",
    ) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", key):
        raise Unavailable()
    return root().split("/v1/", 1)[1] + "/documents/haytile_" + collection + "/" + key


def request(method, suffix, **kwargs):
    try:
        response = transport.request(method, root() + suffix, **kwargs)
    except transport.LimitUnavailable:
        raise Unavailable() from None
    if response.status_code >= 500 or response.status_code in (401, 403, 429):
        raise Unavailable()
    return response


def encode(data):
    fields = {}
    for key, value in data.items():
        if isinstance(value, str):
            fields[key] = {"stringValue": value}
        elif isinstance(value, datetime):
            fields[key] = {"timestampValue": value.isoformat()}
        elif type(value) is int:
            fields[key] = {"integerValue": str(value)}
        else:
            raise Unavailable()
    return fields


def decode(document):
    try:
        values = {}
        for key, value in document.get("fields", {}).items():
            if "stringValue" in value:
                values[key] = value["stringValue"]
            elif "timestampValue" in value:
                values[key] = datetime.fromisoformat(
                    value["timestampValue"].replace("Z", "+00:00")
                )
            elif "integerValue" in value:
                values[key] = int(value["integerValue"])
            else:
                raise ValueError()
        return values
    except (TypeError, KeyError, ValueError):
        raise Unavailable() from None


def read(collection, key):
    response = request(
        "GET", "/documents/" + name(collection, key).split("/documents/", 1)[1]
    )
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise Unavailable()
    doc = response.json()
    return decode(doc), doc["updateTime"]


def update_write(collection, key, data, version=None, create=False):
    result = {"update": {"name": name(collection, key), "fields": encode(data)}}
    if create:
        result["currentDocument"] = {"exists": False}
    elif version:
        result["currentDocument"] = {"updateTime": version}
    return result


def delete_write(collection, key, version=None):
    result = {"delete": name(collection, key)}
    if version:
        result["currentDocument"] = {"updateTime": version}
    return result


def commit(writes):
    response = request("POST", "/documents:commit", json={"writes": writes})
    if response.status_code == 200:
        return
    try:
        conflict = response.json().get("error", {}).get("status") in (
            "ABORTED",
            "ALREADY_EXISTS",
            "FAILED_PRECONDITION",
        )
    except ValueError:
        conflict = False
    if conflict or response.status_code in (409, 412):
        raise Conflict()
    raise Unavailable()


def audit_write(actor, action, user_id):
    return update_write(
        "account_audit",
        uid(),
        {"actor_id": actor, "action": action, "user_id": user_id, "created_at": now()},
        create=True,
    )


def validate(data):
    try:
        if (
            data["status"] != "active"
            or data["role"] not in ("user", "admin")
            or not re.fullmatch(r"[0-9a-f]{32}:[0-9a-f]{128}", data["password"])
            or not data["id"]
            or not data["email"]
            or not data["epoch"]
            or not isinstance(data["created_at"], datetime)
        ):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise Unavailable() from None
    return data


def get(user_id):
    found = read("accounts", user_id)
    if not found or found[0].get("status") != "active":
        return None
    return validate(found[0])


def by_email(email):
    index = read("account_emails", hash_token(email.strip().lower()))
    if not index:
        return None
    data = get(index[0]["user_id"])
    if data and data["email"] != email.strip().lower():
        raise Unavailable()
    return data


def create(email, password, display_name, locale, existing=None):
    data = {
        "id": existing.id if existing else uid(),
        "email": email,
        "password": password,
        "name": display_name,
        "locale": locale,
        "role": existing.role if existing else "user",
        "epoch": secrets.token_hex(16),
        "status": "active",
        "created_at": existing.created_at.replace(tzinfo=timezone.utc)
        if existing and existing.created_at.tzinfo is None
        else existing.created_at
        if existing
        else now(),
    }
    try:
        commit(
            [
                update_write("accounts", data["id"], data, create=True),
                update_write(
                    "account_emails",
                    hash_token(email),
                    {"user_id": data["id"]},
                    create=True,
                ),
                audit_write(data["id"], "account.create", data["id"]),
            ]
        )
    except Conflict:
        raise DuplicateEmail() from None
    return data


def hydrate(data):
    """Rebuild only identity columns. Never overwrite existing SQL wallet balances."""
    try:
        with Session.begin() as db:
            lock_sqlite_write(db)
            user = db.get(User, data["id"])
            if user is None:
                user = User(id=data["id"], email=data["email"], balance=0, reserved=0)
                db.add(user)
            for key in ("email", "password", "name", "locale", "role", "created_at"):
                setattr(user, key, data[key])
            db.flush()
        return user
    except IntegrityError:
        raise Unavailable() from None


def session(data, digest, expires):
    for _ in range(5):
        found = read("accounts", data["id"])
        if (
            not found
            or found[0].get("status") != "active"
            or found[0]["epoch"] != data["epoch"]
        ):
            return False
        latest, version = found
        try:
            commit(
                [
                    update_write("accounts", data["id"], latest, version=version),
                    update_write(
                        "sessions",
                        digest,
                        {
                            "user_id": data["id"],
                            "epoch": data["epoch"],
                            "expires_at": expires,
                        },
                        create=True,
                    ),
                ]
            )
            return True
        except Conflict:
            continue
    raise Unavailable()


def resolve(digest):
    stored = read("sessions", digest)
    if not stored or stored[0]["expires_at"] <= now():
        return None
    data = get(stored[0]["user_id"])
    if not data or data["epoch"] != stored[0]["epoch"]:
        return None
    return data


def logout(digest):
    commit([delete_write("sessions", digest)])


def change(user_id, fields, actor=None):
    for _ in range(5):
        found = read("accounts", user_id)
        if not found or found[0].get("status") != "active":
            raise Unavailable()
        data, version = found
        data.update(fields)
        validate(data)
        try:
            commit(
                [
                    update_write("accounts", user_id, data, version=version),
                    audit_write(
                        actor or user_id,
                        "account.role" if "role" in fields else "account.profile",
                        user_id,
                    ),
                ]
            )
            return data
        except Conflict:
            continue
    raise Unavailable()


def remove(user_id):
    for _ in range(5):
        found = read("accounts", user_id)
        if not found or found[0].get("status") != "active":
            return
        data, version = found
        try:
            commit(
                [
                    update_write(
                        "accounts",
                        user_id,
                        {"id": user_id, "status": "deleted", "deleted_at": now()},
                        version=version,
                    ),
                    delete_write("account_emails", hash_token(data["email"])),
                    delete_write("wallets", user_id),
                    audit_write(user_id, "account.delete", user_id),
                ]
            )
            return
        except Conflict:
            continue
    raise Unavailable()


def issue_reset(data, digest):
    # Epoch binds the reset to the current password; old reset codes cannot reset a newer password.
    commit(
        [
            update_write(
                "password_resets",
                digest,
                {
                    "user_id": data["id"],
                    "epoch": data["epoch"],
                    "expires_at": now() + timedelta(minutes=20),
                },
                create=True,
            )
        ]
    )


def reset_password(digest, hashed_password):
    found = read("password_resets", digest)
    if not found or found[0]["expires_at"] <= now():
        return False
    reset, reset_version = found
    current = read("accounts", reset["user_id"])
    if (
        not current
        or current[0].get("status") != "active"
        or current[0]["epoch"] != reset["epoch"]
    ):
        return False
    data, version = current
    data.update(password=hashed_password, epoch=secrets.token_hex(16))
    try:
        commit(
            [
                update_write("accounts", data["id"], data, version=version),
                delete_write("password_resets", digest, version=reset_version),
                audit_write(data["id"], "account.password_reset", data["id"]),
            ]
        )
    except Conflict:
        return False
    hydrate(data)
    return True


def directory(search="", offset=0):
    # Email-prefix query uses a single-field index; no full-account scan.
    prefix = search.strip().lower()
    filters = [
        {
            "fieldFilter": {
                "field": {"fieldPath": "email"},
                "op": "GREATER_THAN_OR_EQUAL",
                "value": {"stringValue": prefix},
            }
        }
    ]
    if prefix:
        filters.append(
            {
                "fieldFilter": {
                    "field": {"fieldPath": "email"},
                    "op": "LESS_THAN",
                    "value": {"stringValue": prefix + "\uf8ff"},
                }
            }
        )
    where = (
        filters[0]
        if len(filters) == 1
        else {"compositeFilter": {"op": "AND", "filters": filters}}
    )
    query = {"from": [{"collectionId": "haytile_accounts"}], "where": where}
    count = request(
        "POST",
        "/documents:runAggregationQuery",
        json={
            "structuredAggregationQuery": {
                "structuredQuery": query,
                "aggregations": [{"alias": "total", "count": {}}],
            }
        },
    )
    if count.status_code != 200:
        raise Unavailable()
    try:
        total = sum(
            int(
                x.get("result", {})
                .get("aggregateFields", {})
                .get("total", {})
                .get("integerValue", 0)
            )
            for x in count.json()
        )
    except (TypeError, ValueError):
        raise Unavailable() from None
    query.update(
        orderBy=[{"field": {"fieldPath": "email"}, "direction": "ASCENDING"}],
        limit=25,
        offset=offset,
    )
    response = request("POST", "/documents:runQuery", json={"structuredQuery": query})
    if response.status_code != 200:
        raise Unavailable()
    return [
        validate(decode(x["document"])) for x in response.json() if "document" in x
    ], total


def audit():
    response = request(
        "POST",
        "/documents:runQuery",
        json={
            "structuredQuery": {
                "from": [{"collectionId": "haytile_account_audit"}],
                "orderBy": [
                    {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
                ],
                "limit": 30,
            }
        },
    )
    if response.status_code != 200:
        raise Unavailable()
    return [
        {
            "action": d["action"],
            "created_at": d["created_at"],
            "details": {
                k: d[k]
                for k in ("actor_id", "user_id", "amount", "plan", "days", "reason")
                if k in d
            },
        }
        for d in (decode(x["document"]) for x in response.json() if "document" in x)
    ]


def migrate_local():
    """Import surviving SQL identities before serving; never overwrite remote credentials."""
    with Session() as db:
        users = list(db.scalars(select(User)))
    for user in users:
        original = read("accounts", user.id)
        if original and original[0].get("status") == "deleted":
            continue
        existing = by_email(user.email)
        if existing:
            if existing["id"] != user.id:
                raise Unavailable()
            continue
        try:
            create(user.email, user.password, user.name, user.locale, existing=user)
        except DuplicateEmail:
            existing = by_email(user.email)
            if not existing or existing["id"] != user.id:
                raise Unavailable() from None
