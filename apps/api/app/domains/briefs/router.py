"""Brief routes — GET/PUT the one business brief per client, with completeness scoring.

A thin "JSON document resource": store the opaque form document, return it with the
server-computed completeness (the ring's single source of truth, from `completeness.py`).
Tenant scope × role is enforced by the A4 central guard (`require_membership`), so a caller
can only ever reach their own client's brief.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import AccessContext, get_db, require_membership
from app.domains.briefs.completeness import completeness, missing_fields
from app.domains.briefs.research_spec import (
    DEFAULT_SYSTEM_PROMPT,
    PROMPT_VERSION,
    PURPOSE,
    RESEARCH_SPEC_JSON_SCHEMA,
    ResearchSpecV1,
    assemble_spec,
    build_messages,
)
from app.domains.briefs.schemas import (
    BriefIn,
    BriefOut,
    ResearchSpecList,
    ResearchSpecOut,
    ScopingPromptOut,
    SystemPromptIn,
    SystemPromptOut,
)
from app.integrations.openrouter.client import (
    LlmError,
    configured_models,
    structured_completion,
)
from app.models import Brief, Icp, ResearchSpec, SourcingDoc

# Operators can override the scoping system prompt per client; it is stored as a versioned
# SourcingDoc of this kind (the user/input prompt is never editable — it is the client brief).
SYSTEM_PROMPT_KIND = "brief_system_prompt"


def _latest_system_prompt(db: Session, tenant_id) -> SourcingDoc | None:
    return db.execute(
        select(SourcingDoc)
        .where(SourcingDoc.tenant_id == tenant_id, SourcingDoc.kind == SYSTEM_PROMPT_KIND)
        .order_by(SourcingDoc.version.desc())
        .limit(1)
    ).scalar_one_or_none()


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
    icps = db.execute(
        select(Icp).where(Icp.tenant_id == ctx.tenant.id).order_by(Icp.created_at)
    ).scalars()
    icp_docs = [{**i.data, "id": str(i.id), "name": i.name, "tag": i.tag} for i in icps]
    saved = _latest_system_prompt(db, ctx.tenant.id)
    messages = build_messages(
        brief.data if brief else {}, icp_docs, system_override=saved.body if saved else None
    )
    by_role = {m["role"]: m["content"] for m in messages}
    return ScopingPromptOut(
        system=by_role.get("system", ""),
        user=by_role.get("user", ""),
        system_is_custom=saved is not None,
        model=configured_models(),
        purpose=PURPOSE,
        prompt_version=PROMPT_VERSION,
    )


@router.put("/{client}/brief/structure/system-prompt", response_model=SystemPromptOut)
def save_system_prompt(
    body: SystemPromptIn,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> SystemPromptOut:
    """Save an operator-edited scoping system prompt for this client (a new versioned doc).

    Saving the default text verbatim is treated as 'reset': any custom override is cleared so the
    code default stays the single source of truth (no stale copy drifting from the code)."""
    text_in = body.system.strip()
    if not text_in or text_in == DEFAULT_SYSTEM_PROMPT.strip():
        # Reset to default — drop all custom versions so structuring uses the code default.
        for d in db.execute(
            select(SourcingDoc).where(
                SourcingDoc.tenant_id == ctx.tenant.id, SourcingDoc.kind == SYSTEM_PROMPT_KIND
            )
        ).scalars():
            db.delete(d)
        db.commit()
        return SystemPromptOut(system=DEFAULT_SYSTEM_PROMPT, version=0, is_custom=False)

    prev = _latest_system_prompt(db, ctx.tenant.id)
    next_version = (prev.version + 1) if prev else 1
    doc = SourcingDoc(
        tenant_id=ctx.tenant.id, kind=SYSTEM_PROMPT_KIND, version=next_version, body=body.system
    )
    db.add(doc)
    db.commit()
    return SystemPromptOut(system=body.system, version=next_version, is_custom=True)


@router.post("/{client}/brief/structure", response_model=ResearchSpecOut)
def structure_brief(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> ResearchSpecOut:
    """Brief (+ICPs) → a new versioned ResearchSpec via the LLM. The bridge into Clay (B4)."""
    brief = db.execute(select(Brief).where(Brief.tenant_id == ctx.tenant.id)).scalar_one_or_none()
    if brief is None or completeness(brief.data) == 0:
        # Don't spend a (billed) LLM call structuring an empty brief.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "fill in the brief before structuring")

    icps = db.execute(
        select(Icp).where(Icp.tenant_id == ctx.tenant.id).order_by(Icp.created_at)
    ).scalars()
    # Canonical id/name/tag must win over any same-named keys in the opaque ICP document.
    icp_docs = [{**i.data, "id": str(i.id), "name": i.name, "tag": i.tag} for i in icps]

    # Use the operator's saved system prompt if present, else the code default.
    saved = _latest_system_prompt(db, ctx.tenant.id)
    messages = build_messages(brief.data, icp_docs, system_override=saved.body if saved else None)
    try:
        result = structured_completion(
            tenant_id=ctx.tenant.id,
            purpose=PURPOSE,
            messages=messages,
            schema=RESEARCH_SPEC_JSON_SCHEMA,
            prompt_version=PROMPT_VERSION,
        )
    except LlmError as e:
        # Telemetry is already persisted (e.llm_call_id); surface the specific cause.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    # Defensive server-side validation — never persist an off-contract spec.
    try:
        ResearchSpecV1(**result.data)
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "LLM returned an off-contract spec") from e

    spec, gaps, icp_suggestions = assemble_spec(result.data)
    # Insert the next version, retrying on the unique (tenant, version) race so a concurrent
    # structuring never discards this already-completed (and billed) LLM result with a 500.
    for _ in range(5):
        next_version = (
            db.execute(
                select(func.coalesce(func.max(ResearchSpec.version), 0)).where(
                    ResearchSpec.tenant_id == ctx.tenant.id
                )
            ).scalar_one()
            + 1
        )
        row = ResearchSpec(
            tenant_id=ctx.tenant.id,
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
        db.refresh(row)
        return _spec_out(row)
    raise HTTPException(status.HTTP_409_CONFLICT, "could not allocate a spec version")


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
