"""D+ Stages 3 & 4 — negative-signal recycling + vocabulary grounding (`prospects/feedback.py`).
Pure aggregations, no DB: the per-keyword yield table (Stage 4 — the sole keyword-feedback signal, a
0%-yield keyword is the negative to drop), which technologies correlate with bad rows (Stage 4 →
`not_using` UIDs), and when bad rows cluster on a country (the conditional exclude)."""

from __future__ import annotations

from app.domains.prospects import feedback

# V2-4: feedback.py now classifies won/lost by the v2 `label`, not the v1 tier. Map the old tier
# labels the cases use → the equivalent v2 label (a market-gated row → excluded_by_rules).
_TIER_TO_LABEL = {"Below": "low_fit", "Strong": "contact_now", "Good": "contact_soon"}


def _row(tier, *, market_excluded=False, keywords=None, industry="", country="", technologies=None):
    label = "excluded_by_rules" if market_excluded else _TIER_TO_LABEL.get(tier, tier)
    return {
        "label": label,
        "keywords": keywords or [],
        "industry": industry,
        "country": country,
        "technologies": technologies or [],
    }


def test_negative_technologies_surfaces_bad_correlated_stacks():
    rows = [
        _row("Below", technologies=["Wix", "GoDaddy"]),
        _row("Below", technologies=["Wix", "Squarespace"]),
        _row("Strong", technologies=["Salesforce", "Snowflake"]),
    ]
    # 'wix' taints 2 bad, 0 good → surfaced (lowercased); single-bad stacks below the floor.
    assert feedback.negative_technologies(rows) == ["wix"]


def test_negative_technologies_keeps_stacks_that_also_mark_good_rows():
    rows = [
        _row("Below", technologies=["hubspot"]),
        _row("Below", technologies=["hubspot"]),
        _row("Good", technologies=["hubspot"]),
        _row("Strong", technologies=["hubspot"]),
    ]
    assert feedback.negative_technologies(rows) == []


def test_keyword_yield_ranks_worst_first_with_win_share():
    rows = (
        [_row("Below", keywords=["crypto"]) for _ in range(4)]
        + [_row("Strong", keywords=["fintech"]) for _ in range(3)]
        + [_row("Below", keywords=["fintech"])]  # fintech: 3 good / 4 total = 75%
    )
    table = feedback.keyword_yield(rows)
    by_kw = {e["keyword"]: e for e in table}
    assert by_kw["crypto"] == {"keyword": "crypto", "good": 0, "total": 4, "yield_pct": 0}
    assert by_kw["fintech"]["yield_pct"] == 75
    assert table[0]["keyword"] == "crypto"  # worst-yield first


def test_keyword_yield_drops_thin_samples_and_attaches_breadth():
    rows = [_row("Strong", keywords=["saas"]) for _ in range(3)]
    rows += [_row("Below", keywords=["rare"])]
    table = feedback.keyword_yield(rows, breadth={"saas": 12000})
    kws = {e["keyword"] for e in table}
    assert "saas" in kws and "rare" not in kws  # 'rare' has 1 row (< YIELD_MIN_SAMPLE)
    assert next(e for e in table if e["keyword"] == "saas")["total_entries"] == 12000


def test_cluster_exclusions_excludes_a_dominant_bad_country():
    rows = [
        _row("Below", country="china"),
        _row("Below", country="china"),
        _row("Below", country="china"),
        _row("Good", country="united states"),
    ]
    assert feedback.cluster_exclusions(rows) == {"organization_not_locations": ["china"]}


def test_cluster_exclusions_spares_a_country_with_good_rows():
    rows = [
        _row("Below", country="china"),
        _row("Below", country="china"),
        _row("Below", country="china"),
        _row("Strong", country="china"),  # a winner here → never exclude the whole country
    ]
    assert feedback.cluster_exclusions(rows) == {}


def test_cluster_exclusions_needs_a_real_cluster():
    # Below the 3-bad floor → nothing.
    assert feedback.cluster_exclusions([_row("Below", country="china")]) == {}
    # Bad rows spread thin (no country ≥60%) → nothing.
    spread = [_row("Below", country=c) for c in ("china", "india", "japan", "brazil")]
    assert feedback.cluster_exclusions(spread) == {}
