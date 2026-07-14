"""Prospect scope & targeting helpers — tenant brief/spec loaders, scope-override rows, exclusions,
and the scoring targeting trim — plus the shared id helpers (`_parse_ids`, `_apollo_run_id`,
`_validate_icp_id`). Dependency-free leaf of the prospects package."""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import uuid_or_404
from app.domains.briefs.research_spec import (
    targeting_for_icp,
)
from app.domains.prospects import (
    tech_vocab,
)
from app.domains.prospects.suppression import extract_exclusions
from app.integrations.apollo import client as apollo
from app.models import (
    Brief,
    Company,
    Icp,
    Prompt,
    ResearchSpec,
    ScopeOverride,
)

log = logging.getLogger("holdslot.prospects")


def _parse_ids(raw: list[str]) -> list[uuid.UUID]:
    """Parse a batch of client-supplied id strings into UUIDs, raising 400 on any malformed value.

    A bare `uuid.UUID(bad)` raises ValueError, which would surface as an unhandled 500; this turns
    it into a clean 400 (W2 consolidation — one parse door for every batch endpoint).
    """
    try:
        return [uuid.UUID(i) for i in raw]
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid id") from exc

def _latest_brief(db: Session, tenant_id) -> Brief | None:
    return db.execute(select(Brief).where(Brief.tenant_id == tenant_id)).scalar_one_or_none()

def _latest_spec(db: Session, tenant_id) -> ResearchSpec | None:
    """The newest ResearchSpec version for a tenant. Version-ordering / tenant-scope lives here."""
    return (
        db.execute(
            select(ResearchSpec)
            .where(ResearchSpec.tenant_id == tenant_id)
            .order_by(ResearchSpec.version.desc())
        )
        .scalars()
        .first()
    )

SCOPE_KIND_PEOPLE = "people"  # ScopeOverride.kind for the Step-2 Find Settings facets

SCOPE_KIND_COMPANY = "company"  # ScopeOverride.kind for the Step-1 Find Settings facets

_SCOPE_GLOBAL = "*"  # by_icp key for an ICP-less (single-ICP / legacy) override

def _scope_override_row(db: Session, tenant_id, kind: str) -> ScopeOverride | None:
    """The tenant's single ScopeOverride row for this pipeline step (`people`/`company`), or None.
    The row holds a per-ICP map (`params.by_icp`); resolve one ICP's block with
    `_scope_override_block`."""
    return db.execute(
        select(ScopeOverride).where(
            ScopeOverride.tenant_id == tenant_id, ScopeOverride.kind == kind
        )
    ).scalar_one_or_none()

def _scope_override_block(row: ScopeOverride | None, icp_id) -> dict | None:
    """The saved manual override block for ONE ICP (`{people_search_params}` for people;
    `{company_search_params, intent_filters}` for company), or None → use the AI scope.

    Reads the per-ICP map (`params.by_icp`, keyed by ICP id string). A row with no `by_icp` map
    (absent or empty) yields None → the caller falls back to the AI scope."""
    if row is None:
        return None
    params = row.params or {}
    by_icp = params.get("by_icp") or {}
    if icp_id is not None:
        hit = by_icp.get(str(icp_id))
        if hit is not None:
            return hit  # per-ICP override wins
    return by_icp.get(_SCOPE_GLOBAL)  # ICP-less global entry as the fallback (or None → AI scope)

def _has_scope_value(v) -> bool:
    """True if a save payload carries any actual facet value (recursing into nested dicts). An
    all-empty block — every leaf array/number empty/None — is a revert, not a stored override that
    would silently widen every search."""
    if isinstance(v, dict):
        return any(_has_scope_value(x) for x in v.values())
    if isinstance(v, (list, tuple, set, str)):
        return len(v) > 0
    return v is not None

def _merge_scope_map(params: dict | None, icp_id, block: dict | None) -> dict | None:
    """Set (or clear, when `block` is None) one ICP's entry in a (tenant, kind) row's per-ICP map.
    Returns the new `params` payload, or None when the map is empty (→ delete the row). A legacy
    FLAT payload (no `by_icp`) is discarded here: the first per-ICP write supersedes it. Other ICPs'
    entries are always preserved."""
    by_icp = dict((params or {}).get("by_icp") or {})
    key = str(icp_id) if icp_id is not None else _SCOPE_GLOBAL
    if block is None:
        by_icp.pop(key, None)
    else:
        by_icp[key] = block
    return {"by_icp": by_icp} if by_icp else None

def _write_scope_override(db: Session, tenant_id, kind: str, icp_id, block: dict | None) -> None:
    """Upsert (or clear) one ICP's entry in the (tenant, kind) override row's per-ICP map. When the
    map empties the row is deleted (→ full AI scope)."""
    row = _scope_override_row(db, tenant_id, kind)
    payload = _merge_scope_map(row.params if row else None, icp_id, block)
    if payload is None:
        if row is not None:
            db.delete(row)
            db.commit()
        return
    if row is None:
        db.add(ScopeOverride(tenant_id=tenant_id, kind=kind, params=payload))
    else:
        row.params = payload
    db.commit()

def _require_scope_kind(kind: str) -> None:
    if kind not in (SCOPE_KIND_PEOPLE, SCOPE_KIND_COMPANY):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown scope kind")

def _build_exclusions(brief: Brief | None, spec: ResearchSpec | None):
    return extract_exclusions(brief.data if brief else {}, spec.spec if spec else None)

def _exclusions(db: Session, tenant_id):
    return _build_exclusions(_latest_brief(db, tenant_id), _latest_spec(db, tenant_id))

def _feedback_rows(db: Session, tenant_id) -> list[dict]:
    """The tenant's labeled companies as the rows `feedback.py` aggregates over (D+ Stage 3/4):
    the v2 `label` (won = contact_now/contact_soon, lost = low_fit/excluded_by_rules) + country +
    descriptive keywords/industry + enrich technology names. Only labeled rows carry signal."""
    rows = db.execute(
        select(
            Company.label, Company.country, Company.industry, Company.evidence,
        ).where(Company.tenant_id == tenant_id, Company.label.is_not(None))
    ).all()
    return [
        {
            "label": label,
            "country": country,
            "industry": industry,
            "keywords": (evidence or {}).get("keywords") or [],
            "technologies": (evidence or {}).get("technology_names") or [],
        }
        for label, country, industry, evidence in rows
    ]

def _resolve_tech(names: list[str]) -> list[str]:
    """Free-text tech names → Apollo tech UIDs via the cached `supported_technologies_csv` vocab
    (D+ Stage 4). Best-effort: an Apollo/transport failure or empty vocab degrades to 'no tech
    filter' (never crashes the find). Returns the ordered, de-duped UID hit list; ambiguous/miss
    names are dropped (never guessed) — see `tech_vocab.resolve`."""
    clean = [n for n in names if n and str(n).strip()]
    if not clean:
        return []
    try:
        vocab = tech_vocab.parse_vocab(apollo.supported_technologies_csv())
    except apollo.ApolloError as e:
        log.warning("tech vocab unavailable — skipping tech filter: %s", e)
        return []
    return tech_vocab.resolve(clean, vocab).uids

def _merge_uids(filter_body: dict, key: str, uids: list[str]) -> dict:
    """Merge `uids` into `filter_body[key]`, de-duped and order-preserving (existing first)."""
    if not uids:
        return filter_body
    existing = filter_body.get(key) or []
    return {**filter_body, key: list(dict.fromkeys([*existing, *uids]))}

def _drop_conflicts(values: list[str], reserved: set[str], *, fold: bool = False) -> list[str]:
    """Drop any `values` entry that also appears in `reserved` — the self-contradiction guard for
    the two server-added filter pairs: never exclude a location the scope includes, never forbid a
    tech UID the ICP requires (either would AND include∩exclude to zero results). `fold` case-folds
    the membership test for location names; tech UIDs come pre-normalized so match exactly."""
    if fold:
        return [v for v in values if str(v).strip().lower() not in reserved]
    return [v for v in values if v not in reserved]

# W7 — only the FIT-relevant brief fields reach the paid scorer (founder-approved keep-list,
# 2026-06-25). The dropped fields (logistics/handoff: attendee emails, attendees, availability,
# channel, contact, approver, meetingsPerMonth · messaging: website, proofPoints, tone, languages ·
# exclusions, already applied by suppression) don't inform whether a prospect FITS — cutting them
# trims tokens on every scoring call AND keeps PII (emails / contact) out of the LLM prompt.
_SCORING_BRIEF_FIELDS = frozenset(
    {
        "companyName",
        "sell",
        "problem",
        "dealSize",
        "salesCycle",
        "valueProps",
        "signals",
        "qualifiedDef",
        # B2B / B2C / Both — drives the v2 market gate (labeling.build_rules_config reads it from
        # the brief). Must reach the scorer's targeting.brief slice for the gate to read it.
        "targetMarket",
    }
)

def _trim_brief_for_scoring(data: dict) -> dict:
    """Keep only the fit-relevant brief fields (W7). Scoping (Brief→ResearchSpec) still gets the
    full brief; this trim is fit-scoring only."""
    return {k: v for k, v in data.items() if k in _SCORING_BRIEF_FIELDS}

def _trim_spec_for_scoring(spec_blob: dict, icp_id=None) -> dict:
    """Drop the spec's `credit_policy` (operational budget caps — not a fit signal) from the scoring
    context (W7); the search-param blocks that define the ICP stay.

    For a v4 multi-ICP spec, keep only the scored row's own ICP block — flattened back to the
    single-block shape the fit rubrics already read, so the rubric prompts never change and the
    scorer isn't fed N-1 irrelevant ICPs' params (smaller prompt, sharper targeting). A v3 spec
    passes through unchanged; an unresolvable ICP (multi-ICP spec, unscoped row) falls back to the
    whole spec so scoring still has the ICP-union context it had before."""
    trimmed = {k: v for k, v in spec_blob.items() if k != "credit_policy"}
    if "icp_targeting" not in trimmed:
        return trimmed
    block = targeting_for_icp(spec_blob, icp_id)
    if block is None:
        return trimmed
    return {
        "spec_version": trimmed.get("spec_version"),
        "company_search_params": block.get("company_search_params") or {},
        "people_search_params": block.get("people_search_params") or {},
        "intent_filters": block.get("intent_filters") or {},
        "icp_validation": trimmed.get("icp_validation") or {},
    }

def _build_targeting(
    brief: Brief | None,
    spec: ResearchSpec | None,
    icps: list[dict] | None = None,
    icp_id=None,
) -> dict:
    """The fit scorer's targeting context. Trimmed to the fit-relevant slice (W7): the keep-listed
    brief fields + the spec minus `credit_policy` + the ICP persona profiles.

    `icps` carries the persona profiles the rubric grades maturity/department/tech/economic-buyer
    against (docs/prompts/fit-scoring-rubric-v1.md §2/§3). Without them those sub-criteria score 0
    by the rubric's Unknown policy, so the ICP docs are not optional context — they unlock points
    that are otherwise structurally unreachable. `icp_id` (the scored row's ICP) narrows a v4
    spec to that ICP's own targeting block — pass it whenever the row carries one.
    """
    return {
        "brief": _trim_brief_for_scoring(brief.data) if brief else {},
        "spec": _trim_spec_for_scoring(spec.spec, icp_id) if spec else {},
        "icps": icps or [],
    }

def _latest_doc(db: Session, tenant_id, stage: str) -> Prompt | None:
    return (
        db.execute(
            select(Prompt)
            .where(Prompt.tenant_id == tenant_id, Prompt.stage == stage)
            .order_by(Prompt.version.desc())
        )
        .scalars()
        .first()
    )

def _apollo_run_id() -> str:
    return f"apollo-{uuid.uuid4().hex[:12]}"

def _validate_icp_id(db: Session, tenant_id, raw: str | None) -> uuid.UUID | None:
    """The ONE ICP door-guard (L8, extends M20/N24). Parse `raw` and confirm it belongs to this
    tenant, or 404 — returning the parsed UUID (None passes through; the ICP is optional). A
    malformed id, a well-formed-but-unknown id, and a cross-tenant id all read the same 404: never a
    raw 500 (add_prospect/find_people used a bare `uuid.UUID`), a worker crash after the job was
    queued (N24), or a silently-stored foreign id. `create_batch` already 404s non-owned ICPs — this
    brings find/add into line."""
    if not raw:
        return None
    icp_id = uuid_or_404(raw, "no such ICP")
    owned = db.execute(
        select(Icp.id).where(Icp.id == icp_id, Icp.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such ICP")
    return icp_id
