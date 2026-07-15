"""Client (tenant) routes — /me and the membership-scoped client list/create.

These power the login landing + client switcher (§8). The list is always scoped to the
caller's memberships, so a user only ever sees tenants they belong to.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.core.deps import AccessContext, get_current_user, get_db, require_membership
from app.domains.clients.schemas import (
    ClientCreateIn,
    ClientOut,
    LlmUsageOut,
    LlmUsageRow,
    MeOut,
    UiPrefs,
    UiPrefsIn,
    slugify,
)
from app.models import AppUser, LlmCall, Membership, MembershipRole, Tenant

router = APIRouter(tags=["clients"])


def _llm_month_bucket():
    """The UTC `YYYY-MM` month bucket for the NF-4 llm-usage rollup. The date_trunc / timezone /
    to_char format args are SQL literals (literal_column), NOT bound params: a bound param makes the
    SELECT and GROUP BY copies of this expression differ textually, so Postgres rejects the query
    ("created_at must appear in the GROUP BY clause") — a live-caught bug (test_clients)."""
    return func.to_char(
        func.date_trunc(
            literal_column("'month'"), func.timezone(literal_column("'UTC'"), LlmCall.created_at)
        ),
        literal_column("'YYYY-MM'"),
    )


def _clients_for(db: Session, user: AppUser) -> list[ClientOut]:
    rows = db.execute(
        select(Tenant, Membership.role)
        .join(Membership, Membership.tenant_id == Tenant.id)
        .where(Membership.user_id == user.id)
        .order_by(Tenant.name)
    ).all()
    return [ClientOut(slug=t.slug, name=t.name, role=role.value) for t, role in rows]


def _me_out(db: Session, user: AppUser) -> MeOut:
    return MeOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        clients=_clients_for(db, user),
        # Unknown keys in the stored bag are ignored; a missing bag falls back to the defaults.
        ui_prefs=UiPrefs(**(user.ui_prefs or {})),
    )


@router.get("/me", response_model=MeOut)
def me(user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    return _me_out(db, user)


@router.put("/me/prefs", response_model=MeOut)
def update_me_prefs(
    body: UiPrefsIn,
    user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeOut:
    """Persist the caller's console UI preferences (account-scoped, so they follow across devices).
    A partial merge: only the fields the caller sends overwrite the stored bag. Reassign a new dict
    (not in-place mutation) so SQLAlchemy flags the JSONB column dirty."""
    updates = body.model_dump(exclude_none=True)
    if updates:
        user.ui_prefs = {**(user.ui_prefs or {}), **updates}
        db.commit()
    return _me_out(db, user)


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


@router.get("/{client}/llm-usage", response_model=LlmUsageOut)
def llm_usage(
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> LlmUsageOut:
    """NF-4 — owner-only AI-COGS read: the `llm_call` telemetry grouped by month × purpose × model
    with call/token/cost sums. The single source stays `llm_call`; this is a derived rollup (no
    stored counters, the Phase-D rule). Swagger is the MVP surface — the FE panel + the spend alarm
    land at cutover (GP, new-AWS-resource posture). Months bucket in UTC."""
    month = _llm_month_bucket()
    rows = db.execute(
        select(
            month.label("month"),
            LlmCall.purpose,
            LlmCall.model,
            func.count().label("calls"),
            func.coalesce(func.sum(LlmCall.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(LlmCall.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(LlmCall.cost_usd), 0).label("cost_usd"),
        )
        .where(LlmCall.tenant_id == ctx.tenant.id)
        .group_by(month, LlmCall.purpose, LlmCall.model)
        .order_by(month.desc(), func.coalesce(func.sum(LlmCall.cost_usd), 0).desc())
    ).all()
    out_rows = [
        LlmUsageRow(
            month=r.month,
            purpose=r.purpose,
            model=r.model,
            calls=r.calls,
            input_tokens=int(r.input_tokens),
            output_tokens=int(r.output_tokens),
            cost_usd=float(r.cost_usd),
        )
        for r in rows
    ]
    return LlmUsageOut(
        rows=out_rows,
        total_cost_usd=round(sum(r.cost_usd for r in out_rows), 6),
        total_calls=sum(r.calls for r in out_rows),
    )


@router.get("/{client}/context", response_model=ClientOut)
def client_context(ctx: AccessContext = Depends(require_membership())) -> ClientOut:
    """Resolve + authorize the caller against the `[client]` tenant (the central guard).

    The console shell calls this on entry to confirm access and learn the caller's role.
    A non-member gets 404 (tenant existence isn't leaked); an owner-gated variant passes
    `require_membership(MembershipRole.owner)`.
    """
    return ClientOut(slug=ctx.tenant.slug, name=ctx.tenant.name, role=ctx.role.value)
