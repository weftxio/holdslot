"""Scoring v2 — the deterministic label engine (docs/holdslot-scoring-spec-v2.md).

Pure, no DB, no LLM, no network → the whole gate ladder is exercised off the spec's §12 fixture.
The two paid signals (liveness verdict; ICP-match + subscores) are passed in as data, so this proves
the FULL processing order even though V2-2 is what wires the live web/score calls. The `$0 at find`
invariant is structural: nothing here imports the OpenRouter/Apollo clients.
"""

from __future__ import annotations

from app.domains.prospects import labeling as L
from app.domains.prospects.labeling import RulesConfig, assign_label

# The client's intake rules for the fixture below (spec §5): B2B-only, HK/SG/TH.
RULES = RulesConfig(
    market="B2B",
    geographies=("Hong Kong", "Singapore", "Thailand"),
    excluded_names=frozenset({"acme test co"}),
    excluded_domains=frozenset({"blocked.example"}),
)


# --- score → label (spec §8) --------------------------------------------------
def test_label_from_score_thresholds():
    assert L.label_from_score(20) == "contact_now"
    assert L.label_from_score(16) == "contact_now"
    assert L.label_from_score(15) == "contact_soon"
    assert L.label_from_score(10) == "contact_soon"
    assert L.label_from_score(9) == "low_fit"
    assert L.label_from_score(4) == "low_fit"


def test_collapse_subscores_clamps_and_sums():
    total, clean = L.collapse_subscores(
        {"deal_fit": 9, "outbound_gap": 0, "trigger": 3, "reachability": None}
    )
    assert clean == {"deal_fit": 5, "outbound_gap": 1, "trigger": 3, "reachability": 1}
    assert total == 10
    # A missing axis defaults to 1; bounds keep the sum in 4–20.
    lo, _ = L.collapse_subscores({})
    assert lo == 4


# --- rules gate (spec §5) -----------------------------------------------------
def test_market_rule_excludes_b2c_for_b2b_client():
    v = assign_label(
        business_model="B2C", has_b2b_line=False, hq_country="Singapore",
        industry="Insurance", name="Bowtie", config=RULES,
    )
    assert v.label == "excluded_by_rules"
    assert v.reason == "rule: B2B only"


def test_b2c_with_b2b_line_still_excluded_for_b2b_client():
    """Founder 2026-07-10 — the Luma guard is removed: a B2C-tagged firm is excluded for a strict
    B2B client even with a secondary B2B line (has_b2b_line=True). Ruled out at step 1, before any
    paid score (Aegis / Mothership)."""
    v = assign_label(
        business_model="B2C", has_b2b_line=True, hq_country="Singapore",
        industry="Insurance", name="Aegis Organization", config=RULES,
    )
    assert v.label == "excluded_by_rules"
    assert v.reason == "rule: B2B only"


def test_complex_treated_as_b2b():
    v = assign_label(
        business_model="Complex", hq_country="Singapore",
        industry="Payments", name="SomePlatform", config=RULES,
    )
    assert v.label != "excluded_by_rules"  # Complex is not B2C → market rule never fires


def test_geography_in_target_by_apollo_field_not_excluded():
    """Founder 2026-07-09 — the geo-filtered Apollo search returned this row as HQ'd in Singapore,
    so it must NOT be geo-excluded just because the description names a founding country (US).
    Apollo's field is authoritative for the geo rule; the description mismatch only raises the
    hq_mismatch flag. (Altered Security, ArkTalents, Ceffu … — the wrongly-excluded APAC rows.)"""
    v = assign_label(
        business_model="B2B", hq_country="United States", field_country="Singapore",
        industry="Executive search", name="Altered Security", config=RULES,
    )
    assert v.label != "excluded_by_rules"
    assert "hq_mismatch" in v.flags


def test_geography_rule_excludes_when_no_known_country_in_target():
    """Excluded only when EVERY known country is out of target — both the description HQ and the
    Apollo field say a non-target country."""
    v = assign_label(
        business_model="B2B", hq_country="United States", field_country="United Kingdom",
        industry="Executive search", name="Faraway Co", config=RULES,
    )
    assert v.label == "excluded_by_rules"
    assert v.reason == "rule: outside target geography"


def test_client_exclusion_rule_by_name_and_domain():
    by_name = assign_label(
        business_model="B2B", hq_country="Singapore", industry="IT",
        name="Acme Test Co", config=RULES,
    )
    assert by_name.label == "excluded_by_rules" and by_name.reason == "rule: client exclusion"
    by_domain = assign_label(
        business_model="B2B", hq_country="Singapore", industry="IT",
        name="Whatever", domain="blocked.example", config=RULES,
    )
    assert by_domain.reason == "rule: client exclusion"


# --- data gate (spec §6) ------------------------------------------------------
def test_data_gate_missing_industry_or_country():
    no_ind = assign_label(business_model="B2B", hq_country="Singapore", industry="—", config=RULES)
    assert no_ind.label == "low_fit" and no_ind.reason == "data_unusable"
    no_geo = assign_label(business_model="B2B", hq_country=None, industry="IT", config=RULES)
    assert no_geo.reason == "data_unusable"  # AddSecure — no geo, no industry, no headcount


def test_data_gate_aggregator_website():
    # In-geography (SG) so the geo rule passes and the data check owns the verdict.
    v = assign_label(
        business_model="B2B", hq_country="Singapore", industry="Media",
        website="https://www.newswire.ca/news/foo", config=RULES,
    )
    assert v.label == "low_fit" and v.reason == "data_unusable"


# --- size gate (spec §7) ------------------------------------------------------
def test_size_gate_too_large():
    v = assign_label(
        business_model="B2B", hq_country="Singapore", industry="Telecom",
        name="Singtel", headcount=25000, size_ceiling=500, config=RULES,
    )
    assert v.label == "low_fit" and v.reason == "too large"


def test_size_gate_suppressed_by_headcount_uncertain():
    """A row whose sources disagree >2× (Bytesforce: 46/60/200–500) is not size-gated (spec §7)."""
    v = assign_label(
        business_model="B2B", hq_country="Singapore", industry="Insurtech",
        headcount=800, size_ceiling=500, extra_flags=["headcount_uncertain"], config=RULES,
    )
    assert v.reason != "too large"


# --- liveness gate (spec §4) --------------------------------------------------
def test_liveness_excludes_defunct_before_scoring():
    """CXA — in liquidation while Apollo shows it healthy. Liveness short-circuits the whole ladder,
    so even a great subscore never rescues it (the entire point of the v2 spec)."""
    v = assign_label(
        business_model="B2B", hq_country="Singapore", industry="Insurtech", name="CXA Group",
        liveness={"status": "defunct"},
        icp_match={"icp": "A", "reason": "fits ICP A"},
        subscores={"deal_fit": 5, "outbound_gap": 5, "trigger": 5, "reachability": 5},
        config=RULES,
    )
    assert v.label == "excluded_by_rules"
    assert v.reason == "company defunct"
    assert v.score_total is None  # never scored


def test_liveness_stale_flags_but_does_not_exclude():
    v = assign_label(
        business_model="B2B", hq_country="Singapore", industry="IT",
        liveness={"status": "stale"}, config=RULES,
    )
    assert v.label != "excluded_by_rules"
    assert "stale_record" in v.flags


# --- ICP gate (spec §7) -------------------------------------------------------
def test_icp_no_match_is_wrong_vertical():
    v = assign_label(
        business_model="B2B", hq_country="Singapore", industry="Robotics",
        icp_match={"icp": None}, config=RULES,
    )
    assert v.label == "low_fit" and v.reason == "wrong vertical"


# --- ladder order + survivor state --------------------------------------------
def test_survivor_without_score_needs_rescore():
    """V2-1: a row that clears every deterministic gate but has no paid signal is unlabeled."""
    v = assign_label(
        business_model="B2B", hq_country="Singapore", industry="IT services", config=RULES,
    )
    assert v.label is None and v.score_total is None


def test_rules_beat_data_and_size():
    """A B2C company that is also missing industry AND oversized is excluded_by_rules, not low_fit —
    the rule check runs before the data/size checks (spec §3 order)."""
    v = assign_label(
        business_model="B2C", has_b2b_line=False, hq_country="Singapore",
        industry="—", headcount=9999, size_ceiling=100, config=RULES,
    )
    assert v.label == "excluded_by_rules" and v.reason == "rule: B2B only"


# --- the §12 fixture: the 5 verified rows land exact --------------------------
# Inputs mirror spec §12 (subscores are illustrative — §12 is "a test fixture, not ground truth");
# the assertion is that the LADDER maps each row to the spec's stated label + reason.
VERIFIED_ROWS = [
    {
        "name": "Bytesforce", "expect": ("contact_now", "A"),
        "kw": dict(
            business_model="B2B", hq_country="Singapore", industry="Insurtech",
            icp_match={"icp": "A", "reason": "fits ICP A — grown purely through word of mouth"},
            subscores={"deal_fit": 3, "outbound_gap": 5, "trigger": 4, "reachability": 5},
        ),
    },
    {
        "name": "Pro5.ai", "expect": ("contact_now", "B"),
        "kw": dict(
            business_model="B2B", hq_country="Singapore", industry="IT services",
            icp_match={"icp": "B", "reason": "fits ICP B — inbound-only recruiting platform"},
            subscores={"deal_fit": 4, "outbound_gap": 4, "trigger": 5, "reachability": 5},
            extra_flags=["competitor_adjacent", "partner_led"],
        ),
    },
    {
        "name": "Blackpanda", "expect": ("contact_soon", "A"),
        "kw": dict(
            business_model="B2B", hq_country="Singapore", industry="Insurtech",
            icp_match={"icp": "A", "reason": "fits ICP A — Lloyd's coverholder, cyber insurance"},
            subscores={"deal_fit": 3, "outbound_gap": 1, "trigger": 3, "reachability": 4},
            extra_flags=["partner_led"],
        ),
    },
    {
        # Deviation from spec §12 (founder 2026-07-10): the Luma guard is removed, so a B2C-tagged
        # insurer is ruled out at step 1 even with a group-insurance B2B line — a strict-B2B client
        # does not want primarily-consumer companies scored. (Spec §12 had this as contact_soon.)
        "name": "Luma Health", "expect": ("excluded_by_rules", None),
        "kw": dict(
            business_model="B2C", has_b2b_line=True, hq_country="Thailand", industry="Insurance",
            icp_match={"icp": "A", "reason": "fits ICP A — group insurance for companies/NGOs"},
            subscores={"deal_fit": 3, "outbound_gap": 2, "trigger": 3, "reachability": 3},
        ),
    },
    {
        "name": "CXA Group", "expect": ("excluded_by_rules", None),
        "kw": dict(
            business_model="B2B", hq_country="Singapore", industry="Insurtech",
            liveness={"status": "defunct"},
        ),
    },
]


def test_verified_five_rows_land_exact():
    for row in VERIFIED_ROWS:
        v = assign_label(name=row["name"], config=RULES, **row["kw"])
        want_label, want_icp = row["expect"]
        assert v.label == want_label, f"{row['name']}: {v.label} != {want_label} ({v.reason})"
        if want_icp is not None:
            assert v.icp == want_icp, f"{row['name']}: icp {v.icp} != {want_icp}"
    # CXA is the headline: defunct → excluded, never scored.
    cxa = assign_label(name="CXA Group", config=RULES, **VERIFIED_ROWS[-1]["kw"])
    assert cxa.reason == "company defunct" and cxa.score_total is None


def test_partner_led_flag_survives_on_blackpanda():
    v = assign_label(name="Blackpanda", config=RULES, **VERIFIED_ROWS[2]["kw"])
    assert "partner_led" in v.flags


# --- people tier (V2-2) — the company label caps the person -------------------
def test_person_excluded_when_parent_company_excluded():
    v = L.assign_person_label(
        company_label="excluded_by_rules", title="VP Sales", has_contact=True,
        subscores={"persona_fit": 5, "authority": 5, "trigger": 5, "reachability": 5},
    )
    assert v.label == "excluded_by_rules" and v.reason == "parent company excluded"
    assert v.score_total is None  # never scored — the parent is out


def test_person_avoided_title_excluded():
    v = L.assign_person_label(
        company_label="contact_now", title="Sales Intern", has_contact=True,
        avoid_titles=("intern", "student"),
    )
    assert v.label == "excluded_by_rules" and v.reason == "rule: avoided title"


def test_person_missing_contact_or_title_is_data_unusable():
    no_email = L.assign_person_label(company_label="contact_now", title="CFO", has_contact=False)
    assert no_email.label == "low_fit" and no_email.reason == "data_unusable"
    no_title = L.assign_person_label(company_label="contact_now", title="", has_contact=True)
    assert no_title.reason == "data_unusable"


def test_person_capped_by_company_band():
    strong = {"persona_fit": 5, "authority": 5, "trigger": 5, "reachability": 5}  # → contact_now
    # A contact_now person at a contact_soon company can't outrank the account.
    at_soon = L.assign_person_label(
        company_label="contact_soon", title="CFO", has_contact=True, subscores=strong
    )
    assert at_soon.label == "contact_soon"
    # At a low_fit company the person is low_fit regardless of their own score.
    at_low = L.assign_person_label(
        company_label="low_fit", title="CFO", has_contact=True, subscores=strong
    )
    assert at_low.label == "low_fit"
    # At a contact_now company the person keeps their own (uncapped) score.
    at_now = L.assign_person_label(
        company_label="contact_now", title="CFO", has_contact=True, subscores=strong
    )
    assert at_now.label == "contact_now" and at_now.score_total == 20


def test_person_survivor_without_score_needs_rescore():
    v = L.assign_person_label(company_label="contact_now", title="CFO", has_contact=True)
    assert v.label is None


# --- rules-config extraction (V2-2 wiring seam) -------------------------------
def test_build_rules_config_from_brief_and_spec():
    cfg = L.build_rules_config(
        {"targetMarket": "B2B"},
        {"company_search_params": {"organization_locations": ["singapore", "hong kong"]}},
        excluded_domains=("Known.Example",),
    )
    assert cfg.market == "B2B"
    assert cfg.geographies == ("singapore", "hong kong")
    assert "known.example" in cfg.excluded_domains  # normalized
    # Both / absent target disables the market rule.
    assert L.build_rules_config({"targetMarket": "Both"}, {}).market == "Both"
    assert L.build_rules_config({}, {}).market is None


def test_size_ceiling_from_spec_takes_max_upper_bound():
    spec = {
        "icp_targeting": [
            {"company_search_params": {"organization_num_employees_ranges": ["1,50"]}},
            {"company_search_params": {"organization_num_employees_ranges": ["51,200", "201,500"]}},
        ]
    }
    assert L.size_ceiling_from_spec(spec) == 500
    assert L.size_ceiling_from_spec({}) is None  # no ranges → gate off (fail-open)
