"""External approval routes — public, token-only (Phase D, D4). NO auth, NO `{client}` segment.

The single highest-leverage + highest-risk code in Phase D: the masking allow-list serializer is
the control that stops the client ever seeing clear-text identity/contact data. Validity is checked
on READ (`expires_at` + single-use `used_at` + `batch.status == sent`) — no scheduler. Decisions
write through the shared `batches/service.apply_decision`, so console + external can never diverge.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.security import as_utc, hash_token
from app.domains.approvals.schemas import ApprovalDecisionOut, ApprovalProspect, ApprovalView
from app.domains.batches import service as svc
from app.domains.batches.schemas import DecisionIn
from app.models import ApprovalLink, Batch, Company, Prospect, ProspectApproval, Tenant

router = APIRouter(tags=["approvals"])
log = logging.getLogger("holdslot.approvals")


def _load_link(db: Session, token: str) -> ApprovalLink | None:
    return db.execute(
        select(ApprovalLink).where(ApprovalLink.token_hash == hash_token(token))
    ).scalar_one_or_none()


def _state(link: ApprovalLink, batch: Batch | None) -> str:
    """valid · expired · used — checked on read. A decided batch reads `used` for EVERY link it has,
    so a second still-live link (from a Follow-Up resend) can never double-decide."""
    if batch is None:
        return "expired"
    if link.used_at is not None or batch.status in (svc.APPROVED_BATCH, svc.CHANGES_REQUESTED):
        return "used"
    if as_utc(link.expires_at) < datetime.now(UTC):
        return "expired"
    if batch.status != svc.SENT:
        return "expired"
    return "valid"


def _masked(
    approval: ProspectApproval, prospect: Prospect, company: Company | None
) -> ApprovalProspect:
    """The allow-list serializer — fit context ONLY. Built solely from the masking primitives; no
    raw enrichment/contact vector is ever read into the output."""
    e = prospect.enrichment or {}
    comps = prospect.fit_components or {}
    descriptor = svc.company_descriptor(
        (company.industry if company else None) or e.get("company_industry"),
        (company.size if company else None) or e.get("company_size"),
        (company.country if company else None),
    )
    return ApprovalProspect(
        id=str(approval.id),
        name=svc.mask_name(e.get("full_name")),
        company_descriptor=descriptor,
        title=e.get("title", ""),
        seniority=e.get("seniority", ""),
        fit_tier=prospect.fit_tier,
        fit_reason=prospect.fit_reason or comps.get("fit_reason", ""),
        decision=approval.decision,
    )


@router.get("/approve/{token}", response_model=ApprovalView)
def view_approval(token: str, db: Session = Depends(get_db)) -> ApprovalView:
    """The masked batch view. Never errors — an unknown/expired/used token returns a `state` so the
    page shows its expired pane (uniform; tenant existence is never leaked)."""
    link = _load_link(db, token)
    if link is None:
        return ApprovalView(state="expired")
    batch = db.get(Batch, link.batch_id)
    state = _state(link, batch)

    # Non-valid links reveal nothing but the state — a forwarded/expired link must not leak the
    # client's company name, the batch name, or its size (tenant existence stays hidden).
    if state != "valid" or batch is None:
        return ApprovalView(
            state=state,
            expires_at=link.expires_at.isoformat() if link.expires_at else None,
        )

    tenant = db.get(Tenant, link.tenant_id)
    client_name = tenant.name if tenant else ""
    rows = db.execute(
        select(ProspectApproval, Prospect, Company)
        .join(Prospect, Prospect.id == ProspectApproval.prospect_id)
        .outerjoin(Company, Company.id == Prospect.company_id)
        .where(ProspectApproval.batch_id == batch.id, ProspectApproval.decision != svc.REMOVED)
        .order_by(Company.name.asc().nullslast(), Prospect.fit_score.desc().nullslast())
    ).all()
    prospects = [_masked(a, p, c) for a, p, c in rows]
    return ApprovalView(
        state="valid",
        batch_name=batch.name,
        client_name=client_name,
        count=len(prospects),
        expires_at=link.expires_at.isoformat() if link.expires_at else None,
        prospects=prospects,
    )


@router.post("/approve/{token}/decide", response_model=ApprovalDecisionOut)
def decide_approval(
    token: str, body: DecisionIn, db: Session = Depends(get_db)
) -> ApprovalDecisionOut:
    """Record the client's approve/remove decision (single-use). 410 once the link is expired/used
    or the batch already decided — so a replay can never re-open or double-write a batch."""
    link = _load_link(db, token)
    if link is None:
        raise HTTPException(status.HTTP_410_GONE, "this link is invalid or has expired")
    batch = db.get(Batch, link.batch_id)
    if _state(link, batch) != "valid" or batch is None:
        raise HTTPException(status.HTTP_410_GONE, "this link is no longer valid")

    # Claim the link atomically (single-use) BEFORE writing the decision, so two concurrent submits
    # can't both pass the read-time `_state` check and double-write the batch. If the conditional
    # update touched no row, another request already claimed it. (rowcount < 0 = dialect can't say →
    # fall through to the `batch.status` guard, which still blocks a re-decide.)
    claimed = db.execute(
        update(ApprovalLink)
        .where(ApprovalLink.id == link.id, ApprovalLink.used_at.is_(None))
        .values(used_at=datetime.now(UTC))
    )
    if claimed.rowcount == 0:
        raise HTTPException(status.HTTP_410_GONE, "this link is no longer valid")

    approvals = (
        db.execute(select(ProspectApproval).where(ProspectApproval.batch_id == batch.id))
        .scalars()
        .all()
    )
    result = svc.apply_decision(
        batch,
        approvals,
        approved_ids=body.approved_ids,
        removed_ids=body.removed_ids,
        request_changes=body.request_changes,
    )
    db.commit()
    log.info("approval decided batch=%s status=%s", batch.id, batch.status)
    return ApprovalDecisionOut(
        status=batch.status, approved=result["approved"], removed=result["removed"]
    )
