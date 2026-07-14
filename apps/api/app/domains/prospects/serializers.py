"""Row serializers for the prospects package — Company/Prospect/enrichment/sourcing-doc → API
shapes. Dependency-free leaf."""

from __future__ import annotations

from app.domains.prospects.schemas import (
    CompanyEnrichment,
    CompanyOut,
    ProspectOut,
    SourcingDocOut,
)
from app.models import (
    Company,
    Prompt,
    Prospect,
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
        fit_reason=comps.get("fit_reason", ""),
        # Scoring v2 — label/score_total from columns; reason/subscores/flags/icp from components.
        label=p.label,
        score_total=p.score_total,
        reason=p.fit_reason or comps.get("reason", "") or comps.get("fit_reason", ""),
        subscores=comps.get("subscores", {}),
        flags=comps.get("flags", []),
        icp=comps.get("icp"),
        source=p.source,
        status=p.status,
        created_at=p.created_at.isoformat() if p.created_at else None,
    )

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
        fit_reason=c.fit_reason or comps.get("fit_reason", ""),
        business_model=comps.get("business_model", ""),
        # Scoring v2 — label/score_total from the columns; the rest from components.
        label=c.label,
        score_total=c.score_total,
        reason=c.fit_reason or comps.get("reason", "") or comps.get("fit_reason", ""),
        subscores=comps.get("subscores", {}),
        flags=comps.get("flags", []),
        icp=comps.get("icp"),
        enrichment=_company_enrichment(c.evidence),
        source=c.source,
        status=c.status,
        created_at=c.created_at.isoformat() if c.created_at else None,
    )

def _company_payload(c: Company) -> dict:
    """The company facts the rubric scores against (stage-1 firmographics + evidence). Carries the
    already-classified `business_model` (stamped by classify_business_model at find/add time) so
    score_company can re-apply the market gate WITHOUT re-classifying (stage-0 owns the label)."""
    return {
        "name": c.name,
        "domain": c.domain,
        "industry": c.industry,
        "size": c.size,
        "country": c.country,
        "linkedin_url": c.linkedin_url,
        **(c.evidence or {}),
        "business_model": (c.fit_components or {}).get("business_model", ""),
    }

def _classify_payload(c: Company) -> dict:
    """The minimal signals the stage-0 business-model classifier judges from — identity + the
    description / industries / keywords out of the enrich evidence. Deliberately excludes the
    rubric, targeting and full firmographics (business_model is factual + client-independent) to
    keep the call tiny."""
    ev = c.evidence or {}
    return {
        "name": c.name,
        "domain": c.domain,
        "industry": c.industry,
        "short_description": ev.get("short_description") or "",
        "industries": [*(ev.get("industries") or []), *(ev.get("secondary_industries") or [])],
        "keywords": ev.get("keywords") or [],
    }

def _prospect_payload(enrichment: dict | None, company: Company | None) -> dict:
    """The person facts the stage-2 rubric scores against — the decision-maker signals (title,
    seniority, department, email) PLUS the parent company's firmographics + its v2 `label` (which
    caps the person), so a person is judged as a decision-maker INSIDE an already-qualified account.
    Apollo obfuscates seniority/department until enrich, so those stay empty pre-enrich (rubric
    Unknown policy applies); the persona scope reaches the model via the targeting `spec`."""
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
        payload["company_label"] = company.label
        payload["company_reason"] = company.fit_reason or (company.fit_components or {}).get(
            "reason", ""
        )
    return payload

def _doc_out(d: Prompt | None) -> SourcingDocOut | None:
    if d is None:
        return None
    return SourcingDocOut(
        stage=d.stage,
        version=d.version,
        body=d.body,
        created_at=d.created_at.isoformat() if d.created_at else None,
    )
