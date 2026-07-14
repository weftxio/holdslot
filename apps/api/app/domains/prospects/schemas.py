"""API I/O for the prospects domain (Apollo find + enrich).

Thin Pydantic shapes over the ORM rows; the business logic lives in the pure modules
(`suppression`, `fit`). The research-run list doubles as the cost scoreboard (`cost_usd` per run).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyEnrichment(BaseModel):
    """The 8 Apollo-enrich fields surfaced for user study (the "Enrichment" column), normalized
    from `Company.evidence`. All optional — an un-enriched / manual row carries empty values."""

    short_description: str = ""
    industries: list[str] = []  # primary + secondary, deduped
    annual_revenue: float | None = None  # USD, raw — the web formats it compact
    founded_year: int | None = None
    headcount_growth_12mo: float | None = None  # fraction (0.04 = +4%); web formats as %
    technologies: list[str] = []
    keywords: list[str] = []
    hq: str = ""  # "City, State"


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
    fit_reason: str = ""
    # Stage-1 B2B/B2C label (B2B · B2C · Complex · Unknown; "" if classified before the label
    # shipped). Feeds the v2 market gate + the Step-1 model chip. Empty until the row is classified.
    business_model: str = ""
    # Scoring v2 (build plan §D+.2) — the 4-label contract (the v1 0–100 fit_* fields
    # were retired in V2-4). `label` is null until (re)scored ("needs re-score"); `reason`
    # is the always-populated one-liner; `subscores` is the 4-axis 1–5 map; `flags` non-blocking
    # markers; `icp` the A/B badge.
    label: str | None = None
    score_total: int | None = None
    reason: str = ""
    subscores: dict = Field(default_factory=dict)
    flags: list[str] = []
    icp: str | None = None
    enrichment: CompanyEnrichment = Field(default_factory=CompanyEnrichment)
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
    the spec's `credit_policy.max_companies` server-side.

    `company_search_params`/`intent_filters` are an OPTIONAL operator override (the Settings modal):
    when present they replace the spec's blocks for *this call only* — the spec stays the AI source
    of truth, the override is the manual tuning. Omitted → the saved spec is used unchanged.

    `limit` defaults to the async ceiling (`FIND_COMPANY_LIMIT`); the web app omits it so a find
    targets the full width. (The v1 sync route + its separate clamp were retired in V2-4.)
    """

    limit: int = 100
    icp_id: str | None = None
    company_search_params: dict | None = None
    intent_filters: dict | None = None


class PeopleFindIn(BaseModel):
    """Trigger Apollo Flow B (find people) across an explicit set of Step-2 companies. `per_company`
    is how many people each org contributes (one api_search call per org); the default fetches
    everyone matching the Find Settings, up to Apollo's 100-per-call max — no artificial 10 cap.

    `company_ids` are the Step-2 rows to search, by Company.id. The search is driven by this set —
    NOT a server-side "selected" status — so an already-searched company can be re-searched and a
    0-result company is never permanently burned. Rows land UNSCORED ("Pending"); the operator
    scores on demand via the Step-2 'Get AI score' button (`/prospects/rescore`).

    `people_search_params` is an OPTIONAL operator override (the Step-2 Settings modal): when
    present it replaces the spec's people block for *this call only* (`organization_ids` is still
    set per-org by the loop, never by the override). Omitted → the saved spec is used unchanged.
    """

    per_company: int = 100
    icp_id: str | None = None
    people_search_params: dict | None = None
    company_ids: list[str] = Field(default_factory=list)
    # FE-minted uuid threading the chunked calls of one merged stage→find (U3 runs find-people in
    # 8-org chunks); stored in `research_run.result_meta.group_id` so the drawer collapses them.
    group_id: str | None = None


class PeopleFacetsIn(BaseModel):
    """Compute the live Find-Settings facet sidebar for an explicit set of Step-2 companies.

    Counts are scoped to the union of the selected companies' Apollo orgs (one `organization_ids`
    array) and computed PER facet value — exactly Apollo's UI sidebar ("Manager (9), Senior (3)…").
    Free: people search costs no credits. `company_ids` are Company.id; companies without an Apollo
    org id are ignored."""

    company_ids: list[str] = Field(default_factory=list)


class FacetOption(BaseModel):
    """A selectable Apollo facet value + its human label (no count)."""

    value: str
    label: str


class FacetCount(FacetOption):
    """A facet value with its live people count in scope."""

    count: int


class DepartmentFacet(FacetCount):
    """A master department row (with count) + its selectable subdepartment options. Only the 14
    masters are probed for counts, to bound the request to 11 + 14 free calls; subs are
    selection-only (the operator can refine to a subdepartment, but it shows no live count)."""

    subs: list[FacetOption] = Field(default_factory=list)


class PeopleFacetsOut(BaseModel):
    """The facet sidebar: total people in scope + per-Management-Level and per-Department counts."""

    total: int
    seniorities: list[FacetCount]
    departments: list[DepartmentFacet]


class ScopeOverrideIn(BaseModel):
    """Save a Find-Settings override for one (pipeline step, ICP). `params` is the step's Apollo
    block — people: `{people_search_params}`; company: `{company_search_params, intent_filters}`.
    An all-empty block is a revert (the endpoint drops the ICP's entry); DELETE also reverts."""

    params: dict = Field(default_factory=dict)


class ScopeOverrideOut(BaseModel):
    """The saved override block for one (step, ICP), or `null` when none is saved (→ AI scope)."""

    params: dict | None = None


class CompanyLookalikeIn(BaseModel):
    """Find peers of the selected stage-1 rows (the 'Lookalike' button). The seeds are aggregated
    into an Apollo company-search filter HoldSlot-side (Apollo has no native lookalike API), then
    run through the normal Flow A tail — the seeds drop out by domain dedupe, so the result is the
    *next* batch. `icp_id` overrides the seeds' common ICP for fit scoring (omitted → inferred)."""

    company_ids: list[str] = Field(default_factory=list)
    icp_id: str | None = None


class CompanySelectIn(BaseModel):
    """Select/deselect stage-1 companies (scopes Flow B). `selected=False` reverts to discovered."""

    ids: list[str] = Field(default_factory=list)
    selected: bool = True


class CompanyRescoreIn(BaseModel):
    """Re-run company fit scoring for an explicit set of already-sourced companies (the Step-1
    selection). Unlike find-company, this ignores the `label is None` (unscored) gate — it re-scores
    the given rows against the current rubric + scoring prompt so an existing list reflects an edit.
    """

    ids: list[str] = Field(default_factory=list)


class CompanyEnrichIn(BaseModel):
    """Refresh Apollo firmographics (the 'Update Field' button) for an explicit set of selected
    companies — re-enrich each row's industry/size/country/evidence on demand. This is the
    deliberate credit spend; find-company only enriches NEW rows to avoid paying twice per org."""

    ids: list[str] = Field(default_factory=list)


class ProspectRescoreIn(BaseModel):
    """Re-run people fit scoring for an explicit set of already-found prospects (by identity key) —
    the Step-2 'Get AI score' button. Mirrors CompanyRescoreIn: re-scores against the current rubric
    regardless of whether the row was scored, so the people list reflects a rubric change."""

    identity_keys: list[str] = Field(default_factory=list)


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
    fit_reason: str = ""
    # Scoring v2 (people tier — the company label caps the person; the v1 fit_* fields were retired
    # in V2-4). Null `label` until (re)scored.
    label: str | None = None
    score_total: int | None = None
    reason: str = ""
    subscores: dict = Field(default_factory=dict)
    flags: list[str] = []
    icp: str | None = None
    source: str = ""
    status: str = ""
    created_at: str | None = None


class ScoringJobOut(BaseModel):
    """Async scoring-job status (W4) — polled until `status` is `done`/`error`. `result` carries the
    per-run counts (`{scored, failed, cost_usd}`); `status=idle` when no job of the kind has run.
    """

    job_id: str | None = None
    status: str  # idle | queued | running | done | error
    result: dict = Field(default_factory=dict)
    error: str | None = None


class ProspectPage(BaseModel):
    """One page of the prospect list feed (W5). `next_cursor` is the opaque cursor for the page
    after this one, or `null` at the end — the web app follows it until exhausted or the ceiling.
    """

    items: list[ProspectOut] = []
    next_cursor: str | None = None


class CompanyPage(BaseModel):
    """One page of the company list feed (W5) — same envelope as `ProspectPage`."""

    items: list[CompanyOut] = []
    next_cursor: str | None = None


class FindResult(BaseModel):
    """Result of a find run: the run id + counts + the rows that landed (best fit first).

    D+ Stage 3: `scope_exhausted` = the page cursor reached the end of this scope's Apollo results
    (the "regenerate" signal); `known_skipped` = rows dropped as already stored for the tenant (the
    $0 invariant — never re-enriched/re-classified/re-stamped)."""

    run_id: str
    found: int
    dropped: int
    companies: list[CompanyOut] = []
    prospects: list[ProspectOut] = []
    scope_exhausted: bool = False
    known_skipped: int = 0


class ResearchRunOut(BaseModel):
    """One research run. The `scope_source` / `filter_body` / `result_meta` fields (D+ Stage 1,
    migration 0019) feed the Find-history drawer — they are None for runs recorded before 0019.
    (N26/S16 — `cost_per_accepted` + `rows_accepted` + `rubric_version` dropped from the Out shape:
    `rows_accepted` was never written; the underlying columns stay for DB lineage.)"""

    run_id: str
    source: str
    prompt_version: str | None = None
    rows_pushed: int
    cost_usd: float | None = None
    icp_id: str | None = None
    scope_source: str | None = None
    filter_body: dict | None = None
    result_meta: dict | None = None
    created_at: str | None = None


class SourcingDocOut(BaseModel):
    stage: str
    version: int
    body: str
    created_at: str | None = None


class SourcingDocList(BaseModel):
    """Latest version of each editable fit rubric: `company_fit` (Step 1) and
    `prospect_fit` (Step 2)."""

    company_fit: SourcingDocOut | None = None
    prospect_fit: SourcingDocOut | None = None


class SourcingDocIn(BaseModel):
    """Save the founder's edit as the next version of a fit rubric
    (`company_fit` | `prospect_fit`)."""

    stage: str  # company_fit | prospect_fit
    body: str


class FitPromptOut(BaseModel):
    """The exact system + input prompt a company fit-score call would send (preview, no LLM call).

    Mirrors the scoping-prompt preview, but for stage-1 company scoring: `user` carries the real
    TARGETING CONTEXT (this client's brief + research spec + ICP docs from the DB) plus the sample
    company, so the Fit-rubric modal shows what actually reaches the model. `company` names the
    sample row used; null when the tenant has no companies yet."""

    system: str
    user: str
    company: str | None = None
    model: list[str]
    purpose: str
    prompt_version: str
