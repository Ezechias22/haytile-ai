"""Configuration gates. Passing these checks is not full product certification."""

import os
from urllib.parse import urlsplit


def configuration_checks(environ, dialect):
    origin = urlsplit(environ.get("HAYTILE_PUBLIC_ORIGIN", ""))
    endpoint = environ.get("STORAGE_ENDPOINT", "")
    return {
        "postgresql": dialect == "postgresql",
        "https_origin": origin.scheme == "https" and bool(origin.hostname) and not origin.username,
        "explicit_signing_key": len(environ.get("HAYTILE_SIGNING_KEY", "")) >= 32,
        "private_object_storage_configured": bool(environ.get("STORAGE_BUCKET")),
        "storage_tls": not endpoint or urlsplit(endpoint).scheme == "https",
        "smtp_configured": bool(environ.get("SMTP_HOST") and environ.get("SMTP_FROM")),
    }


def require_durable_runtime(dialect):
    if os.environ.get("HAYTILE_ENV") != "production" or os.environ.get("HAYTILE_FREE_BETA") == "1":
        return
    checks = configuration_checks(os.environ, dialect)
    required = (
        "postgresql",
        "https_origin",
        "explicit_signing_key",
        "private_object_storage_configured",
        "storage_tls",
    )
    failed = [name for name in required if not checks[name]]
    if failed:
        raise RuntimeError("Production runtime prerequisites missing: " + ", ".join(failed))
