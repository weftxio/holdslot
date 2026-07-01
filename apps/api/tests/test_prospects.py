"""Phase C unit tests — the pure suppression / identity / scoring logic (no DB, no net).

These cover the parts that must be testable independently of transport: the suppression gate,
identity-key dedupe, and the deterministic fit collapse. The integration paths (manual add,
score) are exercised by the gated DB tests like test_briefs_icps.
"""

from __future__ import annotations

from app.domains.prospects import fit
from app.domains.prospects.identity import identity_key, normalize_domain
from app.domains.prospects.suppression import extract_exclusions

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


# --------------------------------------------------------------- company fit collapse (stage 1)


def test_company_fit_schema_is_verdict_plus_market_label():
    # Company scoring stays minimal: the model returns the verdict (score + reason) plus a factual
    # B2B/B2C `business_model` label — NOT the line-item grid (a reasoning model fills it
    # unreliably). The server derives the tier and applies the market gate from the label.
    schema = fit.COMPANY_FIT_JSON_SCHEMA["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"fit_score", "fit_reason", "business_model"}
    assert set(schema["properties"]) == {"fit_score", "fit_reason", "business_model"}
    assert schema["properties"]["business_model"]["enum"] == ["B2B", "B2C", "Complex", "Unknown"]


def test_company_tier_derives_from_score():
    # The tier policy thresholds apply to the model's 0–100 company score directly.
    assert fit.tier_for(80) == "Strong"
    assert fit.tier_for(60) == "Good"
    assert fit.tier_for(45) == "Moderate"
    assert fit.tier_for(10) == "Below"


# ------------------------------------------------------ company market hard gate (B2B/B2C, stage 1)


class _StubResult:
    """A structured_completion result stand-in (score_company reads .data + telemetry fields)."""

    def __init__(self, data: dict):
        self.data = data
        self.llm_call_id = "call-1"
        self.model = "stub-model"
        self.cost_usd = 0.0


def _stub_company_call(monkeypatch, data: dict):
    monkeypatch.setattr(fit, "structured_completion", lambda **kw: _StubResult(data))


def _score_company(targeting: dict):
    return fit.score_company(
        tenant_id="t", rubric_body="", company={"domain": "x.example"}, targeting=targeting
    )


def test_company_market_gate_excludes_opposite_market(monkeypatch):
    # A B2C company scored for a B2B client is forced into the Below band (0) and stamped — before
    # any person is sourced or enriched. The business_model label is preserved for audit.
    _stub_company_call(
        monkeypatch,
        {"fit_score": 85, "fit_reason": "Strong firmographic fit.", "business_model": "B2C"},
    )
    out = _score_company({"brief": {"targetMarket": "B2B"}})
    assert out["fit_score"] == 0 and out["fit_tier"] == "Below"
    assert out["fit_components"]["market_excluded"] is True
    assert out["fit_components"]["business_model"] == "B2C"
    assert out["fit_reason"].startswith("Excluded: B2C-only company for a B2B client.")


def test_company_market_gate_keeps_matching_market(monkeypatch):
    # A B2B company for a B2B client keeps its verdict; no gate.
    _stub_company_call(
        monkeypatch, {"fit_score": 85, "fit_reason": "Strong fit.", "business_model": "B2B"}
    )
    out = _score_company({"brief": {"targetMarket": "B2B"}})
    assert out["fit_score"] == 85 and out["fit_tier"] == "Strong"
    assert out["fit_components"]["market_excluded"] is False


def test_company_market_gate_ignores_unknown_and_both(monkeypatch):
    # `Unknown` is never gated (a mixed company surfaces for a human); a `Both`/absent targetMarket
    # disables the gate entirely even for a confirmed opposite-market company.
    _stub_company_call(
        monkeypatch, {"fit_score": 70, "fit_reason": "Fits.", "business_model": "Unknown"}
    )
    out = _score_company({"brief": {"targetMarket": "B2B"}})
    assert out["fit_score"] == 70 and out["fit_components"]["market_excluded"] is False

    _stub_company_call(
        monkeypatch, {"fit_score": 70, "fit_reason": "Fits.", "business_model": "B2C"}
    )
    out = _score_company({"brief": {"targetMarket": "Both"}})
    assert out["fit_score"] == 70 and out["fit_components"]["market_excluded"] is False
    out = _score_company({"brief": {}})
    assert out["fit_score"] == 70 and out["fit_components"]["market_excluded"] is False


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
    # `fit_tier`/`fit_score` are model-committed (anchor the reason to the chip); the server still
    # recomputes both authoritatively from `components`.
    assert set(schema["required"]) == {
        "components",
        "reasons",
        "reason_tags",
        "fit_reason",
        "fit_tier",
        "fit_score",
    }
