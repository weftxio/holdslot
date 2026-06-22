"""Apollo transport (C2) — the three live endpoints behind the find→enrich loop.

Mirrors the B3 OpenRouter discipline: **lazy / SnapStart-safe** (no secret read, no network at
import — the `X-Api-Key` loads on first use and is cached), stdlib `urllib` (no runtime HTTP dep),
bounded 429/5xx backoff. Three calls, exactly the C0-verified contract:

  * `search_companies` — `POST mixed_companies/search` (**consumes plan credits**; confirm the per-
    call cost on the dashboard). Paginates to `max_results`.
  * `search_people`    — `POST mixed_people/api_search` (**0 credits**, no email/phone; **master
    key**). NEVER the legacy `mixed_people/search` (422). One org per call (Flow B loops).
  * `match_person`     — `POST people/match` (**the enrich spend**; `reveal_personal_emails` = 1 cr;
    `reveal_phone_number` off at MVP — it is async + needs a webhook).

The map/parse of request+response lives in the pure `domains/prospects/apollo_map.py`; this layer is
transport only.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from functools import lru_cache

import boto3

log = logging.getLogger("holdslot.apollo")

BASE_URL = "https://api.apollo.io/api/v1"
DEFAULT_TIMEOUT = 25  # seconds; under the 30s sync Lambda budget (find/enrich are sync routes)
PER_PAGE_MAX = 100  # Apollo hard cap
PAGE_HARD_CAP = 500  # Apollo: 500 pages = 50k rows
_RETRYABLE = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3


class ApolloError(RuntimeError):
    """A non-recoverable Apollo call (bad key, exhausted retries, transport). Carries the status."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@lru_cache(maxsize=1)
def _api_key() -> str:
    """Read `{prefix}/apollo` = `{"key": …}` once and cache it. `HOLDSLOT_APOLLO_KEY` env wins
    (local dev / a rotation) so a key change needs no Secrets Manager round-trip."""
    if env := os.environ.get("HOLDSLOT_APOLLO_KEY"):
        return env
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    prefix = os.environ.get("HOLDSLOT_SECRETS_PREFIX", "holdslot/prod")
    sm = boto3.client("secretsmanager", region_name=region)
    raw = sm.get_secret_value(SecretId=f"{prefix}/apollo")["SecretString"]
    return json.loads(raw)["key"]


def reset_key() -> None:
    _api_key.cache_clear()


def _post(path: str, body: dict, *, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """POST one request with `X-Api-Key`; retry transient 429/5xx with linear backoff. A 401/403
    drops the cached key (so a rotation is picked up next call) and raises immediately."""
    data = json.dumps(body).encode()
    for attempt in range(_MAX_RETRIES + 1):
        req = urllib.request.Request(
            f"{BASE_URL}/{path}",
            data=data,
            headers={
                "X-Api-Key": _api_key(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                reset_key()
                raise ApolloError(f"Apollo auth/plan error (HTTP {e.code})", status=e.code) from e
            if e.code in _RETRYABLE and attempt < _MAX_RETRIES:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise ApolloError(f"Apollo HTTP {e.code} on {path}", status=e.code) from e
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < _MAX_RETRIES:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise ApolloError(f"Apollo transport error on {path}: {e}") from e
    raise ApolloError(f"Apollo exhausted retries on {path}")  # unreachable


def _paginate(path: str, filter_body: dict, *, key: str, max_results: int) -> list[dict]:
    """POST `path` page by page, collecting `resp[key]` until `max_results` (or the data ends)."""
    rows: list[dict] = []
    page = 1
    while len(rows) < max_results and page <= PAGE_HARD_CAP:
        per_page = min(PER_PAGE_MAX, max_results - len(rows))
        resp = _post(path, {**filter_body, "page": page, "per_page": per_page})
        batch = resp.get(key) or []
        rows.extend(batch)
        pagination = resp.get("pagination") or {}
        total_pages = pagination.get("total_pages")
        if not batch or (total_pages is not None and page >= total_pages):
            break
        page += 1
    return rows[:max_results]


def search_companies(filter_body: dict, *, max_results: int = 100) -> list[dict]:
    """`mixed_companies/search` (credit-consuming) → `organizations` rows, capped at max_results."""
    return _paginate(
        "mixed_companies/search", filter_body, key="organizations", max_results=max_results
    )


def search_people(filter_body: dict, *, max_results: int = 100) -> list[dict]:
    """`mixed_people/api_search` (0 cr, master key) → `people` rows. One org per call (Flow B)."""
    return _paginate("mixed_people/api_search", filter_body, key="people", max_results=max_results)


def match_person(
    apollo_person_id: str, *, reveal_email: bool = True, reveal_phone: bool = False
) -> dict:
    """`people/match` (the enrich spend) → the revealed `person` object (email/last name/linkedin/
    departments). `reveal_email` = 1 credit; phone stays off at MVP (async + webhook)."""
    resp = _post(
        "people/match",
        {
            "id": apollo_person_id,
            "reveal_personal_emails": reveal_email,
            "reveal_phone_number": reveal_phone,
        },
    )
    return resp.get("person") or {}


__all__ = [
    "search_companies",
    "search_people",
    "match_person",
    "reset_key",
    "ApolloError",
    "BASE_URL",
    "PER_PAGE_MAX",
]
