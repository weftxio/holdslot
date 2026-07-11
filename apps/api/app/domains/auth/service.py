"""Auth service — token issuing + refresh rotation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    as_utc,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)
from app.domains.auth.schemas import TokenPair
from app.models import AppUser, RefreshToken, UserStatus


def issue_tokens(db: Session, user: AppUser) -> TokenPair:
    s = get_settings()
    now = datetime.now(UTC)
    # N36 — opportunistically prune this user's EXPIRED refresh tokens so the table can't grow
    # unbounded (one row per login/rotation). Cheap, user-scoped, no scheduler needed; runs on every
    # login and rotation since both mint a token.
    db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.expires_at < now
        )
    )
    access = create_access_token(str(user.id), s.jwt_signing_key, s.access_ttl_seconds)
    refresh, _jti = create_refresh_token(str(user.id), s.jwt_refresh_key, s.refresh_ttl_seconds)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            expires_at=now + timedelta(seconds=s.refresh_ttl_seconds),
        )
    )
    db.commit()
    return TokenPair(access_token=access, refresh_token=refresh)


def rotate_refresh(db: Session, raw_refresh: str) -> tuple[AppUser, TokenPair] | None:
    """Verify + single-use rotate a refresh token. Returns None if invalid/expired/revoked."""
    s = get_settings()
    try:
        payload = decode_token(raw_refresh, s.jwt_refresh_key, "refresh")
    except jwt.PyJWTError:
        return None

    row = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or as_utc(row.expires_at) < now:
        return None

    user = db.get(AppUser, payload["sub"])
    # N9 — a disabled user must not be able to keep minting access tokens by rotating a still-valid
    # refresh token. Reject here too (defence in depth: deps.py also rejects a non-active user on
    # the access path), and do NOT revoke the presented token — a re-enabled user can then resume.
    if user is None or user.status != UserStatus.active:
        return None

    # N33 — consume the token with a GUARDED conditional UPDATE (revoked_at IS NULL) and require
    # rowcount == 1. Two concurrent rotations of the same token both pass the read check above, but
    # only one can win this write; the loser gets rowcount 0 and is rejected — so single-use is
    # atomic, not a read-then-write race that could mint two token pairs from one refresh token.
    consumed = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if consumed.rowcount != 1:
        return None
    return user, issue_tokens(db, user)
