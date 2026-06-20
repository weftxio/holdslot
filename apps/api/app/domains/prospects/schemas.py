"""API I/O for the prospects domain (C2/C3/C4/C5/C6).

Thin Pydantic shapes over the ORM rows; the business logic lives in the pure modules
(`suppression`, `clay`, `fit`, `sourcing`). The round-history list doubles as the C4 cost
scoreboard (`cost_per_accepted` is derived, not stored).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateIn(BaseModel):
    """A seed prospect to push to Clay (C2). Mirrors the Clay push-input contract."""

    full_name: str = ""
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    domain: str = ""
    linkedin_url: str = ""
    email: str = ""
    company_industry: str = ""
    target_titles: str = ""
    target_seniority: str = ""


class ResearchRequestIn(BaseModel):
    """C2 — push a suppressed, deduped candidate set into the one Clay webhook for an ICP."""

    candidates: list[CandidateIn] = Field(default_factory=list)


class DropSummary(BaseModel):
    reason: str
    count: int


class ResearchResult(BaseModel):
    """C2 result — the suppression scoreboard + how many rows actually reached Clay."""

    run_id: str
    received: int
    pushed: int
    suppressed: int
    drops: list[DropSummary] = []


class ProspectOut(BaseModel):
    """One Prospect-list row (C6) — fit context + source, scoped to the caller's client."""

    id: str
    identity_key: str
    icp_id: str | None = None
    run_id: str | None = None
    full_name: str = ""
    company: str = ""
    domain: str = ""
    email: str = ""
    email_valid: bool = False
    title: str = ""
    company_industry: str = ""
    company_size: str = ""
    fit_score: int | None = None
    fit_tier: str | None = None
    fit_reason: str = ""
    reason_tags: list[str] = []
    source: str = ""
    status: str = ""
    created_at: str | None = None


class ImportResult(BaseModel):
    """C3 result — what an exported CSV became after suppress → store → score."""

    run_id: str | None = None
    parsed: int
    stored: int
    suppressed: int
    scored: int
    score_errors: int = 0
    by_tier: dict[str, int] = {}


class ResearchRunOut(BaseModel):
    """C4 — one round in the history table; `cost_per_accepted` is the derived $/accepted."""

    run_id: str
    source: str
    prompt_version: str | None = None
    rubric_version: str | None = None
    rows_pushed: int
    rows_accepted: int
    cost_usd: float | None = None
    cost_per_accepted: float | None = None
    created_at: str | None = None


class SourcingDocOut(BaseModel):
    kind: str
    version: int
    body: str
    created_at: str | None = None


class SourcingDocList(BaseModel):
    """Latest + version list per kind, for the Sourcing-controls panel chips."""

    sourcing_prompt: SourcingDocOut | None = None
    fit_rubric: SourcingDocOut | None = None
    prompt_versions: list[int] = []
    rubric_versions: list[int] = []


class SourcingDocIn(BaseModel):
    """Save the founder's edit as the next version of one kind."""

    kind: str  # sourcing_prompt | fit_rubric
    body: str


class SourcingRoundIn(BaseModel):
    icp_id: str | None = None
    seed_limit: int = 10  # how many existing passed-fit prospects to anchor on


class SourcingCandidate(BaseModel):
    """A pending-review AI candidate (the raw evidence object + its computed identity)."""

    identity_key: str
    full_name: str = ""
    company: str = ""
    domain: str = ""
    preliminary_tier: str = ""
    evidence: dict = {}


class SourcingRoundResult(BaseModel):
    run_id: str
    returned: int
    validated: int
    suppressed: int
    pending_review: int
    candidates: list[SourcingCandidate] = []


class AcceptIn(BaseModel):
    """Accept pending AI candidates by identity key → push them through the C2 path."""

    identity_keys: list[str] = Field(default_factory=list)
