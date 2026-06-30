"""Batch routes — the console (JWT, owner) Sendout-batch + client-approval surface (Phase D).

D2: create a batch + `prospect_approval(pending)` rows from an enriched selection · list with
DERIVED counts · company-grouped detail · the step-3 human-fallback decide. D3: the per-tenant
sendout template (GET/PUT) + the tokenized approval send (mint `approval_link`, SES `send_email`).
Tenant scope × role is the A4 central guard; the public token-only client surface is `approvals`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import AccessContext, get_db, require_membership
from app.core.email import send_email
from app.core.security import hash_token, new_opaque_token
from app.domains.batches import service as svc
from app.domains.batches.schemas import (
    BatchCompanyGroup,
    BatchCreateIn,
    BatchDetailOut,
    BatchOut,
    BatchProspect,
    DecisionIn,
    SendIn,
    TemplateIn,
    TemplateOut,
)
from app.models import ApprovalLink, Batch, Company, Icp, MembershipRole, Prospect, ProspectApproval

router = APIRouter(tags=["batches"])
log = logging.getLogger("holdslot.batches")


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse_ids(raw: list[str]) -> list[uuid.UUID]:
    """Parse client-supplied id strings to UUIDs, 400 on any malformed value (mirrors prospects)."""
    try:
        return [uuid.UUID(i) for i in raw]
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid id") from exc


def _icp_name_map(
    db: Session, tenant_id: uuid.UUID, ids: list[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    """ICP id → name, tenant-scoped — a cross-tenant id resolves to nothing, never another
    client's ICP name."""
    real = [i for i in ids if i]
    if not real:
        return {}
    rows = db.execute(
        select(Icp.id, Icp.name).where(Icp.tenant_id == tenant_id, Icp.id.in_(real))
    ).all()
    return {r[0]: r[1] or "" for r in rows}


def _batch_out(batch: Batch, counts: dict[str, int], icp_name: str) -> BatchOut:
    return BatchOut(
        id=str(batch.id),
        name=batch.name or "",
        icp=icp_name,
        status=batch.status,
        total=counts["total"],
        approved=counts["approved"],
        removed=counts["removed"],
        pending=counts["pending"],
        created_at=_iso(batch.created_at),
        sent_at=_iso(batch.sent_at),
        decided_at=_iso(batch.decided_at),
    )


def _load_batch(db: Session, tenant_id: uuid.UUID, batch_id: str) -> Batch:
    try:
        pk = uuid.UUID(batch_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such batch") from e
    batch = db.execute(
        select(Batch).where(Batch.id == pk, Batch.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such batch")
    return batch


# --------------------------------------------------------------------------- D2: list / create


@router.get("/{client}/batches", response_model=list[BatchOut])
def list_batches(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[BatchOut]:
    """All batches for the client, newest first, with derived total/approved/removed/pending counts.
    Batches are few per tenant, so this is an unpaginated list (no cursor)."""
    batches = (
        db.execute(
            select(Batch)
            .where(Batch.tenant_id == ctx.tenant.id)
            .order_by(Batch.created_at.desc(), Batch.id.desc())
        )
        .scalars()
        .all()
    )
    counts = svc.count_map(db, [b.id for b in batches])
    names = _icp_name_map(db, ctx.tenant.id, [b.icp_id for b in batches])
    empty = {"total": 0, "approved": 0, "removed": 0, "pending": 0}
    return [
        _batch_out(b, counts.get(b.id, empty), names.get(b.icp_id, "")) for b in batches
    ]


@router.post("/{client}/batches", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
def create_batch(
    body: BatchCreateIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> BatchOut:
    """Group an enriched-prospect selection into a `draft` batch + one `prospect_approval(pending)`
    row per prospect (the billable rows). Auto-names `Batch N` and infers a shared ICP when omitted.
    """
    if not body.prospect_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select prospects first")
    ids = _parse_ids(body.prospect_ids)
    prospects = (
        db.execute(
            select(Prospect).where(Prospect.tenant_id == ctx.tenant.id, Prospect.id.in_(ids))
        )
        .scalars()
        .all()
    )
    if not prospects:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no matching prospects")

    # ICP: explicit override wins (validated as the tenant's own); else the prospects' common ICP
    # (only when they all share one).
    if body.icp_id:
        icp_id: uuid.UUID | None = _parse_ids([body.icp_id])[0]
        owned = db.execute(
            select(Icp.id).where(Icp.id == icp_id, Icp.tenant_id == ctx.tenant.id)
        ).scalar_one_or_none()
        if owned is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such ICP")
    else:
        icp_ids = {p.icp_id for p in prospects}
        icp_id = next(iter(icp_ids)) if len(icp_ids) == 1 else None

    if body.name and body.name.strip():
        name = body.name.strip()
    else:
        existing = db.execute(
            select(func.count()).select_from(Batch).where(Batch.tenant_id == ctx.tenant.id)
        ).scalar_one()
        name = f"Batch {existing + 1}"

    batch = Batch(tenant_id=ctx.tenant.id, name=name, status=svc.DRAFT, icp_id=icp_id)
    db.add(batch)
    db.flush()  # need batch.id for the child rows
    for p in prospects:
        db.add(
            ProspectApproval(
                tenant_id=ctx.tenant.id,
                batch_id=batch.id,
                prospect_id=p.id,
                decision=svc.PENDING,
            )
        )
    db.commit()
    db.refresh(batch)
    counts = svc.counts_for(db, batch.id)
    names = _icp_name_map(db, ctx.tenant.id, [batch.icp_id])
    return _batch_out(batch, counts, names.get(batch.icp_id, ""))


# --------------------------------------------------------------------------- D2: detail


@router.get("/{client}/batches/{batch_id}", response_model=BatchDetailOut)
def get_batch(
    batch_id: str,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> BatchDetailOut:
    """Company-grouped prospect detail for one batch (FULL data — the operator owns it; the masked
    view is the external surface). Drives the Sendout Batch tab's expandable rows."""
    batch = _load_batch(db, ctx.tenant.id, batch_id)
    rows = db.execute(
        select(ProspectApproval, Prospect, Company)
        .join(Prospect, Prospect.id == ProspectApproval.prospect_id)
        .outerjoin(Company, Company.id == Prospect.company_id)
        .where(ProspectApproval.batch_id == batch.id)
        .order_by(
            Company.name.asc().nullslast(),
            Prospect.fit_score.desc().nullslast(),
            ProspectApproval.id.asc(),
        )
    ).all()

    groups: dict[str, BatchCompanyGroup] = {}
    for approval, prospect, company in rows:
        e = prospect.enrichment or {}
        comps = prospect.fit_components or {}
        key = str(company.id) if company else (e.get("company") or e.get("domain") or "—")
        group = groups.get(key)
        if group is None:
            group = BatchCompanyGroup(
                company=(company.name if company else None) or e.get("company", ""),
                domain=(company.domain if company else None) or e.get("domain", ""),
                industry=(company.industry if company else None) or e.get("company_industry", ""),
                size=(company.size if company else None) or e.get("company_size", ""),
                country=(company.country if company else "") or "",
                fit_tier=company.fit_tier if company else None,
                fit_reason=(company.fit_reason if company else "") or "",
            )
            groups[key] = group
        group.prospects.append(
            BatchProspect(
                approval_id=str(approval.id),
                prospect_id=str(prospect.id),
                full_name=e.get("full_name", ""),
                title=e.get("title", ""),
                seniority=e.get("seniority", ""),
                fit_tier=prospect.fit_tier,
                fit_reason=prospect.fit_reason or comps.get("fit_reason", ""),
                decision=approval.decision,
            )
        )

    counts = svc.counts_for(db, batch.id)
    names = _icp_name_map(db, ctx.tenant.id, [batch.icp_id])
    base = _batch_out(batch, counts, names.get(batch.icp_id, ""))
    return BatchDetailOut(**base.model_dump(), companies=list(groups.values()))


# --------------------------------------------------------------------------- D2: decide (step-3)


@router.post("/{client}/batches/{batch_id}/decide", response_model=BatchOut)
def decide_batch(
    batch_id: str,
    body: DecisionIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> BatchOut:
    """STEP-3 human fallback — the operator records the client's approve/remove decision by hand
    when the link route is exhausted. Same `prospect_approval` write path as the external decide."""
    batch = _load_batch(db, ctx.tenant.id, batch_id)
    # A decided batch is final — re-deciding would silently overwrite the client's recorded
    # approve/remove choices (the billable evidence). Mirrors the send guard.
    if batch.status in (svc.APPROVED_BATCH, svc.CHANGES_REQUESTED):
        raise HTTPException(status.HTTP_409_CONFLICT, "batch already decided")
    approvals = (
        db.execute(select(ProspectApproval).where(ProspectApproval.batch_id == batch.id))
        .scalars()
        .all()
    )
    svc.apply_decision(
        batch,
        approvals,
        approved_ids=body.approved_ids,
        removed_ids=body.removed_ids,
        request_changes=body.request_changes,
    )
    db.commit()
    db.refresh(batch)
    counts = svc.counts_for(db, batch.id)
    names = _icp_name_map(db, ctx.tenant.id, [batch.icp_id])
    return _batch_out(batch, counts, names.get(batch.icp_id, ""))


# --------------------------------------------------------------------------- D3: template


@router.get("/{client}/approval-template", response_model=TemplateOut)
def get_approval_template(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> TemplateOut:
    """The tenant's sendout copy (saved override merged over the seeded default)."""
    return TemplateOut(**svc.get_template(db, ctx.tenant.id))


@router.put("/{client}/approval-template", response_model=TemplateOut)
def save_approval_template(
    body: TemplateIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> TemplateOut:
    """Upsert the per-tenant override. An empty field falls back to the default on read."""
    out = svc.save_template(db, ctx.tenant.id, body.model_dump())
    db.commit()
    return TemplateOut(**out)


# ------------------------------------------------------------------------ D3: send (resend ladder)


@router.post("/{client}/batches/{batch_id}/send", response_model=BatchOut)
def send_approval(
    batch_id: str,
    body: SendIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> BatchOut:
    """Mint a tokenized, 7-day `approval_link` and email the client the rendered template (SES,
    best-effort). A second send is the **Follow-Up** resend: it expires any prior live link for this
    batch and mints a fresh 7-day one, so only the latest send's link is ever valid — a mistyped or
    forwarded earlier recipient can no longer view or decide. Double-decide is also prevented
    downstream by gating link validity on `batch.status == sent`.
    """
    s = get_settings()
    batch = _load_batch(db, ctx.tenant.id, batch_id)
    if batch.status in (svc.APPROVED_BATCH, svc.CHANGES_REQUESTED):
        raise HTTPException(status.HTTP_409_CONFLICT, "batch already decided")
    email = (body.email or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a recipient email is required")

    counts = svc.counts_for(db, batch.id)
    count = counts["total"] - counts["removed"]  # live (non-removed) prospects
    rendered = svc.render_template(
        svc.get_template(db, ctx.tenant.id), client_name=ctx.tenant.name, count=count
    )

    now = datetime.now(UTC)
    # Revoke any still-live earlier link before minting the new one (expire = revoke).
    db.execute(
        update(ApprovalLink)
        .where(ApprovalLink.batch_id == batch.id, ApprovalLink.used_at.is_(None))
        .values(expires_at=now)
    )
    token = new_opaque_token()
    db.add(
        ApprovalLink(
            tenant_id=ctx.tenant.id,
            batch_id=batch.id,
            recipient_email=email,
            token_hash=hash_token(token),
            expires_at=now + timedelta(seconds=s.approval_ttl_seconds),
        )
    )
    batch.status = svc.SENT
    if batch.sent_at is None:
        batch.sent_at = now

    link = f"{s.web_base_url}/{ctx.tenant.slug}/approve/{token}"
    send_email(
        email,
        rendered["subject"],
        f"{rendered['body']}\n\n{rendered['cta']}:\n{link}\n\n"
        "This link is valid for 7 days. Nothing is contacted until you approve.\n",
    )
    db.commit()
    db.refresh(batch)
    names = _icp_name_map(db, ctx.tenant.id, [batch.icp_id])
    # Sending never touches `prospect_approval`, so the decision counts are unchanged — reuse them.
    return _batch_out(batch, counts, names.get(batch.icp_id, ""))
