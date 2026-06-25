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

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScoringJob

log = logging.getLogger("holdslot.scoring")

# Background-job event contract — same key as structuring; the VALUE selects the worker (see
# app.main.handler, which routes scoring vs. structuring events).
JOB_EVENT_KEY = "holdslot_job"
JOB_PROSPECT_SCORING = "prospect_scoring"

# Job kinds == scoring_job.kind. The router registers one handler per kind in SCORING_HANDLERS.
KIND_RESCORE_COMPANIES = "rescore_companies"
KIND_RESCORE_PROSPECTS = "rescore_prospects"
KIND_FIND_COMPANY = "find_company"
KIND_FIND_LOOKALIKES = "find_lookalikes"
KIND_UPDATE_FIELDS = "update_fields"

_ACTIVE = ("queued", "running")
_ERR_MAX = 500  # cap the stored error message


def latest_job(db: Session, tenant_id, kind: str) -> ScoringJob | None:
    """The most recent job of this kind for the tenant (what the status poll reads)."""
    return db.execute(
        select(ScoringJob)
        .where(ScoringJob.tenant_id == tenant_id, ScoringJob.kind == kind)
        .order_by(ScoringJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def job_by_id(db: Session, tenant_id, job_id) -> ScoringJob | None:
    """A specific job, tenant-scoped (the poll fetches by id once kicked off)."""
    return db.execute(
        select(ScoringJob).where(ScoringJob.tenant_id == tenant_id, ScoringJob.id == job_id)
    ).scalar_one_or_none()


def enqueue_scoring(db: Session, tenant_id, kind: str, params: dict) -> ScoringJob:
    """Create a queued job + dispatch the worker. A still-active job of this kind is returned
    unchanged so a double-click coalesces onto the in-flight batch (never double-spends)."""
    active = db.execute(
        select(ScoringJob)
        .where(
            ScoringJob.tenant_id == tenant_id,
            ScoringJob.kind == kind,
            ScoringJob.status.in_(_ACTIVE),
        )
        .order_by(ScoringJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if active is not None:
        return active

    job = ScoringJob(tenant_id=tenant_id, kind=kind, params=params, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    _dispatch(tenant_id, job.id)
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
        job.status = "running"
        db.commit()

        # The per-kind handlers live in the router (they own the scoring helpers); import lazily so
        # this module never imports the router at load time (the router imports this one).
        from app.domains.prospects.router import SCORING_HANDLERS

        handler = SCORING_HANDLERS.get(job.kind)
        if handler is None:
            _fail(db, job, f"unknown scoring kind: {job.kind}")
            return

        try:
            result = handler(db, tid, job.params or {})
        except HTTPException as e:
            # A handler validation/upstream error (e.g. no research scope, Apollo 502) — surface its
            # message as the job error rather than a generic "internal error" for the FE to show.
            db.rollback()
            _fail(db, job, str(e.detail) if e.detail else "scoring failed")
            return
        job.result = result or {}
        job.status = "done"
        db.commit()
        log.info("scoring[%s] job=%s done %s", job.kind, job_id, job.result)
    except Exception:
        log.exception("scoring job failed (job_id=%s)", job_id)
        try:
            db.rollback()
            job = db.get(ScoringJob, jid)
            if job is not None and job.status not in ("done", "error"):
                _fail(db, job, "internal error during scoring")
        except Exception:
            log.exception("could not record scoring failure (job_id=%s)", job_id)
    finally:
        db.close()
