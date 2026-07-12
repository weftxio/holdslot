"""Google transport (F2) — the six methods behind booking + meeting ingest.

Two Google surfaces, ONE adapter: **Calendar v3** (event + Meet create · free/busy) and **Meet REST
v2** (conference records — the held/duration evidence). Auth = **service-account JWT (RS256) +
domain-wide delegation** — no OAuth consent flow, no Google client library, stdlib `urllib`
transport
(the Smartlead/Apollo discipline: lazy / SnapStart-safe, no secret read or network at import).

Token flow (Google's service-account HTTP/REST doc; `verify_keys.google_access_token` is the working
reference, but it signs via an `openssl` subprocess — a script trick, not the app pattern): mint a
short-lived JWT (`iss=client_email · sub=delegated_subject · scope=<the two scopes> ·
aud=oauth2.googleapis.com/token · exp≤iat+3600`), sign RS256 with **pyjwt + cryptography** (the one
new
runtime dep, GR8), exchange it at `oauth2.googleapis.com/token` for a Bearer access token, cache it
module-level with an expiry refresh (~60s early — NEVER `@lru_cache`, tokens expire). The DWD grant
is
frozen to exactly two scopes (calendar + meetings.space.readonly) — adding any scope = founder admin
re-auth, GR1; don't. **Redaction is mandatory:** the token and `private_key` never reach a log or
exception (`_redact`, FT2-10). The six contract methods, nothing more (docs/initial-build-plan.md →
Phase F → Google API contract):

  access_token · create_event · get_event · freebusy · list_conference_records · list_participants
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
import uuid
from functools import lru_cache

import boto3
import jwt

log = logging.getLogger("holdslot.google")

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
MEET_BASE = "https://meet.googleapis.com/v2"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 — a public endpoint, not a secret
DEFAULT_TIMEOUT = 25  # seconds
USER_AGENT = "HoldSlot/1.0 (+https://tryholdslot.com)"
_RETRYABLE = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4

# The DWD grant is frozen to exactly these two scopes (GR1). Fallback subject = the known host seat.
DEFAULT_SUBJECT = "info@tryholdslot.com"
DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/meetings.space.readonly",
)

# The conference-create is async: statusCode walks pending → success. Re-read the event a bounded
# number of times before trusting hangoutLink / conferenceId (GR2).
_PENDING_RETRIES = 3
_PENDING_SLEEP = 1.0  # seconds between pending re-reads (monkeypatched to 0 in tests)

# Scrub any Bearer token / access_token / private_key fragment from a string before it reaches a log
# or exception (FT2-10). Belt-and-braces: we also simply never log the token or the SA.
_REDACT_RES = (
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r'("access_token"\s*:\s*")[^"]+'),
    re.compile(r'("private_key"\s*:\s*")[^"]+'),
    re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)[\s\S]+?(-----END [A-Z ]*PRIVATE KEY-----)"),
)


class GoogleError(RuntimeError):
    """A non-recoverable Google call (auth, exhausted retries, transport). Carries the HTTP status.
    Its message is always redacted — a token or private key must never reach an exception string."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(_redact(message))
        self.status = status


class GoogleCalendarUnavailable(GoogleError):
    """free/busy could not be read for the host calendar (a per-calendar `errors[]`, notFound…). The
    slot builder treats this as 'no availability' (offer no slots) — never a 500 (FT2-7 / FT3-9)."""


def _redact(text: str) -> str:
    out = text or ""
    for rx in _REDACT_RES:
        out = (
            rx.sub(lambda m: m.group(1) + "***", out) if rx.groups == 1 else rx.sub(r"\1***\2", out)
        )
    return out


@lru_cache(maxsize=1)
def _secret() -> dict:
    """Read `{prefix}/google` once and cache it. Accepts the planned envelope
    `{service_account_json, delegated_subject, scopes}` OR a raw service-account JSON (the
    `verify_keys.check_google` contract). `HOLDSLOT_GOOGLE_SA` env wins for local dev/tests (JSON).
    """
    if env := os.environ.get("HOLDSLOT_GOOGLE_SA"):
        return json.loads(env)
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    prefix = os.environ.get("HOLDSLOT_SECRETS_PREFIX", "holdslot/prod")
    sm = boto3.client("secretsmanager", region_name=region)
    raw = sm.get_secret_value(SecretId=f"{prefix}/google")["SecretString"]
    return json.loads(raw)


def _resolve_auth() -> tuple[dict, str, list[str]]:
    """→ (service_account_dict, delegated_subject, scopes). Both shapes, GR1 defaults."""
    sec = _secret()
    if sec.get("service_account_json"):
        sa = sec["service_account_json"]
        if isinstance(sa, str):
            sa = json.loads(sa)  # the SA nested as an escaped JSON string (common in the console)
        subject = sec.get("delegated_subject") or DEFAULT_SUBJECT
        scopes = sec.get("scopes") or list(DEFAULT_SCOPES)
    elif sec.get("client_email") and sec.get("private_key"):
        sa, subject, scopes = sec, DEFAULT_SUBJECT, list(DEFAULT_SCOPES)
    else:
        raise GoogleError("google secret shape: need service_account_json envelope or raw SA JSON")
    if not (sa.get("client_email") and sa.get("private_key")):
        raise GoogleError("google service-account JSON missing client_email / private_key")
    return sa, subject, scopes


# --------------------------------------------------------------------------- delegated access token

_token_lock = threading.Lock()
_token: dict = {
    "value": None,
    "expires_at": 0.0,
}  # module-level cache (NOT lru_cache — tokens expire)


def _mint_token() -> tuple[str, float]:
    """Sign the DWD JWT (RS256, pyjwt+cryptography) → a Bearer access token. Returns
    (token, monotonic_expiry). Never logs the JWT/token; a token-endpoint failure is redacted."""
    sa, subject, scopes = _resolve_auth()
    iat = int(time.time()) - 60  # backdate 60s so a slightly-fast clock isn't rejected
    claims = {
        "iss": sa["client_email"],
        "sub": subject,
        "scope": " ".join(scopes),
        "aud": TOKEN_URL,
        "iat": iat,
        "exp": iat + 3600,  # Google's hard max: exp ≤ iat + 1h
    }
    assertion = jwt.encode(claims, sa["private_key"], algorithm="RS256")
    body = urllib.parse.urlencode(
        {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
        method="POST",
    )
    for attempt in range(_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as r:
                payload = json.loads(r.read().decode())
            break
        except urllib.error.HTTPError as e:
            if e.code in _RETRYABLE and attempt < _MAX_RETRIES:
                time.sleep(0.5 * (2**attempt))
                continue
            raise GoogleError(f"google token endpoint HTTP {e.code}", status=e.code) from e
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < _MAX_RETRIES:
                time.sleep(0.5 * (2**attempt))
                continue
            raise GoogleError("google token endpoint transport error") from e
    token = payload.get("access_token")
    if not token:
        raise GoogleError("google token endpoint returned no access_token")
    expires_in = int(payload.get("expires_in", 3600))
    return token, time.monotonic() + expires_in - 60  # refresh 60s early


def access_token(*, force: bool = False) -> str:
    """The cached delegated Bearer token, minted (and re-minted on expiry / `force`) on demand."""
    with _token_lock:
        if force or not _token["value"] or time.monotonic() >= _token["expires_at"]:
            _token["value"], _token["expires_at"] = _mint_token()
        return _token["value"]


def reset_secret() -> None:
    """Drop the cached secret AND token (tests / a rotated secret)."""
    _secret.cache_clear()
    with _token_lock:
        _token["value"], _token["expires_at"] = None, 0.0


# --------------------------------------------------------------------------- transport


def _request(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """One Bearer-authed request, retried on transient 429/5xx with exponential backoff. A 401 drops
    the cached token and replays ONCE with a fresh mint (no retry storm, FT2-4). All error paths are
    redacted so a token never leaks into a log or exception."""
    data = json.dumps(body).encode() if body is not None else None
    reminted = False
    for attempt in range(_MAX_RETRIES + 1):
        headers = {
            "Authorization": f"Bearer {access_token()}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode()
                return json.loads(text) if text.strip() else {}
        except urllib.error.HTTPError as e:
            if e.code == 401 and not reminted:
                access_token(force=True)  # drop + re-mint once, then replay
                reminted = True
                continue
            if e.code in _RETRYABLE and attempt < _MAX_RETRIES:
                time.sleep(0.5 * (2**attempt))
                continue
            detail = _http_error_detail(e)
            raise GoogleError(f"google HTTP {e.code}{detail}", status=e.code) from e
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < _MAX_RETRIES:
                time.sleep(0.5 * (2**attempt))
                continue
            raise GoogleError("google transport error") from e
    raise GoogleError("google exhausted retries")  # unreachable


def _http_error_detail(e: urllib.error.HTTPError) -> str:
    """A short, redacted reason string off an error body (never the token/key)."""
    try:
        msg = json.loads(e.read().decode()).get("error", {})
        reason = msg.get("message") if isinstance(msg, dict) else str(msg)
        return f": {_redact(str(reason))[:160]}" if reason else ""
    except Exception:  # noqa: BLE001 — the detail is best-effort; never mask the real error
        return ""


# --------------------------------------------------------------------------- the six methods


def create_event(
    *,
    summary: str,
    start: str,
    end: str,
    timezone: str,
    attendees: list[str],
    description: str = "",
    request_id: str | None = None,
) -> dict:
    """`POST /calendars/primary/events?conferenceDataVersion=1&sendUpdates=all` — create on
    the impersonated host seat's calendar with a Meet conference; `sendUpdates=all` makes Google
    send invites to `attendees` (populating attendees REQUIRES DWD — we always impersonate).

    `start`/`end` are RFC3339 instants. Returns the final event — if the conference create comes
    back `pending`, this re-reads via `get_event` (≤3) until `success`, else raises (GR2). Read
    `id`/`hangoutLink` and `meeting_code_of(event)` (== `conferenceData.conferenceId`) off it.
    """
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start, "timeZone": timezone},
        "end": {"dateTime": end, "timeZone": timezone},
        "attendees": [{"email": a} for a in attendees],
        "conferenceData": {
            "createRequest": {
                "requestId": request_id or str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }
    url = f"{CALENDAR_BASE}/calendars/primary/events?conferenceDataVersion=1&sendUpdates=all"
    event = _request("POST", url, body=body)
    return _resolve_pending(event)


def _resolve_pending(event: dict) -> dict:
    """Re-read the event until its conference `statusCode` is `success` (bounded, GR2)."""
    for _ in range(_PENDING_RETRIES):
        status = (event.get("conferenceData", {}).get("status") or {}).get("statusCode")
        if status != "pending":
            return event  # success (or no async conference at all)
        time.sleep(_PENDING_SLEEP)
        event = get_event(event["id"])
    status = (event.get("conferenceData", {}).get("status") or {}).get("statusCode")
    if status == "pending":
        raise GoogleError("google conference create still pending after bounded re-reads")
    return event


def get_event(event_id: str) -> dict:
    """`GET /calendars/primary/events/{eventId}` — the pending re-read (+ a general fetch)."""
    return _request(
        "GET", f"{CALENDAR_BASE}/calendars/primary/events/{urllib.parse.quote(event_id)}"
    )


def freebusy(time_min: str, time_max: str, *, subject: str | None = None) -> list[dict]:
    """`POST /freeBusy` → the host seat's busy intervals `[{start, end}]` (start inclusive, end
    exclusive) across `[time_min, time_max]` (RFC3339). A per-calendar `errors[]` raises
    `GoogleCalendarUnavailable` — the slot builder maps that to 'no slots', never a 500 (FT2-7)."""
    subj = subject or _resolve_auth()[1]
    body = {"timeMin": time_min, "timeMax": time_max, "timeZone": "UTC", "items": [{"id": subj}]}
    resp = _request("POST", f"{CALENDAR_BASE}/freeBusy", body=body)
    cal = (resp.get("calendars") or {}).get(subj) or {}
    if cal.get("errors"):
        raise GoogleCalendarUnavailable(f"freebusy calendar error for host seat: {cal['errors']}")
    return list(cal.get("busy") or [])


def list_conference_records(meeting_code: str) -> list[dict]:
    """`GET meet/v2/conferenceRecords?filter=space.meeting_code = "…"` → the records for a Meet code
    (`startTime` always set; `endTime` unset while ongoing; a record exists iff someone joined)."""
    q = urllib.parse.urlencode({"filter": f'space.meeting_code = "{meeting_code}"'})
    resp = _request("GET", f"{MEET_BASE}/conferenceRecords?{q}")
    return list(resp.get("conferenceRecords") or [])


def list_participants(record_id: str) -> list[dict]:
    """`GET meet/v2/conferenceRecords/{id}/participants` → the join evidence (each carries
    `earliestStartTime` / `latestEndTime` + the signedin/anonymous/phone user union)."""
    name = (
        record_id
        if record_id.startswith("conferenceRecords/")
        else f"conferenceRecords/{record_id}"
    )
    resp = _request("GET", f"{MEET_BASE}/{name}/participants")
    return list(resp.get("participants") or [])


__all__ = [
    "access_token",
    "create_event",
    "get_event",
    "freebusy",
    "list_conference_records",
    "list_participants",
    "reset_secret",
    "GoogleError",
    "GoogleCalendarUnavailable",
    "CALENDAR_BASE",
    "MEET_BASE",
    "TOKEN_URL",
    "DEFAULT_SCOPES",
    "DEFAULT_SUBJECT",
]
