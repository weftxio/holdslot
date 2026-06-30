"""External (token-only) approval contracts. `ApprovalProspect` is the MASKING ALLOW-LIST — it
declares EXACTLY the fields the client may see; the response_model emits nothing else, so a new
field on the underlying row can never leak. `DecisionIn` is shared with the console decide."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ApprovalProspect(BaseModel):
    """The allow-list. Fit context ONLY — no email/phone/LinkedIn, no full last name, no exact
    company name/domain, no `fit_components`, no verified-presence badges."""

    id: str  # the prospect_approval id — the opaque decide handle (carries no identity)
    name: str  # "Sarah K." — first name + last initial
    company_descriptor: str  # "SaaS · 200–500 · US" — firmographics, NOT the exact company
    title: str = ""
    seniority: str = ""
    fit_tier: str | None = None
    fit_reason: str = ""
    decision: str


class ApprovalView(BaseModel):
    """What `GET /approve/{token}` returns. `state` picks the page's pane; `prospects` is populated
    only when `state == "valid"`."""

    state: str  # valid · expired · used
    batch_name: str = ""
    client_name: str = ""
    count: int = 0  # live (non-removed) prospect count
    expires_at: str | None = None
    prospects: list[ApprovalProspect] = Field(default_factory=list)


class ApprovalDecisionOut(BaseModel):
    status: str  # the resulting batch.status (approved · changes_requested)
    approved: int = 0
    removed: int = 0
