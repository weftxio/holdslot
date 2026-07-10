"""Scoring v2 — the two paid score calls (fit.company_score_v2 / prospect_score_v2).

The LLM transport is monkeypatched (no network, no DB), so these assert the strict-schema SHAPES and
the normalization each fn does on the raw completion — the seam that feeds `labeling.assign_label` /
`assign_person_label`. The end-to-end label ladder itself is covered in test_labeling.
"""

from __future__ import annotations

import uuid

from app.domains.prospects import fit
from app.integrations.openrouter.client import StructuredResult


def _stub(monkeypatch, payload: dict):
    """Make `structured_completion` return `payload` as the parsed data, no network."""

    def fake(**kwargs):
        return StructuredResult(
            data=payload, llm_call_id="00000000-0000-0000-0000-000000000000",
            model="deepseek/deepseek-v4-pro", cost_usd=0.001,
        )

    monkeypatch.setattr(fit, "structured_completion", fake)


# --- schema invariants --------------------------------------------------------
def test_company_score_v2_schema_shape():
    s = fit.COMPANY_SCORE_V2_SCHEMA["schema"]
    assert s["additionalProperties"] is False
    assert set(s["required"]) == {
        "liveness", "deal_fit", "outbound_gap", "trigger", "reachability",
        "icp_match", "reason", "trigger_line", "flags",
    }
    assert s["properties"]["liveness"]["properties"]["status"]["enum"] == [
        "live", "defunct", "acquired", "dead_web", "stale",
    ]
    # The default/base shape is 2-ICP.
    assert s["properties"]["icp_match"]["properties"]["icp"]["enum"] == ["A", "B", "none"]


def test_company_score_v2_schema_icp_enum_is_dynamic():
    """R19 — the icp enum is built from the tenant's ICP count (+ "none"), so a 3rd/4th ICP is a
    valid answer instead of being structurally forced to "none"."""
    three = fit.company_score_v2_schema(["A", "B", "C"])
    assert three["schema"]["properties"]["icp_match"]["properties"]["icp"]["enum"] == [
        "A", "B", "C", "none",
    ]
    # A no-ICP tenant → only "none" is valid.
    zero = fit.company_score_v2_schema([])
    assert zero["schema"]["properties"]["icp_match"]["properties"]["icp"]["enum"] == ["none"]


def test_prospect_score_v2_schema_shape():
    s = fit.PROSPECT_SCORE_V2_SCHEMA["schema"]
    assert s["additionalProperties"] is False
    assert set(s["required"]) == {
        "persona_fit", "authority", "trigger", "reachability", "reason", "flags",
    }


def test_v2_uses_new_prompt_stages_not_v1():
    # New stages so the v1 company_fit/prospect_fit rubrics stay intact through the cutover.
    assert fit.COMPANY_SCORE_STAGE == "company_score"
    assert fit.PROSPECT_SCORE_STAGE == "prospect_score"
    assert fit.COMPANY_SCORE_PURPOSE == "company_score_v2"


def test_company_score_v2_call_is_web_grounded():
    # Liveness needs live sources — the web plugin must ride the (non-US) host pin.
    assert fit.COMPANY_SCORE_V2_EXTRA_BODY["plugins"] == [{"id": "web"}]
    assert fit.SCORE_V2_TIMEOUT > 30  # async path only (exceeds the 30s gateway)
    # People scoring takes NO web (the token win).
    assert "plugins" not in fit.PROSPECT_SCORE_V2_EXTRA_BODY


# --- normalization ------------------------------------------------------------
def test_company_score_v2_normalizes_signals(monkeypatch):
    _stub(monkeypatch, {
        "liveness": {"status": "defunct", "note": "in liquidation since Sept 2025"},
        "deal_fit": 3, "outbound_gap": 5, "trigger": 4, "reachability": 5,
        "icp_match": {"icp": "A", "clause": "insurtech, word of mouth"},
        "reason": "fits ICP A — grown purely through word of mouth",
        "trigger_line": "Celent Luminary, no SDR function",
        "flags": ["partner_led", "not_a_real_flag"],
    })
    out = fit.company_score_v2(tenant_id=uuid.uuid4(), rubric_body="", company={}, targeting={})
    assert out["liveness"]["status"] == "defunct"
    assert out["subscores"] == {"deal_fit": 3, "outbound_gap": 5, "trigger": 4, "reachability": 5}
    assert out["icp_match"] == {"icp": "A", "reason": out["reason"]}
    assert out["trigger_line"] == "Celent Luminary, no SDR function"
    assert out["flags"] == ["partner_led"]  # unknown flag dropped


def test_company_score_v2_icp_none_maps_to_null(monkeypatch):
    _stub(monkeypatch, {
        "liveness": {"status": "live", "note": ""},
        "deal_fit": 2, "outbound_gap": 2, "trigger": 1, "reachability": 2,
        "icp_match": {"icp": "none", "clause": "robotics — not a listed vertical"},
        "reason": "wrong vertical", "trigger_line": "", "flags": [],
    })
    out = fit.company_score_v2(tenant_id=uuid.uuid4(), rubric_body="", company={}, targeting={})
    assert out["icp_match"]["icp"] is None  # "none" → null → labeling marks wrong vertical


def test_prospect_score_v2_normalizes(monkeypatch):
    _stub(monkeypatch, {
        "persona_fit": 5, "authority": 4, "trigger": 3, "reachability": 4,
        "reason": "Head of Sales — economic buyer", "flags": [],
    })
    out = fit.prospect_score_v2(tenant_id=uuid.uuid4(), rubric_body="", enrichment={}, targeting={})
    assert out["subscores"] == {
        "persona_fit": 5, "authority": 4, "trigger": 3, "reachability": 4,
    }
    assert out["reason"] == "Head of Sales — economic buyer"
