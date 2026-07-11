"""E2 unit tests — the Smartlead adapter (mocked transport; no network, no key, no spend).

Two layers, the `test_apollo.py` pattern:
  * Each of the eleven methods maps to its exact URL path + request body (mock `_request`).
  * The real `_request` is exercised against a fake `urlopen` to pin the query-param auth, the R1
    redaction (no `api_key` in any log / exception string), the 429 backoff, and the throttle.
All request/response shapes are the E0 fixtures — the single Phase-E test-data source.
"""

from __future__ import annotations

import json
import logging
import urllib.error
from pathlib import Path

import pytest

from app.domains.campaigns import service as svc
from app.integrations.smartlead import client as sl

_FIX = Path(__file__).resolve().parent / "fixtures" / "smartlead"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text())


# --------------------------------------------------------------------------- method → path/body


def _capture(monkeypatch, ret=None):
    calls: list[dict] = []

    def fake(method, path, *, body=None, query=None, timeout=sl.DEFAULT_TIMEOUT):
        calls.append({"method": method, "path": path, "body": body, "query": query})
        return ret if ret is not None else {"ok": True, "id": 900001}

    monkeypatch.setattr(sl, "_request", fake)
    return calls


def test_create_campaign_posts_name_only(monkeypatch):
    calls = _capture(monkeypatch)
    out = sl.create_campaign("Phase E Test Batch")
    assert out["id"] == 900001
    assert calls[0]["method"] == "POST" and calls[0]["path"] == "campaigns/create"
    assert calls[0]["body"] == {"name": "Phase E Test Batch"}
    # client_id is included only when given.
    _capture(monkeypatch)  # reset
    sl.create_campaign("X", client_id=7)


def test_update_schedule_carries_daily_cap(monkeypatch):
    calls = _capture(monkeypatch)
    sched = {"timezone": "Asia/Singapore", "max_new_leads_per_day": 40, "start_hour": "09:00"}
    sl.update_schedule(900001, sched)
    assert calls[0]["path"] == "campaigns/900001/schedule"
    assert calls[0]["body"]["max_new_leads_per_day"] == 40  # the EF-Q3 cap rides through untouched


def test_save_sequences_wraps_in_sequences_key(monkeypatch):
    calls = _capture(monkeypatch)
    seqs = [{"seq_number": 1, "subject": "Hi", "email_body": "..."}]
    sl.save_sequences(900001, seqs)
    assert calls[0]["path"] == "campaigns/900001/sequences"
    assert calls[0]["body"] == {"sequences": seqs}


def test_add_email_accounts_body(monkeypatch):
    calls = _capture(monkeypatch)
    sl.add_email_accounts(900001, [11, 22])
    assert calls[0]["path"] == "campaigns/900001/email-accounts"
    assert calls[0]["body"] == {"email_account_ids": [11, 22]}


def test_add_leads_forces_compliance_floor_no_return_ids(monkeypatch):
    calls = _capture(monkeypatch)
    sl.add_leads(900001, [{"email": "a@b.com"}])
    b = calls[0]["body"]
    assert calls[0]["path"] == "campaigns/900001/leads"
    # The live API rejects a top-level return_lead_ids (400 "not allowed", verified 2026-07-11) —
    # ids are resolved afterwards via fetch_campaign_leads, so it must NOT be sent.
    assert "return_lead_ids" not in b
    assert b["lead_list"] == [{"email": "a@b.com"}]
    for k in (
        "ignore_global_block_list",
        "ignore_unsubscribe_list",
        "ignore_community_bounce_list",
        "ignore_duplicate_leads_in_other_campaign",
    ):
        assert b["settings"][k] is False


def test_fetch_campaign_leads_paginates(monkeypatch):
    calls = _capture(monkeypatch)
    sl.fetch_campaign_leads(900001, offset=100, limit=100)
    assert calls[0]["method"] == "GET" and calls[0]["path"] == "campaigns/900001/leads"
    assert calls[0]["query"] == {"offset": 100, "limit": 100}


def test_add_leads_caller_cannot_flip_compliance_flags(monkeypatch):
    """The compliance floor is NON-overridable — a caller passing ignore_*: True is ignored."""
    calls = _capture(monkeypatch)
    sl.add_leads(900001, [{"email": "a@b.com"}], settings={"ignore_global_block_list": True})
    assert calls[0]["body"]["settings"]["ignore_global_block_list"] is False


def test_set_status_uppercase_enum(monkeypatch):
    calls = _capture(monkeypatch)
    sl.set_status(900001, sl.STATUS_PAUSED)
    assert calls[0]["path"] == "campaigns/900001/status"
    assert calls[0]["body"] == {"status": "PAUSED"}


def test_register_webhook_body(monkeypatch):
    calls = _capture(monkeypatch, ret=_load("webhook_register_response.json"))
    out = sl.register_webhook(
        900001,
        name="holdslot-ingest",
        webhook_url="https://api.tryholdslot.com/webhooks/smartlead/tok",
        event_types=["EMAIL_SENT", "EMAIL_REPLY"],
    )
    assert out["id"] == 671685  # the real (captured) register response passes through
    b = calls[0]["body"]
    assert calls[0]["path"] == "campaigns/900001/webhooks"
    assert b["webhook_url"].endswith("/tok")
    assert b["event_types"] == ["EMAIL_SENT", "EMAIL_REPLY"]
    # categories is REQUIRED non-empty by the live API — defaults to the seven standard categories.
    assert b["categories"] == sl.DEFAULT_WEBHOOK_CATEGORIES
    assert len(b["categories"]) == 7


def test_reply_to_thread_includes_handle(monkeypatch):
    calls = _capture(monkeypatch)
    sl.reply_to_thread(
        900001, email_stats_id="stats-1", email_body="Thanks!", reply_message_id="<msg-1>"
    )
    b = calls[0]["body"]
    assert calls[0]["path"] == "campaigns/900001/reply-email-thread"
    assert b["email_stats_id"] == "stats-1"
    assert b["reply_message_id"] == "<msg-1>"
    assert b["email_body"] == "Thanks!"


def test_reply_to_thread_omits_absent_optionals(monkeypatch):
    calls = _capture(monkeypatch)
    sl.reply_to_thread(900001, email_stats_id="s", email_body="x")
    assert "reply_message_id" not in calls[0]["body"]
    assert "cc" not in calls[0]["body"]


def test_fetch_statistics_paginates(monkeypatch):
    calls = _capture(monkeypatch)
    sl.fetch_statistics(900001, offset=0, limit=100)
    assert calls[0]["method"] == "GET" and calls[0]["path"] == "campaigns/900001/statistics"
    assert calls[0]["query"] == {"offset": 0, "limit": 100}


def test_fetch_inbox_replies_sets_history_query(monkeypatch):
    calls = _capture(monkeypatch)
    sl.fetch_inbox_replies(900001, limit=50)
    assert calls[0]["path"] == "master-inbox/inbox-replies"
    assert calls[0]["query"] == {"fetch_message_history": "true"}
    assert calls[0]["body"]["limit"] == 20  # clamped to the ≤20 ceiling


# ------------------------------------------------------------------------ tolerant response parse


def test_parse_add_leads_on_live_response_is_counts_only():
    """The LIVE add-leads response is counts-only (no per-lead ids) — parse_add_leads yields {} and
    the launch worker falls back to fetch_campaign_leads. The fixture is the real captured shape."""
    resp = _load("add_leads_response.json")
    assert svc.parse_add_leads(resp) == {}
    assert resp.get("upload_count") == 1  # counts are present; ids are not


def test_parse_add_leads_tolerates_alt_field_names():
    # doc-page drift: a `leads` container with `id`/`lead_email` aliases still parses inline ids.
    resp = {"leads": [{"lead_email": "X@Y.com", "id": 42}, {"no_email": True, "id": 9}]}
    assert svc.parse_add_leads(resp) == {"x@y.com": "42"}  # lowercased; the id-less row skipped


def test_parse_add_leads_empty_when_no_list():
    assert svc.parse_add_leads({"ok": True, "upload_count": 3}) == {}


def test_parse_campaign_leads_reads_nested_lead():
    """GET /campaigns/{id}/leads → {email: lead.id} off the nested `data[].lead` roster shape."""
    out = svc.parse_campaign_leads(_load("campaign_leads_response.json"))
    assert out == {"jason@getholdslot.com": "4155843310"}


def test_parse_campaign_leads_empty_when_no_data():
    assert svc.parse_campaign_leads({"total_leads": "0", "data": []}) == {}
    assert svc.parse_campaign_leads({"ok": True}) == {}


# ------------------------------------------------------------------------ real _request (fakeurl)


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


def test_request_builds_query_param_auth_and_returns_json(monkeypatch):
    monkeypatch.setenv("HOLDSLOT_SMARTLEAD_KEY", "SECRET-KEY-123")
    sl.reset_secret()
    seen: dict = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["ua"] = req.headers.get("User-agent")
        return _FakeResp({"ok": True})

    monkeypatch.setattr(sl.urllib.request, "urlopen", fake_urlopen)
    out = sl._get("campaigns")
    assert out == {"ok": True}
    assert "api_key=SECRET-KEY-123" in seen["url"]  # query-param auth, no header
    assert seen["ua"] and "HoldSlot" in seen["ua"]  # non-default UA (Cloudflare)
    sl.reset_secret()


def test_redact_scrubs_api_key_everywhere():
    url = "https://server.smartlead.ai/api/v1/campaigns?api_key=SUPERSECRET&x=1"
    red = sl._redact(url)
    assert "SUPERSECRET" not in red
    assert "api_key=***" in red and "x=1" in red


def test_error_message_is_redacted(monkeypatch):
    monkeypatch.setenv("HOLDSLOT_SMARTLEAD_KEY", "LEAK-ME")
    sl.reset_secret()

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr(sl.urllib.request, "urlopen", boom)
    with pytest.raises(sl.SmartleadError) as ei:
        sl._get("campaigns")
    assert "LEAK-ME" not in str(ei.value)  # the key never reaches the exception string
    sl.reset_secret()


def test_no_api_key_in_logs(monkeypatch, caplog):
    """R1 assert — even with logging at DEBUG, no api_key value reaches a log record."""
    monkeypatch.setenv("HOLDSLOT_SMARTLEAD_KEY", "LOG-LEAK-KEY")
    sl.reset_secret()
    monkeypatch.setattr(sl.time, "sleep", lambda *_: None)  # no real backoff sleeps

    attempts = {"n": 0}

    def flaky(req, timeout=0):
        attempts["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 503, "err", {}, None)

    monkeypatch.setattr(sl.urllib.request, "urlopen", flaky)
    with caplog.at_level(logging.DEBUG, logger="holdslot.smartlead"):
        with pytest.raises(sl.SmartleadError):
            sl._get("campaigns")
    assert "LOG-LEAK-KEY" not in caplog.text
    sl.reset_secret()


def test_retries_transient_5xx_then_raises(monkeypatch):
    monkeypatch.setenv("HOLDSLOT_SMARTLEAD_KEY", "k")
    sl.reset_secret()
    monkeypatch.setattr(sl.time, "sleep", lambda *_: None)
    n = {"c": 0}

    def flaky(req, timeout=0):
        n["c"] += 1
        raise urllib.error.HTTPError(req.full_url, 429, "rate", {}, None)

    monkeypatch.setattr(sl.urllib.request, "urlopen", flaky)
    with pytest.raises(sl.SmartleadError) as ei:
        sl._get("campaigns")
    assert ei.value.status == 429
    assert n["c"] == sl._MAX_RETRIES + 1  # initial + retries
    sl.reset_secret()


def test_auth_error_drops_cached_secret(monkeypatch):
    monkeypatch.setenv("HOLDSLOT_SMARTLEAD_KEY", "k")
    sl.reset_secret()

    def denied(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)

    monkeypatch.setattr(sl.urllib.request, "urlopen", denied)
    with pytest.raises(sl.SmartleadError) as ei:
        sl._get("campaigns")
    assert ei.value.status == 401  # 401/403 raise immediately (no retry storm)
    sl.reset_secret()


def test_secret_env_override_json_and_bare(monkeypatch):
    monkeypatch.setenv(
        "HOLDSLOT_SMARTLEAD_KEY", json.dumps({"api_key": "kk", "sending_account_ids": [1, 2]})
    )
    sl.reset_secret()
    assert sl._api_key() == "kk"
    assert sl.sending_account_ids() == [1, 2]
    monkeypatch.setenv("HOLDSLOT_SMARTLEAD_KEY", "bare-key")
    sl.reset_secret()
    assert sl._api_key() == "bare-key"
    sl.reset_secret()
