"""Campaign routes — the console (JWT, owner) Outreach + Reply-queue surface (Phase E).

E3 create + async launch · E5 reply queue (list / triage / respond) · E6 variant scoreboard +
pause/resume + statistics poll · E7 performance-summary. Tenant scope × role is the A4 central
guard; the public token-only webhook ingest is `domains/campaigns/webhooks`. All counts/metrics are
DERIVED from `outreach_event` (never stored); the funnel SoT is `campaign_lead.stage`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import is_unique_violation
from app.core.deps import AccessContext, get_db, require_membership, uuid_or_404
from app.core.security import hash_token, new_opaque_token
from app.domains.batches import service as bsvc
from app.domains.campaigns import launch
from app.domains.campaigns import service as svc
from app.domains.campaigns.schemas import (
    CampaignCreateIn,
    CampaignDetailOut,
    CampaignOut,
    FunnelStage,
    LeadEventOut,
    LeadOut,
    MeetingCalendarItem,
    PerformanceSummaryOut,
    ReplyOut,
    RespondIn,
    StageMoveIn,
    TriageIn,
    VariantIn,
    VariantOut,
    VariantsIn,
    WinnerIn,
)
from app.domains.campaigns.stage_moves import move_lead_or_409, record_stage_move
from app.domains.meetings import service as msvc
from app.integrations.smartlead import client as sl
from app.models import (
    Batch,
    BookingLink,
    Campaign,
    CampaignLead,
    Icp,
    Meeting,
    MembershipRole,
    MessageVariant,
    OutreachEvent,
    Prospect,
    ProspectApproval,
)

router = APIRouter(tags=["campaigns"])
log = logging.getLogger("holdslot.campaigns")


def _iso(dt: datetime | None) -> str | None:
    """UTC-pinned `…Z` serialization (mirrors the meetings domain). The Data API hands back
    naive-UTC timestamps, so a bare `.isoformat()` (no offset) is read as LOCAL by the FE
    `new Date(...)` — in HK (+8) that shifts a 20:00 UTC reply to the wrong calendar day (M6/R16).
    `iso_z` attaches the `Z` so every consumer renders viewer-local from a true instant."""
    return msvc.iso_z(dt) if dt else None


def _uuid(raw: str, msg: str = "not found") -> uuid.UUID:
    # M22 — malformed path ids are 404 (not 400), the shared convention (meetings already did this).
    return uuid_or_404(raw, msg)


# --------------------------------------------------------------------------- derived counts


def _stage_counts(db: Session, campaign_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """Current stage → lead count per campaign (from `campaign_lead.stage`, the funnel SoT)."""
    if not campaign_ids:
        return {}
    rows = db.execute(
        select(CampaignLead.campaign_id, CampaignLead.stage, func.count())
        .where(CampaignLead.campaign_id.in_(campaign_ids))
        .group_by(CampaignLead.campaign_id, CampaignLead.stage)
    ).all()
    out: dict[uuid.UUID, dict[str, int]] = {}
    for cid, stage, n in rows:
        out.setdefault(cid, {})[stage] = n
    return out


def _variant_metrics(db: Session, campaign_id: uuid.UUID) -> dict[str, dict[str, int]]:
    """Per-variant sent/opens/replies, DERIVED from the event ledger joined to the lead's
    `variant_key` (NULL until Smartlead reports a per-lead variant → those events go unattributed).
    """
    rows = db.execute(
        select(CampaignLead.variant_key, OutreachEvent.event_type, func.count())
        .join(OutreachEvent, OutreachEvent.campaign_lead_id == CampaignLead.id)
        .where(CampaignLead.campaign_id == campaign_id, CampaignLead.variant_key.isnot(None))
        .group_by(CampaignLead.variant_key, OutreachEvent.event_type)
    ).all()
    out: dict[str, dict[str, int]] = {}
    for key, etype, n in rows:
        d = out.setdefault(key, {"sent": 0, "opens": 0, "replies": 0})
        if etype == svc.EMAIL_SENT:
            d["sent"] += n
        elif etype == svc.LEAD_OPENED:
            d["opens"] += n
        elif etype == svc.LEAD_REPLIED:
            d["replies"] += n
    return out


def _icp_name(db: Session, tenant_id: uuid.UUID, icp_id: uuid.UUID | None) -> str:
    if not icp_id:
        return ""
    name = db.execute(
        select(Icp.name).where(Icp.id == icp_id, Icp.tenant_id == tenant_id)
    ).scalar_one_or_none()
    return name or ""


def _campaign_out(
    campaign: Campaign,
    *,
    batch_name: str,
    icp: str,
    stages: dict[str, int],
) -> CampaignOut:
    return CampaignOut(
        id=str(campaign.id),
        batch_id=str(campaign.batch_id),
        batch_name=batch_name,
        name=campaign.name or "",
        icp=icp,
        status=campaign.status,
        lead_total=sum(stages.values()),
        stages=stages,
        created_at=_iso(campaign.created_at),
    )


def _load_campaign(db: Session, tenant_id: uuid.UUID, campaign_id: str) -> Campaign:
    campaign = db.execute(
        select(Campaign).where(
            Campaign.id == _uuid(campaign_id, "no such campaign"), Campaign.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such campaign")
    # Reap a stale `launching` (worker killed by the Lambda timeout) → error on read (no scheduler).
    launch.reap_if_stale(db, campaign)
    return campaign


# --------------------------------------------------------------------------- E3: create / list


def _seed_variants(variants: list[VariantIn]) -> list[VariantIn]:
    """The variant set to persist — the operator's, or one seeded `A` placeholder if none given.
    L9 — reject duplicate NORMALIZED keys (`strip()[:8] or "A"`, the exact form the callers persist)
    with a 400 before the DB sees them, so a collision (`""`→`A` vs a literal `A`, or two keys equal
    after the 8-char trim) is a clean error on the variants editor rather than an uncaught
    uq_message_variant_campaign_key 500."""
    clean = [v for v in variants if (v.subject.strip() or v.body.strip())]
    if clean:
        seen: set[str] = set()
        for v in clean:
            nk = v.key.strip()[:8] or "A"
            if nk in seen:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"duplicate variant key: {nk!r}")
            seen.add(nk)
        return clean
    return [
        VariantIn(
            key="A",
            subject="A quick idea for {{company_name}}",
            body="Hi {{first_name}}, one line on why HoldSlot fits {{company_name}}.",
        )
    ]


@router.post(
    "/{client}/campaigns", response_model=CampaignDetailOut, status_code=status.HTTP_201_CREATED
)
def create_campaign(
    body: CampaignCreateIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> CampaignDetailOut:
    """Create a `draft` campaign from an **approved** batch (409 otherwise — the mock's "Approved
    batches only" rule, server-enforced) + its A/B/C variants. Idempotent on `batch_id`: a re-POST
    returns the existing campaign (200-shaped, still 201 status — the row is unchanged)."""
    batch = db.execute(
        select(Batch).where(
            Batch.id == _uuid(body.batch_id, "no such batch"), Batch.tenant_id == ctx.tenant.id
        )
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such batch")
    if batch.status != bsvc.APPROVED_BATCH:
        raise HTTPException(status.HTTP_409_CONFLICT, "campaign requires an approved batch")

    # Idempotent on batch_id (the unique constraint) — return the existing campaign for a re-POST.
    existing = db.execute(
        select(Campaign).where(Campaign.batch_id == batch.id)
    ).scalar_one_or_none()
    if existing is not None:
        return _detail(db, ctx.tenant.id, existing)

    campaign = Campaign(
        tenant_id=ctx.tenant.id,
        batch_id=batch.id,
        icp_id=batch.icp_id,
        name=(body.name or "").strip() or batch.name or "Campaign",
        status=launch.DRAFT,
        settings={"daily_cap": launch.DEFAULT_DAILY_CAP},
    )
    db.add(campaign)
    try:
        db.flush()  # need campaign.id for the variants; surfaces the unique-batch race here
    except DBAPIError as exc:
        if not is_unique_violation(exc):
            raise
        db.rollback()  # a concurrent create won the batch_id race — return its campaign
        winner = db.execute(select(Campaign).where(Campaign.batch_id == batch.id)).scalar_one()
        return _detail(db, ctx.tenant.id, winner)
    for v in _seed_variants(body.variants):
        db.add(
            MessageVariant(
                tenant_id=ctx.tenant.id,
                campaign_id=campaign.id,
                key=v.key.strip()[:8] or "A",
                subject=v.subject.strip(),
                body=v.body.strip(),
            )
        )
    db.commit()
    db.refresh(campaign)
    return _detail(db, ctx.tenant.id, campaign)


@router.get("/{client}/campaigns", response_model=list[CampaignOut])
def list_campaigns(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[CampaignOut]:
    """All campaigns for the client, newest first, with derived stage + ever-reached counts."""
    campaigns = (
        db.execute(
            select(Campaign)
            .where(Campaign.tenant_id == ctx.tenant.id)
            .order_by(Campaign.created_at.desc(), Campaign.id.desc())
        )
        .scalars()
        .all()
    )
    for c in campaigns:  # reap stale launching on read
        launch.reap_if_stale(db, c)
    ids = [c.id for c in campaigns]
    stages = _stage_counts(db, ids)
    batch_names = _batch_name_map(db, [c.batch_id for c in campaigns])
    return [
        _campaign_out(
            c,
            batch_name=batch_names.get(c.batch_id, ""),
            icp=_icp_name(db, ctx.tenant.id, c.icp_id),
            stages=stages.get(c.id, {}),
        )
        for c in campaigns
    ]


def _batch_name_map(db: Session, batch_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    real = [b for b in batch_ids if b]
    if not real:
        return {}
    rows = db.execute(select(Batch.id, Batch.name).where(Batch.id.in_(real))).all()
    return {r[0]: r[1] or "" for r in rows}


def _lead_rows(db: Session, campaign_id: uuid.UUID) -> list[LeadOut]:
    """Per-lead cards for the funnel — `campaign_lead` ⋈ prospect enrichment, each with its DERIVED
    event timeline (the ledger is the single source; nothing here is stored). Grouped into companies
    on the FE. Empty until the worker pushes leads (rows exist only on a successful send)."""
    rows = db.execute(
        select(CampaignLead, Prospect.enrichment)
        .outerjoin(Prospect, Prospect.id == CampaignLead.prospect_id)
        .where(CampaignLead.campaign_id == campaign_id)
        .order_by(CampaignLead.created_at.asc(), CampaignLead.id.asc())
    ).all()
    if not rows:
        return []
    # One query for every event under this campaign, bucketed by lead in Python (no N+1).
    ev_rows = (
        db.execute(
            select(OutreachEvent)
            .where(
                OutreachEvent.campaign_id == campaign_id,
                OutreachEvent.campaign_lead_id.isnot(None),
            )
            .order_by(OutreachEvent.occurred_at.asc(), OutreachEvent.id.asc())
        )
        .scalars()
        .all()
    )
    by_lead: dict[uuid.UUID, list[OutreachEvent]] = {}
    for ev in ev_rows:
        by_lead.setdefault(ev.campaign_lead_id, []).append(ev)

    out: list[LeadOut] = []
    for lead, enrichment in rows:
        enr = enrichment or {}
        evs = by_lead.get(lead.id, [])
        timeline = []
        for ev in evs:
            direction, title, summary = svc.describe_event(ev.event_type, ev.payload)
            timeline.append(
                LeadEventOut(
                    event_type=ev.event_type,
                    direction=direction,
                    title=title,
                    summary=summary,
                    occurred_at=_iso(ev.occurred_at),
                )
            )
        out.append(
            LeadOut(
                id=str(lead.id),
                prospect_name=enr.get("full_name", ""),
                prospect_role=enr.get("title", ""),
                company=enr.get("company", ""),
                stage=lead.stage,
                variant_key=lead.variant_key,
                opened=any(e.event_type == svc.LEAD_OPENED for e in evs),
                replied=any(e.event_type == svc.LEAD_REPLIED for e in evs),
                events=timeline,
            )
        )
    return out


def _detail(db: Session, tenant_id: uuid.UUID, campaign: Campaign) -> CampaignDetailOut:
    """The full campaign detail — variants (with derived metrics) + current-stage counts + the
    per-lead funnel cards (each with its derived event timeline)."""
    stages = _stage_counts(db, [campaign.id]).get(campaign.id, {})
    metrics = _variant_metrics(db, campaign.id)
    variants = (
        db.execute(
            select(MessageVariant)
            .where(MessageVariant.campaign_id == campaign.id)
            .order_by(MessageVariant.key.asc())
        )
        .scalars()
        .all()
    )
    batch_name = _batch_name_map(db, [campaign.batch_id]).get(campaign.batch_id, "")
    base = _campaign_out(
        campaign,
        batch_name=batch_name,
        icp=_icp_name(db, tenant_id, campaign.icp_id),
        stages=stages,
    )
    variant_out = [
        VariantOut(
            key=v.key,
            subject=v.subject,
            body=v.body,
            is_winner=v.is_winner,
            **{k: metrics.get(v.key, {}).get(k, 0) for k in ("sent", "opens", "replies")},
        )
        for v in variants
    ]
    return CampaignDetailOut(
        **base.model_dump(), variants=variant_out, leads=_lead_rows(db, campaign.id)
    )


@router.get("/{client}/campaigns/{campaign_id}", response_model=CampaignDetailOut)
def get_campaign(
    campaign_id: str,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> CampaignDetailOut:
    """One campaign's full funnel detail (variants + derived counts + per-lead cards)."""
    campaign = _load_campaign(db, ctx.tenant.id, campaign_id)
    return _detail(db, ctx.tenant.id, campaign)


@router.post(
    "/{client}/campaigns/{campaign_id}/leads/{lead_id}/move", response_model=CampaignDetailOut
)
def move_lead(
    campaign_id: str,
    lead_id: str,
    body: StageMoveIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> CampaignDetailOut:
    """Manually move one lead to another funnel stage (the Campaign-tab 'Move stage…' dropdown).
    Runs through the same allowed-moves guard as every transition — an illegal move is a 409, a
    no-op returns the funnel unchanged. Writes the `stage_moved` ledger row so the per-lead timeline
    and the ever-reached counts both derive from it (never stored)."""
    campaign = _load_campaign(db, ctx.tenant.id, campaign_id)
    lead = db.execute(
        select(CampaignLead).where(
            CampaignLead.id == _uuid(lead_id, "no such lead"),
            CampaignLead.campaign_id == campaign.id,
            CampaignLead.tenant_id == ctx.tenant.id,
        )
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such lead")
    move_lead_or_409(db, lead, body.stage.strip(), via="console")
    db.commit()
    return _detail(db, ctx.tenant.id, campaign)


@router.put("/{client}/campaigns/{campaign_id}/variants", response_model=CampaignDetailOut)
def replace_variants(
    campaign_id: str,
    body: VariantsIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> CampaignDetailOut:
    """Replace a **draft** campaign's variant set (editing before launch). Sequences are locked once
    the campaign is live, so this 409s past `draft`."""
    campaign = _load_campaign(db, ctx.tenant.id, campaign_id)
    if campaign.status != launch.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "variants are locked once a campaign launches"
        )
    db.execute(MessageVariant.__table__.delete().where(MessageVariant.campaign_id == campaign.id))
    for v in _seed_variants(body.variants):
        db.add(
            MessageVariant(
                tenant_id=ctx.tenant.id,
                campaign_id=campaign.id,
                key=v.key.strip()[:8] or "A",
                subject=v.subject.strip(),
                body=v.body.strip(),
            )
        )
    db.commit()
    db.refresh(campaign)
    return _detail(db, ctx.tenant.id, campaign)


# --------------------------------------------------------------------------- E3: launch


@router.post("/{client}/campaigns/{campaign_id}/launch", response_model=CampaignOut)
def launch_campaign(
    campaign_id: str,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> CampaignOut:
    """Flip the campaign to `launching` and fire the async worker (self-invoke; the funnel appears
    as leads are pushed). Idempotent: a launch on `sending` resumes the missing leads; a launch
    already in flight is a 409. The worker builds the Smartlead campaign + adds the FULL approved
    batch (EF-Q2), capped only by the daily send cap (EF-Q3)."""
    campaign = _load_campaign(db, ctx.tenant.id, campaign_id)
    if campaign.status == launch.LAUNCHING:
        raise HTTPException(status.HTTP_409_CONFLICT, "campaign is already launching")
    if campaign.status not in launch.LAUNCHABLE:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"cannot launch a campaign in state '{campaign.status}'"
        )
    if not svc_has_variant(db, campaign.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "author at least one variant first")
    if not launch.claim_for_launch(db, campaign):
        raise HTTPException(status.HTTP_409_CONFLICT, "campaign is already launching")
    try:
        launch.dispatch(ctx.tenant.id, campaign.id)
    except Exception as exc:
        launch.fail(db, campaign.id, f"dispatch failed: {exc!r}")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "could not start the launch"
        ) from exc
    return _campaign_summary(db, ctx.tenant.id, campaign)


def svc_has_variant(db: Session, campaign_id: uuid.UUID) -> bool:
    return (
        db.execute(
            select(func.count())
            .select_from(MessageVariant)
            .where(MessageVariant.campaign_id == campaign_id)
        ).scalar_one()
        > 0
    )


# --------------------------------------------------------------------------- E5: reply queue


def _reply_out(
    event: OutreachEvent, lead: CampaignLead | None, prospect: Prospect | None, campaign_name: str
) -> ReplyOut:
    handle = svc.reply_handle(event.payload or {})
    enr = (prospect.enrichment if prospect else None) or {}
    return ReplyOut(
        id=str(event.id),
        campaign_id=str(event.campaign_id),
        campaign_name=campaign_name,
        prospect_name=enr.get("full_name", ""),
        prospect_role=enr.get("title", ""),
        stage=lead.stage if lead else "",
        reply_body=handle.get("reply_body") or "",
        subject=handle.get("subject") or "",
        occurred_at=_iso(event.occurred_at),
        triage=event.triage,
        handled_at=_iso(event.handled_at),
        response_body=event.response_body,
    )


REPLIES_PAGE_CAP = 500  # M21 — bound the inbox read (was unbounded); the newest N, never all rows


@router.get("/{client}/replies", response_model=list[ReplyOut])
def list_replies(
    campaign_id: str | None = None,
    state: str = "all",
    limit: int = Query(REPLIES_PAGE_CAP, ge=1, le=REPLIES_PAGE_CAP),
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[ReplyOut]:
    """The cross-campaign reply-triage inbox — every `lead_replied` event ⋈ its lead + campaign,
    newest first. `state=open` restricts to unhandled (the tab pip = `handled_at IS NULL`); an
    optional `campaign_id` filter mirrors the mock's campaign dropdown. Bounded to the newest
    `limit` (≤`REPLIES_PAGE_CAP`) so the query can't grow unbounded (M21)."""
    q = (
        select(OutreachEvent, CampaignLead, Prospect, Campaign.name)
        .join(Campaign, Campaign.id == OutreachEvent.campaign_id)
        .outerjoin(CampaignLead, CampaignLead.id == OutreachEvent.campaign_lead_id)
        .outerjoin(Prospect, Prospect.id == CampaignLead.prospect_id)
        .where(
            OutreachEvent.tenant_id == ctx.tenant.id,
            OutreachEvent.event_type == svc.LEAD_REPLIED,
        )
        .order_by(OutreachEvent.occurred_at.desc(), OutreachEvent.id.desc())
    )
    if state == "open":
        q = q.where(OutreachEvent.handled_at.is_(None))
    if campaign_id:
        q = q.where(OutreachEvent.campaign_id == _uuid(campaign_id, "no such campaign"))
    rows = db.execute(q.limit(limit)).all()
    if len(rows) == limit:
        log.info("list_replies: hit the %d-row cap for tenant %s", limit, ctx.tenant.id)
    return [_reply_out(ev, lead, prospect, name) for ev, lead, prospect, name in rows]


def _load_reply(db: Session, tenant_id: uuid.UUID, event_id: str) -> OutreachEvent:
    ev = db.execute(
        select(OutreachEvent).where(
            OutreachEvent.id == _uuid(event_id, "no such reply"),
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.event_type == svc.LEAD_REPLIED,
        )
    ).scalar_one_or_none()
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such reply")
    return ev


@router.post("/{client}/replies/{event_id}/triage", response_model=ReplyOut)
def triage_reply(
    event_id: str,
    body: TriageIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ReplyOut:
    """Classify a reply (positive / objection-timing / referral / nudge / negative) and mark it
    handled. Positive → the lead advances to `replied`; negative → `drop`; the rest just clear the
    pip. The stage move rides the allowed-moves map (an out-of-order move is skipped, not 409'd — a
    re-triage of an already-moved lead is a no-op)."""
    ev = _load_reply(db, ctx.tenant.id, event_id)
    triage_cls = body.triage.strip()
    # M15 — reject an unknown class: a typo'd triage would mark the reply handled with no stage move
    # and then pollute the derived summary counts (which key off this first-class column).
    if triage_cls not in svc.TRIAGE_CLASSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown triage class")
    ev.triage = triage_cls
    ev.handled_at = datetime.now(UTC)
    lead = db.get(CampaignLead, ev.campaign_lead_id) if ev.campaign_lead_id else None
    target = svc.triage_stage(triage_cls)
    if lead is not None and target:
        record_stage_move(db, lead, target, via=f"triage:{triage_cls}")
    db.commit()
    prospect = db.get(Prospect, lead.prospect_id) if lead else None
    name = db.get(Campaign, ev.campaign_id).name if ev.campaign_id else ""
    return _reply_out(ev, lead, prospect, name or "")


@router.post("/{client}/replies/{event_id}/respond", response_model=ReplyOut)
def respond_reply(
    event_id: str,
    body: RespondIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ReplyOut:
    """Send an operator-authored threaded reply via Smartlead `reply_to_thread`, reading the thread
    handle off the stored event row (recovering it via the master inbox if the webhook payload
    lacked one — the R4 two-path plan). Stores `response_body` + a `reply_sent` ledger row and marks
    the reply handled. This is also the F3 booking-link carrier."""
    text = (body.body or "").strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a reply body is required")
    ev = _load_reply(db, ctx.tenant.id, event_id)
    lead = db.get(CampaignLead, ev.campaign_lead_id) if ev.campaign_lead_id else None
    campaign = db.get(Campaign, ev.campaign_id)
    if lead is None or campaign is None or not campaign.smartlead_campaign_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "this reply has no live Smartlead thread")

    handle = svc.reply_handle(ev.payload or {})
    stats_id = handle.get("email_stats_id")
    msg_id = handle.get("reply_message_id")
    if not stats_id:  # R4-b — recover the handle from the master inbox, cache it on the event row
        stats_id, msg_id = _recover_handle(db, ev, lead, campaign)
    if not stats_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "reply thread handle not available yet — retry after a sync"
        )

    # F3 — mint the booking token BEFORE the send (its URL goes in the reply text) but persist the
    # link row only AFTER Smartlead accepts (N31: never persist what didn't send).
    booking_token = None
    if body.include_booking_link:
        s = get_settings()
        booking_token = new_opaque_token()
        url = f"{s.web_base_url}/{ctx.tenant.slug}/book/{booking_token}"
        text = msvc.inject_booking_link(text, url)

    # M17 — a Smartlead failure here was escaping as a raw 500; surface it as a 502 (upstream fault)
    # so the FE can show a real "couldn't send" instead of a generic error. Note the accepted MVP
    # window: the booking-link row is persisted only AFTER this send (N31 — never persist what
    # didn't send), so a DB failure in the commit below leaves an emailed URL that 410s till resend.
    try:
        sl.reply_to_thread(
            campaign.smartlead_campaign_id,
            email_stats_id=stats_id,
            email_body=text,
            lead_id=lead.smartlead_lead_id,
            reply_message_id=msg_id,
        )
    except sl.SmartleadError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "couldn't send the reply via Smartlead — try again"
        ) from exc
    now = datetime.now(UTC)
    ev.response_body = text
    ev.handled_at = ev.handled_at or now
    db.add(
        OutreachEvent(
            tenant_id=ctx.tenant.id,
            campaign_id=campaign.id,
            campaign_lead_id=lead.id,
            event_type=svc.REPLY_SENT,
            payload={"in_reply_to": str(ev.id)},
            response_body=text,
            occurred_at=now,
        )
    )
    if booking_token:
        # Revoke the lead's prior live booking links (the approval resend ladder), then mint fresh.
        db.execute(
            update(BookingLink)
            .where(BookingLink.campaign_lead_id == lead.id, BookingLink.used_at.is_(None))
            .values(expires_at=now)
        )
        db.add(
            BookingLink(
                tenant_id=ctx.tenant.id,
                campaign_lead_id=lead.id,
                token_hash=hash_token(booking_token),
                expires_at=now + timedelta(seconds=get_settings().approval_ttl_seconds),
            )
        )
    db.commit()
    prospect = db.get(Prospect, lead.prospect_id)
    return _reply_out(ev, lead, prospect, campaign.name or "")


def _recover_handle(
    db: Session, ev: OutreachEvent, lead: CampaignLead, campaign: Campaign
) -> tuple[str | None, str | None]:
    """R4-b — recover + cache the reply-to-thread handle via `master-inbox/inbox-replies` when the
    webhook payload carried none. Best-effort: an adapter error leaves the handle unresolved (the
    respond route then 409s cleanly)."""
    prospect = db.get(Prospect, lead.prospect_id)
    lead_email = (prospect.enrichment or {}).get("email", "") if prospect else ""
    try:
        resp = sl.fetch_inbox_replies(campaign.smartlead_campaign_id)
    except sl.SmartleadError:
        return None, None
    found = svc.parse_inbox_handle(resp, lead_email)
    if not found:
        return None, None
    payload = dict(ev.payload or {})
    payload.update(stats_id=found.get("email_stats_id"), message_id=found.get("reply_message_id"))
    ev.payload = payload
    return found.get("email_stats_id"), found.get("reply_message_id")


# ------------------------------------------------------------------------ E6: scoreboard + control


@router.post("/{client}/campaigns/{campaign_id}/winner", response_model=CampaignDetailOut)
def set_variant_winner(
    campaign_id: str,
    body: WinnerIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> CampaignDetailOut:
    """Mark one variant the winner (HoldSlot-side metadata only — Smartlead sequences are locked
    while ACTIVE, so nothing is written back). Clears any prior winner (one per campaign)."""
    campaign = _load_campaign(db, ctx.tenant.id, campaign_id)
    variants = (
        db.execute(select(MessageVariant).where(MessageVariant.campaign_id == campaign.id))
        .scalars()
        .all()
    )
    keys = {v.key for v in variants}
    if body.key not in keys:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such variant")
    for v in variants:
        v.is_winner = v.key == body.key
    db.commit()
    return _detail(db, ctx.tenant.id, campaign)


def _campaign_summary(db: Session, tenant_id: uuid.UUID, campaign: Campaign) -> CampaignOut:
    """The light `CampaignOut` (stages only) — used where the response_model is `CampaignOut`, so we
    skip the expensive `_detail` (variant metrics + per-lead cards) that would just be discarded on
    serialization (M21)."""
    stages = _stage_counts(db, [campaign.id]).get(campaign.id, {})
    return _campaign_out(
        campaign,
        batch_name=_batch_name_map(db, [campaign.batch_id]).get(campaign.batch_id, ""),
        icp=_icp_name(db, tenant_id, campaign.icp_id),
        stages=stages,
    )


def _set_campaign_status(
    db: Session, campaign: Campaign, *, sl_status: str, new_status: str, event_type: str
) -> None:
    """Shared pause/resume: call Smartlead, flip our status, write the control event. The DB flip
    happens only after the Smartlead call succeeds (a failed call must not lie about the state)."""
    if campaign.smartlead_campaign_id:
        # L4 — a Smartlead outage here was escaping as a raw 500 on the first-class Pause/Resume
        # console buttons (the M17 class, unfixed on these siblings). Surface it as a 502 so the FE
        # shows a real "try again"; the DB flip below stays gated on the call succeeding.
        try:
            sl.set_status(campaign.smartlead_campaign_id, sl_status)
        except sl.SmartleadError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "couldn't update the campaign in Smartlead — try again",
            ) from exc
    campaign.status = new_status
    db.add(
        OutreachEvent(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            event_type=event_type,
            payload={"status": new_status},
            occurred_at=datetime.now(UTC),
        )
    )
    db.commit()


@router.post("/{client}/campaigns/{campaign_id}/pause", response_model=CampaignOut)
def pause_campaign(
    campaign_id: str,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> CampaignOut:
    """Pause a sending campaign (Smartlead `PAUSED` + our `paused`)."""
    campaign = _load_campaign(db, ctx.tenant.id, campaign_id)
    if campaign.status != launch.SENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "only a sending campaign can be paused")
    _set_campaign_status(
        db,
        campaign,
        sl_status=sl.STATUS_PAUSED,
        new_status=launch.PAUSED,
        event_type=svc.CAMPAIGN_PAUSED,
    )
    return _campaign_summary(db, ctx.tenant.id, campaign)


@router.post("/{client}/campaigns/{campaign_id}/resume", response_model=CampaignOut)
def resume_campaign(
    campaign_id: str,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> CampaignOut:
    """Resume a paused campaign (Smartlead `START` + our `sending`)."""
    campaign = _load_campaign(db, ctx.tenant.id, campaign_id)
    if campaign.status != launch.PAUSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "only a paused campaign can be resumed")
    _set_campaign_status(
        db,
        campaign,
        sl_status=sl.STATUS_START,
        new_status=launch.SENDING,
        event_type=svc.CAMPAIGN_RESUMED,
    )
    return _campaign_summary(db, ctx.tenant.id, campaign)


@router.post("/{client}/campaigns/{campaign_id}/sync", response_model=CampaignDetailOut)
def sync_campaign(
    campaign_id: str,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> CampaignDetailOut:
    """Poll Smartlead statistics and reconcile webhook drift — any lead Smartlead shows past the
    first email (seq ≥ 2) that our funnel still has at `contacted` is advanced to `followup` (the
    `followup` fallback). Best-effort: an adapter error leaves the funnel as-is."""
    campaign = _load_campaign(db, ctx.tenant.id, campaign_id)
    if campaign.smartlead_campaign_id:
        try:
            resp = sl.fetch_statistics(campaign.smartlead_campaign_id)
            progress = svc.parse_statistics_progress(resp)  # {smartlead_lead_id: max_seq}
            advanced = {lid for lid, seq in progress.items() if seq >= 2}
            if advanced:
                leads = (
                    db.execute(
                        select(CampaignLead).where(
                            CampaignLead.campaign_id == campaign.id,
                            CampaignLead.stage == svc.CONTACTED,
                            CampaignLead.smartlead_lead_id.in_(advanced),
                        )
                    )
                    .scalars()
                    .all()
                )
                for lead in leads:
                    record_stage_move(db, lead, svc.FOLLOWUP, via="statistics_poll")
                db.commit()
        except sl.SmartleadError:
            log.warning("statistics poll failed for campaign %s", campaign.id)
    return _detail(db, ctx.tenant.id, campaign)


# ------------------------------------------------------------------------ E7: performance summary


@router.get("/{client}/performance-summary", response_model=PerformanceSummaryOut)
def performance_summary(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> PerformanceSummaryOut:
    """The performance-summary read (EF-Q9) — derived on read, no stored counters (Phase-D rule).
    The Leads funnel + reply stats + needs-attention ① are live from E7; the meeting cells (headline
    band, Meetings held, Billable, calendar, attention ②③) go live at F5 — the read runs the sweep
    first (the on-read poll)."""
    tid = ctx.tenant.id
    from app.domains.meetings.router import sweep_meetings

    sweep_meetings(db, tid)

    def _count(q) -> int:
        return int(db.execute(q).scalar_one() or 0)

    sourced = _count(select(func.count()).select_from(Prospect).where(Prospect.tenant_id == tid))
    approved = _count(
        select(func.count())
        .select_from(ProspectApproval)
        .where(ProspectApproval.tenant_id == tid, ProspectApproval.decision == "approved")
    )
    contacted = _count(
        select(func.count()).select_from(CampaignLead).where(CampaignLead.tenant_id == tid)
    )
    # Replied = distinct leads with a lead_replied event (a lead may reply on more than one step).
    replied = _count(
        select(func.count(func.distinct(OutreachEvent.campaign_lead_id))).where(
            OutreachEvent.tenant_id == tid, OutreachEvent.event_type == svc.LEAD_REPLIED
        )
    )
    # Positive = distinct leads whose reply was triaged positive — the only path a lead reaches the
    # `replied` stage, so this equals "ever-reached replied" (a lead now at meeting still counts;
    # the funnel never shrinks as leads advance). Uses the first-class `triage` column, so it stays
    # dialect-safe on the RDS Data API (no JSONB `->>`, per the codebase's Data-API convention).
    positive = _count(
        select(func.count(func.distinct(OutreachEvent.campaign_lead_id))).where(
            OutreachEvent.tenant_id == tid,
            OutreachEvent.event_type == svc.LEAD_REPLIED,
            OutreachEvent.triage == svc.TRIAGE_POSITIVE,
        )
    )
    # Meeting booked = ever-reached: distinct leads that have a meeting row (the public booking
    # claim
    # is the only writer, so this never shrinks as a lead advances to billable — FT5-11).
    meetings_booked = _count(
        select(func.count(func.distinct(Meeting.campaign_lead_id))).where(
            Meeting.tenant_id == tid, Meeting.campaign_lead_id.is_not(None)
        )
    )
    funnel = [
        FunnelStage(label="Sourced", n=sourced),
        FunnelStage(label="Approved", n=approved),
        FunnelStage(label="Contacted", n=contacted),
        FunnelStage(label="Replied", n=replied),
        FunnelStage(label="Positive", n=positive),
        FunnelStage(label="Meeting booked", n=meetings_booked),
    ]

    new_positive = _count(
        select(func.count()).where(
            OutreachEvent.tenant_id == tid,
            OutreachEvent.event_type == svc.LEAD_REPLIED,
            OutreachEvent.triage == svc.TRIAGE_POSITIVE,
        )
    )
    awaiting = _count(
        select(func.count()).where(
            OutreachEvent.tenant_id == tid,
            OutreachEvent.event_type == svc.LEAD_REPLIED,
            OutreachEvent.handled_at.is_(None),
        )
    )
    # Needs-attention ① — batches sent to the client but not yet decided (D data, live today).
    approvals_pending = _count(
        select(func.count())
        .select_from(Batch)
        .where(Batch.tenant_id == tid, Batch.status == "sent")
    )

    # ---- F5 meeting cells (all derived off the swept `meeting` rows) --------------------------
    now = datetime.now(UTC)
    d30, d60 = now - timedelta(days=30), now - timedelta(days=60)
    week_ahead = now + timedelta(days=7)

    # M21 — the meeting count-cells collapse into ONE conditional-aggregate query (was 7 sequential
    # `SELECT count(*)` round-trips). Each `_c(...)` = `SUM(CASE WHEN <conds> THEN 1 ELSE 0 END)`,
    # identical semantics to the prior per-count `WHERE`. The money SUM (`billable_this_cycle`) is
    # left as its own query below, untouched.
    def _c(*conds):
        return func.coalesce(func.sum(case((and_(*conds), 1), else_=0)), 0)

    week_ago = now - timedelta(days=7)
    mrow = db.execute(
        select(
            _c(Meeting.outcome == "qualified", Meeting.scheduled_at >= d30),
            _c(
                Meeting.outcome == "qualified",
                Meeting.scheduled_at >= d60,
                Meeting.scheduled_at < d30,
            ),
            _c(Meeting.held.is_(True), Meeting.scheduled_at >= week_ago),
            _c(Meeting.held.is_not(None)),
            _c(Meeting.held.is_(True)),
            _c(
                Meeting.held.is_(None),
                Meeting.scheduled_at >= now,
                Meeting.scheduled_at < week_ahead,
            ),
            _c(Meeting.held.is_(True), Meeting.feedback_at.is_(None)),
        ).where(Meeting.tenant_id == tid)
    ).one()
    qualified_last_30d = int(mrow[0] or 0)
    qualified_prev_30d = int(mrow[1] or 0)
    meetings_held_week = int(mrow[2] or 0)
    ingested = int(mrow[3] or 0)
    held_total = int(mrow[4] or 0)
    awaiting_this_week = int(mrow[5] or 0)
    held_without_feedback = int(mrow[6] or 0)
    show_up_rate = round(held_total / ingested, 3) if ingested else None
    # Billable this cycle = Σ amounts of the meetings whose 48h window has passed, undisputed (the
    # is_billable rule expressed in SQL; amount is only ever stamped on a qualified+approval row).
    # L10 — accrued-UNBILLED only: `billed_at IS NULL`. Without it the sum was all-time, so once
    # Stripe activates every already-invoiced meeting would inflate the console figure forever,
    # diverging from the Stripe invoice. `billed_at` is NULL for every meeting until FR-7/FR-8, so
    # this is a no-op today and correct the day billing goes live (mirrors the charge path's claim).
    billable_this_cycle = float(
        db.execute(
            select(func.coalesce(func.sum(Meeting.amount), 0)).where(
                Meeting.tenant_id == tid,
                Meeting.outcome == "qualified",
                Meeting.amount.is_not(None),
                Meeting.disputed.is_(False),
                Meeting.dispute_window_ends_at < now,
                Meeting.billed_at.is_(None),
            )
        ).scalar_one()
        or 0
    )
    open_booking_links = _count(
        select(func.count())
        .select_from(BookingLink)
        .where(BookingLink.tenant_id == tid, BookingLink.used_at.is_(None))
    )

    # Calendar month feed — meetings scheduled within ±45 days (the react-big-calendar surface).
    cal_rows = (
        db.execute(
            select(Meeting)
            .where(
                Meeting.tenant_id == tid,
                Meeting.scheduled_at >= now - timedelta(days=45),
                Meeting.scheduled_at <= now + timedelta(days=45),
            )
            .order_by(Meeting.scheduled_at.asc())
        )
        .scalars()
        .all()
    )
    prospects = (
        {
            p.id: p
            for p in db.execute(
                select(Prospect).where(
                    Prospect.id.in_({r.prospect_id for r in cal_rows if r.prospect_id})
                )
            ).scalars()
        }
        if cal_rows
        else {}
    )
    calendar = [
        MeetingCalendarItem(
            id=str(r.id),
            scheduled_at=msvc.iso_z(r.scheduled_at),
            prospect_name=(
                (prospects.get(r.prospect_id).enrichment or {}).get("full_name", "")
                if prospects.get(r.prospect_id)
                else ""
            ),
            outcome=r.outcome,
        )
        for r in cal_rows
    ]

    return PerformanceSummaryOut(
        funnel=funnel,
        new_positive_replies=new_positive,
        replies_awaiting_review=awaiting,
        approvals_pending=approvals_pending,
        qualified_last_30d=qualified_last_30d,
        qualified_delta=qualified_last_30d - qualified_prev_30d,
        meetings_held_week=meetings_held_week,
        show_up_rate=show_up_rate,
        awaiting_this_week=awaiting_this_week,
        billable_this_cycle=billable_this_cycle,
        open_booking_links=open_booking_links,
        held_without_feedback=held_without_feedback,
        calendar=calendar,
    )
