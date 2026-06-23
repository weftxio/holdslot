"""C7 unit tests — the pure lookalike aggregator (seed rows → company_search_params).

DB-free: proves the deterministic span/union onto Apollo's four firmographic axes, and that an
all-sparse selection yields an empty filter (the router refuses the find, never searching wide).
"""

from __future__ import annotations

from app.domains.prospects import lookalike


def _seed(industry="", size="", country="", **evidence):
    return {"industry": industry, "size": size, "country": country, "evidence": evidence}


def test_single_seed_spans_all_four_axes():
    flt = lookalike.build_lookalike_filter(
        [
            _seed(
                industry="Robotics",
                country="United States",
                estimated_num_employees=200,
                annual_revenue=50_000_000,
                industries=["Industrial Automation"],
                keywords=["warehouse", "automation"],
            )
        ]
    )
    assert flt["q_organization_keyword_tags"][:2] == ["Robotics", "Industrial Automation"]
    assert "warehouse" in flt["q_organization_keyword_tags"]
    # 200 → widened 0.5×..2× = 100..400
    assert flt["organization_num_employees_ranges"] == ["100,400"]
    assert flt["revenue_range"] == {"min": 25_000_000, "max": 100_000_000}
    assert flt["organization_locations"] == ["United States"]


def test_multi_select_spans_min_to_max_and_unions():
    flt = lookalike.build_lookalike_filter(
        [
            _seed(industry="SaaS", country="United States", estimated_num_employees=50,
                  annual_revenue=10_000_000),
            _seed(industry="Fintech", country="Canada", estimated_num_employees=400,
                  annual_revenue=80_000_000),
        ]
    )
    # band spans the smallest..largest seed, widened: 50*0.5=25 .. 400*2=800
    assert flt["organization_num_employees_ranges"] == ["25,800"]
    assert flt["revenue_range"] == {"min": 5_000_000, "max": 160_000_000}
    assert set(flt["organization_locations"]) == {"United States", "Canada"}
    assert flt["q_organization_keyword_tags"] == ["SaaS", "Fintech"]


def test_size_string_fallback_when_no_evidence_headcount():
    flt = lookalike.build_lookalike_filter([_seed(industry="X", size="154,000")])
    assert flt["organization_num_employees_ranges"] == ["77000,308000"]


def test_keyword_tags_dedupe_case_insensitive_and_capped():
    flt = lookalike.build_lookalike_filter(
        [
            _seed(industry="Robotics", industries=["robotics", "AI"],
                  keywords=[f"kw{i}" for i in range(20)]),
        ]
    )
    tags = flt["q_organization_keyword_tags"]
    assert tags[:2] == ["Robotics", "AI"]  # "robotics" dup dropped case-insensitively
    assert len(tags) == 10  # capped


def test_country_dedupe_preserves_order():
    flt = lookalike.build_lookalike_filter(
        [_seed(country="United States"), _seed(country="united states"), _seed(country="Canada")]
    )
    assert flt["organization_locations"] == ["United States", "Canada"]


def test_all_sparse_selection_yields_empty_filter():
    assert lookalike.build_lookalike_filter([_seed(), _seed()]) == {}


def test_zero_and_nonnumeric_headcount_revenue_ignored():
    flt = lookalike.build_lookalike_filter(
        [_seed(industry="X", estimated_num_employees=0, annual_revenue="n/a", size="")]
    )
    assert "organization_num_employees_ranges" not in flt
    assert "revenue_range" not in flt
    assert flt["q_organization_keyword_tags"] == ["X"]
