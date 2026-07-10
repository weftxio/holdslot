"""Fit scoring — the scoring door (C3 ⭐), scoring v2 (docs/initial-build-plan.md §D+.2).

Two paid LLM calls feed the deterministic label engine (`labeling.py`); the v1 0–100 `fit_score`
grid was retired in V2-4 (this module used to also carry `score`/`score_company`/`collapse`/the
market gate — all deleted). What remains:

* **Business model** (stage 0, `classify_business_model`): a deliberately tiny call (its own split
  system + input prompt) that labels each company B2B / B2C / Complex / Unknown and reads two facts
  the v2 rule engine needs but Apollo gets wrong — `hq_country` (HQ from the description) and
  `has_b2b_line` (classified + stored; the former B2C-with-a-B2B-line "Luma guard" carve-out was
  removed 2026-07-10). Runs up-front on EVERY find-company / find-lookalike / manual-add row so the
  label + market gate are present BEFORE any (on-demand, paid) scoring.
* **Company score v2** (stage 1, `company_score_v2`): ONE web-grounded call — liveness + the four
  axes + icp_match + flags + trigger_line. Slow (~50–120s), async path only.
* **Prospect score v2** (stage 2, `prospect_score_v2`): the no-web people-axis call; the company
  label caps the person.

Routing (see initial-build-plan §"Model usage" / §Model selection): non-US providers only (the
Gemini/OpenAI fallback is geo-blocked, 403 ToS; see openrouter/client.py). Company/prospect scoring
= **DeepSeek V4 Pro**; the stage-0 classifier = **DeepSeek V4 Flash** (A/B-switched 2026-07-10 — the
paid ranking call stays on Pro). The deterministic gates (`labeling.py`) run FIRST, so a paid call
only fires for a gate-survivor.
"""

from __future__ import annotations

import logging

from app.domains.prospects import labeling
from app.integrations.openrouter.client import LlmError, structured_completion

log = logging.getLogger("holdslot.fit")

# Stage-0 business-model classifier — deliberately tiny (its own tiny LLM call, see
# classify_business_model). It runs up-front on EVERY find-company / find-lookalike / manual-add row
# so the B2B/B2C label — and the v2 market gate it drives — is present BEFORE any (on-demand, paid)
# scoring. Minimal: no rubric, no targeting, no full firmographics (business_model is a factual,
# client-independent property); it returns a single enum token + two description-derived facts.
MODEL_PURPOSE = "company_model"
# v2 (2026-07): the classifier also reads the DESCRIPTION for two facts the v2 rule engine needs but
# Apollo's fields get wrong — `hq_country` (spec §5: HQ from the description, not the field) and
# `has_b2b_line` (still classified + stored; the "Luma guard" B2C-with-a-B2B-line → `Both` carve-out
# was removed 2026-07-10, so a B2B line no longer rescues a primarily-B2C company).
MODEL_PROMPT_VERSION = "company-model-v2"
# Flash, not Pro (switched 2026-07-10 after a live A/B — see the build plan §Model selection).
# Over all 239 dogfood companies Flash matched Pro's B2B/B2C on 90.8% and — the key metric —
# agreed on the market-GATE outcome (keep vs exclude) 94.6%, erring only toward `keep` (recoverable:
# a wrongly-kept row just scores low_fit at stage 1). hq_country was noisier (71%) but flipped ZERO
# geo-gate outcomes (Apollo's field_country backstops it). Flash is 21× cheaper + 2.3× faster here
# per-find call, no web search so no drift confound. Company SCORING stays on Pro (SCORE_MODELS).
CLASSIFY_MODELS = ["deepseek/deepseek-v4-flash"]
CLASSIFY_EXTRA_BODY = {"temperature": 0, "reasoning": {"enabled": False}}

# Stage-0 business-model classifier schema — three factual, client-independent fields (v2, spec §5):
# the B2B/B2C `business_model` enum, the description-derived `hq_country` (the geography rule reads
# THIS, not Apollo's unreliable HQ field), and `has_b2b_line` (does a B2C firm also sell to
# businesses — the Luma guard keeping a `Both` firm out of the B2C exclusion).
BUSINESS_MODEL_SCHEMA = {
    "name": "BusinessModel",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "business_model": {"type": "string", "enum": ["B2B", "B2C", "Complex", "Unknown"]},
            # Full country name from the DESCRIPTION (e.g. "Singapore", "United States"); "" if the
            # description gives no location. Not the Apollo HQ field — that is known to be wrong.
            "hq_country": {"type": "string"},
            # True only when a B2C-tagged company also has a real business-selling line.
            "has_b2b_line": {"type": "boolean"},
        },
        "required": ["business_model", "hq_country", "has_b2b_line"],
    },
}


def build_model_messages(company: dict) -> list[dict]:
    """Stage-0 classifier prompt — deliberately tiny (token minimization is the whole point): the
    label definitions + ONLY the company's identity/description signals. No rubric, no targeting, no
    full firmographics — `business_model` is a factual, client-independent property."""
    import json

    system = (
        "Classify a company from its description, industries and keywords. Emit THREE fields.\n\n"
        "1. `business_model` — who it sells to (the customer it serves, not its own size):\n"
        "  • B2B — sells primarily to other businesses.\n"
        "  • B2C — sells directly to consumers (e.g. a digital insurer, retail brand, consumer "
        "app/fintech).\n"
        "  • Complex — serves BOTH sides by design: marketplaces, platforms, B2B2C (e.g. Amazon, a "
        "payments network).\n"
        "  • Unknown — too little signal to tell.\n\n"
        "2. `hq_country` — the HQ country stated or clearly implied by the DESCRIPTION (full "
        "country name, e.g. \"Singapore\", \"United States\", \"Canada\"). Read the description, "
        "not any HQ/location field in the data — that field is often wrong. Return \"\" if the "
        "description gives no usable location.\n\n"
        "3. `has_b2b_line` — true ONLY if the company sells to businesses/organizations at all "
        "(group/corporate plans, an enterprise product, an NGO/embassy/school line, a wholesale "
        "or reseller channel). Set it true whenever a B2B line exists even for a mostly-consumer "
        "brand (e.g. a health insurer that writes group cover for companies). For a pure B2B "
        "company it is true; for a pure consumer company it is false.\n\n"
        "Emit ONLY the JSON object with those three fields."
    )
    user = "COMPANY:\n" + json.dumps(company, ensure_ascii=False)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def classify_business_model(*, tenant_id, company: dict) -> dict:
    """Stage-0 — classify a company's B2B/B2C `business_model` + description-derived `hq_country` +
    `has_b2b_line` in one minimal call. Returns those three plus `{llm_call_id, model, cost_usd}`;
    raises `LlmError` on a non-ok call (telemetry already persisted). Client-independent, so it
    takes no rubric/targeting — the caller applies the v2 rules against the brief's config
    separately (labeling.rules_gate). `hq_country`/`has_b2b_line` feed the v2 geo + Luma rules."""
    result = structured_completion(
        tenant_id=tenant_id,
        purpose=MODEL_PURPOSE,
        messages=build_model_messages(company),
        schema=BUSINESS_MODEL_SCHEMA,
        prompt_version=MODEL_PROMPT_VERSION,
        models=CLASSIFY_MODELS,
        extra_body=CLASSIFY_EXTRA_BODY,
    )
    business_model = result.data.get("business_model") or "Unknown"
    hq_country = (result.data.get("hq_country") or "").strip()
    has_b2b_line = bool(result.data.get("has_b2b_line"))
    log.info(
        "business_model classified: model=%s hq=%s b2b_line=%s company=%s llm=%s call=%s",
        business_model, hq_country or "?", has_b2b_line,
        company.get("domain") or company.get("name") or "?",
        result.model,
        result.llm_call_id,
    )
    return {
        "business_model": business_model,
        "hq_country": hq_country,
        "has_b2b_line": has_b2b_line,
        "llm_call_id": result.llm_call_id,
        "model": result.model,
        "cost_usd": result.cost_usd,
    }


# ===========================================================================================
# Scoring v2 (docs/initial-build-plan.md §D+.2) — the two paid score calls that feed the label
# engine (labeling.py). The deterministic gates already ran (rules/data/size) BEFORE these fire, so
# a call only happens for a gate-survivor (cost saver, spec §3 re-order). The functions return the
# raw paid SIGNALS (liveness verdict + subscores + icp_match + flags + trigger_line); the caller
# hands them to `labeling.assign_label` / `assign_person_label`, which owns the final label.
#
# Prompt stages are `company_score` / `prospect_score` (0025 seeds the v2 rubrics). Company scoring
# is web-grounded — it reuses the proven scoping seam (DeepSeek V4 Pro + `plugins:[{id:"web"}]` on
# the Fireworks host pin, verified live via briefs/research_spec.py). It is SLOW (~50–80s/row) and
# MUST run off the 30s gateway (async scoring_job only). People scoring takes NO web search (the
# company dims are already judged; the person inherits + is capped by the company label).
# ===========================================================================================
COMPANY_SCORE_PURPOSE = "company_score_v2"
PROSPECT_SCORE_PURPOSE = "prospect_score_v2"
COMPANY_SCORE_STAGE = "company_score"
PROSPECT_SCORE_STAGE = "prospect_score"
SCORE_RUBRIC_VERSION = "score-rubric-v1"
SCORE_MODELS = ["deepseek/deepseek-v4-pro"]
# Web-grounded liveness + reasoning ON (weigh live sources) — mirrors SCOPING_EXTRA_BODY.
COMPANY_SCORE_V2_EXTRA_BODY = {
    "reasoning": {"enabled": True},
    "plugins": [{"id": "web"}],
    "temperature": 0,
}
# People scoring: no web, thinking OFF (a bounded axis grid).
PROSPECT_SCORE_V2_EXTRA_BODY = {"temperature": 0, "reasoning": {"enabled": False}}
SCORE_V2_TIMEOUT = 120  # Pro + web reasoning budget; async path only (exceeds the 30s gateway)

_AXES_COMPANY = list(labeling.SUBSCORE_AXES)  # deal_fit / outbound_gap / trigger / reachability
_AXES_PEOPLE = list(labeling.SUBSCORE_AXES_PEOPLE)  # persona_fit / authority / trigger / reach


def company_score_v2_schema(icp_letters: list[str]) -> dict:
    """The strict company-score schema, with the `icp_match.icp` enum built from the tenant's ICP
    letters (+ "none"). Dynamic because the enum was hard-coded to ["A","B","none"] (R19): a 3rd+
    ICP couldn't be returned, so the model was structurally forced to "none" → the row landed
    `low_fit "wrong vertical"` AFTER the paid call. `icp_letters` are positional (A, B, C, …), one
    per ICP profile in targeting order."""
    return {
        "name": "CompanyScoreV2",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "liveness": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["live", "defunct", "acquired", "dead_web", "stale"],
                        },
                        "note": {"type": "string"},
                    },
                    "required": ["status", "note"],
                },
                "deal_fit": {"type": "integer"},
                "outbound_gap": {"type": "integer"},
                "trigger": {"type": "integer"},
                "reachability": {"type": "integer"},
                "icp_match": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "icp": {"type": "string", "enum": [*icp_letters, "none"]},
                        "clause": {"type": "string"},
                    },
                    "required": ["icp", "clause"],
                },
                "reason": {"type": "string"},
                "trigger_line": {"type": "string"},
                "flags": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(labeling.MODEL_FLAGS)},
                },
            },
            "required": [
                "liveness", "deal_fit", "outbound_gap", "trigger", "reachability",
                "icp_match", "reason", "trigger_line", "flags",
            ],
        },
    }


# Default/base shape (2 ICPs) — kept for callers/tests that want the static shape; the live call
# builds the enum per tenant via `company_score_v2_schema` (R19).
COMPANY_SCORE_V2_SCHEMA = company_score_v2_schema(["A", "B"])

PROSPECT_SCORE_V2_SCHEMA = {
    "name": "ProspectScoreV2",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "persona_fit": {"type": "integer"},
            "authority": {"type": "integer"},
            "trigger": {"type": "integer"},
            "reachability": {"type": "integer"},
            "reason": {"type": "string"},
            "flags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["persona_fit", "authority", "trigger", "reachability", "reason", "flags"],
    },
}


def build_company_score_v2_messages(rubric_body: str, company: dict, targeting: dict) -> list[dict]:
    """Stage-1 v2 prompt: one web-grounded call that does liveness AND scores the four axes.

    Liveness is the spec's most important addition (§4) — enrichment lags reality by months, so the
    model must check live sources first. The rubric (§8 anchors, founder-editable) is the scoring
    framework; the ICP definitions ride in the targeting context."""
    import json

    system = (
        "You are HoldSlot's COMPANY scorer v2 (stage 1). ONE call, TWO jobs: (A) verify the firm "
        "is still a live, independent business, then (B) score it on four axes. Return ONLY the "
        "JSON schema.\n\n"
        "(A) LIVENESS — do this FIRST. Run a web search for the company (try "
        "\"<company> liquidation OR acquired OR shut down\" and its recent news). Enrichment data "
        "lags reality by months, so trust live sources over the firmographics. Set "
        "`liveness.status`:\n"
        "  • `defunct` — in liquidation, wound up, ceased operations, dissolved.\n"
        "  • `acquired` — absorbed into a parent, no longer independent.\n"
        "  • `dead_web` — website dead or parked.\n"
        "  • `stale` — still trading but no news item in >24 months.\n"
        "  • `live` — active and independent.\n"
        "Put the deciding evidence in `liveness.note`. If defunct/acquired/dead_web the server "
        "excludes the row regardless of score — still fill the axes with your best estimate.\n\n"
        "(B) SCORE — four axes, integer 1–5 each, using the rubric below as the anchor scale:\n"
        "  • `deal_fit` — does the deal size support $500/meeting?\n"
        "  • `outbound_gap` — do they NEED outbound-as-a-service? Judge by how they CURRENTLY "
        "acquire customers (word-of-mouth=5 … named channel partners / investor-as-distributor=1); "
        "score DOWN if they are hiring in-house sales.\n"
        "  • `trigger` — are they in-market now (raise, exec change, new market, rebrand, >20% "
        "growth)?\n"
        "  • `reachability` — can we reach the buyer (founder-led small team=5 … 1000+ "
        "layered=1)?\n\n"
        "ICP MATCH — the targeting context's `icps` lists MULTIPLE profiles, each with its own "
        "`name` (\"ICP A\", \"ICP B\", …) and industry set; they are DIFFERENT businesses (e.g. "
        "A = insurtech / insurance / healthtech / wellness; B = B2B professional services — "
        "executive search, recruiting, IT services, corporate services, agencies, consultancies). "
        "Test the company against EACH profile's industries + persona in turn and match the FIRST "
        "it fits — read the company DESCRIPTION, not the `industries` field (often wrong; e.g. a "
        "recruiting or IT-services firm tagged \"information technology\" still fits ICP B). Set "
        "`icp_match.icp` to the matching profile's letter (the letter in its `name`: \"ICP A\" → "
        "\"A\", \"ICP B\" → \"B\"); use \"none\" ONLY when it fits NEITHER — do NOT default to "
        "ICP A. `icp_match.clause` = the one-clause why. No match → the server marks it "
        "`wrong vertical`.\n\n"
        "`reason` — ONE short client-facing sentence, no number, matching the verdict; for a match "
        "write \"fits ICP A — <clause>\". `trigger_line` — the single most compelling in-market "
        "hook to open a cold email with (or \"\" if none). `flags` — emit any that apply: "
        "revenue_implausible, founding_date_conflict, competitor_adjacent, partner_led, "
        "stale_record.\n\n"
        "=== SCORING RUBRIC (axis anchors, authoritative) ===\n" + rubric_body
    )
    user = (
        "TARGETING CONTEXT (brief / ICP definitions / spec slice):\n"
        + json.dumps(targeting, ensure_ascii=False)
        + "\n\nCOMPANY:\n"
        + json.dumps(company, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_prospect_score_v2_messages(
    rubric_body: str, enrichment: dict, targeting: dict
) -> list[dict]:
    """Stage-2 v2 prompt — score the PERSON on four people axes; NO web search, NO company
    re-judging (the account already cleared stage 1 and carries a label that caps this person)."""
    import json

    system = (
        "You are HoldSlot's PEOPLE scorer v2 (stage 2). The company already cleared stage 1 and "
        "carries a label — do NOT re-judge the company. Score how strongly THIS PERSON is the "
        "right decision-maker to contact, on four axes, integer 1–5 each, using the rubric:\n"
        "  • `persona_fit` — does the title/role match the decision-maker scope we target?\n"
        "  • `authority` — seniority + power to convert a deal (economic buyer > influencer).\n"
        "  • `trigger` — a person-level in-market signal (recent role change, team they are "
        "building, a mandate).\n"
        "  • `reachability` — can we reach them (a real email present, not buried in a layered "
        "org)?\n\n"
        "A field still unknown after enrichment scores low, not high. `reason` — ONE short "
        "client-facing sentence (no number) on why this person is or is not the right contact. "
        "`flags` — only if something is genuinely off; otherwise []. Emit ONLY the JSON schema.\n\n"
        "=== PEOPLE RUBRIC (axis anchors, authoritative) ===\n" + rubric_body
    )
    user = (
        "TARGETING CONTEXT (brief / ICP / spec slice):\n"
        + json.dumps(targeting, ensure_ascii=False)
        + "\n\nPROSPECT (person signals + parent-company label):\n"
        + json.dumps(enrichment, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def company_score_v2(*, tenant_id, rubric_body: str, company: dict, targeting: dict) -> dict:
    """Stage-1 v2 — the web-grounded liveness + 4-axis score call. Returns the normalized paid
    signals for `labeling.assign_label` (NOT a final label): `{liveness, subscores, icp_match,
    reason, trigger_line, flags, llm_call_id, model, cost_usd}`. Raises `LlmError` on a non-ok call.
    Runs on the async path only (SCORE_V2_TIMEOUT ≫ the 30s gateway)."""
    # R19 — build the icp enum from THIS tenant's ICP set (positional A, B, C, … per targeting
    # order), so a 3rd+ ICP can be returned instead of being forced to "none".
    icp_letters = [chr(ord("A") + i) for i in range(len(targeting.get("icps") or []))]
    result = structured_completion(
        tenant_id=tenant_id,
        purpose=COMPANY_SCORE_PURPOSE,
        messages=build_company_score_v2_messages(rubric_body, company, targeting),
        schema=company_score_v2_schema(icp_letters),
        prompt_version=SCORE_RUBRIC_VERSION,
        models=SCORE_MODELS,
        extra_body=COMPANY_SCORE_V2_EXTRA_BODY,
        timeout=SCORE_V2_TIMEOUT,
    )
    d = result.data
    icp_raw = d.get("icp_match") or {}
    icp = icp_raw.get("icp")
    reason = d.get("reason", "") or ""
    signals = {
        "liveness": d.get("liveness") or {"status": "live", "note": ""},
        "subscores": {ax: d.get(ax) for ax in _AXES_COMPANY},
        "icp_match": {"icp": None if icp in (None, "", "none") else icp, "reason": reason},
        "reason": reason,
        "trigger_line": d.get("trigger_line", "") or "",
        "flags": [f for f in (d.get("flags") or []) if f in labeling.FLAGS],
    }
    log.info(
        "company_score_v2: liveness=%s icp=%s subs=%s company=%s llm=%s call=%s",
        signals["liveness"].get("status"), signals["icp_match"]["icp"], signals["subscores"],
        company.get("domain") or company.get("name") or "?", result.model, result.llm_call_id,
    )
    return {**signals, "llm_call_id": result.llm_call_id, "model": result.model,
            "cost_usd": result.cost_usd}


def prospect_score_v2(*, tenant_id, rubric_body: str, enrichment: dict, targeting: dict) -> dict:
    """Stage-2 v2 — the no-web people-axis score call. Returns `{subscores, reason, flags,
    llm_call_id, model, cost_usd}` for `labeling.assign_person_label` (which applies the company-
    label cap). Raises `LlmError` on a non-ok call."""
    result = structured_completion(
        tenant_id=tenant_id,
        purpose=PROSPECT_SCORE_PURPOSE,
        messages=build_prospect_score_v2_messages(rubric_body, enrichment, targeting),
        schema=PROSPECT_SCORE_V2_SCHEMA,
        prompt_version=SCORE_RUBRIC_VERSION,
        models=SCORE_MODELS,
        extra_body=PROSPECT_SCORE_V2_EXTRA_BODY,
    )
    d = result.data
    return {
        "subscores": {ax: d.get(ax) for ax in _AXES_PEOPLE},
        "reason": d.get("reason", "") or "",
        "flags": [f for f in (d.get("flags") or []) if f in labeling.FLAGS],
        "llm_call_id": result.llm_call_id,
        "model": result.model,
        "cost_usd": result.cost_usd,
    }


__all__ = [
    "classify_business_model",
    "company_score_v2",
    "prospect_score_v2",
    "BUSINESS_MODEL_SCHEMA",
    "COMPANY_SCORE_V2_SCHEMA",
    "company_score_v2_schema",
    "PROSPECT_SCORE_V2_SCHEMA",
    "MODEL_PURPOSE",
    "COMPANY_SCORE_PURPOSE",
    "PROSPECT_SCORE_PURPOSE",
    "COMPANY_SCORE_STAGE",
    "PROSPECT_SCORE_STAGE",
    "SCORE_RUBRIC_VERSION",
    "SCORE_MODELS",
    "LlmError",
]
