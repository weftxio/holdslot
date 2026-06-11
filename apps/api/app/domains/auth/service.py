"""Auth service — token issuing + refresh rotation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select
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
from app.models import AppUser, RefreshToken


def issue_tokens(db: Session, user: AppUser) -> TokenPair:
    s = get_settings()
    access = create_access_token(str(user.id), s.jwt_signing_key, s.access_ttl_seconds)
    refresh, _jti = create_refresh_token(str(user.id), s.jwt_refresh_key, s.refresh_ttl_seconds)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            expires_at=datetime.now(UTC) + timedelta(seconds=s.refresh_ttl_seconds),
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
    if user is None:
        return None

    row.revoked_at = now  # single-use: old token can't be reused
    db.flush()
    return user, issue_tokens(db, user)
