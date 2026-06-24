"""The `identity_key` — HoldSlot's single per-person dedupe key (C1/C2).

One normalized string per person so that "enrich once, reuse across N tenants" is free and a
re-import is idempotent. Precedence (most → least stable identity):
  1. LinkedIn slug  — `linkedin.com/in/<slug>` → `li:<slug>`
  2. domain|last|first — `dlf:<domain>|<last>|<first>` when we have a company domain + name
  3. email — `email:<addr>` as a last resort

Everything is lowercased and trimmed so casing/whitespace/URL noise never splits one person
into two rows. This is pure string logic — no I/O — so it is unit-tested in isolation and runs
identically on the push side (C2) and the ingest side (C3).
"""

from __future__ import annotations

import re

_LINKEDIN_SLUG = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)


def normalize_domain(value: str | None) -> str:
    """A bare, lowercased registrable domain: strip scheme, `www.`, path, port, trailing dot."""
    if not value:
        return ""
    v = value.strip().lower()
    v = re.sub(r"^[a-z]+://", "", v)  # scheme
    v = v.split("/", 1)[0]  # path
    v = v.split("?", 1)[0].split("#", 1)[0]
    v = v.split("@")[-1]  # in case an email slipped in
    v = v.split(":", 1)[0]  # port
    if v.startswith("www."):
        v = v[4:]
    return v.strip(".")


def normalize_email(value: str | None) -> str:
    return value.strip().lower() if value else ""


def linkedin_slug(url: str | None) -> str:
    """The stable `/in/<slug>` part of a LinkedIn URL, lowercased (no trailing slash/query)."""
    if not url:
        return ""
    m = _LINKEDIN_SLUG.search(url)
    return m.group(1).strip("/").lower() if m else ""


def _norm_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()) if value else ""


def identity_key(
    *,
    linkedin_url: str | None = None,
    domain: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    full_name: str | None = None,
) -> str:
    """Compute the canonical identity key, or "" when there is nothing to key on.

    `full_name` is split into first/last only as a fallback when the explicit names are absent.
    """
    slug = linkedin_slug(linkedin_url)
    if slug:
        return f"li:{slug}"

    first, last = _norm_name(first_name), _norm_name(last_name)
    if (not first or not last) and full_name:
        parts = _norm_name(full_name).split(" ")
        if len(parts) >= 2:
            first = first or parts[0]
            last = last or parts[-1]
    dom = normalize_domain(domain)
    # Require BOTH names: a bare `dlf:dom|last|` would over-merge every same-surname person at a
    # company and split the named vs. unnamed record of the same person. Fall through to email.
    if dom and first and last:
        return f"dlf:{dom}|{last}|{first}"

    em = normalize_email(email)
    if em:
        return f"email:{em}"
    return ""
