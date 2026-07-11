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
    """Send an operator-authored threaded reply (→ Smartlead `reply_to_thread`)."""

    body: str


# --------------------------------------------------------------------------- variant winner (E6)


class WinnerIn(BaseModel):
    key: str


# ------------------------------------------------------------------------ performance summary (E7)


class FunnelStage(BaseModel):
    label: str
    n: int


class PerformanceSummaryOut(BaseModel):
    """Derived-on-read (no stored counters). The Leads-funnel + reply stats go live at E7; the
    meeting-dependent cells stay 0/None until Phase F writes `meeting` moves."""

    funnel: list[FunnelStage] = Field(default_factory=list)
    new_positive_replies: int = 0
    replies_awaiting_review: int = 0
    approvals_pending: int = 0  # needs-attention ① (batches sent, undecided — D data, live today)
    # Phase-F cells (0/None until F): meetings held, billable, show-up rate, calendar.
    meetings_booked: int = 0
