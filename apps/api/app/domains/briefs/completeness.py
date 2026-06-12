"""Brief completeness rubric — the single server-side source of truth for the ring.

The rubric is **data, not code** (B0 gate #2): a list of required Brief field keys lifted
from the Workspace UI's Required/Optional tags. Editing this list re-scores every brief
with no code change — the churn-proof guarantee. The brief `data` document is opaque JSONB;
the scorer only asks "is this key filled?", never what the key means.

A field counts as filled when it carries real content: a non-blank string, or a list with
at least one non-blank entry. The 6 Brief fields the UI marks Optional (objections,
competitors, languageOther, doNotContact, compliance, first90) are deliberately absent.
"""

from __future__ import annotations

# Required Brief keys (mirror the UI `Brief` type + its `<Lbl req>` markers). Order is
# the form order so `missing[]` reads top-to-bottom for the operator.
REQUIRED_BRIEF_FIELDS: tuple[str, ...] = (
    # §1 Company & product
    "companyName",
    "website",
    "sell",
    "problem",
    "dealSize",
    "salesCycle",
    # §3 Message inputs
    "valueProps",
    "proofPoints",
    "signals",
    "tone",
    "languages",
    # §4 Exclusions
    "excludeCustomers",
    "excludeDeals",
    # §5 Logistics & handoff
    "meetingsLand",
    "attendees",
    "availability",
    "channel",
    "contact",
    "approver",
    # §6 Meetings & qualification
    "meetingsPerMonth",
    "qualifiedDef",
)


def _is_filled(value: object) -> bool:
    """True when a brief value carries real content (non-blank string / non-empty list)."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(_is_filled(v) for v in value)
    if isinstance(value, dict):
        return any(_is_filled(v) for v in value.values())
    return bool(value)


def missing_fields(data: dict) -> list[str]:
    """Required keys that are absent or blank, in form order."""
    return [k for k in REQUIRED_BRIEF_FIELDS if not _is_filled(data.get(k))]


def completeness(data: dict) -> int:
    """Percent of required fields filled, 0–100 (100 when no fields are required)."""
    total = len(REQUIRED_BRIEF_FIELDS)
    if total == 0:
        return 100
    filled = total - len(missing_fields(data))
    return round(100 * filled / total)
