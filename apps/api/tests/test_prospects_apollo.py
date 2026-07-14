"""C4/C5 integration — the Apollo find→select→find→enrich loop against dev Aurora.

Skipped without the DB env (like the other integration tests). Apollo transport AND the LLM fit
scorer are monkeypatched, so this spends no credits and makes no network call — it proves the
orchestration + persistence: companies land `discovered` + scored, selection scopes Flow B, people
link `company_id` from the per-org loop, and enrich writes the matched email and flips to `scored`.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("HOLDSLOT_DB_CLUSTER_ARN"),
    reason="integration test — needs Aurora dev env (HOLDSLOT_DB_* + AWS creds)",
)

BUILD_PW = "tryholdslot1!"


@pytest.fixture(autouse=True)
def _clear_search_caches():
    """The W8 search memos are module-level warm-container caches (correct for one prod Lambda) but
    are keyed by (scope, page) with NO tenant scoping, so a prior test's cached page for the SAME
    scope suppresses this test's fetch (the cursor-resume test shares the `software` scope with the
    enrich e2e test). Clear before each test so cross-test runs match isolated runs."""
    from app.domains.prospects import router as _pr

    _pr._COMPANY_SEARCH_CACHE.clear()
    _pr._PEOPLE_FACETS_CACHE.clear()
    yield


def _auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def _find_company(client, slug, token, body):
    """Run a company find via the ASYNC endpoint (the sync twin was retired in V2-4): kick the job,
    poll to a terminal state, and return the job's `result` dict augmented with `status`, `error`,
    and a `companies` list (GET /companies). Rows land UNSCORED at find (v2 — the paid web-grounded
    score is a separate pass). A worker validation error (e.g. the multi-ICP guard) surfaces as
    `status='error'` + the message in `error`, NOT an HTTP 4xx — callers assert on that."""
    r = client.post(f"/{slug}/companies/find-company-async", json=body, headers=_auth(token))
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    job: dict = {"status": "queued"}
    for _ in range(300):  # the worker runs on a local daemon thread; apollo/fit are mocked (fast)
        job = client.get(f"/{slug}/scoring-jobs/{job_id}", headers=_auth(token)).json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.02)
    out = dict(job.get("result") or {})
    out["status"] = job["status"]
    out["error"] = job.get("error")
    out["companies"] = client.get(f"/{slug}/companies", headers=_auth(token)).json()["items"]
    return out


def _enrich_score(client, slug, token, keys):
    """Run 'Reveal & score' via the ASYNC door (the sync `/prospects/enrich` twin was retired in
    D+.5/R10): kick the job, poll to terminal, return the merged `result` dict."""
    r = client.post(f"/{slug}/prospects/enrich-score-async",
                    json={"identity_keys": keys}, headers=_auth(token))
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    job: dict = {"status": "queued"}
    for _ in range(300):
        job = client.get(f"/{slug}/scoring-jobs/{job_id}", headers=_auth(token)).json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.02)
    assert job["status"] == "done", job.get("error")
    return dict(job.get("result") or {})


@pytest.fixture
def owner_member():
    """An ephemeral tenant + OWNER user (find endpoints require owner); torn down after."""
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.core.security import hash_password
    from app.main import app
    from app.models import AppUser, Icp, Membership, MembershipRole, ResearchSpec, Tenant

    client = TestClient(app)
    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    slug, email = f"capollo-{suffix}", f"capollo-{suffix}@example.com"
    tenant = Tenant(slug=slug, name=f"CApollo {suffix}")
    db.add(tenant)
    db.flush()
    user = AppUser(email=email, password_hash=hash_password(BUILD_PW), full_name="Owner")
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.owner))
    # An ICP doc carrying the rubric-graded fields that the spec can't hold (maturity/avoidTitles)
    # — proves _build_targeting forwards it to the scorer and Flow B honors `avoidTitles`.
    icp = Icp(
        tenant_id=tenant.id,
        name="Primary",
        tag="primary",
        data={"jobTitles": ["Head of Sales"], "maturity": "growth", "avoidTitles": ["Intern"]},
    )
    db.add(icp)
    db.flush()
    icp_id = str(icp.id)
    # A minimal v4 ResearchSpec so find-company/find-people resolve a per-ICP targeting block.
    # (Production specs are all v4 — `targeting_for_icp` returns None for a pre-v4 spec, so the old
    # top-level `company_search_params` shape 400'd "regenerate the scope".)
    db.add(
        ResearchSpec(
            tenant_id=tenant.id,
            version=1,
            spec={
                "spec_version": 4,
                "icp_targeting": [
                    {
                        "icp_id": icp_id,
                        "icp_name": "Primary",
                        "company_search_params": {"q_organization_keyword_tags": ["software"]},
                        "people_search_params": {
                            "person_seniorities": ["head", "vp"],
                            "person_department_or_subdepartments": ["master_sales"],
                        },
                        "intent_filters": {},
                    }
                ],
                "icp_validation": {},
                "credit_policy": {"max_companies": 500},
            },
        )
    )
    db.commit()
    token = client.post("/auth/login", json={"email": email, "password": BUILD_PW}).json()[
        "access_token"
    ]
    try:
        yield client, slug, token, icp_id
    finally:
        db.delete(icp)
        db.delete(user)
        db.delete(tenant)
        db.commit()
        db.close()


# v2 paid-signal stubs (the scorers return raw signals for labeling.assign_label / _person_label).
_V2_COMPANY_SIGNALS = {
    "liveness": {"status": "live", "note": ""},
    "subscores": {"deal_fit": 5, "outbound_gap": 5, "trigger": 5, "reachability": 5},
    "icp_match": {"icp": "A", "reason": "fits ICP A"},
    "reason": "fits ICP A — good",
    "trigger_line": "raised a round",
    "flags": [],
    "llm_call_id": None,
    "model": "test",
    "cost_usd": 0.0001,
}
_V2_PROSPECT_SIGNALS = {
    "subscores": {"persona_fit": 5, "authority": 5, "trigger": 5, "reachability": 5},
    "reason": "right buyer",
    "flags": [],
    "llm_call_id": None,
    "model": "test",
    "cost_usd": 0.0001,
}


def _patch_apollo_and_fit(monkeypatch, *, orgs, people, match):
    """Patches Apollo + the v2 scorers and RETURNS a list that records every `targeting` dict the
    company scorer was called with — so a test can assert the ICP docs reach the scoring context.
    (Find lands rows UNSCORED in v2; the company scorer only runs on an explicit async rescore.)
    """
    from app.domains.prospects import fit
    from app.integrations.apollo import client as apollo

    seen_targeting: list[dict] = []

    def _co_score(**k):
        seen_targeting.append(k.get("targeting") or {})
        return dict(_V2_COMPANY_SIGNALS)

    # D+ Stage 4 tech resolver — the find only calls this when an ICP carries `technologies` or a
    # bad-tech correlation exists (neither in these fixtures), but stub it so the flow stays
    # network-free regardless.
    monkeypatch.setattr(apollo, "supported_technologies_csv", lambda: "cleaned_name,uid\n")
    # find-company calls search_companies_meta (rows + first-page telemetry) — stub a minimal meta.
    monkeypatch.setattr(
        apollo,
        "search_companies_meta",
        lambda body, *, max_results=100, start_page=1: (
            orgs,
            {
                "total_entries": len(orgs),
                "breadcrumbs": [],
                "pages_fetched": 1,
                "end_page": start_page,  # Stage 3 page cursor
            },
        ),
    )
    # Stage 1b relax-ladder probe (per_page=1 count) — stub a healthy count so the ladder stays
    # dormant and the executed body / found counts these tests assert on are unchanged.
    monkeypatch.setattr(apollo, "count_companies", lambda body: 500)
    # Enrich is best-effort; patch to the same orgs so the merge path runs without a network call.
    monkeypatch.setattr(apollo, "enrich_organizations", lambda domains: orgs)
    monkeypatch.setattr(apollo, "search_people", lambda body, *, max_results=100: people)
    monkeypatch.setattr(
        apollo, "match_person", lambda pid, **k: {**match, "id": pid} if match else {}
    )
    monkeypatch.setattr(fit, "company_score_v2", _co_score)
    monkeypatch.setattr(fit, "prospect_score_v2", lambda **k: dict(_V2_PROSPECT_SIGNALS))
    # Find runs the stage-0 business-model classifier up-front (before any scoring); stub it so the
    # flow doesn't reach the network. B2B keeps the row (no gate for a B2B/absent-market fixture).
    monkeypatch.setattr(
        fit,
        "classify_business_model",
        lambda **k: {
            "business_model": "B2B",
            "hq_country": "",
            "has_b2b_line": False,
            "llm_call_id": None,
            "model": "test",
            "cost_usd": 0.0,
        },
    )
    return seen_targeting


def test_find_select_find_enrich_end_to_end(owner_member, monkeypatch):
    client, slug, token, icp_id = owner_member
    orgs = [
        {"id": "org-A", "name": "Alpha", "primary_domain": "alpha.com", "website_url": "a"},
        {"id": "org-B", "name": "Beta", "primary_domain": "beta.com", "website_url": "b"},
    ]
    people = [
        {"id": "ppl-1", "first_name": "Sam", "title": "Head of Sales",
         "organization": {"name": "Alpha"}, "has_email": True},
        {"id": "ppl-2", "first_name": "Pat", "title": "Sales Intern",  # avoidTitles → dropped
         "organization": {"name": "Alpha"}, "has_email": True},
    ]
    match = {"first_name": "Sam", "last_name": "Reed", "name": "Sam Reed",
             "email": "sam@alpha.com", "email_status": "verified",
             "linkedin_url": "http://linkedin.com/in/sam", "departments": ["master_sales"],
             "organization": {"id": "org-A", "name": "Alpha"}}
    _patch_apollo_and_fit(monkeypatch, orgs=orgs, people=people, match=match)

    # Flow A — find companies (ICP-scoped, so the company is tagged with this ICP). Rows land
    # UNSCORED at find in v2 (label NULL until the paid web-grounded pass); find just lands them.
    body = _find_company(client, slug, token, {"limit": 10, "icp_id": icp_id})
    assert body["status"] == "done", body["error"]
    assert body["found"] == 2 and len(body["companies"]) == 2
    assert all(c["status"] == "discovered" for c in body["companies"])
    alpha = next(c for c in body["companies"] if c["domain"] == "alpha.com")

    # D+ Stage 3 — a re-find of the SAME scope skips orgs already stored ($0 invariant) and returns
    # only NET-NEW rows. Our fake returns the same 2 orgs regardless of page, so both are
    # known-skipped: found=0, known_skipped=2, NO duplicates, no re-processing of the existing rows.
    r2 = _find_company(client, slug, token, {"limit": 10, "icp_id": icp_id})
    assert r2["found"] == 0 and r2["known_skipped"] == 2
    assert len(r2["companies"]) == 2  # no dups

    # Stage Alpha into Step 2 (discovered → selected). Find-people is driven by explicit company_ids
    # (not this status), but staging is what surfaces the company in the Step-2 table.
    r = client.patch(
        f"/{slug}/companies/select", json={"ids": [alpha["id"]], "selected": True},
        headers=_auth(token),
    )
    assert r.status_code == 200 and r.json()[0]["status"] == "selected"

    # Flow B — find people only at the given company. The "Sales Intern" is dropped pre-score by the
    # ICP's avoidTitles, so only the Head of Sales survives (found == 1, not 2). People land
    # UNSCORED ("Pending") — find never blocks on the LLM; scoring is the explicit rescore step.
    r = client.post(f"/{slug}/people/find-people",
                    json={"per_company": 5, "icp_id": icp_id, "company_ids": [alpha["id"]]},
                    headers=_auth(token))
    assert r.status_code == 200, r.text
    pres = r.json()
    assert pres["found"] == 1 and pres["dropped"] >= 1  # intern avoided
    person = pres["prospects"][0]
    assert person["company_id"] == alpha["id"]  # linked from the loop, not the (obfuscated) row
    assert person["status"] == "found" and person["email"] == ""  # no email pre-enrich
    assert person["label"] is None  # unscored on find (the paid people score is a separate pass)

    # Find-people with no company_ids → 400 (nothing to search).
    r = client.post(f"/{slug}/people/find-people", json={}, headers=_auth(token))
    assert r.status_code == 400

    # Reveal & score the found person via the async door → 1 credit, email revealed, status scored.
    res = _enrich_score(client, slug, token, [person["identity_key"]])
    assert res["enriched"] == 1 and res["credits_spent"] == 1
    enriched = client.get(f"/{slug}/prospects", headers=_auth(token)).json()["items"][0]
    assert enriched["email"] == "sam@alpha.com" and enriched["email_valid"] is True
    assert enriched["status"] == "scored"

    # Re-run the SAME (now-revealed) row is idempotent on the enrich side — no second credit spent
    # (R10 — the per-row commit stamps last_enriched_at, so the re-run skips it).
    res2 = _enrich_score(client, slug, token, [person["identity_key"]])
    assert res2["credits_spent"] == 0  # already enriched → skipped, no double-charge


def test_enrich_then_score_worker_reveals_before_scoring(owner_member, monkeypatch):
    """The merged 'Reveal & score' worker (`KIND_ENRICH_SCORE_PROSPECTS`) reveals the verified email
    FIRST, then scores on the revealed row — the fix for scoring a pre-reveal person (no contact →
    `low_fit`/data_unusable). Proven two ways: (1) the enrichment dict handed to the people scorer
    carries the just-revealed email, and (2) the same CFO that would land `low_fit` pre-reveal
    (has_contact=False, see test_labeling) now scores `contact_now` because reveal ran first."""
    from sqlalchemy import select

    from app.core.db import get_session
    from app.domains.prospects import fit
    from app.domains.prospects.router import run_enrich_score_prospects
    from app.integrations.apollo import client as apollo
    from app.models import Company, Prospect, Tenant

    _client, slug, _token, icp_id = owner_member
    db = get_session()
    tenant = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one()

    # A qualified parent account (contact_now) + a found-but-unrevealed CFO (no email pre-reveal).
    company = Company(
        tenant_id=tenant.id, icp_id=uuid.UUID(icp_id), domain="alpha.com", name="Alpha",
        source="apollo", status="people_found", label="contact_now",
    )
    db.add(company)
    db.flush()
    person = Prospect(
        tenant_id=tenant.id, icp_id=uuid.UUID(icp_id), company_id=company.id,
        identity_key="apollo:ppl-99", apollo_person_id="ppl-99", source="apollo",
        status="found", enrichment={"first_name": "Sam", "title": "CFO"},
    )
    db.add(person)
    db.commit()

    # Apollo reveal → a verified email; the people scorer records the enrichment it is handed so the
    # test can prove reveal-happened-before-score.
    monkeypatch.setattr(
        apollo, "match_person",
        lambda pid, **k: {
            "id": pid, "first_name": "Sam", "last_name": "Reed", "name": "Sam Reed",
            "title": "CFO", "email": "sam@alpha.com", "email_status": "verified",
            "linkedin_url": "http://linkedin.com/in/sam", "departments": ["master_finance"],
            "organization": {"id": "org-A", "name": "Alpha"},
        },
    )
    seen_enrichment: list[dict] = []

    def _pscore(**k):
        seen_enrichment.append(k.get("enrichment") or {})
        return {
            "subscores": {"persona_fit": 5, "authority": 5, "trigger": 5, "reachability": 5},
            "reason": "CFO — economic buyer", "flags": [], "cost_usd": 0.0,
        }

    monkeypatch.setattr(fit, "prospect_score_v2", _pscore)

    res = run_enrich_score_prospects(
        db, tenant.id, {"identity_keys": ["apollo:ppl-99"], "slug": slug}
    )
    assert res == {
        "requested": 1, "enriched": 1, "credits_spent": 1, "enrich_failed": 0,
        "skipped_excluded": 0, "scored": 1, "failed": 0, "cost_usd": 0.0,
    }, res
    # (1) Reveal ran BEFORE score — the scorer saw the revealed email, not the pre-reveal blank.
    assert seen_enrichment, "people scorer was never called"
    assert seen_enrichment[0]["email"] == "sam@alpha.com"
    assert seen_enrichment[0]["email_present"] is True
    # (2) The row is both enriched (email/status) AND scored contact_now — pre-reveal it would have
    # gated to low_fit/data_unusable (has_contact=False); reveal-first unlocks the real score.
    db.refresh(person)
    assert person.status == "scored"
    assert person.enrichment["email"] == "sam@alpha.com" and person.email_valid is True
    assert person.label == "contact_now" and person.score_total == 20
    db.close()


def test_enrich_score_skips_person_under_excluded_company(owner_member, monkeypatch):
    """R8 — a person under an `excluded_by_rules` company is skipped pre-enrich (no Apollo match, no
    credit spent) and still labeled `excluded_by_rules` by the free gate. If either the paid match
    or the paid people-score is reached for this row, the stubs fail the test."""
    from sqlalchemy import select

    from app.core.db import get_session
    from app.domains.prospects import fit
    from app.domains.prospects.router import run_enrich_score_prospects
    from app.integrations.apollo import client as apollo
    from app.models import Company, Prospect, Tenant

    _client, slug, _token, icp_id = owner_member
    db = get_session()
    tenant = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one()

    company = Company(
        tenant_id=tenant.id, icp_id=uuid.UUID(icp_id), domain="dead.com", name="Dead",
        source="apollo", status="people_found", label="excluded_by_rules",
    )
    db.add(company)
    db.flush()
    person = Prospect(
        tenant_id=tenant.id, icp_id=uuid.UUID(icp_id), company_id=company.id,
        identity_key="apollo:ppl-x", apollo_person_id="ppl-x", source="apollo",
        status="found", enrichment={"first_name": "Nope", "title": "CFO"},
    )
    db.add(person)
    db.commit()

    monkeypatch.setattr(
        apollo, "match_person",
        lambda *a, **k: pytest.fail("match_person called for a row under an excluded company"),
    )
    monkeypatch.setattr(
        fit, "prospect_score_v2",
        lambda **k: pytest.fail("paid people-score reached a parent-excluded row"),
    )

    res = run_enrich_score_prospects(
        db, tenant.id, {"identity_keys": ["apollo:ppl-x"], "slug": slug}
    )
    assert res["credits_spent"] == 0 and res["enriched"] == 0
    assert res["skipped_excluded"] == 1
    db.refresh(person)
    assert person.label == "excluded_by_rules"  # labeled by the free gate, no spend
    assert person.email_valid is False and not (person.enrichment or {}).get("email")
    db.close()


def test_resume_page_survives_interleaved_nonfind_runs(owner_member):
    """R22b — 50 rescore/enrich runs after a company-find must NOT evict the find cursor: the scan
    is scoped to company-find sources, so the cursor still resolves (page 3 → resume at 4)."""
    from sqlalchemy import select

    from app.core.db import get_session
    from app.domains.prospects.router import _body_hash, _resume_page
    from app.integrations.apollo import client as apollo
    from app.models import ResearchRun, Tenant

    _client, slug, _token, _icp = owner_member
    db = get_session()
    tenant = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one()

    bh = _body_hash({"q_organization_keyword_tags": ["fintech"]})
    db.add(ResearchRun(
        tenant_id=tenant.id, run_id=f"find-{uuid.uuid4().hex[:8]}", source="apollo",
        result_meta={"body_hash": bh, "page_cursor": 3, "per_page": apollo.PER_PAGE_MAX},
    ))
    db.commit()
    for i in range(50):  # would evict the find run from an all-source latest-50 window
        db.add(ResearchRun(
            tenant_id=tenant.id, run_id=f"rs-{i}-{uuid.uuid4().hex[:6]}",
            source="rescore" if i % 2 else "enrich", result_meta={},
        ))
    db.commit()

    resume, exhausted, _meta = _resume_page(db, tenant.id, bh)
    assert resume == 4 and exhausted is False  # cursor survived the interleave
    db.close()


def test_refind_advances_cursor_and_skips_known(owner_member, monkeypatch):
    """D+ Stage 3 — a repeat find of the SAME scope resumes at the next page (never re-buys page 1),
    the known-org skip drops page-overlap rows, and a returning row costs $0 (no re-classify)."""
    from app.domains.prospects import fit
    from app.integrations.apollo import client as apollo

    client, slug, token, icp_id = owner_member
    _patch_apollo_and_fit(monkeypatch, orgs=[], people=[], match={})  # base stubs; overridden below
    monkeypatch.setattr(apollo, "enrich_organizations", lambda domains: [])  # search rows suffice

    pages: list[int] = []

    def _paged(body, *, max_results=100, start_page=1):
        pages.append(start_page)
        if start_page == 1:
            rows = [{"id": "org-1", "name": "One", "primary_domain": "one.com"}]
        else:  # page 2: Apollo ordering drift re-surfaces org-1 (overlap) + a genuinely new org-2
            rows = [
                {"id": "org-1", "name": "One", "primary_domain": "one.com"},
                {"id": "org-2", "name": "Two", "primary_domain": "two.com"},
            ]
        # per_page mirrors the real _paginate meta (R1) — without it the stored cursor reads as an
        # unknown page size and run 2 restarts at page 1 (served from the warm cache) instead of
        # resuming at page 2.
        meta = {"total_entries": 5, "breadcrumbs": [], "pages_fetched": 1,
                "end_page": start_page, "total_pages": 5, "per_page": apollo.PER_PAGE_MAX}
        return rows, meta

    classified: list[dict] = []

    def _classify(**k):
        classified.append(k.get("company") or {})
        return {"business_model": "B2B", "llm_call_id": None, "model": "t", "cost_usd": 0.0}

    monkeypatch.setattr(apollo, "search_companies_meta", _paged)
    monkeypatch.setattr(fit, "classify_business_model", _classify)

    # Run 1 — fetches page 1 (org-1), classifies it once.
    r1 = _find_company(client, slug, token, {"limit": 10, "icp_id": icp_id})
    assert r1["status"] == "done", r1["error"]
    assert pages == [1] and r1["found"] == 1
    assert len(classified) == 1  # org-1 classified

    # Run 2 — the cursor resumes at page 2 (page 1 never re-bought); org-1 re-surfaces but is
    # known-skipped ($0: NOT re-classified), only the NEW org-2 lands and is classified.
    r2 = _find_company(client, slug, token, {"limit": 10, "icp_id": icp_id})
    assert pages == [1, 2]  # resumed at page 2 — the cursor advanced
    assert r2["found"] == 1 and r2["known_skipped"] == 1  # only org-2 is new; org-1 skipped
    assert len(classified) == 2  # +1 (org-2 only) — org-1 was NOT re-classified (the $0 invariant)
    assert not r2["scope_exhausted"]  # page 2 of 5 — more to walk
    domains = {c["domain"] for c in r2["companies"]}
    assert domains == {"one.com", "two.com"}  # both stored exactly once


def test_find_company_requires_spec(owner_member, monkeypatch):
    """A tenant whose only spec lacks company params can't run Flow A (no guesswork)."""
    client, slug, token, _icp_id = owner_member
    # Override the seeded spec path: point find at a fresh tenant would be heavy; instead assert the
    # select-first guard for people, which needs no Apollo at all.
    r = client.post(f"/{slug}/people/find-people", json={}, headers=_auth(token))
    assert r.status_code == 400
    assert "select companies first" in r.text


def test_prospect_fit_prompt_zero_prospects_ok(owner_member):
    """R7 — the prospect-fit preview on a fresh tenant (zero prospects) must return 200. It used to
    500 (AttributeError) because `prospect.enrichment` was dereferenced outside the None-guard."""
    client, slug, token, _icp_id = owner_member  # this tenant has an ICP + spec but NO prospects
    r = client.get(f"/{slug}/fit-prompt?stage=prospect_fit", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["company"] is None  # no sample prospect to preview


# --------------------------------------------------------------------- multi-ICP (spec v4)


@pytest.fixture
def owner_member_v4():
    """An ephemeral tenant with TWO ICPs + a v4 per-ICP ResearchSpec — the multi-ICP loop.

    Each ICP block carries deliberately different company keywords and people personas, so a test
    can prove the find flows run ICP by ICP (block A's params never leak into an ICP-B find)."""
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.core.security import hash_password
    from app.main import app
    from app.models import AppUser, Icp, Membership, MembershipRole, ResearchSpec, Tenant

    client = TestClient(app)
    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    slug, email = f"micp-{suffix}", f"micp-{suffix}@example.com"
    tenant = Tenant(slug=slug, name=f"MultiICP {suffix}")
    db.add(tenant)
    db.flush()
    user = AppUser(email=email, password_hash=hash_password(BUILD_PW), full_name="Owner")
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.owner))
    icp_a = Icp(tenant_id=tenant.id, name="Insurers", tag="primary", data={"maturity": "growth"})
    icp_b = Icp(tenant_id=tenant.id, name="Brokers", tag="secondary", data={})
    db.add_all([icp_a, icp_b])
    db.flush()
    ids = (str(icp_a.id), str(icp_b.id))
    db.add(
        ResearchSpec(
            tenant_id=tenant.id,
            version=1,
            spec={
                "spec_version": 4,
                "icp_targeting": [
                    {
                        "icp_id": ids[0],
                        "icp_name": "Insurers",
                        "company_search_params": {"q_organization_keyword_tags": ["insurance"]},
                        "people_search_params": {
                            "person_seniorities": ["c_suite"],
                            "person_department_or_subdepartments": ["master_sales"],
                        },
                        "intent_filters": {},
                    },
                    {
                        "icp_id": ids[1],
                        "icp_name": "Brokers",
                        "company_search_params": {"q_organization_keyword_tags": ["brokerage"]},
                        "people_search_params": {
                            "person_seniorities": ["manager"],
                            "person_department_or_subdepartments": ["master_operations"],
                        },
                        "intent_filters": {},
                    },
                ],
                "icp_validation": {},
                "credit_policy": {"max_companies": 500},
            },
        )
    )
    db.commit()
    token = client.post("/auth/login", json={"email": email, "password": BUILD_PW}).json()[
        "access_token"
    ]
    try:
        yield client, slug, token, ids
    finally:
        db.delete(icp_a)
        db.delete(icp_b)
        db.delete(user)
        db.delete(tenant)
        db.commit()
        db.close()


def test_multi_icp_find_runs_icp_by_icp(owner_member_v4, monkeypatch):
    """Spec v4: find-company requires an ICP, runs THAT ICP's params, labels the rows; find-people
    resolves each company's personas from its OWN ICP block in a single mixed-selection call."""
    from app.domains.prospects import fit
    from app.integrations.apollo import client as apollo

    client, slug, token, (icp_a, icp_b) = owner_member_v4

    company_bodies: list[dict] = []
    people_bodies: list[dict] = []

    def _search_companies_meta(body, *, max_results=100, start_page=1):
        company_bodies.append(body)
        if "insurance" in (body.get("q_organization_keyword_tags") or []):
            rows = [{"id": "org-A", "name": "Alpha Ins", "primary_domain": "alpha-ins.com"}]
        else:
            rows = [{"id": "org-B", "name": "Beta Brokers", "primary_domain": "beta-brokers.com"}]
        return rows, {
            "total_entries": len(rows), "breadcrumbs": [], "pages_fetched": 1,
            "end_page": start_page,
        }

    def _search_people(body, *, max_results=100):
        people_bodies.append(body)
        org = (body.get("organization_ids") or ["?"])[0]
        return [
            {"id": f"ppl-{org}", "first_name": "Kim", "title": "Buyer",
             "organization": {"name": org}, "has_email": True}
        ]

    monkeypatch.setattr(apollo, "search_companies_meta", _search_companies_meta)
    # Healthy count → the Stage 1b relax ladder stays dormant, so each ICP's executed body is the
    # un-relaxed one this test asserts on (keyword-tag routing intact).
    monkeypatch.setattr(apollo, "count_companies", lambda body: 500)
    monkeypatch.setattr(apollo, "enrich_organizations", lambda domains: [])
    monkeypatch.setattr(apollo, "search_people", _search_people)
    monkeypatch.setattr(
        fit, "classify_business_model",
        lambda **k: {"business_model": "B2B", "llm_call_id": None, "model": "t", "cost_usd": 0.0},
    )

    # 1) A multi-ICP scope refuses an un-scoped find — never a silent merge. (The async find
    #    surfaces the guard as the job's error, not an HTTP 4xx — the check is in the core fn.)
    res = _find_company(client, slug, token, {"limit": 5})
    assert res["status"] == "error"
    assert "pick an ICP" in (res["error"] or "")

    # 2) Find for ICP-A runs block A's params only; rows land labeled icp_id=A.
    body = _find_company(client, slug, token, {"limit": 5, "icp_id": icp_a})
    assert body["status"] == "done", body["error"]
    a_rows = [c for c in body["companies"] if c["icp_id"] == icp_a]
    assert company_bodies[-1]["q_organization_keyword_tags"] == ["insurance"]
    assert a_rows and all(c["icp_id"] == icp_a for c in a_rows)

    # 3) Find for ICP-B runs block B's params; rows labeled icp_id=B.
    body = _find_company(client, slug, token, {"limit": 5, "icp_id": icp_b})
    assert body["status"] == "done", body["error"]
    b_rows = [c for c in body["companies"] if c["icp_id"] == icp_b]
    assert company_bodies[-1]["q_organization_keyword_tags"] == ["brokerage"]
    assert b_rows and all(c["icp_id"] == icp_b for c in b_rows)

    # 4a) An UNOWNED icp_id is rejected at the door (L8 — parse + tenant-owned-or-404), never routed
    #     to another ICP's block or enqueued.
    r = client.post(
        f"/{slug}/companies/find-company-async",
        json={"limit": 5, "icp_id": str(uuid.uuid4())},
        headers=_auth(token),
    )
    assert r.status_code == 404 and "no such ICP" in r.text

    # 4b) An OWNED icp with no targeting block in the v4 spec is a named "regenerate" error (the
    #     worker resolves no block — never silently borrows another ICP's params).
    from sqlalchemy import select as _select

    from app.core.db import get_session
    from app.models import Icp as _Icp
    from app.models import Tenant as _Tenant

    _db = get_session()
    _tid = _db.execute(_select(_Tenant.id).where(_Tenant.slug == slug)).scalar_one()
    _extra = _Icp(tenant_id=_tid, name="Unscoped", tag="tertiary", data={})
    _db.add(_extra)
    _db.flush()
    _extra_id = str(_extra.id)
    _db.commit()
    _db.close()
    res = _find_company(client, slug, token, {"limit": 5, "icp_id": _extra_id})
    assert res["status"] == "error" and "regenerate" in (res["error"] or "")

    # 5) Find-people across BOTH companies in one call: each org is searched with its OWN ICP's
    #    personas (A → c_suite/sales; B → manager/operations) and each prospect inherits its
    #    company's ICP label.
    ids = [a_rows[0]["id"], b_rows[0]["id"]]
    r = client.post(f"/{slug}/people/find-people",
                    json={"per_company": 5, "company_ids": ids}, headers=_auth(token))
    assert r.status_code == 200, r.text
    by_org = {(b.get("organization_ids") or ["?"])[0]: b for b in people_bodies}
    assert by_org["org-A"]["person_seniorities"] == ["c_suite"]
    assert by_org["org-A"]["person_department_or_subdepartments"] == ["master_sales"]
    assert by_org["org-B"]["person_seniorities"] == ["manager"]
    assert by_org["org-B"]["person_department_or_subdepartments"] == ["master_operations"]
    people = r.json()["prospects"]
    assert {p["icp_id"] for p in people} == {icp_a, icp_b}  # label inherited per company
