"""Billing console routes + the on-read billing sweep (GS3/GS4/GS6). Ships DORMANT.

The money layer added at Phase G. Everything here is a no-op until a tenant has a `subscription` row
(FR-7/FR-8) — tenant #0 has none, so `bill_due_meetings` / `reserve_enrichment` return immediately
and the FE status read returns `subscription: null`. The one money RULE (the enrichment cap decision
+ the meter dedupe identifier) lives in `service.py`, tested off fixtures with no Aurora/Stripe.

  * **GS3 — on-read billing sweep** (`bill_due_meetings`): rides F4's `sweep_meetings`. For each
    `is_billable AND billed_at IS NULL` meeting of a tenant with an ACTIVE Stripe subscription →
    emit one `qualified_meeting` meter event (`identifier = meeting:{id}`) → claim
    `UPDATE meeting SET billed_at WHERE billed_at IS NULL`. Event-then-stamp is safe (the identifier
    dedupes a crash-retry). `short_call`/`noshow`/`disputed`/no-subscription rows never emit.
  * **GS4 — enrich-cap guard** (`reserve_enrichment`): called before the paid Apollo match dispatch.
    No subscription → unbounded (today's behavior). Past the cap → `enrichment_overage` meter
    events, never a silent block; a hard stop only when `overage_enabled = false`.
  * **GS4/GS6 — owner doors + the ledger read.**
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from app.core.deps import AccessContext, get_db, require_membership
from app.domains.billing import service as bsvc
from app.domains.billing.schemas import BillingStatusOut, SubscriptionIn, SubscriptionOut
from app.integrations.stripe import client as stripe
from app.models import Meeting, MembershipRole, Subscription

router = APIRouter(tags=["billing"])
log = logging.getLogger("holdslot.billing")


def get_subscription(db: Session, tenant_id) -> Subscription | None:
    return db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    ).scalar_one_or_none()


def _rollover(sub: Subscription, now: datetime) -> None:
    """On-read usage-month rollover (GD-2 — no EventBridge): a new UTC month resets the counter."""
    key = bsvc.usage_month_key(now)
    if sub.usage_month != key:
        sub.usage_month = key
        sub.current_month_usage = 0


# ============================================================ GS3 — the on-read billing sweep


def bill_due_meetings(db: Session, tenant_id) -> int:
    """Emit the Stripe meter event for every newly-billable, not-yet-billed meeting. Dormant (0)
    unless the tenant has an ACTIVE subscription with a Stripe customer. Best-effort per row — a
    Stripe hiccup on one meeting is logged/skipped, never fails the read that called the sweep."""
    sub = get_subscription(db, tenant_id)
    if sub is None or sub.status != "active" or not sub.stripe_customer_id:
        return 0
    now = datetime.now(UTC)
    due = (
        db.execute(
            select(Meeting).where(
                Meeting.tenant_id == tenant_id,
                Meeting.outcome == "qualified",
                Meeting.amount.is_not(None),
                Meeting.disputed.is_(False),
                Meeting.dispute_window_ends_at < now,
                Meeting.billed_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    billed = 0
    for meeting in due:
        try:
            stripe.meter_event(
                event_name=stripe.meter_name("qualified_meeting"),
                stripe_customer_id=sub.stripe_customer_id,
                value=1,
                identifier=bsvc.meeting_identifier(meeting.id),
            )
        except stripe.StripeError:
            log.warning("billing sweep: meter emit failed meeting=%s — skipped", meeting.id)
            continue
        res = db.execute(
            update(Meeting)
            .where(Meeting.id == meeting.id, Meeting.billed_at.is_(None))
            .values(billed_at=now)
        )
        if res.rowcount:
            billed += 1
    if billed:
        db.commit()
    return billed


# ============================================================ GS4 — the enrich-cap guard


def reserve_enrichment(db: Session, tenant_id, requested: int) -> int:
    """Reserve `requested` Apollo `people/match` credits against the tenant's plan cap. Returns how
    many rows MAY spend a credit (== requested unless overage is disabled and the cap is hit). No
    subscription → returns `requested` (dogfood tenant #0 + any pre-billing tenant is unbounded, as
    before Stripe). Increments the month usage; meters the over-cap portion (best-effort)."""
    if requested <= 0:
        return 0
    sub = get_subscription(db, tenant_id)
    if sub is None:
        return requested
    now = datetime.now(UTC)
    key = bsvc.usage_month_key(now)
    # On-read usage-month rollover (GD-2) folded into the read: a new UTC month counts from 0.
    base = sub.current_month_usage if sub.usage_month == key else 0
    cap = bsvc.effective_cap(sub.plan, sub.admin_quota_override)
    decision = bsvc.enrichment_decision(
        cap=cap,
        used=base,
        requested=requested,
        overage_enabled=sub.overage_enabled,
    )
    # M13 — reserve atomically in ONE statement (`usage := this-month usage + allowed`) so two
    # concurrent enrich runs can't lose an increment via read-modify-write; the rollover is folded
    # into the same CASE so a month flip can't race it. We do NOT commit here — the caller owns the
    # txn (a mid-flow commit used to flush the caller's half-done enrich session).
    db.execute(
        update(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .values(
            current_month_usage=(
                case((Subscription.usage_month == key, Subscription.current_month_usage), else_=0)
                + decision.allowed
            ),
            usage_month=key,
        )
    )
    db.refresh(sub)  # sync the ORM object with the atomic write (no stale flush on caller commit)
    # Overage bills as meter events with a deterministic per-unit identifier (dedupes a retry). The
    # DB `current_month_usage` counter is authoritative; a Stripe blip here DROPS that overage unit
    # (best-effort — the counter is already incremented, so a re-run won't re-emit it). If overage
    # revenue ever matters at volume, GSA reconciles emitted meter events vs `current_month_usage`.
    for i in range(decision.overage):
        unit = base + decision.allowed - decision.overage + i + 1
        try:
            stripe.meter_event(
                event_name=stripe.meter_name("enrichment_overage"),
                stripe_customer_id=sub.stripe_customer_id or "",
                value=1,
                identifier=f"enrich-overage:{tenant_id}:{sub.usage_month}:{unit}",
            )
        except stripe.StripeError:
            log.warning("enrich overage meter failed tenant=%s unit=%s — deferred", tenant_id, unit)
    return decision.allowed


# ============================================================ GS4/GS6 — owner doors + the read


def _sub_out(sub: Subscription) -> SubscriptionOut:
    return SubscriptionOut(
        plan=sub.plan,
        status=sub.status,
        stripe_customer_id=sub.stripe_customer_id,
        stripe_subscription_id=sub.stripe_subscription_id,
        activation_paid_at=sub.activation_paid_at.isoformat() if sub.activation_paid_at else None,
        enrichment_cap=bsvc.effective_cap(sub.plan, sub.admin_quota_override),
        icp_limit=sub.icp_limit,
        current_month_usage=sub.current_month_usage,
        usage_month=sub.usage_month,
        overage_enabled=sub.overage_enabled,
    )


@router.get("/{client}/billing/status", response_model=BillingStatusOut)
def billing_status(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> BillingStatusOut:
    """The GS6 ledger line — the tenant's subscription/plan/status, or `null` when it has none
    (every tenant today). The FE renders the line only when this is non-null (dormant-safe)."""
    sub = get_subscription(db, ctx.tenant.id)
    if sub is not None:
        # M12 — reflect the current UTC month even before the first enrich of the month lands (GD-2
        # has no scheduler). Read-only: the GET session is never committed (get_db closes it)
        # so this only fixes the displayed counter, it doesn't persist a write.
        _rollover(sub, datetime.now(UTC))
    return BillingStatusOut(subscription=_sub_out(sub) if sub else None)


@router.post("/{client}/billing/subscription", response_model=SubscriptionOut)
def create_subscription(
    body: SubscriptionIn,
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> SubscriptionOut:
    """GS4 — create the Stripe customer + subscription at close and upsert the `subscription` row.
    The subscription carries the flat plan price + the metered `qualified_meeting` price. Idempotent
    per tenant (the Idempotency-Key is keyed off the tenant id)."""
    plan = body.plan
    if plan not in bsvc.PLAN_ENRICHMENT_CAP:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown plan")
    sub = get_subscription(db, ctx.tenant.id)
    # M14 — a re-POST with a DIFFERENT plan would update the local caps but never touch the Stripe
    # subscription's prices, silently diverging what we enforce from what Stripe bills. Refuse it
    # until an explicit price-swap path exists (dormant — no tenant has a subscription yet).
    if sub is not None and sub.stripe_subscription_id and plan != sub.plan:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "plan changes on an active subscription aren't supported yet"
        )
    if sub is None:
        sub = Subscription(tenant_id=ctx.tenant.id, plan=plan)
        db.add(sub)
    sub.plan = plan
    sub.enrichment_cap = bsvc.PLAN_ENRICHMENT_CAP[plan]
    sub.icp_limit = bsvc.plan_icp_limit(plan)
    if not sub.stripe_customer_id:
        cust = stripe.create_customer(
            email=ctx.user.email,
            name=ctx.tenant.name,
            metadata={"tenant_id": str(ctx.tenant.id), "slug": ctx.tenant.slug},
            idempotency_key=f"cust:{ctx.tenant.id}",
        )
        sub.stripe_customer_id = cust.get("id")
    if not sub.stripe_subscription_id and plan != "free":
        prices = [p for p in (stripe.price_id(plan), stripe.price_id("qualified_meeting")) if p]
        created = stripe.create_subscription(
            customer=sub.stripe_customer_id,
            prices=prices,
            metadata={"tenant_id": str(ctx.tenant.id)},
            idempotency_key=f"sub:{ctx.tenant.id}:{plan}",
        )
        sub.stripe_subscription_id = created.get("id")
        sub.status = created.get("status", "active")
    db.commit()
    return _sub_out(sub)


@router.post("/{client}/billing/activation-invoice", response_model=SubscriptionOut)
def create_activation_invoice(
    ctx: AccessContext = Depends(require_membership(MembershipRole.owner)),
    db: Session = Depends(get_db),
) -> SubscriptionOut:
    """GS4/GD-9 — raise the standalone $400 activation invoice (collect before provisioning). The
    paid stamp (`activation_paid_at`) is set by the `invoice.paid` webhook, not here."""
    sub = get_subscription(db, ctx.tenant.id)
    if sub is None or not sub.stripe_customer_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "no Stripe customer — create the subscription first"
        )
    stripe.create_invoice_item(
        customer=sub.stripe_customer_id,
        amount_cents=bsvc.ACTIVATION_USD * 100,
        description=f"HoldSlot activation — {ctx.tenant.name}",
        idempotency_key=f"activation-item:{ctx.tenant.id}",
    )
    stripe.create_invoice(
        customer=sub.stripe_customer_id,
        auto_advance=True,
        idempotency_key=f"activation-invoice:{ctx.tenant.id}",
    )
    return _sub_out(sub)
