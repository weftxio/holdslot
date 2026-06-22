"""B4/B6 tests — Brief → ResearchSpec structuring.

Unit tests validate the v3 (Apollo-native) contract + the assemble/credit-policy split (no I/O).
Gated integration tests run real structuring against dev: a filled brief yields a schema-valid,
versioned spec with gaps and resolvable telemetry, and the credit policy is server-set.
"""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from app.domains.briefs import research_spec as RS


def _company_params() -> dict:
    return {
        "q_organization_keyword_tags": ["insurance", "insurtech"],
        "organization_num_employees_ranges": ["10,100"],
        "organization_locations": ["hong kong", "singapore"],
        "revenue_range": {"min": None, "max": None},
    }


def _people_params() -> dict:
    return {
        "person_titles": ["head of growth", "head of sales"],
        "include_similar_titles": False,
        "q_keywords": "insurance insurtech",
        "person_seniorities": ["c_suite", "vp", "head"],
        "organization_locations": ["hong kong", "singapore"],
        "organization_num_employees_ranges": ["10,100"],
    }


def _valid_targeting() -> dict:
    return {
        "company_search_params": _company_params(),
        "people_search_params": _people_params(),
        "intent_filters": {
            "company": {
                "latest_funding_date_range": {"min": "2025-12-22", "max": "2026-06-22"},
                "q_organization_job_titles": ["sales", "growth"],
                "organization_job_posted_at_range": {"min": "2026-03-22", "max": "2026-06-22"},
            },
            "recency_window": {"funding_since": "2025-12-22", "jobs_posted_since": "2026-03-22"},
        },
        "icp_validation": {"customer_profiles": [], "paying_customer_summary": ""},
        "icp_suggestions": [
            {
                "name": "Enterprise insurers (paying-customer lookalike)",
                "rationale": "Resolved customers skew larger than the stated SMB ICP.",
                "evidencing_customers": ["aia.com", "prudential.com"],
                "confidence": "low",
                "company_search_params": _company_params(),
                "people_search_params": _people_params(),
            }
        ],
        "gaps": [
            {
                "field": "excludeCustomers",
                "why_it_matters": "Existing customers are the strongest proof of who buys.",
                "ask": "Share current customers as 'domain, name, website'.",
            }
        ],
    }


def test_v3_accepts_canonical_targeting():
    RS.ResearchSpecV3(**_valid_targeting())  # must not raise


def test_v3_rejects_missing_group():
    bad = _valid_targeting()
    del bad["company_search_params"]
    with pytest.raises(ValidationError):
        RS.ResearchSpecV3(**bad)


def test_v3_rejects_extra_field_and_missing_nested():
    # extra="forbid": an unknown root key is rejected.
    with pytest.raises(ValidationError):
        RS.ResearchSpecV3(**{**_valid_targeting(), "surprise": 1})
    # a missing NESTED field (recency_window) is rejected — validator is as strict as the schema.
    bad = _valid_targeting()
    del bad["intent_filters"]["recency_window"]
    with pytest.raises(ValidationError):
        RS.ResearchSpecV3(**bad)


def test_seniority_enum_in_people_schema():
    # The json_schema constrains person_seniorities to the Apollo enum (the Pydantic validator is
    # list[str], so this guards the schema the model is actually held to).
    ppl = RS.RESEARCH_SPEC_JSON_SCHEMA["schema"]["properties"]["people_search_params"]
    assert ppl["properties"]["person_seniorities"]["items"]["enum"] == RS.SENIORITY_ENUM


def test_validator_matches_json_schema_root_keys():
    # The defensive validator and the schema sent to the model can't drift apart.
    schema_keys = set(RS.RESEARCH_SPEC_JSON_SCHEMA["schema"]["properties"].keys())
    model_keys = set(RS.ResearchSpecV3.model_fields.keys())
    assert schema_keys == model_keys
    cs_schema = set(
        RS.RESEARCH_SPEC_JSON_SCHEMA["schema"]["properties"]["company_search_params"][
            "properties"
        ].keys()
    )
    cs_model = set(RS.CompanySearchParams.model_fields.keys())
    assert cs_schema == cs_model


def test_assemble_merges_server_credit_policy_not_llm():
    targeting = _valid_targeting()
    # Even if the model tried to set a credit policy, assemble must use the server's.
    targeting["credit_policy"] = {"email_status_filter": ["unverified"], "evil": True}
    spec, gaps, icp_suggestions = RS.assemble_spec(targeting)
    assert spec["credit_policy"] == RS.CREDIT_POLICY  # server-set, deterministic
    assert spec["credit_policy"]["email_status_filter"] == ["verified"]
    assert spec["credit_policy"]["phone"] is False
    assert spec["spec_version"] == RS.SPEC_VERSION == 3
    assert spec["company_search_params"]["q_organization_keyword_tags"] == [
        "insurance",
        "insurtech",
    ]
    assert "icp_validation" in spec  # analysis travels in the spec, not its own column
    assert gaps and gaps[0]["field"] == "excludeCustomers"
    # icp_suggestions are split out alongside gaps — never folded into the Apollo-bound spec.
    assert "icp_suggestions" not in spec
    assert icp_suggestions and icp_suggestions[0]["confidence"] == "low"


def test_json_schema_is_strict():
    s = RS.RESEARCH_SPEC_JSON_SCHEMA
    assert s["strict"] is True
    root = s["schema"]
    assert root["additionalProperties"] is False
    assert set(root["required"]) == {
        "company_search_params",
        "people_search_params",
        "intent_filters",
        "icp_validation",
        "icp_suggestions",
        "gaps",
    }


def test_build_messages_injects_today():
    msgs = RS.build_messages({"companyName": "X"}, [], today="2026-06-22")
    assert msgs[0]["role"] == "system"
    assert '"today": "2026-06-22"' in msgs[1]["content"]


def test_default_prompt_matches_seed_file():
    # The code fallback (runtime) and the migration's DB seed source must be identical, or a saved
    # default would differ from the seeded `briefing` v1. They have no other binding — assert it.
    from pathlib import Path

    seed = (
        Path(__file__).resolve().parents[3] / "docs" / "prompts" / "brief-structure-v5.md"
    ).read_text(encoding="utf-8")
    assert seed.strip() == RS.DEFAULT_SYSTEM_PROMPT.strip()


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
        # A deliberately thin brief (no customer list) → expect gaps, empty icp_suggestions.
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

        import time

        def run_structuring() -> dict:
            """POST (async, 202) then poll the worker to a terminal job (Pro is slow ~60-80s)."""
            r = client.post(f"/{slug}/brief/structure", headers=auth)
            assert r.status_code == 202, r.text
            assert r.json()["status"] in ("queued", "running")
            deadline = time.monotonic() + 240
            st = r.json()
            while time.monotonic() < deadline:
                st = client.get(f"/{slug}/brief/structure/status", headers=auth).json()
                if st["status"] in ("done", "error"):
                    break
                time.sleep(3)
            assert st["status"] == "done", st
            return st

        j1 = run_structuring()
        assert j1["spec_version"] == 1
        latest = client.get(f"/{slug}/research-spec", headers=auth).json()
        s1 = latest["latest"]
        assert s1["version"] == 1
        # Schema-valid v3 spec, server-set credit policy, real gaps.
        assert s1["spec"]["spec_version"] == 3
        assert s1["spec"]["credit_policy"]["email_status_filter"] == ["verified"]
        assert "company_search_params" in s1["spec"] and "people_search_params" in s1["spec"]
        assert "intent_filters" in s1["spec"] and "icp_validation" in s1["spec"]
        assert isinstance(s1["gaps"], list) and len(s1["gaps"]) >= 1
        assert s1["llm_call_id"]

        # Telemetry resolves to a real ok call.
        row = db.get(LlmCall, s1["llm_call_id"])
        assert row is not None and row.status == "ok" and row.purpose == "brief_structure"

        # Re-run appends v2; v1 is untouched.
        j2 = run_structuring()
        assert j2["spec_version"] == 2
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
