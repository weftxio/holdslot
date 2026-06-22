"""Brief routes — GET/PUT the one business brief per client, with completeness scoring.

A thin "JSON document resource": store the opaque form document, return it with the
server-computed completeness (the ring's single source of truth, from `completeness.py`).
Tenant scope × role is enforced by the A4 central guard (`require_membership`), so a caller
can only ever reach their own client's brief.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AccessContext, get_db, require_membership
from app.domains.briefs.completeness import completeness, missing_fields
from app.domains.briefs.research_spec import (
    DEFAULT_SYSTEM_PROMPT,
    PROMPT_VERSION,
    PURPOSE,
    SCOPING_MODELS,
    build_messages,
)
from app.domains.briefs.schemas import (
    BriefIn,
    BriefOut,
    ResearchJobOut,
    ResearchSpecList,
    ResearchSpecOut,
    ScopingPromptOut,
    SystemPromptIn,
    SystemPromptOut,
)
from app.domains.briefs.structuring import (
    STAGE_BRIEFING,
    enqueue_structuring,
    latest_job,
    latest_system_prompt,
)
from app.domains.icps import icp_docs
from app.models import Brief, Prompt, ResearchJob, ResearchSpec

router = APIRouter(tags=["briefs"])


def _out(brief: Brief | None) -> BriefOut:
    data = brief.data if brief is not None else {}
    return BriefOut(
        data=data,
        completeness=completeness(data),
        missing=missing_fields(data),
        updated_at=brief.updated_at.isoformat() if brief is not None else None,
    )


@router.get("/{client}/brief", response_model=BriefOut)
def get_brief(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> BriefOut:
    brief = db.execute(select(Brief).where(Brief.tenant_id == ctx.tenant.id)).scalar_one_or_none()
    return _out(brief)


@router.put("/{client}/brief", response_model=BriefOut)
def put_brief(
    body: BriefIn,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> BriefOut:
    # Upsert — one brief per client (the unique constraint guarantees a single row).
    brief = db.execute(select(Brief).where(Brief.tenant_id == ctx.tenant.id)).scalar_one_or_none()
    if brief is None:
        brief = Brief(tenant_id=ctx.tenant.id, data=body.data)
        db.add(brief)
    else:
        brief.data = body.data
    db.commit()
    db.refresh(brief)
    return _out(brief)


def _spec_out(row: ResearchSpec) -> ResearchSpecOut:
    return ResearchSpecOut(
        version=row.version,
        spec=row.spec,
        gaps=row.gaps,
        icp_suggestions=row.icp_suggestions,
        model=row.model,
        llm_call_id=str(row.llm_call_id) if row.llm_call_id else None,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.get("/{client}/brief/structure/preview", response_model=ScopingPromptOut)
def preview_structure_prompt(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> ScopingPromptOut:
    """The exact system + input prompt `POST /brief/structure` would send — no LLM call, no spend.

    Built from the same `build_messages(brief, icps)` the live call uses, so the prompt-preview
    popup always mirrors what actually reaches the model.
    """
    brief = db.execute(select(Brief).where(Brief.tenant_id == ctx.tenant.id)).scalar_one_or_none()
    saved = latest_system_prompt(db, ctx.tenant.id)
    messages = build_messages(
        brief.data if brief else {},
        icp_docs(db, ctx.tenant.id),
        system_override=saved.body if saved else None,
    )
    by_role = {m["role"]: m["content"] for m in messages}
    # "Custom" = the stored prompt diverges from the seeded code default (the seed itself reads as
    # the default, not a custom edit), so the badge stays honest now that a v1 is always seeded.
    is_custom = saved is not None and saved.body.strip() != DEFAULT_SYSTEM_PROMPT.strip()
    return ScopingPromptOut(
        system=by_role.get("system", ""),
        user=by_role.get("user", ""),
        system_is_custom=is_custom,
        # The scoping call pins SCOPING_MODELS (DeepSeek V4 Pro) regardless of the secret's generic
        # `models` list, so the preview badge reports THAT — not configured_models(), which still
        # shows the stale flash→llama default the structuring run never uses.
        model=list(SCOPING_MODELS),
        purpose=PURPOSE,
        prompt_version=PROMPT_VERSION,
    )


@router.put("/{client}/brief/structure/system-prompt", response_model=SystemPromptOut)
def save_system_prompt(
    body: SystemPromptIn,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> SystemPromptOut:
    """Save the scoping system prompt for this client as the next `briefing` version (append-only).

    The `prompt` table is the source of truth and never overwritten — every save (including 'reset
    to default') appends a new version; the latest is active. An empty body resets to the code
    default. `is_custom` reflects whether the saved text diverges from that default."""
    text_in = body.system.strip()
    effective = DEFAULT_SYSTEM_PROMPT if not text_in else body.system
    prev = latest_system_prompt(db, ctx.tenant.id)
    next_version = (prev.version + 1) if prev else 1
    doc = Prompt(
        tenant_id=ctx.tenant.id, stage=STAGE_BRIEFING, version=next_version, body=effective
    )
    db.add(doc)
    db.commit()
    is_custom = effective.strip() != DEFAULT_SYSTEM_PROMPT.strip()
    return SystemPromptOut(system=effective, version=next_version, is_custom=is_custom)


def _job_out(job: ResearchJob | None) -> ResearchJobOut:
    if job is None:
        return ResearchJobOut(status="idle")
    return ResearchJobOut(
        job_id=str(job.id),
        status=job.status,
        spec_version=job.spec_version,
        error=job.error,
    )


@router.post(
    "/{client}/brief/structure",
    response_model=ResearchJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def structure_brief(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> ResearchJobOut:
    """Kick off Brief (+ICPs) → ResearchSpec **asynchronously**; returns a job to poll (202).

    Scoping runs DeepSeek V4 Pro with thinking + web search (~55-76s) — too slow for the 30s API
    Gateway sync cap — so the LLM call runs on a background worker and the client polls
    `GET /brief/structure/status` until `done`/`error`. A still-running job is returned as-is, so
    a double-click never double-spends. (B6, async — see domains/briefs/structuring.py.)
    """
    brief = db.execute(select(Brief).where(Brief.tenant_id == ctx.tenant.id)).scalar_one_or_none()
    if brief is None or completeness(brief.data) == 0:
        # Don't enqueue a (billed) LLM call for an empty brief.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "fill in the brief before structuring")
    return _job_out(enqueue_structuring(db, ctx.tenant.id))


@router.get("/{client}/brief/structure/status", response_model=ResearchJobOut)
def structure_status(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> ResearchJobOut:
    """The latest structuring job's status — polled until terminal. `idle` when none has run."""
    return _job_out(latest_job(db, ctx.tenant.id))


@router.get("/{client}/research-spec", response_model=ResearchSpecList)
def get_research_spec(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> ResearchSpecList:
    """Latest ResearchSpec + version history for the Workspace review panel."""
    rows = (
        db.execute(
            select(ResearchSpec)
            .where(ResearchSpec.tenant_id == ctx.tenant.id)
            .order_by(ResearchSpec.version.desc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return ResearchSpecList(latest=None, versions=[])
    return ResearchSpecList(latest=_spec_out(rows[0]), versions=[r.version for r in rows])
