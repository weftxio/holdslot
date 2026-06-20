"""Prospect routes — the Clay seed + AI sourcing loop made real (C2–C6 backend).

One suppression gate (C2) and one scoring door (C3) that the AI loop (C5) reuses, exactly as the
plan's critical path requires. Tenant scope × role is enforced by the A4 central guard, so every
query is scoped to the caller's client. The heavy lifting lives in the pure modules; this layer
is orchestration + persistence.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import AccessContext, get_db, require_membership
from app.domains.prospects import clay, fit, sourcing
from app.domains.prospects.schemas import (
    AcceptIn,
    CandidateIn,
    DropSummary,
    ImportResult,
    ProspectOut,
    ResearchRequestIn,
    ResearchResult,
    ResearchRunOut,
    SourcingCandidate,
    SourcingDocIn,
    SourcingDocList,
    SourcingDocOut,
    SourcingRoundIn,
    SourcingRoundResult,
)
from app.domains.prospects.suppression import Candidate, extract_exclusions, suppress
from app.integrations.openrouter.client import LlmError
from app.models import Brief, MembershipRole, Prospect, ResearchRun, ResearchSpec, SourcingDoc

router = APIRouter(tags=["prospects"])

_VALID_DOC_KINDS = ("sourcing_prompt", "fit_rubric")


# --------------------------------------------------------------------------- helpers


def _new_run_id() -> str:
    return uuid.uuid4().hex


def _candidate(c: CandidateIn) -> Candidate:
    return Candidate(**c.model_dump())


def _seen_keys(db: Session, tenant_id, *, include_pending: bool = True) -> set[str]:
    """Identity keys already in the system of record for this tenant — a re-push pays twice (C2).

    A pushed prospect exists as a row the moment it is sent to Clay (see `run_research`), so this
    set reflects paid pushes even before the CSV round-trips back. `include_pending=False` excludes
    `pending_review` AI candidates (never pushed) — used by accept, which must not treat the very
    rows it is accepting as already-seen duplicates.
    """
    stmt = select(Prospect.identity_key).where(Prospect.tenant_id == tenant_id)
    if not include_pending:
        stmt = stmt.where(Prospect.status != "pending_review")
    rows = db.execute(stmt).scalars()
    return {k for k in rows if k}


def _latest_brief(db: Session, tenant_id) -> Brief | None:
    return db.execute(select(Brief).where(Brief.tenant_id == tenant_id)).scalar_one_or_none()


def _latest_spec(db: Session, tenant_id) -> ResearchSpec | None:
    """The newest ResearchSpec version for a tenant — the one query four call sites used to
    hand-roll. Version-ordering / tenant-scope lives in exactly one place now."""
    return (
        db.execute(
            select(ResearchSpec)
            .where(ResearchSpec.tenant_id == tenant_id)
            .order_by(ResearchSpec.version.desc())
        )
        .scalars()
        .first()
    )


def _build_exclusions(brief: Brief | None, spec: ResearchSpec | None):
    return extract_exclusions(brief.data if brief else {}, spec.spec if spec else None)


def _exclusions(db: Session, tenant_id):
    return _build_exclusions(_latest_brief(db, tenant_id), _latest_spec(db, tenant_id))


def _push_to_clay(
    survivors: list[Candidate], run_id: str
) -> tuple[list[Candidate], Exception | None]:
    """Push survivors to Clay; return (accepted_survivors, error) — never raises.

    On a mid-batch transport failure, only the survivors Clay accepted *before* the failure are
    returned, with the error. The caller commits those (so paid identities are recorded for the
    `_seen_keys` dedupe → a retry never pays twice) and only then surfaces the error.
    """
    if not survivors:
        return [], None
    rows = [clay.assemble_push_row(c, run_id) for c in survivors]
    try:
        accepted_rows = clay.push_rows(rows)
        err: Exception | None = None
    except clay.ClayPushError as e:
        accepted_rows, err = e.accepted, e
    accepted_keys = {r["identity_key"] for r in accepted_rows}
    return [c for c in survivors if c.identity_key in accepted_keys], err


def _latest_doc(db: Session, tenant_id, kind: str) -> SourcingDoc | None:
    return (
        db.execute(
            select(SourcingDoc)
            .where(SourcingDoc.tenant_id == tenant_id, SourcingDoc.kind == kind)
            .order_by(SourcingDoc.version.desc())
        )
        .scalars()
        .first()
    )


def _drops(dropped) -> list[DropSummary]:
    counts = Counter(reason for _c, reason in dropped)
    return [DropSummary(reason=r, count=n) for r, n in counts.items()]


def _prospect_out(p: Prospect) -> ProspectOut:
    comps = p.fit_components or {}
    return ProspectOut(
        id=str(p.id),
        identity_key=p.identity_key,
        icp_id=str(p.icp_id) if p.icp_id else None,
        run_id=p.run_id,
        full_name=(p.enrichment or {}).get("full_name", ""),
        company=(p.enrichment or {}).get("company", ""),
        domain=(p.enrichment or {}).get("domain", ""),
        email=(p.enrichment or {}).get("email", ""),
        email_valid=p.email_valid,
        title=(p.enrichment or {}).get("title", ""),
        company_industry=(p.enrichment or {}).get("company_industry", ""),
        company_size=(p.enrichment or {}).get("company_size", ""),
        fit_score=p.fit_score,
        fit_tier=p.fit_tier,
        fit_reason=comps.get("fit_reason", ""),
        reason_tags=comps.get("reason_tags", []),
        source=p.source,
        status=p.status,
        created_at=p.created_at.isoformat() if p.created_at else None,
    )


# --------------------------------------------------------------------------- C6 list


@router.get("/{client}/prospects", response_model=list[ProspectOut])
def list_prospects(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[ProspectOut]:
    rows = db.execute(
        select(Prospect)
        .where(Prospect.tenant_id == ctx.tenant.id)
        .order_by(Prospect.fit_score.desc().nullslast(), Prospect.created_at.desc())
    ).scalars()
    return [_prospect_out(p) for p in rows]


# --------------------------------------------------------------------------- C2 push


@router.post("/{client}/icps/{icp_id}/research", response_model=ResearchResult)
def run_research(
    icp_id: str,
    body: ResearchRequestIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ResearchResult:
    """C2 — suppress a candidate set, then push survivors to the one Clay webhook (tagged
    run_id + identity_key, no tenant). Suppressed/duplicate rows are never pushed (0 credits)."""
    candidates = [_candidate(c) for c in body.candidates]
    result = suppress(candidates, _exclusions(db, ctx.tenant.id), _seen_keys(db, ctx.tenant.id))

    run_id = _new_run_id()
    spec = _latest_spec(db, ctx.tenant.id)
    icp_uuid = uuid.UUID(icp_id) if icp_id else None
    run = ResearchRun(
        tenant_id=ctx.tenant.id,
        run_id=run_id,
        icp_id=icp_uuid,
        spec_version=spec.version if spec else None,
        source="clay",
    )
    db.add(run)
    db.commit()

    # Push, then record each ACCEPTED identity as a Prospect (status=pushed). The DB is the sole
    # system of record, so a paid push must be visible to `_seen_keys` *before* the CSV round-trips
    # back — otherwise a re-push or AI round in that window pays Clay twice. On a partial transport
    # failure we record exactly the rows Clay accepted, then surface the error: never double-pay,
    # never strand a row that never reached Clay. Import later upserts on (tenant, identity_key).
    accepted, err = _push_to_clay(result.survivors, run_id)
    for c in accepted:
        db.add(
            Prospect(
                tenant_id=ctx.tenant.id,
                icp_id=icp_uuid,
                spec_version=spec.version if spec else None,
                run_id=run_id,
                identity_key=c.identity_key,
                enrichment=c.to_enrichment(),
                source="clay",
                status="pushed",
            )
        )
    run.rows_pushed = len(accepted)
    db.commit()
    if err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Clay push failed: {err}") from err

    return ResearchResult(
        run_id=run_id,
        received=len(candidates),
        pushed=len(accepted),
        suppressed=len(result.dropped),
        drops=_drops(result.dropped),
    )


# --------------------------------------------------------------------------- C3 ingest+score


def _decode_csv(payload: str) -> str:
    """Accept a base64-wrapped CSV (the $default proxy path) or raw CSV text."""
    if "," in payload[:64] and "run_id" in payload[:200]:
        return payload  # looks like raw CSV already
    try:
        return base64.b64decode(payload, validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return payload


def _build_targeting(brief: Brief | None, spec: ResearchSpec | None) -> dict:
    return {"brief": brief.data if brief else {}, "spec": spec.spec if spec else {}}


@router.post("/{client}/prospects/import", response_model=ImportResult)
def import_prospects(
    body: dict,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ImportResult:
    """C3 — operator's CSV export → parse by header → suppress → upsert prospect → fit-score.

    Synchronous, no SQS (the [SCALE] swap is the signed `POST /clay/results` callback). Re-import
    is idempotent on (tenant, identity_key); each score records its rubric version via llm_call.
    """
    raw = body.get("csv") or body.get("file") or ""
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing csv payload")
    rows = clay.parse_export_csv(_decode_csv(raw))
    if not rows:
        return ImportResult(parsed=0, stored=0, suppressed=0, scored=0)

    brief, spec = _latest_brief(db, ctx.tenant.id), _latest_spec(db, ctx.tenant.id)
    exclusions = _build_exclusions(brief, spec)
    targeting = _build_targeting(brief, spec)
    rubric = _latest_doc(db, ctx.tenant.id, "fit_rubric")
    rubric_body = rubric.body if rubric else ""

    stored = suppressed = scored = score_errors = 0
    by_tier: Counter = Counter()
    # A prospect is owned by the run that FIRST landed it (prospect.run_id, never reassigned). Both
    # the accepted tally and the scoring cost roll up to that owning run, so a re-import under a new
    # run_id can't double-count one identity across two runs' scoreboards.
    touched: Counter = Counter()  # accepted prospects per owning-run → runs to recompute
    run_cost: dict[str, float] = {}  # new fit-scoring LLM cost per owning-run → cost_usd (C4)

    for er in rows:
        cand = Candidate(
            full_name=er.full_name, company=er.company, domain=er.domain, email=er.email
        )
        if exclusions.blocks(cand):
            suppressed += 1
            continue

        enrichment = {
            "full_name": er.full_name,
            "company": er.company,
            "domain": er.domain,
            "company_domain": er.company_domain,
            "linkedin_url": er.linkedin_url,
            "email": er.email,
            "provider": er.provider,
            "title": er.title,
            "seniority": er.seniority,
            "company_size": er.company_size,
            "company_industry": er.company_industry,
            **er.enrichment,
        }
        prospect = db.execute(
            select(Prospect).where(
                Prospect.tenant_id == ctx.tenant.id, Prospect.identity_key == er.identity_key
            )
        ).scalar_one_or_none()
        if prospect is None:
            prospect = Prospect(
                tenant_id=ctx.tenant.id, identity_key=er.identity_key, source="clay"
            )
            db.add(prospect)
        # Capture the prior fit state *before* overwriting enrichment — a re-import of an
        # unchanged row must not re-pay the LLM (idempotent on (tenant, identity_key)).
        prior_enrichment = prospect.enrichment or {}
        already_scored = prospect.status == "scored" and prospect.fit_score is not None
        # Bind to the first run that landed this identity; never reassign it on a re-import.
        if not prospect.run_id:
            prospect.run_id = er.run_id
        owning_run = prospect.run_id
        prospect.enrichment = enrichment
        prospect.email_valid = er.email_valid
        prospect.last_enriched_at = func.now()
        stored += 1

        # Rubric gate (§1): no contact path at all → gate out without spending an LLM call. A gated
        # row is NOT an accepted row, so it never counts toward rows_accepted or a fit tier.
        if not er.email:
            prospect.fit_score, prospect.fit_tier = None, "Below"
            prospect.fit_components = {"gated": "no_email"}
            prospect.status = "gated"
            by_tier["Gated"] += 1
            continue

        # Re-import guard: an already-scored row whose enrichment is byte-for-byte unchanged keeps
        # its score without a second paid LLM call. Comparing the whole enrichment (not just email)
        # means a richer re-enrichment — new title/size/industry — correctly re-scores below.
        if already_scored and prior_enrichment == enrichment:
            scored += 1
            by_tier[prospect.fit_tier or "Below"] += 1
            touched[owning_run] += 1
            continue

        try:
            scored_row = fit.score(
                tenant_id=ctx.tenant.id,
                rubric_body=rubric_body,
                enrichment=enrichment,
                targeting=targeting,
            )
        except LlmError:
            prospect.status = "score_error"
            score_errors += 1
            continue
        prospect.fit_score = scored_row["fit_score"]
        prospect.fit_tier = scored_row["fit_tier"]
        prospect.fit_components = scored_row["fit_components"]
        prospect.status = "scored"
        scored += 1
        by_tier[scored_row["fit_tier"]] += 1
        touched[owning_run] += 1
        cost = scored_row.get("cost_usd")
        if cost:
            run_cost[owning_run] = run_cost.get(owning_run, 0.0) + float(cost)

    # C4 — recompute each affected run's accepted tally from the source of truth (its owned,
    # currently-scored prospects), not from a per-import delta, so a re-import — same run or under
    # a new run_id — converges instead of double-counting one identity. cost_usd is accumulated
    # (only a real LLM call adds cost; unchanged re-imports add none). One commit, rolls back clean.
    if touched:
        runs = db.execute(
            select(ResearchRun).where(
                ResearchRun.tenant_id == ctx.tenant.id, ResearchRun.run_id.in_(touched)
            )
        ).scalars()
        for run in runs:
            run.rows_accepted = db.execute(
                select(func.count())
                .select_from(Prospect)
                .where(
                    Prospect.tenant_id == ctx.tenant.id,
                    Prospect.run_id == run.run_id,
                    Prospect.status == "scored",
                )
            ).scalar_one()
            if run_cost.get(run.run_id):
                run.cost_usd = round(float(run.cost_usd or 0) + run_cost[run.run_id], 6)
    db.commit()

    dominant = touched.most_common(1)[0][0] if touched else None
    return ImportResult(
        run_id=dominant,
        parsed=len(rows),
        stored=stored,
        suppressed=suppressed,
        scored=scored,
        score_errors=score_errors,
        by_tier=dict(by_tier),
    )


# --------------------------------------------------------------------------- C4 scoreboard


@router.get("/{client}/research-runs", response_model=list[ResearchRunOut])
def list_research_runs(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[ResearchRunOut]:
    rows = db.execute(
        select(ResearchRun)
        .where(ResearchRun.tenant_id == ctx.tenant.id)
        .order_by(ResearchRun.created_at.desc())
    ).scalars()
    out = []
    for r in rows:
        cost = float(r.cost_usd) if r.cost_usd is not None else None
        per = round(cost / r.rows_accepted, 6) if cost and r.rows_accepted else None
        out.append(
            ResearchRunOut(
                run_id=r.run_id,
                source=r.source,
                prompt_version=r.prompt_version,
                rubric_version=r.rubric_version,
                rows_pushed=r.rows_pushed,
                rows_accepted=r.rows_accepted,
                cost_usd=cost,
                cost_per_accepted=per,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
        )
    return out


# --------------------------------------------------------------------------- C5/C6 sourcing docs


def _doc_out(d: SourcingDoc | None) -> SourcingDocOut | None:
    if d is None:
        return None
    return SourcingDocOut(
        kind=d.kind,
        version=d.version,
        body=d.body,
        created_at=d.created_at.isoformat() if d.created_at else None,
    )


@router.get("/{client}/sourcing-docs", response_model=SourcingDocList)
def get_sourcing_docs(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> SourcingDocList:
    versions = {"sourcing_prompt": [], "fit_rubric": []}
    for kind in _VALID_DOC_KINDS:
        versions[kind] = list(
            db.execute(
                select(SourcingDoc.version)
                .where(SourcingDoc.tenant_id == ctx.tenant.id, SourcingDoc.kind == kind)
                .order_by(SourcingDoc.version.desc())
            ).scalars()
        )
    return SourcingDocList(
        sourcing_prompt=_doc_out(_latest_doc(db, ctx.tenant.id, "sourcing_prompt")),
        fit_rubric=_doc_out(_latest_doc(db, ctx.tenant.id, "fit_rubric")),
        prompt_versions=versions["sourcing_prompt"],
        rubric_versions=versions["fit_rubric"],
    )


@router.post("/{client}/sourcing-docs", response_model=SourcingDocOut, status_code=201)
def save_sourcing_doc(
    body: SourcingDocIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> SourcingDocOut:
    """Append-only — save the founder's edit as the next version of one kind."""
    if body.kind not in _VALID_DOC_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown sourcing_doc kind")
    latest = _latest_doc(db, ctx.tenant.id, body.kind)
    doc = SourcingDoc(
        tenant_id=ctx.tenant.id,
        kind=body.kind,
        version=(latest.version + 1) if latest else 1,
        body=body.body,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_out(doc)


# --------------------------------------------------------------------------- C5 sourcing round


@router.post("/{client}/sourcing-rounds", response_model=SourcingRoundResult)
def run_sourcing_round(
    body: SourcingRoundIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> SourcingRoundResult:
    """C5 — one AI sourcing call (DeepSeek + web search) → validate → suppress → land candidates
    as `ai_loop · pending_review` for founder accept/reject. Reuses the C2 suppression gate."""
    prompt_doc = _latest_doc(db, ctx.tenant.id, "sourcing_prompt")
    if prompt_doc is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no sourcing prompt saved")
    rubric_doc = _latest_doc(db, ctx.tenant.id, "fit_rubric")

    brief, spec = _latest_brief(db, ctx.tenant.id), _latest_spec(db, ctx.tenant.id)

    # Seed sample — existing passed-fit prospects as lookalike anchors.
    seed_rows = db.execute(
        select(Prospect)
        .where(Prospect.tenant_id == ctx.tenant.id, Prospect.fit_tier.in_(("Strong", "Good")))
        .order_by(Prospect.fit_score.desc().nullslast())
        .limit(max(0, body.seed_limit))
    ).scalars()
    seed_sample = [
        {
            "company": (p.enrichment or {}).get("company", ""),
            "domain": (p.enrichment or {}).get("domain", ""),
            "title": (p.enrichment or {}).get("title", ""),
        }
        for p in seed_rows
    ]
    exclusions = _exclusions(db, ctx.tenant.id)
    exclusion_summary = {
        "domains": sorted(exclusions.domains),
        "emails": sorted(exclusions.emails),
        "linkedin_slugs": sorted(exclusions.linkedin_slugs),
    }

    prompt_version = f"sourcing-prompt-v{prompt_doc.version}"
    try:
        result = sourcing.run_round(
            tenant_id=ctx.tenant.id,
            prompt_body=prompt_doc.body,
            prompt_version=prompt_version,
            brief=brief.data if brief else {},
            spec=spec.spec if spec else {},
            seed_sample=seed_sample,
            exclusion_summary=exclusion_summary,
        )
    except LlmError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    raws = result.data.get("candidates", [])
    valid, _rejected = sourcing.validate_candidates(raws)
    cand_objs = [(raw, sourcing.to_candidate(raw)) for raw in valid]
    sup = suppress([c for _r, c in cand_objs], exclusions, _seen_keys(db, ctx.tenant.id))
    survivor_keys = set(sup.survivor_keys)

    run_id = _new_run_id()
    icp_uuid = uuid.UUID(body.icp_id) if body.icp_id else None
    run = ResearchRun(
        tenant_id=ctx.tenant.id,
        run_id=run_id,
        icp_id=icp_uuid,
        spec_version=spec.version if spec else None,
        source="ai_loop",
        prompt_version=prompt_version,
        rubric_version=f"fit-rubric-v{rubric_doc.version}" if rubric_doc else None,
        # The round's sourcing-LLM cost (DeepSeek + web search) recorded on the run so the C4
        # scoreboard shows $/candidate-surfaced; the per-call detail still lives on `llm_call`.
        cost_usd=result.cost_usd,
    )
    db.add(run)

    pending: list[SourcingCandidate] = []
    for raw, cand in cand_objs:
        if cand.identity_key not in survivor_keys:
            continue
        survivor_keys.discard(cand.identity_key)  # collapse intra-batch dupes
        prospect = Prospect(
            tenant_id=ctx.tenant.id,
            icp_id=icp_uuid,
            run_id=run_id,
            identity_key=cand.identity_key,
            enrichment=cand.to_enrichment(),
            source="ai_loop",
            source_lineage={"prompt_version": prompt_version, "evidence": raw},
            status="pending_review",
            fit_tier=raw.get("preliminary_tier", ""),
        )
        db.add(prospect)
        pending.append(
            SourcingCandidate(
                identity_key=cand.identity_key,
                full_name=cand.full_name,
                company=cand.company,
                domain=cand.domain,
                preliminary_tier=raw.get("preliminary_tier", ""),
                evidence=raw,
            )
        )
    # Nothing is pushed to Clay in a sourcing round (that happens on accept), so rows_pushed stays
    # 0 — it means "identities sent to Clay" for both sources. rows_accepted = candidates surfaced
    # for review, which pairs with this round's sourcing cost_usd → C4 reads $/candidate-surfaced.
    run.rows_accepted = len(pending)
    db.commit()

    return SourcingRoundResult(
        run_id=run_id,
        returned=len(raws),
        validated=len(valid),
        suppressed=len(valid) - len(pending),
        pending_review=len(pending),
        candidates=pending,
    )


# --------------------------------------------------------------------------- C5 accept


@router.post("/{client}/prospects/accept", response_model=ResearchResult)
def accept_candidates(
    body: AcceptIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> ResearchResult:
    """C5 — accept pending AI candidates and push them through the SAME C2 path to Clay.

    We push BEFORE persisting status: only the candidates Clay actually accepted are marked
    `accepted`; ones excluded since sourcing are marked `suppressed`; a survivor whose push never
    reached Clay (transport failure) is left `pending_review` so it stays re-acceptable rather than
    stranded as a fake `accepted`. Dedup runs against already-pushed identities
    (`include_pending=False`) so a candidate already enriched via C2 / a prior accept is not paid
    for twice — while the very rows being accepted are not mistaken for duplicates of themselves.
    """
    if not body.identity_keys:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no identity_keys")
    rows = (
        db.execute(
            select(Prospect).where(
                Prospect.tenant_id == ctx.tenant.id,
                Prospect.identity_key.in_(body.identity_keys),
                Prospect.status == "pending_review",
            )
        )
        .scalars()
        .all()
    )

    candidates = [Candidate.from_enrichment(p.enrichment) for p in rows]
    result = suppress(
        candidates,
        _exclusions(db, ctx.tenant.id),
        _seen_keys(db, ctx.tenant.id, include_pending=False),
    )

    run_id = _new_run_id()
    run = ResearchRun(tenant_id=ctx.tenant.id, run_id=run_id, source="ai_loop")
    db.add(run)

    # Push first; record status from what Clay accepted. A 502 leaves un-pushed survivors as
    # pending_review (re-acceptable) instead of committing them as accepted-but-never-enriched.
    accepted, err = _push_to_clay(result.survivors, run_id)
    accepted_keys = {c.identity_key for c in accepted}
    survivor_keys = set(result.survivor_keys)
    for p in rows:
        if p.identity_key in accepted_keys:
            p.status = "accepted"
            p.run_id = run_id
        elif p.identity_key not in survivor_keys:
            # Excluded or already-enriched → not pushed; don't strand it as a fake "accepted".
            p.status = "suppressed"
        # else: survived suppression but its push didn't land → keep pending_review (re-acceptable).
    run.rows_pushed = len(accepted)
    db.commit()
    if err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Clay push failed: {err}") from err

    return ResearchResult(
        run_id=run_id,
        received=len(rows),
        pushed=len(accepted),
        suppressed=len(result.dropped),
        drops=_drops(result.dropped),
    )
