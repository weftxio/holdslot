"""lookalike — synthesize a company-search filter from selected seed rows (C7, the Lookalike door).

Apollo has **no** lookalike/similarity API (`mixed_companies/search` exposes `organization_ids[]`
to *include* but no seed/`organization_not_ids` param). So "find peers of these companies" is built
HoldSlot-side: a **pure, deterministic aggregation** of the selected rows' firmographics onto the
four Flow-A search axes, then run through the existing `apollo_map.map_company_filter` +
`find.filter_companies` tail. No I/O, no LLM — unit-tested against plain seed dicts.

The aggregation spans/unions the seeds (handles multi-select): keyword tags union (industries first,
capped so Apollo's OR doesn't over-broaden), a single employee band min→max widened ~0.5×–2×, a
revenue band min→max widened ~0.5×–2×, and the union of seed countries. The seeds are already tenant
rows, so the find tail's domain dedupe drops them automatically → the result is the *next* batch.
"""

from __future__ import annotations

_MAX_KEYWORD_TAGS = 10  # Apollo ORs keyword tags — too many over-broadens the "lookalike"


def _headcount(seed: dict) -> int | None:
    """Best employee count for one seed: enrich's `estimated_num_employees`, else the parsed `size`
    string (`"154,000"` → 154000). None when neither is present/numeric."""
    ev = seed.get("evidence") or {}
    raw = ev.get("estimated_num_employees")
    if raw is None:
        raw = (seed.get("size") or "").replace(",", "").strip() or None
    try:
        n = int(float(raw)) if raw is not None else None
    except (TypeError, ValueError):
        return None
    return n if n and n > 0 else None


def _revenue(seed: dict) -> float | None:
    """Best annual revenue (USD) for one seed from the enrich evidence; None when absent."""
    ev = seed.get("evidence") or {}
    raw = ev.get("annual_revenue") or ev.get("organization_revenue")
    try:
        v = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None
    return v if v and v > 0 else None


def _keyword_tags(seeds: list[dict]) -> list[str]:
    """Union of seed industry signals, deduped case-insensitively (first spelling wins), capped.

    Industries lead (the strongest "what this company is" signal); free-text keywords fill the
    remainder. Order is stable so the same selection always yields the same filter."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(values) -> None:
        for v in values:
            tag = (v or "").strip()
            key = tag.lower()
            if tag and key not in seen:
                seen.add(key)
                out.append(tag)

    for seed in seeds:
        ev = seed.get("evidence") or {}
        _add([seed.get("industry")])
        _add(ev.get("industries") or [])
        _add(ev.get("secondary_industries") or [])
    for seed in seeds:  # keywords only after all industries, so industries are never starved
        _add((seed.get("evidence") or {}).get("keywords") or [])
    return out[:_MAX_KEYWORD_TAGS]


def _employee_band(seeds: list[dict]) -> list[str] | None:
    """A single `organization_num_employees_ranges` entry spanning min→max headcount across seeds,
    widened ~0.5×–2× so same-size-band peers surface. None when no seed has a headcount."""
    counts = [n for n in (_headcount(s) for s in seeds) if n]
    if not counts:
        return None
    lo = max(1, int(min(counts) * 0.5))
    hi = int(max(counts) * 2)
    return [f"{lo},{hi}"]


def _revenue_range(seeds: list[dict]) -> dict | None:
    """A `revenue_range` {min,max} over seed revenues, widened ~0.5×–2×. None when no revenue."""
    revs = [r for r in (_revenue(s) for s in seeds) if r]
    if not revs:
        return None
    return {"min": int(min(revs) * 0.5), "max": int(max(revs) * 2)}


def _locations(seeds: list[dict]) -> list[str]:
    """Union of seed HQ countries (city is too narrow for a lookalike), deduped, stable order."""
    out: list[str] = []
    seen: set[str] = set()
    for seed in seeds:
        c = (seed.get("country") or "").strip()
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def build_lookalike_filter(seeds: list[dict]) -> dict:
    """Aggregate selected seed rows → a `company_search_params` dict (Apollo field names).

    Each seed is `{"industry", "size", "country", "evidence": {...}}` (the stored Company shape).
    Only populated axes are emitted; an all-sparse selection returns `{}` so the caller can refuse
    the find (the seeds need enrichment first). Pure — no DB, no network, no LLM.
    """
    params: dict = {}
    if tags := _keyword_tags(seeds):
        params["q_organization_keyword_tags"] = tags
    if band := _employee_band(seeds):
        params["organization_num_employees_ranges"] = band
    if rev := _revenue_range(seeds):
        params["revenue_range"] = rev
    if locs := _locations(seeds):
        params["organization_locations"] = locs
    return params
