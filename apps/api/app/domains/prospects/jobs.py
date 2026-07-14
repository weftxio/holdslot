"""Async scoring/find job layer — the `run_*` background handlers, the `SCORING_HANDLERS` dispatch
table (owning it here shrinks the scoring.py lazy import to this leaf, not the whole router),
`ASYNC_BATCH_MAX`, and `_scoring_job_out`."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.prospects import (
    apollo_map,
    labeling,
    scoring,
)
from app.domains.prospects.company_find import (
    _apply_enrichment,
    _find_company_core,
    _lookalike_core,
)
from app.domains.prospects.label_engine import (
    _SCORE_WORKERS,
    _score_companies_v2,
    _score_prospects_v2,
)
from app.domains.prospects.people_find import _enrich_prospects
from app.domains.prospects.schemas import (
    ScoringJobOut,
)
from app.domains.prospects.scope import _apollo_run_id, _parse_ids
from app.integrations.apollo import client as apollo
from app.models import (
    Company,
    Prospect,
    ResearchRun,
    ScoringJob,
)

# Selection-based async jobs (the bucket "Score next 15" CTAs + "Reveal & score" + "Update Field")
# batch at most this many rows per job — the FE messages when a larger selection is picked. Sized to
# one concurrent scoring WAVE (`_SCORE_WORKERS`): a reasoning `company_score` call is ~70s, and two
# waves overran the Lambda and left the worker killed mid-batch → a zombie `running` job. One wave ≈
# one call's wall-clock, well inside the timeout. (scoring.py's reaper backstops any overrun.)
ASYNC_BATCH_MAX = _SCORE_WORKERS  # 15

def run_rescore_companies(db: Session, tenant_id, params: dict) -> dict:
    """W4 handler (`KIND_RESCORE_COMPANIES`): re-score the company ids in `params`."""
    raw = [str(x) for x in (params.get("ids") or [])][:ASYNC_BATCH_MAX]
    ids = _parse_ids(raw)
    if not ids:
        return {"scored": 0, "failed": 0, "cost_usd": 0.0}
    rows = (
        db.execute(select(Company).where(Company.tenant_id == tenant_id, Company.id.in_(ids)))
        .scalars()
        .all()
    )
    if not rows:
        return {"scored": 0, "failed": 0, "cost_usd": 0.0}
    return _score_companies_v2(db, tenant_id, rows)  # scoring v2 cutover (v1 _score_companies dead)

def run_rescore_prospects(db: Session, tenant_id, params: dict) -> dict:
    """W4 handler (`KIND_RESCORE_PROSPECTS`): re-score the people identity_keys in `params`."""
    keys = [str(k) for k in (params.get("identity_keys") or [])][:ASYNC_BATCH_MAX]
    if not keys:
        return {"scored": 0, "failed": 0, "cost_usd": 0.0}
    rows = (
        db.execute(
            select(Prospect).where(
                Prospect.tenant_id == tenant_id, Prospect.identity_key.in_(keys)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return {"scored": 0, "failed": 0, "cost_usd": 0.0}
    return _score_prospects_v2(db, tenant_id, rows)  # scoring v2 cutover (v1 _score_prospects dead)

def run_enrich_score_prospects(db: Session, tenant_id, params: dict) -> dict:
    """W4 handler (`KIND_ENRICH_SCORE_PROSPECTS`) — the combined 'Reveal & score': reveal verified
    emails (Apollo `people/match`, the credit spend) for the identity_keys, THEN score them on the
    revealed data, in one job. Reveal-first is the whole point: Apollo obfuscates
    seniority/department/email until match, so scoring a pre-reveal row gates on missing contact and
    lands a degraded label. Idempotent on the enrich side (an already-revealed row never re-spends),
    so a re-run just re-scores. Bounded by `ASYNC_BATCH_MAX` (one wave). Returns the merged counts
    `{requested, enriched, credits_spent, enrich_failed, skipped_excluded, scored, failed,
    cost_usd}`."""
    keys = [str(k) for k in (params.get("identity_keys") or [])][:ASYNC_BATCH_MAX]
    zero = {
        "requested": 0,
        "enriched": 0,
        "credits_spent": 0,
        "enrich_failed": 0,
        "skipped_excluded": 0,
        "scored": 0,
        "failed": 0,
        "cost_usd": 0.0,
    }
    if not keys:
        return zero
    rows = (
        db.execute(
            select(Prospect).where(
                Prospect.tenant_id == tenant_id, Prospect.identity_key.in_(keys)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return zero
    # R8 — never spend a credit revealing a person under an `excluded_by_rules` company: the free
    # people gate already labels them "parent company excluded", so paying to reveal contact is pure
    # waste. Skip those pre-enrich (no match call); `_score_prospects_v2` still labels ALL rows via
    # the free deterministic gate, so the excluded ones land labeled without a spend.
    company_ids = {p.company_id for p in rows if p.company_id}
    excluded_parents = (
        set(
            db.execute(
                select(Company.id).where(
                    Company.tenant_id == tenant_id,
                    Company.id.in_(company_ids),
                    Company.label == labeling.EXCLUDED,
                )
            ).scalars()
        )
        if company_ids
        else set()
    )
    enrichable = [p for p in rows if p.company_id not in excluded_parents]
    skipped = len(rows) - len(enrichable)
    enr = _enrich_prospects(db, enrichable, str(params.get("slug") or ""))
    sc = _score_prospects_v2(db, tenant_id, rows)  # reads the just-revealed enrichment (email/dept)
    return {
        "requested": len(rows),
        "enriched": enr["enriched"],
        "credits_spent": enr["credits_spent"],
        "enrich_failed": enr["failed"],
        "skipped_excluded": skipped,
        "scored": sc["scored"],
        "failed": sc["failed"],
        "cost_usd": sc["cost_usd"],
    }

def run_find_company(db: Session, tenant_id, params: dict) -> dict:
    """W4 handler (`KIND_FIND_COMPANY`): Apollo Flow-A find (rows land UNSCORED)."""
    fr = _find_company_core(db, tenant_id, params)
    return {
        "found": fr.found,
        "dropped": fr.dropped,
        "run_id": fr.run_id,
        "scope_exhausted": fr.scope_exhausted,  # Stage 3 — surface the "regenerate" signal
        "known_skipped": fr.known_skipped,
    }

def run_find_lookalikes(db: Session, tenant_id, params: dict) -> dict:
    """W4 handler (`KIND_FIND_LOOKALIKES`): Apollo lookalike find (rows land UNSCORED)."""
    fr = _lookalike_core(db, tenant_id, params)
    return {"found": fr.found, "dropped": fr.dropped, "run_id": fr.run_id}

def run_update_fields(db: Session, tenant_id, params: dict) -> dict:
    """W4 handler (`KIND_UPDATE_FIELDS`): re-enrich Apollo firmographics for the company ids."""
    raw = [str(x) for x in (params.get("ids") or [])][:ASYNC_BATCH_MAX]
    ids = _parse_ids(raw)
    if not ids:
        return {"updated": 0, "requested": 0}
    rows = (
        db.execute(select(Company).where(Company.tenant_id == tenant_id, Company.id.in_(ids)))
        .scalars()
        .all()
    )
    if not rows:
        return {"updated": 0, "requested": 0}
    return _update_fields_core(db, tenant_id, rows)

# Registry the worker dispatches on by `scoring_job.kind`. Defined here (not in scoring.py) because
# the handlers reuse this module's scoring helpers; the worker imports this dict lazily (no cycle).
SCORING_HANDLERS = {
    scoring.KIND_RESCORE_COMPANIES: run_rescore_companies,
    scoring.KIND_RESCORE_PROSPECTS: run_rescore_prospects,
    scoring.KIND_ENRICH_SCORE_PROSPECTS: run_enrich_score_prospects,
    scoring.KIND_FIND_COMPANY: run_find_company,
    scoring.KIND_FIND_LOOKALIKES: run_find_lookalikes,
    scoring.KIND_UPDATE_FIELDS: run_update_fields,
}

def _scoring_job_out(job: ScoringJob | None) -> ScoringJobOut:
    if job is None:
        return ScoringJobOut(status="idle")
    return ScoringJobOut(
        job_id=str(job.id),
        status=job.status,
        result=job.result or {},
        error=job.error,
    )

def _update_fields_core(db: Session, tenant_id, rows: list[Company]) -> dict:
    """Re-enrich Apollo firmographics (one `organizations/enrich` call per domain, concurrent) onto
    the given company rows, record one `research_run` (source=enrich, no LLM cost), and return
    counts (`{updated, requested}`). Shared by the sync `/companies/update-fields` endpoint and the
    W4 async worker — both load the (tenant-scoped) rows first. A hard Apollo failure raises (the
    worker turns it into a job error); a per-domain miss simply leaves that row unchanged."""
    domains = [c.domain for c in rows if c.domain]
    try:
        enriched = apollo.enrich_organizations(domains)
    except apollo.ApolloError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"apollo enrich failed: {e}") from e
    by_domain = {
        p["domain"]: p for o in enriched if (p := apollo_map.parse_enrich(o)).get("domain")
    }
    updated = 0
    for c in rows:
        e = by_domain.get(c.domain)
        if e:
            _apply_enrichment(c, e)
            updated += 1
    db.add(
        ResearchRun(
            tenant_id=tenant_id,
            run_id=_apollo_run_id(),
            source="enrich",
            rows_pushed=len(rows),
            cost_usd=0.0,
        )
    )
    db.commit()
    for c in rows:
        db.refresh(c)
    return {"updated": updated, "requested": len(rows)}
