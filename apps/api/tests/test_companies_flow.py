"""Phase C two-stage E2E — company-first flow against the live dev Aurora (+ real LLM scoring).

Skipped without the DB env (like test_briefs_icps). Proves the whole stage-1→stage-2 path:
Find-Companies import → company-fit score → manual add → Find-People import (company_id link by
domain, `found` unenriched) → enrich gate (confirm → export) → enriched re-import flips to
`scored`. Uses an ephemeral tenant with a tiny seeded fit rubric; torn down after.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("HOLDSLOT_DB_CLUSTER_ARN"),
    reason="integration test — needs Aurora dev env (HOLDSLOT_DB_* + AWS creds)",
)

BUILD_PW = "tryholdslot1!"
RUBRIC = (
    "Score company industry/size/maturity/tech, persona title/seniority/department/economic_buyer, "
    "timing triggers, and data deliverability/completeness. Award full points for a strong match."
)


def _auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


@pytest.fixture
def ephemeral_owner():
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.core.security import hash_password
    from app.main import app
    from app.models import AppUser, Membership, MembershipRole, SourcingDoc, Tenant

    client = TestClient(app)
    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    slug = f"cc-{suffix}"
    email = f"cc-{suffix}@example.com"

    tenant = Tenant(slug=slug, name=f"CC {suffix}")
    db.add(tenant)
    db.flush()
    user = AppUser(email=email, password_hash=hash_password(BUILD_PW), full_name="CC Owner")
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.owner))
    db.add(SourcingDoc(tenant_id=tenant.id, kind="fit_rubric", version=1, body=RUBRIC))
    db.commit()

    token = client.post("/auth/login", json={"email": email, "password": BUILD_PW}).json()[
        "access_token"
    ]
    try:
        yield client, slug, token
    finally:
        db.delete(user)
        db.delete(tenant)
        db.commit()
        db.close()


def test_company_first_two_stage_flow(ephemeral_owner):
    client, slug, token = ephemeral_owner
    h = _auth(token)

    # Stage 1 — Find Companies import (free sourcing; scoring is the only $).
    companies_csv = (
        "Company,Website,Company LinkedIn,Industry,Employee Count,Country\n"
        "Acme Robotics,https://www.acme.com,https://linkedin.com/company/acme,Robotics,250,US\n"
    )
    r = client.post(f"/{slug}/companies/import", json={"csv": companies_csv}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["scored"] == 1

    companies = client.get(f"/{slug}/companies", headers=h).json()
    assert len(companies) == 1
    acme = companies[0]
    assert acme["domain"] == "acme.com" and acme["fit_score"] is not None
    assert acme["website"] == "https://www.acme.com"  # raw URL kept distinct from the domain key
    assert acme["status"] == "discovered" and acme["source"] == "clay"

    # Stage 1 — manual add a second company (same schema, source=manual).
    r = client.post(
        f"/{slug}/companies",
        json={"domain": "beta.io", "name": "Beta Inc", "industry": "SaaS"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "manual" and r.json()["fit_score"] is not None

    # Stage 2 — Find People import (operator-sourced: no run_id/identity_key, no work email yet).
    people_csv = (
        "full_name,domain,linkedin_url,Title,target_seniority\n"
        "Jane Doe,acme.com,linkedin.com/in/jane-doe-cc,VP Engineering,VP\n"
    )
    r = client.post(f"/{slug}/prospects/import", json={"csv": people_csv}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["scored"] == 1

    prospects = client.get(f"/{slug}/prospects", headers=h).json()
    assert len(prospects) == 1
    jane = prospects[0]
    assert jane["identity_key"] == "li:jane-doe-cc"
    assert jane["company_id"] == acme["id"]  # linked by domain
    assert jane["status"] == "found" and jane["email"] == ""  # unenriched, but scored
    assert jane["linkedin_url"] == "linkedin.com/in/jane-doe-cc"  # surfaced for the People column
    assert jane["fit_score"] is not None

    # Company flips to people_found once a person links to it.
    acme_after = next(
        c for c in client.get(f"/{slug}/companies", headers=h).json() if c["domain"] == "acme.com"
    )
    assert acme_after["status"] == "people_found"

    # Enrich gate — confirm who to enrich → returns the export list for the Clay waterfall.
    r = client.post(
        f"/{slug}/prospects/enrich", json={"identity_keys": ["li:jane-doe-cc"]}, headers=h
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["confirmed"] == 1 and body["export"][0]["identity_key"] == "li:jane-doe-cc"
    assert client.get(f"/{slug}/prospects", headers=h).json()[0]["status"] == "confirmed"

    # Enriched re-import — same person now carries a validated work email → flips to scored.
    enriched_csv = (
        "full_name,domain,linkedin_url,Title,target_seniority,Work Email,Validate Findymail\n"
        "Jane Doe,acme.com,linkedin.com/in/jane-doe-cc,VP Engineering,VP,jane@acme.com,valid\n"
    )
    r = client.post(f"/{slug}/prospects/import", json={"csv": enriched_csv}, headers=h)
    assert r.status_code == 200, r.text
    jane2 = client.get(f"/{slug}/prospects", headers=h).json()[0]
    assert jane2["status"] == "scored" and jane2["email"] == "jane@acme.com"
    assert jane2["email_valid"] is True
