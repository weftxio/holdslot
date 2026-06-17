"""B4 tests — Brief → ResearchSpec structuring.

Unit tests validate the v1 contract + the assemble/credit-policy split (no I/O). Gated
integration tests run real structuring against dev: a filled brief yields a schema-valid,
versioned spec with gaps and resolvable telemetry, and the credit policy is server-set.
"""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from app.domains.briefs import research_spec as RS


def _valid_targeting() -> dict:
    return {
        "company_search": {
            "industries_include": ["Logistics"],
            "industries_exclude": [],
            "description_keywords_include": [],
            "description_keywords_exclude": [],
            "semantic_description": "Mid-market 3PL operators",
            "employee_count": {"min": 50, "max": 500},
            "revenue_usd": {"min": None, "max": None},
            "company_types": [],
            "founded": {"after": None, "before": None},
            "locations_include": {"countries": ["Netherlands"], "states": [], "cities": []},
            "locations_exclude": {"countries": [], "states": [], "cities": []},
            "technographics": {"enabled": False, "vendors": []},
            "max_results": 500,
        },
        "people_search": [
            {
                "icp_id": "ops",
                "job_title_keywords": ["VP of Operations"],
                "job_title_match_mode": "is_similar",
                "job_title_exclude": [],
                "seniority": ["VP"],
                "departments": ["Operations"],
                "max_per_company": 2,
                "max_total": 800,
            }
        ],
        "exclusions": {"domains": [], "company_linkedin_urls": [], "emails": []},
        "gaps": [{"field": "revenue_usd", "why": "unknown budget", "ask": "What ACV?"}],
        "icp_suggestions": [
            {
                "name": "Enterprise 3PLs (paying-customer lookalike)",
                "rationale": "Existing customers skew larger than the stated mid-market ICP.",
                "resembles_stated_icp": False,
                "evidence_companies": ["dhl.com", "kuehne-nagel.com"],
                "suggested_industries": ["Logistics"],
                "suggested_titles": ["VP of Supply Chain"],
                "confidence": "low",
            }
        ],
    }


def test_v1_accepts_canonical_targeting():
    RS.ResearchSpecV1(**_valid_targeting())  # must not raise


def test_v1_rejects_missing_group():
    bad = _valid_targeting()
    del bad["company_search"]
    with pytest.raises(ValidationError):
        RS.ResearchSpecV1(**bad)


def test_v1_rejects_extra_field_and_missing_nested():
    # extra="forbid": an unknown root key is rejected.
    with pytest.raises(ValidationError):
        RS.ResearchSpecV1(**{**_valid_targeting(), "surprise": 1})
    # a missing NESTED field (revenue_usd) is rejected — validator is as strict as the schema.
    bad = _valid_targeting()
    del bad["company_search"]["revenue_usd"]
    with pytest.raises(ValidationError):
        RS.ResearchSpecV1(**bad)


def test_validator_matches_json_schema_root_keys():
    # The defensive validator and the schema sent to the model can't drift apart.
    schema_keys = set(RS.RESEARCH_SPEC_JSON_SCHEMA["schema"]["properties"].keys())
    model_keys = set(RS.ResearchSpecV1.model_fields.keys())
    assert schema_keys == model_keys
    cs_schema = set(
        RS.RESEARCH_SPEC_JSON_SCHEMA["schema"]["properties"]["company_search"]["properties"].keys()
    )
    cs_model = set(RS.CompanySearchV1.model_fields.keys())
    assert cs_schema == cs_model


def test_assemble_merges_server_credit_policy_not_llm():
    targeting = _valid_targeting()
    # Even if the model tried to set a credit policy, assemble must use the server's.
    targeting["credit_policy"] = {"test_batch_size": 9999, "evil": True}
    spec, gaps, icp_suggestions = RS.assemble_spec(targeting)
    assert spec["credit_policy"] == RS.CREDIT_POLICY  # server-set, deterministic
    assert spec["credit_policy"]["test_batch_size"] == 10
    assert spec["spec_version"] == RS.SPEC_VERSION
    assert spec["company_search"]["industries_include"] == ["Logistics"]
    assert gaps and gaps[0]["field"] == "revenue_usd"
    # icp_suggestions are split out alongside gaps — never folded into the Clay-bound spec.
    assert "icp_suggestions" not in spec
    assert icp_suggestions and icp_suggestions[0]["resembles_stated_icp"] is False


def test_json_schema_is_strict():
    s = RS.RESEARCH_SPEC_JSON_SCHEMA
    assert s["strict"] is True
    root = s["schema"]
    assert root["additionalProperties"] is False
    # All five groups are required at the root.
    assert set(root["required"]) == {
        "company_search",
        "people_search",
        "exclusions",
        "gaps",
        "icp_suggestions",
    }


# --- gated integration ---------------------------------------------------------

_DB = os.environ.get("HOLDSLOT_DB_CLUSTER_ARN")


@pytest.mark.skipif(not _DB, reason="integration — needs Aurora dev env + OpenRouter key")
def test_structure_endpoint_versions_and_links_telemetry():
    import uuid

    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.core.security import hash_password
    from app.main import app
    from app.models import AppUser, LlmCall, Membership, MembershipRole, ResearchSpec, Tenant

    client = TestClient(app)
    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    slug = f"b4-{suffix}"
    email = f"b4-{suffix}@example.com"
    tenant = Tenant(slug=slug, name=f"B4 {suffix}")
    db.add(tenant)
    db.flush()
    user = AppUser(email=email, password_hash=hash_password("tryholdslot1!"), full_name="B4")
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.owner))
    db.commit()
    auth = {
        "authorization": "Bearer "
        + client.post("/auth/login", json={"email": email, "password": "tryholdslot1!"}).json()[
            "access_token"
        ]
    }

    try:
        # A deliberately thin brief → expect gaps.
        client.put(
            f"/{slug}/brief",
            json={
                "data": {
                    "companyName": "Northwind Robotics",
                    "sell": "Warehouse robotics for 3PL logistics operators",
                    "problem": "Manual picking is slow and error-prone",
                }
            },
            headers=auth,
        )
        client.post(
            f"/{slug}/icps",
            json={"name": "Ops leader", "tag": "primary", "data": {"titles": ["VP Operations"]}},
            headers=auth,
        )

        r1 = client.post(f"/{slug}/brief/structure", headers=auth)
        assert r1.status_code == 200, r1.text
        s1 = r1.json()
        assert s1["version"] == 1
        # Schema-valid, server-set credit policy, real gaps.
        assert s1["spec"]["spec_version"] == 1
        assert s1["spec"]["credit_policy"]["test_batch_size"] == 10
        assert "company_search" in s1["spec"] and "people_search" in s1["spec"]
        assert isinstance(s1["gaps"], list) and len(s1["gaps"]) >= 1
        assert s1["llm_call_id"]

        # Telemetry resolves to a real ok call.
        row = db.get(LlmCall, s1["llm_call_id"])
        assert row is not None and row.status == "ok" and row.purpose == "brief_structure"

        # Re-run appends v2; v1 is untouched.
        r2 = client.post(f"/{slug}/brief/structure", headers=auth)
        assert r2.json()["version"] == 2

        latest = client.get(f"/{slug}/research-spec", headers=auth).json()
        assert latest["latest"]["version"] == 2
        assert latest["versions"] == [2, 1]
        versions = db.execute(
            ResearchSpec.__table__.select().where(ResearchSpec.tenant_id == tenant.id)
        ).fetchall()
        assert len(versions) == 2
    finally:
        db.delete(user)
        db.delete(tenant)  # research_spec + icp + brief cascade
        db.commit()
        db.close()
