"""C2 unit tests — apollo_map (pure) against the live C0 fixtures + the client paginator (mocked).

The map/parse tests run against `tests/fixtures/apollo/*.json` — the *actual* Apollo responses
captured at C0 — so they assert against Apollo's real shapes (sparse company rows, obfuscated
people rows), not the docs' stubs. The client tests mock transport (no network, no key, no spend).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.domains.prospects import apollo_map
from app.integrations.apollo import client as apollo

_FIX = Path(__file__).resolve().parent / "fixtures" / "apollo"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text())


# --------------------------------------------------------------------------- request builders


def test_map_company_filter_forwards_and_drops_empties():
    cs = {
        "q_organization_keyword_tags": ["devops", "observability"],
        "organization_num_employees_ranges": ["11,50"],
        "organization_locations": [],  # empty → dropped
        "revenue_range": {"min": 1000000, "max": None},  # null max stripped
    }
    intent = {
        "company": {
            # Date windows may still exist in OLD stored specs / stale saved overrides — the
            # mapper must NEVER forward them (spec v5 removed them from the contract entirely).
            "latest_funding_date_range": {"min": "2026-01-01", "max": None},
            "q_organization_job_titles": ["Head of Sales"],
            "organization_job_posted_at_range": {"min": "2026-03-01", "max": None},
        }
    }
    body = apollo_map.map_company_filter(cs, intent)
    assert body["q_organization_keyword_tags"] == ["devops", "observability"]
    assert body["organization_num_employees_ranges"] == ["11,50"]
    assert "organization_locations" not in body
    assert body["revenue_range"] == {"min": 1000000}
    assert body["q_organization_job_titles"] == ["Head of Sales"]
    assert "latest_funding_date_range" not in body  # dead since v5, even when present upstream
    assert "organization_job_posted_at_range" not in body


def test_map_people_filter_scopes_to_one_org_with_facets():
    ps = {
        "person_seniorities": ["vp", "head"],
        "person_department_or_subdepartments": ["master_sales"],
        "q_keywords": "observability",
        "organization_locations": ["United States"],
        "organization_num_employees_ranges": ["1000,5000"],
    }
    body = apollo_map.map_people_filter(ps, org_id="abc123")
    assert body["organization_ids"] == ["abc123"]
    assert body["person_seniorities"] == ["vp", "head"]
    assert body["person_department_or_subdepartments"] == ["master_sales"]
    # This params carries no person_titles, so none appear (Stage 2 forwards titles only when set).
    assert "person_titles" not in body
    assert "include_similar_titles" not in body
    # Pinned org → org-context filters (keyword/location/size) are dropped: they'd over-constrain
    # that one org to 0 people. Only the two persona facets survive alongside organization_ids.
    assert "q_keywords" not in body
    assert "organization_locations" not in body
    assert "organization_num_employees_ranges" not in body
    # No org (broad search) → org-context filters DO apply, and there is no organization_ids key.
    broad = apollo_map.map_people_filter(ps, org_id=None)
    assert "organization_ids" not in broad
    assert broad["q_keywords"] == "observability"
    assert broad["organization_locations"] == ["United States"]
    assert broad["organization_num_employees_ranges"] == ["1000,5000"]


def test_map_people_filter_forwards_titles_and_toggle():
    # D+ Stage 2 — person_titles + the strict/fuzzy toggle ride through; the toggle survives _clean
    # as an explicit False (Apollo defaults include_similar_titles to true, so strict MUST send it).
    strict = apollo_map.map_people_filter(
        {"person_titles": ["VP Sales", "Head of Sales"], "include_similar_titles": False},
        org_id="org1",
    )
    assert strict["person_titles"] == ["VP Sales", "Head of Sales"]
    assert strict["include_similar_titles"] is False
    fuzzy = apollo_map.map_people_filter(
        {"person_titles": ["VP Sales"], "include_similar_titles": True}, org_id="org1"
    )
    assert fuzzy["include_similar_titles"] is True
    # No titles → the toggle is meaningless and must NOT leak into the body.
    facets = apollo_map.map_people_filter(
        {"person_seniorities": ["vp"], "include_similar_titles": False}, org_id="org1"
    )
    assert "person_titles" not in facets
    assert "include_similar_titles" not in facets


def test_map_people_filter_org_scoped_drops_context_even_with_titles():
    # Stage 2 regression: adding person_titles must NOT resurrect the org-context fields a pinned
    # org drops (q_keywords / locations / size) — they'd re-over-constrain the org back to zero.
    body = apollo_map.map_people_filter(
        {
            "person_titles": ["VP Sales"],
            "include_similar_titles": False,
            "person_seniorities": ["vp"],
            "q_keywords": "fintech",
            "organization_locations": ["singapore"],
            "organization_num_employees_ranges": ["50,200"],
        },
        org_id="org9",
    )
    assert body["organization_ids"] == ["org9"]
    assert body["person_titles"] == ["VP Sales"]
    assert "q_keywords" not in body
    assert "organization_locations" not in body
    assert "organization_num_employees_ranges" not in body


# ----------------------------------------------------------------- response parsers (fixtures)


def test_parse_company_handles_sparse_real_row():
    row = _load("companies_search.json")["organizations"][0]
    parsed = apollo_map.parse_company(row)
    assert parsed["apollo_org_id"] == "638a29a8a2636d00c45d9f0c"
    assert parsed["domain"] == "crossinghurdles.com"
    assert parsed["name"] == "Crossing Hurdles"
    # C0 reality: industry/size/country are null at search and must NOT crash.
    assert parsed["industry"] is None
    assert parsed["size"] is None
    assert parsed["country"] is None
    assert parsed["evidence"].get("founded_year") == 2022


def test_parse_person_search_is_obfuscation_safe():
    row = _load("people_search.json")["people"][0]
    parsed = apollo_map.parse_person(row)
    assert parsed["apollo_person_id"] == "55c8e7b4f3e5bb785b00146c"
    assert parsed["first_name"] == "Carlo"
    assert "Sales Manager" in parsed["title"]
    assert parsed["company"] == "DAZZINI S.R.L."
    # last_name / linkedin / email are absent at search — parser must not invent them.
    assert "last_name" not in parsed
    assert parsed["has_email"] is True


def test_parse_match_reveals_full_contact():
    person = _load("people_match.json")["person"]
    parsed = apollo_map.parse_match(person)
    assert parsed["apollo_person_id"] == "55c8e7b4f3e5bb785b00146c"
    assert parsed["last_name"] == "Scaletti"
    assert parsed["email"] == "carlo.scaletti@dazzinimacchine.com"
    assert parsed["email_valid"] is True
    assert parsed["departments"] == ["master_sales"]
    assert parsed["apollo_org_id"] == "671498a68d35110001e9788e"
    assert parsed["full_name"]


def test_parse_enrich_promotes_firmographics_and_intent():
    row = _load("organizations_enrich_apple.json")["organization"]
    parsed = apollo_map.parse_enrich(row)
    assert parsed["domain"] == "apple.com"
    # The firmographics search omits — promoted to first-class columns.
    assert parsed["industry"] == row["industry"]
    assert parsed["size"] == f"{int(row['estimated_num_employees']):,}"  # display-formatted count
    assert parsed["country"] == row["country"]
    # Buying-intent / context evidence is curated (not all 55 keys) and long lists are capped.
    ev = parsed["evidence"]
    assert ev.get("short_description")
    assert len(ev.get("technology_names", [])) <= 25
    assert len(ev.get("keywords", [])) <= 30


# ----------------------------------------------------------------- client paginator (mocked)


def test_paginate_requests_full_pages_and_trims_client_side(monkeypatch):
    """R1: every page asks the CONSTANT per_page=100 (so page N always means the same rows), fetches
    ⌈150/100⌉=2 pages, and trims the collected 200 down to 150 client-side. A per_page that shrank
    with the remaining budget (the old bug) re-read the prior page's tail and skipped 101-150."""
    calls: list[dict] = []

    def fake_post(path, body, timeout=apollo.DEFAULT_TIMEOUT):
        calls.append(body)
        page = body["page"]
        rows = [{"id": f"p{page}-{i}"} for i in range(body["per_page"])]
        return {"organizations": rows, "pagination": {"page": page, "total_pages": 5}}

    monkeypatch.setattr(apollo, "_post", fake_post)
    out = apollo.search_companies({"q": "x"}, max_results=150)
    assert len(out) == 150  # trimmed to max_results
    assert [c["page"] for c in calls] == [1, 2]  # stopped once ≥150 collected
    assert calls[0]["per_page"] == 100 and calls[1]["per_page"] == 100  # CONSTANT page size
    # No row is dropped or duplicated across the page boundary: rows 1..150 are page-1 items 0..99
    # then page-2 items 0..49, in order.
    assert out[100]["id"] == "p2-0" and out[149]["id"] == "p2-49"


def test_paginate_stops_when_data_runs_out(monkeypatch):
    def fake_post(path, body, timeout=apollo.DEFAULT_TIMEOUT):
        assert path == "mixed_people/api_search"  # search_people uses api_search, never legacy
        return {"people": [{"id": "only"}], "pagination": {"page": 1, "total_pages": 1}}

    monkeypatch.setattr(apollo, "_post", fake_post)
    out = apollo.search_people({"person_titles": ["x"]}, max_results=100)
    assert out == [{"id": "only"}]


def test_paginate_resumes_from_start_page(monkeypatch):
    """D+ Stage 3 — start_page resumes an unchanged scope mid-result-set: pages 3+4 are fetched (not
    1), `end_page` is the cursor for the next resume, and total_entries/total_pages ride off the
    first FETCHED page (page 3), never page 1."""
    calls: list[int] = []

    def fake_post(path, body, timeout=apollo.DEFAULT_TIMEOUT):
        page = body["page"]
        calls.append(page)
        return {
            "organizations": [{"id": f"p{page}-{i}"} for i in range(body["per_page"])],
            "pagination": {"page": page, "total_pages": 9, "total_entries": 861},
        }

    monkeypatch.setattr(apollo, "_post", fake_post)
    rows, meta = apollo.search_companies_meta({"q": "x"}, max_results=150, start_page=3)
    assert calls == [3, 4]  # resumed at page 3 — page 1/2 never re-bought
    assert len(rows) == 150
    assert meta["start_page"] == 3
    assert meta["end_page"] == 4  # the cursor a repeat find resumes past
    assert meta["pages_fetched"] == 2  # count fetched THIS call (pages 3, 4)
    assert meta["total_entries"] == 861 and meta["total_pages"] == 9


def test_cursor_decision_resume_reset_and_exhaustion():
    """D+ Stage 3 — the pure resume decision from the latest same-scope run's result_meta."""
    from app.domains.prospects import router

    pp = apollo.PER_PAGE_MAX  # the cursor is only valid at the page size it was recorded under (R1)
    assert router._cursor_decision(None) == (1, False)  # no prior run → page 1
    assert router._cursor_decision({"per_page": pp}) == (1, False)  # prior run, no cursor → page 1
    assert router._cursor_decision({"per_page": pp, "page_cursor": 3}) == (4, False)  # resume past
    # A prior run that exhausted the scope → short-circuit signal (caller re-flags "regenerate").
    assert router._cursor_decision({"per_page": pp, "scope_exhausted": True, "page_cursor": 9}) == (
        1,
        True,
    )
    # A malformed cursor never crashes the find — falls back to page 1.
    assert router._cursor_decision({"per_page": pp, "page_cursor": "oops"}) == (1, False)
    # R1: a cursor recorded under a DIFFERENT page size (or a pre-R1 run with no per_page) is
    # discarded — its page numbers don't map to the current page width. Start fresh at page 1.
    assert router._cursor_decision({"page_cursor": 3}) == (1, False)  # missing per_page (legacy)
    assert router._cursor_decision({"per_page": pp - 1, "page_cursor": 3}) == (1, False)  # changed
    assert router._cursor_decision({"per_page": pp - 1, "scope_exhausted": True}) == (1, False)


def test_is_apac_country_city_and_negative():
    """R29d — APAC detection matches a country token ("Singapore", "Sydney, Australia") AND a
    city-only scope with no country segment ("Sydney", "Tokyo"); a non-APAC scope is False."""
    from app.domains.prospects import router

    assert router._is_apac(["Singapore"]) is True
    assert router._is_apac(["Hong Kong"]) is True
    assert router._is_apac(["Sydney, Australia"]) is True
    assert router._is_apac(["Kowloon, Hong Kong"]) is True
    assert router._is_apac(["Sydney"]) is True  # city-only, no country — the R29d fix
    assert router._is_apac(["Tokyo"]) is True
    assert router._is_apac(["United States", "Toronto, Canada"]) is False
    assert router._is_apac([]) is False


def test_body_hash_stable_across_feedback_negatives():
    """R4 — the page-cursor key hashes only the STABLE scope: adding/altering feedback-derived
    negatives (`organization_not_locations`, `currently_not_using_any_of_technology_uids`) must NOT
    change the hash (else a re-run of the same scope churns the cursor and re-buys page 1), but a
    genuine scope change must."""
    from app.domains.prospects import router

    scope = {
        "organization_locations": ["United States"],
        "q_organization_keyword_tags": ["fintech"],
        "currently_using_any_of_technology_uids": ["999"],  # positive tech (ICP-derived) is stable
    }
    base = router._body_hash(scope)
    # Different feedback negatives → SAME hash (stripped before hashing).
    assert base == router._body_hash({**scope, "organization_not_locations": ["Canada"]})
    assert base == router._body_hash({
        **scope,
        "organization_not_locations": ["Mexico", "Brazil"],
        "currently_not_using_any_of_technology_uids": ["123", "456"],
    })
    # A real scope change → DIFFERENT hash (resets the cursor to page 1).
    assert base != router._body_hash({**scope, "organization_locations": ["United Kingdom"]})
    assert base != router._body_hash({**scope, "currently_using_any_of_technology_uids": ["111"]})


def test_search_companies_meta_captures_first_page_signal(monkeypatch):
    """D+ Stage 1 — search_companies_meta returns (rows, meta) with `total_entries` + `breadcrumbs`
    read off page 1 ONLY (no extra call) plus `pages_fetched`: the scope-lineage telemetry that the
    find path snapshots into research_run.result_meta."""
    crumbs = [{"label": "Employees", "signal_field_name": "organization_num_employees_ranges",
               "value": "11,50"}]

    def fake_post(path, body, timeout=apollo.DEFAULT_TIMEOUT):
        page = body["page"]
        return {
            "organizations": [{"id": f"p{page}-{i}"} for i in range(body["per_page"])],
            "breadcrumbs": crumbs if page == 1 else [{"label": "later"}],
            "pagination": {"page": page, "total_pages": 5, "total_entries": 372},
        }

    monkeypatch.setattr(apollo, "_post", fake_post)
    rows, meta = apollo.search_companies_meta({"q": "x"}, max_results=150)
    assert len(rows) == 150  # two pages (100 + 50)
    assert meta["total_entries"] == 372
    assert meta["breadcrumbs"] == crumbs  # captured from page 1, not overwritten by page 2
    assert meta["pages_fetched"] == 2


def test_search_companies_still_returns_bare_rows(monkeypatch):
    """The rows-only wrapper is unchanged for callers (e.g. tests) that don't want meta."""
    monkeypatch.setattr(
        apollo, "_post",
        lambda path, body, timeout=apollo.DEFAULT_TIMEOUT: {
            "organizations": [{"id": "a"}], "pagination": {"page": 1, "total_pages": 1}
        },
    )
    assert apollo.search_companies({"q": "x"}, max_results=10) == [{"id": "a"}]


def test_match_person_extracts_person(monkeypatch):
    seen = {}

    def fake_post(path, body, timeout=apollo.DEFAULT_TIMEOUT):
        seen.update(path=path, body=body)
        return {"person": {"id": "x", "email": "a@b.com"}}

    monkeypatch.setattr(apollo, "_post", fake_post)
    person = apollo.match_person("x")
    assert person["email"] == "a@b.com"
    assert seen["path"] == "people/match"
    assert seen["body"]["reveal_personal_emails"] is True
    assert seen["body"]["reveal_phone_number"] is False


def test_enrich_organizations_hits_single_enrich_per_domain(monkeypatch):
    """enrich uses GET organizations/enrich?domain= (ONE org/call) — NOT bulk_enrich — and unwraps
    the `organization` object. A failing domain is dropped, not fatal."""
    seen: list[dict] = []

    def fake_get(path, query, timeout=apollo.DEFAULT_TIMEOUT):
        seen.append({"path": path, "query": query})
        if query["domain"] == "boom.com":
            raise apollo.ApolloError("HTTP 422", status=422)
        return {"organization": {"id": query["domain"], "industry": "Software"}}

    monkeypatch.setattr(apollo, "_get", fake_get)
    out = apollo.enrich_organizations(["a.com", "boom.com", "b.com", "a.com"])
    assert all(c["path"] == "organizations/enrich" for c in seen)  # never bulk_enrich
    assert {c["query"]["domain"] for c in seen} == {"a.com", "boom.com", "b.com"}  # deduped
    assert [o["id"] for o in out] == ["a.com", "b.com"]  # boom dropped, order preserved


def test_parse_org_anchor_extracts_customer_firmographics():
    """D+ Stage 4 — a recorded enrich response → a compact customer anchor (industry / keywords /
    coarse employee band). `industry_tag_id` is parsed but flagged experiment-only."""
    org = _load("organizations_enrich_apple.json")["organization"]
    anchor = apollo_map.parse_org_anchor(org)
    assert anchor["domain"] == "apple.com"
    assert anchor["industry"] == "electrical/electronic manufacturing"
    assert "consumer electronics" in anchor["industries"]
    assert anchor["employee_band"] == "10000+"  # 164,000 employees → open top band
    assert len(anchor["keywords"]) <= 12 and "retail" in anchor["keywords"]
    assert anchor["industry_tag_id"] == "5567cd4c73696439c9030000"  # parsed, not model-fed


def test_parse_org_anchor_omits_empty_fields():
    # A sparse org contributes nothing (the "no empty blocks" rule) beyond its domain.
    anchor = apollo_map.parse_org_anchor({"primary_domain": "x.com"})
    assert anchor == {"domain": "x.com"}
    assert apollo_map.parse_org_anchor({}) == {}


def test_employee_band_maps_counts_to_coarse_ranges():
    assert apollo_map._employee_band(7) == "1-10"
    assert apollo_map._employee_band(120) == "51-200"
    assert apollo_map._employee_band(300) == "201-500"
    assert apollo_map._employee_band(50000) == "10000+"
    assert apollo_map._employee_band(0) == "" and apollo_map._employee_band(None) == ""


def test_supported_technologies_csv_returns_raw_text_and_caches(monkeypatch):
    """D+ Stage 4 — the tech vocabulary is fetched as RAW CSV (raw=True), from the
    `auth/supported_technologies_csv` endpoint, and cached once per warm container."""
    calls: list[dict] = []

    def fake_request(method, path, *, body=None, timeout=apollo.DEFAULT_TIMEOUT, raw=False):
        calls.append({"method": method, "path": path, "raw": raw})
        return "cleaned_name,uid\nSalesforce,salesforce\n"

    apollo.reset_tech_vocab()
    monkeypatch.setattr(apollo, "_request", fake_request)
    first = apollo.supported_technologies_csv()
    second = apollo.supported_technologies_csv()
    assert first.startswith("cleaned_name,uid")
    assert first == second
    assert len(calls) == 1  # cached — one network call for two reads
    assert calls[0] == {"method": "GET", "path": "auth/supported_technologies_csv", "raw": True}
    apollo.reset_tech_vocab()


def test_people_ladder_titles_first_then_facets():
    """D+ Stage 2 ladder: person_titles (strict→fuzzy) leads, the two facets are the fallback.
    The toggle is set per title rung; facet rungs drop titles so they don't AND the fallback."""
    from app.domains.prospects import router

    params = {
        "person_titles": ["VP Sales"],
        "person_seniorities": ["vp", "director"],
        "person_department_or_subdepartments": ["master_sales"],
    }
    rungs = router._people_ladder(params)
    assert [lvl for _, lvl in rungs] == [
        "titles_strict", "titles_fuzzy", "seniority_dept", "seniority_only",
    ]
    assert rungs[0][0]["include_similar_titles"] is False  # strict
    assert rungs[1][0]["include_similar_titles"] is True  # fuzzy
    assert rungs[2][0]["person_titles"] == []  # facet fallback drops titles
    assert rungs[2][0]["person_department_or_subdepartments"] == ["master_sales"]
    assert rungs[3][0]["person_department_or_subdepartments"] == []  # seniority alone
    assert rungs[3][0]["person_seniorities"] == ["vp", "director"]


def test_people_ladder_skips_absent_levers():
    """Each rung is emitted only when the params carry that lever; the ladder is never empty."""
    from app.domains.prospects import router

    L = lambda p: [lvl for _, lvl in router._people_ladder(p)]  # noqa: E731
    # Titles only → the two title rungs (no facet fallback to descend to).
    assert L({"person_titles": ["CEO"]}) == ["titles_strict", "titles_fuzzy"]
    # Facets only → straight to the facet fallback (no title rungs).
    assert L(
        {"person_seniorities": ["vp"], "person_department_or_subdepartments": ["master_sales"]}
    ) == ["seniority_dept", "seniority_only"]
    # A lone department (no seniority, no titles) → nothing to descend: one terminal "as_is" rung.
    assert L({"person_department_or_subdepartments": ["master_sales"]}) == ["as_is"]
    assert L({}) == ["as_is"]  # empty params → one "as_is" rung, never an empty ladder


def test_search_people_relaxed_queries_titles_first(monkeypatch):
    """Titles present → the strict-title rung runs first; when it hits, the facets never run."""
    from app.domains.prospects import router

    calls: list[dict] = []
    monkeypatch.setattr(
        router.apollo,
        "search_people",
        lambda body, max_results=0: (calls.append(body) or [{"id": "p1"}]),  # first rung hits
    )
    params = {
        "person_titles": ["VP Sales"],
        "person_seniorities": ["vp"],
        "person_department_or_subdepartments": ["master_sales"],
    }
    rows, body, level = router._search_people_relaxed(params, "org1", 10)
    assert level == "titles_strict"
    assert body["person_titles"] == ["VP Sales"]
    assert body["include_similar_titles"] is False  # strict rung
    assert body["organization_ids"] == ["org1"]
    assert len(calls) == 1  # hit on rung 1 — no fuzzy, no facet fallback


def test_search_people_relaxed_descends_to_facet_fallback(monkeypatch):
    """No titles → the facet fallback: seniority×dept then seniority-only; stops at first hit."""
    from app.domains.prospects import router

    calls: list[dict] = []

    def fake_search(body, max_results=0):
        calls.append(body)
        has_sen = "person_seniorities" in body
        has_dep = "person_department_or_subdepartments" in body
        return [{"id": "p1"}] if (has_sen and not has_dep) else []  # only seniority_only hits

    monkeypatch.setattr(router.apollo, "search_people", fake_search)
    params = {"person_seniorities": ["vp"], "person_department_or_subdepartments": ["master_sales"]}
    rows, body, level = router._search_people_relaxed(params, "org1", 10)
    assert level == "seniority_only"
    assert rows == [{"id": "p1"}]
    assert body["organization_ids"] == ["org1"]
    assert len(calls) == 2  # seniority_dept, then seniority_only


def test_is_apac_trips_on_apac_country_token():
    """D+ Stage 2 APAC trigger: comma-token, case-insensitive; no substring false positives."""
    from app.domains.prospects import router

    assert router._is_apac(["singapore"]) is True
    assert router._is_apac(["kowloon, hong kong"]) is True  # comma-token match
    assert router._is_apac(["Hong Kong"]) is True  # case-insensitive
    assert router._is_apac(["united states", "germany"]) is False
    assert router._is_apac([]) is False
    assert router._is_apac(None) is False


def test_count_companies_probes_total_off_page_one(monkeypatch):
    """D+ Stage 1b — count_companies is a per_page=1 probe → pagination.total_entries (FREE), the
    relax-ladder breadth signal. It reads the nested pagination total (company-search shape)."""
    seen: dict = {}

    def fake_post(path, body, timeout=apollo.DEFAULT_TIMEOUT):
        seen.update(path=path, body=body)
        return {"organizations": [{"id": "x"}], "pagination": {"total_entries": 8123}}

    monkeypatch.setattr(apollo, "_post", fake_post)
    assert apollo.count_companies({"q_organization_keyword_tags": ["saas"]}) == 8123
    assert seen["path"] == "mixed_companies/search"
    assert seen["body"]["per_page"] == 1  # no rows fetched


# --------------------------------------------------------------- D+ Stage 1b · company relax ladder


def test_widen_employee_ranges_halves_floor_doubles_ceiling():
    from app.domains.prospects import router

    assert router._widen_employee_ranges(["51,100", "11,50"]) == ["25,200", "5,100"]
    assert router._widen_employee_ranges(["1,10"]) == ["1,20"]  # floor never below 1
    assert router._widen_employee_ranges(["junk"]) == ["junk"]  # malformed passed through


def test_weakest_keyword_is_the_longest_ties_break_late():
    from app.domains.prospects import router

    assert router._weakest_keyword(["ai", "healthcare software", "crm"]) == "healthcare software"
    # equal-length tie → the later position wins (deterministic)
    assert router._weakest_keyword(["abcd", "wxyz"]) == "wxyz"


def test_drop_conflicts_guards_self_contradicting_filters():
    """The server-added exclude filters must never contradict what the scope already includes:
    a bad-row country that the scope also targets, or a negative tech UID the ICP also requires —
    each would AND include∩exclude to zero. `_drop_conflicts` strips those (case-folded for
    location names; exact for pre-normalized UIDs)."""
    from app.domains.prospects import router

    # Locations: fold the case — "Hong Kong" excluded but the scope targets "hong kong" → dropped.
    targeted = {"hong kong", "singapore"}
    assert router._drop_conflicts(["Hong Kong", "japan"], targeted, fold=True) == ["japan"]
    # Tech UIDs: exact match — a UID required (positive) is dropped from the negative list.
    assert router._drop_conflicts(["salesforce", "hubspot"], {"salesforce"}) == ["hubspot"]
    # No overlap / empty inputs are pass-throughs.
    assert router._drop_conflicts(["a", "b"], set()) == ["a", "b"]
    assert router._drop_conflicts([], {"x"}, fold=True) == []


def test_company_relax_ladder_order_is_deterministic_and_terminal():
    """revenue → size → weakest-keyword, cumulative, ≤3 rungs, each a genuine widening."""
    from app.domains.prospects import router

    body = {
        "revenue_range": {"min": 1000000},
        "organization_num_employees_ranges": ["51,100"],
        "q_organization_keyword_tags": ["ai", "insurance software"],
        "organization_locations": ["Hong Kong"],
    }
    rungs = list(router._company_relax_ladder(body))
    labels = [lbl for lbl, _ in rungs]
    assert labels == ["drop_revenue_range", "widen_size", "drop_keyword:insurance software"]
    # cumulative: the last rung has revenue dropped AND size widened AND the weakest keyword gone
    final = rungs[-1][1]
    assert "revenue_range" not in final
    assert final["organization_num_employees_ranges"] == ["25,200"]
    assert final["q_organization_keyword_tags"] == ["ai"]
    assert final["organization_locations"] == ["Hong Kong"]  # untouched by the ladder
    # original body is never mutated
    assert body["revenue_range"] == {"min": 1000000}


def test_company_relax_ladder_skips_absent_rungs():
    """A body with only a keyword yields exactly one rung (no revenue/size to relax); a single
    keyword drops to no keyword filter at all rather than an empty list."""
    from app.domains.prospects import router

    rungs = list(router._company_relax_ladder({"q_organization_keyword_tags": ["fintech"]}))
    assert [lbl for lbl, _ in rungs] == ["drop_keyword:fintech"]
    assert "q_organization_keyword_tags" not in rungs[-1][1]
    # nothing relaxable → an empty ladder (terminal, not an error)
    assert list(router._company_relax_ladder({"organization_locations": ["US"]})) == []


def test_resolve_company_scope_stops_at_first_healthy_rung(monkeypatch):
    """The loop widens only while thin: here dropping revenue clears FIND_RELAX_MIN, so it stops at
    level 1 and never widens size/keyword."""
    from app.domains.prospects import router

    counts = iter([3, 40])  # original thin, after drop_revenue healthy
    monkeypatch.setattr(router.apollo, "count_companies", lambda body: next(counts))
    body = {
        "revenue_range": {"min": 5000000},
        "organization_num_employees_ranges": ["51,100"],
        "q_organization_keyword_tags": ["ai"],
    }
    resolved, level, steps, total = router._resolve_company_scope(body)
    assert level == 1 and steps == ["drop_revenue_range"] and total == 40
    assert "revenue_range" not in resolved
    assert resolved["organization_num_employees_ranges"] == ["51,100"]  # size not widened


def test_resolve_company_scope_no_relax_when_already_broad(monkeypatch):
    from app.domains.prospects import router

    monkeypatch.setattr(router.apollo, "count_companies", lambda body: 999)
    body = {"revenue_range": {"min": 1}, "q_organization_keyword_tags": ["ai"]}
    resolved, level, steps, total = router._resolve_company_scope(body)
    assert level == 0 and steps == [] and total == 999 and resolved == body


def test_resolve_company_scope_walks_full_ladder_when_persistently_thin(monkeypatch):
    """Every rung stays under the floor → the loop exhausts the ladder (terminal) and reports the
    final relaxed body + the count of rungs applied."""
    from app.domains.prospects import router

    monkeypatch.setattr(router.apollo, "count_companies", lambda body: 2)
    body = {
        "revenue_range": {"min": 9},
        "organization_num_employees_ranges": ["51,100"],
        "q_organization_keyword_tags": ["ai", "insurance software"],
    }
    resolved, level, steps, total = router._resolve_company_scope(body)
    assert level == 3
    assert steps == ["drop_revenue_range", "widen_size", "drop_keyword:insurance software"]
    assert "revenue_range" not in resolved
    assert resolved["organization_num_employees_ranges"] == ["25,200"]
    assert resolved["q_organization_keyword_tags"] == ["ai"]


def test_resolve_company_scope_probe_failure_is_non_blocking(monkeypatch):
    """A probe ApolloError never dead-ends the find — resolve returns the original body, level 0."""
    from app.domains.prospects import router

    def boom(body):
        raise router.apollo.ApolloError("HTTP 502", status=502)

    monkeypatch.setattr(router.apollo, "count_companies", boom)
    body = {"q_organization_keyword_tags": ["ai"]}
    resolved, level, steps, total = router._resolve_company_scope(body)
    assert resolved == body and level == 0 and steps == [] and total == 0


def test_api_key_env_override(monkeypatch):
    monkeypatch.setenv("HOLDSLOT_APOLLO_KEY", "env-key-123")
    apollo.reset_key()
    assert apollo._api_key() == "env-key-123"
    apollo.reset_key()
