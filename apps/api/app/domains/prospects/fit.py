"""Fit scoring — the one scoring door (C3 ⭐), driven by the founder-edited rubric.

Two shapes, one rubric (the founder-edited `fit-scoring-rubric-v1.md`):

* **Prospect fit** (stage 2, `score`): the LLM classifies each rubric sub-criterion (full /
  partial / zero) and returns the line-item points; the total + **tier are computed
  deterministically server-side** (thresholds are policy, never LLM-set), each sub-score clamped to
  its max. Storing the components is the moat: one structure, three consumers (approval page,
  billing dispute, learning loop).
* **Company fit** (stage 1, `score_company`): deliberately minimal — the rubric is the model's
  SILENT thinking framework and it returns only the verdict (`fit_score` 0–100 + a short
  `fit_reason`); the server clamps the score and derives the tier from it (`tier_for`). We do NOT
  ask a reasoning model to also emit the line-item grid: it fills that unreliably (decides in the
  thinking trace, then zeroes the grid → every company collapsed to "Below · 0"). Two fields it
  fills well; the tier stays policy.
* **Business model** (stage 0, `classify_business_model`): a separate, deliberately tiny call (its
  own split system + input prompt) that labels each company B2B / B2C / Complex / Unknown. Split out
  of company_fit (2026-07) so it runs up-front on EVERY find-company / find-lookalike / manual-add
  row — the label (and the B2B/B2C market gate it drives) is present BEFORE any on-demand AI
  scoring, not just on scored rows. score_company no longer classifies; it reads the stored label.

Routing (see initial-build-plan §"Model usage"): both stages run on **DeepSeek V4 Pro** at
`temperature=0` — a non-US provider (the Gemini/OpenAI fallback was dropped 2026-06-21 as
geo-blocked, 403 ToS; see openrouter/client.py). Reasoning is tuned per purpose (A/B'd 2026-07, see
the EXTRA_BODY constants): **thinking is OFF for both** — the trace was ~98% of output and drove the
batch timeouts, and DeepSeek's structured output is cleaner without it (company_fit is rubric
classification; prospect_fit's 12-criterion grid filled fine without deliberation). The find/rescore
routes still score a batch in ONE concurrent wave (`_SCORE_WORKERS` = `ASYNC_BATCH_MAX`).
"""

from __future__ import annotations

import logging

from app.integrations.openrouter.client import LlmError, structured_completion

log = logging.getLogger("holdslot.fit")

PURPOSE = "prospect_fit"
COMPANY_PURPOSE = "company_fit"
RUBRIC_VERSION = "fit-rubric-v1"
FIT_MODELS = ["deepseek/deepseek-v4-pro"]
# Reasoning is OFF for both purposes (A/B'd 2026-07 — telemetry showed the thinking trace was ~98%
# of a company_fit call's output, drove ~50s (p95 137s) latency + the batch timeouts, and DeepSeek's
# structured output is more reliable WITHOUT it):
#   • company_fit — thinking OFF. Rubric classification at temperature 0; the model's guidance lives
#     in the (founder-editable) rubric it reads. ~10x faster, ~half the cost, cleaner JSON.
#   • prospect_fit — thinking OFF too. The 12-criterion grid filled fine at LOW effort, but the same
#     trace-heavy latency/cost applied; turning it off keeps scoring fast and the JSON grid clean.
# `temperature=0` on both for determinism.
COMPANY_FIT_EXTRA_BODY = {"temperature": 0, "reasoning": {"enabled": False}}
PROSPECT_FIT_EXTRA_BODY = {"temperature": 0, "reasoning": {"enabled": False}}

# Business-model classifier (stage-0, its own tiny LLM call — see classify_business_model). Split
# out of company_fit (2026-07) so EVERY find-company / find-lookalike / manual-add row carries the
# B2B/B2C label — and is market-gated — BEFORE any (on-demand, paid) AI scoring. It is deliberately
# minimal: no rubric, no targeting, no full firmographics reach it (business_model is a factual,
# client-independent property), and it returns a single enum token. Same region-safe model as
# scoring, thinking OFF + temperature 0 — accuracy without the token/latency of the trace.
MODEL_PURPOSE = "company_model"
MODEL_PROMPT_VERSION = "company-model-v1"
CLASSIFY_MODELS = ["deepseek/deepseek-v4-pro"]
CLASSIFY_EXTRA_BODY = {"temperature": 0, "reasoning": {"enabled": False}}

# The rubric's sub-criteria → their max points (the deterministic caps). Mirrors §2 of the
# rubric doc; the LLM scores each, we clamp to max, cap each dimension at its sum-of-maxes.
DIMENSIONS: dict[str, dict[str, int]] = {
    "company": {"industry": 16, "size": 12, "maturity": 8, "tech": 4},
    "persona": {"title": 14, "seniority": 8, "department": 5, "economic_buyer": 3},
    "timing": {"primary_trigger": 12, "secondary_signal": 6, "engagement": 2},
    "data": {"email_deliverability": 6, "profile_completeness": 4},
}
DIMENSION_MAX = {dim: sum(subs.values()) for dim, subs in DIMENSIONS.items()}  # 40/30/20/10

# Tiers — policy thresholds (rubric §4); tuned as outcome data accumulates, never by the LLM.
_TIERS = (("Strong", 75), ("Good", 55), ("Moderate", 40))

# Market-fit hard gate (partner request, 2026-07): when the brief names a target market (B2B / B2C)
# and stage-1 classifies the company on the OTHER side, it is a structural miss — we bury it into
# the Below band BEFORE any person is sourced or enriched (enrich is the only paid step). The score
# is forced (not trusted to the 0–100 verdict) so the exclusion is deterministic + auditable.
_MARKET_GATE_SCORE = 0


def tier_for(score: int) -> str:
    for name, floor in _TIERS:
        if score >= floor:
            return name
    return "Below"


def apply_market_gate(
    *,
    business_model: str | None,
    target_market: str | None,
    fit_score: int | None,
    fit_reason: str,
) -> tuple[int | None, str | None, bool, str]:
    """Deterministic B2B/B2C hard gate → `(fit_score, fit_tier, market_excluded, fit_reason)`.

    When the company's `business_model` is the strict OPPOSITE of the client's `target_market`,
    force it into the Below band (score 0) and stamp an auditable reason — regardless of any LLM
    score — so it is never selected for people-search (no person sourced, no enrich spend). Only a
    strict B2B/B2C opposite gates: `Both`/absent target, or a `Complex`/`Unknown` model, never do.

    Applied at two moments over the same rule: at find/classify time (`fit_score=None` → an excluded
    row is buried before scoring; a non-excluded row stays unscored, tier None) and at score time
    (`fit_score` set → the tier is derived, or the gate overrides it). Pure + deterministic.
    """
    excluded = (
        target_market in ("B2B", "B2C")
        and business_model in ("B2B", "B2C")
        and business_model != target_market
    )
    if excluded:
        reason = (
            f"Excluded: {business_model}-only company for a {target_market} client. {fit_reason}"
        ).strip()
        return _MARKET_GATE_SCORE, tier_for(_MARKET_GATE_SCORE), True, reason
    if fit_score is None:
        return None, None, False, fit_reason
    return fit_score, tier_for(fit_score), False, fit_reason


def _ints(props: dict[str, int]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {k: {"type": "integer"} for k in props},
        "required": list(props),
    }


def _strs(keys: list[str]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {k: {"type": "string"} for k in keys},
        "required": keys,
    }


def _fit_schema(name: str, dims: dict[str, dict[str, int]]) -> dict:
    """A strict fit schema over an arbitrary dimension set (full rubric or company-only)."""
    return {
        "name": name,
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "components": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {d: _ints(subs) for d, subs in dims.items()},
                    "required": list(dims),
                },
                "reasons": _strs(list(dims)),
                "reason_tags": {"type": "array", "items": {"type": "string"}},
                "fit_reason": {"type": "string"},
                # The model commits to the tier + 0–100 score it derives from its own points (the
                # threshold formula is given in the prompt). These are NOT stored — the server
                # recomputes both authoritatively from `components` — but emitting them forces the
                # model to anchor `fit_reason` to the same verdict the chip will show.
                "fit_tier": {
                    "type": "string",
                    "enum": ["Strong", "Good", "Moderate", "Below"],
                },
                "fit_score": {"type": "integer"},
            },
            "required": [
                "components",
                "reasons",
                "reason_tags",
                "fit_reason",
                "fit_tier",
                "fit_score",
            ],
        },
    }


FIT_JSON_SCHEMA = _fit_schema("ProspectFit", DIMENSIONS)

# Stage-1 company scoring (LLM usage B) is intentionally minimal: the model reasons through the
# rubric SILENTLY and returns only the verdict — a 0–100 `fit_score` and a short client-facing
# `fit_reason`. The server derives the tier from the score (tier_for). We do NOT ask the model to
# emit the per-sub-criterion grid: a reasoning model fills it unreliably (it decides in the thinking
# trace, then zeroes the grid → every company collapsed to "Below · 0"). Two fields it fills well.
# The B2B/B2C `business_model` label is NO LONGER produced here (2026-07): it is classified up-front
# by its own dedicated call (classify_business_model) at find/add time, so score_company just READS
# the stored label (via the company payload) to re-apply the market gate.
COMPANY_FIT_JSON_SCHEMA = {
    "name": "CompanyFit",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "fit_score": {"type": "integer"},
            "fit_reason": {"type": "string"},
        },
        "required": ["fit_score", "fit_reason"],
    },
}

# Stage-0 business-model classifier — its own minimal schema: one enum field, nothing else.
BUSINESS_MODEL_SCHEMA = {
    "name": "BusinessModel",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "business_model": {"type": "string", "enum": ["B2B", "B2C", "Complex", "Unknown"]},
        },
        "required": ["business_model"],
    },
}


def build_messages(rubric_body: str, enrichment: dict, targeting: dict) -> list[dict]:
    """Prompt: the founder's rubric verbatim + the enriched candidate + the targeting context.

    The rubric is passed as data (founder-edited, versioned) so a re-weighting is a doc edit,
    never a code change. `targeting` carries the brief/ICP/spec slice the rubric scores against.
    """
    import json

    system = (
        "You are HoldSlot's prospect fit scorer (stage 2 of two: the company already cleared "
        "stage 1, now judge the PERSON). Score how likely this individual is to reply AND to hold "
        "the decision-making power to convert a deal. Score ONE prospect against the fixed "
        "rubric below, criterion by criterion. The prospect carries the person's signals (title, "
        "seniority, department, email) plus the parent company's firmographics and its stage-1 fit "
        "verdict (`company_fit`); the targeting context's `spec.people_search_params` is the "
        "intended decision-maker scope we searched for. For each sub-criterion award the rubric's "
        "full / partial / zero points — never more than its max. A field still unknown after "
        "enrichment scores per the rubric's Unknown policy (firmographic match → 0; tech → "
        "partial; engagement → 0; email risky/accept-all → 3). Return integer points per "
        "sub-criterion, a one-line justification per dimension, short client-facing match tags, "
        "one client-facing `fit_reason` sentence, and the `fit_tier` + `fit_score` you derive from "
        "your own points. SCORING (apply it exactly — the server re-derives the official verdict "
        "from your points the same way): `fit_score` = the sum of points you awarded over all "
        "four dimensions (max 100). `fit_tier` = Strong if fit_score ≥ 75, Good if ≥ 55, Moderate "
        "if ≥ 40, otherwise Below. `fit_reason` MUST match that tier — state what is confirmed and "
        "what is still missing or unknown, and never call a prospect a strong/great match unless "
        "`fit_tier` is Strong. No jargon, no number in the prose. Emit ONLY the schema.\n\n"
        "=== FIT RUBRIC (authoritative) ===\n" + rubric_body
    )
    user = (
        "TARGETING CONTEXT (brief / ICP / spec slice):\n"
        + json.dumps(targeting, ensure_ascii=False)
        + "\n\nENRICHED PROSPECT:\n"
        + json.dumps(enrichment, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _collapse(components: dict, dims: dict[str, dict[str, int]]) -> tuple[int, dict]:
    """Clamp each sub-score to max, cap each dimension, sum → (total, normalized) over `dims`."""
    normalized: dict[str, dict[str, int]] = {}
    total = 0
    for dim, subs in dims.items():
        got = components.get(dim, {}) or {}
        clamped = {sub: max(0, min(int(got.get(sub, 0) or 0), mx)) for sub, mx in subs.items()}
        normalized[dim] = clamped
        total += min(sum(clamped.values()), sum(subs.values()))
    return total, normalized


def collapse(components: dict) -> tuple[int, str, dict]:
    """Clamp each sub-score to its max, cap each dimension, sum → (score, tier, normalized).

    Pure + deterministic, so the same components always yield the same tier (testable without
    the LLM). Returns the normalized components too, so what we store equals what we scored.
    """
    total, normalized = _collapse(components, DIMENSIONS)
    return total, tier_for(total), normalized


def _log_drift(purpose: str, computed_score: int, computed_tier: str, data: dict) -> None:
    """Warn if the model's self-committed tier/score (which `fit_reason` is anchored to) diverges
    from the authoritative server recomputation — i.e. the prose may not match the displayed chip.
    The server value always wins; this only flags a model that mis-applied the threshold formula."""
    llm_tier = data.get("fit_tier")
    if llm_tier and llm_tier != computed_tier:
        log.warning(
            "fit tier drift (%s): model said %s/%s, server computed %s/%s — reason may misalign",
            purpose, llm_tier, data.get("fit_score"), computed_tier, computed_score,
        )


def score(
    *,
    tenant_id,
    rubric_body: str,
    enrichment: dict,
    targeting: dict,
) -> dict:
    """Score one prospect. Returns `{fit_score, fit_tier, fit_components, llm_call_id, model}`.

    `fit_components` carries the normalized line-items + the LLM's per-dimension reasons, the
    client-facing tags, and `fit_reason` (→ Phase D approval page). Raises `LlmError` on a
    non-ok call (telemetry is already persisted by the adapter).
    """
    result = structured_completion(
        tenant_id=tenant_id,
        purpose=PURPOSE,
        messages=build_messages(rubric_body, enrichment, targeting),
        schema=FIT_JSON_SCHEMA,
        prompt_version=RUBRIC_VERSION,
        models=FIT_MODELS,
        extra_body=PROSPECT_FIT_EXTRA_BODY,
    )
    fit_score, fit_tier, normalized = collapse(result.data.get("components", {}))
    _log_drift(PURPOSE, fit_score, fit_tier, result.data)
    fit_components = {
        "points": normalized,
        "reasons": result.data.get("reasons", {}),
        "reason_tags": result.data.get("reason_tags", []),
        "fit_reason": result.data.get("fit_reason", ""),
        "rubric_version": RUBRIC_VERSION,
    }
    return {
        "fit_score": fit_score,
        "fit_tier": fit_tier,
        "fit_components": fit_components,
        "llm_call_id": result.llm_call_id,
        "model": result.model,
        "cost_usd": result.cost_usd,
    }


def build_company_messages(rubric_body: str, company: dict, targeting: dict) -> list[dict]:
    """Stage-1 company prompt: the founder's rubric is the model's SILENT thinking framework; it
    returns only the verdict (`fit_score` 0–100 + a short `fit_reason`).

    No person exists yet, so persona criteria are out of scope. The model weighs company / timing /
    data fit against the rubric in its head — we deliberately do NOT ask it to emit the line-item
    grid (a reasoning model fills that unreliably; see COMPANY_FIT_JSON_SCHEMA)."""
    import json

    system = (
        "You are HoldSlot's COMPANY fit scorer (stage 1 of two: company first, person later). "
        "Decide how strongly ONE company matches the client's brief and shows buying intent, then "
        "output ONLY two fields: an integer `fit_score` (0–100) and a short `fit_reason`.\n\n"
        "THINK SILENTLY, then score — do NOT output your working. Reason through the rubric below "
        "across the company / timing / data dimensions ONLY (there is no person yet, so SKIP all "
        "persona criteria): company fit (industry, size, maturity, tech), timing (buying triggers, "
        "recent signals, engagement) and data quality. For anything still unknown after "
        "enrichment, apply the rubric's Unknown policy (a firmographic mismatch counts against the "
        "company; tech / data unknowns are neutral). Weigh it against the targeting context.\n\n"
        "OUTPUT:\n"
        "• `fit_score` — 0–100, anchored to real evidence in the brief + enrichment, not optimism. "
        "Scale: ≥ 75 strong match · ≥ 55 good · ≥ 40 moderate · below 40 weak.\n"
        "• `fit_reason` — ONE short client-facing sentence (~12–20 words, no number, no internal "
        "jargon) saying what makes this company fit or not. It is shown in a small hover box, so "
        "keep it concise and make it match the score (never call a low-scoring company a strong "
        "fit).\n"
        "Emit ONLY the JSON object with those two fields.\n\n"
        "=== FIT RUBRIC (your thinking framework) ===\n" + rubric_body
    )
    user = (
        "TARGETING CONTEXT (brief / ICP / spec slice):\n"
        + json.dumps(targeting, ensure_ascii=False)
        + "\n\nCOMPANY:\n"
        + json.dumps(company, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def score_company(*, tenant_id, rubric_body: str, company: dict, targeting: dict) -> dict:
    """Score one company (LLM usage B, stage 1). The model returns the verdict directly: a 0–100
    `fit_score` + a short `fit_reason`; the server clamps the score and derives `fit_tier` from it
    (tier_for). Raises `LlmError` on a non-ok call (telemetry already persisted).

    `business_model` is NOT (re-)classified here — it is read from the `company` payload (stamped by
    classify_business_model at find/add time) and used only to re-apply the market gate + preserved
    in the returned components, so a re-score can neither drop the label nor un-exclude the row."""
    result = structured_completion(
        tenant_id=tenant_id,
        purpose=COMPANY_PURPOSE,
        messages=build_company_messages(rubric_body, company, targeting),
        schema=COMPANY_FIT_JSON_SCHEMA,
        prompt_version=RUBRIC_VERSION,
        models=FIT_MODELS,
        extra_body=COMPANY_FIT_EXTRA_BODY,
    )
    raw_score = max(0, min(int(result.data.get("fit_score") or 0), 100))
    business_model = company.get("business_model") or "Unknown"
    # Market hard gate: the brief's `targetMarket` (B2B / B2C / Both / absent) vs the stored
    # `business_model`. A confirmed opposite-market company is a structural miss — forced into the
    # Below band so it is never selected for people-search (no person sourced, no enrich spend),
    # with an auditable reason. `Both`/absent disables the gate; `Complex`/`Unknown` never gate.
    target_market = (targeting.get("brief") or {}).get("targetMarket")
    fit_score, fit_tier, market_excluded, fit_reason = apply_market_gate(
        business_model=business_model,
        target_market=target_market,
        fit_score=raw_score,
        fit_reason=result.data.get("fit_reason", ""),
    )
    # Observability: the model's verdict only lands in the DB otherwise, so a low/0 score is hard to
    # diagnose. One INFO line per company makes "why is this Below/0?" answerable from CloudWatch.
    log.info(
        "company_fit scored: score=%s tier=%s model=%s excluded=%s company=%s llm=%s call=%s "
        "reason=%r",
        fit_score, fit_tier, business_model, market_excluded,
        company.get("domain") or company.get("name") or "?",
        result.model, result.llm_call_id, (fit_reason or "")[:160],
    )
    return {
        "fit_score": fit_score,
        "fit_tier": fit_tier,
        "fit_components": {
            "fit_reason": fit_reason,
            "business_model": business_model,
            "market_excluded": market_excluded,
            "rubric_version": RUBRIC_VERSION,
        },
        "fit_reason": fit_reason,
        "llm_call_id": result.llm_call_id,
        "model": result.model,
        "cost_usd": result.cost_usd,
    }


def build_model_messages(company: dict) -> list[dict]:
    """Stage-0 classifier prompt — deliberately tiny (token minimization is the whole point): the
    label definitions + ONLY the company's identity/description signals. No rubric, no targeting, no
    full firmographics — `business_model` is a factual, client-independent property."""
    import json

    system = (
        "Classify who a company sells to. Judge from its description, industries and keywords — "
        "the customer it serves, not its own size. Output ONE label:\n"
        "• B2B — sells primarily to other businesses.\n"
        "• B2C — sells directly to consumers (e.g. a digital insurer, retail brand, consumer "
        "app/fintech).\n"
        "• Complex — serves BOTH sides by design: marketplaces, platforms, B2B2C (e.g. Amazon, a "
        "payments network).\n"
        "• Unknown — too little signal to tell.\n"
        "Emit ONLY the JSON object with the single `business_model` field."
    )
    user = "COMPANY:\n" + json.dumps(company, ensure_ascii=False)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def classify_business_model(*, tenant_id, company: dict) -> dict:
    """Stage-0 — classify a company's B2B/B2C `business_model` in one minimal call. Returns
    `{business_model, llm_call_id, model, cost_usd}`; raises `LlmError` on a non-ok call (telemetry
    already persisted). Client-independent, so it takes no rubric/targeting — the caller applies the
    market gate against the brief's `targetMarket` separately (apply_market_gate)."""
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
    log.info(
        "business_model classified: model=%s company=%s llm=%s call=%s",
        business_model,
        company.get("domain") or company.get("name") or "?",
        result.model,
        result.llm_call_id,
    )
    return {
        "business_model": business_model,
        "llm_call_id": result.llm_call_id,
        "model": result.model,
        "cost_usd": result.cost_usd,
    }


__all__ = [
    "score",
    "score_company",
    "classify_business_model",
    "apply_market_gate",
    "collapse",
    "tier_for",
    "FIT_JSON_SCHEMA",
    "COMPANY_FIT_JSON_SCHEMA",
    "BUSINESS_MODEL_SCHEMA",
    "PURPOSE",
    "COMPANY_PURPOSE",
    "MODEL_PURPOSE",
    "RUBRIC_VERSION",
    "LlmError",
]
