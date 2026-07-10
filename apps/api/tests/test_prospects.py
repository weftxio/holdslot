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


# --------------------------------------------------------------- stage-0 business-model classifier


def test_business_model_schema_is_three_v2_fields():
    # Scoring v2 (spec §5): the stage-0 classifier stays tiny but now returns the B2B/B2C enum plus
    # the two facts the v2 rules engine needs — description-derived hq_country + has_b2b_line.
    schema = fit.BUSINESS_MODEL_SCHEMA["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"business_model", "hq_country", "has_b2b_line"}
    assert schema["properties"]["business_model"]["enum"] == ["B2B", "B2C", "Complex", "Unknown"]
    assert schema["properties"]["hq_country"]["type"] == "string"
    assert schema["properties"]["has_b2b_line"]["type"] == "boolean"


class _StubResult:
    """A structured_completion result stand-in (score_company reads .data + telemetry fields)."""

    def __init__(self, data: dict):
        self.data = data
        self.llm_call_id = "call-1"
        self.model = "stub-model"
        self.cost_usd = 0.0


def _stub_company_call(monkeypatch, data: dict):
    monkeypatch.setattr(fit, "structured_completion", lambda **kw: _StubResult(data))


def test_classify_business_model_returns_label(monkeypatch):
    # The stage-0 classifier reads the single enum out of its own minimal call.
    _stub_company_call(monkeypatch, {"business_model": "Complex"})
    out = fit.classify_business_model(tenant_id="t", company={"domain": "x.example"})
    assert out["business_model"] == "Complex"


def test_model_messages_stay_minimal():
    # Token minimization: the classifier prompt carries NO rubric / targeting, unlike company_fit.
    msgs = fit.build_model_messages({"domain": "x.example", "short_description": "sells shoes"})
    assert len(msgs) == 2 and msgs[0]["role"] == "system"
    joined = msgs[0]["content"] + msgs[1]["content"]
    assert "RUBRIC" not in joined and "TARGETING" not in joined
