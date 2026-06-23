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
            "latest_funding_date_range": {"min": "2026-01-01", "max": None},
            "q_organization_job_titles": ["Head of Sales"],
            "organization_job_posted_at_range": {"min": None, "max": None},  # all-null → dropped
        }
    }
    body = apollo_map.map_company_filter(cs, intent)
    assert body["q_organization_keyword_tags"] == ["devops", "observability"]
    assert body["organization_num_employees_ranges"] == ["11,50"]
    assert "organization_locations" not in body
    assert body["revenue_range"] == {"min": 1000000}
    assert body["latest_funding_date_range"] == {"min": "2026-01-01"}
    assert body["q_organization_job_titles"] == ["Head of Sales"]
    assert "organization_job_posted_at_range" not in body


def test_map_people_filter_scopes_to_one_org_and_keeps_false_similar():
    ps = {
        "person_titles": ["VP Sales"],
        "include_similar_titles": False,  # must survive _clean
        "q_keywords": "observability",
        "person_seniorities": ["vp"],
        "organization_locations": [],
        "organization_num_employees_ranges": ["11,50"],
    }
    body = apollo_map.map_people_filter(ps, org_id="abc123")
    assert body["organization_ids"] == ["abc123"]
    assert body["include_similar_titles"] is False
    assert body["person_titles"] == ["VP Sales"]
    assert "organization_locations" not in body
    # No org → no organization_ids key (pure-testing path).
    assert "organization_ids" not in apollo_map.map_people_filter(ps, org_id=None)


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


def test_paginate_caps_per_page_and_stops_at_max_results(monkeypatch):
    """150 requested → page 1 asks per_page=100 (the Apollo cap), page 2 asks 50, then stops."""
    calls: list[dict] = []

    def fake_post(path, body, timeout=apollo.DEFAULT_TIMEOUT):
        calls.append(body)
        page = body["page"]
        rows = [{"id": f"p{page}-{i}"} for i in range(body["per_page"])]
        return {"organizations": rows, "pagination": {"page": page, "total_pages": 5}}

    monkeypatch.setattr(apollo, "_post", fake_post)
    out = apollo.search_companies({"q": "x"}, max_results=150)
    assert len(out) == 150
    assert [c["page"] for c in calls] == [1, 2]  # stopped once 150 collected
    assert calls[0]["per_page"] == 100 and calls[1]["per_page"] == 50


def test_paginate_stops_when_data_runs_out(monkeypatch):
    def fake_post(path, body, timeout=apollo.DEFAULT_TIMEOUT):
        assert path == "mixed_people/api_search"  # search_people uses api_search, never legacy
        return {"people": [{"id": "only"}], "pagination": {"page": 1, "total_pages": 1}}

    monkeypatch.setattr(apollo, "_post", fake_post)
    out = apollo.search_people({"person_titles": ["x"]}, max_results=100)
    assert out == [{"id": "only"}]


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


def test_api_key_env_override(monkeypatch):
    monkeypatch.setenv("HOLDSLOT_APOLLO_KEY", "env-key-123")
    apollo.reset_key()
    assert apollo._api_key() == "env-key-123"
    apollo.reset_key()
