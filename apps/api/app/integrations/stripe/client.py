"""Stripe transport (GS2) — the billing methods behind the metered charge + activation invoice.

Mirrors the Apollo/OpenRouter/Smartlead discipline: **lazy / SnapStart-safe** (no secret read, no
network at import — it loads on first use + caches), stdlib `urllib` (NO SDK, no runtime HTTP dep),
bounded 429/5xx backoff. Built on **Stripe Billing Meters** — legacy usage-records is removed at API
version `2025-03-31.basil` (verified 2026-07-12, GF-4), so the version header is pinned and the
metered usage is reported as **meter events**, never usage records.

Contract (docs/initial-build-plan.md → §GS):
  * **Auth is a Bearer header** — `Authorization: Bearer sk_…`. The key is never in a URL, but a
    careless log/exception could still carry it, so `_redact()` scrubs any `sk_`/`rk_`/`whsec_`
    token from every string before it reaches a log / telemetry / exception (assert-tested).
  * **Form-encoded bodies** — Stripe wants `application/x-www-form-urlencoded` with bracket notation
    (`items[0][price]=…`, `payload[stripe_customer_id]=…`); `_encode_form` flattens nested values.
  * **`Idempotency-Key` on every POST** — a create retried after a blip never double-bills. Meter
    events additionally carry an `identifier` (the app-level dedupe: `meeting:{id}`).
  * **Webhook `Stripe-Signature`** — `t=…,v1=…`; `verify_webhook` recomputes HMAC-SHA256 over
    `"{t}.{payload}"` with the signing secret, `compare_digest`, ~300s tolerance (GS0 ⚠ pins it).

The six methods, nothing more: create_customer · create_subscription · create_invoice_item ·
create_invoice · meter_event · verify_webhook (+ get_account/upcoming_invoice for the GS0 probe).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache

from app.core.config import fetch_secret_json

log = logging.getLogger("holdslot.stripe")

BASE_URL = "https://api.stripe.com"
DEFAULT_TIMEOUT = 25  # seconds
# Pinned API version — usage-records is GONE at/after this version, so meters are the only metered
# path (GF-4). GS0 confirms it against the live test-mode account before deploy.
API_VERSION = "2025-03-31.basil"
_RETRYABLE = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
# The webhook timestamp tolerance (replay guard) — GS0 pins the exact value; 300s is Stripe's own.
WEBHOOK_TOLERANCE_SECONDS = 300

# sk_live_… / rk_test_… / whsec_… — scrubbed before any log/exception (the R1 posture). The token
# part is base62 (no underscores), so the prefix (through the mode underscore) is kept, token gone.
_KEY_RE = re.compile(r"((?:(?:sk|rk)_(?:live|test)_|whsec_))[A-Za-z0-9]+")


class StripeError(RuntimeError):
    """A non-recoverable Stripe call (bad key, exhausted retries, transport, or a 4xx). Carries the
    status; its message is always redacted so a secret key can never reach an exception string."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(_redact(message))
        self.status = status


def _redact(text: str) -> str:
    """Scrub any Stripe secret token (`sk_`/`rk_`/`whsec_`) from a string → `sk_***`. The single
    control that keeps a key out of logs/telemetry/exceptions even if one is accidentally formatted
    into a message."""
    return _KEY_RE.sub(r"\1***", text or "")


@lru_cache(maxsize=1)
def _secret() -> dict:
    """Read `{prefix}/stripe` once and cache it (GD-3 envelope):
    `{api_key, webhook_signing_secret, price_launch, price_growth, price_activation,
    meter_qualified_meeting, meter_enrichment_overage}`. `HOLDSLOT_STRIPE_KEY` env wins for local /
    tests (JSON or a bare key), so a swap needs no Secrets Manager round-trip."""
    if env := os.environ.get("HOLDSLOT_STRIPE_KEY"):
        try:
            parsed = json.loads(env)
            return parsed if isinstance(parsed, dict) else {"api_key": env}
        except json.JSONDecodeError:
            return {"api_key": env}
    return fetch_secret_json("stripe")


def _api_key() -> str:
    key = _secret().get("api_key")
    if not key:
        raise StripeError("stripe secret missing api_key")
    return str(key)


def webhook_signing_secret() -> str | None:
    tok = _secret().get("webhook_signing_secret")
    return str(tok) if tok else None


def webhook_path_token() -> str | None:
    """The high-entropy `{token}` segment of the inbound webhook route — defense-in-depth in front
    of the Stripe signature verify (the smartlead path-token posture). Optional; the signature is
    the security-critical check."""
    tok = _secret().get("webhook_path_token")
    return str(tok) if tok else None


def price_id(plan: str) -> str | None:
    """The Stripe price id for a plan (`launch`/`growth`) or the one-time `activation` price."""
    return _secret().get(f"price_{plan}")


def meter_name(kind: str) -> str:
    """The meter `event_name` for `qualified_meeting`/`enrichment_overage` (defaults to `kind`)."""
    return str(_secret().get(f"meter_{kind}") or kind)


def reset_secret() -> None:
    _secret.cache_clear()


# --------------------------------------------------------------------------- form encoding


def _flatten(prefix: str, value, out: list[tuple[str, str]]) -> None:
    """Flatten nested dict/list into Stripe's bracket form: `a[b]`, `a[0][c]`. Skips None."""
    if value is None:
        return
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}[{k}]" if prefix else str(k), v, out)
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _flatten(f"{prefix}[{i}]", v, out)
    elif isinstance(value, bool):
        out.append((prefix, "true" if value else "false"))
    else:
        out.append((prefix, str(value)))


def _encode_form(data: dict) -> bytes:
    out: list[tuple[str, str]] = []
    for k, v in data.items():
        _flatten(str(k), v, out)
    return urllib.parse.urlencode(out).encode()


# --------------------------------------------------------------------------- transport


def _request(
    method: str,
    path: str,
    *,
    form: dict | None = None,
    query: dict | None = None,
    idempotency_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """One request (Bearer auth, form-encoded body, pinned API version), throttled by nothing but
    retried on transient 429/5xx with exponential backoff. 401/402/403 drop the cached secret and
    raise immediately (no retry storm on a bad key). Every error path goes through `_redact`."""
    url = f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    data = _encode_form(form) if form is not None else None
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Stripe-Version": API_VERSION,
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    for attempt in range(_MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode()
                return json.loads(text) if text.strip() else {}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                reset_secret()
                raise StripeError(f"stripe auth error (HTTP {e.code})", status=e.code) from e
            if e.code in _RETRYABLE and attempt < _MAX_RETRIES:
                time.sleep(0.5 * (2**attempt))  # 0.5, 1, 2, 4s
                continue
            body = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
            raise StripeError(
                f"stripe HTTP {e.code} on {path}: {body[:300]}", status=e.code
            ) from e
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < _MAX_RETRIES:
                time.sleep(0.5 * (2**attempt))
                continue
            raise StripeError(f"stripe transport error on {path}: {e}") from e
    raise StripeError(f"stripe exhausted retries on {path}")  # unreachable


# --------------------------------------------------------------------------- the six methods


def create_customer(
    *, email: str, name: str | None = None, metadata: dict | None = None, idempotency_key: str
) -> dict:
    """`POST /v1/customers` → `{id: cus_…, …}`. `metadata[tenant_id]` ties the Stripe customer back
    to our tenant so a webhook can resolve it."""
    form: dict = {"email": email}
    if name:
        form["name"] = name
    if metadata:
        form["metadata"] = metadata
    return _request("POST", "/v1/customers", form=form, idempotency_key=idempotency_key)


def create_subscription(
    *, customer: str, prices: list[str], metadata: dict | None = None, idempotency_key: str
) -> dict:
    """`POST /v1/subscriptions` with one item per `prices` entry → `{id: sub_…, status, …}`. A
    paying tenant carries two: the flat monthly plan price (Launch $800 / Growth $1,600) + metered
    `qualified_meeting` price ($500/unit). The subscription's own billing period does the monthly
    close (GD-2 — no EventBridge). GS0 pins the exact item structure against the live account."""
    form: dict = {"customer": customer, "items": [{"price": p} for p in prices if p]}
    if metadata:
        form["metadata"] = metadata
    return _request("POST", "/v1/subscriptions", form=form, idempotency_key=idempotency_key)


def create_invoice_item(
    *,
    customer: str,
    amount_cents: int,
    currency: str = "usd",
    description: str | None = None,
    idempotency_key: str,
) -> dict:
    """`POST /v1/invoiceitems` — a one-off line (the $400 activation, GD-9). `amount_cents` is the
    integer minor unit ($400 → 40000)."""
    form: dict = {"customer": customer, "amount": int(amount_cents), "currency": currency}
    if description:
        form["description"] = description
    return _request("POST", "/v1/invoiceitems", form=form, idempotency_key=idempotency_key)


def create_invoice(*, customer: str, auto_advance: bool = True, idempotency_key: str) -> dict:
    """`POST /v1/invoices` — sweep the customer's pending invoice items into a standalone invoice.
    `auto_advance` lets Stripe finalize + collect (the standalone activation invoice, GD-9)."""
    return _request(
        "POST",
        "/v1/invoices",
        form={"customer": customer, "auto_advance": auto_advance},
        idempotency_key=idempotency_key,
    )


def meter_event(
    *, event_name: str, stripe_customer_id: str, value: int = 1, identifier: str
) -> dict:
    """`POST /v1/billing/meter_events` — report one unit of metered usage. `identifier` is the
    app-level dedupe (`meeting:{id}`), so an event-then-stamp crash-retry is a no-op at Stripe
    (the GS0 verdict). No `Idempotency-Key` needed — `identifier` IS the idempotency key here."""
    return _request(
        "POST",
        "/v1/billing/meter_events",
        form={
            "event_name": event_name,
            "identifier": identifier,
            "payload": {"stripe_customer_id": stripe_customer_id, "value": str(value)},
        },
    )


def upcoming_invoice(*, customer: str) -> dict:
    """`GET /v1/invoices/upcoming` — the GS0-probe preview confirming a $500 metered line."""
    return _request("GET", "/v1/invoices/upcoming", query={"customer": customer})


def get_account() -> dict:
    """`GET /v1/account` — a free auth check (the verify_keys.py probe). 200 = the key is valid."""
    return _request("GET", "/v1/account")


# --------------------------------------------------------------------------- webhook signature


def verify_webhook(
    payload: bytes, sig_header: str | None, *, secret: str | None = None, now: int | None = None
) -> bool:
    """Verify a `Stripe-Signature` header against the raw request body. Recomputes
    HMAC-SHA256 over `"{t}.{payload}"` with the signing secret and constant-time-compares it to any
    `v1` signature, rejecting a timestamp older than `WEBHOOK_TOLERANCE_SECONDS` (replay guard).
    Returns False on any malformed/absent input — never raises, so the route answers a clean 4xx."""
    key = secret or webhook_signing_secret()
    if not key or not sig_header:
        return False
    parts = dict(
        p.split("=", 1) for p in sig_header.split(",") if "=" in p  # t=…,v1=…,v1=…
    )
    ts = parts.get("t")
    if not ts or not ts.isdigit():
        return False
    now = int(time.time()) if now is None else now
    if abs(now - int(ts)) > WEBHOOK_TOLERANCE_SECONDS:
        return False
    signed = f"{ts}.".encode() + payload
    expected = hmac.new(key.encode(), signed, hashlib.sha256).hexdigest()
    # There can be multiple v1= entries (during a secret roll); accept if any matches.
    provided = [
        v for k, v in (p.split("=", 1) for p in sig_header.split(",") if "=" in p) if k == "v1"
    ]
    return any(hmac.compare_digest(expected, v) for v in provided)


__all__ = [
    "create_customer",
    "create_subscription",
    "create_invoice_item",
    "create_invoice",
    "meter_event",
    "upcoming_invoice",
    "get_account",
    "verify_webhook",
    "webhook_signing_secret",
    "webhook_path_token",
    "price_id",
    "meter_name",
    "reset_secret",
    "StripeError",
    "BASE_URL",
    "API_VERSION",
    "WEBHOOK_TOLERANCE_SECONDS",
]
