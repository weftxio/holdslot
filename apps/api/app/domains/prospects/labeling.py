"""Scoring v2 — the deterministic label engine (docs/initial-build-plan.md §D+.2).

Replaces the v1 0–100 `AI Score` with a 4-label verdict. This module is the **contract + gate
ladder**: pure, LLM-free, and free of Apollo credits. Given a company's stage-0 classification +
firmographics + the client's intake rules, it walks the spec's processing order (§3) and stops at
the first match.

The two web/LLM-grounded signals are INPUTS, not computed here:
  * `liveness` — the "{company} liquidation OR acquired OR shut down" web-search verdict (spec §4).
  * `icp_match` + `subscores` — the ICP-A/B judgment and the four 1–5 axes (spec §7–8).
Both are produced by V2-2's paid `company_score_v2` call and passed in; in V2-1 they are `None`, so
`assign_label` runs the deterministic middle (rules → data → size) and returns `label=None`
("needs re-score") for a row that survives every gate. Passing fixtures for the paid signals makes
the WHOLE ladder unit-testable without a network call (test_labeling exercises the §12 fixture).

Processing order (spec §3, re-ordered so the free deterministic gates run before the paid call —
a rule-killed row is never web-checked):
    1. liveness   → excluded_by_rules        (paid; V2-2)
    2. rules      → excluded_by_rules         (free; here)
    3. data check → low_fit                   (free; here)
    4. size rule  → low_fit                   (free; here)
    5. ICP match  → low_fit if no match       (paid; V2-2)
    6. score      → contact_now / soon / low_fit via label_from_score  (paid; V2-2)
Nothing is ever deleted — every sourced row gets a label and a reason (spec §2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- labels (spec §2) ---------------------------------------------------------
CONTACT_NOW = "contact_now"
CONTACT_SOON = "contact_soon"
LOW_FIT = "low_fit"
EXCLUDED = "excluded_by_rules"
LABELS: tuple[str, ...] = (CONTACT_NOW, CONTACT_SOON, LOW_FIT, EXCLUDED)
# UI + feed sort priority (spec §11): actions first, footnotes last.
LABEL_ORDER: dict[str, int] = {label: i for i, label in enumerate(LABELS)}

# --- subscore axes (spec §8) --------------------------------------------------
SUBSCORE_AXES: tuple[str, ...] = ("deal_fit", "outbound_gap", "trigger", "reachability")
# People tier (V2-2): the same 1–5 / sum-4–20 shape on a person-shaped axis set (company caps it).
SUBSCORE_AXES_PEOPLE: tuple[str, ...] = ("persona_fit", "authority", "trigger", "reachability")

# --- reason strings (spec §9) — canonical enum-ish literals, kept spec-exact ---
REASON_DEFUNCT = "company defunct"
REASON_ACQUIRED = "acquired — no longer independent"
REASON_NO_WEB = "no active web presence"
REASON_RULE_MARKET = {"B2B": "rule: B2B only", "B2C": "rule: B2C only"}
REASON_RULE_GEO = "rule: outside target geography"
REASON_RULE_EXCLUSION = "rule: client exclusion"
REASON_DATA_UNUSABLE = "data_unusable"
REASON_WRONG_VERTICAL = "wrong vertical"
REASON_TOO_LARGE = "too large"

# --- flags (spec §10) — non-blocking warning markers --------------------------
FLAG_HQ_MISMATCH = "hq_mismatch"
FLAG_REVENUE_IMPLAUSIBLE = "revenue_implausible"
FLAG_FOUNDING_DATE_CONFLICT = "founding_date_conflict"
FLAG_COMPETITOR_ADJACENT = "competitor_adjacent"
FLAG_PARTNER_LED = "partner_led"
FLAG_STALE_RECORD = "stale_record"
# `headcount_uncertain` (a size-gate suppression flag) was removed in D+.5/R11: only ONE headcount
# source exists in the data (Apollo `estimated_num_employees`; the LLM score returns none), so the
# "sources disagree >2×" flag was never producible — it and its suppression branch are gone.
FLAGS: frozenset[str] = frozenset({
    FLAG_HQ_MISMATCH, FLAG_REVENUE_IMPLAUSIBLE,
    FLAG_FOUNDING_DATE_CONFLICT, FLAG_COMPETITOR_ADJACENT, FLAG_PARTNER_LED, FLAG_STALE_RECORD,
})
# The flags the LLM score call may emit (content/web-derived). `hq_mismatch` is computed
# deterministically (description-vs-field), never model-set.
MODEL_FLAGS: tuple[str, ...] = (
    FLAG_REVENUE_IMPLAUSIBLE, FLAG_FOUNDING_DATE_CONFLICT,
    FLAG_COMPETITOR_ADJACENT, FLAG_PARTNER_LED, FLAG_STALE_RECORD,
)

# People-tier reasons (people extrapolation — spec is company-tier only; carries risk ⑦).
REASON_PARENT_EXCLUDED = "parent company excluded"
REASON_AVOIDED_TITLE = "rule: avoided title"

# Wire services / press-release aggregators — a company `website` on one of these is not a real web
# presence (spec §6, "newswire.ca"). Matched as a domain suffix.
AGGREGATOR_HOSTS: frozenset[str] = frozenset({
    "newswire.ca", "newswire.com", "prnewswire.com", "businesswire.com", "globenewswire.com",
    "prweb.com", "einnews.com", "accesswire.com", "marketwired.com", "prlog.org",
})

# Values that read as "no industry" in the source data (spec §6: null or "—").
_EMPTY_INDUSTRY: frozenset[str] = frozenset({"", "-", "—", "–", "n/a", "none", "unknown"})


# --- score → label (spec §8) --------------------------------------------------
def label_from_score(total: int) -> str:
    """The one threshold policy (spec §8): ≥16 contact_now · ≥10 contact_soon · else low_fit."""
    if total >= 16:
        return CONTACT_NOW
    if total >= 10:
        return CONTACT_SOON
    return LOW_FIT


def collapse_subscores(
    subscores: dict, axes: tuple[str, ...] = SUBSCORE_AXES
) -> tuple[int, dict[str, int]]:
    """Clamp each axis to 1–5, sum → (total 4–20, normalized). Pure — the server owns the total,
    so a model emitting 0 or 7 can't move the threshold. Reusable by the people tier via `axes`."""
    clean: dict[str, int] = {}
    total = 0
    for ax in axes:
        try:
            v = int(subscores.get(ax, 1) or 1)
        except (TypeError, ValueError):
            v = 1
        v = max(1, min(v, 5))
        clean[ax] = v
        total += v
    return total, clean


# --- helpers ------------------------------------------------------------------
def _norm(s: str | None) -> str:
    return (s or "").strip().casefold()


def title_is_avoided(title: str | None, avoid_titles) -> bool:
    """True if `title` matches any of `avoid_titles` (normalized substring, "sales ops" catches
    "VP, Sales Ops"). The SINGLE source of truth for the avoid-title drop, shared by
    `find.filter_people` (the pre-score drop) and `assign_person_label` (the gate) so the two never
    disagree — they used to drift (`.lower()` vs `_norm`'s strip+casefold), which could drop
    different rows on a whitespace/Unicode edge (R27)."""
    tnorm = _norm(title)
    if not tnorm:
        return False
    return any(_norm(t) in tnorm for t in (avoid_titles or []) if t)


def _effective_market(business_model: str | None, has_b2b_line: bool) -> str:
    """The market side to gate on (spec §5): `Complex` (serves both by design — marketplaces /
    platforms) is not B2C → treat as B2B. B2B/B2C/Unknown/"" pass through; only a strict B2B/B2C
    opposite of the client's rule excludes.

    Founder 2026-07-10: the former B2C-with-a-B2B-line → `Both` carve-out (the "Luma guard") is
    REMOVED. A strict-B2B client wants EVERY B2C-classified company (even a consumer insurer with a
    secondary group line, e.g. Aegis) ruled out at step 1, before any paid score — a secondary B2B
    line no longer rescues a primarily-B2C company. `has_b2b_line` is still classified + stored for
    reference, just no longer consulted here."""
    m = (business_model or "").strip()
    if m == "Complex":
        return "B2B"
    return m


def _host(website: str | None) -> str:
    """Bare host of a website (scheme/path/query stripped, leading www. dropped)."""
    h = (website or "").strip().casefold()
    for sep in ("://",):
        if sep in h:
            h = h.split(sep, 1)[1]
    h = h.split("/", 1)[0].split("?", 1)[0].split(":", 1)[0]
    return h[4:] if h.startswith("www.") else h


def _is_aggregator(website: str | None) -> bool:
    host = _host(website)
    if not host:
        return False
    return any(host == agg or host.endswith("." + agg) for agg in AGGREGATOR_HOSTS)


@dataclass(frozen=True)
class RulesConfig:
    """The client's intake rules (spec §5), extracted from the brief/ICP at wiring time (V2-2).

    `market` is the client's target side (`B2B`/`B2C`/`Both`/`None`); `Both`/`None` disables the
    market rule. `geographies` are the allowed HQ countries (compared case-folded, against the
    description-derived country). `excluded_*` are the client's "who to avoid" set (spec's
    `excluded_companies`), matched on either normalized name or domain."""

    market: str | None = None
    geographies: tuple[str, ...] = ()
    excluded_names: frozenset[str] = frozenset()
    excluded_domains: frozenset[str] = frozenset()


@dataclass
class Verdict:
    """The deterministic outcome for one row. `label=None` = survived every gate but not yet scored
    ("needs re-score" — V2-1, before the paid call). `reason` is always populated for a decided
    label; `flags` accumulate regardless of the deciding gate. `icp`/`score_total`/`subscores` are
    set only when a subscore was supplied (V2-2)."""

    label: str | None
    reason: str
    flags: list[str] = field(default_factory=list)
    icp: str | None = None
    score_total: int | None = None
    subscores: dict[str, int] | None = None


# --- gates (each returns (label, reason) on a hit, else None) -----------------
def liveness_gate(liveness: dict | None) -> tuple[str, str] | None:
    """Spec §4 — the web-search verdict `{"status": ...}` where status is one of
    defunct/acquired/dead_web/stale/live. defunct/acquired/dead_web → excluded_by_rules;
    stale/live/None never exclude (stale adds a flag, in `deterministic_flags`). None = V2-1."""
    if not liveness:
        return None
    status = _norm(liveness.get("status"))
    if status == "defunct":
        return EXCLUDED, REASON_DEFUNCT
    if status == "acquired":
        return EXCLUDED, REASON_ACQUIRED
    if status in ("dead_web", "parked", "no_web"):
        return EXCLUDED, REASON_NO_WEB
    return None


def rules_gate(
    *,
    business_model: str | None,
    has_b2b_line: bool,
    hq_country: str | None,
    field_country: str | None = None,
    name: str | None,
    domain: str | None,
    config: RulesConfig,
) -> tuple[str, str] | None:
    """Spec §5 — the client-defined rules: market (Complex→B2B; the Luma B2B-line guard was removed
    2026-07-10), geography, and the client exclusion list.

    Geography is checked against BOTH the description-derived `hq_country` AND Apollo's
    `field_country` HQ field: the company search was geo-filtered, so Apollo's country is
    authoritative even when the description names a founding/parent country elsewhere (e.g. an
    India-founded firm HQ'd in Singapore — Apollo says Singapore, the description says India). A row
    is excluded only when at least one country is known and NONE of the known countries is in the
    target set (fail-open — a null country falls through to the data check)."""
    market = _effective_market(business_model, has_b2b_line)
    if config.market in ("B2B", "B2C") and market in ("B2B", "B2C") and market != config.market:
        return EXCLUDED, REASON_RULE_MARKET[config.market]
    if config.geographies:
        allowed = {_norm(g) for g in config.geographies}
        candidates = [c for c in (hq_country, field_country) if c and c.strip()]
        if candidates and not any(_norm(c) in allowed for c in candidates):
            return EXCLUDED, REASON_RULE_GEO
    if config.excluded_names and _norm(name) in config.excluded_names:
        return EXCLUDED, REASON_RULE_EXCLUSION
    if config.excluded_domains and _norm(domain) in config.excluded_domains:
        return EXCLUDED, REASON_RULE_EXCLUSION
    return None


def data_gate(
    *, industry: str | None, hq_country: str | None, website: str | None
) -> tuple[str, str] | None:
    """Spec §6 — data check → low_fit `data_unusable` when the row can't be judged: no industry, no
    country, or a wire-service/aggregator website. Headcount is NOT a gate (unreliable field)."""
    if _norm(industry) in _EMPTY_INDUSTRY:
        return LOW_FIT, REASON_DATA_UNUSABLE
    if not (hq_country and hq_country.strip()):
        return LOW_FIT, REASON_DATA_UNUSABLE
    if _is_aggregator(website):
        return LOW_FIT, REASON_DATA_UNUSABLE
    return None


def size_gate(*, headcount: int | None, size_ceiling: int | None) -> tuple[str, str] | None:
    """Spec §7 + founder 2026-07-09 — size rule → low_fit `too large` when headcount exceeds the ICP
    band's ceiling. Never a hard exclusion (headcount data can't carry one). The former
    `headcount_uncertain` suppression was removed in D+.5/R11 — only one headcount source exists, so
    the "sources disagree" flag was never producible."""
    if headcount is None or size_ceiling is None:
        return None
    if headcount > size_ceiling:
        return LOW_FIT, REASON_TOO_LARGE
    return None


def icp_gate(icp_match: dict | None) -> tuple[str, str] | None:
    """Spec §7 — ICP match (from the V2-2 score call): `{"icp": "A"|"B"|None, "reason": "..."}`.
    No match (`icp` falsy) → low_fit `wrong vertical`. None arg = not scored yet (V2-1)."""
    if icp_match is None:
        return None
    if not icp_match.get("icp"):
        return LOW_FIT, REASON_WRONG_VERTICAL
    return None


def deterministic_flags(
    *,
    description_country: str | None,
    field_country: str | None,
    liveness: dict | None,
    extra_flags: list[str] | None,
) -> list[str]:
    """Flags computable without the LLM: `hq_mismatch` (description vs Apollo HQ field disagree),
    `stale_record` (liveness says the last news item is >24mo old). `extra_flags` carries flags the
    V2-2 score call already found (partner_led, revenue_implausible, …), de-duped in spec order."""
    found: set[str] = set(f for f in (extra_flags or []) if f in FLAGS)
    if (
        description_country and field_country
        and _norm(description_country) != _norm(field_country)
    ):
        found.add(FLAG_HQ_MISMATCH)
    if liveness and _norm(liveness.get("status")) == "stale":
        found.add(FLAG_STALE_RECORD)
    # Return in the spec §10 declaration order for a stable UI marker order.
    return [f for f in (
        FLAG_HQ_MISMATCH, FLAG_REVENUE_IMPLAUSIBLE,
        FLAG_FOUNDING_DATE_CONFLICT, FLAG_COMPETITOR_ADJACENT, FLAG_PARTNER_LED, FLAG_STALE_RECORD,
    ) if f in found]


def _icp_reason(icp: str | None) -> str:
    return f"fits ICP {icp}" if icp else REASON_WRONG_VERTICAL


def assign_label(
    *,
    # stage-0 classification (LLM at find time)
    business_model: str | None = None,
    has_b2b_line: bool = False,
    hq_country: str | None = None,
    # firmographics
    industry: str | None = None,
    website: str | None = None,
    name: str | None = None,
    domain: str | None = None,
    field_country: str | None = None,
    headcount: int | None = None,
    # client rules
    config: RulesConfig | None = None,
    size_ceiling: int | None = None,
    # paid signals (None in V2-1)
    liveness: dict | None = None,
    icp_match: dict | None = None,
    subscores: dict | None = None,
    extra_flags: list[str] | None = None,
) -> Verdict:
    """Walk the spec §3 processing order and return the first-matching `Verdict`.

    Free deterministic gates (rules → data → size) always run; the paid gates (liveness, ICP, score)
    only contribute when their signal is supplied. A row that clears every gate with no subscore
    returns `label=None` (needs re-score); with a subscore it is scored via `label_from_score`.
    `field_country` is the Apollo HQ field — description-derived `hq_country` wins where both exist
    (spec §5), so the effective country is `hq_country or field_country`."""
    config = config or RulesConfig()
    flags = deterministic_flags(
        description_country=hq_country, field_country=field_country,
        liveness=liveness, extra_flags=extra_flags,
    )
    eff_country = hq_country or field_country

    for hit in (
        liveness_gate(liveness),
        rules_gate(
            business_model=business_model, has_b2b_line=has_b2b_line,
            hq_country=hq_country, field_country=field_country,
            name=name, domain=domain, config=config,
        ),
        data_gate(industry=industry, hq_country=eff_country, website=website),
        size_gate(headcount=headcount, size_ceiling=size_ceiling),
        icp_gate(icp_match),
    ):
        if hit is not None:
            return Verdict(label=hit[0], reason=hit[1], flags=flags)

    # Survived every gate → score if a subscore was supplied (V2-2), else "needs re-score" (V2-1).
    if subscores is not None:
        total, clean = collapse_subscores(subscores)
        icp = (icp_match or {}).get("icp")
        reason = (icp_match or {}).get("reason") or _icp_reason(icp)
        return Verdict(
            label=label_from_score(total), reason=reason, flags=flags,
            icp=icp, score_total=total, subscores=clean,
        )
    return Verdict(label=None, reason="", flags=flags)


# --- people tier (V2-2) -------------------------------------------------------
def _cap_by_company(person_label: str, company_label: str | None) -> str:
    """A person can never be MORE contactable than their company (spec people-tier). Cap = the
    lower-priority (higher LABEL_ORDER index) of the two — company `low_fit` forces the person
    `low_fit`, company `contact_soon` forbids `contact_now`, company `contact_now` caps nothing."""
    if not company_label or company_label not in LABEL_ORDER:
        return person_label
    return LABELS[max(LABEL_ORDER[person_label], LABEL_ORDER[company_label])]


def assign_person_label(
    *,
    company_label: str | None,
    title: str | None = None,
    has_contact: bool = False,
    avoid_titles: tuple[str, ...] = (),
    subscores: dict | None = None,
    reason: str = "",
    flags: list[str] | None = None,
) -> Verdict:
    """People tier — the company label caps the person (spec people-tier; OUR extrapolation).

    Order: parent `excluded_by_rules` → the person is `excluded_by_rules "parent company excluded"`
    (no per-person web/score spend); an avoided title → `excluded_by_rules`; a missing title or no
    contact path → `low_fit "data_unusable"`; else score the four people axes (persona_fit /
    authority / trigger / reachability) and cap the result by the company band. `subscores=None` =
    not yet scored (`label=None`, needs re-score)."""
    flags = [f for f in (flags or []) if f in FLAGS]
    if company_label == EXCLUDED:
        return Verdict(label=EXCLUDED, reason=REASON_PARENT_EXCLUDED, flags=flags)
    # Shared normalize+match with find.filter_people — "Sales Intern" caught by an "intern" avoid.
    if title_is_avoided(title, avoid_titles):
        return Verdict(label=EXCLUDED, reason=REASON_AVOIDED_TITLE, flags=flags)
    if not (title and title.strip()) or not has_contact:
        return Verdict(label=LOW_FIT, reason=REASON_DATA_UNUSABLE, flags=flags)
    if subscores is None:
        return Verdict(label=None, reason="", flags=flags)
    total, clean = collapse_subscores(subscores, SUBSCORE_AXES_PEOPLE)
    label = _cap_by_company(label_from_score(total), company_label)
    return Verdict(
        label=label, reason=reason or "", flags=flags, score_total=total, subscores=clean
    )


# --- rules config extraction (V2-2 wiring seam, pure) -------------------------
def _geographies_from_spec(spec_data: dict | None) -> tuple[str, ...]:
    """The client's target HQ countries = the `organization_locations` the company search targeted
    (Apollo HQ filter; research_spec.py). Gathered from the spec's `company_search_params` and any
    per-ICP blocks. Empty → the geography rule is disabled (fail-open — never a false exclusion)."""
    spec_data = spec_data or {}
    found: list[str] = []
    seen: set[str] = set()

    def _collect(block: object) -> None:
        if isinstance(block, dict):
            for loc in block.get("organization_locations") or []:
                key = _norm(str(loc))
                if key and key not in seen:
                    seen.add(key)
                    found.append(str(loc))
            for v in block.values():
                _collect(v)
        elif isinstance(block, list):
            for v in block:
                _collect(v)

    _collect(spec_data)
    return tuple(found)


def size_ceiling_from_spec(spec_data: dict | None) -> int | None:
    """The size-rule ceiling = the max upper bound across the spec's `organization_num_employees_
    ranges` (Apollo `"lo,hi"` strings). Client-wide + conservative: a row is only `too large` if it
    exceeds even the largest targeted band, so the rule never over-fires across mixed ICP sizes.
    None when the spec sets no employee range → the size gate is disabled (spec §7 fail-open)."""
    spec_data = spec_data or {}
    best: int | None = None

    def _collect(block: object) -> None:
        nonlocal best
        if isinstance(block, dict):
            for rng in block.get("organization_num_employees_ranges") or []:
                parts = str(rng).replace("-", ",").split(",")
                if len(parts) == 2 and parts[1].strip().isdigit():
                    hi = int(parts[1].strip())
                    best = hi if best is None else max(best, hi)
            for v in block.values():
                _collect(v)
        elif isinstance(block, list):
            for v in block:
                _collect(v)

    _collect(spec_data)
    return best


def build_rules_config(
    brief_data: dict | None,
    spec_data: dict | None,
    *,
    excluded_domains: tuple[str, ...] = (),
    excluded_names: tuple[str, ...] = (),
) -> RulesConfig:
    """Assemble the client's `RulesConfig` (spec §5) from the brief + research spec + exclusion set.
    Pure — the router fetches the rows and the `ExclusionSet` domains, this maps them. `market` only
    gates for a B2B/B2C target (Both/None disables it); geographies come from the spec's search HQ
    filter; the excluded set is the client's 'who to avoid' (decision ⑧-B: labeled, not dropped)."""
    market = (brief_data or {}).get("targetMarket")
    return RulesConfig(
        market=market if market in ("B2B", "B2C", "Both") else None,
        geographies=_geographies_from_spec(spec_data),
        excluded_domains=frozenset(_norm(d) for d in excluded_domains if d),
        excluded_names=frozenset(_norm(n) for n in excluded_names if n),
    )


__all__ = [
    "CONTACT_NOW", "CONTACT_SOON", "LOW_FIT", "EXCLUDED", "LABELS", "LABEL_ORDER",
    "SUBSCORE_AXES", "SUBSCORE_AXES_PEOPLE", "FLAGS", "MODEL_FLAGS", "RulesConfig", "Verdict",
    "label_from_score", "collapse_subscores", "assign_label", "assign_person_label",
    "build_rules_config", "size_ceiling_from_spec", "liveness_gate", "rules_gate", "data_gate",
    "size_gate", "icp_gate", "deterministic_flags", "title_is_avoided",
]
