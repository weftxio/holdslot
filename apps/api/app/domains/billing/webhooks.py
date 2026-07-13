"""Stripe webhook ingest (GS5) — public, signature-verified. NO auth header, NO `{client}` segment.

The inbound Stripe surface. Posture mirrors the Smartlead webhook (initial-build-plan.md → §GS5):

  * **Auth = the Stripe signature** (`Stripe-Signature`, HMAC-SHA256 over `"{t}.{body}"`, ~300s
    tolerance) verified against the RAW body — plus an optional high-entropy PATH token in front
    (defense-in-depth; the signature is the security-critical check). Bad/absent signature → 400.
  * **Always answers 2xx once the raw event is stored** — a 5xx triggers Stripe's retry storm. Store
    raw first, deduped on `stripe_event_id` (the unique index), THEN apply the status effect. A
    downstream error is swallowed (2xx); Stripe re-sends only on a non-2xx.
  * Events handled: `invoice.paid` · `invoice.payment_failed` · `customer.subscription.updated` ·
    `customer.subscription.deleted` → update `subscription.status` (+ the activation stamp).
"""

from __future__ import annotations

import hmac
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.domains.prospects.scoring import is_unique_violation
from app.integrations.stripe import client as stripe
from app.models import BillingEvent, Subscription

router = APIRouter(tags=["stripe-webhooks"])
log = logging.getLogger("holdslot.stripe.webhook")


@router.post("/webhooks/stripe/{token}")
async def ingest_stripe(token: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Ingest one Stripe webhook event. Always 2xx once stored (or a benign dedupe no-op).

    M22: this route stays `async` deliberately — HMAC verification needs the RAW body via
    `await request.body()`, which a sync endpoint can't reach. The sync DB I/O below does not starve
    the event loop here: one Lambda instance serves one request at a time (SnapStart), so no
    concurrent request to block. (This is the only async route in the app.)"""
    # Read the Stripe secret first — but a MISSING secret (dormant: `holdslot/prod/stripe` not yet
    # seeded) must disable the route cleanly (404, no leak), never surface the boto3 lookup error as
    # a 500 on a public endpoint (the smartlead posture).
    try:
        expected = stripe.webhook_path_token()
        signing_secret = stripe.webhook_signing_secret()
    except Exception:  # noqa: BLE001 — secret not provisioned → route disabled
        raise HTTPException(status.HTTP_404_NOT_FOUND) from None
    if not signing_secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    # Path token (if configured) is a bonus gate in front of the signature; mismatch → 404 no leak.
    if expected is not None and not hmac.compare_digest(str(token), str(expected)):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    raw = await request.body()
    sig = request.headers.get("stripe-signature")
    if not stripe.verify_webhook(raw, sig, secret=signing_secret):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad signature")
    try:
        event = json.loads(raw.decode() or "{}")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad payload") from exc
    try:
        return _ingest(db, event)
    except Exception:  # noqa: BLE001 — never 5xx a verified event (Stripe retry-storm guard)
        log.exception("stripe webhook ingest failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "deferred": True}


def _resolve_subscription(db: Session, obj: dict) -> Subscription | None:
    """The tenant's subscription row for this event — by Stripe customer id (present on both invoice
    and subscription objects)."""
    customer = obj.get("customer")
    if not isinstance(customer, str):
        return None
    return db.execute(
        select(Subscription).where(Subscription.stripe_customer_id == customer)
    ).scalar_one_or_none()


def _store_event(
    db: Session, event_id: str, etype: str, payload: dict, tenant_id
) -> BillingEvent | None:
    """Insert the raw event deduped on `stripe_event_id`. Returns the row, or None on a Stripe retry
    (duplicate) — commits either way (the `outreach_event` posture)."""
    ev = BillingEvent(
        tenant_id=tenant_id,
        stripe_event_id=event_id,
        type=etype[:64],
        payload=payload,
    )
    db.add(ev)
    try:
        db.flush()
    except DBAPIError as exc:
        if not is_unique_violation(exc):
            raise
        db.rollback()
        return None
    db.commit()
    return ev


def _apply(etype: str, obj: dict, sub: Subscription | None) -> None:
    """Mirror the Stripe state onto our `subscription` row. Unknown customer → no-op (still stored).
    """
    if sub is None:
        return
    if etype == "invoice.paid":
        # The activation invoice is collected first at close, so the first paid invoice stamps it
        # (GS0/GSA refine this to a billing_reason check if a monthly invoice could arrive first).
        if sub.activation_paid_at is None:
            sub.activation_paid_at = datetime.now(UTC)
        sub.status = "active"
    elif etype == "invoice.payment_failed":
        sub.status = "past_due"
    elif etype == "customer.subscription.deleted":
        sub.status = "canceled"
    elif etype == "customer.subscription.updated":
        new_status = obj.get("status")
        if new_status:
            sub.status = str(new_status)[:16]
        if obj.get("id") and not sub.stripe_subscription_id:
            sub.stripe_subscription_id = str(obj["id"])


def _ingest(db: Session, event: dict) -> dict:
    event_id = event.get("id")
    if not event_id:
        return {"ok": True, "ignored": "no event id"}
    etype = str(event.get("type") or "")
    obj = ((event.get("data") or {}).get("object")) or {}
    sub = _resolve_subscription(db, obj)
    tenant_id = sub.tenant_id if sub else None

    stored = _store_event(db, event_id, etype, event, tenant_id)
    if stored is None:
        return {"ok": True, "deduped": True}  # a Stripe retry — no double-process

    try:
        _apply(etype, obj, sub)
        db.commit()
    except Exception:  # noqa: BLE001 — the event is stored; a bad status effect must not 5xx
        log.exception("stripe status effect failed (event %s)", event_id)
        db.rollback()
    return {"ok": True, "type": etype}
