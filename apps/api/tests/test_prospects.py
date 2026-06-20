"""Phase C unit tests — the pure suppression / identity / ingest / scoring logic (no DB, no net).

These cover the parts the C2/C3 DoD says must be testable independently of transport: the
suppression gate, identity-key dedupe, the Clay CSV contract, the deterministic fit collapse,
and the sourcing liveness gate. The integration paths (push, score, round) are exercised by the
gated DB tests like test_briefs_icps.
"""

from __future__ import annotations

from app.domains.prospects import clay, fit, sourcing
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


# ----------------------------------------------------------------- Clay push + CSV (C2/C3)


def test_assemble_push_row_includes_keys_and_drops_empties():
    c = Candidate(
        full_name="Jane Doe", company="Acme", domain="https://www.acme.com", target_seniority="VP"
    )
    row = clay.assemble_push_row(c, run_id="run123")
    assert row["run_id"] == "run123"
    assert row["identity_key"] == "dlf:acme.com|doe|jane"
    assert row["domain"] == "acme.com"
    assert "email" not in row and "company_industry" not in row  # empty optionals dropped


def test_parse_export_csv_coalesces_per_contract():
    header = (
        "Webhook,run_id,identity_key,full_name,first_name,last_name,company,company_industry,"
        "domain,linkedin_url,target_titles,target_seniority,email,Work Email Data Provider,"
        "Work Email,Enrich person,Name,Title,Org,Enrich Company,Name (2),Website,Employee Count,"
        "Industry,Size,Country,Locality,Annual Revenue,Validate Findymail"
    )
    # email gate blank → coalesce to Work Email; company_industry gate blank → coalesce Industry.
    row = (
        "grp,run123,dlf:acme.com|doe|jane,Jane Doe,Jane,Doe,Acme,,acme.com,,VP Eng,VP,,Findymail,"
        "jane@acme.com,grp,Jane Doe,VP Engineering,Acme,grp,Acme,acme.com,250,Software,"
        "201-500,US,SF,10M,valid"
    )
    rows = clay.parse_export_csv(header + "\n" + row + "\n")
    assert len(rows) == 1
    er = rows[0]
    assert er.email == "jane@acme.com" and er.provider == "Findymail" and er.email_valid is True
    assert er.title == "VP Engineering" and er.seniority == "VP"
    assert er.company_industry == "Software" and er.company_size == "201-500"
    assert er.domain == "acme.com" and er.company_domain == "acme.com"
    assert er.enrichment.get("Country") == "US" and er.enrichment.get("Annual Revenue") == "10M"


def test_parse_export_csv_skips_rows_without_correlation_keys():
    header = "run_id,identity_key,full_name,domain,email,Validate Findymail"
    rows = clay.parse_export_csv(header + "\n,,Nobody,acme.com,,\n")
    assert rows == []


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


# --------------------------------------------------------------------------- sourcing validate (C5)


def test_validate_candidates_requires_domain_person_and_evidence():
    good = {
        "company": {"name": "Acme", "domain": "acme.com", "vertical_source_url": "https://x"},
        "person": {"full_name": "Jane Doe", "profile_url": "https://li/in/jane"},
        "timing": {"primary_trigger": {"source_url": "https://news"}},
    }
    no_domain = {"company": {"name": "X"}, "person": {"full_name": "Y"}}
    no_person = {"company": {"domain": "b.com", "vertical_source_url": "u"}, "person": {}}
    no_evidence = {"company": {"domain": "c.com"}, "person": {"full_name": "Z"}}
    valid, rejected = sourcing.validate_candidates([good, no_domain, no_person, no_evidence])
    assert valid == [good]
    assert sorted(r for _x, r in rejected) == ["no_domain", "no_evidence", "no_person"]


def test_to_candidate_maps_evidence_shape():
    raw = {
        "company": {"name": "Acme", "domain": "https://acme.com", "vertical": "SaaS"},
        "person": {
            "full_name": "Jane Doe",
            "title": "VP Eng",
            "seniority": "VP",
            "profile_url": "https://www.linkedin.com/in/jane-doe",
        },
    }
    c = sourcing.to_candidate(raw)
    assert c.domain == "acme.com" and c.company_industry == "SaaS"
    assert c.identity_key == "li:jane-doe"
