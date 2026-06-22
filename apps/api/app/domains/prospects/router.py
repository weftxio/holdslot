"""Prospect routes — the manual-add + fit-scoring surface (Apollo find/enrich lands in Phase C).

One suppression gate and one scoring door (`fit.py`). Tenant scope × role is enforced by the A4
central guard, so every query is scoped to the caller's client. The heavy lifting lives in the
pure modules; this layer is orchestration + persistence.

The Clay seed/CSV-import/AI-sourcing loop was removed in the Apollo-only teardown; the programmatic
Apollo find → score → select → enrich endpoints replace it in Phase C (see docs/initial-build-plan
→ Phase C). `confirm_enrich` currently only marks the selected rows — the real `people/match`
enrichment is wired in C5.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import AccessContext, get_db, require_membership
from app.domains.prospects import fit
from app.domains.prospects.identity import normalize_domain, normalize_email
from app.domains.prospects.schemas import (
    CompanyManualIn,
    CompanyOut,
    EnrichIn,
    EnrichResult,
    ProspectManualIn,
    ProspectOut,
    ResearchRunOut,
    SourcingDocIn,
    SourcingDocList,
    SourcingDocOut,
)
from app.domains.prospects.suppression import Candidate, extract_exclusions
from app.integrations.openrouter.client import LlmError
from app.models import (
    Brief,
    Company,
    MembershipRole,
    Prompt,
    Prospect,
    ResearchRun,
    ResearchSpec,
)

router = APIRouter(tags=["prospects"])

_VALID_STAGES = ("fit_scoring",)


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


def _build_exclusions(brief: Brief | None, spec: ResearchSpec | None):
    return extract_exclusions(brief.data if brief else {}, spec.spec if spec else None)


def _exclusions(db: Session, tenant_id):
    return _build_exclusions(_latest_brief(db, tenant_id), _latest_spec(db, tenant_id))


def _build_targeting(brief: Brief | None, spec: ResearchSpec | None) -> dict:
    return {"brief": brief.data if brief else {}, "spec": spec.spec if spec else {}}


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


def _score_company(c: Company, *, tenant_id, rubric_body: str, targeting: dict) -> float:
    """Score one company in place (LLM). Returns the call's cost_usd. Raises LlmError."""
    scored = fit.score_company(
        tenant_id=tenant_id,
        rubric_body=rubric_body,
        company=_company_payload(c),
        targeting=targeting,
    )
    c.fit_score = scored["fit_score"]
    c.fit_tier = scored["fit_tier"]
    c.fit_components = scored["fit_components"]
    c.fit_reason = scored["fit_reason"]
    return float(scored.get("cost_usd") or 0.0)


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

    brief, spec = _latest_brief(db, ctx.tenant.id), _latest_spec(db, ctx.tenant.id)
    targeting = _build_targeting(brief, spec)
    rubric = _latest_doc(db, ctx.tenant.id, "fit_scoring")
    rubric_body = rubric.body if rubric else ""

    company = db.execute(
        select(Company).where(Company.tenant_id == ctx.tenant.id, Company.domain == domain)
    ).scalar_one_or_none()
    if company is None:
        company = Company(tenant_id=ctx.tenant.id, domain=domain, source="manual")
        db.add(company)
    company.name = body.name or company.name or ""
    company.website = body.website or company.website
    company.linkedin_url = body.linkedin_url or company.linkedin_url
    company.industry = body.industry or company.industry
    company.size = body.size or company.size
    company.country = body.country or company.country
    if body.icp_id:
        company.icp_id = uuid.UUID(body.icp_id)
    try:
        _score_company(
            company, tenant_id=ctx.tenant.id, rubric_body=rubric_body, targeting=targeting
        )
    except LlmError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"scoring failed: {e}") from e
    db.commit()
    db.refresh(company)
    return _company_out(company)


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
    versions = list(
        db.execute(
            select(Prompt.version)
            .where(Prompt.tenant_id == ctx.tenant.id, Prompt.stage == "fit_scoring")
            .order_by(Prompt.version.desc())
        ).scalars()
    )
    return SourcingDocList(
        fit_scoring=_doc_out(_latest_doc(db, ctx.tenant.id, "fit_scoring")),
        rubric_versions=versions,
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

    brief, spec = _latest_brief(db, ctx.tenant.id), _latest_spec(db, ctx.tenant.id)
    targeting = _build_targeting(brief, spec)
    rubric = _latest_doc(db, ctx.tenant.id, "fit_scoring")
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
    prospect.enrichment = enrichment
    prospect.email_valid = False
    prospect.last_enriched_at = func.now()
    if body.icp_id:
        prospect.icp_id = uuid.UUID(body.icp_id)
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
            enrichment=enrichment,
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


@router.post("/{client}/prospects/enrich", response_model=EnrichResult)
def confirm_enrich(
    body: EnrichIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> EnrichResult:
    """The enrich gate — the user confirms which scored people to enrich. Marks them `confirmed`.

    Interim: this only flips status. The paid Apollo `people/match` enrichment (email/phone) is
    wired in Phase C (C5), gated on this selection.
    """
    if not body.identity_keys:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no identity_keys")
    rows = (
        db.execute(
            select(Prospect).where(
                Prospect.tenant_id == ctx.tenant.id,
                Prospect.identity_key.in_(body.identity_keys),
                Prospect.status.in_(("found", "scored", "confirmed")),
            )
        )
        .scalars()
        .all()
    )
    for p in rows:
        p.status = "confirmed"
    db.commit()
    return EnrichResult(confirmed=len(rows))
