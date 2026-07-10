"""Negative-signal recycling + vocabulary grounding — D+ Stages 3 & 4. Pure aggregations over the
tenant's scored companies that feed the next find/regenerate: Apollo has no exclude-by-keyword/
industry, so the equivalent is built HoldSlot-side from outcome data.

  * `keyword_yield` — the per-keyword yield table (won-share of every keyword the tenant's rows
    carry, worst-first) → the ≤300-token feedback block that teaches the model which keywords earn
    Strong/Good rows and which to drop. This is the SOLE keyword-feedback signal: a 0%-yield keyword
    IS a negative, so it carries the old "avoid" list with magnitude and replaces it. [Stage 4]
  * `cluster_exclusions` — when bad rows CLUSTER on one country, emit `organization_not_locations`
    straight into the search. [Stage 3]
  * `negative_technologies` — tech names (from enrich `technology_names`) that correlate with bad
    rows → resolved to UIDs by `tech_vocab` and emitted as the `not_using` tech filter (the Stage-4
    resolver clears what Stage 3 deferred: raw tech names are not UIDs). [Stage 4]

No I/O — the caller supplies plain rows `{label, country, keywords[], industry, technologies[]}` so
every rule is unit-tested without a DB. A row is BAD (negative evidence) when its v2 `label` is
`low_fit` or `excluded_by_rules`; GOOD when it is `contact_now` or `contact_soon`. (Unlabeled rows
are filtered out upstream in `_feedback_rows`, so every row here is one or the other.)
"""

from __future__ import annotations

from collections import Counter

_BAD_LABELS = frozenset({"low_fit", "excluded_by_rules"})
_GOOD_LABELS = frozenset({"contact_now", "contact_soon"})

# Stage 4 — negative technologies (same correlation shape as keywords, over tech names).
NEG_TECH_MIN_BAD = 2
NEG_TECH_TOP_K = 10

# Stage 4 — keyword yield table.
YIELD_MIN_SAMPLE = 3  # a keyword needs ≥3 scored rows before its win-rate is trustworthy
YIELD_TOP_K = 20  # cap the feedback block (~300 tokens): worst performers lead

EXCL_MIN_BAD = 3  # a country needs ≥3 bad rows before it can be excluded (not a one-off)
EXCL_MIN_SHARE = 0.6  # …and must account for ≥60% of all bad rows (a genuine cluster)


def _is_bad(row: dict) -> bool:
    return row.get("label") in _BAD_LABELS


def _is_good(row: dict) -> bool:
    return row.get("label") in _GOOD_LABELS


def _row_keywords(row: dict) -> set[str]:
    """The descriptive keywords a company contributes: its evidence `keywords` + `industry`,
    lowercased/trimmed, deduped — the tags the LLM can plausibly avoid next regenerate."""
    kws = {str(k).strip().lower() for k in (row.get("keywords") or []) if str(k).strip()}
    ind = (row.get("industry") or "").strip().lower()
    if ind:
        kws.add(ind)
    return kws


def _row_technologies(row: dict) -> set[str]:
    """The technology names a company contributes (from enrich `technology_names`), lowercased/
    trimmed/deduped — the names `tech_vocab` resolves to Apollo UIDs."""
    return {str(t).strip().lower() for t in (row.get("technologies") or []) if str(t).strip()}


def negative_technologies(rows: list[dict], *, top_k: int = NEG_TECH_TOP_K) -> list[str]:
    """Technology names that correlate with BAD rows (Below / market-excluded) and NOT good ones —
    the negative-tech candidates the router resolves to `currently_not_using_any_of_technology_uids`
    (Stage 4 clears the Stage-3 deferral). Bad-vs-good correlation shape: a tech qualifies when it
    taints ≥`NEG_TECH_MIN_BAD` bad rows and is strictly more common in bad rows than good, ranked
    worst-first, capped at `top_k`."""
    bad_ct: Counter[str] = Counter()
    good_ct: Counter[str] = Counter()
    for r in rows:
        if _is_bad(r):
            bad_ct.update(_row_technologies(r))
        elif _is_good(r):
            good_ct.update(_row_technologies(r))
    cands = [t for t, n in bad_ct.items() if n >= NEG_TECH_MIN_BAD and n > good_ct.get(t, 0)]
    cands.sort(key=lambda t: (-(bad_ct[t] - good_ct.get(t, 0)), -bad_ct[t], t))
    return cands[:top_k]


def keyword_yield(
    rows: list[dict], *, breadth: dict[str, int] | None = None, top_k: int = YIELD_TOP_K
) -> list[dict]:
    """The per-keyword yield table (Stage 4): for every descriptive keyword the tenant's SCORED rows
    carry, its won-share = Strong/Good rows / all scored rows carrying it. This is the SOLE keyword-
    feedback signal — the outcome-grounded replacement for the old bare avoid list — carrying
    magnitude (a 0%-yield keyword IS a negative, a 60%-yield keyword is one to keep), so the LLM can
    prefer winners and drop losers.

    Only keywords with ≥`YIELD_MIN_SAMPLE` scored rows are reported (a 1-row keyword is noise).
    `breadth` (optional) attaches each keyword's Apollo `total_entries` (how broad the term is,
    from prior runs) as `total_entries`. Sorted worst-yield-first (then widest sample, then name) so
    the block leads with the keywords to drop; capped at `top_k` to bound the prompt (~300 tokens).
    """
    good_ct: Counter[str] = Counter()
    total_ct: Counter[str] = Counter()
    for r in rows:
        kws = _row_keywords(r)
        total_ct.update(kws)
        if _is_good(r):
            good_ct.update(kws)
    breadth = breadth or {}
    table: list[dict] = []
    for kw, total in total_ct.items():
        if total < YIELD_MIN_SAMPLE:
            continue
        good = good_ct.get(kw, 0)
        entry = {
            "keyword": kw,
            "good": good,
            "total": total,
            "yield_pct": round(100 * good / total),
        }
        if kw in breadth:
            entry["total_entries"] = breadth[kw]
        table.append(entry)
    table.sort(key=lambda e: (e["yield_pct"], -e["total"], e["keyword"]))
    return table[:top_k]


def cluster_exclusions(rows: list[dict]) -> dict:
    """Deterministic Apollo exclude params from clustered bad rows: `organization_not_locations` —
    when one country accounts for ≥`EXCL_MIN_SHARE` of the bad rows (and ≥`EXCL_MIN_BAD` of them)
    AND holds no good rows, exclude it from the next search. Returns an Apollo-shaped dict (possibly
    empty) to merge into `filter_body`. Tech exclusion is NOT here — it needs the `tech_vocab`
    resolver's network CSV, so `negative_technologies` (names) resolves to UIDs in the router
    (`currently_not_using_any_of_technology_uids`) to keep this module pure/DB-free."""
    bad = [r for r in rows if _is_bad(r)]
    if len(bad) < EXCL_MIN_BAD:
        return {}
    good_countries = {(_country(r)) for r in rows if _is_good(r)}
    good_countries.discard("")
    bad_by_country: Counter[str] = Counter(c for r in bad if (c := _country(r)))
    total_bad = len(bad)
    exclude = [
        country
        for country, n in bad_by_country.items()
        if n >= EXCL_MIN_BAD and n / total_bad >= EXCL_MIN_SHARE and country not in good_countries
    ]
    return {"organization_not_locations": sorted(exclude)} if exclude else {}


def _country(row: dict) -> str:
    return (row.get("country") or "").strip().lower()
