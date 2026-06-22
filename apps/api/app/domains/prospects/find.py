"""find — the pure pre-upsert filters for the Apollo find flows (C4/C5).

No I/O: turn parsed Apollo rows into the survivor set the router upserts, dropping exclusions and
duplicates. Kept pure so the credit/scope safeguard is unit-tested without a DB or network.

Exclusion is **not** re-implemented here — `filter_companies` reuses `suppression.ExclusionSet`
`.blocks` (the single source of the brief exclusion rules). What differs from `suppress()` is only
the dedupe *key*: Apollo companies key on registrable **domain** and people on **apollo_person_id**,
neither of which is the person `identity_key` that `suppress()` dedupes on — so these are thin
key-specific passes over the shared exclusion gate, not a parallel implementation.

Flow A (companies): drop rows with no domain, drop existing-customer domains (via ExclusionSet),
collapse duplicate orgs. Flow B (people): drop rows with no Apollo id, collapse duplicates, and
drop ICP `avoidTitles` matches on the (real, non-obfuscated) `title` — email/linkedin person-level
exclusion still can't run here (C0 proved search output is obfuscated), so it happens post-enrich;
the company was already exclusion-checked in Flow A.
"""

from __future__ import annotations

from app.domains.prospects.suppression import Candidate, ExclusionSet


def filter_companies(
    parsed: list[dict], exclusions: ExclusionSet, seen_domains: set[str] | None = None
) -> tuple[list[dict], list[tuple[dict, str]]]:
    """→ (survivors, dropped[(row, reason)]). Dedupe is by domain within the batch + vs `seen`."""
    seen = set(seen_domains or set())
    survivors: list[dict] = []
    dropped: list[tuple[dict, str]] = []
    for row in parsed:
        domain = row.get("domain")
        if not domain:
            dropped.append((row, "no_domain"))
            continue
        if exclusions.blocks(Candidate(domain=domain)):
            dropped.append((row, "excluded_domain"))
            continue
        if domain in seen:
            dropped.append((row, "duplicate"))
            continue
        seen.add(domain)
        survivors.append(row)
    return survivors, dropped


def filter_people(
    parsed: list[dict],
    seen_person_ids: set[str] | None = None,
    avoid_titles: list[str] | None = None,
) -> tuple[list[dict], list[tuple[dict, str]]]:
    """→ (survivors, dropped). Dedupe by `apollo_person_id`; drop rows that lack one.

    `avoid_titles` is the ICP's `avoidTitles` — a hard pre-score drop (Apollo people search has no
    native exclude-title field, and the search row's `title` is one of the few real fields C0
    proved is present). Match is case-insensitive substring so "VP, Sales Ops" is caught by a
    "sales ops" avoid. Applied here so an obvious mis-target never costs an LLM fit-score call.
    """
    seen = set(seen_person_ids or set())
    avoid = [t.lower() for t in (avoid_titles or []) if t]
    survivors: list[dict] = []
    dropped: list[tuple[dict, str]] = []
    for row in parsed:
        pid = row.get("apollo_person_id")
        if not pid:
            dropped.append((row, "no_apollo_id"))
            continue
        if pid in seen:
            dropped.append((row, "duplicate"))
            continue
        title = (row.get("title") or "").lower()
        if title and any(a in title for a in avoid):
            dropped.append((row, "avoided_title"))
            continue
        seen.add(pid)
        survivors.append(row)
    return survivors, dropped
