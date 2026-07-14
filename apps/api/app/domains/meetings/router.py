"""Meeting console routes — the JWT/owner ledger · bookings · feedback surface (Phase F, F4/F5).

The on-read poll (zero new AWS resources): every meetings/bookings/feedback/summary read runs
`sweep_meetings` first — for each due, not-yet-ingested `meeting` it reads the Meet conference
record
and stamps held/duration/outcome/amount ONCE (an idempotent `WHERE held IS NULL` claim; the money
rule lives in `service.py`, unit-tested off the F2 fixtures). Reads derive everything else on the
fly (billing chip, booking status, feedback state) — no stored counters (the Phase-D rule).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import AccessContext, get_db, require_membership, uuid_or_404
from app.core.email import send_email
from app.core.security import hash_token, new_opaque_token
from app.domains.campaigns.stage_moves import record_stage_move
from app.domains.meetings import service as m
from app.domains.meetings.schemas import (
    BookingRowOut,
    FeedbackRowOut,
    MeetingOut,
    OutcomeIn,
    SweepResult,
    WonIn,
)
from app.integrations.google import client as g
from app.models import (
    Batch,
    BookingLink,
    Brief,
    Campaign,
    CampaignLead,
    Company,
    FeedbackLink,
    Meeting,
    MembershipRole,
    OutreachEvent,
    Prospect,
)

router = APIRouter(tags=["meetings"])
log = logging.getLogger("holdslot.meetings")


def _iso(dt: datetime | None) -> str | None:
    return m.iso_z(dt) if dt else None


def _uuid(value: str, detail: str = "not found"):
    return uuid_or_404(value, detail)  # M22 — shared malformed-id → 404 helper


# ============================================================ F4 — the on-read sweep + qualify


def sweep_meetings(db: Session, tenant_id) -> SweepResult:
    """Ingest every due, not-yet-held meeting from its Meet record — held/duration/outcome
    stamped ONCE (idempotent). A Google hiccup on one row is logged/skipped, never fails the read.
    """
    now = datetime.now(UTC)
    _tz, minutes, _windows = m.availability_of(_brief_data(db, tenant_id))
    due = (
        db.execute(
            select(Meeting).where(
                Meeting.tenant_id == tenant_id,
                Meeting.held.is_(None),
                Meeting.scheduled_at < now - timedelta(minutes=minutes),
            )
        )
        .scalars()
        .all()
    )
    res = SweepResult()
    for meeting in due:
        try:
            if _ingest_one(db, meeting, now):
                res.swept += 1
                if meeting.outcome == "qualified":
                    res.qualified += 1
                elif meeting.outcome == "noshow":
                    res.noshow += 1
        except g.GoogleError:
            log.warning("sweep: google read failed for meeting=%s — skipped", meeting.id)
    if res.swept:
        db.commit()
    # GS3 — the on-read billing sweep rides here (dormant until a tenant has a Stripe subscription).
    # Lazy-imported + best-effort: a billing hiccup must never fail the meetings/ledger read. Roll
    # back on any error so a DB-level failure (e.g. an Aurora resume mid-sweep) doesn't leave the
    # session in an aborted transaction that then 500s the list query that follows this call.
    try:
        from app.domains.billing.router import bill_due_meetings

        bill_due_meetings(db, tenant_id)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.warning("sweep: billing sweep failed for tenant=%s — deferred", tenant_id)
    return res


def _ingest_one(db: Session, meeting: Meeting, now: datetime) -> bool:
    """Resolve ONE meeting's outcome from Meet. Returns True iff it was finalized (held set)."""
    code = m.meeting_code(meeting.meet_link)
    records = g.list_conference_records(code) if code else []
    ended = m.select_record(records, meeting.scheduled_at)
    grace_passed = now > m.as_utc(meeting.scheduled_at) + timedelta(hours=m.NOSHOW_GRACE_HOURS)

    if ended:
        participants = g.list_participants(ended["name"])
        if m.is_held(ended, participants):
            duration = m.record_duration_min(ended)
            outcome = m.outcome_for(held=True, duration_min=duration)
            amount, window = _stamp(outcome, meeting.approval_id, m.parse_iso(ended["endTime"]))
            return _finalize(
                db,
                meeting,
                held=True,
                duration=duration,
                outcome=outcome,
                record_id=ended["name"],
                amount=amount,
                window=window,
                stage="billable" if outcome == "qualified" else None,
            )
        # An ended record but host-alone (<2 joined) → treat as a no-show, but only past the grace.
        if grace_passed:
            return _finalize(
                db,
                meeting,
                held=False,
                duration=None,
                outcome="noshow",
                record_id=ended["name"],
                amount=None,
                window=None,
                stage="noshow",
            )
        return False  # within grace — leave NULL ("awaiting")
    if records:
        return False  # a record exists but is still ongoing — skip until it ends
    # No record at all: a no-show only once the grace has passed (a prospect may join late, GR7).
    if grace_passed:
        return _finalize(
            db,
            meeting,
            held=False,
            duration=None,
            outcome="noshow",
            record_id=None,
            amount=None,
            window=None,
            stage="noshow",
        )
    return False


def _stamp(outcome: str, approval_id, record_end: datetime):
    """amount ($500) + 48h dispute window — stamped ONLY when qualified AND the approval evidence is
    present (no approval → never billable)."""
    if outcome == "qualified" and approval_id is not None:
        return m.PER_MEETING_USD, m.dispute_window_end(record_end)
    return None, None


def _finalize(db, meeting, *, held, duration, outcome, record_id, amount, window, stage) -> bool:
    """The idempotent guarded claim — writes it once (`WHERE held IS NULL`), then applies the
    stage effect. A second sweep changes nothing (FT4-10)."""
    res = db.execute(
        update(Meeting)
        .where(Meeting.id == meeting.id, Meeting.held.is_(None))
        .values(
            held=held,
            duration_min=duration,
            outcome=outcome,
            conference_record_id=record_id,
            amount=amount,
            dispute_window_ends_at=window,
        )
    )
    if res.rowcount == 0:
        return False
    meeting.held, meeting.outcome = held, outcome  # keep the in-session object consistent
    if stage and meeting.campaign_lead_id:
        lead = db.get(CampaignLead, meeting.campaign_lead_id)
        if lead is not None:
            record_stage_move(db, lead, stage, via="sweep")
    return True


@router.post("/{client}/meetings/refresh", response_model=SweepResult)
def refresh_meetings(
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> SweepResult:
    """Manual on-demand sweep (the ledger Refresh button)."""
    return sweep_meetings(db, ctx.tenant.id)


@router.post("/{client}/meetings/{meeting_id}/outcome", response_model=MeetingOut)
def correct_outcome(
    meeting_id: str,
    body: OutcomeIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> MeetingOut:
    """The explicit owner-correction door (never the sweep) — re-derives amount/window off the
    corrected outcome + the dispute flag.

    Billing note (GS): the sweep emits a meter event only AFTER the 48h dispute window closes, and a
    correction is expected inside that window, so `billed_at` is normally still NULL here. If a
    meeting were corrected to short_call/noshow AFTER it had already billed, this door zeroes
    `amount` but emits NO Stripe reversal — the dispute window guards that (accepted at MVP)."""
    meeting = _load_meeting(db, ctx.tenant.id, meeting_id)
    if body.outcome not in ("qualified", "short_call", "noshow"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid outcome")
    now = datetime.now(UTC)
    # M18 — a correction must never bill a meeting that hasn't happened: an unswept meeting
    # (`held IS NULL`) still in the future can't be hand-marked qualified → billable. Once it is
    # swept OR its scheduled time has passed, correcting it is legitimate.
    if meeting.held is None and m.as_utc(meeting.scheduled_at) > now:
        raise HTTPException(status.HTTP_409_CONFLICT, "meeting hasn't happened yet")
    meeting.outcome = body.outcome
    meeting.held = body.outcome != "noshow"
    if body.disputed is not None:
        meeting.disputed = body.disputed
    if body.won is not None:
        meeting.won = body.won
    if meeting.outcome == "qualified" and meeting.approval_id is not None:
        meeting.amount = m.PER_MEETING_USD
        meeting.dispute_window_ends_at = meeting.dispute_window_ends_at or (
            now + timedelta(hours=m.DISPUTE_WINDOW_HOURS)
        )
    else:
        meeting.amount = None
        meeting.dispute_window_ends_at = None
    target = {"qualified": "billable", "noshow": "noshow"}.get(meeting.outcome)
    if target and meeting.campaign_lead_id:
        lead = db.get(CampaignLead, meeting.campaign_lead_id)
        if lead is not None:
            record_stage_move(db, lead, target, via="correction")
    db.commit()
    return _meeting_out(meeting, _name_maps(db, [meeting]), now)


@router.post("/{client}/meetings/{meeting_id}/won", response_model=MeetingOut)
def set_won(
    meeting_id: str,
    body: WonIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> MeetingOut:
    """GF-9 — the console 'Deal won / No deal' setter. Writes `won` ONLY — never outcome, amount,
    dispute_window, or disputed — so a post-sale conversion mark can never move a billing decision
    (isolation pinned by a unit test). GOPS loses its one SQL step; the §11 adopter-vs-churn mix
    becomes console-readable per tenant."""
    meeting = _load_meeting(db, ctx.tenant.id, meeting_id)
    meeting.won = body.won
    db.commit()
    return _meeting_out(meeting, _name_maps(db, [meeting]), datetime.now(UTC))


# ============================================================ F5 — reads


def _brief_data(db: Session, tenant_id) -> dict:
    brief = db.execute(select(Brief).where(Brief.tenant_id == tenant_id)).scalar_one_or_none()
    return (brief.data if brief else None) or {}


def _load_meeting(db: Session, tenant_id, meeting_id: str) -> Meeting:
    meeting = db.execute(
        select(Meeting).where(
            Meeting.id == _uuid(meeting_id, "no such meeting"), Meeting.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such meeting")
    return meeting


def _name_maps(db: Session, meetings: list[Meeting]) -> dict:
    """Batch-load the prospect / company / campaign / batch display names for a set of meetings."""
    lead_ids = {x.campaign_lead_id for x in meetings if x.campaign_lead_id}
    prospect_ids = {x.prospect_id for x in meetings if x.prospect_id}
    leads = (
        {
            x.id: x
            for x in db.execute(select(CampaignLead).where(CampaignLead.id.in_(lead_ids))).scalars()
        }
        if lead_ids
        else {}
    )
    camp_ids = {x.campaign_id for x in leads.values()}
    camps = (
        {c.id: c for c in db.execute(select(Campaign).where(Campaign.id.in_(camp_ids))).scalars()}
        if camp_ids
        else {}
    )
    batch_ids = {c.batch_id for c in camps.values()}
    batches = (
        {b.id: b for b in db.execute(select(Batch).where(Batch.id.in_(batch_ids))).scalars()}
        if batch_ids
        else {}
    )
    prospects = (
        {
            p.id: p
            for p in db.execute(select(Prospect).where(Prospect.id.in_(prospect_ids))).scalars()
        }
        if prospect_ids
        else {}
    )
    comp_ids = {p.company_id for p in prospects.values() if p.company_id}
    companies = (
        {c.id: c for c in db.execute(select(Company).where(Company.id.in_(comp_ids))).scalars()}
        if comp_ids
        else {}
    )
    return {
        "leads": leads,
        "camps": camps,
        "batches": batches,
        "prospects": prospects,
        "companies": companies,
    }


def _meeting_out(meeting: Meeting, maps: dict, now: datetime) -> MeetingOut:
    lead = maps["leads"].get(meeting.campaign_lead_id)
    campaign = maps["camps"].get(lead.campaign_id) if lead else None
    batch = maps["batches"].get(campaign.batch_id) if campaign else None
    prospect = maps["prospects"].get(meeting.prospect_id)
    company = (
        maps["companies"].get(prospect.company_id) if prospect and prospect.company_id else None
    )
    enr = (prospect.enrichment if prospect else None) or {}
    return MeetingOut(
        id=str(meeting.id),
        prospect_name=enr.get("full_name", ""),
        company_name=(company.name if company else "") or enr.get("company", ""),
        campaign_name=campaign.name if campaign else "",
        campaign_id=str(campaign.id) if campaign else None,
        batch_name=batch.name if batch else "",
        scheduled_at=m.iso_z(meeting.scheduled_at),
        held=meeting.held,
        outcome=meeting.outcome,
        amount=float(meeting.amount) if meeting.amount is not None else None,
        billing_chip=m.billing_chip(
            meeting.outcome, meeting.amount, meeting.dispute_window_ends_at, meeting.disputed, now
        ),
        disputed=meeting.disputed,
        feedback_state="Received" if meeting.feedback_at else "None",
        feedback_rating=meeting.feedback_rating,
        won=meeting.won,
    )


@router.get("/{client}/meetings", response_model=list[MeetingOut])
def list_meetings(
    when: str = "past",
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[MeetingOut]:
    """The ledger / calendar feed. `upcoming` = unheld future bookings; `past` = ingested rows.
    The sweep runs first (the on-read poll)."""
    sweep_meetings(db, ctx.tenant.id)
    now = datetime.now(UTC)
    q = select(Meeting).where(Meeting.tenant_id == ctx.tenant.id)
    if when == "upcoming":
        q = q.where(Meeting.held.is_(None), Meeting.scheduled_at >= now).order_by(
            Meeting.scheduled_at.asc()
        )
    else:
        q = q.where(Meeting.held.is_not(None)).order_by(Meeting.scheduled_at.desc())
    meetings = list(db.execute(q).scalars().all())
    maps = _name_maps(db, meetings)
    return [_meeting_out(x, maps, now) for x in meetings]


@router.get("/{client}/bookings", response_model=list[BookingRowOut])
def list_bookings(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[BookingRowOut]:
    """The client-status Booking tab — one row per booking link, its derived status + the sent
    invitation preview + the latest reply-event id (the Propose-new-time carrier handle)."""
    sweep_meetings(db, ctx.tenant.id)
    now = datetime.now(UTC)
    links = list(
        db.execute(
            select(BookingLink)
            .where(BookingLink.tenant_id == ctx.tenant.id)
            .order_by(BookingLink.created_at.desc())
        )
        .scalars()
        .all()
    )
    lead_ids = {x.campaign_lead_id for x in links}
    leads = (
        {
            x.id: x
            for x in db.execute(select(CampaignLead).where(CampaignLead.id.in_(lead_ids))).scalars()
        }
        if lead_ids
        else {}
    )
    # a lead has a meeting?  → Confirmed
    have_meeting = {
        row[0]
        for row in db.execute(
            select(Meeting.campaign_lead_id).where(
                Meeting.tenant_id == ctx.tenant.id, Meeting.campaign_lead_id.in_(lead_ids or [None])
            )
        ).all()
    }
    prospect_ids = {leads[i].prospect_id for i in leads if leads[i].prospect_id}
    prospects = (
        {
            p.id: p
            for p in db.execute(select(Prospect).where(Prospect.id.in_(prospect_ids))).scalars()
        }
        if prospect_ids
        else {}
    )
    camp_ids = {leads[i].campaign_id for i in leads}
    camps = (
        {c.id: c for c in db.execute(select(Campaign).where(Campaign.id.in_(camp_ids))).scalars()}
        if camp_ids
        else {}
    )
    company_ids = {prospects[i].company_id for i in prospects if prospects[i].company_id}
    companies = (
        {c.id: c for c in db.execute(select(Company).where(Company.id.in_(company_ids))).scalars()}
        if company_ids
        else {}
    )
    # M21 — bucket the reply-event lookup ONCE for the whole page (was 2 queries per link → 100 RTs
    # at 50 links), mirroring the `_lead_rows` pattern.
    replies_map = _latest_replies(db, ctx.tenant.id, lead_ids)
    out: list[BookingRowOut] = []
    for link in links:
        lead = leads.get(link.campaign_lead_id)
        prospect = prospects.get(lead.prospect_id) if lead else None
        company = companies.get(prospect.company_id) if prospect and prospect.company_id else None
        campaign = camps.get(lead.campaign_id) if lead else None
        enr = (prospect.enrichment if prospect else None) or {}
        state = m.link_state(link.used_at, link.expires_at, now)
        preview, reply_id = replies_map.get(link.campaign_lead_id, ("", None))
        out.append(
            BookingRowOut(
                id=str(link.id),
                prospect_name=enr.get("full_name", ""),
                company_name=(company.name if company else "") or enr.get("company", ""),
                campaign_name=campaign.name if campaign else "",
                status=m.booking_status(
                    has_meeting=link.campaign_lead_id in have_meeting, state=state
                ),
                invitation_preview=preview,
                reply_event_id=reply_id,
                sent_at=_iso(link.created_at),
                expires_at=_iso(link.expires_at),
            )
        )
    return out


def _latest_replies(db: Session, tenant_id, lead_ids) -> dict:
    """Per-lead (invitation_preview, latest_reply_event_id) for a whole page in two queries — the
    bucketed replacement for the old per-link `_latest_reply` (M21). `invitation_preview` = the
    lead's most recent `reply_sent` body; the event id = its most recent inbound `lead_replied` (the
    Propose-new-time respond carrier). Newest-first, first-seen-per-lead wins."""
    ids = [i for i in lead_ids if i is not None]
    if not ids:
        return {}
    from app.domains.campaigns import service as csvc

    sent_by_lead: dict = {}
    for ev in (
        db.execute(
            select(OutreachEvent)
            .where(
                OutreachEvent.tenant_id == tenant_id,
                OutreachEvent.campaign_lead_id.in_(ids),
                OutreachEvent.event_type == csvc.REPLY_SENT,
            )
            .order_by(OutreachEvent.occurred_at.desc(), OutreachEvent.id.desc())
        )
        .scalars()
        .all()
    ):
        sent_by_lead.setdefault(ev.campaign_lead_id, ev)
    reply_by_lead: dict = {}
    for eid, lid in db.execute(
        select(OutreachEvent.id, OutreachEvent.campaign_lead_id)
        .where(
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.campaign_lead_id.in_(ids),
            OutreachEvent.event_type == csvc.LEAD_REPLIED,
        )
        .order_by(OutreachEvent.occurred_at.desc(), OutreachEvent.id.desc())
    ).all():
        reply_by_lead.setdefault(lid, eid)
    out: dict = {}
    for lid in ids:
        sent = sent_by_lead.get(lid)
        rid = reply_by_lead.get(lid)
        out[lid] = ((sent.response_body if sent else "") or "", str(rid) if rid else None)
    return out


@router.get("/{client}/feedback", response_model=list[FeedbackRowOut])
def list_feedback(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[FeedbackRowOut]:
    """The client-status Feedback tab — one row per held meeting: its feedback state + `overdue`
    (pending > 5 days, computed on read)."""
    sweep_meetings(db, ctx.tenant.id)
    now = datetime.now(UTC)
    meetings = list(
        db.execute(
            select(Meeting)
            .where(Meeting.tenant_id == ctx.tenant.id, Meeting.held.is_(True))
            .order_by(Meeting.scheduled_at.desc())
        )
        .scalars()
        .all()
    )
    maps = _name_maps(db, meetings)
    live_links = _live_feedback_links(db, ctx.tenant.id, [x.id for x in meetings], now)
    out: list[FeedbackRowOut] = []
    for meeting in meetings:
        prospect = maps["prospects"].get(meeting.prospect_id)
        company = (
            maps["companies"].get(prospect.company_id) if prospect and prospect.company_id else None
        )
        enr = (prospect.enrichment if prospect else None) or {}
        has_live = meeting.id in live_links
        out.append(
            FeedbackRowOut(
                id=str(meeting.id),
                prospect_name=enr.get("full_name", ""),
                company_name=(company.name if company else "") or enr.get("company", ""),
                state=m.feedback_state(has_live, meeting.feedback_at),
                overdue=m.feedback_overdue(meeting.scheduled_at, meeting.feedback_at, now),
                rating=meeting.feedback_rating,
                comment=meeting.feedback_comment or "",
                feedback_at=_iso(meeting.feedback_at),
                scheduled_at=m.iso_z(meeting.scheduled_at),
            )
        )
    return out


def _live_feedback_links(db: Session, tenant_id, meeting_ids: list, now: datetime) -> set:
    if not meeting_ids:
        return set()
    rows = (
        db.execute(
            select(FeedbackLink).where(
                FeedbackLink.tenant_id == tenant_id, FeedbackLink.meeting_id.in_(meeting_ids)
            )
        )
        .scalars()
        .all()
    )
    return {x.meeting_id for x in rows if m.link_state(x.used_at, x.expires_at, now) == "valid"}


@router.post("/{client}/meetings/{meeting_id}/feedback/send", response_model=FeedbackRowOut)
def send_feedback(
    meeting_id: str,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> FeedbackRowOut:
    """Mint a fresh feedback link + email it to the prospect (send-before-persist, N31). Operator
    manual — needs-attention ③ is the nudge surface, no scheduler."""
    meeting = _load_meeting(db, ctx.tenant.id, meeting_id)
    s = get_settings()
    prospect = db.get(Prospect, meeting.prospect_id) if meeting.prospect_id else None
    to = (prospect.enrichment or {}).get("email") if prospect else None
    if not to:
        raise HTTPException(status.HTTP_409_CONFLICT, "no prospect email on file for this meeting")
    token = new_opaque_token()
    url = f"{s.web_base_url}/{ctx.tenant.slug}/feedback/{token}"
    sent = send_email(
        to,
        f"How was your meeting with {ctx.tenant.name}?",
        f"Thanks for meeting with {ctx.tenant.name}. A minute of feedback helps a lot:\n\n{url}\n\n"
        "This link is valid for 7 days.\n",
    )
    if not sent:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "the feedback email could not be sent")
    now = datetime.now(UTC)
    db.execute(
        update(FeedbackLink)
        .where(FeedbackLink.meeting_id == meeting.id, FeedbackLink.used_at.is_(None))
        .values(expires_at=now)
    )
    db.add(
        FeedbackLink(
            tenant_id=ctx.tenant.id,
            meeting_id=meeting.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(seconds=s.approval_ttl_seconds),
        )
    )
    db.commit()
    maps = _name_maps(db, [meeting])
    prospect = maps["prospects"].get(meeting.prospect_id)
    company = (
        maps["companies"].get(prospect.company_id) if prospect and prospect.company_id else None
    )
    enr = (prospect.enrichment if prospect else None) or {}
    return FeedbackRowOut(
        id=str(meeting.id),
        prospect_name=enr.get("full_name", ""),
        company_name=(company.name if company else "") or enr.get("company", ""),
        state="Pending",
        overdue=m.feedback_overdue(meeting.scheduled_at, meeting.feedback_at, now),
        rating=meeting.feedback_rating,
        comment=meeting.feedback_comment or "",
        feedback_at=_iso(meeting.feedback_at),
        scheduled_at=m.iso_z(meeting.scheduled_at),
    )


@router.post(
    "/{client}/meetings/{meeting_id}/inform-client", status_code=status.HTTP_204_NO_CONTENT
)
def inform_client(
    meeting_id: str,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> None:
    """Email the Brief attendee about a low-rated meeting (context only; no state change)."""
    meeting = _load_meeting(db, ctx.tenant.id, meeting_id)
    from app.domains.meetings.public import brief_attendee

    to = brief_attendee(_brief_data(db, ctx.tenant.id))
    if not to:
        raise HTTPException(status.HTTP_409_CONFLICT, "no client attendee email on file")
    rating = meeting.feedback_rating
    # L11 — honor send_email's result: a swallowed SES failure returned 204, so the operator thought
    # the client was informed. Mirror the sibling send_feedback (:605) and 502 on failure.
    sent = send_email(
        to,
        f"Meeting feedback follow-up — {ctx.tenant.name}",
        f"A recent meeting received a rating of {rating}/5"
        + (f': "{meeting.feedback_comment}"' if meeting.feedback_comment else "")
        + ".\n\nWorth a quick look.\n",
    )
    if not sent:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "the follow-up email could not be sent")
