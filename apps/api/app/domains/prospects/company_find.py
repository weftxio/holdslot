"""Stage-1 Apollo Flow-A company find pipeline — scope resolution + relax ladder + page cursor,
the search cache, enrich/upsert, and the fit-prompt previews."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.domains.briefs.research_spec import (
    targeting_for_icp,
)
from app.domains.icps import icp_docs
from app.domains.prospects import (
    apollo_map,
    feedback,
    find,
    fit,
    lookalike,
)
from app.domains.prospects.label_engine import _label_companies_deterministic, classify_companies
from app.domains.prospects.schemas import (
    FindResult,
    FitPromptOut,
)
from app.domains.prospects.scope import (
    SCOPE_KIND_COMPANY,
    _apollo_run_id,
    _build_targeting,
    _drop_conflicts,
    _exclusions,
    _feedback_rows,
    _latest_brief,
    _latest_doc,
    _latest_spec,
    _merge_uids,
    _parse_ids,
    _resolve_tech,
    _scope_override_block,
    _scope_override_row,
)
from app.domains.prospects.serializers import _company_out, _company_payload, _prospect_payload
from app.integrations.apollo import client as apollo
from app.models import (
    Company,
    Prospect,
    ResearchRun,
    ResearchSpec,
)

log = logging.getLogger("holdslot.prospects")


# W8 caches (warm-container memo; see app/core/cache.py).
#   * Company search is the credit-costing Apollo call — short TTL coalesces a re-run of the same
#     scope (double-click / re-find) without spending again. Keyed by the filter alone: Apollo
#     returns the same rows for any caller, so the key is global (raw rows, pre-suppression).
#   * The people-facet sidebar is ~26 free Apollo probes per open — memoized per (tenant, org set).
_COMPANY_SEARCH_CACHE = TTLCache(ttl_seconds=90)

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

LOOKALIKE_LIMIT = 10  # peers fetched per Lookalike find (seeds drop via domain dedupe → ≤10 net)

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
