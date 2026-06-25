"""FastAPI dependencies — DB session, current user, and the single central access guard.

Every tenant-scoped route depends on `require_membership(...)`, which resolves
request → user → membership(tenant) and enforces tenant scope × role in one place. There
is deliberately no per-route permission table; role lives on the membership row and the
rule lives here.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import ensure_awake, get_session
from app.core.security import decode_token
from app.models import AppUser, Membership, MembershipRole, Tenant, UserStatus

_bearer = HTTPBearer(auto_error=False)
log = logging.getLogger("holdslot.auth")


def get_db() -> Iterator[Session]:
    db = get_session()
    try:
        # Request-path wake budget (~18s) stays inside the 30s API-Gateway cap, so a still-resuming
        # Aurora raises a retryable signal that the DBAPIError handler turns into a clean 503 (W6) —
        # rather than the gateway killing the request at 30s. The web app retries the 503 with a
        # "waking the database…" message. Scripts/migrations keep the longer default budget.
        ensure_awake(db, attempts=3, delay_seconds=6.0)
        yield db
    finally:
        db.close()


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AppUser:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    s = get_settings()
    try:
        payload = decode_token(creds.credentials, s.jwt_signing_key, "access")
    except jwt.PyJWTError as e:
        log.warning("auth: invalid token")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from e
    user = db.get(AppUser, payload["sub"])
    if user is None or user.status != UserStatus.active:
        log.warning("auth: inactive or unknown user sub=%s", payload.get("sub"))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "inactive or unknown user")
    return user


@dataclass
class AccessContext:
    user: AppUser
    tenant: Tenant
    membership: Membership

    @property
    def role(self) -> MembershipRole:
        return self.membership.role


def require_membership(min_role: MembershipRole | None = None):
    """Dependency factory. `min_role=owner` restricts to owners; default allows any member.

    The tenant comes from the `[client]` path segment (its slug). A user with no membership
    in that tenant gets 404 (not 403) so tenant existence isn't leaked across tenants.
    """

    def dependency(
        request: Request,
        user: AppUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> AccessContext:
        slug = request.path_params.get("client")
        if not slug:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing client slug")
        row = db.execute(
            select(Membership, Tenant)
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .where(Tenant.slug == slug, Membership.user_id == user.id)
        ).first()
        if row is None:
            log.warning("authz: membership denied user=%s slug=%s", user.id, slug)
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such client")
        membership, tenant = row
        if min_role == MembershipRole.owner and membership.role != MembershipRole.owner:
            log.warning("authz: owner role required user=%s slug=%s", user.id, slug)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "owner role required")
        return AccessContext(user=user, tenant=tenant, membership=membership)

    return dependency
