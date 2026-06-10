#!/usr/bin/env python3
"""verify_keys.py - connection test for HoldSlot platform keys.

Reads each secret from AWS Secrets Manager via the `aws` CLI (no boto3), then runs
the minimal read/auth call each build-plan phase actually needs, and prints a
PASS/FAIL/PEND table. Secret VALUES are never printed.

The check is PHASE-AWARE: fields a later phase provisions (e.g. Clay's table +
webhook at Phase C, Smartlead's webhook secret + sending accounts at Phase E) are
reported as PEND ("pending"), not FAIL, so a clean run today exits 0. Pass
--strict to treat PEND rows as failures once you reach the phase that needs them.

Scope (only what docs/initial-build-plan.md uses):
  - app        : JWT signing/refresh keys present, strong, distinct          (Phase A)
                 (Aurora master credential is a separate RDS-managed secret, tested later)
  - openrouter : key valid + spend cap set; optional default_model reachable (Phase B)
  - clay       : api_key present now; table/webhook fields PEND until        (Phase C)
  - smartlead  : api key valid; sending accounts + webhook secret PEND until (Phase E)
  - google     : service-account key + domain-wide delegation + Calendar + Meet scopes (Phase F)

Cost: every check is FREE except the Clay row push (~1 credit), which only runs
with --clay-push. Delete that test row from the Clay table afterward.

Usage:
  python3 verify_keys.py                 # all free checks (PEND for future-phase fields)
  python3 verify_keys.py --strict        # PEND counts as failure (use at the field's phase)
  python3 verify_keys.py --clay-push     # also push one Clay test row (~1 credit)
  python3 verify_keys.py --only google   # run a single platform
  AWS_PROFILE / --profile, --region override the defaults below.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_PROFILE = os.environ.get("AWS_PROFILE", "holdslot")
DEFAULT_REGION = os.environ.get("AWS_REGION", "us-east-1")
TIMEOUT = 30
# Cloudflare-fronted APIs (e.g. Smartlead) 403 the default urllib User-Agent.
# The real backend client (Phase E) must send a non-default UA for the same reason.
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) HoldSlot-verify/1.0"

# Host identity for Google domain-wide delegation (not secret; see CLAUDE.md / docs).
GOOGLE_SUBJECT = "info@tryholdslot.com"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/meetings.space.readonly",
]


def _ssl_context() -> ssl.SSLContext:
    """Verified TLS context. python.org macOS builds ship without CA certs, so
    fall back to the system root bundle at /etc/ssl/cert.pem when needed."""
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca", 0) == 0 and os.path.exists("/etc/ssl/cert.pem"):
        ctx.load_verify_locations("/etc/ssl/cert.pem")
    return ctx


SSL_CTX = _ssl_context()

# ---- tiny result table -------------------------------------------------------

PASS, FAIL, PEND = "PASS", "FAIL", "PEND"
ROWS: list[tuple[str, str, str, str]] = []  # (platform, check, status, detail)


def record(platform: str, check: str, ok: bool, detail: str = "") -> None:
    _row(platform, check, PASS if ok else FAIL, detail)


def pending(platform: str, check: str, detail: str = "") -> None:
    """A field a later phase provisions; informational today, fails only --strict."""
    _row(platform, check, PEND, detail)


def _row(platform: str, check: str, status: str, detail: str) -> None:
    ROWS.append((platform, check, status, detail))
    print(f"  [{status}] {check}" + (f" - {detail}" if detail else ""))


# ---- helpers -----------------------------------------------------------------


def get_secret(name: str, profile: str, region: str) -> dict:
    """Fetch + JSON-parse a secret via the aws CLI. Raises on any failure."""
    out = subprocess.run(
        [
            "aws", "secretsmanager", "get-secret-value",
            "--secret-id", name,
            "--profile", profile, "--region", region,
            "--query", "SecretString", "--output", "text",
        ],
        capture_output=True, text=True,
        timeout=TIMEOUT, stdin=subprocess.DEVNULL,  # never block on an MFA/SSO prompt
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "aws CLI failed")
    return json.loads(out.stdout)


def http(method: str, url: str, headers: dict | None = None, body: bytes | None = None):
    """Return (status, text). Non-2xx is returned, not raised; network errors raise."""
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=SSL_CTX) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def fetch_json(platform: str, fail_check: str, method: str, url: str,
               headers: dict | None = None, body: bytes | None = None):
    """HTTP call returning parsed JSON on 200, else None - recording a FAIL row
    under `fail_check`. Never raises: network errors and non-JSON 200s become
    FAIL rows so one dead endpoint can't abort the whole run. On success the
    caller records its own PASS row."""
    try:
        status, text = http(method, url, headers, body)
    except Exception as e:
        record(platform, fail_check, False, f"network error: {type(e).__name__}")
        return None
    if status != 200:
        record(platform, fail_check, False, f"HTTP {status}")
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        record(platform, fail_check, False, "HTTP 200 but non-JSON body")
        return None


def probe_status(platform: str, check: str, url: str, headers: dict | None = None) -> None:
    """Record PASS iff a GET returns 200; network errors become a FAIL row."""
    try:
        status, _ = http("GET", url, headers)
    except Exception as e:
        record(platform, check, False, f"network error: {type(e).__name__}")
        return
    record(platform, check, status == 200, f"HTTP {status}")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


# ---- app (first-party JWT secret) --------------------------------------------

MIN_KEY_LEN = 32  # chars; `openssl rand -base64 48` yields 64


def check_app(sec: dict) -> None:
    print("\nholdslot/prod/app")
    sign = sec.get("jwt_signing_key")
    refresh = sec.get("jwt_refresh_key")

    # Offline checks only: presence + strength + distinctness. (An HS256 sign/verify
    # round-trip would pass for any non-empty string, so it proves nothing here.)
    record("app", "jwt_signing_key present + strong",
           bool(sign) and len(sign) >= MIN_KEY_LEN,
           f"len {len(sign)}" if sign else "missing")
    record("app", "jwt_refresh_key present + strong",
           bool(refresh) and len(refresh) >= MIN_KEY_LEN,
           f"len {len(refresh)}" if refresh else "missing")

    if sign and refresh:
        record("app", "keys are distinct", sign != refresh,
               "ok" if sign != refresh else "signing == refresh - reuse risk")
    # NB: the Aurora master credential is a SEPARATE secret (RDS-managed), not a
    # field here - tested on its own once Aurora is provisioned (Phase A).


# ---- openrouter --------------------------------------------------------------


def check_openrouter(sec: dict) -> None:
    print("\nholdslot/prod/openrouter")
    api_key = sec.get("api_key")
    if not api_key:
        record("openrouter", "secret shape", False, "missing api_key")
        return
    auth = {"Authorization": f"Bearer {api_key}"}

    data = fetch_json("openrouter", "key valid", "GET",
                      "https://openrouter.ai/api/v1/key", auth)
    if data is None:
        return
    d = data.get("data", {})
    limit = d.get("limit")
    usage = d.get("usage")
    record("openrouter", "key valid", True, f"usage={usage}")
    # Spend cap is a cost-control invariant: a key with no cap must NOT pass.
    record("openrouter", "spend cap set", limit is not None,
           f"limit={limit}" if limit is not None else "no spend cap configured")

    want = sec.get("default_model")
    models = fetch_json("openrouter", "models list", "GET",
                        "https://openrouter.ai/api/v1/models", auth)
    if models is None:
        return
    ids = {m.get("id") for m in models.get("data", [])}
    if not want:
        pending("openrouter", "default_model reachable", "default_model not set (optional)")
    else:
        record("openrouter", "default_model reachable", want in ids,
               want if want in ids else f"{want} NOT in model list")


# ---- clay --------------------------------------------------------------------


def check_clay(sec: dict, do_push: bool) -> None:
    print("\nholdslot/prod/clay")
    # api_key is the only field present today. (We can't cheaply auth it against
    # Clay's API without a credit, so this attests "stored", not "valid".)
    record("clay", "api_key present", bool(sec.get("api_key")),
           "stored" if sec.get("api_key") else "missing")

    # table + webhook fields are provisioned at Phase C - PEND until then.
    for field in ("table_id", "inbound_webhook_url", "inbound_webhook_secret"):
        if sec.get(field):
            record("clay", f"{field} present", True)
        else:
            pending("clay", f"{field} present", "added at Phase C")

    url = sec.get("inbound_webhook_url")
    if not url:
        pending("clay", "webhook reachable", "no inbound_webhook_url yet (Phase C)")
        return

    if not do_push:
        # reachability only - OPTIONS so we don't create a row
        try:
            status, _ = http("OPTIONS", url)
            record("clay", "webhook reachable (no push)", status < 500,
                   f"HTTP {status} (use --clay-push for a real 1-credit row test)")
        except Exception as e:
            record("clay", "webhook reachable", False, f"network error: {type(e).__name__}")
        return

    # real 1-credit push of a clearly-marked test row
    payload = json.dumps({
        "_holdslot_test": True,
        "company": "HoldSlot Verify",
        "note": "delete me - verify_keys.py connection test",
    }).encode()
    headers = {"Content-Type": "application/json"}
    secret = sec.get("inbound_webhook_secret")
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    try:
        status, _ = http("POST", url, headers, payload)
        record("clay", "webhook push (~1 credit)", 200 <= status < 300,
               f"HTTP {status} - DELETE the 'HoldSlot Verify' row from the Clay table")
    except Exception as e:
        record("clay", "webhook push", False, f"network error: {type(e).__name__}")


# ---- smartlead ---------------------------------------------------------------


def check_smartlead(sec: dict) -> None:
    print("\nholdslot/prod/smartlead")
    api_key = sec.get("api_key")
    record("smartlead", "api_key present", bool(api_key), "stored" if api_key else "missing")
    if not api_key:
        return
    base = "https://server.smartlead.ai/api/v1"

    camps = fetch_json("smartlead", "api key valid", "GET", f"{base}/campaigns?api_key={api_key}")
    if camps is None:
        return
    record("smartlead", "api key valid", True, "HTTP 200")

    accounts = fetch_json("smartlead", "email accounts", "GET",
                          f"{base}/email-accounts?api_key={api_key}")
    if accounts is None:
        return
    live_ids = {str(a.get("id")) for a in accounts} if isinstance(accounts, list) else set()
    want = sec.get("sending_account_ids") or []
    want = [str(x) for x in (want if isinstance(want, list) else [want])]
    if not want:
        # sending accounts are connected after the ~3-week warm-up (Phase E).
        pending("smartlead", "sending_account_ids resolve",
                f"{len(live_ids)} account(s) on plan; none listed in secret yet (Phase E)")
    else:
        missing = [w for w in want if w not in live_ids]
        record("smartlead", "sending_account_ids resolve", not missing,
               "all resolve" if not missing else f"missing: {', '.join(missing)}")

    # webhook signing secret verifies inbound Smartlead webhooks - added at Phase E.
    if sec.get("webhook_signing_secret"):
        record("smartlead", "webhook_signing_secret present", True)
    else:
        pending("smartlead", "webhook_signing_secret present", "added at Phase E")


# ---- google ------------------------------------------------------------------


def google_access_token(sa: dict, subject: str, scopes: list[str]) -> str:
    """Mint a domain-wide-delegated access token. Signs the JWT with openssl."""
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": sa["client_email"],
        "sub": subject,
        "scope": " ".join(scopes),
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now - 60,  # backdate 60s so a slightly-fast local clock isn't rejected
        "exp": now + 3600,
    }
    signing_input = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(claims).encode())}"
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(sa["private_key"])
        key_path = f.name
    try:
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=signing_input.encode(), capture_output=True, timeout=TIMEOUT,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode().strip() or "openssl sign failed")
        signature = b64url(proc.stdout)
    finally:
        os.unlink(key_path)

    jwt = f"{signing_input}.{signature}"
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt,
    }).encode()
    status, text = http(
        "POST", "https://oauth2.googleapis.com/token",
        {"Content-Type": "application/x-www-form-urlencoded"}, body,
    )
    if status != 200:
        raise RuntimeError(f"token endpoint HTTP {status}: {text[:300]}")
    return json.loads(text)["access_token"]


def check_google(sec: dict) -> None:
    print("\nholdslot/prod/google")
    # Two accepted shapes: the planned envelope, or a raw service-account JSON
    # pasted directly (subject/scopes then fall back to the known host identity).
    if sec.get("service_account_json"):
        sa = sec["service_account_json"]
        if isinstance(sa, str):
            # the SA file nested as an escaped JSON string (common in the console)
            try:
                sa = json.loads(sa)
            except json.JSONDecodeError:
                record("google", "secret shape", False,
                       "service_account_json is a string but not valid JSON")
                return
        subject = sec.get("delegated_subject", GOOGLE_SUBJECT)
        scopes = sec.get("scopes") or GOOGLE_SCOPES
        record("google", "secret shape", True, f"envelope; sub={subject}, {len(scopes)} scope(s)")
    elif sec.get("client_email") and sec.get("private_key"):
        sa = sec
        subject, scopes = GOOGLE_SUBJECT, GOOGLE_SCOPES
        record("google", "secret shape", True,
               "raw SA JSON; using default subject/scopes "
               "(recommend wrapping in {service_account_json, delegated_subject, scopes})")
    else:
        record("google", "secret shape", False,
               "need service_account_json envelope or a raw service-account JSON")
        return

    if not (isinstance(sa, dict) and sa.get("client_email") and sa.get("private_key")):
        record("google", "key + domain-wide delegation", False,
               "service-account JSON missing client_email/private_key")
        return

    try:
        token = google_access_token(sa, subject, scopes)
        record("google", "key + domain-wide delegation", True, "minted delegated token")
    except Exception as e:
        record("google", "key + domain-wide delegation", False, str(e).splitlines()[0][:200])
        return
    auth = {"Authorization": f"Bearer {token}"}

    if any("calendar" in s for s in scopes):
        probe_status("google", "calendar scope (read)",
                     "https://www.googleapis.com/calendar/v3/users/me/calendarList?maxResults=1",
                     auth)
    if any("meetings" in s for s in scopes):
        probe_status("google", "meet REST scope (read)",
                     "https://meet.googleapis.com/v2/conferenceRecords?pageSize=1", auth)


# ---- main --------------------------------------------------------------------

CHECKS = {
    "app": lambda sec, args: check_app(sec),
    "openrouter": lambda sec, args: check_openrouter(sec),
    "clay": lambda sec, args: check_clay(sec, args.clay_push),
    "smartlead": lambda sec, args: check_smartlead(sec),
    "google": lambda sec, args: check_google(sec),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--region", default=DEFAULT_REGION)
    ap.add_argument("--only", choices=list(CHECKS), help="run a single platform")
    ap.add_argument("--clay-push", action="store_true",
                    help="push one Clay test row (~1 credit); off by default")
    ap.add_argument("--strict", action="store_true",
                    help="treat PEND (not-yet-provisioned phase fields) as failures")
    args = ap.parse_args()

    targets = [args.only] if args.only else list(CHECKS)
    print(f"Verifying {len(targets)} secret(s) via profile={args.profile} region={args.region}")

    for name in targets:
        try:
            sec = get_secret(f"holdslot/prod/{name}", args.profile, args.region)
        except Exception as e:
            record(name, "read secret", False, (str(e).splitlines() or [""])[-1][:200] or type(e).__name__)
            continue
        try:
            CHECKS[name](sec, args)
        except Exception as e:  # a check bug must not abort the remaining platforms
            record(name, "check crashed", False,
                   f"{type(e).__name__}: {(str(e).splitlines() or [''])[0][:160]}")

    # summary
    n_pass = sum(1 for r in ROWS if r[2] == PASS)
    n_fail = sum(1 for r in ROWS if r[2] == FAIL)
    n_pend = sum(1 for r in ROWS if r[2] == PEND)
    print("\n" + "=" * 60)
    print(f"SUMMARY: {n_pass} passed, {n_fail} failed, {n_pend} pending"
          + (" (pending = future-phase fields; --strict to fail on them)" if n_pend and not args.strict else ""))
    for p, c, status, _d in ROWS:
        print(f"  {status}  {p:11} {c}")
    print("=" * 60)
    return 1 if (n_fail or (args.strict and n_pend)) else 0


if __name__ == "__main__":
    sys.exit(main())
