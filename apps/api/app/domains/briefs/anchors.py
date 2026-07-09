"""Customer-anchor grounding — D+ Stage 4. The realest proof of who a client sells to is their
existing paying-customer list (`brief.excludeCustomers`). This module enriches those customer
domains and hands the scoping model their ACTUAL firmographics (industry / keywords / size band) as
evidence, so the next scope's targeting is grounded in real buyers rather than the ICP form's guess.

  * `customer_domains` — pure: parse the ordered, de-duped customer domains out of the brief's
    `excludeCustomers` free-text ("domain, name, website" per line), honoring `noExcludeCustomers`.
  * `customer_anchors` — enrich those domains (bounded + best-effort) → the LLM-facing anchor list
    (`apollo_map.parse_org_anchor`, minus the experiment-only `industry_tag_id`).

Bounded to `ANCHOR_MAX` domains so a long customer list can't fan out unbounded enrich calls; enrich
failures are dropped (partial grounding beats none), so an Apollo outage degrades to "no anchors".
"""

from __future__ import annotations

import logging

from app.domains.prospects import apollo_map
from app.domains.prospects.identity import normalize_domain
from app.integrations.apollo import client as apollo

log = logging.getLogger("holdslot.anchors")

ANCHOR_MAX = 8  # cap enriched customer domains (cost + latency guard on the regenerate path)


def customer_domains(brief_data: dict) -> list[str]:
    """Ordered, de-duped customer domains from the brief's `excludeCustomers` list. Honors
    `noExcludeCustomers` (explicit 'no list' → empty). Each line is "domain, name, website"; the
    first dotted token per line is the domain (mirrors the suppression parser's domain rule)."""
    if not brief_data or brief_data.get("noExcludeCustomers"):
        return []
    value = brief_data.get("excludeCustomers")
    if isinstance(value, str):
        lines = value.splitlines()
    elif isinstance(value, (list, tuple)):
        lines = [str(v) for v in value]
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        for raw in line.replace("\t", ",").split(","):
            dom = normalize_domain(raw.strip())
            if dom and "." in dom:  # skip bare company-name / person tokens
                if dom not in seen:
                    seen.add(dom)
                    out.append(dom)
                break  # first domain per line only
    return out


def customer_anchors(brief_data: dict, *, limit: int = ANCHOR_MAX) -> list[dict]:
    """Enrich the brief's customer domains (bounded to `limit`) → the customer-anchor evidence list
    for the scoping prompt. Best-effort: a domain that fails to enrich is dropped. Returns [] when
    there are no customers (or `noExcludeCustomers`), so `build_messages` emits no empty block."""
    domains = customer_domains(brief_data)[:limit]
    if not domains:
        return []
    try:
        orgs = apollo.enrich_organizations(domains)
    except apollo.ApolloError as e:
        log.warning("customer-anchor enrich unavailable — skipping anchors: %s", e)
        return []
    anchors: list[dict] = []
    for org in orgs:
        anchor = apollo_map.parse_org_anchor(org)
        anchor.pop("industry_tag_id", None)  # experiment-only; never fed to the model
        if anchor.get("domain") and (anchor.get("industry") or anchor.get("keywords")):
            anchors.append(anchor)
    return anchors
