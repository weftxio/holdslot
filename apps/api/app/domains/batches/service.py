"""Phase D shared service — template, masking primitives, and the one decision-write path.

Lives below both routers (console `domains/batches` + public `domains/approvals`) so the
security-critical bits exist exactly once: the masking helpers (`mask_name`/`company_descriptor`)
that the external serializer is built from, and `apply_decision` — the single function that writes
`prospect_approval` decisions (used by both the external client decide and the console step-3 human
fallback). Pure-ish: it mutates ORM rows passed in but never commits — the router owns the txn.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ApprovalTemplate, Batch, ProspectApproval

# The sendout copy default — kept in sync with the web app's editable default (client-status/
# approval). Tokens: `{{prospects}}` (count + grammatical noun, e.g. "1 prospect" / "3 prospects"),
# `{{count}}` (the bare number), and `{{client_name}}` (the client org). A code default serves until
# the founder edits it (then an `approval_template` row wins). The greeting is neutral ("Hi there,")
# rather than the client/tenant name, which otherwise mis-addresses the recipient.
DEFAULT_TEMPLATE: dict[str, str] = {
    "subject": "HoldSlot: your prospect list is ready to approve",
    "body": (
        "Hi there,\n\n"
        "HoldSlot has prepared a new batch of {{prospects}} matched to your brief. "
        "Take a look, then approve the list or remove anyone who isn't a fit."
    ),
    "cta": "Review the list",
}

# Decision values on prospect_approval (string, not a DB enum). `request_changes` is a batch-level
# status, not a per-prospect decision.
PENDING = "pending"
APPROVED = "approved"
REMOVED = "removed"

# batch.status lifecycle.
DRAFT = "draft"
SENT = "sent"
APPROVED_BATCH = "approved"
CHANGES_REQUESTED = "changes_requested"


# --------------------------------------------------------------------------- template


def get_template(db: Session, tenant_id: uuid.UUID) -> dict[str, str]:
    """The tenant's sendout copy — the saved override merged over `DEFAULT_TEMPLATE`, so a missing
    key always falls back to the default rather than rendering blank."""
    row = db.execute(
        select(ApprovalTemplate).where(ApprovalTemplate.tenant_id == tenant_id)
    ).scalar_one_or_none()
    data = row.data if row and row.data else {}
    return {k: data.get(k) or DEFAULT_TEMPLATE[k] for k in DEFAULT_TEMPLATE}


def save_template(db: Session, tenant_id: uuid.UUID, data: dict[str, str]) -> dict[str, str]:
    """Upsert the per-tenant override (one row per tenant). Does not commit."""
    row = db.execute(
        select(ApprovalTemplate).where(ApprovalTemplate.tenant_id == tenant_id)
    ).scalar_one_or_none()
    clean = {k: (data.get(k) or "") for k in DEFAULT_TEMPLATE}
    if row is None:
        row = ApprovalTemplate(tenant_id=tenant_id, data=clean)
        db.add(row)
    else:
        row.data = clean
    return get_template_from(clean)


def get_template_from(data: dict[str, str]) -> dict[str, str]:
    """Merge a raw data dict over the default (same fallback rule as `get_template`)."""
    return {k: data.get(k) or DEFAULT_TEMPLATE[k] for k in DEFAULT_TEMPLATE}


def render_template(tpl: dict[str, str], *, client_name: str, count: int) -> dict[str, str]:
    """Substitute the template tokens into each field. `{{prospects}}` renders the count with a
    grammatical noun ("1 prospect" / "3 prospects"); `{{count}}` is the bare number;
    `{{client_name}}` is the client org."""
    prospects = f"{count} prospect" if count == 1 else f"{count} prospects"

    def sub(s: str) -> str:
        return (
            (s or "")
            .replace("{{prospects}}", prospects)
            .replace("{{client_name}}", client_name)
            .replace("{{count}}", str(count))
        )

    return {"subject": sub(tpl["subject"]), "body": sub(tpl["body"]), "cta": sub(tpl["cta"])}


# --------------------------------------------------------------------------- masking primitives
# The anti-data-theft core: the external serializer is built ONLY from these — first name + last
# initial, and a company *descriptor* (never the exact name/domain). Nothing else about identity or
# contact ever leaves through the public endpoint.


def mask_name(full_name: str | None) -> str:
    """`"Sarah Khan"` → `"Sarah K."`; a lone name token is returned as-is; empty → ``""``.

    Defence-in-depth: a value carrying an "@" is an email, not a name (a manual add or a stray
    Apollo field), so we drop the domain and keep only the local-part tokens — a contact vector
    must never leave through the public endpoint."""
    raw = (full_name or "").strip()
    if "@" in raw:
        raw = raw.split("@", 1)[0].replace(".", " ").replace("_", " ")
    parts = raw.split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


def company_descriptor(
    industry: str | None, size: str | None, country: str | None
) -> str:
    """`"SaaS · 200–500 · US"` — firmographics only, joined by middot; the exact company name and
    domain are deliberately NOT included (that's the masking allow-list)."""
    return " · ".join(p for p in (industry, size, country) if p)


# --------------------------------------------------------------------------- counts (derived)


def count_map(db: Session, batch_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """Per-batch decision tallies derived from `prospect_approval` in one grouped query — counts are
    never stored (deriving avoids dual-write drift). Returns `{batch_id: {total, approved, removed,
    pending}}`; a batch with no rows is absent (callers default to zeros)."""
    if not batch_ids:
        return {}
    rows = db.execute(
        select(
            ProspectApproval.batch_id,
            ProspectApproval.decision,
            func.count().label("n"),
        )
        .where(ProspectApproval.batch_id.in_(batch_ids))
        .group_by(ProspectApproval.batch_id, ProspectApproval.decision)
    ).all()
    out: dict[uuid.UUID, dict[str, int]] = {}
    for batch_id, decision, n in rows:
        d = out.setdefault(batch_id, {"total": 0, "approved": 0, "removed": 0, "pending": 0})
        d["total"] += n
        if decision in d:
            d[decision] += n
    return out


def counts_for(db: Session, batch_id: uuid.UUID) -> dict[str, int]:
    return count_map(db, [batch_id]).get(
        batch_id, {"total": 0, "approved": 0, "removed": 0, "pending": 0}
    )


# ----------------------------------------------------------------------- decision write (shared)


def apply_decision(
    batch: Batch,
    approvals: list[ProspectApproval],
    *,
    approved_ids: list[str] | None = None,
    removed_ids: list[str] | None = None,
    request_changes: bool = False,
    now: datetime | None = None,
) -> dict[str, int]:
    """The ONE place a batch decision is written — shared by the external client decide and the
    console step-3 human fallback. Mutates the rows in place (caller commits); returns a small
    `{approved, removed}` tally.

    Semantics (approve-the-rest):
      * `request_changes` → batch `changes_requested`; per-prospect decisions left untouched.
      * else `approved_ids` given → exactly those approved, every other prospect removed.
      * else → `removed_ids` removed, every other prospect approved (the external UI's model: the
        client toggles a few off, then approves the rest). `removed` always wins over `approved`.
    """
    now = now or datetime.now(UTC)
    if request_changes:
        batch.status = CHANGES_REQUESTED
        batch.decided_at = now
        return {"approved": 0, "removed": 0}

    by_id = {str(a.id): a for a in approvals}
    removed = set(removed_ids or [])
    approved = set(approved_ids) if approved_ids is not None else (set(by_id) - removed)
    n_approved = n_removed = 0
    for aid, a in by_id.items():
        if aid in approved and aid not in removed:
            a.decision = APPROVED
            n_approved += 1
        else:
            a.decision = REMOVED
            n_removed += 1
        a.decided_at = now
    batch.status = APPROVED_BATCH
    batch.decided_at = now
    return {"approved": n_approved, "removed": n_removed}
