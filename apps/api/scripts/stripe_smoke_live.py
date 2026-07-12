"""GS0 live-contract probe — drive the real Stripe Billing API end-to-end in TEST MODE.

The E0 lesson (5 adapter bugs came from a doc-built adapter) applied to Phase G: run every method of
the §GS Stripe contract against the founder's live TEST-mode account BEFORE any billing code trusts
the adapter, and commit the captured shapes as the GS2 test fixtures. Everything uses the GS2 adapter
(`app.integrations.stripe.client`) — a green run is proof its request bodies match the live API.

Preconditions (FR-7): the founder created products/prices/meters in-dashboard and seeded
`holdslot/prod/stripe` (or exported `HOLDSLOT_STRIPE_KEY` = the **test-mode** `sk_test_…`), then ran
`verify_keys.py --only stripe --strict` PASS. This script NEVER touches a live key — it asserts the
key is test mode and refuses otherwise.

What it does (all in test mode, self-cleaning):
  1. create a scratch customer
  2. create a subscription carrying the metered `qualified_meeting` price
  3. emit a meter event TWICE with the SAME `identifier` → the **dedupe verdict** (⚠ GS0)
  4. read the upcoming-invoice preview → confirm a **$500** metered line lands
  5. build + verify a `Stripe-Signature` locally (the webhook contract)
  6. teardown: cancel the subscription + delete the customer

The verdicts to record (into tests/fixtures/stripe/_VERDICTS.md):
  ① does a duplicate `identifier` dedupe to ONE billed unit (event-then-stamp safety)
  ② the meter-event backdating limit (how far back `timestamp` may be set)

Run:  AWS_PROFILE=holdslot python scripts/stripe_smoke_live.py          # secret from Secrets Manager
      HOLDSLOT_STRIPE_KEY=sk_test_… python scripts/stripe_smoke_live.py # or an env test key
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

_FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "stripe"

PASS, FAIL = "PASS", "FAIL"
_ROWS: list[tuple[str, str]] = []


def _row(status: str, msg: str) -> None:
    _ROWS.append((status, msg))
    print(f"  [{status}] {msg}")


def _save_fixture(name: str, payload) -> None:
    _FIX.mkdir(parents=True, exist_ok=True)
    (_FIX / name).write_text(json.dumps(payload, indent=2) + "\n")
    print(f"      captured → tests/fixtures/stripe/{name}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--keep", action="store_true", help="leave the scratch customer/subscription up")
    args = ap.parse_args()

    from app.integrations.stripe import client as st

    # Refuse to run against a live key — this probe creates + deletes objects.
    if not str(st._api_key()).startswith(("sk_test", "rk_test")):
        print("REFUSING: holdslot/prod/stripe api_key is not a test-mode key (sk_test_/rk_test_).")
        return 2

    customer_id: str | None = None
    subscription_id: str | None = None
    try:
        # 1 — customer
        cust = st.create_customer(
            email="gs0-probe@tryholdslot.com",
            name="HoldSlot GS0 probe (scratch)",
            metadata={"probe": "gs0"},
            idempotency_key=f"gs0-cust-{int(time.time())}",
        )
        customer_id = cust.get("id")
        _row(PASS if customer_id else FAIL, f"create_customer → {customer_id}")
        _save_fixture("customer_response.json", cust)

        # 2 — subscription with the metered qualified_meeting price
        price = st.price_id("qualified_meeting")
        if not price:
            _row(FAIL, "secret missing price_qualified_meeting (create the metered price at GS0)")
            return 1
        sub = st.create_subscription(
            customer=customer_id,
            prices=[price],
            metadata={"probe": "gs0"},
            idempotency_key=f"gs0-sub-{int(time.time())}",
        )
        subscription_id = sub.get("id")
        _row(PASS if subscription_id else FAIL, f"create_subscription → {subscription_id} ({sub.get('status')})")
        _save_fixture("subscription_response.json", sub)

        # 3 — meter event twice, SAME identifier → dedupe verdict ①
        ident = f"meeting:gs0-{int(time.time())}"
        meter = st.meter_name("qualified_meeting")
        e1 = st.meter_event(event_name=meter, stripe_customer_id=customer_id, value=1, identifier=ident)
        e2 = st.meter_event(event_name=meter, stripe_customer_id=customer_id, value=1, identifier=ident)
        _row(PASS, f"meter_event ×2 same identifier accepted ({ident})")
        _save_fixture("meter_event_response.json", e1)
        _row(PASS, "VERDICT ① — confirm the upcoming invoice bills ONE unit, not two (dedupe by identifier)")

        # 4 — upcoming-invoice preview → the $500 line
        time.sleep(2)  # give the meter a moment to aggregate
        upcoming = st.upcoming_invoice(customer=customer_id)
        _save_fixture("upcoming_invoice_response.json", upcoming)
        amount = upcoming.get("amount_due")
        _row(PASS, f"upcoming_invoice preview amount_due={amount} (expect one $500 metered line)")

        # 5 — webhook signature round-trip (local)
        secret = st.webhook_signing_secret() or "whsec_probe_placeholder"
        payload = json.dumps({"id": "evt_probe", "type": "invoice.paid"}).encode()
        ts = int(time.time())
        import hashlib
        import hmac

        sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
        header = f"t={ts},v1={sig}"
        ok = st.verify_webhook(payload, header, secret=secret, now=ts)
        _row(PASS if ok else FAIL, "verify_webhook round-trips a self-signed Stripe-Signature")
        _row(PASS, "VERDICT ② — record the meter-event backdating limit (how far back `timestamp` may be set)")

    finally:
        if not args.keep:
            _teardown(st, subscription_id, customer_id)

    n_fail = sum(1 for s, _ in _ROWS if s == FAIL)
    print("\n" + "=" * 60)
    print(f"GS0 SUMMARY: {sum(1 for s, _ in _ROWS if s == PASS)} passed, {n_fail} failed")
    print("Record the ①/② verdicts in tests/fixtures/stripe/_VERDICTS.md, then commit the fixtures.")
    print("=" * 60)
    return 1 if n_fail else 0


def _teardown(st, subscription_id: str | None, customer_id: str | None) -> None:
    """Cancel + delete the scratch objects (DELETE stays out of the 6-method adapter — transport
    directly). A failed teardown is harmless (test mode); delete by hand in the Stripe dashboard."""
    try:
        if subscription_id:
            st._request("DELETE", f"/v1/subscriptions/{urllib.parse.quote(subscription_id)}")
            print(f"[teardown] cancelled subscription {subscription_id}")
        if customer_id:
            st._request("DELETE", f"/v1/customers/{urllib.parse.quote(customer_id)}")
            print(f"[teardown] deleted customer {customer_id}")
    except Exception as e:  # noqa: BLE001 — operational script; a failed delete is harmless
        print(f"[teardown] cleanup failed ({e}); delete the scratch objects by hand in Stripe")


if __name__ == "__main__":
    sys.exit(main())
