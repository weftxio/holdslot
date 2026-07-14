"""Phase F API schemas — public booking/feedback views + console meeting/booking/feedback rows."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- public booking (F3)


class BookingView(BaseModel):
    """`GET /book/{token}` — never-404. Non-valid states carry only `state` (no leak)."""

    state: str  # valid · used · expired
    client_name: str = ""
    duration_min: int = 0
    slots: list[str] = Field(default_factory=list)  # UTC `…Z` instants; the FE groups viewer-local
    expires_at: str | None = None


class BookIn(BaseModel):
    slot: str  # one of the offered UTC instants


class OutcomeIn(BaseModel):
    """Owner correction door (F4) — re-derives amount/window; never the sweep."""

    outcome: str  # qualified · short_call · noshow
    disputed: bool | None = None
    won: bool | None = None


class WonIn(BaseModel):
    """The dedicated `won` setter (NF-3 / GF-9) — writes the post-sale deal flag ONLY. Kept apart
    from OutcomeIn so a conversion mark can never re-derive amount/window (billing isolation);
    `null` clears it back to undecided."""

    won: bool | None = None


class SweepResult(BaseModel):
    swept: int = 0
    qualified: int = 0
    noshow: int = 0


class BookingConfirm(BaseModel):
    state: str = "confirmed"


# --------------------------------------------------------------------------- public feedback (F5)


class FeedbackView(BaseModel):
    state: str  # valid · used · expired
    client_name: str = ""
    expires_at: str | None = None


class FeedbackIn(BaseModel):
    # M16 — public token-authed input: bound the free fields so a link holder can't store MBs on the
    # meeting row (the FE only ever sends ≤5 short chips + a small comment).
    rating: int = Field(ge=1, le=5)
    chips: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=12)
    comment: str = Field("", max_length=2000)


class FeedbackConfirm(BaseModel):
    state: str = "received"


# --------------------------------------------------------------------------- console reads (F5)


class MeetingOut(BaseModel):
    id: str
    prospect_name: str = ""
    company_name: str = ""
    campaign_name: str = ""
    campaign_id: str | None = None  # M27 — FE filters key off id, not the non-unique name
    batch_name: str = ""
    scheduled_at: str
    held: bool | None = None
    outcome: str | None = None
    amount: float | None = None
    billing_chip: str = "Not billable"
    disputed: bool = False
    feedback_state: str = "None"
    feedback_rating: int | None = None
    won: bool | None = None


class BookingRowOut(BaseModel):
    id: str
    prospect_name: str = ""
    company_name: str = ""
    campaign_name: str = ""
    status: str  # Confirmed · Awaiting confirm · Expired
    invitation_preview: str = ""
    reply_event_id: str | None = None  # the Propose-new-time carrier handle
    sent_at: str | None = None
    expires_at: str | None = None


class FeedbackRowOut(BaseModel):
    id: str  # the meeting id
    prospect_name: str = ""
    company_name: str = ""
    state: str  # Received · Pending · None
    overdue: bool = False
    rating: int | None = None
    comment: str = ""
    feedback_at: str | None = None
    scheduled_at: str
