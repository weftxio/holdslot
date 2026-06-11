"""Client (tenant) routes — /me and the membership-scoped client list/create.

These power the login landing + client switcher (§8). The list is always scoped to the
caller's memberships, so a user only ever sees tenants they belong to.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AccessContext, get_current_user, get_db, require_membership
from app.domains.clients.schemas import ClientCreateIn, ClientOut, MeOut, slugify
from app.models import AppUser, Membership, MembershipRole, Tenant

router = APIRouter(tags=["clients"])


def _clients_for(db: Session, user: AppUser) -> list[ClientOut]:
    rows = db.execute(
        select(Tenant, Membership.role)
        .join(Membership, Membership.tenant_id == Tenant.id)
        .where(Membership.user_id == user.id)
        .order_by(Tenant.name)
    ).all()
    return [ClientOut(slug=t.slug, name=t.name, role=role.value) for t, role in rows]


@router.get("/me", response_model=MeOut)
def me(user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    return MeOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        clients=_clients_for(db, user),
    )


@router.get("/clients", response_model=list[ClientOut])
def list_clients(
    user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ClientOut]:
    return _clients_for(db, user)


@router.post("/clients", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    body: ClientCreateIn,
    user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientOut:
    # Dedupe slug (name -> slug, suffixing on collision).
    base = slugify(body.name)
    slug, i = base, 2
    while db.execute(select(Tenant.id).where(Tenant.slug == slug)).first() is not None:
        slug, i = f"{base}-{i}", i + 1
    tenant = Tenant(slug=slug, name=body.name)
    db.add(tenant)
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.owner))
    db.commit()
    return ClientOut(slug=tenant.slug, name=tenant.name, role=MembershipRole.owner.value)


@router.get("/{client}/context", response_model=ClientOut)
def client_context(ctx: AccessContext = Depends(require_membership())) -> ClientOut:
    """Resolve + authorize the caller against the `[client]` tenant (the central guard).

    The console shell calls this on entry to confirm access and learn the caller's role.
    A non-member gets 404 (tenant existence isn't leaked); an owner-gated variant passes
    `require_membership(MembershipRole.owner)`.
    """
    return ClientOut(slug=ctx.tenant.slug, name=ctx.tenant.name, role=ctx.role.value)
