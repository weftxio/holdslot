"""Phase G billing logic — pure functions, no DB, no network (the `meetings/service` posture).

Everything money-adjacent lives here so it can be unit-tested with no Aurora and no Stripe (the N1
rule): the GS4 enrichment-cap decision, the GS3 meter-event dedupe identifier, the plan-derived
caps, and the on-read usage-month rollover key. The DB + Stripe wiring is a thin layer in
`router.py`/`webhooks.py` on top of these.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

# Plan defaults (the pricing lock, §7): the monthly Apollo `people/match` (enrichment) allowance +
# the ICP ceiling per plan. `admin_quota_override` on the subscription wins over the plan default.
PLAN_ENRICHMENT_CAP: dict[str, int] = {"free": 10, "launch": 150, "growth": 400}
PLAN_ICP_LIMIT: dict[str, int] = {"free": 1, "launch": 3, "growth": 10}

# The one-time activation fee (GD-9) — a standalone invoice at close, in whole USD.
ACTIVATION_USD = 400


def effective_cap(plan: str, admin_quota_override: int | None) -> int:
    """The enrichment cap actually enforced: the founder override if set, else the plan default."""
    if admin_quota_override is not None:
        return max(0, admin_quota_override)
    return PLAN_ENRICHMENT_CAP.get(plan, 0)


def plan_icp_limit(plan: str) -> int:
    return PLAN_ICP_LIMIT.get(plan, 0)


@dataclass(frozen=True)
class EnrichDecision:
    allowed: int  # how many of `requested` may spend an Apollo credit this call
    overage: int  # of the allowed, how many are past the cap → `enrichment_overage` meter events
    blocked: int  # how many were refused (hard stop — only when overage is disabled)


def enrichment_decision(
    *, cap: int, used: int, requested: int, overage_enabled: bool
) -> EnrichDecision:
    """The GS4 cap rule (pure, [money]). Within the cap, enrich freely. Past the cap:
      * overage ENABLED (default) → still allow every requested row, but the excess bills as
        `enrichment_overage` meter events — **never a silent block** (§6 #7);
      * overage DISABLED → a hard stop: only the within-cap rows are allowed, the excess is blocked.
    """
    requested = max(0, requested)
    within_cap = max(0, cap - max(0, used))
    if overage_enabled:
        overage = max(0, requested - within_cap)
        return EnrichDecision(allowed=requested, overage=overage, blocked=0)
    allowed = min(requested, within_cap)
    return EnrichDecision(allowed=allowed, overage=0, blocked=requested - allowed)


def meeting_identifier(meeting_id) -> str:
    """The meter-event dedupe id (GS3) — `meeting:{id}`. A crash between emit and the `billed_at`
    stamp re-emits the SAME identifier, so Stripe counts the qualified meeting exactly once."""
    return f"meeting:{meeting_id}"


def usage_month_key(now: datetime | None = None) -> str:
    """`YYYY-MM` (UTC) — the usage bucket. When a subscription's stored `usage_month` differs from
    this, the on-read rollover resets `current_month_usage` (no EventBridge, GD-2)."""
    now = now or datetime.now(UTC)
    return now.astimezone(UTC).strftime("%Y-%m")
