"""Scoring-v2 label engine (docs/initial-build-plan.md §D+.2) — the 4-label company/prospect
verdict, the deterministic rules gate, and the concurrent LLM fit-score fan-out."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.icps import icp_docs
from app.domains.prospects import (
    fit,
    labeling,
)
from app.domains.prospects.scope import (
    _apollo_run_id,
    _build_exclusions,
    _build_targeting,
    _latest_brief,
    _latest_doc,
    _latest_spec,
)
from app.domains.prospects.serializers import _classify_payload, _company_payload, _prospect_payload
from app.integrations.openrouter.client import LlmError
from app.models import (
    Brief,
    Company,
    Prospect,
    ResearchRun,
    ResearchSpec,
)

# Sync-budget caps. Find/enrich run synchronously behind the 30s API-Gateway HTTP-API cap, and each
# scored row is one blocking LLM call — so a single request must bound how many it does. Larger sets
# are drained over repeated calls (find_people advances each processed org to `people_found`; the
# operator re-clicks to continue). Keep the product (calls × ~1-2s) comfortably under 30s.
MAX_COMPANIES_PER_FIND = 15  # LLM-scored companies per RESCORE/update request (30s sync cap)

def _rules_config(brief: Brief | None, spec: ResearchSpec | None) -> labeling.RulesConfig:
    """The client's v2 `RulesConfig` (spec §5) — market from the brief, geographies from the spec's
    search HQ filter, excluded domains from the `excludeCustomers` set (decision ⑧-B: the client's
    'who to avoid' domains become the client-exclusion set — labeled `excluded_by_rules`, not
    dropped). Company rows are matched by domain, which the exclusion set carries reliably."""
    ex = _build_exclusions(brief, spec)
    return labeling.build_rules_config(
        brief.data if brief else {},
        spec.spec if spec else {},
        excluded_domains=tuple(ex.domains),
    )

def _company_det_inputs(c: Company) -> dict:
    """The deterministic `assign_label` inputs from a company row: the stage-0 classification (in
    `fit_components`: business_model / hq_country / has_b2b_line) + firmographics + the raw Apollo
    headcount. The caller adds the client-wide `config` + `size_ceiling`."""
    comps = c.fit_components or {}
    ev = c.evidence or {}
    return {
        "business_model": comps.get("business_model") or "Unknown",
        "has_b2b_line": bool(comps.get("has_b2b_line")),
        "hq_country": comps.get("hq_country") or "",
        "industry": c.industry,
        "website": c.website,
        "name": c.name,
        "domain": c.domain,
        "field_country": c.country,
        "headcount": ev.get("estimated_num_employees"),
    }

def _apply_company_verdict(
    c: Company, verdict: labeling.Verdict, *, signals: dict | None = None
) -> None:
    """Persist a v2 `Verdict` on a company row: `label`/`score_total` cols · reason→`fit_reason`
    · subscores/flags/icp/trigger_line/liveness→`fit_components`. `signals` present = the web score
    call ran (adds trigger_line + the liveness verdict). v1 `fit_*` untouched."""
    comps = dict(c.fit_components or {})
    comps["reason"] = verdict.reason
    comps["flags"] = verdict.flags
    comps["icp"] = verdict.icp
    if verdict.subscores is not None:
        comps["subscores"] = verdict.subscores
    if signals is not None:
        comps["trigger_line"] = signals.get("trigger_line", "")
        comps["liveness"] = signals.get("liveness", {})
    else:
        # N23 — this row was caught by the FREE gate (no paid call), so any trigger_line/liveness
        # from a PRIOR paid score is stale residue that no longer matches the new verdict. Drop it.
        comps.pop("trigger_line", None)
        comps.pop("liveness", None)
    c.label = verdict.label
    c.score_total = verdict.score_total
    if verdict.reason:
        c.fit_reason = verdict.reason
    c.fit_components = comps

def _score_companies_v2(db: Session, tenant_id, rows: list[Company]) -> dict:
    """v2 rescore (spec §3): deterministic gates on every row → the paid web score on survivors →
    persist the `Verdict`. Records one `research_run` for cost; returns `{scored, failed, cost}`.
    Slow (web + reasoning) — async path only. Mirrors `_score_companies` wave mechanics."""
    brief, spec = _latest_brief(db, tenant_id), _latest_spec(db, tenant_id)
    rubric = _latest_doc(db, tenant_id, fit.COMPANY_SCORE_STAGE)
    rubric_body = rubric.body if rubric else ""
    config = _rules_config(brief, spec)
    ceiling = labeling.size_ceiling_from_spec(spec.spec if spec else {})
    # The scorer judges each row against the FULL ICP set and picks the ICP itself (`icp_match.icp`
    # = A / B / none — spec §7: one company pool, the model assigns the ICP). So targeting carries
    # EVERY ICP profile, NOT the row's find-time `icp_id`. Narrowing to one ICP was the wrong-
    # vertical bug: a professional-services firm sourced under ICP A never saw the ICP-B definition,
    # so the model called it "not insurtech → wrong vertical". Built once, client-wide, per row.
    all_icps = icp_docs(db, tenant_id)
    company_targeting = _build_targeting(brief, spec, all_icps, None)
    # Letter → ICP row id, so a row whose model-matched ICP differs from its find-time icp_id is
    # re-tagged to the matched ICP — Step-2 people-search then uses that ICP's personas (ICP B's
    # Founder/MD, not ICP A's Head of Growth/Sales). Only the score pass can re-tag: it is the one
    # place an ICP is judged. Built from the SAME `fit.icp_letter_map` the score schema's enum uses
    # (N6), so the letter the model emits is guaranteed to map back here.
    icp_by_letter = fit.icp_letter_map(all_icps)

    # Pass 1 — free deterministic gates. A caught row (excluded_by_rules / low_fit) is labeled now
    # and never web-checked; a survivor (label None) goes to the paid pass.
    survivors: list[Company] = []
    for c in rows:
        v = labeling.assign_label(config=config, size_ceiling=ceiling, **_company_det_inputs(c))
        if v.label is not None:
            _apply_company_verdict(c, v)
        else:
            survivors.append(c)

    # Pass 2 — the paid web-grounded liveness + score call, survivors only.
    jobs = [
        (
            c,
            (
                lambda payload=_company_payload(c), targeting=company_targeting: (
                    fit.company_score_v2(
                        tenant_id=tenant_id,
                        rubric_body=rubric_body,
                        company=payload,
                        targeting=targeting,
                    )
                )
            ),
        )
        for c in survivors
    ]
    cost = 0.0
    web_scored = 0
    for c, signals in _score_concurrently(jobs):
        if signals is None:
            continue
        v = labeling.assign_label(
            config=config,
            size_ceiling=ceiling,
            **_company_det_inputs(c),
            liveness=signals["liveness"],
            icp_match=signals["icp_match"],
            subscores=signals["subscores"],
            extra_flags=signals["flags"],
        )
        _apply_company_verdict(c, v, signals=signals)
        # Re-tag to the ICP the model matched (spec §7: the model assigns the ICP). A no-match
        # (`icp` None → wrong vertical) leaves the find-time tag untouched.
        matched = icp_by_letter.get((signals["icp_match"] or {}).get("icp"))
        if matched and str(matched) != str(c.icp_id):
            c.icp_id = uuid.UUID(matched) if isinstance(matched, str) else matched
        cost += float(signals.get("cost_usd") or 0.0)
        web_scored += 1
        # Lever 2 — commit each verdict the instant it lands (rows are pre-loaded + already
        # persisted, so this only flushes THIS row's label/score), so the FE list poll shows scores
        # filling in one-by-one instead of a single end-of-wave dump, and a mid-wave worker kill
        # keeps every row scored so far. The trailing research_run commit still records total cost.
        db.commit()

    db.add(
        ResearchRun(
            tenant_id=tenant_id,
            run_id=_apollo_run_id(),
            spec_version=spec.version if spec else None,
            source="rescore",
            # R28 — stamp the rubric prompt version ACTUALLY loaded for this run (founder-editable),
            # not the static code default, so the telemetry ties the run to the real prompt.
            rubric_version=(f"v{rubric.version}" if rubric else fit.SCORE_RUBRIC_VERSION),
            rows_pushed=len(rows),
            cost_usd=round(cost, 6),
        )
    )
    db.commit()
    # R20b — no per-row refresh: this worker returns only counts, so re-reading each row after the
    # commit was one wasted round-trip per row for values nobody reads.
    web_failed = len(survivors) - web_scored
    return {
        "scored": len(rows) - web_failed,  # gated rows + web successes both carry a label
        "failed": web_failed,
        "cost_usd": round(cost, 6),
    }

def _label_companies_deterministic(
    db: Session, tenant_id, rows: list[Company], *, brief: Brief | None = None, spec=None
) -> None:
    """Find-time v2 labeling (spec §3 free gates + ⑧-B). After stage-0 classify has stamped
    business_model / hq_country / has_b2b_line, run the deterministic ladder (rules → data → size)
    on each NEW row so `excluded_by_rules` / `low_fit` show immediately — no rescore click, no spend
    (no web call). A survivor (label None) stays "needs re-score" until the paid pass. Idempotent:
    the gate verdict is a pure function of the row + config. `brief`/`spec` are passed in when the
    caller already has them (the find path), else fetched."""
    if not rows:
        return
    brief = brief if brief is not None else _latest_brief(db, tenant_id)
    spec = spec if spec is not None else _latest_spec(db, tenant_id)
    config = _rules_config(brief, spec)
    ceiling = labeling.size_ceiling_from_spec(spec.spec if spec else {})
    for c in rows:
        v = labeling.assign_label(config=config, size_ceiling=ceiling, **_company_det_inputs(c))
        if v.label is not None:
            _apply_company_verdict(c, v)

def _prospect_v2_payload(enrichment: dict | None, company: Company | None) -> dict:
    """The person facts the v2 people scorer judges — decision-maker signals + the parent company's
    LABEL (not a fit score). The company label caps the person server-side; the model reads it only
    as context and does NOT re-judge the company. (Now identical to `_prospect_payload`, which since
    V2-4 carries `company_label`/`company_reason` directly; kept as the v2 call site's name.)"""
    return _prospect_payload(enrichment, company)

def _apply_prospect_verdict(p: Prospect, verdict: labeling.Verdict) -> None:
    """Persist a v2 people `Verdict`: `label`/`score_total` columns + reason/subscores/flags into
    `fit_components` (+ `fit_reason` parity)."""
    comps = dict(p.fit_components or {})
    comps["reason"] = verdict.reason
    comps["flags"] = verdict.flags
    if verdict.subscores is not None:
        comps["subscores"] = verdict.subscores
    p.label = verdict.label
    p.score_total = verdict.score_total
    if verdict.reason:
        p.fit_reason = verdict.reason
    p.fit_components = comps

def _score_prospects_v2(db: Session, tenant_id, rows: list[Prospect]) -> dict:
    """v2 people rescore: the company label caps each person (spec people-tier). Deterministic gates
    (parent-excluded / avoided title / missing title-or-contact) run free; survivors get the no-web
    people-axis score. Returns `{scored, failed, cost_usd}`."""
    brief, spec = _latest_brief(db, tenant_id), _latest_spec(db, tenant_id)
    rubric = _latest_doc(db, tenant_id, fit.PROSPECT_SCORE_STAGE)
    rubric_body = rubric.body if rubric else ""
    # avoidTitles are PER-ICP (ICP docs), keyed by icp id — mirrors find.filter_people (the people
    # find path), not the brief. A title avoided in one profile must not gate another.
    avoid_by_icp = {
        d["id"]: tuple(t for t in (d.get("avoidTitles") or []) if t)
        for d in icp_docs(db, tenant_id, None)
    }

    def _avoid_for(p: Prospect) -> tuple[str, ...]:
        return avoid_by_icp.get(str(p.icp_id), ()) if p.icp_id else ()

    company_ids = {p.company_id for p in rows if p.company_id}
    companies = (
        {
            c.id: c
            for c in db.execute(
                select(Company).where(Company.tenant_id == tenant_id, Company.id.in_(company_ids))
            ).scalars()
        }
        if company_ids
        else {}
    )
    targeting_cache: dict[str | None, dict] = {}

    def _targeting_for(icp_id) -> dict:
        key = str(icp_id) if icp_id else None
        if key not in targeting_cache:
            targeting_cache[key] = _build_targeting(
                brief, spec, icp_docs(db, tenant_id, icp_id), icp_id
            )
        return targeting_cache[key]

    def _det(p: Prospect) -> labeling.Verdict:
        e = p.enrichment or {}
        company = companies.get(p.company_id)
        return labeling.assign_person_label(
            company_label=company.label if company else None,
            title=e.get("title"),
            has_contact=bool(e.get("email")),
            avoid_titles=_avoid_for(p),
        )

    # Pass 1 — deterministic people gates.
    survivors: list[Prospect] = []
    for p in rows:
        # R2 — a row client-excluded at the post-enrich DNC gate stays excluded; never re-score it
        # into a contactable label (the enrich pass set label + this reason together).
        if p.label == labeling.EXCLUDED and (p.fit_components or {}).get(
            "reason"
        ) == labeling.REASON_RULE_EXCLUSION:
            continue
        v = _det(p)
        if v.label is not None:
            _apply_prospect_verdict(p, v)
        else:
            survivors.append(p)

    # Pass 2 — the no-web people-axis score on survivors.
    jobs = [
        (
            p,
            (
                lambda payload=_prospect_v2_payload(p.enrichment, companies.get(p.company_id)),
                targeting=_targeting_for(p.icp_id): fit.prospect_score_v2(
                    tenant_id=tenant_id,
                    rubric_body=rubric_body,
                    enrichment=payload,
                    targeting=targeting,
                )
            ),
        )
        for p in survivors
    ]
    cost = 0.0
    web_scored = 0
    for p, scored in _score_concurrently(jobs):
        if scored is None:
            continue
        company = companies.get(p.company_id)
        e = p.enrichment or {}
        v = labeling.assign_person_label(
            company_label=company.label if company else None,
            title=e.get("title"),
            has_contact=bool(e.get("email")),
            avoid_titles=_avoid_for(p),
            subscores=scored["subscores"],
            reason=scored["reason"],
            flags=scored["flags"],
        )
        _apply_prospect_verdict(p, v)
        cost += float(scored.get("cost_usd") or 0.0)
        web_scored += 1
        # Lever 2 — commit each verdict as it lands (see `_score_companies_v2`): incremental FE
        # visibility + mid-wave-kill resilience. Only this row's label/score is flushed.
        db.commit()

    db.add(
        ResearchRun(
            tenant_id=tenant_id,
            run_id=_apollo_run_id(),
            spec_version=spec.version if spec else None,
            source="rescore",
            # R28 — stamp the rubric prompt version ACTUALLY loaded for this run (founder-editable),
            # not the static code default, so the telemetry ties the run to the real prompt.
            rubric_version=(f"v{rubric.version}" if rubric else fit.SCORE_RUBRIC_VERSION),
            rows_pushed=len(rows),
            cost_usd=round(cost, 6),
        )
    )
    db.commit()
    # R20b — no per-row refresh (returns only counts; the re-read was waste, mirrors companies).
    web_failed = len(survivors) - web_scored
    return {"scored": len(rows) - web_failed, "failed": web_failed, "cost_usd": round(cost, 6)}

# A full find can score up to MAX_*_PER_FIND rows; a *sequential* LLM call per row overruns the 30s
# API Gateway sync cap (→ 503). The LLM client is stdlib-urllib with its own telemetry session per
# call, so the calls are thread-safe — we fan them out, then apply each result on the main thread
# (ORM mutation stays single-threaded). The concurrency WAVE WIDTH — deliberately decoupled from the
# find-company row cap (D+ Stage 1a `FIND_COMPANY_LIMIT`) so widening the find never fans out an
# unbounded number of concurrent LLM calls. Sized to the sync rescore batch
# (`MAX_COMPANIES_PER_FIND`) so THAT path still scores in one reasoning wave. Env-tunable.
_SCORE_WORKERS = int(os.environ.get("HOLDSLOT_SCORE_WORKERS", str(MAX_COMPANIES_PER_FIND)))

def _score_concurrently(jobs: list[tuple]):
    """Run independent fit-score jobs concurrently, YIELDING `(key, scored | None)` as each call
    lands (completion order, not submission order) — None when that call failed (row kept unscored).
    `jobs` = [(key, fn)] where `fn() -> scored dict` (or raises LlmError). Each `fn` must close over
    plain data, never touch the request session off-thread.

    A generator (not a list) so a caller can apply + COMMIT each verdict the moment it arrives
    (Lever 2): scored rows then surface incrementally on the FE's list poll instead of all at once,
    and a worker killed mid-wave keeps the rows it already scored rather than losing the batch.
    """
    if not jobs:
        return

    def _run(job: tuple) -> tuple:
        key, fn = job
        try:
            return key, fn()
        except LlmError:
            return key, None

    with ThreadPoolExecutor(max_workers=min(_SCORE_WORKERS, len(jobs))) as ex:
        futures = [ex.submit(_run, j) for j in jobs]
        for fut in as_completed(futures):
            yield fut.result()

def classify_companies(tenant_id, rows: list[Company], brief: Brief | None) -> float:
    """Stage-0 — stamp `business_model` (+ the description-derived `hq_country` and
    `has_b2b_line`) on every row that lacks one (idempotent, so a re-find never re-classifies) via a
    dedicated minimal LLM call. These three facts feed the v2 rules engine — the market/geo/Luma
    gates run in `_label_companies_deterministic` (called right after this in the find path), which
    stamps `excluded_by_rules` on an opposite-market row. Returns the total cost_usd for the run.

    One concurrent wave (the LLM client is thread-safe); the ORM mutation stays on the calling
    thread (results applied in the loop below). Does NOT commit — the caller owns the transaction. A
    per-row classify failure is absorbed (row kept unlabeled), never fatal.
    """
    todo = [c for c in rows if not (c.fit_components or {}).get("business_model")]
    jobs = [
        (
            c,
            (lambda payload=_classify_payload(c): fit.classify_business_model(
                tenant_id=tenant_id, company=payload
            )),
        )
        for c in todo
    ]
    cost = 0.0
    for c, res in _score_concurrently(jobs):
        if res is None:
            continue
        comps = dict(c.fit_components or {})
        # The three facts the v2 rules engine reads at label time (`_company_det_inputs`): the
        # B2B/B2C model + the description-derived HQ country (geo rule) + the B2B-line Luma guard.
        comps["business_model"] = res.get("business_model") or "Unknown"
        comps["hq_country"] = res.get("hq_country") or ""
        comps["has_b2b_line"] = bool(res.get("has_b2b_line"))
        c.fit_components = comps
        cost += float(res.get("cost_usd") or 0.0)
    return cost
