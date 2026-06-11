"""Security primitives — argon2 password hashing, token hashing, and JWT access/refresh.

Pure functions: keys and TTLs are passed in, so this module is unit-testable with no AWS
or DB. The app layer wires the real keys from `config.get_settings()`.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()
_ALG = "HS256"


def as_utc(dt: datetime) -> datetime:
    """Coerce a DB datetime to tz-aware UTC. The Data API returns timestamptz as naive
    (UTC) values, so comparisons against datetime.now(UTC) must normalize first."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# ---- passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# ---- opaque-token hashing (refresh + reset tokens stored hashed) -------------


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 hex — refresh/reset tokens are stored hashed, never raw."""
    return hashlib.sha256(token.encode()).hexdigest()


# ---- JWT ---------------------------------------------------------------------


def create_access_token(user_id: str, key: str, ttl_seconds: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, key, algorithm=_ALG)


def create_refresh_token(user_id: str, key: str, ttl_seconds: int) -> tuple[str, str]:
    """Returns (token, jti). The jti lets us track/revoke the refresh token in the DB."""
    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, key, algorithm=_ALG), jti


def decode_token(token: str, key: str, expected_type: str) -> dict[str, Any]:
    """Decode + verify signature/exp and the token type. Raises jwt exceptions on failure."""
    payload = jwt.decode(token, key, algorithms=[_ALG])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return payload
