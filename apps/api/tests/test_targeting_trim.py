"""W7 — the fit-scoring targeting trim. Pure functions; no DB / LLM."""

from app.domains.prospects.router import (
    _SCORING_BRIEF_FIELDS,
    _trim_brief_for_scoring,
    _trim_spec_for_scoring,
)

# A representative full brief (all 21 fields), with PII + operational fields that must NOT reach
# the paid LLM scorer.
FULL_BRIEF = {
    "companyName": "Acme",
    "website": "acme.com",
    "sell": "robots",
    "problem": "manual ops",
    "dealSize": "$50k",
    "salesCycle": "60d",
    "valueProps": ["fast"],
    "proofPoints": ["case study"],
    "signals": ["hiring ops"],
    "tone": "warm",
    "languages": ["en"],
    "excludeCustomers": ["x.com"],
    "excludeDeals": ["y.com"],
    "attendeeEmails": ["founder@acme.com"],
    "attendees": ["Founder"],
    "availability": "Tue/Thu",
    "channel": "email",
    "contact": "ops@acme.com",
    "approver": "CEO",
    "meetingsPerMonth": 10,
    "qualifiedDef": "VP+ at 200-1000 employees",
}


def test_keeps_only_fit_fields():
    trimmed = _trim_brief_for_scoring(FULL_BRIEF)
    assert set(trimmed) == _SCORING_BRIEF_FIELDS & set(FULL_BRIEF)
    # Spot-check the fit signals survive and the operational/PII ones are gone.
    assert trimmed["sell"] == "robots"
    assert trimmed["qualifiedDef"] == "VP+ at 200-1000 employees"


def test_pii_and_operational_dropped():
    trimmed = _trim_brief_for_scoring(FULL_BRIEF)
    for dropped in (
        "attendeeEmails",
        "contact",
        "attendees",
        "availability",
        "channel",
        "approver",
        "meetingsPerMonth",
        "tone",
        "languages",
        "proofPoints",
        "website",
        "excludeCustomers",
        "excludeDeals",
    ):
        assert dropped not in trimmed


def test_spec_drops_credit_policy_keeps_search_params():
    spec = {
        "company_search_params": {"a": 1},
        "people_search_params": {"b": 2},
        "intent_filters": {"c": 3},
        "credit_policy": {"max_companies": 500},
    }
    out = _trim_spec_for_scoring(spec)
    assert "credit_policy" not in out
    assert out["company_search_params"] == {"a": 1}
    assert out["people_search_params"] == {"b": 2}


_V4_SPEC = {
    "spec_version": 4,
    "icp_targeting": [
        {
            "icp_id": "icp-a",
            "icp_name": "Insurers",
            "company_search_params": {"a": 1},
            "people_search_params": {"b": 2},
            "intent_filters": {"c": 3},
        },
        {
            "icp_id": "icp-b",
            "icp_name": "Brokers",
            "company_search_params": {"a": 9},
            "people_search_params": {"b": 8},
            "intent_filters": {"c": 7},
        },
    ],
    "icp_validation": {"paying_customer_summary": "s"},
    "credit_policy": {"max_companies": 500},
}


def test_v4_spec_slices_to_the_rows_own_icp_block():
    # The scorer sees ONLY the scored row's ICP block, flattened to the single-block shape the
    # rubrics already read — never the other ICPs' params.
    out = _trim_spec_for_scoring(_V4_SPEC, "icp-b")
    assert "credit_policy" not in out and "icp_targeting" not in out
    assert out["company_search_params"] == {"a": 9}
    assert out["people_search_params"] == {"b": 8}
    assert out["intent_filters"] == {"c": 7}
    assert out["icp_validation"] == {"paying_customer_summary": "s"}


def test_v4_spec_unresolvable_icp_falls_back_to_whole_spec():
    # A multi-ICP spec scored for an unlabeled row keeps the full (union) context, minus policy.
    out = _trim_spec_for_scoring(_V4_SPEC, None)
    assert "credit_policy" not in out
    assert len(out["icp_targeting"]) == 2
