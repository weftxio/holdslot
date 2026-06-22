"""Phase C unit tests — the pure suppression / identity / scoring logic (no DB, no net).

These cover the parts that must be testable independently of transport: the suppression gate,
identity-key dedupe, and the deterministic fit collapse. The integration paths (manual add,
score) are exercised by the gated DB tests like test_briefs_icps.
"""

from __future__ import annotations

from app.domains.prospects import fit
from app.domains.prospects.identity import identity_key, normalize_domain
from app.domains.prospects.suppression import (
    Candidate,
    ExclusionSet,
    extract_exclusions,
    suppress,
)

# --------------------------------------------------------------------------- identity


def test_identity_key_precedence_and_normalization():
    # LinkedIn slug wins and is lowercased / de-noised.
    assert (
        identity_key(linkedin_url="https://www.LinkedIn.com/in/Jane-Doe/?x=1", domain="acme.com")
        == "li:jane-doe"
    )
    # Falls back to domain|last|first; domain is normalized (scheme/www/path stripped).
    assert (
        identity_key(domain="https://www.Acme.com/team", first_name="Jane", last_name="Doe")
        == "dlf:acme.com|doe|jane"
    )
    # full_name is split only when explicit names are absent.
    assert identity_key(domain="acme.com", full_name="Jane Q Doe") == "dlf:acme.com|doe|jane"
    # Email is the last resort.
    assert identity_key(email="Jane@Acme.com") == "email:jane@acme.com"
    # Nothing to key on.
    assert identity_key(full_name="Acme") == ""


def test_normalize_domain_handles_email_and_port():
    assert normalize_domain("HTTP://www.Acme.com:443/path?q=1") == "acme.com"
    assert normalize_domain("jane@acme.com") == "acme.com"


# --------------------------------------------------------------------------- exclusions (C0.4)


def test_extract_exclusions_from_brief_text_and_spec():
    brief = {
        "excludeCustomers": "acme.com, Acme Inc, https://acme.com\nbeta.io, Beta",
        "excludeDeals": "gamma.co, Gamma Corp",
        "doNotContact": "ceo@delta.com\nlinkedin.com/in/blocked-person",
        "competitors": "Just A Name With No Domain",
    }
    spec = {
        "exclusions": {
            "domains": ["epsilon.com"],
            "emails": ["x@zeta.com"],
            "company_linkedin_urls": ["https://linkedin.com/company/zzz"],
        }
    }
    ex = extract_exclusions(brief, spec)
    assert {"acme.com", "beta.io", "gamma.co", "epsilon.com"} <= ex.domains
    assert "ceo@delta.com" in ex.emails and "x@zeta.com" in ex.emails
    assert "blocked-person" in ex.linkedin_slugs
    # A bare company name (no dot) is NOT treated as a domain.
    assert all("." in d for d in ex.domains)


# --------------------------------------------------------------------------- suppression (C2)


def test_suppress_drops_excluded_dupes_and_unkeyable():
    ex = ExclusionSet(domains={"acme.com"}, emails={"vip@beta.io"}, linkedin_slugs={"blocked"})
    cands = [
        Candidate(full_name="A One", domain="acme.com"),  # excluded_domain
        Candidate(full_name="B Two", domain="good.com", email="vip@beta.io"),  # excluded_email
        Candidate(full_name="C Three", linkedin_url="linkedin.com/in/blocked"),  # excluded_linkedin
        Candidate(full_name="D Four", domain="good.com"),  # survivor
        Candidate(full_name="D Four", domain="good.com"),  # duplicate of prev
        Candidate(company="No Identity"),  # no_identity_key
    ]
    res = suppress(cands, ex)
    assert [c.full_name for c in res.survivors] == ["D Four"]
    reasons = sorted(r for _c, r in res.dropped)
    assert reasons == [
        "duplicate",
        "excluded_domain",
        "excluded_email",
        "excluded_linkedin",
        "no_identity_key",
    ]


def test_suppress_respects_already_seen_keys():
    cand = Candidate(full_name="Jane Doe", domain="acme.com")
    res = suppress([cand], ExclusionSet(), seen_identity_keys={cand.identity_key})
    assert res.survivors == [] and res.dropped[0][1] == "duplicate"


# --------------------------------------------------------------- company fit collapse (stage 1)


def test_collapse_company_omits_persona_and_normalizes_to_100():
    # Full company+timing+data (persona is out of scope at stage 1) → 70/70 → 100 → Strong.
    components = {
        "company": {"industry": 99, "size": 12, "maturity": 8, "tech": 4},  # clamps to 40
        "timing": {"primary_trigger": 12, "secondary_signal": 6, "engagement": 2},  # 20
        "data": {"email_deliverability": 6, "profile_completeness": 4},  # 10
    }
    score, tier, normalized = fit.collapse_company(components)
    assert score == 100 and tier == "Strong"
    assert normalized["company"]["industry"] == 16  # clamped to its max
    assert "persona" not in normalized  # persona omitted at company stage

    # Company-only (40/70) normalizes to 57 → Good.
    company_only = {"company": {"industry": 16, "size": 12, "maturity": 8, "tech": 4}}
    score2, tier2, _ = fit.collapse_company(company_only)
    assert score2 == 57 and tier2 == "Good"


def test_company_fit_schema_is_strict_and_company_scoped():
    schema = fit.COMPANY_FIT_JSON_SCHEMA["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]["components"]["properties"]) == {"company", "timing", "data"}


# --------------------------------------------------------------------------- fit collapse (C3)


def test_fit_collapse_clamps_caps_and_tiers():
    # Over-max sub-scores are clamped; each dimension capped; total drives the tier.
    components = {
        "company": {"industry": 99, "size": 12, "maturity": 8, "tech": 4},  # clamps to 40
        "persona": {"title": 14, "seniority": 8, "department": 5, "economic_buyer": 3},  # 30
        "timing": {"primary_trigger": 12, "secondary_signal": 6, "engagement": 2},  # 20
        "data": {"email_deliverability": 6, "profile_completeness": 4},  # 10
    }
    score, tier, normalized = fit.collapse(components)
    assert score == 100 and tier == "Strong"
    assert normalized["company"]["industry"] == 16  # clamped to its max

    assert fit.tier_for(74) == "Good" and fit.tier_for(54) == "Moderate"
    assert fit.tier_for(39) == "Below"


def test_fit_collapse_tolerates_missing_components():
    score, tier, normalized = fit.collapse({})
    assert score == 0 and tier == "Below"
    assert normalized["company"]["industry"] == 0


def test_fit_schema_is_strict():
    schema = fit.FIT_JSON_SCHEMA["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"components", "reasons", "reason_tags", "fit_reason"}
