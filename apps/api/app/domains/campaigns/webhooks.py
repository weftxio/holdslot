"""Smartlead webhook ingest (E4) — public, token-only. NO auth, NO `{client}` segment.

The one inbound Smartlead surface, and the reason the funnel moves. Posture (initial-build-plan.md
→ Phase E, risks R2/R3/R8):

  * **Auth = a high-entropy PATH token** (Smartlead publishes no HMAC). Compared in constant time; a
    bad/absent token → 404 with no body (route + tenant existence never leak).
  * **Always answers 2xx once the raw event is stored** — a 5xx would trigger Smartlead's ≤5×300 s
    retry storm. Store raw first (`INSERT … ON CONFLICT DO NOTHING` — the partial-unique dedupe),
    THEN normalize + move the stage. A downstream error is swallowed (2xx); the E6 statistics poll
    is the safety net for a genuinely missed event.
  * **Unknown campaign** → logged, 2xx no-op (the ledger row needs a campaign FK). **Unknown lead**
    (known campaign) → stored with `campaign_lead_id` NULL, 2xx.
  * `normalize_event` absorbs provider-name drift; an unknown name is stored raw and moves no stage.
"""

from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.domains.campaigns import service as svc
from app.domains.campaigns.router import record_stage_move
from app.domains.prospects.scoring import is_unique_violation
from app.integrations.smartlead import client as sl
from app.models import Brief, Campaign, CampaignLead, OutreachEvent, Prospect

router = APIRouter(tags=["smartlead-webhooks"])
log = logging.getLogger("holdslot.smartlead.webhook")


@router.post("/webhooks/smartlead/{token}")
def ingest_smartlead(
    token: str,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
) -> dict:
    """Ingest one Smartlead webhook event. Always 2xx once stored (or a benign no-op)."""
    expected = sl.webhook_path_token()
    # Constant-time compare; a missing/blank expected token disables the route (also 404, no leak).
    if not expected or not hmac.compare_digest(str(token), str(expected)):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        return _ingest(db, payload)
    except Exception:  # noqa: BLE001 — never 5xx a stored/duplicate event (retry-storm guard)
        log.exception("smartlead webhook ingest failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "deferred": True}


def _resolve_campaign(db: Session, payload: dict) -> Campaign | None:
    """The campaign this event belongs to, by smartlead_campaign_id. None = unknown (2xx no-op)."""
    sl_id = payload.get("campaign_id")
    if sl_id is None:
        return None
    return db.execute(
        select(Campaign).where(Campaign.smartlead_campaign_id == str(sl_id))
    ).scalar_one_or_none()


def _resolve_lead(db: Session, campaign: Campaign, payload: dict) -> CampaignLead | None:
    """The `campaign_lead` this event is about — by Smartlead's lead id (fast, exact), else by
    matching any candidate email in the payload against the campaign's leads' prospect emails.
    The live webhook carries the id as `sl_email_lead_id` (== our stored `smartlead_lead_id`,
    verified 2026-07-11); `lead_id`/`sl_lead_id` are kept as tolerant aliases."""
    lead_id = (
        payload.get("lead_id") or payload.get("sl_lead_id") or payload.get("sl_email_lead_id")
    )
    if lead_id is not None:
        lead = db.execute(
            select(CampaignLead).where(
                CampaignLead.campaign_id == campaign.id,
                CampaignLead.smartlead_lead_id == str(lead_id),
            )
        ).scalar_one_or_none()
        if lead is not None:
            return lead
    emails = svc.lead_emails(payload)
    if not emails:
        return None
    # Match by prospect email (stored in enrichment) — one query over this campaign's leads.
    rows = db.execute(
        select(CampaignLead, Prospect.enrichment)
        .join(Prospect, Prospect.id == CampaignLead.prospect_id)
        .where(CampaignLead.campaign_id == campaign.id)
    ).all()
    email_set = set(emails)
    for lead, enrichment in rows:
        pe = (enrichment or {}).get("email", "").strip().lower()
        if pe and pe in email_set:
            return lead
    return None


def _store_event(
    db: Session,
    campaign: Campaign,
    lead: CampaignLead | None,
    *,
    event_type: str,
    dedupe: str,
    payload: dict,
) -> OutreachEvent | None:
    """Insert the raw event, deduped on `smartlead_event_id` (the partial-unique). Returns the row,
    or None if it was a duplicate (a Smartlead retry) — commits either way. `occurred_at` is the
    provider timestamp, UTC-pinned (R16), falling back to now() (NOT NULL — never pass None)."""
    occurred = svc.parse_occurred_at(payload) or datetime.now(UTC)
    ev = OutreachEvent(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        campaign_lead_id=lead.id if lead else None,
        event_type=event_type,
        smartlead_event_id=dedupe,
        payload=payload,
        occurred_at=occurred,
    )
    db.add(ev)
    try:
        db.flush()
    except DBAPIError as exc:
        if not is_unique_violation(exc):
            raise
        db.rollback()  # a retried event — dedupe no-op
        return None
    db.commit()
    return ev


def _unsub_writeback(db: Session, tenant_id, payload: dict) -> None:
    """Append the unsubscribed address to the tenant's Brief `doNotContact` list — the one
    `ExclusionSet` source, so every future find/enrich/batch excludes it (SG-PDPA ≤5-day honor)."""
    emails = svc.lead_emails(payload)
    if not emails:
        return
    email = emails[0]
    brief = db.execute(select(Brief).where(Brief.tenant_id == tenant_id)).scalar_one_or_none()
    if brief is None:
        return
    data = dict(brief.data or {})
    dnc = data.get("doNotContact")
    if isinstance(dnc, list):
        if email not in {str(x).strip().lower() for x in dnc}:
            data["doNotContact"] = [*dnc, email]
    else:
        existing = dnc or ""
        if email not in existing.lower():
            data["doNotContact"] = f"{existing}\n{email}".strip() if existing else email
    brief.data = data


def _ingest(db: Session, payload: dict) -> dict:
    campaign = _resolve_campaign(db, payload)
    if campaign is None:
        log.info("smartlead webhook for unknown campaign %s — ignored", payload.get("campaign_id"))
        return {"ok": True, "ignored": "unknown campaign"}

    raw_type = payload.get("event_type")
    internal = svc.normalize_event(raw_type)
    event_type = internal or (str(raw_type or "unknown").strip().lower()[:32])
    lead = _resolve_lead(db, campaign, payload)
    dedupe = svc.dedupe_key(payload, campaign_id=payload.get("campaign_id"))

    ev = _store_event(db, campaign, lead, event_type=event_type, dedupe=dedupe, payload=payload)
    if ev is None:
        return {"ok": True, "deduped": True}  # a Smartlead retry — no double-process

    # Stage effects — best-effort, fresh txn; a failure here still leaves the event stored (2xx).
    moved = None
    try:
        if internal and lead is not None:
            target = svc.event_stage_effect(internal, svc.sequence_number(payload), lead.stage)
            if target and record_stage_move(db, lead, target, via=internal):
                moved = target
                if internal == svc.LEAD_UNSUBSCRIBED:
                    _unsub_writeback(db, campaign.tenant_id, payload)
        db.commit()
    except Exception:  # noqa: BLE001 — the event is stored; the poll recovers a missed move
        log.exception("smartlead stage effect failed (event %s)", ev.id)
        db.rollback()
    return {"ok": True, "event_type": event_type, "moved_to": moved}
