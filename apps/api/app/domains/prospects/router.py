"""Prospect routes — the Apollo find → score → enrich surface (Phase C, live).

One suppression gate and one scoring door (`fit.py`). Tenant scope × role is enforced by the A4
central guard, so every query is scoped to the caller's client. The heavy lifting lives in the
pure modules; this layer is orchestration + persistence.

The Clay seed/CSV-import/AI-sourcing loop was removed in the Apollo-only teardown. The two-stage
company→people loop is live: find-company / find-people return rows UNSCORED, fit scoring is an
explicit step (`/companies/rescore`, `/prospects/rescore`), and `confirm_enrich` spends the Apollo
`people/match` credit to reveal verified emails (the only credit spend in this surface).
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.deps import AccessContext, get_db, require_membership
from app.domains.briefs.research_spec import (
    DEPARTMENT_TAXONOMY,
    MASTER_DEPARTMENTS,
    SENIORITY_ENUM,
)
from app.domains.icps import icp_docs
from app.domains.prospects import apollo_map, find, fit, lookalike
from app.domains.prospects.identity import normalize_domain, normalize_email
from app.domains.prospects.schemas import (
    CompanyEnrichIn,
    CompanyEnrichment,
    CompanyFindIn,
    CompanyLookalikeIn,
    CompanyManualIn,
    CompanyOut,
    CompanyRescoreIn,
    CompanySelectIn,
    DepartmentFacet,
    EnrichIn,
    EnrichResult,
    FacetCount,
    FacetOption,
    FindResult,
    FitPromptOut,
    PeopleFacetsIn,
    PeopleFacetsOut,
    PeopleFindIn,
    PeopleScopeOverrideIn,
    PeopleScopeOverrideOut,
    ProspectManualIn,
    ProspectOut,
    ProspectRescoreIn,
    ResearchRunOut,
    SourcingDocIn,
    SourcingDocList,
    SourcingDocOut,
)
from app.domains.prospects.suppression import Candidate, extract_exclusions
from app.integrations.apollo import client as apollo
from app.integrations.openrouter.client import LlmError
from app.models import (
    Brief,
    Company,
    MembershipRole,
    Prompt,
    Prospect,
    ResearchRun,
    ResearchSpec,
    ScopeOverride,
)

router = APIRouter(tags=["prospects"])
log = logging.getLogger("holdslot.prospects")

# The two editable fit rubrics — one per scoring stage. `company_fit` (Step 1) grades buying intent;
# `prospect_fit` (Step 2) grades a person's reply potential + decision-making power. The stage names
# match the LLM purposes in `fit.py` (COMPANY_PURPOSE / PURPOSE) so doc ↔ scorer line up 1:1.
COMPANY_STAGE = "company_fit"
PROSPECT_STAGE = "prospect_fit"
_VALID_STAGES = (COMPANY_STAGE, PROSPECT_STAGE)

# Sync-budget caps. Find/enrich run synchronously behind the 30s API-Gateway HTTP-API cap, and each
# scored row is one blocking LLM call — so a single request must bound how many it does. Larger sets
# are drained over repeated calls (find_people advances each processed org to `people_found`; the
# operator re-clicks to continue). Keep the product (calls × ~1-2s) comfortably under 30s.
MAX_COMPANIES_PER_FIND = 15  # company-search rows scored per find-company request
MAX_ORGS_PER_FIND = 8  # selected orgs searched per find-people request (1 Apollo call each)
MAX_PEOPLE_PER_FIND = 15  # LLM-scored people per RESCORE request (30s sync cap; the spend)
MAX_PEOPLE_PER_FIND_RUN = 250  # unscored people landed per find-people request (free, no LLM)
LOOKALIKE_LIMIT = 10  # peers fetched per Lookalike find (seeds drop via domain dedupe → ≤10 net)


# --------------------------------------------------------------------------- helpers


def _latest_brief(db: Session, tenant_id) -> Brief | None:
    return db.execute(select(Brief).where(Brief.tenant_id == tenant_id)).scalar_one_or_none()


def _latest_spec(db: Session, tenant_id) -> ResearchSpec | None:
    """The newest ResearchSpec version for a tenant. Version-ordering / tenant-scope lives here."""
    return (
        db.execute(
            select(ResearchSpec)
            .where(ResearchSpec.tenant_id == tenant_id)
            .order_by(ResearchSpec.version.desc())
        )
        .scalars()
        .first()
    )


SCOPE_KIND_PEOPLE = "people"  # ScopeOverride.kind for the Step-2 Find Settings facets


def _people_scope_override(db: Session, tenant_id) -> ScopeOverride | None:
    """The tenant's persisted Step-2 people-scope override (the Find Settings the operator saved),
    or None → use the AI scope. Single row per (tenant, kind)."""
    return db.execute(
        select(ScopeOverride).where(
            ScopeOverride.tenant_id == tenant_id, ScopeOverride.kind == SCOPE_KIND_PEOPLE
        )
    ).scalar_one_or_none()


def _build_exclusions(brief: Brief | None, spec: ResearchSpec | None):
    return extract_exclusions(brief.data if brief else {}, spec.spec if spec else None)


def _exclusions(db: Session, tenant_id):
    return _build_exclusions(_latest_brief(db, tenant_id), _latest_spec(db, tenant_id))


def _build_targeting(
    brief: Brief | None, spec: ResearchSpec | None, icps: list[dict] | None = None
) -> dict:
    """The fit scorer's targeting context — the SAME client documents brief scoping (B) consumes.

    `icps` carries the persona profiles the rubric grades maturity/department/tech/economic-buyer
    against (docs/prompts/fit-scoring-rubric-v1.md §2/§3). Without them those sub-criteria score 0
    by the rubric's Unknown policy, so the ICP docs are not optional context — they unlock points
    that are otherwise structurally unreachable.
    """
    return {
        "brief": brief.data if brief else {},
        "spec": spec.spec if spec else {},
        "icps": icps or [],
    }


def _latest_doc(db: Session, tenant_id, stage: str) -> Prompt | None:
    return (
        db.execute(
            select(Prompt)
            .where(Prompt.tenant_id == tenant_id, Prompt.stage == stage)
            .order_by(Prompt.version.desc())
        )
        .scalars()
        .first()
    )


def _prospect_out(p: Prospect) -> ProspectOut:
    e = p.enrichment or {}
    comps = p.fit_components or {}
    return ProspectOut(
        id=str(p.id),
        identity_key=p.identity_key,
        icp_id=str(p.icp_id) if p.icp_id else None,
        company_id=str(p.company_id) if p.company_id else None,
        run_id=p.run_id,
        full_name=e.get("full_name", ""),
        company=e.get("company", ""),
        domain=e.get("domain", ""),
        linkedin_url=e.get("linkedin_url", ""),
        email=e.get("email", ""),
        email_valid=p.email_valid,
        title=e.get("title", ""),
        company_industry=e.get("company_industry", ""),
        company_size=e.get("company_size", ""),
        fit_score=p.fit_score,
        fit_tier=p.fit_tier,
        fit_reason=comps.get("fit_reason", ""),
        reason_tags=comps.get("reason_tags", []),
        source=p.source,
        status=p.status,
        created_at=p.created_at.isoformat() if p.created_at else None,
    )


# --------------------------------------------------------------------------- prospects list


@router.get("/{client}/prospects", response_model=list[ProspectOut])
def list_prospects(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[ProspectOut]:
    rows = db.execute(
        select(Prospect)
        .where(Prospect.tenant_id == ctx.tenant.id)
        .order_by(Prospect.fit_score.desc().nullslast(), Prospect.created_at.desc())
    ).scalars()
    return [_prospect_out(p) for p in rows]


# ----------------------------------------------------------- Stage 1: companies (find → review)


def _company_enrichment(ev: dict | None) -> CompanyEnrichment:
    """Normalize the raw `evidence` blob into the 8 study fields (the Enrichment column)."""
    ev = ev or {}
    industries = [*(ev.get("industries") or []), *(ev.get("secondary_industries") or [])]
    hq = ", ".join(p for p in (ev.get("city"), ev.get("state")) if p)
    return CompanyEnrichment(
        short_description=ev.get("short_description") or "",
        industries=list(dict.fromkeys(industries)),  # dedupe, keep order
        annual_revenue=ev.get("annual_revenue") or ev.get("organization_revenue") or None,
        founded_year=ev.get("founded_year"),
        headcount_growth_12mo=ev.get("organization_headcount_twelve_month_growth"),
        technologies=ev.get("technology_names") or [],
        keywords=ev.get("keywords") or [],
        hq=hq,
    )


def _company_out(c: Company) -> CompanyOut:
    comps = c.fit_components or {}
    return CompanyOut(
        id=str(c.id),
        icp_id=str(c.icp_id) if c.icp_id else None,
        run_id=c.run_id,
        domain=c.domain,
        website=c.website or "",
        linkedin_url=c.linkedin_url or "",
        name=c.name or "",
        industry=c.industry or "",
        size=c.size or "",
        country=c.country or "",
        fit_score=c.fit_score,
        fit_tier=c.fit_tier,
        fit_reason=c.fit_reason or comps.get("fit_reason", ""),
        reason_tags=comps.get("reason_tags", []),
        enrichment=_company_enrichment(c.evidence),
        source=c.source,
        status=c.status,
        created_at=c.created_at.isoformat() if c.created_at else None,
    )


def _company_payload(c: Company) -> dict:
    """The company facts the rubric scores against (stage-1 firmographics + evidence)."""
    return {
        "name": c.name,
        "domain": c.domain,
        "industry": c.industry,
        "size": c.size,
        "country": c.country,
        "linkedin_url": c.linkedin_url,
        **(c.evidence or {}),
    }


def _prospect_payload(enrichment: dict | None, company: Company | None) -> dict:
    """The person facts the stage-2 rubric scores against — the decision-maker signals (title,
    seniority, department, email) PLUS the parent company's firmographics and its stage-1 fit
    verdict, so a person is judged as a decision-maker INSIDE an already-qualified account. Apollo
    obfuscates seniority/department until enrich, so those stay empty pre-enrich (rubric Unknown
    policy applies); the intended persona scope reaches the model via the targeting `spec` block."""
    e = dict(enrichment or {})
    payload = {
        "full_name": e.get("full_name", ""),
        "title": e.get("title", ""),
        "seniority": e.get("seniority", ""),
        "departments": e.get("departments", []),
        "email": e.get("email", ""),
        "email_present": bool(e.get("email")),
        "linkedin_url": e.get("linkedin_url", ""),
        "company": e.get("company", ""),
        "company_domain": e.get("company_domain") or e.get("domain", ""),
        "company_industry": e.get("company_industry", ""),
        "company_size": e.get("company_size", ""),
    }
    if company is not None:
        payload["company_fit"] = {
            "score": company.fit_score,
            "tier": company.fit_tier,
            "reason": company.fit_reason or (company.fit_components or {}).get("fit_reason", ""),
        }
    return payload


def _apply_company_score(c: Company, scored: dict) -> float:
    """Write a company fit result onto the row in place; return the call's cost_usd."""
    c.fit_score = scored["fit_score"]
    c.fit_tier = scored["fit_tier"]
    c.fit_components = scored["fit_components"]
    c.fit_reason = scored["fit_reason"]
    return float(scored.get("cost_usd") or 0.0)


def _score_company(c: Company, *, tenant_id, rubric_body: str, targeting: dict) -> float:
    """Score one company in place (LLM). Returns the call's cost_usd. Raises LlmError."""
    return _apply_company_score(
        c,
        fit.score_company(
            tenant_id=tenant_id,
            rubric_body=rubric_body,
            company=_company_payload(c),
            targeting=targeting,
        ),
    )


# A full find can score up to MAX_*_PER_FIND rows; a *sequential* LLM call per row overruns the 30s
# API Gateway sync cap (→ 503). The LLM client is stdlib-urllib with its own telemetry session per
# call, so the calls are thread-safe — we fan them out, then apply each result on the main thread
# (ORM mutation stays single-threaded). Workers ≥ the per-find cap so the whole batch scores in ONE
# wave: with DeepSeek V4 Pro reasoning ON the wall-clock is ~one reasoning call, not stacked waves.
_SCORE_WORKERS = MAX_COMPANIES_PER_FIND


def _score_concurrently(jobs: list[tuple]) -> list[tuple]:
    """Run independent fit-score jobs concurrently. `jobs` = [(key, fn)] where `fn() -> scored dict`
    (or raises LlmError). Returns [(key, scored | None)] — None when that call failed (row kept
    unscored). Each `fn` must close over plain data, never touch the request session off-thread."""
    if not jobs:
        return []

    def _run(job: tuple) -> tuple:
        key, fn = job
        try:
            return key, fn()
        except LlmError:
            return key, None

    with ThreadPoolExecutor(max_workers=min(_SCORE_WORKERS, len(jobs))) as ex:
        return list(ex.map(_run, jobs))


@router.get("/{client}/companies", response_model=list[CompanyOut])
def list_companies(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[CompanyOut]:
    """Stage-1 review feed — companies for this client, best fit first."""
    rows = db.execute(
        select(Company)
        .where(Company.tenant_id == ctx.tenant.id)
        .order_by(Company.fit_score.desc().nullslast(), Company.created_at.desc())
    ).scalars()
    return [_company_out(c) for c in rows]


@router.post("/{client}/companies", response_model=CompanyOut, status_code=201)
def add_company(
    body: CompanyManualIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> CompanyOut:
    """Stage-1 manual add — one company, `source=manual`, same schema + scoring as sourced rows.

    Upserts on (tenant, domain) so a manual add of an existing company updates it in place.
    """
    domain = normalize_domain(body.domain)
    if not domain or "." not in domain:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a valid company domain is required")
    if exclusions := _exclusions(db, ctx.tenant.id):
        if exclusions.blocks(Candidate(domain=domain)):
            raise HTTPException(status.HTTP_409_CONFLICT, "company is on the exclusion list")

    icp = uuid.UUID(body.icp_id) if body.icp_id else None
    brief, spec = _latest_brief(db, ctx.tenant.id), _latest_spec(db, ctx.tenant.id)
    targeting = _build_targeting(brief, spec, icp_docs(db, ctx.tenant.id, icp))
    rubric = _latest_doc(db, ctx.tenant.id, COMPANY_STAGE)
    rubric_body = rubric.body if rubric else ""

    company = db.execute(
        select(Company).where(Company.tenant_id == ctx.tenant.id, Company.domain == domain)
    ).scalar_one_or_none()
    if company is None:
        company = Company(tenant_id=ctx.tenant.id, domain=domain, source="manual")
        db.add(company)
    company.source = "manual"  # a manual upload is authoritative for provenance, even on re-add
    company.name = body.name or company.name or ""
    company.website = body.website or company.website
    company.linkedin_url = body.linkedin_url or company.linkedin_url
    company.industry = body.industry or company.industry
    company.size = body.size or company.size
    company.country = body.country or company.country
    if icp:
        company.icp_id = icp
    try:
        _score_company(
            company, tenant_id=ctx.tenant.id, rubric_body=rubric_body, targeting=targeting
        )
    except LlmError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"scoring failed: {e}") from e
    db.commit()
    db.refresh(company)
    return _company_out(company)


# --------------------------------------------------------------- Stage 1: Apollo Flow A (find)


def _apollo_run_id() -> str:
    return f"apollo-{uuid.uuid4().hex[:12]}"


def _enrich_survivors(survivors: list[dict]) -> None:
    """Enrich the surviving search rows in place via `organizations/bulk_enrich` — promote real
    industry/size/country onto each row and merge buying-intent evidence (tech, keywords, headcount
    growth, description) so the scorer judges firmographics instead of nulls. Best-effort: an Apollo
    failure logs and leaves the sparse search rows untouched rather than failing the whole find.
    """
    domains = [p["domain"] for p in survivors if p.get("domain")]
    if not domains:
        return
    try:
        rows = apollo.enrich_organizations(domains)
    except apollo.ApolloError as e:
        log.warning("company enrich skipped (%s) — scoring on sparse search rows", e)
        return
    by_domain: dict[str, dict] = {}
    for o in rows:
        e = apollo_map.parse_enrich(o)
        if e.get("domain"):
            by_domain[e["domain"]] = e
    for p in survivors:
        e = by_domain.get(p.get("domain"))
        if not e:
            continue
        for col in ("industry", "size", "country"):
            if e.get(col):
                p[col] = e[col]
        p["apollo_org_id"] = p.get("apollo_org_id") or e.get("apollo_org_id")
        p["website"] = p.get("website") or e.get("website")
        p["linkedin_url"] = p.get("linkedin_url") or e.get("linkedin_url")
        p["evidence"] = {**(p.get("evidence") or {}), **(e.get("evidence") or {})}


def _new_survivors(db: Session, tenant_id, survivors: list[dict]) -> list[dict]:
    """The survivors NOT already stored for this tenant (by domain OR apollo_org_id). find-company
    enriches only these — an org already in the list would re-enrich to the same firmographics and
    waste an Apollo credit; the 'Update Field' button is the deliberate refresh path for existing
    rows."""
    domains = [p["domain"] for p in survivors if p.get("domain")]
    org_ids = [p["apollo_org_id"] for p in survivors if p.get("apollo_org_id")]
    if not domains and not org_ids:
        return list(survivors)
    rows = db.execute(
        select(Company.domain, Company.apollo_org_id).where(
            Company.tenant_id == tenant_id,
            or_(Company.domain.in_(domains), Company.apollo_org_id.in_(org_ids)),
        )
    ).all()
    ex_domains = {r[0] for r in rows}
    ex_orgs = {r[1] for r in rows if r[1]}
    return [
        p
        for p in survivors
        if p.get("domain") not in ex_domains and p.get("apollo_org_id") not in ex_orgs
    ]


def _apply_enrichment(company: Company, e: dict) -> None:
    """Write a parsed-enrich dict onto a stored Company (industry/size/country + merged evidence);
    a null enrich value never clobbers an existing one. Used by the 'Update Field' refresh."""
    company.industry = e.get("industry") or company.industry
    company.size = e.get("size") or company.size
    company.country = e.get("country") or company.country
    company.website = company.website or e.get("website")
    company.linkedin_url = company.linkedin_url or e.get("linkedin_url")
    if e.get("evidence"):
        company.evidence = {**(company.evidence or {}), **e["evidence"]}


def _upsert_company(db: Session, tenant_id, parsed: dict) -> Company:
    """Find-or-create a company by `apollo_org_id` (else `domain`); update identity fields in place.

    Industry/size/country come from `organizations/enrich` (merged into `parsed` before this call
    for NEW rows only), so a non-null enrich value REFRESHES the stored one; a null never clobbers a
    real value. `apollo_org_id` is always (re)stamped and `evidence` is merged (new keys win).
    """
    org_id, domain = parsed.get("apollo_org_id"), parsed["domain"]
    company = None
    if org_id:
        company = db.execute(
            select(Company).where(
                Company.tenant_id == tenant_id, Company.apollo_org_id == org_id
            )
        ).scalar_one_or_none()
    if company is None:
        company = db.execute(
            select(Company).where(Company.tenant_id == tenant_id, Company.domain == domain)
        ).scalar_one_or_none()
    if company is None:
        company = Company(tenant_id=tenant_id, domain=domain, source="apollo")
        db.add(company)
    company.apollo_org_id = org_id or company.apollo_org_id
    company.name = parsed.get("name") or company.name or ""
    company.website = parsed.get("website") or company.website
    company.linkedin_url = parsed.get("linkedin_url") or company.linkedin_url
    company.industry = parsed.get("industry") or company.industry
    company.size = parsed.get("size") or company.size
    company.country = parsed.get("country") or company.country
    if parsed.get("evidence"):
        company.evidence = {**(company.evidence or {}), **parsed["evidence"]}
    if company.status not in ("selected", "people_found"):
        company.status = "discovered"
    return company


@router.post("/{client}/companies/find-company", response_model=FindResult)
def find_company(
    body: CompanyFindIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> FindResult:
    """Flow A — Apollo company search from the latest ResearchSpec → suppress → enrich → upsert.

    The search params are the v3 `company_search_params` + `intent_filters` (already Apollo-shaped);
    existing-customer domains and same-batch dupes are dropped before any row is stored. Survivors
    are upserted (a previously-known company is re-stamped with its `apollo_org_id`, not skipped).
    Capped at `MAX_COMPANIES_PER_FIND` per request. Records one `research_run` (source=apollo).

    Rows come back UNSCORED (`score=False`): fit-scoring a fresh batch is the slow step and would
    blow the 30s gateway cap, so the web app fires scoring in the background (chunked `/rescore`)
    and shows a per-row "Scoring…" status. The scoring spend is then booked under `rescore` runs.
    """
    spec = _latest_spec(db, ctx.tenant.id)
    if spec is None or not (spec.spec or {}).get("company_search_params"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "generate a research scope before finding companies"
        )
    credit = spec.spec.get("credit_policy") or {}
    hard_cap = min(MAX_COMPANIES_PER_FIND, credit.get("max_companies", 500))
    limit = max(1, min(body.limit, hard_cap))
    # Operator override (Settings modal) wins over the AI spec for *this call only*; an omitted
    # block falls back to the spec. `_clean` in apollo_map drops empty filters, so a cleared field
    # simply widens the search.
    csp = (
        body.company_search_params
        if body.company_search_params is not None
        else (spec.spec.get("company_search_params") or {})
    )
    intent = (
        body.intent_filters
        if body.intent_filters is not None
        else (spec.spec.get("intent_filters") or {})
    )
    filter_body = apollo_map.map_company_filter(csp, intent)
    icp = uuid.UUID(body.icp_id) if body.icp_id else None
    return _run_company_find(
        db,
        ctx.tenant.id,
        spec,
        filter_body=filter_body,
        limit=limit,
        icp=icp,
        source="apollo",
        score=False,
    )


def _run_company_find(
    db: Session,
    tenant_id,
    spec: ResearchSpec | None,
    *,
    filter_body: dict,
    limit: int,
    icp: uuid.UUID | None,
    source: str,
    seen_domains: set[str] | None = None,
    score: bool = True,
) -> FindResult:
    """The Flow-A tail shared by find-company and find-lookalikes: Apollo search → suppress + dedupe
    → enrich NEW survivors → upsert + concurrent fit-score → one `research_run`.

    `filter_body` is already Apollo-shaped (the caller builds it from the spec or from seed rows);
    `source` tags the run (`apollo` vs `lookalike`) so the cost scoreboard separates the two doors.
    `spec` may be None (lookalike needs no spec); its version/prompt stamp the run only when set.
    `seen_domains` are domains to DROP from the result (Lookalike passes the tenant's existing
    domains so the seeds + already-listed peers fall out and only NET-NEW companies come back; find
    passes None so an existing org is re-upserted/re-stamped instead). `score=False` upserts the new
    rows UNSCORED and returns immediately (Lookalike: fit-scoring a fresh batch is the slow part and
    would blow the 30s gateway cap, so the web app triggers it in the background via `/rescore` and
    shows a per-row "Scoring…" status). Latency of each stage is logged.
    """
    t0 = time.monotonic()
    try:
        rows = apollo.search_companies(filter_body, max_results=limit)
    except apollo.ApolloError as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"apollo company search failed: {e}"
        ) from e
    t_search = time.monotonic() - t0

    parsed = [apollo_map.parse_company(r) for r in rows]
    # Dedupe within this batch + drop `seen_domains`. find passes None → an org already in the
    # tenant is upserted (apollo_org_id re-stamped), not dropped. Lookalike passes the tenant
    # domains, so seeds + already-listed peers drop here and `found` reflects only new companies.
    survivors, dropped = find.filter_companies(
        parsed, _exclusions(db, tenant_id), seen_domains=seen_domains
    )
    # Enrich ONLY companies new to this tenant — an existing row would re-enrich to the same
    # firmographics and burn an Apollo credit. The 'Update Field' button refreshes existing rows.
    _enrich_survivors(_new_survivors(db, tenant_id, survivors))
    t_enrich = time.monotonic() - t0 - t_search

    run_id = _apollo_run_id()
    brief = _latest_brief(db, tenant_id)
    targeting = _build_targeting(brief, spec, icp_docs(db, tenant_id, icp))
    rubric = _latest_doc(db, tenant_id, COMPANY_STAGE)
    rubric_body = rubric.body if rubric else ""
    cost = 0.0
    companies: list[Company] = []
    for p in survivors:
        c = _upsert_company(db, tenant_id, p)
        c.run_id, c.icp_id = run_id, icp or c.icp_id
        companies.append(c)

    # Score the unscored rows concurrently (re-finds don't re-spend on already-scored rows). The
    # scoring payload is built here on the main thread so no lazy ORM load runs off-thread; results
    # are applied back here too. Sequential scoring of a full batch overruns the 30s gateway cap.
    t_pre_score = time.monotonic() - t0
    to_score = (
        [(c, _company_payload(c)) for c in companies if c.fit_score is None] if score else []
    )
    jobs = [
        (
            c,
            (
                lambda payload=payload: fit.score_company(
                    tenant_id=tenant_id,
                    rubric_body=rubric_body,
                    company=payload,
                    targeting=targeting,
                )
            ),
        )
        for c, payload in to_score
    ]
    for c, scored in _score_concurrently(jobs):
        if scored is not None:
            cost += _apply_company_score(c, scored)
    t_total = time.monotonic() - t0
    log.info(
        "company-find[%s]: apollo=%d search=%.1fs survivors=%d enrich=%.1fs scored=%d "
        "score=%.1fs total=%.1fs%s",
        source,
        len(rows),
        t_search,
        len(survivors),
        t_enrich,
        len(to_score),
        t_total - t_pre_score,
        t_total,
        " ⚠OVER-30s-GATEWAY-CAP" if t_total > 28 else "",
    )

    spec_blob = spec.spec if spec else {}
    db.add(
        ResearchRun(
            tenant_id=tenant_id,
            run_id=run_id,
            spec_version=spec.version if spec else None,
            icp_id=icp,
            source=source,
            prompt_version=(
                f"spec-v{spec_blob['spec_version']}" if spec_blob.get("spec_version") else None
            ),
            rubric_version=fit.RUBRIC_VERSION,
            rows_pushed=len(companies),
            cost_usd=round(cost, 6),
        )
    )
    db.commit()
    for c in companies:
        db.refresh(c)
    companies.sort(key=lambda c: (c.fit_score is None, -(c.fit_score or 0)))
    return FindResult(
        run_id=run_id,
        found=len(companies),
        dropped=len(dropped),
        companies=[_company_out(c) for c in companies],
    )


@router.post("/{client}/companies/find-lookalikes", response_model=FindResult)
def find_lookalikes(
    body: CompanyLookalikeIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> FindResult:
    """Lookalike (C7) — find the next batch of peers of the selected stage-1 rows.

    Apollo has no native lookalike API, so the selected rows' firmographics are aggregated
    HoldSlot-side (`lookalike.build_lookalike_filter`) into a normal company-search filter, then run
    through the same Flow-A tail as find-company. The tenant's existing domains are passed as
    `seen_domains`, so the seeds + any already-listed peers drop out → the result is the genuinely
    NEW *next* batch (≤`LOOKALIKE_LIMIT`, often fewer). The run is tagged `source=lookalike`; the
    new rows themselves keep `source=apollo`.

    Rows come back UNSCORED (`score=False`): fit-scoring a batch of brand-new companies is the slow
    step and would exceed the 30s gateway cap, so the web app fires the scoring in the background
    (chunked `/rescore` calls) and shows a per-row "Scoring…" status until each lands.
    """
    if not body.company_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select companies first")
    ids = [uuid.UUID(i) for i in body.company_ids]
    seeds = (
        db.execute(select(Company).where(Company.tenant_id == ctx.tenant.id, Company.id.in_(ids)))
        .scalars()
        .all()
    )
    if not seeds:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no matching companies")

    csp = lookalike.build_lookalike_filter(
        [
            {"industry": c.industry, "size": c.size, "country": c.country, "evidence": c.evidence}
            for c in seeds
        ]
    )
    if not csp:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "the selected companies lack firmographics to find lookalikes — enrich them first",
        )
    filter_body = apollo_map.map_company_filter(csp, None)

    # icp: explicit override wins; else the seeds' common ICP (only when they all share one); else
    # null (fit scores against the ICP union, exactly as Flow A does for an unscoped find).
    if body.icp_id:
        icp = uuid.UUID(body.icp_id)
    else:
        seed_icps = {c.icp_id for c in seeds}
        icp = next(iter(seed_icps)) if len(seed_icps) == 1 else None

    # Drop every company already in this tenant (seeds included) so Lookalike returns net-new peers.
    seen_domains = set(
        db.execute(
            select(Company.domain).where(
                Company.tenant_id == ctx.tenant.id, Company.domain.is_not(None)
            )
        ).scalars()
    )
    spec = _latest_spec(db, ctx.tenant.id)
    return _run_company_find(
        db,
        ctx.tenant.id,
        spec,
        filter_body=filter_body,
        limit=LOOKALIKE_LIMIT,
        icp=icp,
        source="lookalike",
        seen_domains=seen_domains,
        score=False,
    )


@router.patch("/{client}/companies/select", response_model=list[CompanyOut])
def select_companies(
    body: CompanySelectIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> list[CompanyOut]:
    """Stage stage-1 companies into Step 2 (`discovered` → `selected`) or remove them (`selected` or
    `people_found` → `discovered`).

    `selected=True` only promotes `discovered` rows (an already-searched `people_found` row is left
    as-is). `selected=False` is the Step-2 "Remove" — it un-stages a `selected` row OR an already
    searched `people_found` row back to the stage-1 pool, so an Accepted company can be taken out
    of Step 2. Re-searching is by explicit id (find-people), so demoting never blocks a later find.
    """
    if not body.ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no company ids")
    ids = [uuid.UUID(i) for i in body.ids]
    rows = (
        db.execute(
            select(Company).where(Company.tenant_id == ctx.tenant.id, Company.id.in_(ids))
        )
        .scalars()
        .all()
    )
    for c in rows:
        if body.selected and c.status == "discovered":
            c.status = "selected"
        elif not body.selected and c.status in ("selected", "people_found"):
            c.status = "discovered"
    db.commit()
    for c in rows:
        db.refresh(c)
    return [_company_out(c) for c in rows]


def _company_fit_prompt(db: Session, tenant_id, sample_id: str | None) -> FitPromptOut:
    """Stage-1 preview — `fit.build_company_messages` with the REAL targeting context (brief +
    research spec + the sample row's ICP docs). `sample_id` picks the company; omitted → newest."""
    company = None
    if sample_id:
        try:
            cid = uuid.UUID(sample_id)
        except ValueError:
            cid = None
        if cid is not None:
            company = db.execute(
                select(Company).where(Company.tenant_id == tenant_id, Company.id == cid)
            ).scalar_one_or_none()
    if company is None:
        company = (
            db.execute(
                select(Company)
                .where(Company.tenant_id == tenant_id)
                .order_by(Company.created_at.desc().nullslast())
            )
            .scalars()
            .first()
        )
    brief, spec = _latest_brief(db, tenant_id), _latest_spec(db, tenant_id)
    rubric = _latest_doc(db, tenant_id, COMPANY_STAGE)
    rubric_body = rubric.body if rubric else ""
    icp_id = company.icp_id if company else None
    targeting = _build_targeting(brief, spec, icp_docs(db, tenant_id, icp_id))
    payload = _company_payload(company) if company else {}
    msgs = fit.build_company_messages(rubric_body, payload, targeting)
    by_role = {m["role"]: m["content"] for m in msgs}
    return FitPromptOut(
        system=by_role.get("system", ""),
        user=by_role.get("user", ""),
        company=(company.name or company.domain) if company else None,
        model=list(fit.FIT_MODELS),
        purpose=fit.COMPANY_PURPOSE,
        prompt_version=f"v{rubric.version}" if rubric else "—",
    )


def _prospect_fit_prompt(db: Session, tenant_id, sample_id: str | None) -> FitPromptOut:
    """Stage-2 preview — `fit.build_messages` with a sample prospect's payload (decision-maker
    signals + parent-company fit) and the same targeting context. `sample_id` picks the prospect;
    omitted → newest. Mirrors live scoring, so the modal shows exactly what reaches the model."""
    prospect = None
    if sample_id:
        try:
            pid = uuid.UUID(sample_id)
        except ValueError:
            pid = None
        if pid is not None:
            prospect = db.execute(
                select(Prospect).where(Prospect.tenant_id == tenant_id, Prospect.id == pid)
            ).scalar_one_or_none()
    if prospect is None:
        prospect = (
            db.execute(
                select(Prospect)
                .where(Prospect.tenant_id == tenant_id)
                .order_by(Prospect.created_at.desc().nullslast())
            )
            .scalars()
            .first()
        )
    company = None
    if prospect and prospect.company_id:
        company = db.execute(
            select(Company).where(
                Company.tenant_id == tenant_id, Company.id == prospect.company_id
            )
        ).scalar_one_or_none()
    brief, spec = _latest_brief(db, tenant_id), _latest_spec(db, tenant_id)
    rubric = _latest_doc(db, tenant_id, PROSPECT_STAGE)
    rubric_body = rubric.body if rubric else ""
    icp_id = prospect.icp_id if prospect else None
    targeting = _build_targeting(brief, spec, icp_docs(db, tenant_id, icp_id))
    payload = _prospect_payload(prospect.enrichment, company) if prospect else {}
    by_role = {m["role"]: m["content"] for m in fit.build_messages(rubric_body, payload, targeting)}
    sample = (prospect.enrichment or {}).get("full_name") or (
        (prospect.enrichment or {}).get("company") if prospect else None
    )
    return FitPromptOut(
        system=by_role.get("system", ""),
        user=by_role.get("user", ""),
        company=sample or None,
        model=list(fit.FIT_MODELS),
        purpose=fit.PURPOSE,
        prompt_version=f"v{rubric.version}" if rubric else "—",
    )


@router.get("/{client}/fit-prompt", response_model=FitPromptOut)
def preview_fit_prompt(
    stage: str = COMPANY_STAGE,
    sample_id: str | None = None,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> FitPromptOut:
    """The exact system + input prompt a fit-score call would send — no LLM call, no spend.

    `stage=company_fit` (default) previews Step-1 company scoring; `stage=prospect_fit` previews
    Step-2 people scoring. Each is built from the SAME function the live scorer uses, with the real
    targeting context from the DB, so the Fit-rubric modal mirrors what reaches the model.
    `sample_id` picks the sample row (company id or prospect id for the respective stage)."""
    if stage == PROSPECT_STAGE:
        return _prospect_fit_prompt(db, ctx.tenant.id, sample_id)
    if stage != COMPANY_STAGE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown stage {stage!r}")
    return _company_fit_prompt(db, ctx.tenant.id, sample_id)


@router.post("/{client}/companies/rescore", response_model=list[CompanyOut])
def rescore_companies(
    body: CompanyRescoreIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> list[CompanyOut]:
    """Re-run company fit scoring for an explicit set of already-sourced companies (the Step-1
    selection), ignoring the `fit_score is None` gate that find-company uses. Run this after the
    rubric or the scoring prompt changes so existing rows reflect the new scoring.

    Bounded by `MAX_COMPANIES_PER_FIND` (the 30s API-Gateway sync cap) — a larger selection is
    rejected, not silently truncated, so the caller never thinks rows were re-scored when they
    weren't. Each row is scored against ITS OWN ICP context (targeting is memoized per icp_id, so
    a mixed selection is scored correctly). Records one `research_run` (source=rescore) for cost.
    """
    if not body.ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no company ids")
    if len(body.ids) > MAX_COMPANIES_PER_FIND:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"re-score at most {MAX_COMPANIES_PER_FIND} companies per request",
        )
    ids = [uuid.UUID(i) for i in body.ids]
    rows = (
        db.execute(select(Company).where(Company.tenant_id == ctx.tenant.id, Company.id.in_(ids)))
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no matching companies")

    brief, spec = _latest_brief(db, ctx.tenant.id), _latest_spec(db, ctx.tenant.id)
    rubric = _latest_doc(db, ctx.tenant.id, COMPANY_STAGE)
    rubric_body = rubric.body if rubric else ""
    # ICP docs differ per row, so build targeting once per distinct icp_id on the main thread (the
    # off-thread jobs must close over plain data, never the session). Mirrors find/add scoring.
    targeting_cache: dict[str | None, dict] = {}

    def _targeting_for(icp_id) -> dict:
        key = str(icp_id) if icp_id else None
        if key not in targeting_cache:
            targeting_cache[key] = _build_targeting(
                brief, spec, icp_docs(db, ctx.tenant.id, icp_id)
            )
        return targeting_cache[key]

    jobs = [
        (
            c,
            (
                lambda payload=_company_payload(c), targeting=_targeting_for(c.icp_id): (
                    fit.score_company(
                        tenant_id=ctx.tenant.id,
                        rubric_body=rubric_body,
                        company=payload,
                        targeting=targeting,
                    )
                )
            ),
        )
        for c in rows
    ]
    cost = 0.0
    for c, scored in _score_concurrently(jobs):
        if scored is not None:
            cost += _apply_company_score(c, scored)

    db.add(
        ResearchRun(
            tenant_id=ctx.tenant.id,
            run_id=_apollo_run_id(),
            spec_version=spec.version if spec else None,
            source="rescore",
            rubric_version=fit.RUBRIC_VERSION,
            rows_pushed=len(rows),
            cost_usd=round(cost, 6),
        )
    )
    db.commit()
    for c in rows:
        db.refresh(c)
    rows.sort(key=lambda c: (c.fit_score is None, -(c.fit_score or 0)))
    return [_company_out(c) for c in rows]


@router.post("/{client}/companies/update-fields", response_model=list[CompanyOut])
def update_company_fields(
    body: CompanyEnrichIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> list[CompanyOut]:
    """'Update Field' — re-enrich Apollo firmographics for an explicit set of selected companies
    (industry/size/country + the evidence study fields). This is the deliberate, on-demand credit
    spend; find-company only enriches NEW rows so an existing org is never re-enriched for free.

    One `organizations/enrich` call per distinct domain (concurrent). Bounded by
    `MAX_COMPANIES_PER_FIND` (the 30s sync cap) — a larger selection is rejected, not truncated.
    """
    if not body.ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no company ids")
    if len(body.ids) > MAX_COMPANIES_PER_FIND:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"update at most {MAX_COMPANIES_PER_FIND} companies per request",
        )
    ids = [uuid.UUID(i) for i in body.ids]
    rows = (
        db.execute(select(Company).where(Company.tenant_id == ctx.tenant.id, Company.id.in_(ids)))
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no matching companies")

    domains = [c.domain for c in rows if c.domain]
    try:
        enriched = apollo.enrich_organizations(domains)
    except apollo.ApolloError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"apollo enrich failed: {e}") from e
    by_domain = {
        p["domain"]: p for o in enriched if (p := apollo_map.parse_enrich(o)).get("domain")
    }
    for c in rows:
        e = by_domain.get(c.domain)
        if e:
            _apply_enrichment(c, e)
    db.add(
        ResearchRun(
            tenant_id=ctx.tenant.id,
            run_id=_apollo_run_id(),
            source="enrich",
            rows_pushed=len(rows),
            cost_usd=0.0,
        )
    )
    db.commit()
    for c in rows:
        db.refresh(c)
    rows.sort(key=lambda c: (c.fit_score is None, -(c.fit_score or 0)))
    return [_company_out(c) for c in rows]


# ----------------------------------------------------------------- research-run scoreboard


@router.get("/{client}/research-runs", response_model=list[ResearchRunOut])
def list_research_runs(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[ResearchRunOut]:
    rows = db.execute(
        select(ResearchRun)
        .where(ResearchRun.tenant_id == ctx.tenant.id)
        .order_by(ResearchRun.created_at.desc())
    ).scalars()
    out = []
    for r in rows:
        cost = float(r.cost_usd) if r.cost_usd is not None else None
        per = round(cost / r.rows_accepted, 6) if cost and r.rows_accepted else None
        out.append(
            ResearchRunOut(
                run_id=r.run_id,
                source=r.source,
                prompt_version=r.prompt_version,
                rubric_version=r.rubric_version,
                rows_pushed=r.rows_pushed,
                rows_accepted=r.rows_accepted,
                cost_usd=cost,
                cost_per_accepted=per,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
        )
    return out


# ----------------------------------------------------------------- sourcing docs (fit rubric)


def _doc_out(d: Prompt | None) -> SourcingDocOut | None:
    if d is None:
        return None
    return SourcingDocOut(
        stage=d.stage,
        version=d.version,
        body=d.body,
        created_at=d.created_at.isoformat() if d.created_at else None,
    )


@router.get("/{client}/sourcing-docs", response_model=SourcingDocList)
def get_sourcing_docs(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> SourcingDocList:
    """The two editable fit rubrics: `company_fit` (Step 1) and `prospect_fit` (Step 2)."""
    return SourcingDocList(
        company_fit=_doc_out(_latest_doc(db, ctx.tenant.id, COMPANY_STAGE)),
        prospect_fit=_doc_out(_latest_doc(db, ctx.tenant.id, PROSPECT_STAGE)),
    )


@router.post("/{client}/sourcing-docs", response_model=SourcingDocOut, status_code=201)
def save_sourcing_doc(
    body: SourcingDocIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> SourcingDocOut:
    """Append-only — save the founder's fit-rubric edit as the next version."""
    if body.stage not in _VALID_STAGES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown prompt stage")
    latest = _latest_doc(db, ctx.tenant.id, body.stage)
    doc = Prompt(
        tenant_id=ctx.tenant.id,
        stage=body.stage,
        version=(latest.version + 1) if latest else 1,
        body=body.body,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_out(doc)


# ------------------------------------------------------- Stage 2: people (manual add + enrich gate)


@router.post("/{client}/prospects", response_model=ProspectOut, status_code=201)
def add_prospect(
    body: ProspectManualIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ProspectOut:
    """Stage-2 manual add — one person, `source=manual`, same suppression + scoring as sourced
    rows. `company_id` is resolved by domain; upserts on (tenant, identity_key)."""
    cand = Candidate(
        full_name=body.full_name,
        company=body.company,
        domain=body.domain,
        linkedin_url=body.linkedin_url,
        email=body.email,
        company_industry=body.company_industry,
        target_titles=body.title,
        target_seniority=body.seniority,
    )
    key = cand.identity_key
    if not key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "need a LinkedIn URL, company domain + name, or email"
        )
    exclusions = _exclusions(db, ctx.tenant.id)
    if reason := exclusions.blocks(cand):
        raise HTTPException(status.HTTP_409_CONFLICT, f"person is excluded ({reason})")

    icp = uuid.UUID(body.icp_id) if body.icp_id else None
    brief, spec = _latest_brief(db, ctx.tenant.id), _latest_spec(db, ctx.tenant.id)
    targeting = _build_targeting(brief, spec, icp_docs(db, ctx.tenant.id, icp))
    rubric = _latest_doc(db, ctx.tenant.id, PROSPECT_STAGE)
    rubric_body = rubric.body if rubric else ""

    domain = normalize_domain(body.domain)
    enrichment = {
        "full_name": body.full_name,
        "company": body.company,
        "domain": domain,
        "company_domain": domain,
        "linkedin_url": body.linkedin_url,
        "email": normalize_email(body.email),
        "title": body.title,
        "seniority": body.seniority,
        "company_size": body.company_size,
        "company_industry": body.company_industry,
    }
    prospect = db.execute(
        select(Prospect).where(Prospect.tenant_id == ctx.tenant.id, Prospect.identity_key == key)
    ).scalar_one_or_none()
    if prospect is None:
        prospect = Prospect(tenant_id=ctx.tenant.id, identity_key=key, source="manual")
        db.add(prospect)
    prospect.source = "manual"  # a manual add is authoritative for provenance, even on re-add
    prospect.enrichment = enrichment
    prospect.email_valid = False
    prospect.last_enriched_at = func.now()
    if icp:
        prospect.icp_id = icp
    comp = db.execute(
        select(Company).where(Company.tenant_id == ctx.tenant.id, Company.domain == domain)
    ).scalar_one_or_none()
    if comp is not None:
        prospect.company_id = comp.id
        if comp.status in ("discovered", "selected"):
            comp.status = "people_found"
    try:
        scored_row = fit.score(
            tenant_id=ctx.tenant.id,
            rubric_body=rubric_body,
            enrichment=_prospect_payload(enrichment, comp),
            targeting=targeting,
        )
    except LlmError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"scoring failed: {e}") from e
    prospect.fit_score = scored_row["fit_score"]
    prospect.fit_tier = scored_row["fit_tier"]
    prospect.fit_components = scored_row["fit_components"]
    prospect.status = "scored" if enrichment["email"] else "found"
    db.commit()
    db.refresh(prospect)
    return _prospect_out(prospect)


# --------------------------------------------------------------- Stage 2: Apollo Flow B (find)

# Auto-relax order: Apollo AND's the two persona facets, so a strict Management-Level ∩ Department
# combo can be empty at a small org even when each facet alone has people (the Luma case). When the
# strict combo returns 0 we widen by dropping ONE facet — department-only, then seniority-only — but
# never all the way to org-only (that would dump interns/irrelevant roles, defeating "suitable").
def _search_people_relaxed(
    people_params: dict, org_id: str, per_company: int
) -> tuple[list[dict], dict, str]:
    """Search one org, widening the persona facets until people appear. → (rows, body_sent, level).

    `level` is a short tag for diagnostics: "strict" (both facets), "dept_only" / "seniority_only"
    (one facet dropped), or "as_is" (the spec had ≤1 facet, so nothing to relax)."""
    sen = people_params.get("person_seniorities") or []
    dep = people_params.get("person_department_or_subdepartments") or []
    if sen and dep:
        attempts = [
            (people_params, "strict"),
            ({**people_params, "person_seniorities": []}, "dept_only"),
            ({**people_params, "person_department_or_subdepartments": []}, "seniority_only"),
        ]
    else:
        attempts = [(people_params, "as_is")]
    last_body: dict = {}
    for params, level in attempts:
        last_body = apollo_map.map_people_filter(params, org_id=org_id)
        rows = apollo.search_people(last_body, max_results=per_company)
        if rows:
            return rows, last_body, level
    return [], last_body, attempts[-1][1]


@router.post("/{client}/people/find-people", response_model=FindResult)
def find_people(
    body: PeopleFindIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> FindResult:
    """Flow B — find people across the SELECTED companies (one api_search per org), 0 credits.

    C0: search rows carry no `organization_id`, so we loop the selected orgs and pass one
    `organization_ids` per call — each person's `company_id` is known from the loop. Rows land
    `found` (no email yet), are fit-scored on what's known, and dedupe on `apollo_person_id`.
    Enrichment (the credit spend) is a separate, human-gated step (`/prospects/enrich`).

    No per-company people cap: each org contributes everyone matching the Find Settings (up to
    Apollo's 100/call). Bounded per request only by `MAX_ORGS_PER_FIND` orgs and
    `MAX_PEOPLE_PER_FIND_RUN` total people (find is free + unscored, an I/O bound, not the LLM one).
    Every org
    actually searched advances to `people_found`; the operator re-runs to drain a large selection.
    """
    spec = _latest_spec(db, ctx.tenant.id)
    if spec is None or not (spec.spec or {}).get("people_search_params"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "generate a research scope before finding people"
        )
    if not body.company_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select companies first")
    # Driven by the explicit Step-2 selection (not a "selected" status): only rows with an Apollo
    # org id can be searched, best fit first, bounded by the 30s cap. Re-searching an already
    # people_found row is allowed — Apollo search is free and the seen-id dedupe drops repeats.
    ids = [uuid.UUID(i) for i in body.company_ids]
    selected = (
        db.execute(
            select(Company)
            .where(
                Company.tenant_id == ctx.tenant.id,
                Company.id.in_(ids),
                Company.apollo_org_id.is_not(None),
            )
            .order_by(Company.fit_score.desc().nullslast())
            .limit(MAX_ORGS_PER_FIND)
        )
        .scalars()
        .all()
    )
    if not selected:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "the selected companies have no Apollo id to search"
        )

    # Precedence: a per-call override in the request → the tenant's saved Find-Settings override
    # (persisted server-side, survives across browsers) → the AI spec. `_clean` in apollo_map drops
    # empty filters, so a cleared field widens the search. `organization_ids` is never taken from
    # here: the per-org loop sets it (C0: search rows carry no org id).
    if body.people_search_params is not None:
        people_params = body.people_search_params
    else:
        saved = _people_scope_override(db, ctx.tenant.id)
        saved_params = (saved.params or {}).get("people_search_params") if saved else None
        people_params = (
            saved_params
            if saved_params is not None
            else (spec.spec.get("people_search_params") or {})
        )
    per_company = max(1, min(body.per_company, apollo.PER_PAGE_MAX))
    seen_ids = set(
        db.execute(
            select(Prospect.apollo_person_id).where(
                Prospect.tenant_id == ctx.tenant.id, Prospect.apollo_person_id.is_not(None)
            )
        ).scalars()
    )
    run_id, icp = _apollo_run_id(), (uuid.UUID(body.icp_id) if body.icp_id else None)
    docs = icp_docs(db, ctx.tenant.id, icp)
    # avoidTitles → hard pre-score drop (Apollo people search has no exclude-title field). Keyed per
    # ICP so a title avoided in one profile is not dropped from another when the run spans ICPs.
    avoid_by_icp = {d["id"]: [t for t in (d.get("avoidTitles") or []) if t] for d in docs}
    new_rows: list[tuple[dict, Company]] = []
    dropped_total = 0
    for comp in selected:
        if len(new_rows) >= MAX_PEOPLE_PER_FIND_RUN:
            continue  # batch full — leave this org as-is (still "Pending") for the next run
        try:
            rows, pbody, relax = _search_people_relaxed(
                people_params, comp.apollo_org_id, per_company
            )
        except apollo.ApolloError as e:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"apollo people search failed: {e}"
            ) from e
        # Searched (even on 0 results). Re-searchable: find is by explicit id, so a later run with
        # looser filters can search this org again; the seen-id dedupe drops repeats.
        comp.status = "people_found"
        parsed = [apollo_map.parse_person(r) for r in rows]
        applicable = str(icp) if icp else (str(comp.icp_id) if comp.icp_id else None)
        survivors, dropped = find.filter_people(
            parsed, seen_ids, avoid_titles=avoid_by_icp.get(applicable, [])
        )
        dropped_total += len(dropped)
        # Per-org diagnostics — makes a 0-result explainable (Apollo returned nothing for the org
        # vs. everything filtered out). `filters` = people params actually sent (org_id excluded).
        log.info(
            "people-find[%s]: org=%s relax=%s raw=%d survivors=%d dropped=%d filters=%s",
            comp.domain,
            comp.apollo_org_id,
            relax,
            len(rows),
            len(survivors),
            len(dropped),
            {k: v for k, v in pbody.items() if k != "organization_ids"},
        )
        for p in survivors:
            if len(new_rows) >= MAX_PEOPLE_PER_FIND_RUN:
                break
            seen_ids.add(p["apollo_person_id"])
            new_rows.append((p, comp))

    prospects: list[Prospect] = []
    for p, comp in new_rows:
        key = f"apollo:{p['apollo_person_id']}"
        prospect = db.execute(
            select(Prospect).where(
                Prospect.tenant_id == ctx.tenant.id, Prospect.identity_key == key
            )
        ).scalar_one_or_none()
        if prospect is None:
            prospect = Prospect(tenant_id=ctx.tenant.id, identity_key=key, source="apollo")
            db.add(prospect)
        enrichment = {
            "full_name": p.get("first_name", ""),
            "company": p.get("company") or comp.name,
            "domain": comp.domain,
            "company_domain": comp.domain,
            "linkedin_url": "",
            "email": "",
            "title": p.get("title", ""),
            "company_industry": comp.industry or "",
        }
        prospect.apollo_person_id = p["apollo_person_id"]
        prospect.company_id = comp.id
        prospect.icp_id = icp or comp.icp_id
        prospect.run_id = run_id
        prospect.spec_version = spec.version
        prospect.enrichment = enrichment
        prospect.email_valid = False
        prospect.source_lineage = {"apollo_org_id": comp.apollo_org_id, "run_id": run_id}
        # Land UNSCORED ("Pending") — find never blocks on the LLM; the operator scores on demand
        # via the Step-2 'Get AI score' button (`/prospects/rescore`). Mirrors the Step-1 find.
        prospect.status = "found"
        prospects.append(prospect)

    # Find is free and unscored, so cost is 0 — the scoring spend is booked under the rescore run.
    db.add(
        ResearchRun(
            tenant_id=ctx.tenant.id,
            run_id=run_id,
            spec_version=spec.version,
            icp_id=icp,
            source="apollo",
            rubric_version=fit.RUBRIC_VERSION,
            rows_pushed=len(prospects),
            cost_usd=0.0,
        )
    )
    db.commit()
    for p in prospects:
        db.refresh(p)
    prospects.sort(key=lambda p: (p.fit_score is None, -(p.fit_score or 0)))
    return FindResult(
        run_id=run_id,
        found=len(prospects),
        dropped=dropped_total,
        prospects=[_prospect_out(p) for p in prospects],
    )


# Display labels for the two facet sidebars (Apollo machine value → human text).
_SENIORITY_LABELS = {
    "c_suite": "C-Suite",
    "vp": "VP",
}


def _humanize(value: str) -> str:
    """Apollo machine value → label: drop a leading `master_`, underscores → spaces, Title-case."""
    text = value[len("master_") :] if value.startswith("master_") else value
    return text.replace("_", " ").title()


def _facet_label(value: str) -> str:
    return _SENIORITY_LABELS.get(value) or ("C-Suite" if value == "c_suite" else _humanize(value))


@router.post("/{client}/people/facets", response_model=PeopleFacetsOut)
def people_facets(
    body: PeopleFacetsIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> PeopleFacetsOut:
    """Live Find-Settings facet sidebar — per Management-Level / Department people counts across the
    selected Step-2 companies (free; Apollo people search costs no credits). One probe per facet
    value, scoped to the union of selected orgs, run concurrently to stay under the 30s sync cap.
    Only the 14 master departments are probed (not the ~245 subs) so the call is a fixed 11 + 14 + 1
    searches regardless of how many companies are selected."""
    if not body.company_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select companies first")
    ids = [uuid.UUID(i) for i in body.company_ids]
    org_ids = list(
        db.execute(
            select(Company.apollo_org_id).where(
                Company.tenant_id == ctx.tenant.id,
                Company.id.in_(ids),
                Company.apollo_org_id.is_not(None),
            )
        ).scalars()
    )
    if not org_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "the selected companies have no Apollo id to search"
        )
    base = {"organization_ids": org_ids}
    # (kind, value, extra-filter) — one free count_people probe each, fanned out concurrently.
    probes: list[tuple[str, str, dict]] = [
        ("total", "", {}),
        *[("sen", s, {"person_seniorities": [s]}) for s in SENIORITY_ENUM],
        *[("dep", d, {"person_department_or_subdepartments": [d]}) for d in MASTER_DEPARTMENTS],
    ]
    try:
        with ThreadPoolExecutor(max_workers=min(12, len(probes))) as ex:
            counts = list(ex.map(lambda p: apollo.count_people({**base, **p[2]}), probes))
    except apollo.ApolloError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"apollo facet probe failed: {e}") from e
    by_key = {(p[0], p[1]): c for p, c in zip(probes, counts, strict=True)}
    return PeopleFacetsOut(
        total=by_key[("total", "")],
        seniorities=[
            FacetCount(value=s, label=_facet_label(s), count=by_key[("sen", s)])
            for s in SENIORITY_ENUM
        ],
        departments=[
            DepartmentFacet(
                value=d,
                label=_facet_label(d),
                count=by_key[("dep", d)],
                subs=[
                    FacetOption(value=s, label=_humanize(s)) for s in DEPARTMENT_TAXONOMY[d]
                ],
            )
            for d in MASTER_DEPARTMENTS
        ],
    )


@router.get("/{client}/people/scope-override", response_model=PeopleScopeOverrideOut)
def get_people_scope_override(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> PeopleScopeOverrideOut:
    """The tenant's saved Step-2 Find Settings (people facets), or null params when none is saved
    (→ the Workspace shows the AI scope). Persisted server-side so it follows the operator across
    browsers/devices."""
    row = _people_scope_override(db, ctx.tenant.id)
    params = (row.params or {}).get("people_search_params") if row else None
    return PeopleScopeOverrideOut(people_search_params=params)


@router.put("/{client}/people/scope-override", response_model=PeopleScopeOverrideOut)
def save_people_scope_override(
    body: PeopleScopeOverrideIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> PeopleScopeOverrideOut:
    """Save the Step-2 Find Settings as the tenant's people-scope override. It then wins over the AI
    spec on every Find People until reset.

    An EMPTY payload (no seniority/department chosen) is a revert, not a save: it deletes any saved
    row so the next Find People falls back to the AI scope — same as the 'Reset to AI scope' button.
    Persisting an all-empty override would otherwise silently widen every search to the whole org.
    A non-empty payload is UPSERTed atomically (ON CONFLICT) so concurrent saves can't race the
    unique (tenant, kind) constraint into a 500."""
    psp = body.people_search_params or {}
    if not any(psp.values()):
        row = _people_scope_override(db, ctx.tenant.id)
        if row is not None:
            db.delete(row)
            db.commit()
        return PeopleScopeOverrideOut(people_search_params=None)
    payload = {"people_search_params": body.people_search_params}
    stmt = (
        pg_insert(ScopeOverride)
        .values(tenant_id=ctx.tenant.id, kind=SCOPE_KIND_PEOPLE, params=payload)
        .on_conflict_do_update(
            constraint="uq_scope_override_tenant_kind",
            set_={"params": payload, "updated_at": func.now()},
        )
    )
    db.execute(stmt)
    db.commit()
    return PeopleScopeOverrideOut(people_search_params=body.people_search_params)


@router.get("/{client}/people/departments", response_model=list[FacetOption])
def people_departments(
    ctx: AccessContext = Depends(require_membership()),
) -> list[FacetOption]:
    """The 14 master Department & Job Function options (value + label) — the single source of truth
    for the Find-Settings department list before live counts load. Static (Apollo's taxonomy), no
    Apollo call, no spend; the frontend renders these so it never hardcodes the master list."""
    return [FacetOption(value=d, label=_facet_label(d)) for d in MASTER_DEPARTMENTS]


@router.delete("/{client}/people/scope-override", status_code=status.HTTP_204_NO_CONTENT)
def reset_people_scope_override(
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> None:
    """Discard the saved Step-2 override → Find People reverts to the AI scope. Idempotent: a no-op
    when nothing is saved."""
    row = _people_scope_override(db, ctx.tenant.id)
    if row is not None:
        db.delete(row)
        db.commit()


@router.post("/{client}/prospects/rescore", response_model=list[ProspectOut])
def rescore_prospects(
    body: ProspectRescoreIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> list[ProspectOut]:
    """Step-2 'Get AI score' — re-run people fit scoring for an explicit set of prospects (by
    identity key), against the current rubric. Mirrors `rescore_companies`: people land unscored
    from find, so this is how a person gets a fit tier; re-running after a rubric change re-scores.

    Bounded by `MAX_PEOPLE_PER_FIND` (the 30s sync cap) — a larger selection is rejected, not
    truncated. Each row scores against ITS OWN ICP context (targeting memoized per icp_id). Records
    one `research_run` (source=rescore) for cost.
    """
    if not body.identity_keys:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no identity_keys")
    if len(body.identity_keys) > MAX_PEOPLE_PER_FIND:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"re-score at most {MAX_PEOPLE_PER_FIND} people per request",
        )
    rows = (
        db.execute(
            select(Prospect).where(
                Prospect.tenant_id == ctx.tenant.id,
                Prospect.identity_key.in_(body.identity_keys),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no matching prospects")

    brief, spec = _latest_brief(db, ctx.tenant.id), _latest_spec(db, ctx.tenant.id)
    rubric = _latest_doc(db, ctx.tenant.id, PROSPECT_STAGE)
    rubric_body = rubric.body if rubric else ""
    # Parent companies, loaded once, so each person is scored with its account's firmographics + the
    # stage-1 fit verdict (decision-maker INSIDE an already-qualified company).
    company_ids = {p.company_id for p in rows if p.company_id}
    companies = (
        {
            c.id: c
            for c in db.execute(
                select(Company).where(
                    Company.tenant_id == ctx.tenant.id, Company.id.in_(company_ids)
                )
            ).scalars()
        }
        if company_ids
        else {}
    )
    targeting_cache: dict[str | None, dict] = {}

    def _targeting_for(icp_id) -> dict:
        key = str(icp_id) if icp_id else None
        if key not in targeting_cache:
            targeting_cache[key] = _build_targeting(
                brief, spec, icp_docs(db, ctx.tenant.id, icp_id)
            )
        return targeting_cache[key]

    jobs = [
        (
            p,
            (
                lambda payload=_prospect_payload(p.enrichment, companies.get(p.company_id)),
                targeting=_targeting_for(p.icp_id): fit.score(
                    tenant_id=ctx.tenant.id,
                    rubric_body=rubric_body,
                    enrichment=payload,
                    targeting=targeting,
                )
            ),
        )
        for p in rows
    ]
    cost = 0.0
    for p, scored in _score_concurrently(jobs):
        if scored is not None:
            p.fit_score = scored["fit_score"]
            p.fit_tier = scored["fit_tier"]
            p.fit_components = scored["fit_components"]
            cost += float(scored.get("cost_usd") or 0.0)

    db.add(
        ResearchRun(
            tenant_id=ctx.tenant.id,
            run_id=_apollo_run_id(),
            spec_version=spec.version if spec else None,
            source="rescore",
            rubric_version=fit.RUBRIC_VERSION,
            rows_pushed=len(rows),
            cost_usd=round(cost, 6),
        )
    )
    db.commit()
    for p in rows:
        db.refresh(p)
    rows.sort(key=lambda p: (p.fit_score is None, -(p.fit_score or 0)))
    return [_prospect_out(p) for p in rows]


@router.post("/{client}/prospects/enrich", response_model=EnrichResult)
def confirm_enrich(
    body: EnrichIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> EnrichResult:
    """The enrich gate (C5) — Apollo `people/match` on the confirmed rows. The only credit spend.

    Human-gated and **idempotent**: each Apollo-sourced row that isn't already enriched spends 1
    credit to reveal a verified email (phone off at MVP), is written back with email / last name /
    linkedin / departments, and moves to `scored`. Rows already enriched (email on file) or with no
    `apollo_person_id` (manual) are confirmed without a match call, so a re-submit never re-spends.

    Each row is committed independently, so a mid-batch Apollo failure can't roll back — and lose
    the DB record of — credits already charged for earlier rows.
    """
    if not body.identity_keys:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no identity_keys")
    rows = (
        db.execute(
            select(Prospect).where(
                Prospect.tenant_id == ctx.tenant.id,
                Prospect.identity_key.in_(body.identity_keys),
                Prospect.status.in_(("found", "scored", "confirmed", "enrich_failed")),
            )
        )
        .scalars()
        .all()
    )
    enriched = credits = 0
    for p in rows:
        already_enriched = bool(p.email_valid or (p.enrichment or {}).get("email"))
        if not p.apollo_person_id or already_enriched:
            # Manual row (nothing to match) or already enriched — confirm without spending.
            if p.status == "found":
                p.status = "confirmed"
            db.commit()  # persist this row before moving on
            continue
        try:
            person = apollo.match_person(p.apollo_person_id, reveal_email=True, reveal_phone=False)
        except apollo.ApolloError as e:
            # Earlier rows are already committed; surface the failure without losing their spend.
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"apollo enrich failed: {e}"
            ) from e
        matched = apollo_map.parse_match(person)
        if not matched.get("apollo_person_id"):
            p.status = "enrich_failed"  # Apollo had no match; distinct so it won't sit as "pending"
            db.commit()
            continue
        credits += 1  # one reveal_personal_emails credit
        e = dict(p.enrichment or {})
        e.update(
            full_name=matched.get("full_name") or e.get("full_name", ""),
            email=matched.get("email", ""),
            linkedin_url=matched.get("linkedin_url", ""),
            departments=matched.get("departments", []),
        )
        p.enrichment = e
        p.email_valid = bool(matched.get("email_valid"))
        p.last_enriched_at = func.now()
        p.status = "scored"
        enriched += 1
        db.commit()  # durable per row — bounds any Apollo spend to committed work
    return EnrichResult(confirmed=len(rows), enriched=enriched, credits_spent=credits)
