"""Fit scoring — the one scoring door (C3 ⭐), driven by the founder-edited rubric.

Shape (locked, see `docs/prompts/fit-scoring-rubric-v1.md`): the LLM classifies each rubric
sub-criterion (full / partial / zero) against the **fixed rubric text** and returns the line-item
points + a one-line justification per dimension + client-facing match tags. The total and the
**tier are computed deterministically server-side** — thresholds are policy, never LLM-set — and
each sub-score is clamped to its max so no single attribute can inflate the rest. Storing the
components (not just the total) is the moat: one structure, three consumers (approval page,
billing dispute, the learning loop).

Routing (FINAL, see initial-build-plan §"Model usage"): `prospect_fit` → qwen3.5-flash,
`temperature=0`, thinking disabled (Qwen bills thinking 3–10× output). Confirm the exact slug +
that thinking is off at deploy time.
"""

from __future__ import annotations

from app.integrations.openrouter.client import LlmError, structured_completion

PURPOSE = "prospect_fit"
RUBRIC_VERSION = "fit-rubric-v1"
# Per-purpose routing. Confirm the live slug at deploy (labs reprice/rename ~monthly).
FIT_MODELS = ["qwen/qwen3.5-flash"]
# `temperature=0` for determinism; `reasoning.enabled=false` disables Qwen thinking tokens.
FIT_EXTRA_BODY = {"temperature": 0, "reasoning": {"enabled": False}}

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


def _fit_schema() -> dict:
    return {
        "name": "ProspectFit",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "components": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {d: _ints(subs) for d, subs in DIMENSIONS.items()},
                    "required": list(DIMENSIONS),
                },
                "reasons": _strs(list(DIMENSIONS)),
                "reason_tags": {"type": "array", "items": {"type": "string"}},
                "fit_reason": {"type": "string"},
            },
            "required": ["components", "reasons", "reason_tags", "fit_reason"],
        },
    }


def _strs(keys: list[str]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {k: {"type": "string"} for k in keys},
        "required": keys,
    }


FIT_JSON_SCHEMA = _fit_schema()


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
        "and one client-facing `fit_reason` sentence (no internal jargon, no score). Emit ONLY "
        "the schema; do not compute totals or tiers — the system does that.\n\n"
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


def collapse(components: dict) -> tuple[int, str, dict]:
    """Clamp each sub-score to its max, cap each dimension, sum → (score, tier, normalized).

    Pure + deterministic, so the same components always yield the same tier (testable without
    the LLM). Returns the normalized components too, so what we store equals what we scored.
    """
    normalized: dict[str, dict[str, int]] = {}
    total = 0
    for dim, subs in DIMENSIONS.items():
        got = components.get(dim, {}) or {}
        clamped = {sub: max(0, min(int(got.get(sub, 0) or 0), mx)) for sub, mx in subs.items()}
        dim_score = min(sum(clamped.values()), DIMENSION_MAX[dim])
        normalized[dim] = clamped
        total += dim_score
    return total, tier_for(total), normalized


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


__all__ = [
    "score",
    "collapse",
    "tier_for",
    "FIT_JSON_SCHEMA",
    "PURPOSE",
    "RUBRIC_VERSION",
    "LlmError",
]
