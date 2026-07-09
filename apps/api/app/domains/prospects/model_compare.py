"""One-off in-Lambda model A/B — score companies with an arbitrary model, READ-ONLY.

Why it exists: the OpenRouter key lives only in the Lambda's execution role (reading the prod
secret locally is policy-blocked), so a Pro-vs-Flash scoring comparison cannot run from a local
script. This worker runs the EXACT production company-scoring path — Pass-1 deterministic gate →
Pass-2 web-grounded `company_score_v2` → `labeling.assign_label` — for ONE requested model over a
given set of company ids, but NEVER persists a Verdict back onto the `company` row. It is invoked
directly (`aws lambda invoke`, off the API-gateway/auth path) on the shared `{"holdslot_job": ...}`
event contract `app.main.handler` routes; the caller chunks the id list so a single concurrent
wave stays under the Lambda timeout, and reads the comparison from the RequestResponse payload.

The only side effect is the per-call `LlmCall` telemetry row the OpenRouter client always writes
(the audit trail) — no `company` row is mutated, so the experiment is safe against live data. Diff
the returned verdicts against the stored production baseline (`label`/`score_total`/`subscores`,
produced by the locked Pro model) to decide whether to switch `SCORE_MODELS`.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.domains.prospects import fit, labeling
from app.integrations.openrouter.client import LlmError

log = logging.getLogger("holdslot.model_compare")

JOB_MODEL_COMPARE = "model_compare"

# One concurrent wave. Each company_score_v2 call is web-grounded + reasoning (~50-120s); keep the
# per-invoke chunk small enough that one wave finishes well under the 300s Lambda timeout.
_WORKERS = 12


def _subscores_of(comps: dict | None) -> dict | None:
    subs = (comps or {}).get("subscores")
    return subs if isinstance(subs, dict) and subs else None


def run_compare(event: dict) -> dict:
    """Score `event['company_ids']` with `event['model']` (READ-ONLY) and return per-row verdicts.

    Event: {"holdslot_job": "model_compare", "tenant_id": <uuid>, "model": <slug>,
            "company_ids": [<uuid>, ...]}.
    Returns {"model": <requested>, "served_models": [...], "count": n, "scored": n, "gated": n,
             "failed": n, "rows": [...]}. Each row carries the fresh verdict AND the stored Pro
    baseline so the caller can diff without a second DB read:
      {company_id, domain, name, gated, error, served_model, latency_ms, cost_usd,
       label, score_total, subscores, liveness, icp, reason,
       prior_label, prior_score_total, prior_subscores}.

    `event['task'] == "classify"` routes to the stage-0 business-model classifier A/B instead (no
    web, no gate — a pure model-vs-model diff on the stored classifier inputs)."""
    if event.get("task") == "classify":
        return _run_classify(event)

    from app.core.db import get_session
    from app.domains.icps import icp_docs
    from app.domains.prospects.router import (
        _build_targeting,
        _company_det_inputs,
        _company_payload,
        _latest_brief,
        _latest_doc,
        _latest_spec,
        _rules_config,
    )
    from app.models import Company

    tid = uuid.UUID(str(event["tenant_id"]))
    model = event["model"]
    ids = [uuid.UUID(str(x)) for x in (event.get("company_ids") or [])]
    if not ids:
        return {"model": model, "served_models": [], "count": 0, "scored": 0, "gated": 0,
                "failed": 0, "rows": []}

    db = get_session()
    try:
        # Client-wide scoring context, built ONCE (mirrors _score_companies_v2). Read-only.
        brief, spec = _latest_brief(db, tid), _latest_spec(db, tid)
        rubric = _latest_doc(db, tid, fit.COMPANY_SCORE_STAGE)
        rubric_body = rubric.body if rubric else ""
        config = _rules_config(brief, spec)
        ceiling = labeling.size_ceiling_from_spec(spec.spec if spec else {})
        all_icps = icp_docs(db, tid)
        targeting = _build_targeting(brief, spec, all_icps, None)

        rows = db.query(Company).filter(Company.tenant_id == tid, Company.id.in_(ids)).all()
        by_id = {str(c.id): c for c in rows}

        # Extract every plain-data input on THIS thread — the ORM session is not thread-safe, so the
        # pool workers below close over dicts only (same discipline as router._score_concurrently).
        prepared: list[dict] = []
        for cid in [str(i) for i in ids]:
            c = by_id.get(cid)
            if c is None:
                prepared.append({"company_id": cid, "missing": True})
                continue
            det = _company_det_inputs(c)
            base = {
                "company_id": cid,
                "domain": c.domain,
                "name": c.name,
                "prior_label": c.label,
                "prior_score_total": c.score_total,
                "prior_subscores": _subscores_of(c.fit_components),
                "det": det,
            }
            v1 = labeling.assign_label(config=config, size_ceiling=ceiling, **det)
            if v1.label is not None:
                # A deterministic gate catches it before any paid call — record the free verdict.
                base.update({"gated": True, "payload": None, "gate_verdict": v1})
            else:
                base.update({"gated": False, "payload": _company_payload(c)})
            prepared.append(base)

        def _score_one(item: dict) -> dict:
            t0 = time.monotonic()
            try:
                signals = fit.company_score_v2(
                    tenant_id=tid,
                    rubric_body=rubric_body,
                    company=item["payload"],
                    targeting=targeting,
                    models=[model],
                )
            except LlmError as e:
                return {**item, "error": f"{e.status}: {e}"[:200], "served_model": None,
                        "latency_ms": int((time.monotonic() - t0) * 1000)}
            latency = int((time.monotonic() - t0) * 1000)
            v = labeling.assign_label(
                config=config,
                size_ceiling=ceiling,
                **item["det"],
                liveness=signals["liveness"],
                icp_match=signals["icp_match"],
                subscores=signals["subscores"],
                extra_flags=signals["flags"],
            )
            return {
                **item,
                "served_model": signals.get("model"),
                "latency_ms": latency,
                "cost_usd": signals.get("cost_usd"),
                "label": v.label,
                "score_total": v.score_total,
                "subscores": v.subscores,
                "liveness": (signals.get("liveness") or {}).get("status"),
                "icp": v.icp,
                "reason": (v.reason or "")[:240],
            }

        to_score = [p for p in prepared if not p.get("missing") and not p.get("gated")]
        scored_by_id: dict[str, dict] = {}
        if to_score:
            with ThreadPoolExecutor(max_workers=min(_WORKERS, len(to_score))) as ex:
                for r in ex.map(_score_one, to_score):
                    scored_by_id[r["company_id"]] = r

        out_rows: list[dict] = []
        served: set[str] = set()
        scored = gated = failed = 0
        for p in prepared:
            cid = p["company_id"]
            if p.get("missing"):
                out_rows.append({"company_id": cid, "error": "not found for tenant"})
                failed += 1
                continue
            common = {k: p[k] for k in ("company_id", "domain", "name", "prior_label",
                                        "prior_score_total", "prior_subscores")}
            if p.get("gated"):
                gv = p["gate_verdict"]
                out_rows.append({**common, "gated": True, "label": gv.label,
                                 "score_total": gv.score_total, "subscores": gv.subscores,
                                 "reason": gv.reason, "served_model": None})
                gated += 1
                continue
            r = scored_by_id.get(cid, {})
            if r.get("error"):
                out_rows.append({**common, "gated": False, "error": r["error"],
                                 "latency_ms": r.get("latency_ms")})
                failed += 1
                continue
            if r.get("served_model"):
                served.add(r["served_model"])
            out_rows.append({**common, "gated": False, **{k: r.get(k) for k in (
                "served_model", "latency_ms", "cost_usd", "label", "score_total",
                "subscores", "liveness", "icp", "reason")}})
            scored += 1

        log.info(
            "model_compare model=%s ids=%d scored=%d gated=%d failed=%d served=%s",
            model, len(ids), scored, gated, failed, sorted(served),
        )
        return {
            "model": model,
            "served_models": sorted(served),
            "count": len(ids),
            "scored": scored,
            "gated": gated,
            "failed": failed,
            "rows": out_rows,
        }
    finally:
        db.close()


def _run_classify(event: dict) -> dict:
    """Stage-0 business-model classifier A/B (READ-ONLY). Re-run `classify_business_model` with the
    requested model over `event['company_ids']` and return each row's `{business_model, hq_country,
    has_b2b_line}` alongside the stored production values. No web, no gate — the classifier's inputs
    (`_classify_payload`: identity + description/industries/keywords) are static, so this is a pure
    model-vs-model diff with zero web-drift confound. Never mutates the company row."""
    from app.core.db import get_session
    from app.domains.prospects.router import _classify_payload
    from app.models import Company

    tid = uuid.UUID(str(event["tenant_id"]))
    model = event["model"]
    ids = [uuid.UUID(str(x)) for x in (event.get("company_ids") or [])]
    if not ids:
        return {"task": "classify", "model": model, "served_models": [], "count": 0,
                "ok": 0, "failed": 0, "rows": []}

    db = get_session()
    try:
        rows = db.query(Company).filter(Company.tenant_id == tid, Company.id.in_(ids)).all()
        by_id = {str(c.id): c for c in rows}
        prepared: list[dict] = []
        for cid in [str(i) for i in ids]:
            c = by_id.get(cid)
            if c is None:
                prepared.append({"company_id": cid, "missing": True})
                continue
            comps = c.fit_components or {}
            prepared.append({
                "company_id": cid,
                "domain": c.domain,
                "name": c.name,
                "payload": _classify_payload(c),
                "prior_business_model": comps.get("business_model"),
                "prior_hq_country": (comps.get("hq_country") or "").strip(),
                "prior_has_b2b_line": bool(comps.get("has_b2b_line")),
            })

        def _classify_one(item: dict) -> dict:
            t0 = time.monotonic()
            try:
                r = fit.classify_business_model(
                    tenant_id=tid, company=item["payload"], models=[model]
                )
            except LlmError as e:
                return {"company_id": item["company_id"], "error": f"{e.status}: {e}"[:200]}
            return {
                "company_id": item["company_id"],
                "served_model": r.get("model"),
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "cost_usd": r.get("cost_usd"),
                "business_model": r.get("business_model"),
                "hq_country": r.get("hq_country"),
                "has_b2b_line": r.get("has_b2b_line"),
            }

        to_do = [p for p in prepared if not p.get("missing")]
        done: dict[str, dict] = {}
        if to_do:
            with ThreadPoolExecutor(max_workers=min(_WORKERS, len(to_do))) as ex:
                for r in ex.map(_classify_one, to_do):
                    done[r["company_id"]] = r

        out_rows: list[dict] = []
        served: set[str] = set()
        ok = failed = 0
        for p in prepared:
            cid = p["company_id"]
            common = {k: p.get(k) for k in ("company_id", "domain", "name",
                                            "prior_business_model", "prior_hq_country",
                                            "prior_has_b2b_line")}
            if p.get("missing"):
                out_rows.append({"company_id": cid, "error": "not found for tenant"})
                failed += 1
                continue
            r = done.get(cid, {})
            if r.get("error"):
                out_rows.append({**common, "error": r["error"]})
                failed += 1
                continue
            if r.get("served_model"):
                served.add(r["served_model"])
            out_rows.append({**common, **{k: r.get(k) for k in (
                "served_model", "latency_ms", "cost_usd",
                "business_model", "hq_country", "has_b2b_line")}})
            ok += 1

        log.info("model_compare[classify] model=%s ids=%d ok=%d failed=%d served=%s",
                 model, len(ids), ok, failed, sorted(served))
        return {
            "task": "classify",
            "model": model,
            "served_models": sorted(served),
            "count": len(ids),
            "ok": ok,
            "failed": failed,
            "rows": out_rows,
        }
    finally:
        db.close()
