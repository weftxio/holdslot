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
  * `enrich_organizations` — `GET organizations/enrich?domain=` (ONE org/call, run concurrently):
    the firmographics company-search omits (industry / size / address / tech). Single-enrich, not
    `bulk_enrich`, is the verified contract for this account.

The map/parse of request+response lives in the pure `domains/prospects/apollo_map.py`; this layer is
transport only.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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


def _request(
    method: str, path: str, *, body: dict | None = None, timeout: int = DEFAULT_TIMEOUT
) -> dict:
    """One `X-Api-Key` request (POST with a JSON body, or GET with the query baked into `path`);
    retry transient 429/5xx with linear backoff. A 401/403 drops the cached key (so a rotation is
    picked up next call) and raises immediately."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"X-Api-Key": _api_key(), "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(_MAX_RETRIES + 1):
        req = urllib.request.Request(
            f"{BASE_URL}/{path}", data=data, headers=headers, method=method
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


def _post(path: str, body: dict, *, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """POST one request with a JSON body."""
    return _request("POST", path, body=body, timeout=timeout)


def _get(path: str, query: dict, *, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """GET one request, URL-encoding `query` into the path."""
    return _request("GET", f"{path}?{urllib.parse.urlencode(query)}", timeout=timeout)


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


def count_people(filter_body: dict) -> int:
    """Total people matching `filter_body`, no rows fetched (per_page=1) → `total_entries` (0 cr).

    The cheap primitive behind the Find-Settings facet sidebar: one call per Management-Level /
    Department value yields its live count (Apollo exposes no facet/aggregation param, so counts are
    N independent searches — free, since people search costs no credits)."""
    r = _post("mixed_people/api_search", {**filter_body, "page": 1, "per_page": 1})
    return int(r.get("total_entries") or 0)


_ENRICH_WORKERS = 10  # concurrent single-domain enrich calls (the find batch is ≤15)


def enrich_organizations(domains: list[str]) -> list[dict]:
    """Enrich a set of company domains via `organizations/enrich` (GET `?domain=`, ONE org per call)
    → the rich org shape (industry / employee count / address / tech / keywords / headcount growth)
    that `mixed_companies/search` omits. Calls run concurrently (the find batch is small) and a
    single-domain failure is dropped, not fatal — partial enrichment beats none.

    Single-enrich is the endpoint Apollo's docs confirm for this account (the bulk variant takes
    `domains[]` as query params, not a JSON body — a mismatch that silently returns nothing). Cost:
    org enrichment is metered separately from the `people/match` email credit; confirm per-org cost
    on the dashboard before scaling.
    """
    clean = [d for d in dict.fromkeys(domains) if d]  # dedupe, preserve order, drop empties
    if not clean:
        return []

    def _one(domain: str) -> dict | None:
        try:
            return _get("organizations/enrich", {"domain": domain}).get("organization") or None
        except ApolloError as e:
            log.warning("org enrich failed for %s: %s", domain, e)
            return None

    with ThreadPoolExecutor(max_workers=min(_ENRICH_WORKERS, len(clean))) as ex:
        return [o for o in ex.map(_one, clean) if o]


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
    "count_people",
    "enrich_organizations",
    "match_person",
    "reset_key",
    "ApolloError",
    "BASE_URL",
    "PER_PAGE_MAX",
]
