"""Shared funnel stage-move writers (Phase E) — a leaf module.

`record_stage_move` / `move_lead_or_409` write the `stage_moved` ledger row that the per-lead
timeline and the ever-reached funnel both derive from. They live here (not in `router.py`) so the
non-router callers can import them EAGERLY: the meetings domain (`router` sweep + outcome
correction, `public` booking) and the webhook ingest all move leads, and importing the whole
campaigns *router* module (APIRouter + launch + batches/meetings services) just to reach these two
functions forced two of them into lazy in-function imports as a campaigns↔meetings cycle guard.
This module depends only on models + `campaigns.service`, so every caller is now eager and honest.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.campaigns import service as svc
from app.models import CampaignLead, OutreachEvent

__all__ = ["move_lead_or_409", "record_stage_move"]


def record_stage_move(db: Session, lead: CampaignLead, target: str, *, via: str) -> bool:
    """Move `lead` to `target` if the allowed-moves map permits it, writing the `stage_moved` ledger
    row (per-lead timeline + ever-reached funnel both derive from it). Returns True iff it moved;
    a no-op or illegal move returns False (webhook ingest skips silently; the console route 409s).
    Does NOT commit — the caller owns the txn."""
    if lead.stage == target or not svc.is_legal_move(lead.stage, target):
        return False
    now = datetime.now(UTC)
    prev = lead.stage
    lead.stage = target
    lead.stage_changed_at = now
    db.add(
        OutreachEvent(
            tenant_id=lead.tenant_id,
            campaign_id=lead.campaign_id,
            campaign_lead_id=lead.id,
            event_type=svc.STAGE_MOVED,
            payload={"from": prev, "to": target, "via": via},
            occurred_at=now,
        )
    )
    return True


def move_lead_or_409(db: Session, lead: CampaignLead, target: str, *, via: str) -> None:
    """Console move — raise 409 on an illegal transition (mirrors the FE `MOVES` guard)."""
    if lead.stage == target:
        return
    if not svc.is_legal_move(lead.stage, target):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"cannot move a lead from '{lead.stage}' to '{target}'"
        )
    record_stage_move(db, lead, target, via=via)
