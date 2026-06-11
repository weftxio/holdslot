"""Auth routes — login, refresh, forgot, reset."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_db
from app.core.email import send_email
from app.core.security import (
    as_utc,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.domains.auth.schemas import (
    ForgotIn,
    LoginIn,
    LoginOut,
    RefreshIn,
    ResetIn,
    TokenPair,
    UserOut,
)
from app.domains.auth.service import issue_tokens, rotate_refresh
from app.models import AppUser, PasswordReset, RefreshToken, UserStatus

router = APIRouter(prefix="/auth", tags=["auth"])


def _norm(email: str) -> str:
    return email.strip().lower()


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> LoginOut:
    user = db.execute(
        select(AppUser).where(AppUser.email == _norm(body.email))
    ).scalar_one_or_none()
    # Verify even when the user is missing is overkill here; a generic 401 avoids leaking.
    if (
        user is None
        or user.status != UserStatus.active
        or not verify_password(user.password_hash, body.password)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    user.last_login_at = datetime.now(UTC)
    pair = issue_tokens(db, user)
    return LoginOut(
        **pair.model_dump(),
        user=UserOut(id=str(user.id), email=user.email, full_name=user.full_name),
    )


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> TokenPair:
    result = rotate_refresh(db, body.refresh_token)
    if result is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")
    _user, pair = result
    return pair


@router.post("/forgot", status_code=status.HTTP_202_ACCEPTED)
def forgot(body: ForgotIn, db: Session = Depends(get_db)) -> dict[str, str]:
    s = get_settings()
    user = db.execute(
        select(AppUser).where(AppUser.email == _norm(body.email))
    ).scalar_one_or_none()
    # Always 202, whether or not the email exists — don't reveal account existence.
    if user is not None:
        token = new_opaque_token()
        db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(seconds=s.reset_ttl_seconds),
            )
        )
        db.commit()
        link = f"{s.web_base_url}/login?reset={quote(token)}"
        send_email(
            user.email,
            "Reset your HoldSlot password",
            "We received a request to reset your HoldSlot password.\n\n"
            f"Set a new password (link valid 1 hour):\n{link}\n\n"
            "If you didn't request this, you can ignore this email.\n",
        )
    return {"status": "accepted"}


@router.post("/reset", status_code=status.HTTP_200_OK)
def reset(body: ResetIn, db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.execute(
        select(PasswordReset).where(PasswordReset.token_hash == hash_token(body.token))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or as_utc(row.expires_at) < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired token")
    user = db.get(AppUser, row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid token")
    user.password_hash = hash_password(body.new_password)
    row.used_at = now
    # Revoke all outstanding refresh tokens on password change.
    for rt in db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
    ).scalars():
        rt.revoked_at = now
    db.commit()
    return {"status": "reset"}
