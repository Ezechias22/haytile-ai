import hashlib
import hmac
import os
import secrets
import tempfile
import time

from .db import ROOT

KEYFILE = ROOT / "signing.key"
if not KEYFILE.exists():
    # Publish a completely written key atomically; API and worker may start together.
    fd, temporary = tempfile.mkstemp(prefix="signing-", dir=ROOT)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_hex(32))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, KEYFILE)
        except FileExistsError:
            pass
    finally:
        os.unlink(temporary)
SIGNING_KEY = os.environ.get("HAYTILE_SIGNING_KEY") or KEYFILE.read_text().strip()
if len(SIGNING_KEY) < 32:
    raise RuntimeError("Signing key must contain at least 32 characters.")


def hash_token(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + ":" + digest.hex()


def verify_password(password, stored):
    try:
        salt, expected = stored.split(":")
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
        )
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def sign_asset(asset_id, expires):
    return hmac.new(
        SIGNING_KEY.encode(), f"{asset_id}:{expires}".encode(), hashlib.sha256
    ).hexdigest()


def valid_signature(asset_id, expires, signature):
    return int(time.time()) <= expires <= int(
        time.time()
    ) + 900 and hmac.compare_digest(sign_asset(asset_id, expires), signature)
