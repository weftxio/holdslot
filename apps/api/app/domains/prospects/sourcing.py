"""AI sourcing loop (C5 ⭐) — the discovery heart, human-in-the-loop.

The one call site where model quality carries the outcome (mistakes burn enrichment credits),
so it routes to DeepSeek V4 Pro + the OpenRouter web-search plugin at reasoning effort High
(NOT Max) — see initial-build-plan §"Model usage". The founder's `sourcing_prompt` doc drives
it (versioned data, edited between rounds); candidates come back **with evidence URLs**, never
contact data. They then run the SAME C2 suppression gate and land as `ai_loop · Pending review`
for founder accept/reject; accepted ones push through C2 and return scored via the C3 import.

`candidate_validate` at MVP is the deterministic liveness gate below (cheap, drops the
un-defensible before any spend); the qwen evidence re-check on survivors is the next increment.
"""

from __future__ import annotations

import json

from app.domains.prospects.identity import normalize_domain
from app.domains.prospects.suppression import Candidate
from app.integrations.openrouter.client import structured_completion

PURPOSE = "sourcing_round"
# Per-purpose routing — DeepSeek V4 Pro for agentic reasoning + live web research. Confirm the
# live slug at deploy. Web search rides OpenRouter's plugin (no new vendor/secret).
SOURCING_MODELS = ["deepseek/deepseek-v4-pro"]
SOURCING_EXTRA_BODY = {"plugins": [{"id": "web"}], "reasoning": {"effort": "high"}}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": required if required is not None else list(props),
    }


def _str() -> dict:
    return {"type": "string"}


_CANDIDATE = _obj(
    {
        "company": _obj(
            {
                "name": _str(),
                "domain": _str(),
                "vertical": _str(),
                "vertical_source_url": _str(),
                "employee_band": _str(),
                "size_source_url": _str(),
                "maturity": _str(),
                "tech": {"type": "array", "items": _str()},
                "tech_source_url": _str(),
            }
        ),
        "person": _obj(
            {
                "full_name": _str(),
                "title": _str(),
                "seniority": _str(),
                "department": _str(),
                "is_likely_economic_buyer": {"type": "boolean"},
                "profile_url": _str(),
            }
        ),
        "timing": _obj(
            {
                "primary_trigger": _obj(
                    {"description": _str(), "date": _str(), "source_url": _str()}
                ),
                "secondary_signal": _obj({"description": _str(), "source_url": _str()}),
                "engagement": _str(),
            }
        ),
        "preliminary_tier": {"type": "string", "enum": ["Strong", "Good", "Moderate"]},
        "reasons": _obj({"company": _str(), "persona": _str(), "timing": _str()}),
        "confidence": _obj(
            {
                "confirmed": {"type": "array", "items": _str()},
                "inferred": {"type": "array", "items": _str()},
            }
        ),
        "gate_check": _str(),
    }
)

SOURCING_JSON_SCHEMA = {
    "name": "SourcingRound",
    "strict": True,
    "schema": _obj({"candidates": {"type": "array", "items": _CANDIDATE}}),
}


def build_messages(
    *,
    prompt_body: str,
    brief: dict,
    spec: dict,
    seed_sample: list[dict],
    exclusion_summary: dict,
) -> list[dict]:
    """System = the founder's sourcing prompt verbatim; user = the round's inputs as JSON."""
    payload = {
        "brief": brief,
        "research_spec": spec,
        "seed_sample": seed_sample,
        "exclusion_summary": exclusion_summary,
    }
    user = (
        "Source NEW candidates for this client. Return only the schema — targeting with evidence "
        "URLs, never contact data, and self-suppress against the exclusion summary.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": prompt_body},
        {"role": "user", "content": user},
    ]


def run_round(
    *,
    tenant_id,
    prompt_body: str,
    prompt_version: str,
    brief: dict,
    spec: dict,
    seed_sample: list[dict],
    exclusion_summary: dict,
):
    """One sourcing call through B3. Returns the StructuredResult (raises LlmError on failure)."""
    return structured_completion(
        tenant_id=tenant_id,
        purpose=PURPOSE,
        messages=build_messages(
            prompt_body=prompt_body,
            brief=brief,
            spec=spec,
            seed_sample=seed_sample,
            exclusion_summary=exclusion_summary,
        ),
        schema=SOURCING_JSON_SCHEMA,
        prompt_version=prompt_version,
        models=SOURCING_MODELS,
        extra_body=SOURCING_EXTRA_BODY,
    )


def to_candidate(raw: dict) -> Candidate:
    """Map one LLM candidate object → the shared Candidate (the C2/C3 shape)."""
    company = raw.get("company", {}) or {}
    person = raw.get("person", {}) or {}
    return Candidate(
        full_name=person.get("full_name", ""),
        company=company.get("name", ""),
        domain=normalize_domain(company.get("domain", "")),
        linkedin_url=person.get("profile_url", ""),
        company_industry=company.get("vertical", ""),
        target_titles=person.get("title", ""),
        target_seniority=person.get("seniority", ""),
    )


def _has_evidence(raw: dict) -> bool:
    """At least one cited URL anywhere — the prompt's core 'never state a fact you can't cite'."""
    company = raw.get("company", {}) or {}
    timing = raw.get("timing", {}) or {}
    person = raw.get("person", {}) or {}
    urls = [
        company.get("vertical_source_url"),
        company.get("size_source_url"),
        person.get("profile_url"),
        (timing.get("primary_trigger") or {}).get("source_url"),
    ]
    return any(u and u.strip() for u in urls)


def validate_candidates(raws: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Deterministic liveness gate (candidate_validate, MVP): drop the un-defensible before any
    spend. Keeps only candidates with a resolvable company domain, a person name, and ≥1 cited
    URL. Returns (valid, rejected[(raw, reason)])."""
    valid: list[dict] = []
    rejected: list[tuple[dict, str]] = []
    for raw in raws:
        company = raw.get("company", {}) or {}
        person = raw.get("person", {}) or {}
        domain = normalize_domain(company.get("domain", ""))
        if not domain or "." not in domain:
            rejected.append((raw, "no_domain"))
        elif not (person.get("full_name") or "").strip():
            rejected.append((raw, "no_person"))
        elif not _has_evidence(raw):
            rejected.append((raw, "no_evidence"))
        else:
            valid.append(raw)
    return valid, rejected
