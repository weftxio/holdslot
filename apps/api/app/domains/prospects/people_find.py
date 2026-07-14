"""Stage-2 Apollo Flow-B people find — the per-org people search + relax ladder, facet labels,
and the reveal-and-enrich worker (`_enrich_prospects`)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.prospects import (
    apollo_map,
    labeling,
)
from app.domains.prospects.label_engine import _apply_prospect_verdict
from app.domains.prospects.scope import _exclusions
from app.domains.prospects.suppression import Candidate
from app.integrations.apollo import client as apollo
from app.models import (
    Prospect,
)

log = logging.getLogger("holdslot.prospects")


_ENRICH_WORKERS = 8  # concurrent Apollo people/match calls (HTTP-bound, like the score fan-out)

# Auto-relax order (D+ Stage 2 — "Query = rubric"): `person_titles` is the precise, rubric-aligned
# persona lever (the fit rubric scores a 14-pt title dimension), so the ladder queries titles FIRST
# — strict (include_similar_titles=false) then fuzzy (=true) — before dropping to Apollo's two
# native facets: seniority×department (both AND'd), then seniority alone. Apollo AND's the facets,
# so a strict combo can be empty at a small org even when each facet alone has people (Luma); the
# descent guarantees suitable people still surface, but never widens all the way to org-only
# (that would dump interns/irrelevant roles, defeating "suitable"). No-op rungs (params that lack
# the lever) are skipped, so the ladder is exactly the rungs the spec can actually express.
def _people_ladder(people_params: dict) -> list[tuple[dict, str]]:
    """The ordered (params, level) rungs for one org's people search — titles first, facets as the
    fallback. Deterministic + terminal; skips rungs the params can't fill."""
    titles = people_params.get("person_titles") or []
    sen = people_params.get("person_seniorities") or []
    dep = people_params.get("person_department_or_subdepartments") or []
    rungs: list[tuple[dict, str]] = []
    if titles:
        rungs.append(({**people_params, "include_similar_titles": False}, "titles_strict"))
        rungs.append(({**people_params, "include_similar_titles": True}, "titles_fuzzy"))
    # Facet rungs drop titles so a stale title match doesn't AND against the facet fallback.
    facet_base = {**people_params, "person_titles": []}
    if sen and dep:
        rungs.append((facet_base, "seniority_dept"))
    if sen:
        rungs.append(({**facet_base, "person_department_or_subdepartments": []}, "seniority_only"))
    return rungs or [(people_params, "as_is")]

def _search_people_relaxed(
    people_params: dict, org_id: str, per_company: int
) -> tuple[list[dict], dict, str]:
    """Search one org, descending the persona ladder until people appear → (rows, body_sent, level).

    `level` is a short diagnostic tag: titles_strict / titles_fuzzy (person_titles, exact then
    similar), seniority_dept / seniority_only (facet fallback), or "as_is" (the spec carried no
    persona lever, so nothing to relax)."""
    last_body: dict = {}
    level = "as_is"
    for params, level in _people_ladder(people_params):
        last_body = apollo_map.map_people_filter(params, org_id=org_id)
        rows = apollo.search_people(last_body, max_results=per_company)
        if rows:
            return rows, last_body, level
    return [], last_body, level

# Display labels for the two facet sidebars (Apollo machine value → human text).
_SENIORITY_LABELS = {
    "c_suite": "C-Suite",
    "vp": "VP",
}

def _humanize(value: str) -> str:
    """Apollo machine value → label: drop a leading `master_`, underscores → spaces, Title-case."""
    text = value[len("master_") :] if value.startswith("master_") else value
    return text.replace("_", " ").title()

def _facet_label(value: str) -> str:
    return _SENIORITY_LABELS.get(value) or _humanize(value)

def _enrich_prospects(db: Session, rows: list[Prospect], slug: str) -> dict:
    """Apollo `people/match` on `rows` — reveal a verified email (the only credit spend) and write
    it back, moving the row to `scored`. The reveal step of the async reveal-&-score worker
    (`run_enrich_score_prospects`); the caller owns loading + the per-request cap. (The sync
    `/prospects/enrich` twin was retired in D+.5/R10 — the async door is the only reveal path now.)

    **Idempotent + concurrent (the credit-safety contract):** `last_enriched_at` gates a re-spend,
    so a row already matched (even one Apollo returned no email for) is confirmed without a second
    charge; a manual row (no `apollo_person_id`) is confirmed without a match call. The match calls
    fan out on a thread pool (HTTP-only; ORM writes stay single-threaded), then results are applied
    and **committed per row** (R10): the `last_enriched_at` stamp lands when a credit is spent,
    so a concurrent door or a re-run skips that row — a crash mid-batch can't re-charge the rows
    already revealed. A per-row Apollo error counts in `failed` (row → `enrich_failed`); the spend
    counts are always returned. Returns `{confirmed, enriched, credits_spent, failed}`.
    """
    # R2 — post-enrich do-not-contact set (loaded once per batch). Apollo search obfuscates
    # email/linkedin, so a client-excluded PERSON can only be caught here, after reveal (find.py's
    # docstring promises this). Company-domain exclusion already ran at find time (Flow A).
    exclusions = _exclusions(db, rows[0].tenant_id) if rows else None

    # Partition: rows that need a paid match call vs rows that confirm without spending (manual rows
    # with no apollo_person_id, or rows already enriched).
    to_match: list[Prospect] = []
    for p in rows:
        # Credit-safety gate (idempotency): `last_enriched_at` is stamped on every completed
        # Apollo match, even one that charged a credit but returned no verified email. Gate on
        # it so a re-submit never re-charges such a row. (Gating on email presence alone silently
        # re-spent a credit on every matched-but-no-email row when the founder re-clicked Enrich.)
        already_enriched = p.last_enriched_at is not None or bool(
            p.email_valid or (p.enrichment or {}).get("email")
        )
        if not p.apollo_person_id or already_enriched:
            if p.status == "found":
                p.status = "confirmed"
            continue
        to_match.append(p)
    db.commit()  # R10 — persist the no-spend confirmations (covers the all-manual/all-cached case)

    # GS4 — reserve the paid Apollo matches against the tenant's plan cap BEFORE dispatch. Lazy +
    # dormant: no `subscription` row (tenant #0 + every tenant today) → returns len(to_match) as-is
    # (unbounded, the pre-Stripe behavior). Past the cap it meters `enrichment_overage`; only when
    # overage is disabled does it hard-stop the excess (those rows stay unmatched for next cycle).
    if to_match:
        allowed = len(to_match)
        try:
            from app.domains.billing.router import reserve_enrichment

            allowed = reserve_enrichment(db, rows[0].tenant_id, len(to_match))
            # L2 — commit the reservation NOW, before the slow Apollo fan-out. reserve_enrichment
            # deliberately doesn't commit (M13: helpers don't own the txn), and nothing else is
            # dirty here (R10 already committed the no-spend rows). Two reasons it must land first:
            #  · reserve-before-spend — a Lambda timeout mid-fan-out would otherwise spend the
            #    Apollo credits but roll back the reservation, leaking cap (spend uncounted).
            #    Over-reserving (reserve N, match <N on crash) is the safe direction.
            #  · the atomic UPDATE holds the tenant's `subscription` row lock; leaving it open for
            #    the fan-out's duration blocks create_subscription / the Stripe webhook _apply.
            db.commit()
        except Exception:  # noqa: BLE001 — a cap-guard hiccup must NEVER break the paid enrich loop
            db.rollback()  # restore a usable session (R10 already committed the no-spend rows)
            log.warning("enrich[%s]: cap guard failed — proceeding uncapped", slug)
        if allowed < len(to_match):
            log.info("enrich[%s]: cap reached — %d of %d matched", slug, allowed, len(to_match))
            to_match = to_match[:allowed]

    # Fan out the slow Apollo match calls concurrently (HTTP-bound, thread-safe); collect results
    # before touching the ORM so DB writes stay single-threaded.
    matched_by_pid: dict[str, dict | Exception] = {}
    if to_match:
        with ThreadPoolExecutor(max_workers=min(_ENRICH_WORKERS, len(to_match))) as ex:
            futs = {
                ex.submit(
                    apollo.match_person, p.apollo_person_id, reveal_email=True, reveal_phone=False
                ): p
                for p in to_match
            }
            for fut in as_completed(futs):
                p = futs[fut]
                try:
                    matched_by_pid[p.apollo_person_id] = fut.result()
                except apollo.ApolloError as exc:  # counted as `failed`, never a lost-spend 502
                    matched_by_pid[p.apollo_person_id] = exc

    enriched = credits = failed = 0
    for p in to_match:
        res = matched_by_pid.get(p.apollo_person_id)
        if isinstance(res, Exception):
            log.warning("enrich[%s]: match errored person=%s: %s", slug, p.apollo_person_id, res)
            p.status = "enrich_failed"
            failed += 1
            db.commit()  # R10 — per-row
            continue
        matched = apollo_map.parse_match(res)
        if not matched.get("apollo_person_id"):
            log.warning("enrich[%s]: no apollo match person=%s", slug, p.apollo_person_id)
            p.status = "enrich_failed"  # Apollo had no match; distinct so it won't sit as "pending"
            failed += 1
            db.commit()  # R10 — per-row
            continue
        credits += 1  # one reveal_personal_emails credit
        e = dict(p.enrichment or {})
        e.update(
            full_name=matched.get("full_name") or e.get("full_name", ""),
            email=matched.get("email", ""),
            linkedin_url=matched.get("linkedin_url", ""),
            departments=matched.get("departments", []),
        )
        p.enrichment = e
        p.email_valid = bool(matched.get("email_valid"))
        p.last_enriched_at = func.now()
        p.status = "scored"
        enriched += 1
        # R2 — do-not-contact on the just-revealed contact. The credit was already counted (spent
        # honestly), but a DNC hit is labeled `excluded_by_rules` and never becomes batchable. The
        # score pass that follows (run_enrich_score_prospects) leaves this label intact — it skips
        # rows already client-excluded here.
        revealed_email = matched.get("email") or ""
        if exclusions is not None and exclusions.blocks(
            Candidate(
                email=revealed_email,
                linkedin_url=matched.get("linkedin_url") or "",
                domain=revealed_email.split("@", 1)[1] if "@" in revealed_email else "",
            )
        ):
            _apply_prospect_verdict(
                p,
                labeling.Verdict(label=labeling.EXCLUDED, reason=labeling.REASON_RULE_EXCLUSION),
            )
        db.commit()  # R10 — per-row: the last_enriched_at stamp lands NOW, so a concurrent door or
        # a re-run skips this already-charged row (no double-spend); bounds a crash to one row.
    # Credit-spend audit trail (the only place HoldSlot spends an Apollo credit).
    log.info(
        "enrich[%s]: rows=%d to_match=%d enriched=%d credits=%d failed=%d",
        slug,
        len(rows),
        len(to_match),
        enriched,
        credits,
        failed,
    )
    return {
        "confirmed": len(rows),
        "enriched": enriched,
        "credits_spent": credits,
        "failed": failed,
    }
