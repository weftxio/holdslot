"""apollo_map — the pure Brief→Apollo forwarder + response parsers (C2, the B→C linkage).

No I/O, no network — every function is a pure transform, so it is unit-tested against the live C0
fixtures in `tests/fixtures/apollo/` (Apollo's *real* response shapes, not the docs' idealized
stubs). Two halves:

  * **Request builders** — turn the validated `ResearchSpec` v3 params into the exact request body
    `mixed_companies/search` / `mixed_people/api_search` accept. Because v3 already emits Apollo
    field names (see briefs/research_spec.py), this is mostly a copy: drop empties, pack the
    intent block in, and pass **one** `organization_ids` per people call (Flow B loops the selected
    orgs — C0 proved search rows carry no `organization_id`, so the org must be known per call).
  * **Response parsers** — pull the columns HoldSlot stores out of each row. C0 reality baked in:
    company-search rows are **sparse** (no industry/size/address); people-search rows are
    **obfuscated** (no last_name/linkedin/email/departments — those appear only at `people/match`).
    So `parse_person` (search) fills first_name/title only; `parse_match` (enrich) fills the rest.
"""

from __future__ import annotations

from app.domains.prospects.identity import normalize_domain

# --------------------------------------------------------------------------- request builders


def _clean(d: dict) -> dict:
    """Drop keys whose value is empty/null so Apollo never sees a meaningless filter
    (`[]`/`""`/`None`, or a `{min,max}` range that is all-null)."""
    out: dict = {}
    for k, v in d.items():
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, dict):
            inner = {ik: iv for ik, iv in v.items() if iv is not None and iv != ""}
            if inner:
                out[k] = inner
            continue
        out[k] = v
    return out


def map_company_filter(company_search_params: dict, intent_filters: dict | None = None) -> dict:
    """Build the `mixed_companies/search` request body from v3 fit + intent params (no paging).

    Fit firmographics forward 1:1; the intent block (funding date + hiring-title/date windows) is
    merged in as native Apollo recency filters. The caller adds `page`/`per_page`.
    """
    cs = company_search_params or {}
    body = {
        "q_organization_keyword_tags": cs.get("q_organization_keyword_tags"),
        "organization_num_employees_ranges": cs.get("organization_num_employees_ranges"),
        "organization_locations": cs.get("organization_locations"),
        "revenue_range": cs.get("revenue_range"),
    }
    company_intent = (intent_filters or {}).get("company") or {}
    body.update(
        {
            "latest_funding_date_range": company_intent.get("latest_funding_date_range"),
            "q_organization_job_titles": company_intent.get("q_organization_job_titles"),
            "organization_job_posted_at_range": company_intent.get(
                "organization_job_posted_at_range"
            ),
        }
    )
    return _clean(body)


def map_people_filter(people_search_params: dict, org_id: str | None = None) -> dict:
    """Build one `mixed_people/api_search` request body, scoped to a SINGLE org.

    Flow B loops the selected companies and calls this once per `org_id`, so each returned person's
    company is known from the loop (C0: search output has no `organization_id`). `org_id` is
    optional only so the builder stays pure/testable; the live flow always passes one.
    """
    ps = people_search_params or {}
    body = {
        "person_titles": ps.get("person_titles"),
        "include_similar_titles": ps.get("include_similar_titles"),
        "q_keywords": ps.get("q_keywords"),
        "person_seniorities": ps.get("person_seniorities"),
        "organization_locations": ps.get("organization_locations"),
        "organization_num_employees_ranges": ps.get("organization_num_employees_ranges"),
        "organization_ids": [org_id] if org_id else None,
    }
    # `_clean` drops None/""/[] but keeps a real boolean (False != [] / "" / None), so
    # `include_similar_titles` survives whether True or False; only a None value is dropped.
    return _clean(body)


# --------------------------------------------------------------------------- response parsers


def parse_company(row: dict) -> dict:
    """One `mixed_companies/search` org row → the Company columns HoldSlot stores.

    C0: search rows are sparse — `industry`/`estimated_num_employees`/address are null, so those
    columns stay None (the *filter* still constrained the result; the value just isn't returned).
    `domain` is the registrable dedupe key (from `primary_domain`, else `website_url`).
    """
    row = row or {}
    domain = normalize_domain(row.get("primary_domain") or row.get("website_url"))
    # Search rows are sparse on firmographics but DO carry free buying-intent signals (Apollo's own
    # intent score + headcount-growth trend) — keep them so intent survives even if enrich is off.
    evidence = {
        k: row.get(k)
        for k in (
            "founded_year",
            "organization_revenue",
            "naics_codes",
            "sic_codes",
            "intent_strength",
            "has_intent_signal_account",
            "organization_headcount_six_month_growth",
            "organization_headcount_twelve_month_growth",
            "organization_headcount_twenty_four_month_growth",
        )
        if row.get(k) not in (None, "", [], 0, 0.0, False)
    }
    return {
        "apollo_org_id": row.get("id"),
        "domain": domain,
        "name": row.get("name") or "",
        "website": row.get("website_url"),
        "linkedin_url": row.get("linkedin_url"),
        "industry": row.get("industry"),  # null at search; filled by parse_enrich
        "size": None,  # estimated_num_employees null at search; filled by parse_enrich
        "country": None,  # no address at search; filled by parse_enrich
        "evidence": evidence,
    }


# Enrich firmographics promoted to first-class columns are handled inline; everything else in this
# set is buying-intent / context evidence the fit rubric scores against — deliberately NOT all 55
# enrich keys, just the signals that move a score (timing, tech, scale, descriptive match).
_ENRICH_EVIDENCE_KEYS = (
    "founded_year",
    "annual_revenue",
    "organization_revenue",
    "estimated_num_employees",
    "industries",
    "secondary_industries",
    "departmental_head_count",
    "organization_headcount_six_month_growth",
    "organization_headcount_twelve_month_growth",
    "organization_headcount_twenty_four_month_growth",
    "short_description",
    "city",
    "state",
    "naics_codes",
    "sic_codes",
)


def _fmt_headcount(n) -> str | None:
    """Employee count → a compact display/scoring string (`"154,000"`); None when absent."""
    try:
        return f"{int(n):,}" if n else None
    except (TypeError, ValueError):
        return None


def parse_enrich(row: dict) -> dict:
    """One `organizations/bulk_enrich` org → the columns + buying-intent evidence HoldSlot stores.

    Unlike `parse_company` (search, sparse), enrich returns industry / employee count / address /
    tech / keywords / headcount growth — the firmographic + timing signals the fit rubric scores.
    Industry/size/country become columns; the rest lands in `evidence` (long lists are capped to
    keep the scorer payload lean). Empty values are dropped so a merge never clobbers a real value.
    """
    row = row or {}
    domain = normalize_domain(row.get("primary_domain") or row.get("website_url"))
    evidence = {
        k: row.get(k)
        for k in _ENRICH_EVIDENCE_KEYS
        if row.get(k) not in (None, "", [], {}, 0, 0.0)
    }
    if row.get("keywords"):
        evidence["keywords"] = row["keywords"][:30]
    if row.get("technology_names"):
        evidence["technology_names"] = row["technology_names"][:25]
    return {
        "apollo_org_id": row.get("id"),
        "domain": domain,
        "name": row.get("name") or "",
        "website": row.get("website_url"),
        "linkedin_url": row.get("linkedin_url"),
        "industry": row.get("industry"),
        "size": _fmt_headcount(row.get("estimated_num_employees")),
        "country": row.get("country"),
        "evidence": evidence,
    }


def parse_person(row: dict) -> dict:
    """One `mixed_people/api_search` row → the find-time fields (pre-enrich, obfuscated).

    Only `id`/`first_name`/`title` + the nested `organization.name` are real here; last
    name/linkedin/email/departments are revealed by `parse_match` after `people/match`.
    """
    row = row or {}
    org = row.get("organization") or {}
    return {
        "apollo_person_id": row.get("id"),
        "first_name": row.get("first_name") or "",
        "title": row.get("title") or "",
        "company": org.get("name") or "",
        "has_email": bool(row.get("has_email")),
    }


def parse_match(person: dict) -> dict:
    """One `people/match` person → the enriched contact (the credit-spend reveal).

    This is where full name / linkedin / email / departments / the real org id appear. `email_valid`
    is the verified-status gate (CREDIT_POLICY.email_status_filter); phone is off at MVP.
    """
    person = person or {}
    org = person.get("organization") or {}
    email = person.get("email") or ""
    return {
        "apollo_person_id": person.get("id"),
        "first_name": person.get("first_name") or "",
        "last_name": person.get("last_name") or "",
        "full_name": person.get("name")
        or " ".join(p for p in (person.get("first_name"), person.get("last_name")) if p),
        "title": person.get("title") or "",
        "email": email,
        "email_valid": person.get("email_status") == "verified",
        "linkedin_url": person.get("linkedin_url") or "",
        "departments": person.get("departments") or [],
        "company": org.get("name") or "",
        "apollo_org_id": org.get("id"),
    }
