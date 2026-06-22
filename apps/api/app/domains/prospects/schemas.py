"""API I/O for the prospects domain (Apollo find + enrich).

Thin Pydantic shapes over the ORM rows; the business logic lives in the pure modules
(`suppression`, `fit`). The research-run list doubles as the cost scoreboard
(`cost_per_accepted` is derived, not stored).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyOut(BaseModel):
    """One stage-1 Company-list row — firmographics + company-level fit, scoped to the client."""

    id: str
    icp_id: str | None = None
    run_id: str | None = None
    domain: str = ""
    website: str = ""
    linkedin_url: str = ""
    name: str = ""
    industry: str = ""
    size: str = ""
    country: str = ""
    fit_score: int | None = None
    fit_tier: str | None = None
    fit_reason: str = ""
    reason_tags: list[str] = []
    source: str = ""
    status: str = ""
    created_at: str | None = None


class CompanyManualIn(BaseModel):
    """Manually add one company (stage-1 gate) — same schema as a sourced row, `source=manual`."""

    domain: str
    name: str = ""
    website: str = ""
    linkedin_url: str = ""
    industry: str = ""
    size: str = ""
    country: str = ""
    icp_id: str | None = None


class ProspectManualIn(BaseModel):
    """Manually add one person (stage-2 gate) — same schema as a sourced row, `source=manual`."""

    full_name: str = ""
    company: str = ""
    domain: str = ""
    linkedin_url: str = ""
    email: str = ""
    title: str = ""
    seniority: str = ""
    company_industry: str = ""
    company_size: str = ""
    icp_id: str | None = None


class CompanyFindIn(BaseModel):
    """Trigger Apollo Flow A (find companies) from the latest ResearchSpec. `limit` is capped to
    the spec's `credit_policy.max_companies` server-side."""

    limit: int = 25
    icp_id: str | None = None


class PeopleFindIn(BaseModel):
    """Trigger Apollo Flow B (find people) across the selected companies. `per_company` caps how
    many people each selected org contributes (one api_search call per org)."""

    per_company: int = 10
    icp_id: str | None = None


class CompanySelectIn(BaseModel):
    """Select/deselect stage-1 companies (scopes Flow B). `selected=False` reverts to discovered."""

    ids: list[str] = Field(default_factory=list)
    selected: bool = True


class EnrichIn(BaseModel):
    """Confirm which scored people to enrich (the enrich gate) by identity key."""

    identity_keys: list[str] = Field(default_factory=list)


class EnrichResult(BaseModel):
    """Enrich-gate result — how many rows were enriched (Apollo people/match) + credits spent."""

    confirmed: int
    enriched: int = 0
    credits_spent: int = 0


class ProspectOut(BaseModel):
    """One Prospect-list row — fit context + source, scoped to the caller's client."""

    id: str
    identity_key: str
    icp_id: str | None = None
    company_id: str | None = None
    run_id: str | None = None
    full_name: str = ""
    company: str = ""
    domain: str = ""
    linkedin_url: str = ""
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


class FindResult(BaseModel):
    """Result of a find run: the run id + counts + the rows that landed (best fit first)."""

    run_id: str
    found: int
    dropped: int
    companies: list[CompanyOut] = []
    prospects: list[ProspectOut] = []


class ResearchRunOut(BaseModel):
    """One research run; `cost_per_accepted` is the derived $/accepted."""

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
    stage: str
    version: int
    body: str
    created_at: str | None = None


class SourcingDocList(BaseModel):
    """Latest + version list for the fit rubric (the one editable scoring doc)."""

    fit_scoring: SourcingDocOut | None = None
    rubric_versions: list[int] = []


class SourcingDocIn(BaseModel):
    """Save the founder's edit as the next version of the fit-scoring rubric."""

    stage: str  # fit_scoring
    body: str
