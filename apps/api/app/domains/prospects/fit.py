"""Fit scoring — the one scoring door (C3 ⭐), driven by the founder-edited rubric.

Shape (locked, see `docs/prompts/fit-scoring-rubric-v1.md`): the LLM classifies each rubric
sub-criterion (full / partial / zero) against the **fixed rubric text** and returns the line-item
points + a one-line justification per dimension + client-facing match tags. The total and the
**tier are computed deterministically server-side** — thresholds are policy, never LLM-set — and
each sub-score is clamped to its max so no single attribute can inflate the rest. Storing the
components (not just the total) is the moat: one structure, three consumers (approval page,
billing dispute, the learning loop).

Routing (FINAL, see initial-build-plan §"Model usage"): `prospect_fit`/`company_fit` →
**DeepSeek V4 Pro with reasoning ON** (`effort=medium`, `temperature=0`) for best-quality fit
judgement — a non-US provider (the Gemini/OpenAI fallback was dropped 2026-06-21 as geo-blocked,
403 ToS, for this account; see openrouter/client.py module docstring). V4 Pro is a reasoning model,
so to hold the 30s sync-gateway budget the find/rescore routes score the whole batch in ONE
concurrent wave (`_SCORE_WORKERS` ≥ `MAX_COMPANIES_PER_FIND`): wall-clock ≈ one reasoning call, not
N waves. Dial `effort` down to "low" or shrink the per-find cap if a batch nears the timeout.
"""

from __future__ import annotations

import logging

from app.integrations.openrouter.client import LlmError, structured_completion

log = logging.getLogger("holdslot.fit")

PURPOSE = "prospect_fit"
COMPANY_PURPOSE = "company_fit"
RUBRIC_VERSION = "fit-rubric-v1"
FIT_MODELS = ["deepseek/deepseek-v4-pro"]
# `temperature=0` for determinism; reasoning ON (effort medium) for judgement quality. The batch
# runs single-wave (workers = cap) so the reasoning latency does not stack across waves.
FIT_EXTRA_BODY = {"temperature": 0, "reasoning": {"enabled": True, "effort": "medium"}}

# The rubric's sub-criteria → their max points (the deterministic caps). Mirrors §2 of the
# rubric doc; the LLM scores each, we clamp to max, cap each dimension at its sum-of-maxes.
DIMENSIONS: dict[str, dict[str, int]] = {
    "company": {"industry": 16, "size": 12, "maturity": 8, "tech": 4},
    "persona": {"title": 14, "seniority": 8, "department": 5, "economic_buyer": 3},
    "timing": {"primary_trigger": 12, "secondary_signal": 6, "engagement": 2},
    "data": {"email_deliverability": 6, "profile_completeness": 4},
}
DIMENSION_MAX = {dim: sum(subs.values()) for dim, subs in DIMENSIONS.items()}  # 40/30/20/10

# Stage-1 company scoring (LLM usage B) reuses the SAME rubric, persona omitted — no person is
# sourced yet. Company / timing / data dimensions only (70 max); the total is normalized to /100
# so the one tier policy below applies to companies and people identically.
COMPANY_DIMENSIONS: dict[str, dict[str, int]] = {
    k: DIMENSIONS[k] for k in ("company", "timing", "data")
}
COMPANY_MAX = sum(sum(subs.values()) for subs in COMPANY_DIMENSIONS.values())  # 70

# Tiers — policy thresholds (rubric §4); tuned as outcome data accumulates, never by the LLM.
_TIERS = (("Strong", 75), ("Good", 55), ("Moderate", 40))


def tier_for(score: int) -> str:
    for name, floor in _TIERS:
        if score >= floor:
            return name
    return "Below"


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
COMPANY_FIT_JSON_SCHEMA = _fit_schema("CompanyFit", COMPANY_DIMENSIONS)


def build_messages(rubric_body: str, enrichment: dict, targeting: dict) -> list[dict]:
    """Prompt: the founder's rubric verbatim + the enriched candidate + the targeting context.

    The rubric is passed as data (founder-edited, versioned) so a re-weighting is a doc edit,
    never a code change. `targeting` carries the brief/ICP/spec slice the rubric scores against.
    """
    import json

    system = (
        "You are HoldSlot's prospect fit scorer. Score ONE enriched prospect against the fixed "
        "rubric below, criterion by criterion. For each sub-criterion award the rubric's "
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


def collapse_company(components: dict) -> tuple[int, str, dict]:
    """Company-only collapse (persona omitted): sum company/timing/data (≤70), normalize to /100
    so the one tier policy applies to companies and people on the same 0–100 scale."""
    total, normalized = _collapse(components, COMPANY_DIMENSIONS)
    score = round(total / COMPANY_MAX * 100) if COMPANY_MAX else 0
    return score, tier_for(score), normalized


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
        extra_body=FIT_EXTRA_BODY,
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
    """Stage-1 company prompt: the founder's rubric verbatim, scored at the COMPANY level only.

    No person exists yet, so persona criteria are out of scope — the model scores company,
    timing, and data (deliverability → unknown policy) dimensions against the same rubric text.
    """
    import json

    system = (
        "You are HoldSlot's COMPANY fit scorer (stage 1 of two: company first, person later). "
        "Score ONE company against the fixed rubric below, criterion by criterion, for the "
        "company / timing / data dimensions ONLY — there is no person yet, so SKIP all persona "
        "criteria. For each in-scope sub-criterion award the rubric's full / partial / zero "
        "points, never more than its max. A field still unknown scores per the rubric's Unknown "
        "policy (firmographic match → 0; tech → partial; engagement → 0; email "
        "deliverability → 3, person not yet sourced). Return integer points per sub-criterion, a "
        "one-line justification per dimension, short client-facing match tags, one client-facing "
        "`fit_reason` sentence about this COMPANY (no person), and the `fit_tier` + `fit_score` "
        "you derive from your points. SCORING (apply it exactly — the server re-derives the "
        "official verdict from your points the same way): sum the points you awarded across the "
        "company, timing and data dimensions (max 70), then `fit_score` = round(that_sum ÷ 70 × "
        "100). `fit_tier` = Strong if fit_score ≥ 75, Good if ≥ 55, Moderate if ≥ 40, otherwise "
        "Below. `fit_reason` MUST match that tier — state what is confirmed and what is still "
        "missing or unknown (e.g. firmographic size, timing triggers), and never call a company a "
        "strong/great fit unless `fit_tier` is Strong. No internal jargon, no number in the prose. "
        "Emit ONLY the schema.\n\n"
        "=== FIT RUBRIC (authoritative) ===\n" + rubric_body
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
    """Score one company (LLM usage B, stage 1). Same return shape as `score`; persona omitted,
    total normalized to /100. Raises `LlmError` on a non-ok call (telemetry already persisted)."""
    result = structured_completion(
        tenant_id=tenant_id,
        purpose=COMPANY_PURPOSE,
        messages=build_company_messages(rubric_body, company, targeting),
        schema=COMPANY_FIT_JSON_SCHEMA,
        prompt_version=RUBRIC_VERSION,
        models=FIT_MODELS,
        extra_body=FIT_EXTRA_BODY,
    )
    fit_score, fit_tier, normalized = collapse_company(result.data.get("components", {}))
    _log_drift(COMPANY_PURPOSE, fit_score, fit_tier, result.data)
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
        "fit_reason": result.data.get("fit_reason", ""),
        "llm_call_id": result.llm_call_id,
        "model": result.model,
        "cost_usd": result.cost_usd,
    }


__all__ = [
    "score",
    "score_company",
    "collapse",
    "collapse_company",
    "tier_for",
    "FIT_JSON_SCHEMA",
    "COMPANY_FIT_JSON_SCHEMA",
    "PURPOSE",
    "COMPANY_PURPOSE",
    "RUBRIC_VERSION",
    "LlmError",
]
