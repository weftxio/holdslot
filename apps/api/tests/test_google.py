"""F2 unit tests — the Google adapter (mocked transport; no network, no real key, no Google calls).

Two layers, the `test_smartlead.py` pattern:
  * the six methods map to their exact URL + query + body (mock `_request`);
  * the real `_request`/`_mint_token` are exercised against a fake `urlopen` to pin the JWT claims,
    the token cache, the 401 re-mint, the 429/5xx backoff, and the R1-style redaction (no token /
    private_key in any log or exception string).
All response shapes are the `tests/fixtures/google/` fixtures — the F2 live-probe overwrites them
with the real captured shapes, but doc-built shapes let every logic branch run offline.
"""

from __future__ import annotations

import json
import logging
import urllib.error
from pathlib import Path

import jwt
import pytest

from app.integrations.google import client as g

_FIX = Path(__file__).resolve().parent / "fixtures" / "google"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text())


def _sa_env(monkeypatch) -> dict:
    """Point the adapter at the throwaway test service account (the generated RSA key)."""
    sec = _load("service_account_test.json")
    monkeypatch.setenv("HOLDSLOT_GOOGLE_SA", json.dumps(sec))
    g.reset_secret()
    return sec


# --------------------------------------------------------------------------- method → url/body


def _capture(monkeypatch, ret=None):
    calls: list[dict] = []

    def fake(method, url, *, body=None, timeout=g.DEFAULT_TIMEOUT):
        calls.append({"method": method, "url": url, "body": body})
        return ret if ret is not None else {}

    monkeypatch.setattr(g, "_request", fake)
    return calls


def test_create_event_url_and_body(monkeypatch):
    calls = _capture(monkeypatch, ret=_load("event_insert_response.json"))
    out = g.create_event(
        summary="HoldSlot × Prospect",
        start="2026-07-15T10:00:00Z",
        end="2026-07-15T10:30:00Z",
        timezone="UTC",
        attendees=["buyer@prospect.com", "founder@getholdslot.com"],
        request_id="req-1",
    )
    c = calls[0]
    assert c["method"] == "POST"
    # FT2-5 — conferenceDataVersion=1 + sendUpdates=all in the query.
    assert (
        c["url"]
        == f"{g.CALENDAR_BASE}/calendars/primary/events?conferenceDataVersion=1&sendUpdates=all"
    )
    b = c["body"]
    assert b["start"] == {"dateTime": "2026-07-15T10:00:00Z", "timeZone": "UTC"}
    assert b["end"] == {"dateTime": "2026-07-15T10:30:00Z", "timeZone": "UTC"}
    assert b["attendees"] == [{"email": "buyer@prospect.com"}, {"email": "founder@getholdslot.com"}]
    cr = b["conferenceData"]["createRequest"]
    assert cr["requestId"] == "req-1"
    assert cr["conferenceSolutionKey"] == {"type": "hangoutsMeet"}
    # FT2-6 — response parse fields present on the returned event.
    assert out["id"] == "evt_abc123"
    assert out["hangoutLink"] == "https://meet.google.com/abc-defg-hij"
    assert out["conferenceData"]["conferenceId"] == "abc-defg-hij"
    assert out["conferenceData"]["status"]["statusCode"] == "success"


def test_create_event_generates_request_id_when_absent(monkeypatch):
    calls = _capture(monkeypatch, ret=_load("event_insert_response.json"))
    g.create_event(summary="x", start="s", end="e", timezone="UTC", attendees=["a@b.com"])
    rid = calls[0]["body"]["conferenceData"]["createRequest"]["requestId"]
    assert rid and len(rid) >= 8  # a uuid4 idempotency key


def test_create_event_pending_reread_until_success(monkeypatch):
    """FT2-6 — a `pending` conference create re-reads via get_event (≤3) until `success`."""
    monkeypatch.setattr(g.time, "sleep", lambda *_: None)
    seq = [
        _load("event_insert_pending.json"),
        _load("event_insert_pending.json"),
        _load("event_insert_response.json"),
    ]
    urls: list[str] = []

    def fake(method, url, *, body=None, timeout=g.DEFAULT_TIMEOUT):
        urls.append(url)
        return seq[len(urls) - 1]

    monkeypatch.setattr(g, "_request", fake)
    out = g.create_event(summary="x", start="s", end="e", timezone="UTC", attendees=["a@b.com"])
    assert out["conferenceData"]["status"]["statusCode"] == "success"
    assert urls[0].endswith("events?conferenceDataVersion=1&sendUpdates=all")
    assert urls[1].endswith("/events/evt_abc123")  # get_event re-read


def test_create_event_still_pending_raises(monkeypatch):
    monkeypatch.setattr(g.time, "sleep", lambda *_: None)

    def fake(method, url, *, body=None, timeout=g.DEFAULT_TIMEOUT):
        return _load("event_insert_pending.json")

    monkeypatch.setattr(g, "_request", fake)
    with pytest.raises(g.GoogleError):
        g.create_event(summary="x", start="s", end="e", timezone="UTC", attendees=["a@b.com"])


def test_get_event_url(monkeypatch):
    calls = _capture(monkeypatch, ret={"id": "evt_abc123"})
    g.get_event("evt_abc123")
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == f"{g.CALENDAR_BASE}/calendars/primary/events/evt_abc123"


def test_freebusy_body_and_busy_parse(monkeypatch):
    """FT2-7 — freeBusy body pin + busy[] parse."""
    _sa_env(monkeypatch)
    calls = _capture(monkeypatch, ret=_load("freebusy_response.json"))
    busy = g.freebusy("2026-07-15T00:00:00Z", "2026-07-20T00:00:00Z")
    c = calls[0]
    assert c["method"] == "POST" and c["url"] == f"{g.CALENDAR_BASE}/freeBusy"
    assert c["body"]["timeZone"] == "UTC"
    assert c["body"]["items"] == [{"id": "info@tryholdslot.com"}]
    assert busy[0] == {"start": "2026-07-15T14:00:00Z", "end": "2026-07-15T15:00:00Z"}
    assert len(busy) == 2


def test_freebusy_calendar_error_is_typed(monkeypatch):
    """FT2-7 — a per-calendar errors[] raises typed GoogleCalendarUnavailable, not a KeyError."""
    _sa_env(monkeypatch)
    _capture(monkeypatch, ret=_load("freebusy_error_response.json"))
    with pytest.raises(g.GoogleCalendarUnavailable):
        g.freebusy("2026-07-15T00:00:00Z", "2026-07-20T00:00:00Z")


def test_list_conference_records_filter_and_parse(monkeypatch):
    """FT2-8 — meeting-code filter URL-encoded + records parse; ongoing (endTime absent) handled."""
    calls = _capture(monkeypatch, ret=_load("conference_records_response.json"))
    recs = g.list_conference_records("abc-defg-hij")
    url = calls[0]["url"]
    assert url.startswith(f"{g.MEET_BASE}/conferenceRecords?")
    assert "filter=space.meeting_code" in url and "abc-defg-hij" in url
    assert recs[0]["name"] == "conferenceRecords/rec_xyz"
    assert recs[0]["endTime"] == "2026-07-15T10:47:00Z"
    # ongoing fixture: endTime absent, no crash
    _capture(monkeypatch, ret=_load("conference_records_ongoing.json"))
    ongoing = g.list_conference_records("abc-defg-hij")
    assert "endTime" not in ongoing[0]


def test_list_participants_parse(monkeypatch):
    """FT2-9 — participants parse incl. the three user-union arms."""
    calls = _capture(monkeypatch, ret=_load("participants_response.json"))
    ps = g.list_participants("conferenceRecords/rec_xyz")
    assert calls[0]["url"] == f"{g.MEET_BASE}/conferenceRecords/rec_xyz/participants"
    assert len(ps) == 2
    assert ps[0]["earliestStartTime"] and ps[0]["latestEndTime"]
    assert "signedinUser" in ps[0]
    # bare id (no prefix) is normalized to the conferenceRecords/{id} path.
    _capture(monkeypatch, ret=_load("participants_response.json"))
    g.list_participants("rec_xyz")


# --------------------------------------------------------------------------- token flow (fakeurl)


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


def test_jwt_claims_pin(monkeypatch):
    """FT2-1/2 — the assertion carries the right iss/sub/scope/aud/exp; the token POST body pins the
    grant_type + assertion, and the response's access_token parses + caches."""
    sec = _sa_env(monkeypatch)
    sa = sec["service_account_json"]
    seen: dict = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["body"] = req.data.decode()
        return _FakeResp(_load("token_response.json"))

    monkeypatch.setattr(g.urllib.request, "urlopen", fake_urlopen)
    tok = g.access_token()
    assert tok == "ya29.TEST-ACCESS-TOKEN-do-not-log"
    assert seen["url"] == g.TOKEN_URL
    assert "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer" in seen["body"]
    assert "assertion=" in seen["body"]
    # decode the assertion (verify the RS256 signature with the test public key).
    from urllib.parse import parse_qs

    assertion = parse_qs(seen["body"])["assertion"][0]
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        load_pem_private_key,
    )

    pub_pem = (
        load_pem_private_key(sa["private_key"].encode(), password=None)
        .public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )
    claims = jwt.decode(
        assertion,
        pub_pem,
        algorithms=["RS256"],
        audience=g.TOKEN_URL,
        options={"verify_aud": True},
    )
    assert claims["iss"] == sa["client_email"]
    assert claims["sub"] == "info@tryholdslot.com"
    assert claims["scope"] == " ".join(sec["scopes"])
    assert claims["aud"] == g.TOKEN_URL
    assert claims["exp"] - claims["iat"] <= 3600
    g.reset_secret()


def test_token_cache_reuses_then_refreshes(monkeypatch):
    """FT2-3 — a 2nd call inside expiry does NO 2nd token POST; a forced expiry re-mints."""
    _sa_env(monkeypatch)
    posts = {"n": 0}

    def fake_urlopen(req, timeout=0):
        posts["n"] += 1
        return _FakeResp(_load("token_response.json"))

    monkeypatch.setattr(g.urllib.request, "urlopen", fake_urlopen)
    g.access_token()
    g.access_token()  # cached — no 2nd POST
    assert posts["n"] == 1
    g.access_token(force=True)  # re-mint
    assert posts["n"] == 2
    g.reset_secret()


def test_401_at_api_call_remints_once_then_raises(monkeypatch):
    """FT2-4 — a 401 drops the token + replays once with a fresh mint; a persistent 401 raises (no
    retry storm)."""
    _sa_env(monkeypatch)
    forces = {"n": 0}

    def mock_at(*, force=False):
        if force:
            forces["n"] += 1
        return "tok"

    monkeypatch.setattr(g, "access_token", mock_at)
    attempts = {"n": 0}

    def always_401(req, timeout=0):
        attempts["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr(g.urllib.request, "urlopen", always_401)
    with pytest.raises(g.GoogleError) as ei:
        g._request("GET", f"{g.CALENDAR_BASE}/calendars/primary/events/x")
    assert ei.value.status == 401
    assert forces["n"] == 1  # exactly ONE forced re-mint (no retry storm)
    assert attempts["n"] == 2  # the original call + exactly one replay
    g.reset_secret()


def test_backoff_bounded_on_5xx(monkeypatch):
    """FT2-11 — 5xx retries with exponential backoff, bounded to _MAX_RETRIES+1 attempts, then
    raises."""
    _sa_env(monkeypatch)
    monkeypatch.setattr(g, "access_token", lambda *, force=False: "tok")
    monkeypatch.setattr(g.time, "sleep", lambda *_: None)
    attempts = {"n": 0}

    def flaky(req, timeout=0):
        attempts["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 503, "err", {}, None)

    monkeypatch.setattr(g.urllib.request, "urlopen", flaky)
    with pytest.raises(g.GoogleError) as ei:
        g._request("GET", f"{g.MEET_BASE}/conferenceRecords")
    assert ei.value.status == 503
    assert attempts["n"] == g._MAX_RETRIES + 1
    g.reset_secret()


def test_redaction_no_token_or_key_in_logs_or_errors(monkeypatch, caplog):
    """FT2-10 [compliance] — no access_token / private_key fragment reaches a log/exception."""
    sec = _sa_env(monkeypatch)
    private_key = sec["service_account_json"]["private_key"]
    caplog.set_level(logging.DEBUG, logger="holdslot.google")

    def fake_urlopen(req, timeout=0):
        return _FakeResp(_load("token_response.json"))

    monkeypatch.setattr(g.urllib.request, "urlopen", fake_urlopen)
    g.access_token()
    # nothing logs the token or the key.
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "ya29." not in joined
    assert "PRIVATE KEY" not in joined
    # the redactor scrubs a Bearer/token/private_key echo.
    red = g._redact(f"Authorization: Bearer {'ya29.SECRET'} body {private_key[:80]}")
    assert "ya29.SECRET" not in red and "Bearer ***" in red
    err = g.GoogleError(f"boom access_token leak {'{'}\"access_token\": \"ya29.LEAK\"{'}'}")
    assert "ya29.LEAK" not in str(err)
    g.reset_secret()


def test_secret_shapes_env_wins_and_both_parse(monkeypatch):
    """FT2-12 — HOLDSLOT_GOOGLE_SA env wins; both the envelope and a raw SA JSON resolve."""
    envelope = _load("service_account_test.json")
    monkeypatch.setenv("HOLDSLOT_GOOGLE_SA", json.dumps(envelope))
    g.reset_secret()
    sa, subject, scopes = g._resolve_auth()
    assert subject == "info@tryholdslot.com"
    assert len(scopes) == 2 and sa["client_email"].endswith("gserviceaccount.com")
    # raw SA JSON (no envelope) → default subject + the two frozen scopes.
    raw = envelope["service_account_json"]
    monkeypatch.setenv("HOLDSLOT_GOOGLE_SA", json.dumps(raw))
    g.reset_secret()
    sa2, subject2, scopes2 = g._resolve_auth()
    assert subject2 == g.DEFAULT_SUBJECT
    assert tuple(scopes2) == g.DEFAULT_SCOPES
    g.reset_secret()
