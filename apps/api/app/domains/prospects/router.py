"""Prospect routes — the Apollo find → score → enrich surface (Phase C, live).

One suppression gate and one scoring door (`fit.py`). Tenant scope × role is enforced by the A4
central guard, so every query is scoped to the caller's client. The heavy lifting lives in the
pure modules; this layer is orchestration + persistence.

The legacy seed/CSV-import/AI-sourcing loop was removed in the Apollo-only teardown. The two-stage
company→people loop is live: find-company / find-people return rows UNSCORED, fit scoring is an
explicit step (`/companies/rescore`, `/prospects/rescore`), and the async **Reveal & score** door
(`/prospects/enrich-score-async`) spends the Apollo `people/match` credit to reveal verified emails
(the only credit spend in this surface — the v1 sync `/prospects/enrich` twin was retired in D+.5).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.core.deps import AccessContext, get_db, require_membership, uuid_or_404
from app.core.pagination import DEFAULT_PAGE, MAX_PAGE, decode_cursor, encode_cursor
from app.domains.briefs.research_spec import (
    DEPARTMENT_TAXONOMY,
    MASTER_DEPARTMENTS,
    SENIORITY_ENUM,
    targeting_for_icp,
)
from app.domains.icps import icp_docs
from app.domains.prospects import (
    apollo_map,
    find,
    fit,
    scoring,
)
from app.domains.prospects.company_find import (  # noqa: F401  (endpoints + full re-export)
    _APAC_CITIES,
    _APAC_LOCATIONS,
    _COMPANY_SEARCH_CACHE,
    _CURSOR_FIND_SOURCES,
    _CURSOR_SCAN_LIMIT,
    _VOLATILE_SCOPE_KEYS,
    FIND_COMPANY_LIMIT,
    FIND_OVER_BROAD,
    FIND_RELAX_MIN,
    LOOKALIKE_LIMIT,
    _apply_enrichment,
    _body_hash,
    _company_fit_prompt,
    _company_relax_ladder,
    _cursor_decision,
    _enrich_survivors,
    _find_company_core,
    _is_apac,
    _lookalike_core,
    _new_survivors,
    _prospect_fit_prompt,
    _resolve_company_scope,
    _resume_page,
    _run_company_find,
    _upsert_company,
    _weakest_keyword,
    _widen_employee_ranges,
)
from app.domains.prospects.identity import normalize_domain, normalize_email
from app.domains.prospects.jobs import (  # noqa: F401  (endpoints + full re-export)
    ASYNC_BATCH_MAX,
    SCORING_HANDLERS,
    _scoring_job_out,
    _update_fields_core,
    run_enrich_score_prospects,
    run_find_company,
    run_find_lookalikes,
    run_rescore_companies,
    run_rescore_prospects,
    run_update_fields,
)
from app.domains.prospects.label_engine import (  # noqa: F401  (endpoints + full re-export)
    _SCORE_WORKERS,
    MAX_COMPANIES_PER_FIND,
    _apply_company_verdict,
    _apply_prospect_verdict,
    _company_det_inputs,
    _label_companies_deterministic,
    _prospect_v2_payload,
    _rules_config,
    _score_companies_v2,
    _score_concurrently,
    _score_prospects_v2,
    classify_companies,
)
from app.domains.prospects.people_find import (  # noqa: F401  (endpoints + full re-export)
    _ENRICH_WORKERS,
    _SENIORITY_LABELS,
    _enrich_prospects,
    _facet_label,
    _humanize,
    _people_ladder,
    _search_people_relaxed,
)
from app.domains.prospects.schemas import (
    CompanyEnrichIn,
    CompanyFindIn,
    CompanyLookalikeIn,
    CompanyManualIn,
    CompanyOut,
    CompanyPage,
    CompanyRescoreIn,
    CompanySelectIn,
    DepartmentFacet,
    FacetCount,
    FacetOption,
    FindResult,
    FitPromptOut,
    PeopleFacetsIn,
    PeopleFacetsOut,
    PeopleFindIn,
    ProspectManualIn,
    ProspectOut,
    ProspectPage,
    ProspectRescoreIn,
    ResearchRunOut,
    ScopeOverrideIn,
    ScopeOverrideOut,
    ScoringJobOut,
    SourcingDocIn,
    SourcingDocList,
    SourcingDocOut,
)
from app.domains.prospects.scope import (  # noqa: F401  (endpoints + full re-export)
    _SCOPE_GLOBAL,
    _SCORING_BRIEF_FIELDS,
    SCOPE_KIND_COMPANY,
    SCOPE_KIND_PEOPLE,
    _apollo_run_id,
    _build_exclusions,
    _build_targeting,
    _drop_conflicts,
    _exclusions,
    _feedback_rows,
    _has_scope_value,
    _latest_brief,
    _latest_doc,
    _latest_spec,
    _merge_scope_map,
    _merge_uids,
    _parse_ids,
    _require_scope_kind,
    _resolve_tech,
    _scope_override_block,
    _scope_override_row,
    _trim_brief_for_scoring,
    _trim_spec_for_scoring,
    _validate_icp_id,
    _write_scope_override,
)
from app.domains.prospects.serializers import (  # noqa: F401  (endpoints + full re-export)
    _classify_payload,
    _company_enrichment,
    _company_out,
    _company_payload,
    _doc_out,
    _prospect_out,
    _prospect_payload,
)
from app.domains.prospects.suppression import Candidate
from app.integrations.apollo import client as apollo
from app.models import (
    Company,
    MembershipRole,
    Prompt,
    Prospect,
    ResearchRun,
)

router = APIRouter(tags=["prospects"])

log = logging.getLogger("holdslot.prospects")

_PEOPLE_FACETS_CACHE = TTLCache(ttl_seconds=300)

# The two editable fit rubrics — one per scoring stage. `company_fit` (Step 1) grades buying intent;
# `prospect_fit` (Step 2) grades a person's reply potential + decision-making power. The stage names
# match the LLM purposes in `fit.py` (COMPANY_PURPOSE / PURPOSE) so doc ↔ scorer line up 1:1.
COMPANY_STAGE = "company_fit"

PROSPECT_STAGE = "prospect_fit"

_VALID_STAGES = (COMPANY_STAGE, PROSPECT_STAGE)

# Scoring v2 cutover: the "Fit rubric" modal keeps these FE-facing tokens (API compatibility), but
# they now read / preview / save the ACTIVE v2 score rubrics — so the modal shows and edits exactly
# what the live scorer uses (`company_score_v2` / `prospect_score_v2`), not the retired v1 rubric.
_RUBRIC_STAGE = {
    COMPANY_STAGE: fit.COMPANY_SCORE_STAGE,
    PROSPECT_STAGE: fit.PROSPECT_SCORE_STAGE,
}

MAX_ORGS_PER_FIND = 8  # selected orgs searched per find-people request (1 Apollo call each)

MAX_PEOPLE_PER_FIND_RUN = 250  # unscored people landed per find-people request (free, no LLM)

@router.get("/{client}/prospects", response_model=ProspectPage)
def list_prospects(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> ProspectPage:
    # `Prospect.id` is the deterministic tiebreaker: a whole find-run batch shares one created_at
    # (Postgres now() is fixed per transaction), so without it offset paging could skip/duplicate
    # rows at a page boundary. `ix_prospect_tenant_score` (0027) covers the leading
    # (tenant_id, score_total DESC, created_at DESC) sort; the id sort is a cheap final tiebreak.
    offset = decode_cursor(cursor)
    rows = (
        db.execute(
            select(Prospect)
            .where(Prospect.tenant_id == ctx.tenant.id)
            .order_by(
                Prospect.score_total.desc().nullslast(),
                Prospect.created_at.desc(),
                Prospect.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)  # one extra row tells us whether a next page exists
        )
        .scalars()
        .all()
    )
    has_more = len(rows) > limit
    items = [_prospect_out(p) for p in rows[:limit]]
    next_cursor = encode_cursor(offset + limit) if has_more else None
    return ProspectPage(items=items, next_cursor=next_cursor)

@router.get("/{client}/companies", response_model=CompanyPage)
def list_companies(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> CompanyPage:
    """Stage-1 review feed — companies for this client, best fit first (cursor-paged, W5).

    `Company.id` is the deterministic tiebreaker (see `list_prospects` — a find-run batch shares
    one created_at), so offset paging never skips or duplicates a row at a page boundary.
    """
    offset = decode_cursor(cursor)
    rows = (
        db.execute(
            select(Company)
            .where(Company.tenant_id == ctx.tenant.id)
            .order_by(
                Company.score_total.desc().nullslast(),
                Company.created_at.desc(),
                Company.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)  # one extra row tells us whether a next page exists
        )
        .scalars()
        .all()
    )
    has_more = len(rows) > limit
    items = [_company_out(c) for c in rows[:limit]]
    next_cursor = encode_cursor(offset + limit) if has_more else None
    return CompanyPage(items=items, next_cursor=next_cursor)

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

    icp = _validate_icp_id(db, ctx.tenant.id, body.icp_id)  # L8 — parse + tenant-owned-or-404

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
    # Land UNSCORED. Fit scoring is a ~15-25s reasoning call (+retry) that can exceed the 30s API
    # Gateway sync cap on the request path — the web app scores the new row in the background
    # (chunked /companies/rescore), like an Apollo-found row. A re-add keeps the prior score.
    db.flush()  # assign the row's identity before the stage-0 classify mutates its fit_components
    # Stage-0: classify the business model now (one fast, minimal LLM call — NOT the AI-score call)
    # so the manual row carries its Model chip immediately and is market-gated like a found row. A
    # re-add that already has a label is skipped by classify_companies (idempotent).
    classify_companies(ctx.tenant.id, [company], _latest_brief(db, ctx.tenant.id))
    # Scoring v2: stamp the free deterministic label so a manual row shows its v2 verdict too.
    _label_companies_deterministic(db, ctx.tenant.id, [company])
    db.commit()
    db.refresh(company)
    return _company_out(company)

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
    ids = _parse_ids(body.ids)
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

@router.post(
    "/{client}/companies/rescore-async",
    response_model=ScoringJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def rescore_companies_async(
    body: CompanyRescoreIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ScoringJobOut:
    """Kick off a company rescore **asynchronously** (W4); returns a job to poll (202).

    Removes the `MAX_COMPANIES_PER_FIND` sync cap — the same `_score_companies` runs on a background
    worker, so the selection re-scores in one batch (the browser no longer drives a chunk loop),
    capped at `ASYNC_BATCH_MAX`. A still-running job of this kind is returned as-is, so a re-click
    never double-spends. Poll `GET /{client}/scoring-jobs/{job_id}` until `done`/`error`.
    """
    if not body.ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no company ids")
    if len(body.ids) > ASYNC_BATCH_MAX:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"score at most {ASYNC_BATCH_MAX} companies at a time",
        )
    _parse_ids(body.ids)  # validate ids up front (bad UUID → 400) before enqueuing
    job = scoring.enqueue_scoring(
        db, ctx.tenant.id, scoring.KIND_RESCORE_COMPANIES, {"ids": body.ids}
    )
    return _scoring_job_out(job)

@router.post(
    "/{client}/prospects/rescore-async",
    response_model=ScoringJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def rescore_prospects_async(
    body: ProspectRescoreIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ScoringJobOut:
    """Kick off a people rescore (Step-2 'Get AI score') **asynchronously** (W4), capped at
    `ASYNC_BATCH_MAX`. Mirrors `rescore_companies_async`."""
    if not body.identity_keys:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no identity_keys")
    if len(body.identity_keys) > ASYNC_BATCH_MAX:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"score at most {ASYNC_BATCH_MAX} people at a time",
        )
    job = scoring.enqueue_scoring(
        db, ctx.tenant.id, scoring.KIND_RESCORE_PROSPECTS, {"identity_keys": body.identity_keys}
    )
    return _scoring_job_out(job)

@router.post(
    "/{client}/prospects/enrich-score-async",
    response_model=ScoringJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def enrich_score_prospects_async(
    body: ProspectRescoreIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ScoringJobOut:
    """Kick off the combined **'Reveal & score'** (W4): reveal verified emails for the selected
    people (Apollo `people/match` — the credit spend), THEN score them on the revealed data, in ONE
    job.
    Replaces the separate reveal + rescore clicks — scoring pre-reveal gates on missing contact, so
    reveal must come first. Capped at `ASYNC_BATCH_MAX`; the enrich side is idempotent so a re-run
    over already-revealed rows just re-scores (no spend). Mirrors `rescore_prospects_async`."""
    if not body.identity_keys:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no identity_keys")
    if len(body.identity_keys) > ASYNC_BATCH_MAX:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"reveal & score at most {ASYNC_BATCH_MAX} people at a time",
        )
    job = scoring.enqueue_scoring(
        db,
        ctx.tenant.id,
        scoring.KIND_ENRICH_SCORE_PROSPECTS,
        {"identity_keys": body.identity_keys, "slug": ctx.tenant.slug},
    )
    return _scoring_job_out(job)

@router.post(
    "/{client}/companies/find-company-async",
    response_model=ScoringJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def find_company_async(
    body: CompanyFindIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ScoringJobOut:
    """Kick off an Apollo Flow-A company find **asynchronously** (W4). Rows land UNSCORED; the
    worker surfaces deeper errors (e.g. no research scope) as the job's `error`."""
    _validate_icp_id(db, ctx.tenant.id, body.icp_id)
    job = scoring.enqueue_scoring(
        db, ctx.tenant.id, scoring.KIND_FIND_COMPANY, body.model_dump()
    )
    return _scoring_job_out(job)

@router.post(
    "/{client}/companies/find-lookalikes-async",
    response_model=ScoringJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def find_lookalikes_async(
    body: CompanyLookalikeIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ScoringJobOut:
    """Kick off an Apollo lookalike find **asynchronously** (W4). Rows land UNSCORED."""
    if not body.company_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select companies first")
    _validate_icp_id(db, ctx.tenant.id, body.icp_id)
    job = scoring.enqueue_scoring(
        db, ctx.tenant.id, scoring.KIND_FIND_LOOKALIKES, body.model_dump()
    )
    return _scoring_job_out(job)

@router.post(
    "/{client}/companies/update-fields-async",
    response_model=ScoringJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def update_fields_async(
    body: CompanyEnrichIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ScoringJobOut:
    """Kick off an Apollo firmographics refresh ('Update Field') **asynchronously** (W4), capped at
    `ASYNC_BATCH_MAX`."""
    if not body.ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no company ids")
    if len(body.ids) > ASYNC_BATCH_MAX:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"update at most {ASYNC_BATCH_MAX} companies at a time",
        )
    _parse_ids(body.ids)
    job = scoring.enqueue_scoring(db, ctx.tenant.id, scoring.KIND_UPDATE_FIELDS, {"ids": body.ids})
    return _scoring_job_out(job)

@router.get("/{client}/scoring-jobs/{job_id}", response_model=ScoringJobOut)
def scoring_job_status(
    job_id: str,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> ScoringJobOut:
    """Poll one async scoring job (W4) — `status` runs `queued`→`running`→`done`/`error`; `result`
    holds the run counts once `done`. 404 if the id isn't this client's job."""
    jid = uuid_or_404(job_id, "no such job")  # L12 — malformed path id → 404 (M22 standard)
    job = scoring.job_by_id(db, ctx.tenant.id, jid)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such job")
    return _scoring_job_out(job)

@router.get("/{client}/research-runs", response_model=list[ResearchRunOut])
def list_research_runs(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[ResearchRunOut]:
    # §6 perf — bound the scoreboard/drawer feed to the latest 50 runs instead of selecting every
    # research_run the tenant recorded (one per find/rescore/enrich, so it grows without limit).
    rows = db.execute(
        select(ResearchRun)
        .where(ResearchRun.tenant_id == ctx.tenant.id)
        .order_by(ResearchRun.created_at.desc())
        .limit(50)
    ).scalars()
    out = []
    for r in rows:
        cost = float(r.cost_usd) if r.cost_usd is not None else None
        out.append(
            ResearchRunOut(
                run_id=r.run_id,
                source=r.source,
                prompt_version=r.prompt_version,
                rows_pushed=r.rows_pushed,
                cost_usd=cost,
                icp_id=str(r.icp_id) if r.icp_id else None,
                scope_source=r.scope_source,
                filter_body=r.filter_body,
                result_meta=r.result_meta,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
        )
    return out

@router.get("/{client}/sourcing-docs", response_model=SourcingDocList)
def get_sourcing_docs(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> SourcingDocList:
    """The two editable fit rubrics — the v2 score rubrics served under the Step-1/Step-2 tokens."""
    return SourcingDocList(
        company_fit=_doc_out(_latest_doc(db, ctx.tenant.id, fit.COMPANY_SCORE_STAGE)),
        prospect_fit=_doc_out(_latest_doc(db, ctx.tenant.id, fit.PROSPECT_SCORE_STAGE)),
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
    save_stage = _RUBRIC_STAGE[body.stage]  # the FE token → the active v2 rubric stage it edits
    latest = _latest_doc(db, ctx.tenant.id, save_stage)
    doc = Prompt(
        tenant_id=ctx.tenant.id,
        stage=save_stage,
        version=(latest.version + 1) if latest else 1,
        body=body.body,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_out(doc)

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

    icp = _validate_icp_id(db, ctx.tenant.id, body.icp_id)  # L8 — parse + tenant-owned-or-404
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
    # Land UNSCORED (see add_company) — the web app background-scores the new row (chunked
    # /prospects/rescore), keeping the ~15-25s reasoning call off the 30s-capped request path.
    # `scored` here is the lifecycle state (has contact data), NOT a fit score: a manual email is
    # operator-provided, not Apollo-verified, so `email_valid` stays False until people/match.
    prospect.status = "scored" if enrichment["email"] else "found"
    db.commit()
    db.refresh(prospect)
    return _prospect_out(prospect)

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
    spec_blob = (spec.spec or {}) if spec else {}
    if not (spec_blob.get("icp_targeting") or spec_blob.get("people_search_params")):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "generate a research scope before finding people"
        )
    if not body.company_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select companies first")
    # Driven by the explicit Step-2 selection (not a "selected" status): only rows with an Apollo
    # org id can be searched, best fit first, bounded by the 30s cap. Re-searching an already
    # people_found row is allowed — Apollo search is free and the seen-id dedupe drops repeats.
    ids = _parse_ids(body.company_ids)
    selected = (
        db.execute(
            select(Company)
            .where(
                Company.tenant_id == ctx.tenant.id,
                Company.id.in_(ids),
                Company.apollo_org_id.is_not(None),
            )
            .order_by(Company.score_total.desc().nullslast())
            .limit(MAX_ORGS_PER_FIND)
        )
        .scalars()
        .all()
    )
    if not selected:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "the selected companies have no Apollo id to search"
        )

    # Precedence, resolved PER COMPANY from each org's own ICP (the multi-ICP "find ICP by ICP": a
    # mixed selection searches each org with its own personas in one click; `body.icp_id`, when set,
    # pins one ICP for the whole call): a per-call override in the request body → the tenant's SAVED
    # Find-Settings override FOR THAT ICP (persisted server-side, per-ICP — so tuning one ICP's
    # personas never clobbers another's) → the AI spec block for that ICP. `_clean` drops empty
    # filters, so a cleared field widens; `organization_ids` is never taken from here (the loop sets
    # it).
    call_icp = _validate_icp_id(db, ctx.tenant.id, body.icp_id)  # L8 — parse + tenant-owned-or-404
    saved_row = (
        None
        if body.people_search_params is not None
        else _scope_override_row(db, ctx.tenant.id, SCOPE_KIND_PEOPLE)
    )

    # R28 — did an override actually CONTRIBUTE a field this run? A saved override row (or per-call
    # body) can exist yet resolve to an empty block, so `saved_row is not None` over-claims. Track
    # the real contribution so scope_source is truthful.
    used_override = False

    def _people_params_for(comp: Company) -> dict:
        nonlocal used_override
        if body.people_search_params is not None:  # per-call pin → every org in the call
            used_override = used_override or bool(body.people_search_params)
            return body.people_search_params
        icp = call_icp or comp.icp_id
        saved = _scope_override_block(saved_row, icp)
        if saved is not None:
            params = saved.get("people_search_params") or {}
            used_override = used_override or bool(params)
            return params
        block = targeting_for_icp(spec_blob, icp)
        if block is None:
            # Unlabeled/unknown-ICP company under a multi-ICP scope: fall back to the FIRST
            # block — people search is free and a reviewable near-miss beats a hard fail.
            block = (spec_blob.get("icp_targeting") or [{}])[0]
        return block.get("people_search_params") or {}

    per_company = max(1, min(body.per_company, apollo.PER_PAGE_MAX))
    seen_ids = set(
        db.execute(
            select(Prospect.apollo_person_id).where(
                Prospect.tenant_id == ctx.tenant.id, Prospect.apollo_person_id.is_not(None)
            )
        ).scalars()
    )
    run_id, icp = _apollo_run_id(), call_icp
    docs = icp_docs(db, ctx.tenant.id, icp)
    # avoidTitles → hard pre-score drop (Apollo people search has no exclude-title field). Keyed per
    # ICP so a title avoided in one profile is not dropped from another when the run spans ICPs.
    avoid_by_icp = {d["id"]: [t for t in (d.get("avoidTitles") or []) if t] for d in docs}
    new_rows: list[tuple[dict, Company]] = []
    dropped_total = 0
    per_org_meta: dict[str, dict] = {}  # U2 lineage — domain → executed body + relax + counts
    for comp in selected:
        if len(new_rows) >= MAX_PEOPLE_PER_FIND_RUN:
            continue  # batch full — leave this org as-is (still "Pending") for the next run
        try:
            rows, pbody, relax = _search_people_relaxed(
                _people_params_for(comp), comp.apollo_org_id, per_company
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
        per_org_meta[comp.domain or str(comp.apollo_org_id)] = {
            "body": {k: v for k, v in pbody.items() if k != "organization_ids"},
            "relax": relax,
            "raw": len(rows),
            "survivors": len(survivors),
        }
        for p in survivors:
            if len(new_rows) >= MAX_PEOPLE_PER_FIND_RUN:
                break
            seen_ids.add(p["apollo_person_id"])
            new_rows.append((p, comp))

    prospects: list[Prospect] = []
    # R20a — batch-preload the existing prospect rows for this batch (one IN()) instead of a point
    # SELECT per person inside the loop; a row created below is registered so a duplicate reuses it.
    keys = [f"apollo:{p['apollo_person_id']}" for p, _ in new_rows]
    by_key = (
        {
            pr.identity_key: pr
            for pr in db.execute(
                select(Prospect).where(
                    Prospect.tenant_id == ctx.tenant.id, Prospect.identity_key.in_(keys)
                )
            ).scalars()
        }
        if keys
        else {}
    )
    for p, comp in new_rows:
        key = f"apollo:{p['apollo_person_id']}"
        prospect = by_key.get(key)
        if prospect is None:
            prospect = Prospect(tenant_id=ctx.tenant.id, identity_key=key, source="apollo")
            db.add(prospect)
            by_key[key] = prospect
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
    # U2 lineage: the per-org executed bodies (`filter_body.per_org`) + run summary (`result_meta`)
    # feed the Find-history drawer; `group_id` (FE-minted) threads the chunked calls of one merged
    # stage→find so N 8-org chunks collapse to one history entry.
    db.add(
        ResearchRun(
            tenant_id=ctx.tenant.id,
            run_id=run_id,
            spec_version=spec.version,
            icp_id=icp,
            # N25 — people-finds get their OWN source tag so they don't dilute the company-find
            # cursor scan (`_CURSOR_FIND_SOURCES` = apollo/lookalike): a burst of people-finds could
            # push company-find runs out of the latest-50 scan and lose the company page cursor. The
            # drawer still shows them as "Find" (source→type defaults to find) and tells people from
            # company finds by `filter_body.per_org`, not the source.
            source="apollo_people",
            rubric_version=fit.SCORE_RUBRIC_VERSION,
            rows_pushed=len(prospects),
            cost_usd=0.0,
            filter_body={"per_org": per_org_meta},
            # R28 — "custom" only when an override actually contributed ≥1 field (an empty per-call
            # body or a saved row that resolved to nothing is really an "ai" scope).
            scope_source="custom" if used_override else "ai",
            result_meta={
                "orgs_searched": len(selected),
                "people_found": len(prospects),
                "dropped": dropped_total,
                "group_id": body.group_id,
            },
        )
    )
    db.commit()
    # N7 — reload the freshly-inserted rows in ONE query instead of a per-row db.refresh (which was
    # up to ASYNC_BATCH_MAX Data-API round trips on the 30s sync find path). PKs are populated by
    # the flush RETURNING and survive the commit-expire without emitting SQL, so an IN()-by-id
    # re-select is equivalent to the loop.
    ids = [p.id for p in prospects]
    fresh = (
        db.execute(
            select(Prospect).where(
                Prospect.tenant_id == ctx.tenant.id, Prospect.id.in_(ids)
            )
        )
        .scalars()
        .all()
        if ids
        else []
    )
    fresh.sort(key=lambda p: (p.score_total is None, -(p.score_total or 0)))
    return FindResult(
        run_id=run_id,
        found=len(prospects),
        dropped=dropped_total,
        prospects=[_prospect_out(p) for p in fresh],
    )

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
    ids = _parse_ids(body.company_ids)
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
    # W8 — the same org set re-opened (or re-ticked) within the TTL returns the memoized sidebar
    # instead of re-firing ~26 Apollo probes. Keyed per (tenant, org set); counts are stable enough
    # over a few minutes that a short TTL is invisible to the operator.
    facets_key = (str(ctx.tenant.id), tuple(sorted(org_ids)))
    cached = _PEOPLE_FACETS_CACHE.get(facets_key)
    if cached is not None:
        return cached
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
    out = PeopleFacetsOut(
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
    _PEOPLE_FACETS_CACHE.set(facets_key, out)
    return out

@router.get("/{client}/scope-override", response_model=ScopeOverrideOut)
def get_scope_override(
    kind: str = SCOPE_KIND_PEOPLE,
    icp_id: str | None = None,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> ScopeOverrideOut:
    """The tenant's saved Find-Settings override for one pipeline step + ICP (`kind`=people|company,
    `icp_id` optional), or null when none is saved (→ the Workspace shows the AI scope). Persisted
    server-side so a saved tuning follows the operator across browsers/devices, per ICP."""
    _require_scope_kind(kind)
    block = _scope_override_block(_scope_override_row(db, ctx.tenant.id, kind), icp_id)
    return ScopeOverrideOut(params=block)

@router.put("/{client}/scope-override", response_model=ScopeOverrideOut)
def save_scope_override(
    body: ScopeOverrideIn,
    kind: str = SCOPE_KIND_PEOPLE,
    icp_id: str | None = None,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ScopeOverrideOut:
    """Save the Find Settings as the tenant's override for one (step, ICP). It then wins over the AI
    spec on every Find for that ICP until reset.

    An EMPTY payload (no facet chosen) is a revert, not a save: it drops this ICP's entry so the
    next Find falls back to the AI scope — same as DELETE. Persisting an all-empty override would
    otherwise silently widen every search. Other ICPs' saved overrides are left untouched."""
    _require_scope_kind(kind)
    block = body.params if _has_scope_value(body.params) else None
    _write_scope_override(db, ctx.tenant.id, kind, icp_id, block)
    return ScopeOverrideOut(params=block)

@router.get("/{client}/people/departments", response_model=list[FacetOption])
def people_departments(
    ctx: AccessContext = Depends(require_membership()),
) -> list[FacetOption]:
    """The 14 master Department & Job Function options (value + label) — the single source of truth
    for the Find-Settings department list before live counts load. Static (Apollo's taxonomy), no
    Apollo call, no spend; the frontend renders these so it never hardcodes the master list."""
    return [FacetOption(value=d, label=_facet_label(d)) for d in MASTER_DEPARTMENTS]

@router.delete("/{client}/scope-override", status_code=status.HTTP_204_NO_CONTENT)
def reset_scope_override(
    kind: str = SCOPE_KIND_PEOPLE,
    icp_id: str | None = None,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> None:
    """Discard the saved override for one (step, ICP) → that ICP's Find reverts to the AI scope.
    Idempotent; leaves other ICPs' overrides intact."""
    _require_scope_kind(kind)
    _write_scope_override(db, ctx.tenant.id, kind, icp_id, None)
