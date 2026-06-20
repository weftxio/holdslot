"""Clay transport + CSV ingest — the one stateless-enrichment boundary (C2 push, C3 ingest).

Clay is enrichment *compute*, not storage: HoldSlot pushes suppressed, identity-keyed rows into
the one shared webhook (tagged `run_id` + `identity_key`, no tenant), Clay enriches, the operator
exports a CSV, and `parse_export_csv` reads it back **by header name** (order-independent) into
the documented field contract. Both pure functions are unit-tested without network; only
`push_rows` touches AWS/Clay.

Auth (verified 2026-06-19): header `x-clay-webhook-auth: <webhook_authentication_token>` to
`inbound_webhook_url`, both in secret `holdslot/prod/clay`. The legacy `api_key` field is stale.
"""

from __future__ import annotations

import csv
import io
import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache

import boto3

from app.domains.prospects.identity import normalize_domain, normalize_email
from app.domains.prospects.suppression import Candidate

# Webhook guardrails (data-schema Part 1): ≤10 rows/s, ≤100KB/push. We push one row per POST
# (Clay webhook = create-record) with a throttle that stays under the rate cap.
_PUSH_INTERVAL_SECONDS = 0.12


def assemble_push_row(candidate: Candidate, run_id: str) -> dict:
    """A candidate → the Clay webhook payload (all Text). Pure; `email`/`company_industry`
    are optional gate/coalesce inputs, included only when known."""
    row = {
        "run_id": run_id,
        "identity_key": candidate.identity_key,
        "full_name": candidate.full_name,
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "company": candidate.company,
        "domain": normalize_domain(candidate.domain),
        "linkedin_url": candidate.linkedin_url,
        "target_titles": candidate.target_titles,
        "target_seniority": candidate.target_seniority,
    }
    if candidate.email:
        row["email"] = normalize_email(candidate.email)
    if candidate.company_industry:
        row["company_industry"] = candidate.company_industry
    return {k: v for k, v in row.items() if v}


# ---------------------------------------------------------------------------
# Transport (the only impure part) — lazy secret load, SnapStart-safe (mirrors B3).
# ---------------------------------------------------------------------------


@dataclass
class ClayConfig:
    inbound_webhook_url: str
    webhook_authentication_token: str


@lru_cache(maxsize=1)
def _config() -> ClayConfig:
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    prefix = os.environ.get("HOLDSLOT_SECRETS_PREFIX", "holdslot/prod")
    sm = boto3.client("secretsmanager", region_name=region)
    raw = sm.get_secret_value(SecretId=f"{prefix}/clay")["SecretString"]
    sec = json.loads(raw)
    return ClayConfig(
        inbound_webhook_url=sec["inbound_webhook_url"],
        webhook_authentication_token=sec["webhook_authentication_token"],
    )


def reset_config() -> None:
    _config.cache_clear()


def _post_row(row: dict, *, timeout: int = 15) -> int:
    cfg = _config()
    req = urllib.request.Request(
        cfg.inbound_webhook_url,
        data=json.dumps(row).encode(),
        headers={
            "Content-Type": "application/json",
            "x-clay-webhook-auth": cfg.webhook_authentication_token,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


class ClayPushError(Exception):
    """A transport failure mid-batch. Carries the rows Clay already accepted (2xx) before the
    failure so the caller can record exactly those — a paid identity must never be re-pushed."""

    def __init__(self, accepted: list[dict], cause: Exception) -> None:
        self.accepted = accepted
        super().__init__(str(cause))


def push_rows(rows: list[dict], *, sleep=time.sleep) -> list[dict]:
    """Push assembled rows to the one Clay webhook, throttled under the rate cap. Returns the
    rows Clay accepted (HTTP 2xx). On a transport error raises `ClayPushError` carrying the rows
    accepted *before* the failure, so the caller records only what was actually paid for."""
    accepted: list[dict] = []
    for i, row in enumerate(rows):
        if i:
            sleep(_PUSH_INTERVAL_SECONDS)
        try:
            status = _post_row(row)
        except Exception as e:
            raise ClayPushError(accepted, e) from e
        if 200 <= status < 300:
            accepted.append(row)
    return accepted


# ---------------------------------------------------------------------------
# CSV ingest (pure) — read by header name against the locked export contract (C3).
# ---------------------------------------------------------------------------

# Columns folded into the `enrichment` JSONB extras (kept, not promoted to a column).
_EXTRA_COLS = ("Country", "Locality", "Annual Revenue", "Website", "Employee Count")
_TRUTHY = {"valid", "true", "yes", "deliverable", "ok", "1"}


@dataclass
class EnrichedRow:
    """One parsed CSV row — the coalesced field contract + the raw row for the prospect."""

    run_id: str
    identity_key: str
    full_name: str = ""
    company: str = ""
    domain: str = ""
    company_domain: str = ""
    linkedin_url: str = ""
    email: str = ""
    provider: str = ""
    email_valid: bool = False
    title: str = ""
    seniority: str = ""
    company_size: str = ""
    company_industry: str = ""
    enrichment: dict = field(default_factory=dict)


def _coalesce(*values: str) -> str:
    for v in values:
        if v and v.strip():
            return v.strip()
    return ""


def parse_export_csv(text: str) -> list[EnrichedRow]:
    """Parse a Clay CSV export into EnrichedRows, matched by header name (order-independent).

    Rows missing both correlation keys (`run_id`/`identity_key`) are skipped — they cannot be
    matched back to a prospect. Coalescing follows the data-schema contract: gate value wins over
    the enriched output when both are present.
    """
    reader = csv.DictReader(io.StringIO(text))
    out: list[EnrichedRow] = []
    for raw in reader:
        # csv.DictReader keys can carry stray whitespace from the export header.
        r = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        run_id, identity_key = r.get("run_id", ""), r.get("identity_key", "")
        if not run_id or not identity_key:
            continue
        domain = normalize_domain(r.get("domain", ""))
        extras = {col: r[col] for col in _EXTRA_COLS if r.get(col)}
        out.append(
            EnrichedRow(
                run_id=run_id,
                identity_key=identity_key,
                full_name=r.get("full_name", ""),
                company=r.get("company", ""),
                domain=domain,
                company_domain=domain,  # input domain, not enriched Website (can be a subdomain)
                linkedin_url=r.get("linkedin_url", ""),
                email=normalize_email(_coalesce(r.get("email", ""), r.get("Work Email", ""))),
                provider=r.get("Work Email Data Provider", ""),
                email_valid=r.get("Validate Findymail", "").strip().lower() in _TRUTHY,
                title=r.get("Title", ""),
                seniority=r.get("target_seniority", ""),
                company_size=_coalesce(r.get("Size", ""), r.get("Employee Count", "")),
                company_industry=_coalesce(r.get("company_industry", ""), r.get("Industry", "")),
                enrichment=extras,
            )
        )
    return out
