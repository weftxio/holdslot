"""Suppression — the pure gate every candidate passes before any paid Apollo call (C0.4 + C2).

Two halves, both pure functions (no I/O), so the safeguard is unit-tested independently of
transport (the C2 DoD):

  * **C0.4 — promote exclusions** from the opaque Brief JSONB into a validated `ExclusionSet`.
    The founder types customers / active deals / competitors / do-not-contact as free text (one
    entry per line, typically `domain, name, website`); `extract_exclusions` normalizes that into
    domain / email / linkedin-slug sets plus the spec's structured `exclusions`.
  * **C2 — the exclusion gate**: `ExclusionSet.blocks(candidate)` returns the suppression reason
    (or None) for one candidate. Callers (find.py, the manual-add path) apply it inline before any
    paid Apollo call — a row never created costs zero credits, so this is the primary credit
    safeguard (the DB-side domain/identity dedupe is the backstop).

The boundary (locked, see fit-rubric §1): *no contact path at all* is a gate handled downstream
on enrichment; here we gate on **who they are** (exclusion membership).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.prospects.identity import (
    identity_key,
    linkedin_slug,
    normalize_domain,
    normalize_email,
)


@dataclass
class Candidate:
    """A normalized prospect-to-be — the shared shape for suppression, push, and ingest."""

    full_name: str = ""
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    domain: str = ""
    linkedin_url: str = ""
    email: str = ""
    company_industry: str = ""
    target_titles: str = ""
    target_seniority: str = ""
    icp_id: str | None = None

    @property
    def identity_key(self) -> str:
        return identity_key(
            linkedin_url=self.linkedin_url,
            domain=self.domain,
            first_name=self.first_name,
            last_name=self.last_name,
            email=self.email,
            full_name=self.full_name,
        )


@dataclass
class ExclusionSet:
    """Normalized do-not-contact universe. Membership tests use normalized forms only."""

    domains: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    linkedin_slugs: set[str] = field(default_factory=set)

    def blocks(self, c: Candidate) -> str | None:
        """Return the suppression reason if this candidate is excluded, else None."""
        if c.email and normalize_email(c.email) in self.emails:
            return "excluded_email"
        if c.domain and normalize_domain(c.domain) in self.domains:
            return "excluded_domain"
        slug = linkedin_slug(c.linkedin_url)
        if slug and slug in self.linkedin_slugs:
            return "excluded_linkedin"
        return None


# Brief keys whose text lists feed suppression (C0.4). Required: customers + active deals;
# optional: competitors + explicit do-not-contact. All parsed identically.
_EXCLUSION_BRIEF_FIELDS = ("excludeCustomers", "excludeDeals", "competitors", "doNotContact")


def _looks_like_email(token: str) -> bool:
    return "@" in token and "." in token.split("@")[-1]


def _parse_exclusion_line(line: str, ex: ExclusionSet) -> None:
    """A free-text line (`domain, name, website` or an email/url) → add normalized tokens."""
    for raw in line.replace("\t", ",").split(","):
        token = raw.strip()
        if not token:
            continue
        if _looks_like_email(token):
            ex.emails.add(normalize_email(token))
            continue
        slug = linkedin_slug(token)
        if slug:
            ex.linkedin_slugs.add(slug)
            continue
        dom = normalize_domain(token)
        # Only treat as a domain when it actually has a dot (skip the bare company-name token).
        if dom and "." in dom:
            ex.domains.add(dom)


def extract_exclusions(brief_data: dict, spec: dict | None = None) -> ExclusionSet:
    """C0.4 — build the validated ExclusionSet from the Brief (+ optional ResearchSpec).

    The spec's structured `exclusions` (domains / company_linkedin_urls / emails) are merged in
    when present, so an operator-curated spec and the raw brief text both feed one gate.
    """
    ex = ExclusionSet()
    for key in _EXCLUSION_BRIEF_FIELDS:
        value = brief_data.get(key)
        lines: list[str] = []
        if isinstance(value, str):
            lines = value.splitlines()
        elif isinstance(value, (list, tuple)):
            lines = [str(v) for v in value]
        for line in lines:
            _parse_exclusion_line(line, ex)

    spec_ex = (spec or {}).get("exclusions") or {}
    for d in spec_ex.get("domains", []) or []:
        dom = normalize_domain(d)
        if dom:
            ex.domains.add(dom)
    for e in spec_ex.get("emails", []) or []:
        em = normalize_email(e)
        if em:
            ex.emails.add(em)
    for url in spec_ex.get("company_linkedin_urls", []) or []:
        slug = linkedin_slug(url)
        if slug:
            ex.linkedin_slugs.add(slug)
    return ex
