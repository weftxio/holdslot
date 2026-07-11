"""Async fit-scoring jobs (W4).

The five scoring-bearing surfaces — find-company, find-lookalikes, company/prospect rescore, and
the company field refresh — each fan out one fit-scoring LLM call per row. With DeepSeek V4 Pro
reasoning a single batch can exceed the API Gateway HTTP-API 30s cap, and the prior mitigation (the
web app chunking the work and driving it from the browser) dies the moment the tab closes. So the
work moves off the request path onto a background worker, like Brief→ResearchSpec structuring:

  * `enqueue_scoring(db, tenant_id, kind, params)` inserts a `scoring_job` (queued) and dispatches a
    worker, returning at once. A still-active job of the SAME kind is returned as-is (one in flight
    per tenant×kind) so a double-click never double-spends a (billed) batch.
  * Dispatch is environment-aware: Lambda self async-invoke (`InvocationType=Event`) on the same
    `{"holdslot_job": ...}` event contract `app.main` routes; a local daemon thread otherwise.
  * `run_scoring_job(...)` flips the job `running`→`done`/`error`, delegating the actual scoring to
    the per-kind handler in the prospects router (lazily imported to avoid an import cycle) and
    recording the run counts on `scoring_job.result`. The frontend polls the job until terminal.

This module owns the job lifecycle only; the scoring logic stays in the router with its helpers.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models import ScoringJob

log = logging.getLogger("holdslot.scoring")


def is_unique_violation(exc: BaseException) -> bool:
    """True if `exc` is a Postgres unique-violation (SQLSTATE 23505), HOWEVER the driver surfaced it
    (N29). Over psycopg SQLAlchemy raises `IntegrityError`, but the RDS Data API driver
    (aurora-data-api) can wrap it as a generic `DBAPIError`/`DatabaseError` — so match the SQLSTATE
    or the message text too, or the enqueue race would 500 on the live driver, not coalesce."""
    if isinstance(exc, IntegrityError):
        return True
    orig = getattr(exc, "orig", None)
    if getattr(orig, "sqlstate", None) == "23505" or getattr(orig, "pgcode", None) == "23505":
        return True
    text = str(orig if orig is not None else exc).lower()
    return "23505" in text or "duplicate key" in text or "unique constraint" in text

# Background-job event contract — same key as structuring; the VALUE selects the worker (see
# app.main.handler, which routes scoring vs. structuring events).
JOB_EVENT_KEY = "holdslot_job"
JOB_PROSPECT_SCORING = "prospect_scoring"

# Job kinds == scoring_job.kind. The router registers one handler per kind in SCORING_HANDLERS.
KIND_RESCORE_COMPANIES = "rescore_companies"
KIND_RESCORE_PROSPECTS = "rescore_prospects"
KIND_ENRICH_SCORE_PROSPECTS = "enrich_score_prospects"
KIND_FIND_COMPANY = "find_company"
KIND_FIND_LOOKALIKES = "find_lookalikes"
KIND_UPDATE_FIELDS = "update_fields"

_ACTIVE = ("queued", "running")
_ERR_MAX = 500  # cap the stored error message

# A worker runs inside a SINGLE Lambda invocation, so it cannot outlive the function timeout. A hard
# timeout kills it mid-run WITHOUT raising, so run_scoring_job's except/finally never fires and the
# job is left `running` forever (a zombie): the poll spins to its ceiling, AND enqueue_scoring
# coalesces every retry onto it, wedging the surface. So on each read we reap any non-terminal job
# older than a worker could possibly live → `error`, settling the poll and freeing the next.
#
# The window must exceed the WORST-CASE worker lifetime, else it reaps a job still legitimately
# scoring (R3): an async dispatch can sit up to `maximum_event_age_in_seconds` (120s, lambda.tf)
# before the worker even starts, then run the full `timeout` (300s) — 420s worst case. 480s = 420 +
# a 60s buffer. A false reap + a re-click would double-run a (billed) DeepSeek batch, which the
# atomic claim in `run_scoring_job` now also guards. This constant is the single source of truth:
# briefs/structuring imports it (was a drifting 360 copy — R27 dedupe).
MAX_JOB_AGE_SECONDS = 480


def _job_age_seconds(job: ScoringJob) -> float:
    created = job.created_at
    if created.tzinfo is None:  # aurora-data-api can hand back a naive UTC datetime
        created = created.replace(tzinfo=UTC)
    return (datetime.now(UTC) - created).total_seconds()


def _reap_if_stale(db: Session, job: ScoringJob) -> bool:
    """Flip a non-terminal job that outlived any possible worker run to `error`. Idempotent; returns
    True when it reaped (so callers stop treating the job as active/in-flight)."""
    if job.status not in _ACTIVE or _job_age_seconds(job) <= MAX_JOB_AGE_SECONDS:
        return False
    _fail(db, job, "scoring worker timed out — try a smaller selection")
    log.warning("reaped stale scoring job kind=%s id=%s", job.kind, job.id)
    return True


def job_by_id(db: Session, tenant_id, job_id) -> ScoringJob | None:
    """A specific job, tenant-scoped (the poll fetches by id once kicked off)."""
    job = db.execute(
        select(ScoringJob).where(ScoringJob.tenant_id == tenant_id, ScoringJob.id == job_id)
    ).scalar_one_or_none()
    if job is not None:
        _reap_if_stale(db, job)
    return job


def _active_job(db: Session, tenant_id, kind: str) -> ScoringJob | None:
    """The newest queued/running job of this kind for the tenant (the coalesce target)."""
    return db.execute(
        select(ScoringJob)
        .where(
            ScoringJob.tenant_id == tenant_id,
            ScoringJob.kind == kind,
            ScoringJob.status.in_(_ACTIVE),
        )
        .order_by(ScoringJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def enqueue_scoring(db: Session, tenant_id, kind: str, params: dict) -> ScoringJob:
    """Create a queued job + dispatch the worker. A still-active job of this kind is returned
    unchanged so a double-click coalesces onto the in-flight batch (never double-spends)."""
    active = _active_job(db, tenant_id, kind)
    # Coalesce onto a genuinely in-flight job (prevents a double-click double-spend); but a stale
    # zombie must NOT wedge the surface — reap it and fall through to enqueue a fresh one.
    if active is not None and not _reap_if_stale(db, active):
        return active

    job = ScoringJob(tenant_id=tenant_id, kind=kind, params=params, status="queued")
    db.add(job)
    try:
        db.commit()
    except DBAPIError as exc:
        # A concurrent POST won the (tenant, kind) partial-unique race (0027) between our check and
        # our insert — coalesce onto its job rather than 500 (like the "already active" path). N29 —
        # match the unique violation across driver shapes, not just SQLAlchemy's IntegrityError.
        if not is_unique_violation(exc):
            raise
        db.rollback()
        winner = _active_job(db, tenant_id, kind)
        if winner is not None:
            return winner
        raise  # constraint fired but no active row visible — genuinely unexpected, surface it
    db.refresh(job)
    # N30 — the job is committed `queued`; if the dispatch invoke fails, mark it `error` here so it
    # doesn't sit queued forever (the reaper would only flip it after MAX_JOB_AGE_SECONDS), and
    # surface the failure to the caller.
    try:
        _dispatch(tenant_id, job.id)
    except Exception as exc:
        _fail(db, job, f"dispatch failed: {exc!r}")
        raise HTTPException(status_code=503, detail="could not start the job") from exc
    return job


def _dispatch(tenant_id, job_id) -> None:
    """Run the worker off the request path: Lambda self async-invoke, else a local daemon thread."""
    payload = {
        JOB_EVENT_KEY: JOB_PROSPECT_SCORING,
        "tenant_id": str(tenant_id),
        "job_id": str(job_id),
    }
    fn = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if fn:
        import boto3

        boto3.client("lambda").invoke(
            FunctionName=fn, InvocationType="Event", Payload=json.dumps(payload).encode()
        )
    else:
        threading.Thread(
            target=run_scoring_job,
            args=(payload["tenant_id"], payload["job_id"]),
            daemon=True,
        ).start()


def handle_job_event(event: dict) -> dict:
    """Entry-handler hook for a scoring background-job Lambda event (see app.main.handler)."""
    if event.get(JOB_EVENT_KEY) == JOB_PROSPECT_SCORING:
        run_scoring_job(event["tenant_id"], event["job_id"])
    else:
        log.warning("unknown scoring job event: %s", event.get(JOB_EVENT_KEY))
    return {"ok": True}


def _fail(db: Session, job: ScoringJob, message: str) -> None:
    job.status = "error"
    job.error = message[:_ERR_MAX]
    db.commit()


def _finalize(db: Session, job_id, status: str, *, result: dict | None = None,
              error: str | None = None) -> bool:
    """Worker terminal write, guarded on the worker still OWNING the job (`status='running'`). If
    the job was reaped mid-run (falsely, or claimed by a duplicate dispatch), it's no longer active,
    so this no-ops instead of resurrecting a reaped `error` job to `done` (the R3 double-run tell).
    Returns True iff it wrote."""
    values: dict = {"status": status}
    if result is not None:
        values["result"] = result
    if error is not None:
        values["error"] = error[:_ERR_MAX]
    wrote = db.execute(
        update(ScoringJob)
        .where(ScoringJob.id == job_id, ScoringJob.status == "running")
        .values(**values)
    ).rowcount
    db.commit()
    return bool(wrote)


def run_scoring_job(tenant_id, job_id, session_factory=None) -> None:
    """The worker: run the kind's scoring handler, flipping the job terminal + recording counts.

    Owns its own Session (it runs on a thread or a fresh Lambda invocation, never inside a request).
    Per-row LLM failures are absorbed by the handler (an un-scored row is kept, not fatal); only a
    hard error flips the job to `error`. Each handler returns the `result` counts to store.
    """
    tid = uuid.UUID(str(tenant_id))
    jid = uuid.UUID(str(job_id))
    if session_factory is None:
        from app.core.db import get_session

        session_factory = get_session
    db = session_factory()
    try:
        job = db.get(ScoringJob, jid)
        if job is None:
            log.warning("scoring job vanished (job_id=%s)", job_id)
            return
        # R3 — claim the job ATOMICALLY. If the row isn't `queued` (a duplicate dispatch already
        # claimed it, it's terminal, or the reaper flipped it to `error`), another path owns it:
        # abort with NO side effects so we never double-run the (billed) batch or clobber its state.
        kind, params = job.kind, (job.params or {})
        claimed = db.execute(
            update(ScoringJob)
            .where(ScoringJob.id == jid, ScoringJob.status == "queued")
            .values(status="running")
        ).rowcount
        db.commit()
        if not claimed:
            log.warning("scoring job %s not claimable (dup dispatch / terminal / reaped) — abort",
                        job_id)
            return

        # The per-kind handlers live in the router (they own the scoring helpers); import lazily so
        # this module never imports the router at load time (the router imports this one).
        from app.domains.prospects.router import SCORING_HANDLERS

        handler = SCORING_HANDLERS.get(kind)
        if handler is None:
            _finalize(db, jid, "error", error=f"unknown scoring kind: {kind}")
            return

        try:
            result = handler(db, tid, params)
        except HTTPException as e:
            # A handler validation/upstream error (e.g. no research scope, Apollo 502) — surface its
            # message as the job error rather than a generic "internal error" for the FE to show.
            db.rollback()
            _finalize(db, jid, "error", error=str(e.detail) if e.detail else "scoring failed")
            return
        if _finalize(db, jid, "done", result=result or {}):
            log.info("scoring[%s] job=%s done %s", kind, job_id, result or {})
        else:
            log.warning("scoring[%s] job=%s finished but no longer owned (reaped?) — not written",
                        kind, job_id)
    except Exception:
        log.exception("scoring job failed (job_id=%s)", job_id)
        try:
            db.rollback()
            _finalize(db, jid, "error", error="internal error during scoring")
        except Exception:
            log.exception("could not record scoring failure (job_id=%s)", job_id)
    finally:
        db.close()
