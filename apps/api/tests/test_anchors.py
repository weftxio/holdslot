"""D+ Stage 4 — customer-anchor grounding (`briefs/anchors.py`).

`customer_domains` is a pure parse of the brief's `excludeCustomers` text; `customer_anchors`
enriches those domains (mocked here — no network) and shapes the LLM-facing anchor list.
"""

from __future__ import annotations

from app.domains.briefs import anchors


def test_customer_domains_parses_first_domain_per_line_and_dedupes():
    brief = {
        "excludeCustomers": (
            "acme.com, Acme Robotics, https://acme.com\n"
            "Northwind Traders, northwind.io, other\n"
            "acme.com, Acme again\n"  # duplicate → dropped
            "Just A Company Name\n"  # no domain → skipped
        )
    }
    assert anchors.customer_domains(brief) == ["acme.com", "northwind.io"]


def test_customer_domains_honors_no_list_flag_and_list_form():
    assert anchors.customer_domains({"excludeCustomers": "x.com", "noExcludeCustomers": True}) == []
    assert anchors.customer_domains({}) == []
    # A list-valued field parses the same way as newline text.
    assert anchors.customer_domains({"excludeCustomers": ["a.com, A", "b.com, B"]}) == [
        "a.com",
        "b.com",
    ]


def test_customer_anchors_enriches_and_strips_experiment_field(monkeypatch):
    def fake_enrich(domains):
        assert domains == ["acme.com", "beta.com"]  # bounded + ordered
        return [
            {
                "primary_domain": "acme.com",
                "industry": "software",
                "industries": ["software", "b2b"],
                "keywords": ["b2b saas", "devtools"],
                "estimated_num_employees": 150,
                "industry_tag_id": "abc123",
            },
            {"primary_domain": "beta.com"},  # sparse → dropped (no industry/keywords)
        ]

    monkeypatch.setattr(anchors.apollo, "enrich_organizations", fake_enrich)
    out = anchors.customer_anchors({"excludeCustomers": "acme.com\nbeta.com"})
    assert len(out) == 1
    a = out[0]
    assert a["domain"] == "acme.com" and a["employee_band"] == "51-200"
    assert "industry_tag_id" not in a  # experiment-only field never reaches the model


def test_customer_anchors_bounded_and_empty_when_no_customers(monkeypatch):
    monkeypatch.setattr(anchors.apollo, "enrich_organizations", lambda d: [])
    assert anchors.customer_anchors({"noExcludeCustomers": True}) == []

    seen: list[list[str]] = []

    def fake_enrich(domains):
        seen.append(domains)
        return []

    monkeypatch.setattr(anchors.apollo, "enrich_organizations", fake_enrich)
    many = "\n".join(f"c{i}.com" for i in range(20))
    anchors.customer_anchors({"excludeCustomers": many}, limit=8)
    assert len(seen[0]) == 8  # capped at limit — a long list can't fan out unbounded enrich


def test_customer_anchors_degrades_on_apollo_error(monkeypatch):
    def boom(domains):
        raise anchors.apollo.ApolloError("down", status=502)

    monkeypatch.setattr(anchors.apollo, "enrich_organizations", boom)
    assert anchors.customer_anchors({"excludeCustomers": "acme.com"}) == []
