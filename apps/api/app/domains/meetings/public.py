"""External booking + feedback routes — public, token-only (Phase F). NO auth, NO `{client}`
segment.

Mirrors the Phase-D approvals router: validity is checked **on read** (`expires_at` + single-use
`used_at`), an unknown/expired/used token returns a `state` (never 404 — no tenant-existence leak),
and the single-use claim is an atomic `UPDATE … WHERE used_at IS NULL`. `POST /book/{token}` is the
ONE `meeting`-row writer (FD-4): claim FIRST, then create the Google event, releasing the claim on
any failure so the prospect can retry (FD-6). `POST /feedback/{token}` writes the answers onto the
referenced meeting (1:1).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.security import hash_token
from app.domains.meetings import service as msvc
from app.domains.meetings.schemas import (
    BookIn,
    BookingConfirm,
    BookingView,
    FeedbackConfirm,
    FeedbackIn,
    FeedbackView,
)
from app.integrations.google import client as g
from app.models import (
    BookingLink,
    Brief,
    CampaignLead,
    FeedbackLink,
    Meeting,
    Prospect,
    Tenant,
)

router = APIRouter(tags=["booking"])
log = logging.getLogger("holdslot.booking")

# The free/busy read horizon — covers the 5-weekday slot scan plus its weekends.
_FREEBUSY_HORIZON_DAYS = 14


def _iso(dt: datetime | None) -> str | None:
    return msvc.iso_z(dt) if dt else None


def _brief_data(db: Session, tenant_id) -> dict:
    brief = db.execute(select(Brief).where(Brief.tenant_id == tenant_id)).scalar_one_or_none()
    return (brief.data if brief else None) or {}


def _read_busy(now: datetime) -> list[dict] | None:
    """The host seat's free/busy over the slot horizon. A Google error returns the `None` sentinel
    (NOT `[]` — an empty list means 'no busy intervals', i.e. every slot free), so the caller offers
    NO slots / 503s during an outage rather than double-booking the seat (FT3-9 · M2)."""
    try:
        return g.freebusy(msvc.iso_z(now), msvc.iso_z(now + timedelta(days=_FREEBUSY_HORIZON_DAYS)))
    except g.GoogleError:
        return None


def brief_attendee(brief_data: dict) -> str | None:
    """The client-side attendee to invite alongside the prospect (from the Brief). Checked in the
    availability block first, then a top-level key — an opaque JSONB field the founder authors."""
    av = brief_data.get("availability") or {}
    return av.get("attendee_email") or brief_data.get("attendee_email") or None


# --------------------------------------------------------------------------- booking (F3)


def _load_booking(db: Session, token: str) -> BookingLink | None:
    return db.execute(
        select(BookingLink).where(BookingLink.token_hash == hash_token(token))
    ).scalar_one_or_none()


@router.get("/book/{token}", response_model=BookingView)
def view_booking(token: str, db: Session = Depends(get_db)) -> BookingView:
    """The booking page view. Never errors — an unknown/expired/used token returns a `state` so the
    page shows its expired/used pane; a valid link returns the offered slots (windows ∩ free/busy).
    """
    link = _load_booking(db, token)
    if link is None:
        return BookingView(state="expired")
    now = datetime.now(UTC)
    state = msvc.link_state(link.used_at, link.expires_at, now)
    if state != "valid":
        return BookingView(state=state, expires_at=_iso(link.expires_at))
    tenant = db.get(Tenant, link.tenant_id)
    brief_data = _brief_data(db, link.tenant_id)
    _tz, minutes, _windows = msvc.availability_of(brief_data)
    # A free/busy outage (None sentinel) offers no slots — never the full grid (M2).
    busy = _read_busy(now)
    slots = [] if busy is None else msvc.available_slots(brief_data, busy, now)
    return BookingView(
        state="valid",
        client_name=tenant.name if tenant else "",
        duration_min=minutes,
        slots=slots,
        expires_at=_iso(link.expires_at),
    )


def _release(db: Session, link_id, code: int, detail: str) -> None:
    """Release the single-use claim (used_at→NULL) so the prospect can retry, then raise (FD-6)."""
    db.execute(update(BookingLink).where(BookingLink.id == link_id).values(used_at=None))
    db.commit()
    raise HTTPException(code, detail)


@router.post("/book/{token}", response_model=BookingConfirm)
def book_meeting(token: str, body: BookIn, db: Session = Depends(get_db)) -> BookingConfirm:
    """Claim the slot → create the Google Meet event → write the ONE `meeting` row (the approval
    snapshot) → advance the lead to `meeting`. The atomic claim is the double-book guard; a second
    POST on the same token 410s. Any failure after the claim releases it (FD-6)."""
    link = _load_booking(db, token)
    if link is None:
        raise HTTPException(status.HTTP_410_GONE, "this link is invalid or has expired")
    now = datetime.now(UTC)
    if msvc.link_state(link.used_at, link.expires_at, now) != "valid":
        raise HTTPException(status.HTTP_410_GONE, "this link is no longer valid")
    lead = db.get(CampaignLead, link.campaign_lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_410_GONE, "this link is no longer valid")
    tenant = db.get(Tenant, link.tenant_id)
    brief_data = _brief_data(db, link.tenant_id)
    tz_name, minutes, _windows = msvc.availability_of(brief_data)

    # 1. Atomic single-use claim FIRST — the double-book guard. A lost race → 410 (FT3-10).
    claimed = db.execute(
        update(BookingLink)
        .where(BookingLink.id == link.id, BookingLink.used_at.is_(None))
        .values(used_at=now)
    )
    if claimed.rowcount == 0:
        raise HTTPException(status.HTTP_410_GONE, "this link is no longer valid")

    # 2. Tamper check — the slot must be on the availability grid (a slot off it was never offered).
    if not msvc.is_grid_slot(brief_data, body.slot, now):
        _release(db, link.id, status.HTTP_400_BAD_REQUEST, "that time isn't available")
    # 3. Re-check the slot is still free against a fresh free/busy read. A Google outage (the None
    #    sentinel, distinct from an empty-busy list) releases + 503s — it must never fall through as
    #    "all slots free" and confirm a booking blind (M2).
    busy = _read_busy(now)
    if busy is None:
        _release(
            db,
            link.id,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "couldn't confirm the time is free just now — please retry",
        )
    if not msvc.slot_is_free(body.slot, minutes, busy):
        _release(db, link.id, status.HTTP_409_CONFLICT, "that time was just taken — pick another")

    # 4. Create the event (sendUpdates=all sends the invites). A Google hard-fail releases + 503s.
    start = msvc.iso_z(msvc.parse_iso(body.slot))
    end = msvc.iso_z(msvc.parse_iso(body.slot) + timedelta(minutes=minutes))
    prospect = db.get(Prospect, lead.prospect_id) if lead.prospect_id else None
    attendees = _attendees(prospect, brief_data)
    try:
        event = g.create_event(
            summary=f"{tenant.name if tenant else 'HoldSlot'} · intro call",
            description="Booked via HoldSlot.",
            start=start,
            end=end,
            timezone=tz_name,
            attendees=attendees,
        )
    except g.GoogleError:
        log.warning("book: google create_event failed for lead=%s — released claim", lead.id)
        _release(
            db,
            link.id,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "couldn't create the meeting just now — please retry",
        )

    # 5. Persist the ONE meeting row (approval_id snapshotted off the lead) + advance the stage.
    meet_link = event.get("hangoutLink")
    meeting = Meeting(
        tenant_id=link.tenant_id,
        campaign_lead_id=lead.id,
        prospect_id=lead.prospect_id,
        approval_id=lead.approval_id,  # the billing-evidence snapshot at booking time
        google_event_id=event.get("id"),
        meet_link=meet_link,
        scheduled_at=msvc.parse_iso(body.slot),
    )
    db.add(meeting)
    db.flush()
    _advance_to_meeting(db, lead)
    db.commit()
    return BookingConfirm()


def _attendees(prospect: Prospect | None, brief_data: dict) -> list[str]:
    out: list[str] = []
    email = (prospect.enrichment if prospect else None) or {}
    if email.get("email"):
        out.append(email["email"])
    attendee = brief_attendee(brief_data)
    if attendee and attendee not in out:
        out.append(attendee)
    return out


def _advance_to_meeting(db: Session, lead: CampaignLead) -> None:
    """Move the lead to `meeting` via the shared allowed-moves writer — but a lead the operator
    deliberately sent a link to from a non-bookable stage still books; the move is just skipped +
    logged (FT3-14). Lazy import avoids a campaigns↔meetings module cycle."""
    from app.domains.campaigns.router import record_stage_move
    from app.domains.campaigns.service import MEETING

    moved = record_stage_move(db, lead, MEETING, via="booking")
    if not moved:
        log.info("book: lead=%s stage=%s not advanced to meeting (deliberate)", lead.id, lead.stage)


# --------------------------------------------------------------------------- feedback (F5)


def _load_feedback(db: Session, token: str) -> FeedbackLink | None:
    return db.execute(
        select(FeedbackLink).where(FeedbackLink.token_hash == hash_token(token))
    ).scalar_one_or_none()


@router.get("/feedback/{token}", response_model=FeedbackView)
def view_feedback(token: str, db: Session = Depends(get_db)) -> FeedbackView:
    """The feedback page view — never-404, same state machine as booking."""
    link = _load_feedback(db, token)
    if link is None:
        return FeedbackView(state="expired")
    now = datetime.now(UTC)
    state = msvc.link_state(link.used_at, link.expires_at, now)
    if state != "valid":
        return FeedbackView(state=state, expires_at=_iso(link.expires_at))
    tenant = db.get(Tenant, link.tenant_id)
    return FeedbackView(
        state="valid", client_name=tenant.name if tenant else "", expires_at=_iso(link.expires_at)
    )


@router.post("/feedback/{token}", response_model=FeedbackConfirm)
def submit_feedback(token: str, body: FeedbackIn, db: Session = Depends(get_db)) -> FeedbackConfirm:
    """Record the post-meeting feedback onto the meeting row (1:1), single-use. A second submit 410s
    (the atomic claim), so the answers can't be overwritten."""
    link = _load_feedback(db, token)
    if link is None:
        raise HTTPException(status.HTTP_410_GONE, "this link is invalid or has expired")
    now = datetime.now(UTC)
    if msvc.link_state(link.used_at, link.expires_at, now) != "valid":
        raise HTTPException(status.HTTP_410_GONE, "this link is no longer valid")

    claimed = db.execute(
        update(FeedbackLink)
        .where(FeedbackLink.id == link.id, FeedbackLink.used_at.is_(None))
        .values(used_at=now)
    )
    if claimed.rowcount == 0:
        raise HTTPException(status.HTTP_410_GONE, "this link is no longer valid")

    meeting = db.get(Meeting, link.meeting_id)
    if meeting is not None:
        meeting.feedback_rating = body.rating
        meeting.feedback_chips = list(body.chips)
        meeting.feedback_comment = body.comment.strip()
        meeting.feedback_at = now
    db.commit()
    return FeedbackConfirm(state="received")
