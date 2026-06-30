"""Pydantic contracts for the console batch surface (JWT, owner). The external token-only shapes
live in `domains/approvals/schemas.py`; `DecisionIn` is shared by both decide paths."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BatchCreateIn(BaseModel):
    """Create a batch from an enriched-prospect selection. `name`/`icp_id` are optional — the server
    auto-names (`Batch N`) and infers a shared ICP when omitted."""

    prospect_ids: list[str] = Field(default_factory=list)
    name: str | None = None
    icp_id: str | None = None


class BatchOut(BaseModel):
    """A batch with DERIVED counts (never stored). status ∈ draft·sent·approved·changes_req."""

    id: str
    name: str
    icp: str = ""  # ICP name (header label), "" when unset
    status: str
    total: int
    approved: int
    removed: int
    pending: int
    created_at: str | None = None
    sent_at: str | None = None
    decided_at: str | None = None


class BatchProspect(BaseModel):
    """One prospect inside the console (FULL) batch detail — the operator owns the data, so this is
    NOT masked. The external surface uses `domains/approvals` instead."""

    approval_id: str
    prospect_id: str
    full_name: str = ""
    title: str = ""
    seniority: str = ""
    fit_tier: str | None = None
    fit_reason: str = ""
    decision: str


class BatchCompanyGroup(BaseModel):
    company: str = ""
    domain: str = ""
    industry: str = ""
    size: str = ""
    country: str = ""
    fit_tier: str | None = None
    fit_reason: str = ""
    prospects: list[BatchProspect] = Field(default_factory=list)


class BatchDetailOut(BatchOut):
    companies: list[BatchCompanyGroup] = Field(default_factory=list)


class SendIn(BaseModel):
    """Send (or Follow-Up resend) the approval email to the client recipient."""

    email: str


class DecisionIn(BaseModel):
    """Approve/remove a batch's prospects. Shared by the external client decide and the console
    step-3 human fallback. Approve-the-rest: `removed_ids` off, everyone else approved; or an
    explicit `approved_ids` set; or `request_changes` to flag the whole batch."""

    approved_ids: list[str] | None = None
    removed_ids: list[str] = Field(default_factory=list)
    request_changes: bool = False


class TemplateIn(BaseModel):
    subject: str = ""
    body: str = ""
    cta: str = ""


class TemplateOut(BaseModel):
    subject: str
    body: str
    cta: str
