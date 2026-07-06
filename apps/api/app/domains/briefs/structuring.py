"""Async Brief→ResearchSpec structuring (B6).

Scoping runs on DeepSeek V4 Pro with thinking + the web-search plugin (~55-76s) — past the API
Gateway HTTP-API hard 30s cap. So the work is moved off the request path:

  * `enqueue_structuring(...)` inserts a `research_job` (queued) and dispatches a background worker,
    returning immediately so `POST /brief/structure` answers in well under 30s.
  * Dispatch is **environment-aware**: on Lambda it self async-invokes (`InvocationType=Event`) with
    a `{"holdslot_job": ...}` event the entry handler (`app.main`) routes to `run_structuring_job`;
    locally (uvicorn) it runs the worker on a daemon thread. Either way the worker has the full
    Lambda timeout / no cap.
  * `run_structuring_job(...)` runs the LLM, inserts the next `ResearchSpec` version, and flips the
    job to `done` (recording `spec_version`) or `error`. The frontend polls the job until terminal.

A single in-flight job per tenant is enforced (a queued/running job is returned as-is) so a
double-click never double-spends a (billed) LLM call.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.briefs.completeness import completeness
from app.domains.briefs.research_spec import (
    PROMPT_VERSION,
    PURPOSE,
    RESEARCH_SPEC_JSON_SCHEMA,
    SCOPING_EXTRA_BODY,
    SCOPING_MODELS,
    SCOPING_TIMEOUT,
    ResearchSpecV4,
    assemble_spec,
    build_messages,
    reconcile_icp_targeting,
)
from app.domains.icps import icp_docs
from app.integrations.openrouter.client import LlmError, structured_completion
from app.models import Brief, Prompt, ResearchJob, ResearchSpec

log = logging.getLogger("holdslot.structuring")

# The per-client scoping system prompt lives in the `prompt` table at this stage (seeded by
# migration 0010, editable in the UI). `latest_system_prompt` reads it; absent → code default.
STAGE_BRIEFING = "briefing"

# Background-job event contract (the entry handler routes on JOB_EVENT_KEY; see app.main).
JOB_EVENT_KEY = "holdslot_job"
JOB_BRIEF_STRUCTURE = "brief_structure"

_ACTIVE = ("queued", "running")
_ERR_MAX = 500  # cap the stored error message

# A worker runs inside a SINGLE Lambda invocation, so it cannot outlive the function timeout. A hard
# timeout (or a killed local thread) ends it mid-run WITHOUT raising, so run_structuring_job's
# except/finally never fires and the job is left `running` forever (a zombie): every page load
# resumes the "Generating…" poll, AND enqueue_structuring coalesces each Regenerate click onto it —
# the surface is wedged. So on each read we reap any non-terminal job older than a worker could
# possibly live → `error` (mirrors prospects/scoring.py). Keep this comfortably ABOVE the Lambda
# timeout (infra/terraform/lambda.tf, currently 300s).
MAX_JOB_AGE_SECONDS = 360


def _job_age_seconds(job: ResearchJob) -> float:
    created = job.created_at
    if created.tzinfo is None:  # aurora-data-api can hand back a naive UTC datetime
        created = created.replace(tzinfo=UTC)
    return (datetime.now(UTC) - created).total_seconds()


def _reap_if_stale(db: Session, job: ResearchJob) -> bool:
    """Flip a non-terminal job that outlived any possible worker run to `error`. Idempotent; returns
    True when it reaped (so callers stop treating the job as active/in-flight)."""
    if job.status not in _ACTIVE or _job_age_seconds(job) <= MAX_JOB_AGE_SECONDS:
        return False
    _fail(db, job, "scope generation timed out — click Generate Scope to retry")
    log.warning("reaped stale structuring job id=%s", job.id)
    return True


def latest_system_prompt(db: Session, tenant_id) -> Prompt | None:
    """The newest stored scoping system prompt for the tenant (None → use the code default)."""
    return db.execute(
        select(Prompt)
        .where(Prompt.tenant_id == tenant_id, Prompt.stage == STAGE_BRIEFING)
        .order_by(Prompt.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def latest_job(db: Session, tenant_id) -> ResearchJob | None:
    """The most recent structuring job for the tenant (what the status poll reads). A zombie
    `running` job is reaped here, so a page refresh never resumes a dead run's spinner."""
    job = db.execute(
        select(ResearchJob)
        .where(ResearchJob.tenant_id == tenant_id)
        .order_by(ResearchJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if job is not None:
        _reap_if_stale(db, job)
    return job


def enqueue_structuring(db: Session, tenant_id) -> ResearchJob:
    """Create a queued job + dispatch the worker. A still-active job is returned unchanged."""
    active = db.execute(
        select(ResearchJob)
        .where(ResearchJob.tenant_id == tenant_id, ResearchJob.status.in_(_ACTIVE))
        .order_by(ResearchJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    # Coalesce onto a genuinely in-flight job (a double-click never double-spends); but a stale
    # zombie must NOT wedge Regenerate forever — reap it and fall through to a fresh job.
    if active is not None and not _reap_if_stale(db, active):
        return active

    job = ResearchJob(tenant_id=tenant_id, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    _dispatch(tenant_id, job.id)
    return job


def _dispatch(tenant_id, job_id) -> None:
    """Run the worker off the request path: Lambda self async-invoke, else a local daemon thread."""
    payload = {
        JOB_EVENT_KEY: JOB_BRIEF_STRUCTURE,
        "tenant_id": str(tenant_id),
        "job_id": str(job_id),
    }
    fn = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if fn:
        # Async self-invoke — the same deployment artifact, dispatched off the gateway so it runs
        # up to the Lambda timeout (not the 30s API Gateway cap). The entry handler routes it.
        import boto3

        boto3.client("lambda").invoke(
            FunctionName=fn, InvocationType="Event", Payload=json.dumps(payload).encode()
        )
    else:
        threading.Thread(
            target=run_structuring_job,
            args=(payload["tenant_id"], payload["job_id"]),
            daemon=True,
        ).start()


def handle_job_event(event: dict) -> dict:
    """Entry-handler hook for a background-job Lambda event (see app.main.handler)."""
    kind = event.get(JOB_EVENT_KEY)
    if kind == JOB_BRIEF_STRUCTURE:
        run_structuring_job(event["tenant_id"], event["job_id"])
    else:
        log.warning("unknown background job event: %s", kind)
    return {"ok": True}


def _fail(db: Session, job: ResearchJob, message: str) -> None:
    job.status = "error"
    job.error = message[:_ERR_MAX]
    db.commit()


def _insert_spec(db: Session, tenant_id, spec, gaps, icp_suggestions, result) -> int | None:
    """Insert the next ResearchSpec version, retrying the unique (tenant, version) race. Returns
    the version written, or None if it could not allocate one."""
    for _ in range(5):
        next_version = (
            db.execute(
                select(func.coalesce(func.max(ResearchSpec.version), 0)).where(
                    ResearchSpec.tenant_id == tenant_id
                )
            ).scalar_one()
            + 1
        )
        row = ResearchSpec(
            tenant_id=tenant_id,
            version=next_version,
            spec=spec,
            gaps=gaps,
            icp_suggestions=icp_suggestions,
            model=result.model,
            llm_call_id=result.llm_call_id,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        return next_version
    return None


def run_structuring_job(tenant_id, job_id, session_factory=None) -> None:
    """The worker: Brief (+ICPs) → LLM → next ResearchSpec version, flipping the job terminal.

    Owns its own Session (it runs on a thread or a fresh Lambda invocation, never inside a request).
    Every failure path records `status=error` with a short cause; the (billed) telemetry row is
    still written by `structured_completion` regardless.
    """
    tid = uuid.UUID(str(tenant_id))
    jid = uuid.UUID(str(job_id))
    if session_factory is None:
        from app.core.db import get_session

        session_factory = get_session
    db = session_factory()
    try:
        job = db.get(ResearchJob, jid)
        if job is None:
            log.warning("structuring job vanished (job_id=%s)", job_id)
            return
        job.status = "running"
        db.commit()

        brief = db.execute(select(Brief).where(Brief.tenant_id == tid)).scalar_one_or_none()
        if brief is None or completeness(brief.data) == 0:
            _fail(db, job, "fill in the brief before structuring")
            return

        saved = latest_system_prompt(db, tid)
        docs = icp_docs(db, tid)
        messages = build_messages(brief.data, docs, system_override=saved.body if saved else None)

        try:
            result = structured_completion(
                tenant_id=tid,
                purpose=PURPOSE,
                messages=messages,
                schema=RESEARCH_SPEC_JSON_SCHEMA,
                prompt_version=PROMPT_VERSION,
                models=SCOPING_MODELS,
                extra_body=SCOPING_EXTRA_BODY,
                timeout=SCOPING_TIMEOUT,
                session_factory=session_factory,
            )
        except LlmError as e:
            _fail(db, job, f"LLM call failed: {e}")
            return

        try:
            ResearchSpecV4(**result.data)
        except Exception:
            _fail(db, job, "LLM returned an off-contract spec")
            return

        # Multi-ICP coverage check: one block per input ICP, ids echoed (typos repaired by name).
        # A missing ICP is a NAMED failure, never a silently merged/dropped profile (the v3 bug).
        blocks, cover_err = reconcile_icp_targeting(
            result.data["icp_targeting"], {d["id"]: d["name"] for d in docs}
        )
        if cover_err:
            _fail(db, job, cover_err)
            return
        result.data["icp_targeting"] = blocks

        spec, gaps, icp_suggestions = assemble_spec(result.data)
        version = _insert_spec(db, tid, spec, gaps, icp_suggestions, result)
        if version is None:
            _fail(db, job, "could not allocate a spec version")
            return

        job.status = "done"
        job.spec_version = version
        job.llm_call_id = result.llm_call_id
        db.commit()
    except Exception:
        log.exception("structuring job failed (job_id=%s)", job_id)
        try:
            db.rollback()
            job = db.get(ResearchJob, jid)
            if job is not None and job.status not in ("done", "error"):
                _fail(db, job, "internal error during structuring")
        except Exception:
            log.exception("could not record structuring failure (job_id=%s)", job_id)
    finally:
        db.close()
