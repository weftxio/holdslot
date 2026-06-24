"""Suppression — the pure gate every candidate passes before any paid Apollo call (C0.4 + C2).

Two halves, both pure functions (no I/O), so the safeguard is unit-tested independently of
transport (the C2 DoD):

  * **C0.4 — promote exclusions** from the opaque Brief JSONB into a validated `ExclusionSet`.
    The founder types customers / active deals / competitors / do-not-contact as free text (one
    entry per line, typically `domain, name, website`); `extract_exclusions` normalizes that into
    domain / email / linkedin-slug sets plus the spec's structured `exclusions`.
  * **C2 — suppress** a candidate set against the exclusions + already-seen identity keys. A row
    never created costs zero credits, so this is the primary credit safeguard (the DB-side
    domain/identity dedupe is the backstop). Every drop carries a reason for audit.

The boundary (locked, see fit-rubric §1): *no contact path at all* is a gate handled downstream
on enrichment; here we gate on **who they are** (exclusion membership) and **dedupe**.
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

    def to_enrichment(self) -> dict:
        """The Prospect.enrichment shape this candidate lands as (C2 push / C5 sourcing). One
        mapper so push, sourcing, and accept agree on the key set (`title` ← target_titles)."""
        return {
            "full_name": self.full_name,
            "company": self.company,
            "domain": self.domain,
            "linkedin_url": self.linkedin_url,
            "email": self.email,
            "company_industry": self.company_industry,
            "title": self.target_titles,
        }

    @classmethod
    def from_enrichment(cls, enrichment: dict | None) -> Candidate:
        """Rebuild a Candidate from a stored Prospect.enrichment (C5 accept) — the inverse of
        `to_enrichment`, so the round-trip is symmetric (accept reads back what push wrote)."""
        e = enrichment or {}
        return cls(
            full_name=e.get("full_name", ""),
            company=e.get("company", ""),
            domain=e.get("domain", ""),
            linkedin_url=e.get("linkedin_url", ""),
            email=e.get("email", ""),
            company_industry=e.get("company_industry", ""),
            target_titles=e.get("title", ""),
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


@dataclass
class SuppressionResult:
    survivors: list[Candidate]
    dropped: list[tuple[Candidate, str]]  # (candidate, reason)

    @property
    def survivor_keys(self) -> list[str]:
        return [c.identity_key for c in self.survivors]


def suppress(
    candidates: list[Candidate],
    exclusions: ExclusionSet,
    seen_identity_keys: set[str] | None = None,
) -> SuppressionResult:
    """C2 — drop excluded, un-keyable, and duplicate candidates before any push.

    `seen_identity_keys` are identities already enriched for this tenant (existing prospects);
    a re-push of one of them would pay twice, so it is dropped. Duplicates *within* the input
    batch are collapsed to the first occurrence.
    """
    seen = set(seen_identity_keys or set())
    survivors: list[Candidate] = []
    dropped: list[tuple[Candidate, str]] = []
    for c in candidates:
        reason = exclusions.blocks(c)
        if reason:
            dropped.append((c, reason))
            continue
        key = c.identity_key
        if not key:
            dropped.append((c, "no_identity_key"))
            continue
        if key in seen:
            dropped.append((c, "duplicate"))
            continue
        seen.add(key)
        survivors.append(c)
    return SuppressionResult(survivors=survivors, dropped=dropped)
