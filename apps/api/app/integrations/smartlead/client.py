"""Smartlead transport (E2) — the eleven live methods behind the outreach loop.

Mirrors the Apollo/OpenRouter discipline: **lazy / SnapStart-safe** (no secret read, no network at
import — the secret loads on first use and is cached), stdlib `urllib` (no runtime HTTP dep),
client-side throttle + bounded 429/5xx backoff. The map/parse of request+response lives in the pure
`domains/campaigns/service.py`; this layer is transport only.

**Auth is a query-param** — `?api_key=…` (Smartlead offers no header option, verified 2026-07-11).
That makes redaction mandatory: `_redact()` scrubs the key from every URL before it reaches a log,
telemetry, or exception string (risk R1, assert-tested in `test_smartlead.py`). Smartlead is
Cloudflare-fronted and 403s the default urllib User-Agent, so every request sends a real UA.

Rate limit is ~10 requests / 2 s → a client-side sliding-window throttle gates every call, and 429
(or a transient 5xx) is retried with exponential backoff. The eleven contract methods, nothing more
(docs/initial-build-plan.md → Phase E → Smartlead API contract):

  create_campaign · update_schedule · update_settings · save_sequences · add_email_accounts ·
  add_leads · set_status · register_webhook · reply_to_thread · fetch_analytics/fetch_statistics ·
  fetch_inbox_replies  (+ list_email_accounts, the one-shot lookup resolving sending-account ids).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from functools import lru_cache

import boto3

log = logging.getLogger("holdslot.smartlead")

BASE_URL = "https://server.smartlead.ai/api/v1"
DEFAULT_TIMEOUT = 25  # seconds
# Cloudflare 403s the stdlib urllib UA — send a real one (the verify_keys.py lesson).
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) HoldSlot/1.0"
_RETRYABLE = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4

# Rate limit: ~10 requests / 2 s. A sliding-window throttle keeps us safely under it; 429 backoff is
# the belt to this braces. Slightly conservative (9/2s) to leave headroom for clock jitter.
_RATE_MAX = 9
_RATE_WINDOW = 2.0
_recent: deque[float] = deque()
_rate_lock = threading.Lock()

# api_key=<value> up to the next & or end-of-string — scrubbed before any log/exception.
_KEY_RE = re.compile(r"(api_key=)[^&\s]+")


class SmartleadError(RuntimeError):
    """A non-recoverable Smartlead call (bad key, exhausted retries, transport). Carries the status.
    Its message is always redacted — a raw URL carrying `api_key` must never reach an exception."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(_redact(message))
        self.status = status


def _redact(text: str) -> str:
    """Scrub `api_key=…` from any string (URL, log line, exception) → `api_key=***`. The single
    control that keeps the query-param key out of logs/telemetry (R1)."""
    return _KEY_RE.sub(r"\1***", text or "")


@lru_cache(maxsize=1)
def _secret() -> dict:
    """Read `{prefix}/smartlead` once and cache it: `{api_key, webhook_path_token,
    sending_account_ids}`. `HOLDSLOT_SMARTLEAD_KEY` env wins for local dev / tests (JSON or a bare
    key), so a swap needs no Secrets Manager round-trip."""
    if env := os.environ.get("HOLDSLOT_SMARTLEAD_KEY"):
        try:
            parsed = json.loads(env)
            return parsed if isinstance(parsed, dict) else {"api_key": env}
        except json.JSONDecodeError:
            return {"api_key": env}
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    prefix = os.environ.get("HOLDSLOT_SECRETS_PREFIX", "holdslot/prod")
    sm = boto3.client("secretsmanager", region_name=region)
    raw = sm.get_secret_value(SecretId=f"{prefix}/smartlead")["SecretString"]
    return json.loads(raw)


def _api_key() -> str:
    key = _secret().get("api_key")
    if not key:
        raise SmartleadError("smartlead secret missing api_key")
    return str(key)


def sending_account_ids() -> list[int]:
    """The numeric sending-inbox ids the launch worker adds to a campaign (from the secret)."""
    raw = _secret().get("sending_account_ids") or []
    if not isinstance(raw, list):
        raw = [raw]
    return [int(x) for x in raw]


def webhook_path_token() -> str | None:
    """The high-entropy `{token}` segment of the inbound webhook route (auth; no HMAC exists)."""
    tok = _secret().get("webhook_path_token")
    return str(tok) if tok else None


def reset_secret() -> None:
    _secret.cache_clear()


def _throttle() -> None:
    """Block until a slot frees in the sliding window (≤ `_RATE_MAX` per `_RATE_WINDOW` seconds)."""
    while True:
        with _rate_lock:
            now = time.monotonic()
            while _recent and now - _recent[0] >= _RATE_WINDOW:
                _recent.popleft()
            if len(_recent) < _RATE_MAX:
                _recent.append(now)
                return
            wait = _RATE_WINDOW - (now - _recent[0])
        time.sleep(max(wait, 0.01))


def _url(path: str, query: dict | None = None) -> str:
    """Build the full URL with the api_key query param (+ any extra query) baked in."""
    params = {"api_key": _api_key(), **(query or {})}
    return f"{BASE_URL}/{path}?{urllib.parse.urlencode(params)}"


def _request(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    query: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict | list:
    """One request (POST/GET with `?api_key=`), throttled + retried on transient 429/5xx with
    exponential backoff. Auth errors (401/403) drop the cached secret and raise immediately. All
    error paths go through `_redact` so the key never leaks into a log or exception."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    url = _url(path, query)
    for attempt in range(_MAX_RETRIES + 1):
        _throttle()
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode()
                return json.loads(text) if text.strip() else {}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                reset_secret()
                raise SmartleadError(f"smartlead auth error (HTTP {e.code})", status=e.code) from e
            if e.code in _RETRYABLE and attempt < _MAX_RETRIES:
                time.sleep(0.5 * (2**attempt))  # 0.5, 1, 2, 4s
                continue
            raise SmartleadError(f"smartlead HTTP {e.code} on {path}", status=e.code) from e
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < _MAX_RETRIES:
                time.sleep(0.5 * (2**attempt))
                continue
            raise SmartleadError(f"smartlead transport error on {path}: {e}") from e
    raise SmartleadError(f"smartlead exhausted retries on {path}")  # unreachable


def _post(path: str, body: dict, *, timeout: int = DEFAULT_TIMEOUT) -> dict | list:
    return _request("POST", path, body=body, timeout=timeout)


def _get(path: str, query: dict | None = None, *, timeout: int = DEFAULT_TIMEOUT) -> dict | list:
    return _request("GET", path, query=query, timeout=timeout)


# --------------------------------------------------------------------------- the eleven methods


def create_campaign(name: str, client_id: int | None = None) -> dict:
    """`POST /campaigns/create` → `{ok, id}`. A fresh campaign can't send until sequences + accounts
    + leads exist. `client_id` is Smartlead's optional sub-client (unused single-tenant)."""
    body: dict = {"name": name}
    if client_id is not None:
        body["client_id"] = client_id
    return _post("campaigns/create", body)  # type: ignore[return-value]


def update_schedule(campaign_id: str | int, schedule: dict) -> dict:
    """`POST /campaigns/{id}/schedule` — timezone · days_of_the_week[] · start_hour/end_hour ·
    min_time_btw_emails · **max_new_leads_per_day** (the EF-Q3 daily cap). Body passed through as
    built by the launch worker (EF-Q4 prospect-local window)."""
    return _post(f"campaigns/{campaign_id}/schedule", schedule)  # type: ignore[return-value]


def update_settings(campaign_id: str | int, settings: dict) -> dict:
    """`POST /campaigns/{id}/settings` — tracking / stop-on-reply / unsubscribe text."""
    return _post(f"campaigns/{campaign_id}/settings", settings)  # type: ignore[return-value]


def save_sequences(campaign_id: str | int, sequences: list[dict]) -> dict:
    """`POST /campaigns/{id}/sequences` — the A/B/C sequence copy. A blank follow-up `subject` =
    same-thread "Re:". Sequences are LOCKED while the campaign is ACTIVE (push before start)."""
    return _post(f"campaigns/{campaign_id}/sequences", {"sequences": sequences})  # type: ignore[return-value]


def add_email_accounts(campaign_id: str | int, email_account_ids: list[int]) -> dict:
    """`POST /campaigns/{id}/email-accounts` — attach the warmed sending inboxes (the numeric ids
    from the secret's `sending_account_ids`)."""
    return _post(  # type: ignore[return-value]
        f"campaigns/{campaign_id}/email-accounts", {"email_account_ids": email_account_ids}
    )


def add_leads(campaign_id: str | int, lead_list: list[dict], settings: dict | None = None) -> dict:
    """`POST /campaigns/{id}/leads` — ≤ 400 leads/req. **Every `ignore_*` flag stays false** (the
    Smartlead global block + unsubscribe lists are a compliance floor, never bypassed).

    **The live API returns COUNTS ONLY** — `{upload_count, block_count, duplicate_count,
    unsubscribed_leads, invalid_emails, …}`, no per-lead ids, and it **rejects a top-level
    `return_lead_ids`** (`400 "not allowed"`, verified live 2026-07-11 by `e_smoke_live.py`). The
    launch worker resolves `email → smartlead_lead_id` afterwards via `fetch_campaign_leads`."""
    # The compliance floor is NON-overridable: caller settings are applied first, then every
    # `ignore_*` flag is hard-set false so no code path can bypass Smartlead's global block /
    # unsubscribe / bounce lists (the SG-PDPA suppression floor).
    body_settings = {
        **(settings or {}),
        "ignore_global_block_list": False,
        "ignore_unsubscribe_list": False,
        "ignore_community_bounce_list": False,
        "ignore_duplicate_leads_in_other_campaign": False,
    }
    return _post(  # type: ignore[return-value]
        f"campaigns/{campaign_id}/leads",
        {"lead_list": lead_list, "settings": body_settings},
    )


def fetch_campaign_leads(campaign_id: str | int, *, offset: int = 0, limit: int = 100) -> dict:
    """`GET /campaigns/{id}/leads` — per-lead roster `{total_leads, data:[{lead:{id,email}}]}`. The
    launch worker's `email → smartlead_lead_id` resolver (the add-leads response carries no ids);
    `lead.id` is the handle the webhook `lead_id` + `reply_to_thread` use (verified 2026-07-11)."""
    return _get(  # type: ignore[return-value]
        f"campaigns/{campaign_id}/leads", {"offset": offset, "limit": limit}
    )


def set_status(campaign_id: str | int, status: str) -> dict:
    """`POST /campaigns/{id}/status` — start / pause / resume (Smartlead expects UPPERCASE:
    `START` / `PAUSED`). The exact enum casing is an E0-probe ⚠; the constants below encode it."""
    return _post(f"campaigns/{campaign_id}/status", {"status": status})  # type: ignore[return-value]


# Smartlead's seven standard lead categories. The webhook API REQUIRES a non-empty `categories`
# (400 `"categories" does not contain 1 required value(s)` otherwise, verified live 2026-07-11) —
# subscribing to all of them means no lead's events are filtered out.
DEFAULT_WEBHOOK_CATEGORIES = [
    "Interested",
    "Meeting Request",
    "Not Interested",
    "Do Not Contact",
    "Information Request",
    "Out Of Office",
    "Wrong Person",
]


def register_webhook(
    campaign_id: str | int,
    *,
    name: str,
    webhook_url: str,
    event_types: list[str],
    categories: list[str] | None = None,
) -> dict:
    """`POST /campaigns/{id}/webhooks` — subscribe our ingest route to the campaign's events. The
    accepted event-type strings drift across Smartlead's docs (E0-probe ⚠); ingest normalizes.
    `categories` is REQUIRED non-empty by the live API — defaults to all seven standard lead
    categories so every lead's events fire."""
    return _post(  # type: ignore[return-value]
        f"campaigns/{campaign_id}/webhooks",
        {
            "id": None,
            "name": name,
            "webhook_url": webhook_url,
            "event_types": event_types,
            "categories": categories or DEFAULT_WEBHOOK_CATEGORIES,
        },
    )


def reply_to_thread(
    campaign_id: str | int,
    *,
    email_stats_id: str,
    email_body: str,
    lead_id: str | int | None = None,
    reply_message_id: str | None = None,
    reply_email_time: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict:
    """`POST /campaigns/{id}/reply-email-thread` — the E5 respond door + the F3 booking-link
    carrier. `lead_id`/`email_stats_id`/`reply_message_id` are read off the stored `outreach_event`
    row + its `campaign_lead` (the R4 two-path plan makes E5 source-agnostic)."""
    body: dict = {"email_stats_id": email_stats_id, "email_body": email_body}
    if lead_id is not None:
        body["lead_id"] = lead_id
    if reply_message_id:
        body["reply_message_id"] = reply_message_id
    if reply_email_time:
        body["reply_email_time"] = reply_email_time
    if cc:
        body["cc"] = cc
    if bcc:
        body["bcc"] = bcc
    return _post(f"campaigns/{campaign_id}/reply-email-thread", body)  # type: ignore[return-value]


def fetch_analytics(campaign_id: str | int) -> dict:
    """`GET /campaigns/{id}/analytics` — top-level campaign metrics (the E6 on-read poll)."""
    return _get(f"campaigns/{campaign_id}/analytics")  # type: ignore[return-value]


def fetch_statistics(campaign_id: str | int, *, offset: int = 0, limit: int = 100) -> dict:
    """`GET /campaigns/{id}/statistics` — per-lead rows (the followup fallback + webhook-drift
    check)."""
    return _get(  # type: ignore[return-value]
        f"campaigns/{campaign_id}/statistics", {"offset": offset, "limit": limit}
    )


def fetch_inbox_replies(
    campaign_id: str | int | None = None, *, offset: int = 0, limit: int = 20
) -> dict:
    """`POST /master-inbox/inbox-replies` — the R4-b recovery path for a missing reply handle:
    `fetch_message_history=true` returns per-message ids + `message_history[]` with direction."""
    body: dict = {"offset": offset, "limit": min(limit, 20)}
    if campaign_id is not None:
        body["campaign_id"] = campaign_id
    return _request(  # type: ignore[return-value]
        "POST", "master-inbox/inbox-replies", body=body, query={"fetch_message_history": "true"}
    )


def list_email_accounts() -> list:
    """`GET /email-accounts` — resolve/verify the sending-inbox ids once (E0 + launch preflight)."""
    return _get("email-accounts", {"offset": 0, "limit": 100})  # type: ignore[return-value]


# Smartlead status enum (E0-probe pins the exact casing; encoded once here so callers use the name).
STATUS_START = "START"
STATUS_PAUSED = "PAUSED"


__all__ = [
    "create_campaign",
    "update_schedule",
    "update_settings",
    "save_sequences",
    "add_email_accounts",
    "add_leads",
    "set_status",
    "register_webhook",
    "reply_to_thread",
    "fetch_analytics",
    "fetch_statistics",
    "fetch_inbox_replies",
    "fetch_campaign_leads",
    "list_email_accounts",
    "sending_account_ids",
    "webhook_path_token",
    "reset_secret",
    "SmartleadError",
    "BASE_URL",
    "STATUS_START",
    "STATUS_PAUSED",
]
