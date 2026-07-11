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

import hashlib
import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.core.deps import AccessContext, get_db, require_membership
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
    feedback,
    find,
    fit,
    labeling,
    lookalike,
    scoring,
    tech_vocab,
)
from app.domains.prospects.identity import normalize_domain, normalize_email
from app.domains.prospects.schemas import (
    CompanyEnrichIn,
    CompanyEnrichment,
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
    ScoringJob,
)

router = APIRouter(tags=["prospects"])
log = logging.getLogger("holdslot.prospects")

# W8 caches (warm-container memo; see app/core/cache.py).
#   * Company search is the credit-costing Apollo call — short TTL coalesces a re-run of the same
#     scope (double-click / re-find) without spending again. Keyed by the filter alone: Apollo
#     returns the same rows for any caller, so the key is global (raw rows, pre-suppression).
#   * The people-facet sidebar is ~26 free Apollo probes per open — memoized per (tenant, org set).
_COMPANY_SEARCH_CACHE = TTLCache(ttl_seconds=90)
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

# Sync-budget caps. Find/enrich run synchronously behind the 30s API-Gateway HTTP-API cap, and each
# scored row is one blocking LLM call — so a single request must bound how many it does. Larger sets
# are drained over repeated calls (find_people advances each processed org to `people_found`; the
# operator re-clicks to continue). Keep the product (calls × ~1-2s) comfortably under 30s.
MAX_COMPANIES_PER_FIND = 15  # LLM-scored companies per RESCORE/update request (30s sync cap)
# D+ Stage 1b — find-company fetches + stage-0-classifies this many rows. Fit-scoring is deferred to
# the async rescore path, so find is latency-bound (classify+enrich), NOT credit-bound (company
# search + org enrich are FREE on this account). The find-company path is ASYNC (a background
# scoring_job, not the 30s request), so the ceiling is the worker/Lambda budget — Stage 1b lifts it
# to 100 to hit the ≥3× rows/find KPI. (The v1 sync `/find-company` twin + its separate clamp were
# retired in V2-4 — the web app uses the async variant only.)
FIND_COMPANY_LIMIT = int(os.environ.get("HOLDSLOT_FIND_COMPANY_LIMIT", "100"))
# D+ Stage 1b relax ladder. A company search returning fewer than FIND_RELAX_MIN matches auto-widens
# one deterministic rung at a time (see `_company_relax_ladder`) so a find never dead-ends on an
# over-narrow AI scope (KPI: <10% zero-result finds). FIND_OVER_BROAD flags a scope so loose the
# result is noise (surfaced in the Find-history drawer, not auto-narrowed). Both env-tunable.
FIND_RELAX_MIN = int(os.environ.get("HOLDSLOT_FIND_RELAX_MIN", "25"))
FIND_OVER_BROAD = int(os.environ.get("HOLDSLOT_FIND_OVER_BROAD", "100000"))
MAX_ORGS_PER_FIND = 8  # selected orgs searched per find-people request (1 Apollo call each)
MAX_PEOPLE_PER_FIND_RUN = 250  # unscored people landed per find-people request (free, no LLM)


def _parse_ids(raw: list[str]) -> list[uuid.UUID]:
    """Parse a batch of client-supplied id strings into UUIDs, raising 400 on any malformed value.

    A bare `uuid.UUID(bad)` raises ValueError, which would surface as an unhandled 500; this turns
    it into a clean 400 (W2 consolidation — one parse door for every batch endpoint).
    """
    try:
        return [uuid.UUID(i) for i in raw]
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid id") from exc
_ENRICH_WORKERS = 8  # concurrent Apollo people/match calls (HTTP-bound, like the score fan-out)
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
SCOPE_KIND_COMPANY = "company"  # ScopeOverride.kind for the Step-1 Find Settings facets
_SCOPE_GLOBAL = "*"  # by_icp key for an ICP-less (single-ICP / legacy) override


def _scope_override_row(db: Session, tenant_id, kind: str) -> ScopeOverride | None:
    """The tenant's single ScopeOverride row for this pipeline step (`people`/`company`), or None.
    The row holds a per-ICP map (`params.by_icp`); resolve one ICP's block with
    `_scope_override_block`."""
    return db.execute(
        select(ScopeOverride).where(
            ScopeOverride.tenant_id == tenant_id, ScopeOverride.kind == kind
        )
    ).scalar_one_or_none()


def _scope_override_block(row: ScopeOverride | None, icp_id) -> dict | None:
    """The saved manual override block for ONE ICP (`{people_search_params}` for people;
    `{company_search_params, intent_filters}` for company), or None → use the AI scope.

    Reads the per-ICP map (`params.by_icp`, keyed by ICP id string). A legacy FLAT payload — one
    saved before per-ICP keying — is treated as a global fallback that applies to any ICP until it
    is re-saved per-ICP (the first per-ICP save supersedes it)."""
    if row is None:
        return None
    params = row.params or {}
    by_icp = params.get("by_icp")
    if by_icp is None:
        return params or None  # legacy flat payload → global fallback
    if icp_id is not None:
        hit = by_icp.get(str(icp_id))
        if hit is not None:
            return hit  # per-ICP override wins
    return by_icp.get(_SCOPE_GLOBAL)  # ICP-less global entry as the fallback (or None → AI scope)


def _has_scope_value(v) -> bool:
    """True if a save payload carries any actual facet value (recursing into nested dicts). An
    all-empty block — every leaf array/number empty/None — is a revert, not a stored override that
    would silently widen every search."""
    if isinstance(v, dict):
        return any(_has_scope_value(x) for x in v.values())
    if isinstance(v, (list, tuple, set, str)):
        return len(v) > 0
    return v is not None


def _merge_scope_map(params: dict | None, icp_id, block: dict | None) -> dict | None:
    """Set (or clear, when `block` is None) one ICP's entry in a (tenant, kind) row's per-ICP map.
    Returns the new `params` payload, or None when the map is empty (→ delete the row). A legacy
    FLAT payload (no `by_icp`) is discarded here: the first per-ICP write supersedes it. Other ICPs'
    entries are always preserved."""
    by_icp = dict((params or {}).get("by_icp") or {})
    key = str(icp_id) if icp_id is not None else _SCOPE_GLOBAL
    if block is None:
        by_icp.pop(key, None)
    else:
        by_icp[key] = block
    return {"by_icp": by_icp} if by_icp else None


def _write_scope_override(db: Session, tenant_id, kind: str, icp_id, block: dict | None) -> None:
    """Upsert (or clear) one ICP's entry in the (tenant, kind) override row's per-ICP map. When the
    map empties the row is deleted (→ full AI scope)."""
    row = _scope_override_row(db, tenant_id, kind)
    payload = _merge_scope_map(row.params if row else None, icp_id, block)
    if payload is None:
        if row is not None:
            db.delete(row)
            db.commit()
        return
    if row is None:
        db.add(ScopeOverride(tenant_id=tenant_id, kind=kind, params=payload))
    else:
        row.params = payload
    db.commit()


def _require_scope_kind(kind: str) -> None:
    if kind not in (SCOPE_KIND_PEOPLE, SCOPE_KIND_COMPANY):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown scope kind")


def _build_exclusions(brief: Brief | None, spec: ResearchSpec | None):
    return extract_exclusions(brief.data if brief else {}, spec.spec if spec else None)


def _exclusions(db: Session, tenant_id):
    return _build_exclusions(_latest_brief(db, tenant_id), _latest_spec(db, tenant_id))


def _feedback_rows(db: Session, tenant_id) -> list[dict]:
    """The tenant's labeled companies as the rows `feedback.py` aggregates over (D+ Stage 3/4):
    the v2 `label` (won = contact_now/contact_soon, lost = low_fit/excluded_by_rules) + country +
    descriptive keywords/industry + enrich technology names. Only labeled rows carry signal."""
    rows = db.execute(
        select(
            Company.label, Company.country, Company.industry, Company.evidence,
        ).where(Company.tenant_id == tenant_id, Company.label.is_not(None))
    ).all()
    return [
        {
            "label": label,
            "country": country,
            "industry": industry,
            "keywords": (evidence or {}).get("keywords") or [],
            "technologies": (evidence or {}).get("technology_names") or [],
        }
        for label, country, industry, evidence in rows
    ]


def _resolve_tech(names: list[str]) -> list[str]:
    """Free-text tech names → Apollo tech UIDs via the cached `supported_technologies_csv` vocab
    (D+ Stage 4). Best-effort: an Apollo/transport failure or empty vocab degrades to 'no tech
    filter' (never crashes the find). Returns the ordered, de-duped UID hit list; ambiguous/miss
    names are dropped (never guessed) — see `tech_vocab.resolve`."""
    clean = [n for n in names if n and str(n).strip()]
    if not clean:
        return []
    try:
        vocab = tech_vocab.parse_vocab(apollo.supported_technologies_csv())
    except apollo.ApolloError as e:
        log.warning("tech vocab unavailable — skipping tech filter: %s", e)
        return []
    return tech_vocab.resolve(clean, vocab).uids


def _merge_uids(filter_body: dict, key: str, uids: list[str]) -> dict:
    """Merge `uids` into `filter_body[key]`, de-duped and order-preserving (existing first)."""
    if not uids:
        return filter_body
    existing = filter_body.get(key) or []
    return {**filter_body, key: list(dict.fromkeys([*existing, *uids]))}


def _drop_conflicts(values: list[str], reserved: set[str], *, fold: bool = False) -> list[str]:
    """Drop any `values` entry that also appears in `reserved` — the self-contradiction guard for
    the two server-added filter pairs: never exclude a location the scope includes, never forbid a
    tech UID the ICP requires (either would AND include∩exclude to zero results). `fold` case-folds
    the membership test for location names; tech UIDs come pre-normalized so match exactly."""
    if fold:
        return [v for v in values if str(v).strip().lower() not in reserved]
    return [v for v in values if v not in reserved]


# W7 — only the FIT-relevant brief fields reach the paid scorer (founder-approved keep-list,
# 2026-06-25). The dropped fields (logistics/handoff: attendee emails, attendees, availability,
# channel, contact, approver, meetingsPerMonth · messaging: website, proofPoints, tone, languages ·
# exclusions, already applied by suppression) don't inform whether a prospect FITS — cutting them
# trims tokens on every scoring call AND keeps PII (emails / contact) out of the LLM prompt.
_SCORING_BRIEF_FIELDS = frozenset(
    {
        "companyName",
        "sell",
        "problem",
        "dealSize",
        "salesCycle",
        "valueProps",
        "signals",
        "qualifiedDef",
        # B2B / B2C / Both — drives the v2 market gate (labeling.build_rules_config reads it from
        # the brief). Must reach the scorer's targeting.brief slice for the gate to read it.
        "targetMarket",
    }
)


def _trim_brief_for_scoring(data: dict) -> dict:
    """Keep only the fit-relevant brief fields (W7). Scoping (Brief→ResearchSpec) still gets the
    full brief; this trim is fit-scoring only."""
    return {k: v for k, v in data.items() if k in _SCORING_BRIEF_FIELDS}


def _trim_spec_for_scoring(spec_blob: dict, icp_id=None) -> dict:
    """Drop the spec's `credit_policy` (operational budget caps — not a fit signal) from the scoring
    context (W7); the search-param blocks that define the ICP stay.

    For a v4 multi-ICP spec, keep only the scored row's own ICP block — flattened back to the
    single-block shape the fit rubrics already read, so the rubric prompts never change and the
    scorer isn't fed N-1 irrelevant ICPs' params (smaller prompt, sharper targeting). A v3 spec
    passes through unchanged; an unresolvable ICP (multi-ICP spec, unscoped row) falls back to the
    whole spec so scoring still has the ICP-union context it had before."""
    trimmed = {k: v for k, v in spec_blob.items() if k != "credit_policy"}
    if "icp_targeting" not in trimmed:
        return trimmed
    block = targeting_for_icp(spec_blob, icp_id)
    if block is None:
        return trimmed
    return {
        "spec_version": trimmed.get("spec_version"),
        "company_search_params": block.get("company_search_params") or {},
        "people_search_params": block.get("people_search_params") or {},
        "intent_filters": block.get("intent_filters") or {},
        "icp_validation": trimmed.get("icp_validation") or {},
    }


def _build_targeting(
    brief: Brief | None,
    spec: ResearchSpec | None,
    icps: list[dict] | None = None,
    icp_id=None,
) -> dict:
    """The fit scorer's targeting context. Trimmed to the fit-relevant slice (W7): the keep-listed
    brief fields + the spec minus `credit_policy` + the ICP persona profiles.

    `icps` carries the persona profiles the rubric grades maturity/department/tech/economic-buyer
    against (docs/prompts/fit-scoring-rubric-v1.md §2/§3). Without them those sub-criteria score 0
    by the rubric's Unknown policy, so the ICP docs are not optional context — they unlock points
    that are otherwise structurally unreachable. `icp_id` (the scored row's ICP) narrows a v4
    spec to that ICP's own targeting block — pass it whenever the row carries one.
    """
    return {
        "brief": _trim_brief_for_scoring(brief.data) if brief else {},
        "spec": _trim_spec_for_scoring(spec.spec, icp_id) if spec else {},
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


# --------------------------------------------------------------------------- prospects list


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
        fit_reason=c.fit_reason or comps.get("fit_reason", ""),
        business_model=comps.get("business_model", ""),
        # Scoring v2 — label/score_total from the columns; the rest from components.
        label=c.label,
        score_total=c.score_total,
        reason=c.fit_reason or comps.get("reason", "") or comps.get("fit_reason", ""),
        subscores=comps.get("subscores", {}),
        flags=comps.get("flags", []),
        icp=comps.get("icp"),
        trigger_line=comps.get("trigger_line", ""),
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


# --- scoring v2 — the label engine (docs/initial-build-plan.md §D+.2) ---------------------------
# The v2 rescore path: the free deterministic gates (rules → data → size) run FIRST; the paid
# web-grounded score call fires ONLY on a gate-survivor (spec §3 re-order — a rule-killed row is
# never web-checked). The Verdict is persisted to the v2 columns (`label`/`score_total`) +
# `fit_components`; the v1 `fit_*` columns are left untouched (expand → cutover → contract).


def _rules_config(brief: Brief | None, spec: ResearchSpec | None) -> labeling.RulesConfig:
    """The client's v2 `RulesConfig` (spec §5) — market from the brief, geographies from the spec's
    search HQ filter, excluded domains from the `excludeCustomers` set (decision ⑧-B: the client's
    'who to avoid' domains become the client-exclusion set — labeled `excluded_by_rules`, not
    dropped). Company rows are matched by domain, which the exclusion set carries reliably."""
    ex = _build_exclusions(brief, spec)
    return labeling.build_rules_config(
        brief.data if brief else {},
        spec.spec if spec else {},
        excluded_domains=tuple(ex.domains),
    )


def _company_det_inputs(c: Company) -> dict:
    """The deterministic `assign_label` inputs from a company row: the stage-0 classification (in
    `fit_components`: business_model / hq_country / has_b2b_line) + firmographics + the raw Apollo
    headcount. The caller adds the client-wide `config` + `size_ceiling`."""
    comps = c.fit_components or {}
    ev = c.evidence or {}
    return {
        "business_model": comps.get("business_model") or "Unknown",
        "has_b2b_line": bool(comps.get("has_b2b_line")),
        "hq_country": comps.get("hq_country") or "",
        "industry": c.industry,
        "website": c.website,
        "name": c.name,
        "domain": c.domain,
        "field_country": c.country,
        "headcount": ev.get("estimated_num_employees"),
    }


def _apply_company_verdict(
    c: Company, verdict: labeling.Verdict, *, signals: dict | None = None
) -> None:
    """Persist a v2 `Verdict` on a company row: `label`/`score_total` cols · reason→`fit_reason`
    · subscores/flags/icp/trigger_line/liveness→`fit_components`. `signals` present = the web score
    call ran (adds trigger_line + the liveness verdict). v1 `fit_*` untouched."""
    comps = dict(c.fit_components or {})
    comps["reason"] = verdict.reason
    comps["flags"] = verdict.flags
    comps["icp"] = verdict.icp
    if verdict.subscores is not None:
        comps["subscores"] = verdict.subscores
    if signals is not None:
        comps["trigger_line"] = signals.get("trigger_line", "")
        comps["liveness"] = signals.get("liveness", {})
    c.label = verdict.label
    c.score_total = verdict.score_total
    if verdict.reason:
        c.fit_reason = verdict.reason
    c.fit_components = comps


def _score_companies_v2(db: Session, tenant_id, rows: list[Company]) -> dict:
    """v2 rescore (spec §3): deterministic gates on every row → the paid web score on survivors →
    persist the `Verdict`. Records one `research_run` for cost; returns `{scored, failed, cost}`.
    Slow (web + reasoning) — async path only. Mirrors `_score_companies` wave mechanics."""
    brief, spec = _latest_brief(db, tenant_id), _latest_spec(db, tenant_id)
    rubric = _latest_doc(db, tenant_id, fit.COMPANY_SCORE_STAGE)
    rubric_body = rubric.body if rubric else ""
    config = _rules_config(brief, spec)
    ceiling = labeling.size_ceiling_from_spec(spec.spec if spec else {})
    # The scorer judges each row against the FULL ICP set and picks the ICP itself (`icp_match.icp`
    # = A / B / none — spec §7: one company pool, the model assigns the ICP). So targeting carries
    # EVERY ICP profile, NOT the row's find-time `icp_id`. Narrowing to one ICP was the wrong-
    # vertical bug: a professional-services firm sourced under ICP A never saw the ICP-B definition,
    # so the model called it "not insurtech → wrong vertical". Built once, client-wide, per row.
    all_icps = icp_docs(db, tenant_id)
    company_targeting = _build_targeting(brief, spec, all_icps, None)
    # Letter → ICP row id, so a row whose model-matched ICP differs from its find-time icp_id is
    # re-tagged to the matched ICP — Step-2 people-search then uses that ICP's personas (ICP B's
    # Founder/MD, not ICP A's Head of Growth/Sales). Only the score pass can re-tag: it is the one
    # place an ICP is judged. Built from the SAME `fit.icp_letter_map` the score schema's enum uses
    # (N6), so the letter the model emits is guaranteed to map back here.
    icp_by_letter = fit.icp_letter_map(all_icps)

    # Pass 1 — free deterministic gates. A caught row (excluded_by_rules / low_fit) is labeled now
    # and never web-checked; a survivor (label None) goes to the paid pass.
    survivors: list[Company] = []
    for c in rows:
        v = labeling.assign_label(config=config, size_ceiling=ceiling, **_company_det_inputs(c))
        if v.label is not None:
            _apply_company_verdict(c, v)
        else:
            survivors.append(c)

    # Pass 2 — the paid web-grounded liveness + score call, survivors only.
    jobs = [
        (
            c,
            (
                lambda payload=_company_payload(c), targeting=company_targeting: (
                    fit.company_score_v2(
                        tenant_id=tenant_id,
                        rubric_body=rubric_body,
                        company=payload,
                        targeting=targeting,
                    )
                )
            ),
        )
        for c in survivors
    ]
    cost = 0.0
    web_scored = 0
    for c, signals in _score_concurrently(jobs):
        if signals is None:
            continue
        v = labeling.assign_label(
            config=config,
            size_ceiling=ceiling,
            **_company_det_inputs(c),
            liveness=signals["liveness"],
            icp_match=signals["icp_match"],
            subscores=signals["subscores"],
            extra_flags=signals["flags"],
        )
        _apply_company_verdict(c, v, signals=signals)
        # Re-tag to the ICP the model matched (spec §7: the model assigns the ICP). A no-match
        # (`icp` None → wrong vertical) leaves the find-time tag untouched.
        matched = icp_by_letter.get((signals["icp_match"] or {}).get("icp"))
        if matched and str(matched) != str(c.icp_id):
            c.icp_id = uuid.UUID(matched) if isinstance(matched, str) else matched
        cost += float(signals.get("cost_usd") or 0.0)
        web_scored += 1

    db.add(
        ResearchRun(
            tenant_id=tenant_id,
            run_id=_apollo_run_id(),
            spec_version=spec.version if spec else None,
            source="rescore",
            # R28 — stamp the rubric prompt version ACTUALLY loaded for this run (founder-editable),
            # not the static code default, so the telemetry ties the run to the real prompt.
            rubric_version=(f"v{rubric.version}" if rubric else fit.SCORE_RUBRIC_VERSION),
            rows_pushed=len(rows),
            cost_usd=round(cost, 6),
        )
    )
    db.commit()
    # R20b — no per-row refresh: this worker returns only counts, so re-reading each row after the
    # commit was one wasted round-trip per row for values nobody reads.
    web_failed = len(survivors) - web_scored
    return {
        "scored": len(rows) - web_failed,  # gated rows + web successes both carry a label
        "failed": web_failed,
        "cost_usd": round(cost, 6),
    }


def _label_companies_deterministic(
    db: Session, tenant_id, rows: list[Company], *, brief: Brief | None = None, spec=None
) -> None:
    """Find-time v2 labeling (spec §3 free gates + ⑧-B). After stage-0 classify has stamped
    business_model / hq_country / has_b2b_line, run the deterministic ladder (rules → data → size)
    on each NEW row so `excluded_by_rules` / `low_fit` show immediately — no rescore click, no spend
    (no web call). A survivor (label None) stays "needs re-score" until the paid pass. Idempotent:
    the gate verdict is a pure function of the row + config. `brief`/`spec` are passed in when the
    caller already has them (the find path), else fetched."""
    if not rows:
        return
    brief = brief if brief is not None else _latest_brief(db, tenant_id)
    spec = spec if spec is not None else _latest_spec(db, tenant_id)
    config = _rules_config(brief, spec)
    ceiling = labeling.size_ceiling_from_spec(spec.spec if spec else {})
    for c in rows:
        v = labeling.assign_label(config=config, size_ceiling=ceiling, **_company_det_inputs(c))
        if v.label is not None:
            _apply_company_verdict(c, v)


def _prospect_v2_payload(enrichment: dict | None, company: Company | None) -> dict:
    """The person facts the v2 people scorer judges — decision-maker signals + the parent company's
    LABEL (not a fit score). The company label caps the person server-side; the model reads it only
    as context and does NOT re-judge the company. (Now identical to `_prospect_payload`, which since
    V2-4 carries `company_label`/`company_reason` directly; kept as the v2 call site's name.)"""
    return _prospect_payload(enrichment, company)


def _apply_prospect_verdict(p: Prospect, verdict: labeling.Verdict) -> None:
    """Persist a v2 people `Verdict`: `label`/`score_total` columns + reason/subscores/flags into
    `fit_components` (+ `fit_reason` parity)."""
    comps = dict(p.fit_components or {})
    comps["reason"] = verdict.reason
    comps["flags"] = verdict.flags
    if verdict.subscores is not None:
        comps["subscores"] = verdict.subscores
    p.label = verdict.label
    p.score_total = verdict.score_total
    if verdict.reason:
        p.fit_reason = verdict.reason
    p.fit_components = comps


def _score_prospects_v2(db: Session, tenant_id, rows: list[Prospect]) -> dict:
    """v2 people rescore: the company label caps each person (spec people-tier). Deterministic gates
    (parent-excluded / avoided title / missing title-or-contact) run free; survivors get the no-web
    people-axis score. Returns `{scored, failed, cost_usd}`."""
    brief, spec = _latest_brief(db, tenant_id), _latest_spec(db, tenant_id)
    rubric = _latest_doc(db, tenant_id, fit.PROSPECT_SCORE_STAGE)
    rubric_body = rubric.body if rubric else ""
    # avoidTitles are PER-ICP (ICP docs), keyed by icp id — mirrors find.filter_people (the people
    # find path), not the brief. A title avoided in one profile must not gate another.
    avoid_by_icp = {
        d["id"]: tuple(t for t in (d.get("avoidTitles") or []) if t)
        for d in icp_docs(db, tenant_id, None)
    }

    def _avoid_for(p: Prospect) -> tuple[str, ...]:
        return avoid_by_icp.get(str(p.icp_id), ()) if p.icp_id else ()

    company_ids = {p.company_id for p in rows if p.company_id}
    companies = (
        {
            c.id: c
            for c in db.execute(
                select(Company).where(Company.tenant_id == tenant_id, Company.id.in_(company_ids))
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
                brief, spec, icp_docs(db, tenant_id, icp_id), icp_id
            )
        return targeting_cache[key]

    def _det(p: Prospect) -> labeling.Verdict:
        e = p.enrichment or {}
        company = companies.get(p.company_id)
        return labeling.assign_person_label(
            company_label=company.label if company else None,
            title=e.get("title"),
            has_contact=bool(e.get("email")),
            avoid_titles=_avoid_for(p),
        )

    # Pass 1 — deterministic people gates.
    survivors: list[Prospect] = []
    for p in rows:
        # R2 — a row client-excluded at the post-enrich DNC gate stays excluded; never re-score it
        # into a contactable label (the enrich pass set label + this reason together).
        if p.label == labeling.EXCLUDED and (p.fit_components or {}).get(
            "reason"
        ) == labeling.REASON_RULE_EXCLUSION:
            continue
        v = _det(p)
        if v.label is not None:
            _apply_prospect_verdict(p, v)
        else:
            survivors.append(p)

    # Pass 2 — the no-web people-axis score on survivors.
    jobs = [
        (
            p,
            (
                lambda payload=_prospect_v2_payload(p.enrichment, companies.get(p.company_id)),
                targeting=_targeting_for(p.icp_id): fit.prospect_score_v2(
                    tenant_id=tenant_id,
                    rubric_body=rubric_body,
                    enrichment=payload,
                    targeting=targeting,
                )
            ),
        )
        for p in survivors
    ]
    cost = 0.0
    web_scored = 0
    for p, scored in _score_concurrently(jobs):
        if scored is None:
            continue
        company = companies.get(p.company_id)
        e = p.enrichment or {}
        v = labeling.assign_person_label(
            company_label=company.label if company else None,
            title=e.get("title"),
            has_contact=bool(e.get("email")),
            avoid_titles=_avoid_for(p),
            subscores=scored["subscores"],
            reason=scored["reason"],
            flags=scored["flags"],
        )
        _apply_prospect_verdict(p, v)
        cost += float(scored.get("cost_usd") or 0.0)
        web_scored += 1

    db.add(
        ResearchRun(
            tenant_id=tenant_id,
            run_id=_apollo_run_id(),
            spec_version=spec.version if spec else None,
            source="rescore",
            # R28 — stamp the rubric prompt version ACTUALLY loaded for this run (founder-editable),
            # not the static code default, so the telemetry ties the run to the real prompt.
            rubric_version=(f"v{rubric.version}" if rubric else fit.SCORE_RUBRIC_VERSION),
            rows_pushed=len(rows),
            cost_usd=round(cost, 6),
        )
    )
    db.commit()
    # R20b — no per-row refresh (returns only counts; the re-read was waste, mirrors companies).
    web_failed = len(survivors) - web_scored
    return {"scored": len(rows) - web_failed, "failed": web_failed, "cost_usd": round(cost, 6)}


# A full find can score up to MAX_*_PER_FIND rows; a *sequential* LLM call per row overruns the 30s
# API Gateway sync cap (→ 503). The LLM client is stdlib-urllib with its own telemetry session per
# call, so the calls are thread-safe — we fan them out, then apply each result on the main thread
# (ORM mutation stays single-threaded). The concurrency WAVE WIDTH — deliberately decoupled from the
# find-company row cap (D+ Stage 1a `FIND_COMPANY_LIMIT`) so widening the find never fans out an
# unbounded number of concurrent LLM calls. Sized to the sync rescore batch
# (`MAX_COMPANIES_PER_FIND`) so THAT path still scores in one reasoning wave. Env-tunable.
_SCORE_WORKERS = int(os.environ.get("HOLDSLOT_SCORE_WORKERS", str(MAX_COMPANIES_PER_FIND)))


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


def classify_companies(tenant_id, rows: list[Company], brief: Brief | None) -> float:
    """Stage-0 — stamp `business_model` (+ the description-derived `hq_country` and
    `has_b2b_line`) on every row that lacks one (idempotent, so a re-find never re-classifies) via a
    dedicated minimal LLM call. These three facts feed the v2 rules engine — the market/geo/Luma
    gates run in `_label_companies_deterministic` (called right after this in the find path), which
    stamps `excluded_by_rules` on an opposite-market row. Returns the total cost_usd for the run.

    One concurrent wave (the LLM client is thread-safe); the ORM mutation stays on the calling
    thread (results applied in the loop below). Does NOT commit — the caller owns the transaction. A
    per-row classify failure is absorbed (row kept unlabeled), never fatal.
    """
    todo = [c for c in rows if not (c.fit_components or {}).get("business_model")]
    jobs = [
        (
            c,
            (lambda payload=_classify_payload(c): fit.classify_business_model(
                tenant_id=tenant_id, company=payload
            )),
        )
        for c in todo
    ]
    cost = 0.0
    for c, res in _score_concurrently(jobs):
        if res is None:
            continue
        comps = dict(c.fit_components or {})
        # The three facts the v2 rules engine reads at label time (`_company_det_inputs`): the
        # B2B/B2C model + the description-derived HQ country (geo rule) + the B2B-line Luma guard.
        comps["business_model"] = res.get("business_model") or "Unknown"
        comps["hq_country"] = res.get("hq_country") or ""
        comps["has_b2b_line"] = bool(res.get("has_b2b_line"))
        c.fit_components = comps
        cost += float(res.get("cost_usd") or 0.0)
    return cost


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

    icp = uuid.UUID(body.icp_id) if body.icp_id else None

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


# --------------------------------------------------------------- Stage 1: Apollo Flow A (find)


def _apollo_run_id() -> str:
    return f"apollo-{uuid.uuid4().hex[:12]}"


def _enrich_survivors(survivors: list[dict]) -> None:
    """Enrich the surviving search rows via per-domain `organizations/enrich` — promote real
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


def _upsert_company(
    db: Session,
    tenant_id,
    parsed: dict,
    by_org: dict[str, Company],
    by_domain: dict[str, Company],
) -> Company:
    """Find-or-create a company by `apollo_org_id` (else `domain`); update identity fields in place.

    `by_org` / `by_domain` are the batch-preloaded existing rows (R20c — one `IN()` per key, not two
    point SELECTs per row); a row created here is registered back into them so a later survivor in
    the same batch reuses it (matching the old flush-then-reselect behaviour).

    Industry/size/country come from `organizations/enrich` (merged into `parsed` before this call
    for NEW rows only), so a non-null enrich value REFRESHES the stored one; a null never clobbers a
    real value. `apollo_org_id` is always (re)stamped and `evidence` is merged (new keys win).
    """
    org_id, domain = parsed.get("apollo_org_id"), parsed["domain"]
    company = (by_org.get(org_id) if org_id else None) or by_domain.get(domain)
    if company is None:
        company = Company(tenant_id=tenant_id, domain=domain, source="apollo")
        db.add(company)
        by_domain[domain] = company
    company.apollo_org_id = org_id or company.apollo_org_id
    if company.apollo_org_id:
        by_org[company.apollo_org_id] = company  # so a later same-org survivor reuses this row
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


def _find_company_core(db: Session, tenant_id, params: dict) -> FindResult:
    """Flow-A find from the latest spec (request body — `limit`, `icp_id`, and the optional
    `company_search_params` / `intent_filters` Settings overrides). Driven by the W4 async worker
    (`run_find_company`); the v1 sync twin was retired in V2-4. Rows land UNSCORED, capped at
    `FIND_COMPANY_LIMIT` (bounded by the Lambda timeout, not the 30s gateway).

    Multi-ICP (spec v4): the find is ICP-scoped — `icp_id` picks which ICP's targeting block runs.
    A single-block spec resolves without one (and the row still gets labeled from the block); a
    multi-block spec with no/unknown `icp_id` is a 400, never a silent merge."""
    spec = _latest_spec(db, tenant_id)
    blob = (spec.spec or {}) if spec else {}
    has_scope = bool(blob.get("icp_targeting") or blob.get("company_search_params"))
    if not has_scope:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "generate a research scope before finding companies"
        )
    icp = uuid.UUID(params["icp_id"]) if params.get("icp_id") else None
    block = targeting_for_icp(blob, icp)
    if block is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            (
                "this scope has per-ICP targeting — pick an ICP to find for"
                if icp is None
                else "no targeting for this ICP yet — regenerate the scope"
            ),
        )
    if icp is None and block.get("icp_id"):
        # Single-block spec found without an explicit ICP: adopt the block's own ICP so the rows
        # still land labeled ("" = brief-derived block stays unlabeled).
        try:
            icp = uuid.UUID(str(block["icp_id"]))
        except ValueError:
            icp = None
    ceiling = FIND_COMPANY_LIMIT
    credit = blob.get("credit_policy") or {}
    hard_cap = min(ceiling, credit.get("max_companies", 500))
    limit = max(1, min(params.get("limit") or ceiling, hard_cap))
    # Precedence: a per-call override in the request body (Settings modal) → the tenant's SAVED
    # per-ICP company override (persisted server-side, survives across browsers) → the AI spec.
    # `_clean` in apollo_map drops empty filters, so a cleared field simply widens the search.
    o_csp = params.get("company_search_params")
    o_intent = params.get("intent_filters")
    if o_csp is None and o_intent is None:
        saved = _scope_override_block(_scope_override_row(db, tenant_id, SCOPE_KIND_COMPANY), icp)
        if saved is not None:
            o_csp = saved.get("company_search_params")
            o_intent = saved.get("intent_filters")
    has_override = o_csp is not None or o_intent is not None
    csp = o_csp if o_csp is not None else (block.get("company_search_params") or {})
    intent = o_intent if o_intent is not None else (block.get("intent_filters") or {})
    filter_body = apollo_map.map_company_filter(csp, intent)
    # Conditional negative signal — only for the AI scope; a custom company override (per-call OR
    # saved) is the source of truth and left untouched. Stage 3: when bad rows cluster on one
    # country, drop it via `organization_not_locations`. Stage 4: resolve tech vocabulary → the two
    # Apollo tech UID filters (positive from the ICP's required stack, negative from bad-row tech).
    if not has_override:
        rows = _feedback_rows(db, tenant_id)
        # Never exclude a country the scope explicitly targets — a bad-row cluster on the SAME
        # country the AI is searching (e.g. a single-market client whose early rows all scored
        # Below) would AND `organization_not_locations` against `organization_locations` and zero
        # the search un-relaxably. Drop the contradiction (case-folded country match).
        locs = filter_body.get("organization_locations") or []
        targeted = {str(loc).strip().lower() for loc in locs}
        drop = feedback.cluster_exclusions(rows).get("organization_not_locations") or []
        drop = _drop_conflicts(drop, targeted, fold=True)
        filter_body = _merge_uids(filter_body, "organization_not_locations", drop)
        # D+ Stage 4 — positive tech: the scoped ICP's `technologies` → companies USING that stack.
        icp_tech = [t for d in icp_docs(db, tenant_id, icp) for t in (d.get("technologies") or [])]
        pos_tech = _resolve_tech(icp_tech)
        filter_body = _merge_uids(filter_body, "currently_using_any_of_technology_uids", pos_tech)
        # D+ Stage 4 — negative tech: stacks that correlated with bad rows → companies NOT using
        # them (clears the Stage-3 deferral; `negative_technologies` gives names, resolved here).
        # Drop any UID also required by the ICP — require+forbid the same stack zeroes the search.
        neg_tech = _drop_conflicts(
            _resolve_tech(feedback.negative_technologies(rows)), set(pos_tech)
        )
        filter_body = _merge_uids(
            filter_body, "currently_not_using_any_of_technology_uids", neg_tech
        )
    # `custom` only when the per-call OR saved override actually CONTRIBUTED a field (R28 — an empty
    # override present but resolved to nothing is an "ai" scope). `has_override` still gates the
    # feedback merge above (an override, even empty, is the source of truth there — untouched).
    scope_source = "custom" if (o_csp or o_intent) else "ai"
    return _run_company_find(
        db,
        tenant_id,
        spec,
        filter_body=filter_body,
        limit=limit,
        icp=icp,
        source="apollo",
        scope_source=scope_source,
        use_cursor=True,  # Stage 3 — repeat find resumes at the next page (never re-buys page 1)
        skip_known=True,  # Stage 3 — returning orgs are skipped ($0: no re-enrich/classify/stamp)
    )


# Feedback-derived NEGATIVE filters that flip as rows get scored (Stage 3 country exclusion, Stage 4
# negative tech). They must NOT key the page cursor: a re-run of the same scope would else churn the
# hash every rescore and re-buy page 1 (R4). Stripped before hashing; they still ride in the run's
# executed `filter_body` lineage.
_VOLATILE_SCOPE_KEYS = (
    "organization_not_locations",
    "currently_not_using_any_of_technology_uids",
)


def _body_hash(filter_body: dict) -> str:
    """Stable short hash of the SCOPE — the page-cursor key (D+ Stage 3). Only the stable scope keys
    are hashed: the volatile feedback negatives (`_VOLATILE_SCOPE_KEYS`) are dropped here, and the
    caller passes the PRE-relax body so the live relax rung is excluded too. So an identical scope
    re-run resolves to the same hash and resumes at the next page; a genuine scope change (incl. an
    ICP-tech edit) changes the hash and resets to page 1."""
    stable = {k: v for k, v in filter_body.items() if k not in _VOLATILE_SCOPE_KEYS}
    blob = json.dumps(stable, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# --------------------------------------------------------------------- D+ Stage 3 · page cursor
# Apollo has no exclude-by-id, so a repeat find with an unchanged scope would re-buy page 1 forever.
# The cursor recycles that: each run records the last page it reached (`page_cursor` in the run),
# and the next run of the SAME resolved body (matched by `body_hash`) resumes at the next page. A
# changed scope has a different hash → no prior cursor → starts at page 1 (reset is inherent). When
# the cursor reaches `total_pages` the scope is exhausted → the "regenerate" signal.
_CURSOR_SCAN_LIMIT = 50  # tenant's recent runs scanned to find this scope's cursor (small N)
# R22b — only company-find runs carry a page `body_hash`; scoping the scan to these sources keeps
# the high-frequency rescore/enrich runs (one per scoring pass) from evicting a find cursor out of
# the latest-N window. (`apollo` = company find, `lookalike` = lookalike find; the Python body_hash
# match below still skips people-find `apollo` runs, which never carry a cursor.)
_CURSOR_FIND_SOURCES = ("apollo", "lookalike")


def _cursor_decision(prior_meta: dict | None) -> tuple[int, bool]:
    """(resume_page, prior_exhausted) from the latest same-scope run's result_meta. No prior → page
    1. A prior run flagged `scope_exhausted` → the full set was already walked (caller
    short-circuits). A prior `page_cursor` → resume at the next page so page 1 is never re-bought.
    """
    if not prior_meta:
        return 1, False
    per_page = prior_meta.get("per_page")
    # R1: the cursor's page numbers are denominated in a page SIZE. A cursor recorded under a
    # DIFFERENT (non-None) page size is stale — its page numbers don't map to the current width, so
    # discard the whole meta (page AND exhaustion) and restart at page 1. `_paginate` always fetches
    # `PER_PAGE_MAX`-wide pages now, so this only trips if that knob is ever changed.
    if per_page is not None and per_page != apollo.PER_PAGE_MAX:
        return 1, False
    # N5 — honor exhaustion BEFORE treating a missing per_page as legacy. An exhausted-scope
    # short-circuit historically stored no page size (per_page None); ordering the size guard ahead
    # of this made a walked-to-exhaustion scope look legacy → it re-bought page 1 every other find
    # instead of short-circuiting. (New runs also carry per_page forward now — belt and braces.)
    if prior_meta.get("scope_exhausted"):
        return 1, True
    # A missing per_page with no exhaustion flag is a pre-R1 cursor whose page can't be trusted.
    if per_page != apollo.PER_PAGE_MAX:
        return 1, False
    cursor = prior_meta.get("page_cursor")
    if isinstance(cursor, int) and cursor >= 1:
        return cursor + 1, False
    return 1, False


def _resume_page(db: Session, tenant_id, body_hash: str) -> tuple[int, bool, dict | None]:
    """DB-side of the page cursor: the most-recent run for THIS exact resolved scope (matched by
    `result_meta.body_hash`) decides where to resume. Scanned in Python over the tenant's recent
    runs (small N) so it stays dialect-agnostic — no JSONB `->>` on the RDS Data API path. Returns
    `(resume_page, prior_exhausted, prior_meta)`; the matched meta lets an exhausted short-circuit
    carry the walked scope's cursor forward (N5)."""
    recent = (
        db.execute(
            select(ResearchRun.result_meta)
            .where(
                ResearchRun.tenant_id == tenant_id,
                ResearchRun.source.in_(_CURSOR_FIND_SOURCES),  # R22b — skip rescore/enrich runs
            )
            .order_by(ResearchRun.created_at.desc())
            .limit(_CURSOR_SCAN_LIMIT)
        )
        .scalars()
        .all()
    )
    for meta in recent:
        if (meta or {}).get("body_hash") == body_hash:
            resume_page, prior_exhausted = _cursor_decision(meta)
            return resume_page, prior_exhausted, meta
    return 1, False, None


# --------------------------------------------------------------------- D+ Stage 1b · relax ladder
# A thin/empty company search auto-widens one deterministic rung at a time so a find never dead-ends
# on an over-narrow AI scope. The ladder is pure (no I/O) + terminal (≤3 rungs) so its ordering is
# unit-tested without Apollo. `_resolve_company_scope` drives it, probing `total_entries` per rung
# (FREE — `count_companies`, per_page=1), stopping at the first rung that clears FIND_RELAX_MIN.


def _widen_employee_ranges(ranges: list[str]) -> list[str]:
    """Proportionally widen each Apollo `"lo,hi"` employee range — halve the floor (≥1), double the
    ceiling — so the size band keeps its center but admits neighbours. Deterministic; a malformed
    entry is passed through untouched."""
    out: list[str] = []
    for r in ranges:
        try:
            lo_s, hi_s = str(r).split(",", 1)
            lo, hi = int(lo_s), int(hi_s)
        except (ValueError, AttributeError):
            out.append(r)
            continue
        out.append(f"{max(1, lo // 2)},{hi * 2}")
    return out


def _weakest_keyword(tags: list[str]) -> str:
    """The 'weakest' keyword to drop first: the longest tag — the most specific phrase narrows the
    match hardest. Deterministic — ties break on the later position in the list."""
    weakest_i = max(range(len(tags)), key=lambda i: (len(tags[i]), i))
    return tags[weakest_i]


def _company_relax_ladder(filter_body: dict):
    """Yield `(step_label, relaxed_body)` rungs for a thin search — deterministic, cumulative (each
    rung further relaxes the previous), terminal (≤3 rungs): drop `revenue_range` → widen the
    employee ranges → drop the weakest keyword tag. A rung with nothing to change is skipped, so
    every yielded rung is a genuine widening (never a no-op re-probe).
    """
    cur = dict(filter_body)
    if "revenue_range" in cur:
        cur = {k: v for k, v in cur.items() if k != "revenue_range"}
        yield "drop_revenue_range", cur
    ranges = cur.get("organization_num_employees_ranges")
    if ranges:
        widened = _widen_employee_ranges(ranges)
        if widened != ranges:
            cur = {**cur, "organization_num_employees_ranges": widened}
            yield "widen_size", cur
    tags = cur.get("q_organization_keyword_tags")
    if tags:
        weakest = _weakest_keyword(tags)
        remaining = [t for t in tags if t != weakest]
        if remaining:
            cur = {**cur, "q_organization_keyword_tags": remaining}
        else:
            cur = {k: v for k, v in cur.items() if k != "q_organization_keyword_tags"}
        yield f"drop_keyword:{weakest}", cur


def _resolve_company_scope(filter_body: dict) -> tuple[dict, int, list[str], int]:
    """Fetch-page-1-then-assess relax loop (D+ Stage 1b). Probe `total_entries` (FREE, per_page=1)
    on the executed body; while it's under FIND_RELAX_MIN, widen one rung and re-probe. Returns
    `(resolved_body, relax_level, relax_steps, total_entries)`; level 0 means the scope already had
    enough breadth. A probe failure never blocks the find (the real fetch surfaces any hard Apollo
    error): the loop stops and the caller runs the current body.
    """
    resolved = filter_body
    try:
        total = apollo.count_companies(resolved)
    except apollo.ApolloError:
        return resolved, 0, [], 0
    if total >= FIND_RELAX_MIN:
        return resolved, 0, [], total
    steps: list[str] = []
    for label, body in _company_relax_ladder(filter_body):
        try:
            t = apollo.count_companies(body)
        except apollo.ApolloError:
            break
        resolved, total = body, t
        steps.append(label)
        if total >= FIND_RELAX_MIN:
            break
    return resolved, len(steps), steps, total


# D+ Stage 2 — APAC broadening. Apollo's revenue coverage is sparse in APAC, so a `revenue_range`
# filter silently zeroes otherwise-valid orgs there; for an APAC-located scope we drop revenue up
# front, not waiting for the thin-relax ladder to reach it. Country match is comma-token exact (so
# "kowloon, hong kong" trips on "hong kong", but no substring hits like "china" in "indochina").
_APAC_LOCATIONS = frozenset(
    {
        "hong kong", "singapore", "japan", "china", "south korea", "korea", "taiwan",
        "india", "indonesia", "malaysia", "thailand", "vietnam", "philippines", "australia",
        "new zealand", "pakistan", "bangladesh", "sri lanka", "cambodia", "myanmar", "laos",
        "brunei", "mongolia", "macau", "macao", "nepal",
    }
)
# Major APAC CITIES — so a city-only scope ("Sydney", "Tokyo") that carries NO country segment is
# still caught (R29d). Kept to unambiguous metros to avoid a same-name collision with a non-APAC
# place; a "City, Country" scope already trips on its country token above.
_APAC_CITIES = frozenset(
    {
        "sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra",
        "auckland", "wellington", "christchurch",
        "tokyo", "osaka", "yokohama", "nagoya", "fukuoka",
        "seoul", "busan", "taipei", "kaohsiung",
        "shanghai", "beijing", "shenzhen", "guangzhou", "hangzhou", "chengdu",
        "mumbai", "bengaluru", "bangalore", "hyderabad", "chennai", "pune", "kolkata",
        "jakarta", "surabaya", "bandung", "manila", "cebu",
        "bangkok", "hanoi", "ho chi minh city", "kuala lumpur",
        "colombo", "dhaka", "karachi", "lahore", "islamabad", "kathmandu", "phnom penh", "yangon",
    }
)


def _is_apac(locations) -> bool:
    """True if any Apollo location names an APAC country OR a major APAC city (case-insensitive,
    comma-token match). The city set catches a city-only scope like "Sydney" with no country segment
    (R29d); a "City, Country" scope still trips on its country token."""
    for loc in locations or []:
        for token in str(loc).lower().split(","):
            t = token.strip()
            if t in _APAC_LOCATIONS or t in _APAC_CITIES:
                return True
    return False


def _run_company_find(
    db: Session,
    tenant_id,
    spec: ResearchSpec | None,
    *,
    filter_body: dict,
    limit: int,
    icp: uuid.UUID | None,
    source: str,
    scope_source: str | None = None,
    seen_domains: set[str] | None = None,
    use_cursor: bool = False,
    skip_known: bool = False,
) -> FindResult:
    """The Flow-A tail shared by find-company and find-lookalikes: Apollo search → suppress + dedupe
    → enrich NEW survivors → upsert + stage-0 classify + deterministic label → one `research_run`.

    `filter_body` is already Apollo-shaped (the caller builds it from the spec or from seed rows);
    `source` tags the run (`apollo` vs `lookalike`) so the cost scoreboard separates the two doors.
    `spec` may be None (lookalike needs no spec); its version/prompt stamp the run only when set.
    `seen_domains` are domains to DROP from the result (Lookalike passes the tenant's existing
    domains so the seeds + already-listed peers fall out and only NET-NEW companies come back).
    NEW rows land UNSCORED (v2: `label` NULL) — the paid web-grounded score is a separate on-demand
    async pass (`run_rescore_companies` → `_score_companies_v2`); find never scores inline.

    D+ Stage 3: `use_cursor` resumes an unchanged scope at its stored page cursor (find-company), so
    a repeat find advances instead of re-buying page 1; `skip_known` drops orgs already stored for
    the tenant BEFORE enrich/classify/upsert so a returning row costs $0 (never re-enriched, never
    re-classified, never re-stamped) and the find returns only NET-NEW rows. Latency is logged.
    """
    t0 = time.monotonic()
    # D+ Stage 2 — APAC broadening: Apollo's revenue coverage is sparse across APAC, so a
    # `revenue_range` filter silently zeroes otherwise-valid orgs there. For an APAC-located scope
    # we drop revenue up front (before the thin-relax ladder would reach it) so the search sees the
    # full APAC population, not just the few orgs Apollo happens to hold revenue for. Recorded in
    # result_meta.apac for the drawer/telemetry.
    apac = _is_apac(filter_body.get("organization_locations"))
    if apac and "revenue_range" in filter_body:
        filter_body = {k: v for k, v in filter_body.items() if k != "revenue_range"}
    # D+ Stage 1b — fetch-page-1-then-assess relax ladder: widen a thin/empty scope one rung at a
    # time so a find never dead-ends on an over-narrow AI scope (KPI: <10% zero-result finds). The
    # probes are FREE (per_page=1); `resolved_body` is what actually executes (and the run stores it
    # as override-proof lineage); `relax_level`/`relax_steps` record how far it widened.
    resolved_body, relax_level, relax_steps, _ = _resolve_company_scope(filter_body)
    t_relax = time.monotonic() - t0
    # D+ Stage 3 — page cursor: an unchanged scope resumes at the page after the last one fetched,
    # so a repeat find advances instead of re-buying page 1. A scope already walked to exhaustion
    # short-circuits (no re-buy) and just re-flags "regenerate".
    # R4 — key the cursor on the PRE-relax body (relax rung excluded), with feedback negatives
    # stripped inside `_body_hash`; a repeat find of the same scope keeps the cursor instead of
    # re-buying page 1 the moment feedback or the relax rung shifts. `resolved_body` (post-relax,
    # feedback) is still stored as the executed lineage on the run.
    body_hash = _body_hash(filter_body)
    resume_page, prior_exhausted, prior_meta = (
        _resume_page(db, tenant_id, body_hash) if use_cursor else (1, False, None)
    )
    if prior_exhausted:
        # N5 — carry the exhausted scope's cursor forward so the new run's lineage stays well-formed
        # (a valid per_page + page_cursor), not a bare {scope_exhausted} whose per_page=None reads
        # as "unknown page size". Belt-and-braces with the reordered `_cursor_decision`: even if the
        # exhaustion flag were ever missed, a valid per_page keeps the cursor from re-buying page 1.
        pm = prior_meta or {}
        rows, cache_hit = [], False
        search_meta = {
            "scope_exhausted": True,
            "per_page": pm.get("per_page") or apollo.PER_PAGE_MAX,
            "end_page": pm.get("page_cursor"),
            "total_pages": pm.get("total_pages"),
            "total_entries": pm.get("total_entries"),
        }
    else:
        # W8 — serve a recent identical page from the warm-container cache so a re-run of the same
        # scope+page inside the TTL avoids the round-trip. `search_companies_meta` returns rows AND
        # the first-fetched-page meta (`total_entries`/`breadcrumbs`/`total_pages`/`end_page`) for
        # D+ scope lineage, off the same call (no extra request); the tuple is cached together.
        search_key = json.dumps([resolved_body, limit, resume_page], sort_keys=True, default=str)
        cached = _COMPANY_SEARCH_CACHE.get(search_key)
        cache_hit = cached is not None
        if cache_hit:
            rows, search_meta = cached
        else:
            try:
                rows, search_meta = apollo.search_companies_meta(
                    resolved_body, max_results=limit, start_page=resume_page
                )
            except apollo.ApolloError as e:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY, f"apollo company search failed: {e}"
                ) from e
            _COMPANY_SEARCH_CACHE.set(search_key, (rows, search_meta))
    t_search = time.monotonic() - t0 - t_relax

    parsed = [apollo_map.parse_company(r) for r in rows]
    # Dedupe within this batch + drop `seen_domains` (Lookalike passes the tenant domains, so seeds
    # + already-listed peers drop here and `found` reflects only new companies).
    survivors, dropped = find.filter_companies(
        parsed, _exclusions(db, tenant_id), seen_domains=seen_domains
    )
    # D+ Stage 3 — known-org skip ($0 invariant): drop orgs already stored for this tenant (by
    # domain OR apollo_org_id) BEFORE enrich/classify/upsert, so a returning row is never
    # re-enriched, re-classified, or re-stamped — it stays pinned + labelled as-is. This is the
    # page-overlap safety net (Apollo ordering can drift) that makes a repeat find return only NEW.
    # Companies new to this tenant (by domain OR apollo_org_id), computed ONCE. Enrich only these —
    # an existing row would re-enrich to the same firmographics and burn an Apollo credit (the
    # 'Update Field' button is the deliberate refresh path). Stage 3 `skip_known` also DROPS the
    # returning orgs from the batch so a repeat find returns only NET-NEW rows at $0.
    new_survivors = _new_survivors(db, tenant_id, survivors)
    known_skipped = 0
    if skip_known:
        known_skipped = len(survivors) - len(new_survivors)
        survivors = new_survivors
    _enrich_survivors(new_survivors)
    t_enrich = time.monotonic() - t0 - t_search

    run_id = _apollo_run_id()
    brief = _latest_brief(db, tenant_id)
    cost = 0.0
    companies: list[Company] = []
    # R20c — batch-preload the survivors' existing rows (one IN() per key) instead of two point
    # SELECTs per row inside the loop; `_upsert_company` reads/updates these maps in memory.
    domains = {p["domain"] for p in survivors if p.get("domain")}
    org_ids = {p["apollo_org_id"] for p in survivors if p.get("apollo_org_id")}
    existing = (
        db.execute(
            select(Company).where(
                Company.tenant_id == tenant_id,
                or_(Company.domain.in_(domains), Company.apollo_org_id.in_(org_ids)),
            )
        )
        .scalars()
        .all()
        if (domains or org_ids)
        else []
    )
    by_domain = {c.domain: c for c in existing}
    by_org = {c.apollo_org_id: c for c in existing if c.apollo_org_id}
    for p in survivors:
        c = _upsert_company(db, tenant_id, p, by_org, by_domain)
        c.run_id, c.icp_id = run_id, icp or c.icp_id
        companies.append(c)

    # Stage-0: classify the business model of every NEW row up-front (a dedicated minimal LLM call)
    # so the B2B/B2C label — and the market gate — is present BEFORE any scoring.
    cost += classify_companies(tenant_id, companies, brief)
    # Scoring v2 (spec §3 + ⑧-B): stamp the free deterministic label (rules/data/size) at find time
    # so excluded_by_rules / low_fit — incl. the kept client-excluded rows — show without a rescore.
    # A survivor (label NULL) lands UNSCORED — the paid web-grounded score is a separate on-demand
    # async pass (run_rescore_companies → _score_companies_v2); find never scores inline (v2).
    _label_companies_deterministic(db, tenant_id, companies, brief=brief, spec=spec)
    t_total = time.monotonic() - t0
    log.info(
        "company-find[%s]: apollo=%d relax=%.1fs(L%d%s) search=%.1fs%s survivors=%d enrich=%.1fs "
        "total=%.1fs%s",
        source,
        len(rows),
        t_relax,
        relax_level,
        ":" + ">".join(relax_steps) if relax_steps else "",
        t_search,
        " (cached)" if cache_hit else "",
        len(survivors),
        t_enrich,
        t_total,
        " ⚠OVER-30s-GATEWAY-CAP" if t_total > 28 else "",
    )

    spec_blob = spec.spec if spec else {}
    total_entries = search_meta.get("total_entries")
    # D+ Stage 3 — exhaustion: the cursor reached the last page of this scope's result set (or a
    # prior run already had). Terminal signal for the "scope exhausted → regenerate" notice; a
    # changed scope (new body_hash) resets it. `page_cursor` = last page fetched (the resume key).
    end_page = search_meta.get("end_page")
    total_pages = search_meta.get("total_pages")
    scope_exhausted = bool(
        prior_exhausted
        or (end_page is not None and total_pages is not None and end_page >= total_pages)
    )
    # D+ Stage 1 — snapshot the EXECUTED body + the search-response signal (override-proof lineage).
    # Stage 1b adds the relax trail + the over-broad flag; Stage 3 adds the page cursor
    # (`page_cursor`/`resume_page`/`total_pages`) + `scope_exhausted` + `known_skipped`.
    result_meta = {
        "total_entries": total_entries,
        "breadcrumbs": search_meta.get("breadcrumbs") or [],
        "pages_fetched": search_meta.get("pages_fetched"),
        "relax_level": relax_level,
        "relax_steps": relax_steps,
        "over_broad": (total_entries or 0) > FIND_OVER_BROAD,
        "apac": apac,  # Stage 2 — APAC scope, so revenue_range was dropped up front
        "body_hash": body_hash,  # the page-cursor key (Stage 3)
        "resume_page": resume_page,  # page this run started at (Stage 3)
        "page_cursor": end_page,  # last page reached → next run resumes at +1 (Stage 3)
        "per_page": search_meta.get("per_page"),  # page SIZE the cursor is denominated in (R1)
        "total_pages": total_pages,
        "scope_exhausted": scope_exhausted,
        "known_skipped": known_skipped,
        "cache_hit": cache_hit,
    }
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
            rubric_version=fit.SCORE_RUBRIC_VERSION,
            rows_pushed=len(companies),
            cost_usd=round(cost, 6),
            filter_body=resolved_body,
            scope_source=scope_source,
            result_meta=result_meta,
        )
    )
    db.commit()
    for c in companies:
        db.refresh(c)
    companies.sort(key=lambda c: (c.score_total is None, -(c.score_total or 0)))
    return FindResult(
        run_id=run_id,
        found=len(companies),
        dropped=len(dropped) + known_skipped,
        companies=[_company_out(c) for c in companies],
        scope_exhausted=scope_exhausted,
        known_skipped=known_skipped,
    )


def _lookalike_core(db: Session, tenant_id, params: dict) -> FindResult:
    """Lookalike find from the seed `company_ids` (+ optional `icp_id`). Shared by the sync
    `/companies/find-lookalikes` endpoint and the W4 async worker. Aggregates the seeds'
    firmographics into a company-search filter, drops the tenant's existing domains, and runs the
    Flow-A tail UNSCORED (`score=False`)."""
    ids = _parse_ids(params.get("company_ids") or [])
    seeds = (
        db.execute(select(Company).where(Company.tenant_id == tenant_id, Company.id.in_(ids)))
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
    if params.get("icp_id"):
        icp = uuid.UUID(params["icp_id"])
    else:
        seed_icps = {c.icp_id for c in seeds}
        icp = next(iter(seed_icps)) if len(seed_icps) == 1 else None

    # Drop every company already in this tenant (seeds included) so Lookalike returns net-new peers.
    seen_domains = set(
        db.execute(
            select(Company.domain).where(
                Company.tenant_id == tenant_id, Company.domain.is_not(None)
            )
        ).scalars()
    )
    spec = _latest_spec(db, tenant_id)
    return _run_company_find(
        db,
        tenant_id,
        spec,
        filter_body=filter_body,
        limit=LOOKALIKE_LIMIT,
        icp=icp,
        source="lookalike",
        scope_source="lookalike",
        seen_domains=seen_domains,
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
    rubric = _latest_doc(db, tenant_id, fit.COMPANY_SCORE_STAGE)
    rubric_body = rubric.body if rubric else ""
    # Mirror live company scoring: the FULL ICP set (the model picks A / B / none), not the row's
    # find-time icp_id — so the modal shows exactly the context the scorer receives.
    targeting = _build_targeting(brief, spec, icp_docs(db, tenant_id), None)
    payload = _company_payload(company) if company else {}
    msgs = fit.build_company_score_v2_messages(rubric_body, payload, targeting)
    by_role = {m["role"]: m["content"] for m in msgs}
    return FitPromptOut(
        system=by_role.get("system", ""),
        user=by_role.get("user", ""),
        company=(company.name or company.domain) if company else None,
        model=list(fit.SCORE_MODELS),
        purpose=fit.COMPANY_SCORE_PURPOSE,
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
    rubric = _latest_doc(db, tenant_id, fit.PROSPECT_SCORE_STAGE)
    rubric_body = rubric.body if rubric else ""
    icp_id = prospect.icp_id if prospect else None
    targeting = _build_targeting(brief, spec, icp_docs(db, tenant_id, icp_id), icp_id)
    payload = _prospect_payload(prospect.enrichment, company) if prospect else {}
    by_role = {
        m["role"]: m["content"]
        for m in fit.build_prospect_score_v2_messages(rubric_body, payload, targeting)
    }
    # R7 — the whole deref must be inside the guard: a fresh tenant with zero prospects hit
    # `prospect.enrichment` here (only the second access was guarded) → 500 AttributeError.
    sample = None
    if prospect:
        e = prospect.enrichment or {}
        sample = e.get("full_name") or e.get("company")
    return FitPromptOut(
        system=by_role.get("system", ""),
        user=by_role.get("user", ""),
        company=sample or None,
        model=list(fit.SCORE_MODELS),
        purpose=fit.PROSPECT_SCORE_PURPOSE,
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
        kind=job.kind,
        status=job.status,
        result=job.result or {},
        error=job.error,
    )


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
    try:
        jid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid job id") from exc
    job = scoring.job_by_id(db, ctx.tenant.id, jid)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such job")
    return _scoring_job_out(job)


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
                icp_id=str(r.icp_id) if r.icp_id else None,
                scope_source=r.scope_source,
                filter_body=r.filter_body,
                result_meta=r.result_meta,
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


# --------------------------------------------------------------- Stage 2: Apollo Flow B (find)

# Auto-relax order (D+ Stage 2 — "Query = rubric"): `person_titles` is the precise, rubric-aligned
# persona lever (the fit rubric scores a 14-pt title dimension), so the ladder queries titles FIRST
# — strict (include_similar_titles=false) then fuzzy (=true) — before dropping to Apollo's two
# native facets: seniority×department (both AND'd), then seniority alone. Apollo AND's the facets,
# so a strict combo can be empty at a small org even when each facet alone has people (Luma); the
# descent guarantees suitable people still surface, but never widens all the way to org-only
# (that would dump interns/irrelevant roles, defeating "suitable"). No-op rungs (params that lack
# the lever) are skipped, so the ladder is exactly the rungs the spec can actually express.
def _people_ladder(people_params: dict) -> list[tuple[dict, str]]:
    """The ordered (params, level) rungs for one org's people search — titles first, facets as the
    fallback. Deterministic + terminal; skips rungs the params can't fill."""
    titles = people_params.get("person_titles") or []
    sen = people_params.get("person_seniorities") or []
    dep = people_params.get("person_department_or_subdepartments") or []
    rungs: list[tuple[dict, str]] = []
    if titles:
        rungs.append(({**people_params, "include_similar_titles": False}, "titles_strict"))
        rungs.append(({**people_params, "include_similar_titles": True}, "titles_fuzzy"))
    # Facet rungs drop titles so a stale title match doesn't AND against the facet fallback.
    facet_base = {**people_params, "person_titles": []}
    if sen and dep:
        rungs.append((facet_base, "seniority_dept"))
    if sen:
        rungs.append(({**facet_base, "person_department_or_subdepartments": []}, "seniority_only"))
    return rungs or [(people_params, "as_is")]


def _search_people_relaxed(
    people_params: dict, org_id: str, per_company: int
) -> tuple[list[dict], dict, str]:
    """Search one org, descending the persona ladder until people appear → (rows, body_sent, level).

    `level` is a short diagnostic tag: titles_strict / titles_fuzzy (person_titles, exact then
    similar), seniority_dept / seniority_only (facet fallback), or "as_is" (the spec carried no
    persona lever, so nothing to relax)."""
    last_body: dict = {}
    level = "as_is"
    for params, level in _people_ladder(people_params):
        last_body = apollo_map.map_people_filter(params, org_id=org_id)
        rows = apollo.search_people(last_body, max_results=per_company)
        if rows:
            return rows, last_body, level
    return [], last_body, level


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
    call_icp = uuid.UUID(body.icp_id) if body.icp_id else None
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
            source="apollo",
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
    return _SENIORITY_LABELS.get(value) or _humanize(value)


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


def _enrich_prospects(db: Session, rows: list[Prospect], slug: str) -> dict:
    """Apollo `people/match` on `rows` — reveal a verified email (the only credit spend) and write
    it back, moving the row to `scored`. The reveal step of the async reveal-&-score worker
    (`run_enrich_score_prospects`); the caller owns loading + the per-request cap. (The sync
    `/prospects/enrich` twin was retired in D+.5/R10 — the async door is the only reveal path now.)

    **Idempotent + concurrent (the credit-safety contract):** `last_enriched_at` gates a re-spend,
    so a row already matched (even one Apollo returned no email for) is confirmed without a second
    charge; a manual row (no `apollo_person_id`) is confirmed without a match call. The match calls
    fan out on a thread pool (HTTP-only; ORM writes stay single-threaded), then results are applied
    and **committed per row** (R10): the `last_enriched_at` stamp lands when a credit is spent,
    so a concurrent door or a re-run skips that row — a crash mid-batch can't re-charge the rows
    already revealed. A per-row Apollo error counts in `failed` (row → `enrich_failed`); the spend
    counts are always returned. Returns `{confirmed, enriched, credits_spent, failed}`.
    """
    # R2 — post-enrich do-not-contact set (loaded once per batch). Apollo search obfuscates
    # email/linkedin, so a client-excluded PERSON can only be caught here, after reveal (find.py's
    # docstring promises this). Company-domain exclusion already ran at find time (Flow A).
    exclusions = _exclusions(db, rows[0].tenant_id) if rows else None

    # Partition: rows that need a paid match call vs rows that confirm without spending (manual rows
    # with no apollo_person_id, or rows already enriched).
    to_match: list[Prospect] = []
    for p in rows:
        # Credit-safety gate (idempotency): `last_enriched_at` is stamped on every completed
        # Apollo match, even one that charged a credit but returned no verified email. Gate on
        # it so a re-submit never re-charges such a row. (Gating on email presence alone silently
        # re-spent a credit on every matched-but-no-email row when the founder re-clicked Enrich.)
        already_enriched = p.last_enriched_at is not None or bool(
            p.email_valid or (p.enrichment or {}).get("email")
        )
        if not p.apollo_person_id or already_enriched:
            if p.status == "found":
                p.status = "confirmed"
            continue
        to_match.append(p)
    db.commit()  # R10 — persist the no-spend confirmations (covers the all-manual/all-cached case)

    # Fan out the slow Apollo match calls concurrently (HTTP-bound, thread-safe); collect results
    # before touching the ORM so DB writes stay single-threaded.
    matched_by_pid: dict[str, dict | Exception] = {}
    if to_match:
        with ThreadPoolExecutor(max_workers=min(_ENRICH_WORKERS, len(to_match))) as ex:
            futs = {
                ex.submit(
                    apollo.match_person, p.apollo_person_id, reveal_email=True, reveal_phone=False
                ): p
                for p in to_match
            }
            for fut in as_completed(futs):
                p = futs[fut]
                try:
                    matched_by_pid[p.apollo_person_id] = fut.result()
                except apollo.ApolloError as exc:  # counted as `failed`, never a lost-spend 502
                    matched_by_pid[p.apollo_person_id] = exc

    enriched = credits = failed = 0
    for p in to_match:
        res = matched_by_pid.get(p.apollo_person_id)
        if isinstance(res, Exception):
            log.warning("enrich[%s]: match errored person=%s: %s", slug, p.apollo_person_id, res)
            p.status = "enrich_failed"
            failed += 1
            db.commit()  # R10 — per-row
            continue
        matched = apollo_map.parse_match(res)
        if not matched.get("apollo_person_id"):
            log.warning("enrich[%s]: no apollo match person=%s", slug, p.apollo_person_id)
            p.status = "enrich_failed"  # Apollo had no match; distinct so it won't sit as "pending"
            failed += 1
            db.commit()  # R10 — per-row
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
        # R2 — do-not-contact on the just-revealed contact. The credit was already counted (spent
        # honestly), but a DNC hit is labeled `excluded_by_rules` and never becomes batchable. The
        # score pass that follows (run_enrich_score_prospects) leaves this label intact — it skips
        # rows already client-excluded here.
        revealed_email = matched.get("email") or ""
        if exclusions is not None and exclusions.blocks(
            Candidate(
                email=revealed_email,
                linkedin_url=matched.get("linkedin_url") or "",
                domain=revealed_email.split("@", 1)[1] if "@" in revealed_email else "",
            )
        ):
            _apply_prospect_verdict(
                p,
                labeling.Verdict(label=labeling.EXCLUDED, reason=labeling.REASON_RULE_EXCLUSION),
            )
        db.commit()  # R10 — per-row: the last_enriched_at stamp lands NOW, so a concurrent door or
        # a re-run skips this already-charged row (no double-spend); bounds a crash to one row.
    # Credit-spend audit trail (the only place HoldSlot spends an Apollo credit).
    log.info(
        "enrich[%s]: rows=%d to_match=%d enriched=%d credits=%d failed=%d",
        slug,
        len(rows),
        len(to_match),
        enriched,
        credits,
        failed,
    )
    return {
        "confirmed": len(rows),
        "enriched": enriched,
        "credits_spent": credits,
        "failed": failed,
    }
