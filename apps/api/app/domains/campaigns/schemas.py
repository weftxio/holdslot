"""Pydantic contracts for the console campaign + reply-queue surface (JWT, owner).

The public webhook route (`domains/campaigns/webhooks.py`) takes a raw JSON body, so it needs no
schema here. Counts/metrics on every Out shape are DERIVED from `outreach_event` (never stored)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- create / variants (E3)


class VariantIn(BaseModel):
    """One A/B/C outreach variant. `key` is A/B/C; blank fields fall back on the server default."""

    key: str
    subject: str = ""
    body: str = ""


class CampaignCreateIn(BaseModel):
    """Create a draft campaign from an APPROVED batch. `name` defaults from the batch; `variants`
    default to one seeded `A` variant when omitted (the founder authors real copy before launch)."""

    batch_id: str
    name: str | None = None
    variants: list[VariantIn] = Field(default_factory=list)


class VariantOut(BaseModel):
    key: str
    subject: str
    body: str
    is_winner: bool = False
    # DERIVED from the event ledger (per-variant), never stored.
    sent: int = 0
    opens: int = 0
    replies: int = 0


class CampaignOut(BaseModel):
    """A campaign with DERIVED funnel counts (status: draft/launching/sending/paused/completed)."""

    id: str
    batch_id: str
    batch_name: str = ""
    name: str
    icp: str = ""
    status: str
    smartlead_campaign_id: str | None = None
    lead_total: int = 0
    stages: dict[str, int] = Field(default_factory=dict)  # current stage → lead count
    created_at: str | None = None
    updated_at: str | None = None


class LeadEventOut(BaseModel):
    """One row in a lead's per-card timeline — DERIVED from `outreach_event` (never stored)."""

    event_type: str
    direction: str  # out (we sent) · in (prospect acted) · sys (workflow)
    title: str
    summary: str = ""
    occurred_at: str | None = None


class LeadOut(BaseModel):
    """One prospect in the funnel — a `campaign_lead` ⋈ its prospect enrichment + event timeline.
    Grouped by `company` into the Campaign-tab cards; `stage` is the funnel SoT."""

    id: str
    prospect_name: str = ""
    prospect_role: str = ""
    company: str = ""
    stage: str
    variant_key: str | None = None
    opened: bool = False
    replied: bool = False
    events: list[LeadEventOut] = Field(default_factory=list)


class CampaignDetailOut(CampaignOut):
    variants: list[VariantOut] = Field(default_factory=list)
    leads: list[LeadOut] = Field(default_factory=list)


class VariantsIn(BaseModel):
    """Replace a draft campaign's variant set (editing before launch, E7)."""

    variants: list[VariantIn] = Field(default_factory=list)


# --------------------------------------------------------------------------- stage move (E4/E7)


class StageMoveIn(BaseModel):
    """Manually move a lead to another funnel stage (illegal → 409). Mirrors the FE dropdown."""

    stage: str


# --------------------------------------------------------------------------- reply queue (E5)


class ReplyOut(BaseModel):
    """One row in the cross-campaign reply-triage inbox (`outreach_event(lead_replied)` ⋈ lead)."""

    id: str
    campaign_id: str
    campaign_name: str = ""
    campaign_lead_id: str | None = None
    prospect_name: str = ""
    prospect_role: str = ""
    stage: str = ""
    reply_body: str = ""
    subject: str = ""
    occurred_at: str | None = None
    triage: str | None = None
    handled_at: str | None = None
    response_body: str | None = None


class TriageIn(BaseModel):
    """Classify a reply (positive / objection-timing / referral / nudge / negative). Positive →
    `replied`, negative → `drop`; the rest just mark it handled (no stage move)."""

    triage: str


class RespondIn(BaseModel):
    """Send an operator-authored threaded reply (→ Smartlead `reply_to_thread`).

    `include_booking_link` (F3) mints a single-use booking link for the lead and substitutes it
    into the reply (`{{booking_link}}` placeholder, or appended) — the one booking-link carrier."""

    body: str
    include_booking_link: bool = False


# --------------------------------------------------------------------------- variant winner (E6)


class WinnerIn(BaseModel):
    key: str


# ------------------------------------------------------------------------ performance summary (E7)


class FunnelStage(BaseModel):
    label: str
    n: int


class MeetingCalendarItem(BaseModel):
    id: str
    scheduled_at: str  # UTC `…Z`; the FE renders viewer-local
    prospect_name: str = ""
    outcome: str | None = None


class PerformanceSummaryOut(BaseModel):
    """Derived-on-read (no stored counters). The Leads-funnel + reply stats go live at E7; the
    meeting-dependent cells go live at F5 (the summary read runs the F4 sweep first)."""

    funnel: list[FunnelStage] = Field(default_factory=list)
    new_positive_replies: int = 0
    replies_awaiting_review: int = 0
    approvals_pending: int = 0  # needs-attention ① (batches sent, undecided — D data, live today)
    meetings_booked: int = 0  # ever-reached meeting (funnel + headline)
    # Phase-F meeting cells (live at F5).
    qualified_last_30d: int = 0
    qualified_delta: int = 0  # vs the prior 30-day window
    meetings_held_week: int = 0
    show_up_rate: float | None = None  # held ÷ ingested
    awaiting_this_week: int = 0
    billable_this_cycle: float = 0.0  # Σ is_billable amounts
    open_booking_links: int = 0  # needs-attention ② (unused booking links)
    held_without_feedback: int = 0  # needs-attention ③ (held meetings, no feedback)
    calendar: list[MeetingCalendarItem] = Field(default_factory=list)
