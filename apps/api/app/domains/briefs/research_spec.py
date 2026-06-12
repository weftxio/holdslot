"""ResearchSpec v1 — the locked Clay contract + the LLM seam that produces it (B4).

Two halves with different stability profiles (see docs/initial-build-plan.md → Phase B):
  * **The LLM emits targeting only** — `company_search`, `people_search`, `exclusions`, `gaps`
    — via a strict `json_schema` (so the structure can't drift). It is fed the *whole* Brief +
    ICP documents (no per-field plumbing → churn-proof prompt).
  * **The credit policy is deterministic server config** (`CREDIT_POLICY`), merged in at save
    time — never LLM-inferred. Credit rules are policy, not judgment.

The persisted spec = `{spec_version, company_search, people_search, exclusions, credit_policy}`;
`gaps` are stored alongside on the `ResearchSpec` row. Fields map 1:1 to Clay's Find
Companies / Find People filters; the contract hardens further in Phase C against the real
Clay table.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

SPEC_VERSION = 1
PROMPT_VERSION = "brief-structure-v1"
PURPOSE = "brief_structure"

# Deterministic credit policy (server-merged, NOT LLM-set). Encodes the credit-minimization
# rules: accuracy-first waterfall gated on prior-blank, validate before any paid downstream,
# a human-reviewed test batch, and conservative caps. Real enforcement is Phase C/S2.
CREDIT_POLICY: dict = {
    "email_waterfall": [
        {"provider": "prospeo", "only_run_if": "always"},
        {"provider": "findymail", "only_run_if": "email_prior_blank"},
        {"provider": "datagma", "only_run_if": "all_prior_blank"},
    ],
    "email_validation": True,
    "phone": False,
    "test_batch_size": 10,
    "deliver_only_if": "email_valid",
    "max_companies": 500,
    "max_people": 800,
}


# ---------------------------------------------------------------------------
# The strict json_schema sent to OpenRouter. Strict mode requires every property to be
# listed in `required` and `additionalProperties: false`; "optional" is expressed as a
# nullable type or an empty array the model fills when unknown.
# ---------------------------------------------------------------------------


def _arr_str() -> dict:
    return {"type": "array", "items": {"type": "string"}}


def _obj(props: dict) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": list(props.keys()),
    }


_INT_OR_NULL = {"type": ["integer", "null"]}

_COMPANY_SEARCH = _obj(
    {
        "industries_include": _arr_str(),
        "industries_exclude": _arr_str(),
        "description_keywords_include": _arr_str(),
        "description_keywords_exclude": _arr_str(),
        "semantic_description": {"type": "string"},
        "employee_count": _obj({"min": _INT_OR_NULL, "max": _INT_OR_NULL}),
        "revenue_usd": _obj({"min": _INT_OR_NULL, "max": _INT_OR_NULL}),
        "company_types": _arr_str(),
        "founded": _obj({"after": _INT_OR_NULL, "before": _INT_OR_NULL}),
        "locations_include": _obj(
            {"countries": _arr_str(), "states": _arr_str(), "cities": _arr_str()}
        ),
        "locations_exclude": _obj(
            {"countries": _arr_str(), "states": _arr_str(), "cities": _arr_str()}
        ),
        "technographics": _obj({"enabled": {"type": "boolean"}, "vendors": _arr_str()}),
        "max_results": {"type": "integer"},
    }
)

_PEOPLE_ITEM = _obj(
    {
        "icp_id": {"type": "string"},
        "job_title_keywords": _arr_str(),
        "job_title_match_mode": {
            "type": "string",
            "enum": ["is_similar", "contains", "is_exactly"],
        },
        "job_title_exclude": _arr_str(),
        "seniority": _arr_str(),
        "departments": _arr_str(),
        "max_per_company": {"type": "integer"},
        "max_total": {"type": "integer"},
    }
)

_EXCLUSIONS = _obj(
    {
        "domains": _arr_str(),
        "company_linkedin_urls": _arr_str(),
        "emails": _arr_str(),
    }
)

_GAP_ITEM = _obj(
    {
        "field": {"type": "string"},
        "why": {"type": "string"},
        "ask": {"type": "string"},
    }
)

RESEARCH_SPEC_JSON_SCHEMA: dict = {
    "name": "ResearchSpec",
    "strict": True,
    "schema": _obj(
        {
            "company_search": _COMPANY_SEARCH,
            "people_search": {"type": "array", "items": _PEOPLE_ITEM},
            "exclusions": _EXCLUSIONS,
            "gaps": {"type": "array", "items": _GAP_ITEM},
        }
    ),
}


# ---------------------------------------------------------------------------
# Server-side validation of the LLM output (defensive — strict mode should already
# guarantee shape, but we never persist an off-contract spec).
# ---------------------------------------------------------------------------


# These mirror RESEARCH_SPEC_JSON_SCHEMA 1:1 (every field required, no extras) so the
# defensive validator is exactly as strict as the schema sent to the model — they can't
# drift silently (test_research_spec binds them to the canonical example + the schema keys).
_STRICT = ConfigDict(extra="forbid")


class MinMaxV1(BaseModel):
    model_config = _STRICT
    min: int | None
    max: int | None


class FoundedV1(BaseModel):
    model_config = _STRICT
    after: int | None
    before: int | None


class LocationsV1(BaseModel):
    model_config = _STRICT
    countries: list[str]
    states: list[str]
    cities: list[str]


class TechnographicsV1(BaseModel):
    model_config = _STRICT
    enabled: bool
    vendors: list[str]


class CompanySearchV1(BaseModel):
    model_config = _STRICT
    industries_include: list[str]
    industries_exclude: list[str]
    description_keywords_include: list[str]
    description_keywords_exclude: list[str]
    semantic_description: str
    employee_count: MinMaxV1
    revenue_usd: MinMaxV1
    company_types: list[str]
    founded: FoundedV1
    locations_include: LocationsV1
    locations_exclude: LocationsV1
    technographics: TechnographicsV1
    max_results: int


class PeopleSearchItemV1(BaseModel):
    model_config = _STRICT
    icp_id: str
    job_title_keywords: list[str]
    job_title_match_mode: str
    job_title_exclude: list[str]
    seniority: list[str]
    departments: list[str]
    max_per_company: int
    max_total: int


class ExclusionsV1(BaseModel):
    model_config = _STRICT
    domains: list[str]
    company_linkedin_urls: list[str]
    emails: list[str]


class GapV1(BaseModel):
    model_config = _STRICT
    field: str
    why: str
    ask: str


class ResearchSpecV1(BaseModel):
    """Validates the LLM targeting output — exactly as strict as the json_schema."""

    model_config = _STRICT
    company_search: CompanySearchV1
    people_search: list[PeopleSearchItemV1]
    exclusions: ExclusionsV1
    gaps: list[GapV1]


def build_messages(brief_data: dict, icps: list[dict]) -> list[dict]:
    """Prompt the model with the WHOLE brief + ICP documents — no per-field plumbing."""
    system = (
        "You are a B2B go-to-market analyst. Translate a client's business brief and ICP "
        "profiles into Clay prospecting parameters. Map prose to concrete filters: LinkedIn "
        "industry labels, employee-count and revenue ranges, locations, and job-title keywords "
        "(prefer specific titles over seniority). Emit ONLY the schema. When a field cannot be "
        "determined from the brief, leave its array empty or value null AND add a precise entry "
        "to `gaps` (field, why it matters for targeting, and a one-line ask to the client). Do "
        "not invent facts; gaps are better than guesses. Do not include enrichment or credit "
        "settings — those are set by the system."
    )
    payload = {"brief": brief_data, "icps": icps}
    user = (
        "Build the ResearchSpec targeting parameters from this brief and ICP set.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def assemble_spec(targeting: dict) -> tuple[dict, list[dict]]:
    """Split the validated LLM output into the persisted spec + gaps, merging credit policy."""
    spec = {
        "spec_version": SPEC_VERSION,
        "company_search": targeting["company_search"],
        "people_search": targeting["people_search"],
        "exclusions": targeting["exclusions"],
        "credit_policy": CREDIT_POLICY,  # deterministic, server-set
    }
    gaps = targeting.get("gaps", [])
    return spec, gaps
