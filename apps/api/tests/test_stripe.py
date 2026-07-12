"""GS2 unit tests — the Stripe adapter + the pure billing money rules (mocked transport; no network,
no key, no charge).

Three layers, the `test_smartlead.py` pattern:
  * Each contract method maps to its exact path + form body (mock `_request`).
  * The real `_request` is exercised against a fake `urlopen` to pin the Bearer auth, the pinned
    Stripe-Version, the Idempotency-Key, the form encoding, the secret redaction (no `sk_` in any
    log/exception), and the 429 backoff.
  * `verify_webhook` is pinned against a self-signed `Stripe-Signature` (good / tampered / stale /
    absent), and the pure GS4 money rule (`enrichment_decision` + caps) is table-tested — all
    [money], all non-Aurora (the N1 rule). These are the doc-fixtures the GS0 probe later confirms.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error

import pytest

from app.domains.billing import service as bsvc
from app.integrations.stripe import client as st

# --------------------------------------------------------------------------- method → path/body


def _capture(monkeypatch, ret=None):
    calls: list[dict] = []

    def fake(method, path, *, form=None, query=None, idempotency_key=None, timeout=25):
        calls.append(
            {"method": method, "path": path, "form": form, "query": query, "idem": idempotency_key}
        )
        return ret if ret is not None else {"id": "obj_1"}

    monkeypatch.setattr(st, "_request", fake)
    return calls


def test_create_customer_posts_email_and_metadata(monkeypatch):
    calls = _capture(monkeypatch, ret={"id": "cus_1"})
    out = st.create_customer(
        email="a@b.com", name="Acme", metadata={"tenant_id": "t1"}, idempotency_key="cust:t1"
    )
    assert out["id"] == "cus_1"
    assert calls[0]["method"] == "POST" and calls[0]["path"] == "/v1/customers"
    assert calls[0]["form"]["email"] == "a@b.com"
    assert calls[0]["form"]["metadata"] == {"tenant_id": "t1"}
    assert calls[0]["idem"] == "cust:t1"  # a retry never double-creates the customer


def test_create_subscription_builds_price_items(monkeypatch):
    calls = _capture(monkeypatch, ret={"id": "sub_1", "status": "active"})
    st.create_subscription(
        customer="cus_1", prices=["price_flat", "price_metered"], idempotency_key="sub:t1"
    )
    assert calls[0]["path"] == "/v1/subscriptions"
    assert calls[0]["form"]["items"] == [{"price": "price_flat"}, {"price": "price_metered"}]


def test_create_invoice_item_amount_in_cents(monkeypatch):
    calls = _capture(monkeypatch)
    st.create_invoice_item(
        customer="cus_1", amount_cents=40000, description="activation", idempotency_key="a:t1"
    )
    assert calls[0]["path"] == "/v1/invoiceitems"
    assert calls[0]["form"] == {
        "customer": "cus_1",
        "amount": 40000,
        "currency": "usd",
        "description": "activation",
    }


def test_meter_event_carries_identifier_and_payload(monkeypatch):
    calls = _capture(monkeypatch)
    st.meter_event(
        event_name="qualified_meeting",
        stripe_customer_id="cus_1",
        value=1,
        identifier="meeting:abc",
    )
    assert calls[0]["path"] == "/v1/billing/meter_events"
    b = calls[0]["form"]
    assert b["event_name"] == "qualified_meeting"
    assert b["identifier"] == "meeting:abc"  # the app-level dedupe key
    assert b["payload"] == {"stripe_customer_id": "cus_1", "value": "1"}
    assert calls[0]["idem"] is None  # meter events dedupe on `identifier`, not Idempotency-Key


# --------------------------------------------------------------------------- form encoding


def test_encode_form_flattens_nested_bracket_notation():
    body = st._encode_form(
        {"customer": "cus_1", "items": [{"price": "p1"}], "metadata": {"tenant_id": "t1"}}
    )
    parts = body.decode()
    assert "customer=cus_1" in parts
    assert "items%5B0%5D%5Bprice%5D=p1" in parts  # items[0][price]=p1
    assert "metadata%5Btenant_id%5D=t1" in parts  # metadata[tenant_id]=t1


# ------------------------------------------------------------------------- real _request (fakeurl)


class _FakeResp:
    def __init__(self, payload: dict, status: int = 200):
        self._body = json.dumps(payload).encode()
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_request_builds_bearer_auth_version_and_idempotency(monkeypatch):
    monkeypatch.setenv("HOLDSLOT_STRIPE_KEY", "sk_test_SECRET123")
    st.reset_secret()
    seen: dict = {}

    def fake_urlopen(req, timeout=0):
        seen["auth"] = req.headers.get("Authorization")
        seen["version"] = req.headers.get("Stripe-version")
        seen["idem"] = req.headers.get("Idempotency-key")
        seen["ctype"] = req.headers.get("Content-type")
        seen["body"] = req.data.decode() if req.data else ""
        return _FakeResp({"id": "cus_1"})

    monkeypatch.setattr(st.urllib.request, "urlopen", fake_urlopen)
    out = st._request("POST", "/v1/customers", form={"email": "a@b.com"}, idempotency_key="k1")
    assert out == {"id": "cus_1"}
    assert seen["auth"] == "Bearer sk_test_SECRET123"  # Bearer header, not a query param
    assert seen["version"] == st.API_VERSION  # pinned so usage-records never resurfaces
    assert seen["idem"] == "k1"
    assert seen["ctype"] == "application/x-www-form-urlencoded"
    assert "email=a%40b.com" in seen["body"]
    st.reset_secret()


def test_redact_scrubs_secret_keys():
    assert "SUPERSECRET" not in st._redact("failed with sk_live_SUPERSECRET now")
    assert "sk_live_***" in st._redact("sk_live_SUPERSECRET")
    assert "whsec_***" in st._redact("whsec_ABCDEF")


def test_error_message_is_redacted(monkeypatch):
    monkeypatch.setenv("HOLDSLOT_STRIPE_KEY", "sk_live_LEAKME")
    st.reset_secret()

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr(st.urllib.request, "urlopen", boom)
    with pytest.raises(st.StripeError) as ei:
        st._request("POST", "/v1/customers", form={"x": "1"}, idempotency_key="k")
    assert "LEAKME" not in str(ei.value)
    st.reset_secret()


def test_no_secret_in_logs(monkeypatch, caplog):
    monkeypatch.setenv("HOLDSLOT_STRIPE_KEY", "sk_live_LOGLEAK")
    st.reset_secret()
    monkeypatch.setattr(st.time, "sleep", lambda *_: None)

    def flaky(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 503, "err", {}, None)

    monkeypatch.setattr(st.urllib.request, "urlopen", flaky)
    with caplog.at_level(logging.DEBUG, logger="holdslot.stripe"):
        with pytest.raises(st.StripeError):
            st._request("GET", "/v1/account")
    assert "LOGLEAK" not in caplog.text
    st.reset_secret()


def test_retries_transient_5xx_then_raises(monkeypatch):
    monkeypatch.setenv("HOLDSLOT_STRIPE_KEY", "sk_test_k")
    st.reset_secret()
    monkeypatch.setattr(st.time, "sleep", lambda *_: None)
    n = {"c": 0}

    def flaky(req, timeout=0):
        n["c"] += 1
        raise urllib.error.HTTPError(req.full_url, 429, "rate", {}, None)

    monkeypatch.setattr(st.urllib.request, "urlopen", flaky)
    with pytest.raises(st.StripeError) as ei:
        st._request("GET", "/v1/account")
    assert ei.value.status == 429
    assert n["c"] == st._MAX_RETRIES + 1
    st.reset_secret()


def test_auth_error_drops_cached_secret(monkeypatch):
    monkeypatch.setenv("HOLDSLOT_STRIPE_KEY", "sk_test_k")
    st.reset_secret()

    def denied(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)

    monkeypatch.setattr(st.urllib.request, "urlopen", denied)
    with pytest.raises(st.StripeError) as ei:
        st._request("GET", "/v1/account")
    assert ei.value.status == 401  # 401/403 raise immediately (no retry storm)
    st.reset_secret()


def test_secret_env_override_json_and_bare(monkeypatch):
    env = {"api_key": "sk_test_kk", "price_launch": "price_L", "meter_qualified_meeting": "qm"}
    monkeypatch.setenv("HOLDSLOT_STRIPE_KEY", json.dumps(env))
    st.reset_secret()
    assert st._api_key() == "sk_test_kk"
    assert st.price_id("launch") == "price_L"
    assert st.meter_name("qualified_meeting") == "qm"
    assert st.meter_name("enrichment_overage") == "enrichment_overage"  # falls back to the kind
    monkeypatch.setenv("HOLDSLOT_STRIPE_KEY", "sk_test_bare")
    st.reset_secret()
    assert st._api_key() == "sk_test_bare"
    st.reset_secret()


# --------------------------------------------------------------------------- webhook signature


def _sign(secret: str, payload: bytes, ts: int) -> str:
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def test_verify_webhook_accepts_good_signature():
    payload = json.dumps({"id": "evt_1", "type": "invoice.paid"}).encode()
    ts = 1_800_000_000
    header = _sign("whsec_TESTSECRET", payload, ts)
    assert st.verify_webhook(payload, header, secret="whsec_TESTSECRET", now=ts) is True


def test_verify_webhook_rejects_tamper_stale_and_absent(monkeypatch):
    # A bare-key envelope carries no webhook_signing_secret, so the `secret=None` case below is
    # None deterministically instead of hitting Secrets Manager.
    monkeypatch.setenv("HOLDSLOT_STRIPE_KEY", "sk_test_x")
    st.reset_secret()
    payload = json.dumps({"id": "evt_1"}).encode()
    ts = 1_800_000_000
    good = _sign("whsec_TESTSECRET", payload, ts)
    # tampered body
    assert st.verify_webhook(b'{"id":"evt_2"}', good, secret="whsec_TESTSECRET", now=ts) is False
    # stale timestamp (beyond tolerance)
    assert st.verify_webhook(payload, good, secret="whsec_TESTSECRET", now=ts + 400) is False
    # wrong secret
    assert st.verify_webhook(payload, good, secret="whsec_OTHER", now=ts) is False
    # absent header / secret
    assert st.verify_webhook(payload, None, secret="whsec_TESTSECRET", now=ts) is False
    assert st.verify_webhook(payload, good, secret=None, now=ts) is False
    st.reset_secret()


# --------------------------------------------------------------------------- GS4 money rule (pure)


def test_effective_cap_override_wins():
    assert bsvc.effective_cap("launch", None) == 150
    assert bsvc.effective_cap("growth", None) == 400
    assert bsvc.effective_cap("launch", 999) == 999  # founder override wins
    assert bsvc.effective_cap("unknown", None) == 0


def test_enrichment_decision_within_cap():
    d = bsvc.enrichment_decision(cap=150, used=10, requested=20, overage_enabled=True)
    assert (d.allowed, d.overage, d.blocked) == (20, 0, 0)


def test_enrichment_decision_overage_enabled_meters_excess():
    # cap 150, used 140, ask 20 → 10 within cap, 10 over → all allowed, 10 metered as overage.
    d = bsvc.enrichment_decision(cap=150, used=140, requested=20, overage_enabled=True)
    assert (d.allowed, d.overage, d.blocked) == (20, 10, 0)


def test_enrichment_decision_overage_disabled_hard_stops_excess():
    d = bsvc.enrichment_decision(cap=150, used=140, requested=20, overage_enabled=False)
    assert (d.allowed, d.overage, d.blocked) == (10, 0, 10)  # only the within-cap rows spend


def test_enrichment_decision_at_cap_boundary():
    # exactly at cap, overage disabled → nothing allowed, everything blocked (the 150/400 boundary).
    d = bsvc.enrichment_decision(cap=150, used=150, requested=5, overage_enabled=False)
    assert (d.allowed, d.overage, d.blocked) == (0, 0, 5)


def test_meeting_identifier_and_month_key():
    assert bsvc.meeting_identifier("abc-123") == "meeting:abc-123"
    from datetime import UTC, datetime

    assert bsvc.usage_month_key(datetime(2026, 7, 13, 23, 30, tzinfo=UTC)) == "2026-07"
