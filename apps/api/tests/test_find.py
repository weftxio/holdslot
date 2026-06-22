"""C4/C5 unit tests — the pure find filters (exclusion + dedupe) before any upsert.

DB-free: proves the credit/scope safeguard drops the right rows. The end-to-end find→score→enrich
path is exercised by the DB-gated integration tests (test_prospects_apollo, run on dev Aurora).
"""

from __future__ import annotations

from app.domains.prospects import find
from app.domains.prospects.suppression import ExclusionSet


def test_filter_companies_drops_excluded_dupes_and_domainless():
    exclusions = ExclusionSet(domains={"customer.com"})
    parsed = [
        {"apollo_org_id": "1", "domain": "good.com"},
        {"apollo_org_id": "2", "domain": "customer.com"},  # existing customer → dropped
        {"apollo_org_id": "3", "domain": "good.com"},  # dup of #1 within batch → dropped
        {"apollo_org_id": "4", "domain": ""},  # no domain → dropped
        {"apollo_org_id": "5", "domain": "seen.com"},  # already in DB → dropped
    ]
    survivors, dropped = find.filter_companies(parsed, exclusions, seen_domains={"seen.com"})
    assert [s["apollo_org_id"] for s in survivors] == ["1"]
    assert len(dropped) == 4
    assert {r for _, r in dropped} == {"excluded_domain", "duplicate", "no_domain"}


def test_filter_people_dedupes_by_apollo_id_and_drops_idless():
    parsed = [
        {"apollo_person_id": "a", "first_name": "A"},
        {"apollo_person_id": "a", "first_name": "A-dup"},  # dup → dropped
        {"apollo_person_id": "", "first_name": "X"},  # no id → dropped
        {"apollo_person_id": "b", "first_name": "B"},
        {"apollo_person_id": "c", "first_name": "C"},  # already seen → dropped
    ]
    survivors, dropped = find.filter_people(parsed, seen_person_ids={"c"})
    assert [s["apollo_person_id"] for s in survivors] == ["a", "b"]
    assert {r for _, r in dropped} == {"duplicate", "no_apollo_id"}


def test_filter_people_drops_avoided_titles_case_insensitive_substring():
    parsed = [
        {"apollo_person_id": "a", "title": "VP of Sales"},  # kept
        {"apollo_person_id": "b", "title": "Sales Intern"},  # "intern" → dropped
        {"apollo_person_id": "c", "title": "VP, Sales Operations"},  # "sales ops"? no — substring
        {"apollo_person_id": "d", "title": "Recruiter, Talent"},  # "recruiter" → dropped
        {"apollo_person_id": "e", "title": ""},  # no title → never avoided
    ]
    survivors, dropped = find.filter_people(parsed, avoid_titles=["Intern", "recruiter"])
    assert [s["apollo_person_id"] for s in survivors] == ["a", "c", "e"]
    assert {r for _, r in dropped} == {"avoided_title"}
    # Empty/absent avoid list is a no-op (no row dropped for title).
    survivors2, dropped2 = find.filter_people(parsed, avoid_titles=[])
    assert len(survivors2) == 5 and not dropped2
