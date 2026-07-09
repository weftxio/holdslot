"""B4/B6 tests — Brief → ResearchSpec structuring.

Unit tests validate the v4 (per-ICP Apollo-native) contract + the assemble/credit-policy split,
the `targeting_for_icp` resolver (v4 match + v3 fallback), and `reconcile_icp_targeting` (the
coverage guard that makes the original "second ICP silently dropped" bug impossible). No I/O.
Gated integration tests run real structuring against dev: a filled brief yields a schema-valid,
versioned spec with gaps and resolvable telemetry, and the credit policy is server-set.
"""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from app.domains.briefs import research_spec as RS

ICP_A = "11111111-1111-1111-1111-111111111111"
ICP_B = "22222222-2222-2222-2222-222222222222"


def _company_params() -> dict:
    return {
        "q_organization_keyword_tags": ["insurance", "insurtech"],
        "organization_num_employees_ranges": ["10,100"],
        "organization_locations": ["hong kong", "singapore"],
        "revenue_range": {"min": None, "max": None},
    }


def _people_params() -> dict:
    return {
        "person_titles": ["Head of Sales", "VP Sales", "Chief Revenue Officer"],
        "person_seniorities": ["c_suite", "vp", "head"],
        "person_department_or_subdepartments": ["master_sales", "master_marketing"],
        "q_keywords": "insurance insurtech",
        "organization_locations": ["hong kong", "singapore"],
        "organization_num_employees_ranges": ["10,100"],
    }


def _intent_filters() -> dict:
    # v5: hiring titles only — the funding/jobs-posted date windows are gone from the contract.
    return {"company": {"q_organization_job_titles": ["sales", "growth"]}}


def _block(icp_id: str = ICP_A, icp_name: str = "Insurers") -> dict:
    return {
        "icp_id": icp_id,
        "icp_name": icp_name,
        "company_search_params": _company_params(),
        "people_search_params": _people_params(),
        "intent_filters": _intent_filters(),
    }


def _valid_targeting() -> dict:
    return {
        "icp_targeting": [_block(), _block(ICP_B, "Brokers")],
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
                "icp_name": "",
            }
        ],
    }


def test_v4_accepts_canonical_targeting():
    RS.ResearchSpecV4(**_valid_targeting())  # must not raise


def test_v4_rejects_missing_group():
    bad = _valid_targeting()
    del bad["icp_targeting"]
    with pytest.raises(ValidationError):
        RS.ResearchSpecV4(**bad)


def test_v4_rejects_extra_field_and_missing_nested():
    # extra="forbid": an unknown root key is rejected.
    with pytest.raises(ValidationError):
        RS.ResearchSpecV4(**{**_valid_targeting(), "surprise": 1})
    # a missing NESTED field (a block's intent company) is rejected — validator is as strict as
    # the schema, per targeting entry. An extra nested date field is rejected too (v5 removed the
    # funding/jobs windows from the contract; strict mode keeps them out).
    bad = _valid_targeting()
    del bad["icp_targeting"][0]["intent_filters"]["company"]
    with pytest.raises(ValidationError):
        RS.ResearchSpecV4(**bad)
    bad3 = _valid_targeting()
    bad3["icp_targeting"][0]["intent_filters"]["company"]["latest_funding_date_range"] = {
        "min": "2026-01-01",
        "max": None,
    }
    with pytest.raises(ValidationError):
        RS.ResearchSpecV4(**bad3)
    # a block without its icp_id echo is rejected too (the attribution contract).
    bad2 = _valid_targeting()
    del bad2["icp_targeting"][1]["icp_id"]
    with pytest.raises(ValidationError):
        RS.ResearchSpecV4(**bad2)


def _people_schema() -> dict:
    item = RS.RESEARCH_SPEC_JSON_SCHEMA["schema"]["properties"]["icp_targeting"]["items"]
    return item["properties"]["people_search_params"]


def test_seniority_enum_in_people_schema():
    # The json_schema constrains person_seniorities to the Apollo enum (the Pydantic validator is
    # list[str], so this guards the schema the model is actually held to).
    assert _people_schema()["properties"]["person_seniorities"]["items"]["enum"] == (
        RS.SENIORITY_ENUM
    )


def test_department_enum_in_people_schema_and_taxonomy_is_consistent():
    # Departments are constrained to the (deduped) master+sub enum, and the flat enum is exactly
    # the masters + their subs — so a value the LLM emits always maps to a real facet.
    enum = _people_schema()["properties"]["person_department_or_subdepartments"]["items"]["enum"]
    assert enum == RS.DEPARTMENT_ENUM
    assert RS.MASTER_DEPARTMENTS == list(RS.DEPARTMENT_TAXONOMY.keys())
    flat = RS.MASTER_DEPARTMENTS + [s for subs in RS.DEPARTMENT_TAXONOMY.values() for s in subs]
    assert set(RS.DEPARTMENT_ENUM) == set(flat)  # masters + subs, nothing extra
    assert len(RS.DEPARTMENT_ENUM) == len(set(RS.DEPARTMENT_ENUM))  # deduped


def test_validator_matches_json_schema_root_keys():
    # The defensive validator and the schema sent to the model can't drift apart.
    schema_keys = set(RS.RESEARCH_SPEC_JSON_SCHEMA["schema"]["properties"].keys())
    model_keys = set(RS.ResearchSpecV4.model_fields.keys())
    assert schema_keys == model_keys
    item_schema = set(
        RS.RESEARCH_SPEC_JSON_SCHEMA["schema"]["properties"]["icp_targeting"]["items"][
            "properties"
        ].keys()
    )
    item_model = set(RS.IcpTargetingV4.model_fields.keys())
    assert item_schema == item_model
    gap_schema = set(
        RS.RESEARCH_SPEC_JSON_SCHEMA["schema"]["properties"]["gaps"]["items"][
            "properties"
        ].keys()
    )
    assert gap_schema == set(RS.GapV4.model_fields.keys())


def test_assemble_merges_server_credit_policy_not_llm():
    targeting = _valid_targeting()
    # Even if the model tried to set a credit policy, assemble must use the server's.
    targeting["credit_policy"] = {"email_status_filter": ["unverified"], "evil": True}
    spec, gaps, icp_suggestions = RS.assemble_spec(targeting)
    assert spec["credit_policy"] == RS.CREDIT_POLICY  # server-set, deterministic
    assert spec["credit_policy"]["email_status_filter"] == ["verified"]
    assert spec["credit_policy"]["phone"] is False
    assert spec["spec_version"] == RS.SPEC_VERSION == 6
    assert [b["icp_id"] for b in spec["icp_targeting"]] == [ICP_A, ICP_B]
    assert spec["icp_targeting"][0]["company_search_params"][
        "q_organization_keyword_tags"
    ] == ["insurance", "insurtech"]
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
        "icp_targeting",
        "icp_validation",
        "icp_suggestions",
        "gaps",
    }


# --- targeting_for_icp — the one spec reader (v4 match + v3 fallback) -----------------


def _v4_blob(*blocks: dict) -> dict:
    return {
        "spec_version": 4,
        "icp_targeting": list(blocks),
        "icp_validation": {"customer_profiles": [], "paying_customer_summary": ""},
        "credit_policy": RS.CREDIT_POLICY,
    }


def test_targeting_for_icp_matches_block_by_id():
    blob = _v4_blob(_block(), _block(ICP_B, "Brokers"))
    got = RS.targeting_for_icp(blob, ICP_B)
    assert got is not None and got["icp_name"] == "Brokers"


def test_targeting_for_icp_multi_block_requires_icp():
    blob = _v4_blob(_block(), _block(ICP_B, "Brokers"))
    assert RS.targeting_for_icp(blob, None) is None  # caller 400s: "pick an ICP"
    # An unknown id never silently gets another ICP's targeting.
    assert RS.targeting_for_icp(blob, "33333333-3333-3333-3333-333333333333") is None


def test_targeting_for_icp_single_block_resolves_without_icp():
    blob = _v4_blob(_block())
    got = RS.targeting_for_icp(blob, None)
    assert got is not None and got["icp_id"] == ICP_A


def test_targeting_for_icp_v3_fallback_answers_any_icp():
    v3 = {
        "spec_version": 3,
        "company_search_params": _company_params(),
        "people_search_params": _people_params(),
        "intent_filters": _intent_filters(),
        "icp_validation": {"customer_profiles": [], "paying_customer_summary": ""},
        "credit_policy": RS.CREDIT_POLICY,
    }
    for icp in (None, ICP_A):
        got = RS.targeting_for_icp(v3, icp)
        assert got is not None
        assert got["company_search_params"] == _company_params()
        assert got["people_search_params"] == _people_params()
    assert RS.targeting_for_icp({}, None) is None
    assert RS.targeting_for_icp(None, ICP_A) is None
    assert RS.targeting_for_icp(_v4_blob(), ICP_A) is None  # v4 with zero blocks


# --- reconcile_icp_targeting — the coverage guard --------------------------------------


def test_reconcile_passes_exact_echo_and_orders_by_input():
    expected = {ICP_A: "Insurers", ICP_B: "Brokers"}
    blocks, err = RS.reconcile_icp_targeting(
        [_block(ICP_B, "Brokers"), _block(ICP_A, "Insurers")], expected
    )
    assert err is None
    assert [b["icp_id"] for b in blocks] == [ICP_A, ICP_B]  # input order restored


def test_reconcile_repairs_echo_typo_by_name():
    expected = {ICP_A: "Insurers", ICP_B: "Brokers"}
    typo = _block("not-a-real-id", "brokers ")  # bad id, name matches case/space-insensitively
    blocks, err = RS.reconcile_icp_targeting([_block(ICP_A, "Insurers"), typo], expected)
    assert err is None
    assert blocks[1]["icp_id"] == ICP_B and blocks[1]["icp_name"] == "Brokers"


def test_reconcile_fails_loudly_on_missing_icp():
    expected = {ICP_A: "Insurers", ICP_B: "Brokers"}
    blocks, err = RS.reconcile_icp_targeting([_block(ICP_A, "Insurers")], expected)
    assert blocks == []
    assert err is not None and "Brokers" in err  # the missed ICP is NAMED


def test_reconcile_drops_extra_invented_blocks():
    expected = {ICP_A: "Insurers"}
    blocks, err = RS.reconcile_icp_targeting(
        [_block(ICP_A, "Insurers"), _block("99", "Invented")], expected
    )
    assert err is None and len(blocks) == 1 and blocks[0]["icp_id"] == ICP_A


def test_reconcile_no_expected_passes_blocks_through():
    blocks, err = RS.reconcile_icp_targeting([_block("", "Brief-derived")], {})
    assert err is None and blocks[0]["icp_name"] == "Brief-derived"
    blocks, err = RS.reconcile_icp_targeting([], {})
    assert blocks == [] and err is not None  # zero blocks for a brief-only tenant is an error


def test_build_messages_injects_today():
    msgs = RS.build_messages({"companyName": "X"}, [], today="2026-06-22")
    assert msgs[0]["role"] == "system"
    assert '"today": "2026-06-22"' in msgs[1]["content"]


# --- merge_targeting — selective (per-ICP) re-scope splice ------------------------------


def test_merge_targeting_replaces_only_regenerated_block():
    # Re-scoped ICP_A only: its fresh block replaces the old, ICP_B's prior block carries over, and
    # the input order is preserved.
    prior = {"icp_targeting": [_block(ICP_A, "Insurers"), _block(ICP_B, "Brokers")]}
    fresh_a = _block(ICP_A, "Insurers")
    fresh_a["company_search_params"]["q_organization_keyword_tags"] = ["regenerated"]
    merged = RS.merge_targeting(prior, [fresh_a], [ICP_A, ICP_B])
    assert [b["icp_id"] for b in merged] == [ICP_A, ICP_B]
    assert merged[0]["company_search_params"]["q_organization_keyword_tags"] == ["regenerated"]
    assert merged[1]["icp_id"] == ICP_B  # untouched profile preserved verbatim


def test_merge_targeting_adds_first_scope_for_unscoped_icp():
    # ICP_B had no prior block ("no AI scope yet"); scoping it adds the block, keeps ICP_A.
    prior = {"icp_targeting": [_block(ICP_A, "Insurers")]}
    merged = RS.merge_targeting(prior, [_block(ICP_B, "Brokers")], [ICP_A, ICP_B])
    assert [b["icp_id"] for b in merged] == [ICP_A, ICP_B]


def test_merge_targeting_drops_icp_absent_from_input_order():
    # An ICP deleted from the brief (not in doc_order) falls out even if it had a prior block.
    prior = {"icp_targeting": [_block(ICP_A, "Insurers"), _block(ICP_B, "Brokers")]}
    merged = RS.merge_targeting(prior, [], [ICP_A])
    assert [b["icp_id"] for b in merged] == [ICP_A]


def test_merge_targeting_no_prior_blocks_yields_fresh_only():
    merged = RS.merge_targeting({}, [_block(ICP_A, "Insurers")], [ICP_A, ICP_B])
    assert [b["icp_id"] for b in merged] == [ICP_A]  # ICP_B has neither → omitted


def test_default_prompt_matches_seed_file():
    # The code fallback (runtime) and the migration's DB seed source must be identical, or a saved
    # default would differ from the seeded `briefing` row. They have no other binding — assert it.
    from pathlib import Path

    seed = (
        Path(__file__).resolve().parents[3] / "docs" / "prompts" / "brief-structure-v11.md"
    ).read_text(encoding="utf-8")
    assert seed.strip() == RS.DEFAULT_SYSTEM_PROMPT.strip()
    assert RS.PROMPT_VERSION == "brief-structure-v11"


def test_default_prompt_teaches_per_icp_output():
    # The per-ICP contract must be stated in the prompt (schema enforces shape; the prompt carries
    # the echo + no-merge semantics the schema can't express).
    p = RS.DEFAULT_SYSTEM_PROMPT
    assert "icp_targeting" in p
    assert "ONE icp_targeting entry PER input ICP" in p
    assert "NEVER merge two ICPs" in p


def test_default_prompt_never_mentions_date_windows():
    # v5 removed the funding/jobs-posted windows entirely — the prompt must not teach, request, or
    # even name the fields (naming them invites the model to raise gaps about them).
    p = RS.DEFAULT_SYSTEM_PROMPT
    assert "latest_funding_date_range" not in p
    assert "organization_job_posted_at_range" not in p
    assert "recency_window" not in p


def test_default_prompt_folds_avoidance_into_keyword_yield():
    # v11 removed the redundant avoid_keywords block: keyword_yield is now the SOLE keyword-feedback
    # signal, so the prompt must no longer mention avoid_keywords / NEGATIVE EVIDENCE, but its yield
    # block must still teach avoidance (a 0%-yield keyword is the negative to drop).
    p = RS.DEFAULT_SYSTEM_PROMPT
    assert "avoid_keywords" not in p
    assert "NEGATIVE EVIDENCE" not in p
    assert "KEYWORD YIELD" in p
    assert "signal to AVOID" in p


def test_default_prompt_teaches_stage4_grounding_and_server_set_tech():
    # D+ Stage 4 — the prompt must teach the two new learning blocks and that tech UIDs are server-
    # set (never model-emitted, or strict validation would reject them).
    p = RS.DEFAULT_SYSTEM_PROMPT
    assert "keyword_yield" in p and "KEYWORD YIELD" in p
    assert "customer_anchors" in p and "CUSTOMER ANCHORS" in p
    assert "technology-UID filters" in p  # the "do NOT emit" server-set instruction


def test_build_messages_carries_keyword_yield_and_anchors_only_when_present():
    # D+ Stage 4 — the yield table + customer anchors ride in the payload, only when non-empty.
    base = RS.build_messages({"companyName": "X"}, [])
    assert "keyword_yield" not in base[1]["content"]
    assert "customer_anchors" not in base[1]["content"]
    rich = RS.build_messages(
        {"companyName": "X"},
        [],
        keyword_yield=[{"keyword": "fintech", "good": 3, "total": 4, "yield_pct": 75}],
        customer_anchors=[{"domain": "acme.com", "industry": "software", "keywords": ["b2b saas"]}],
    )
    body = rich[1]["content"]
    assert '"keyword_yield"' in body and "fintech" in body
    assert '"customer_anchors"' in body and "acme.com" in body
    # Empty lists stay out (no empty block).
    empty = RS.build_messages({"companyName": "X"}, [], keyword_yield=[], customer_anchors=[])
    assert "keyword_yield" not in empty[1]["content"]
    assert "customer_anchors" not in empty[1]["content"]


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
        # TWO ICPs — the multi-ICP contract: one icp_targeting entry per profile, ids echoed.
        icp_ids = []
        for name, titles in (
            ("Ops leader", ["VP Operations"]),
            ("Founder-led 3PL", ["Founder", "CEO"]),
        ):
            r = client.post(
                f"/{slug}/icps",
                json={"name": name, "tag": "primary", "data": {"titles": titles}},
                headers=auth,
            )
            icp_ids.append(r.json()["id"])

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
        # Schema-valid v4 spec, server-set credit policy, one block per ICP with ids echoed.
        assert s1["spec"]["spec_version"] == 6
        assert s1["spec"]["credit_policy"]["email_status_filter"] == ["verified"]
        blocks = s1["spec"]["icp_targeting"]
        assert [b["icp_id"] for b in blocks] == icp_ids  # both ICPs covered, input order
        for b in blocks:
            assert "company_search_params" in b and "people_search_params" in b
            assert "intent_filters" in b
        assert "icp_validation" in s1["spec"]
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
