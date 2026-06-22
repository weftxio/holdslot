"""ResearchSpec v3 — the Apollo-mapped Brief→targeting contract + the LLM seam (B4/B6).

Two halves with different stability profiles (see docs/initial-build-plan.md → Phase B):
  * **The LLM emits targeting + ICP validation** — `company_search_params`,
    `people_search_params`, `intent_filters`, `icp_validation`, `icp_suggestions`, `gaps` — via a
    strict `json_schema` so the structure can't drift. It is fed the *whole* Brief + ICP documents
    (no per-field plumbing → churn-proof prompt), plus `today` for recency-window math.
  * **The credit policy is deterministic server config** (`CREDIT_POLICY`), merged in at save
    time — never LLM-inferred. Credit rules are policy, not judgment.

The persisted spec = `{spec_version, company_search_params, people_search_params, intent_filters,
icp_validation, credit_policy}`; `gaps` + `icp_suggestions` are stored in their own columns on the
`ResearchSpec` row.

**v3 (Apollo-native, 2026-06-22):** the LLM now emits **exact Apollo request fields** by name
(`q_organization_keyword_tags`, `organization_num_employees_ranges` comma-strings,
`person_seniorities` enum, …) — no intermediate vocabulary to translate. `apollo_map` (Phase C)
forwards them straight to `mixed_companies/search` / `mixed_people/api_search`. Buying signals live
in a separate `intent_filters` block (funding date + hiring titles/dates). `icp_validation`
characterizes the real paying customers (from the brief's `excludeCustomers` list) for the ICP-vs-
reality check. No migration — `spec` is JSONB, append-only.
"""

from __future__ import annotations

import json
from datetime import date

from pydantic import BaseModel, ConfigDict

SPEC_VERSION = 3
PROMPT_VERSION = "brief-structure-v5"
PURPOSE = "brief_structure"

# Apollo's fixed `person_seniorities` enum (the only accepted values). The LLM is constrained to
# these at generation; `apollo_map` passes them straight through to `mixed_people/api_search`.
SENIORITY_ENUM = [
    "owner",
    "founder",
    "c_suite",
    "partner",
    "vp",
    "head",
    "director",
    "manager",
    "senior",
    "entry",
    "intern",
]

# Deterministic credit policy (server-merged, NOT LLM-set). Apollo-shaped: a single `people/match`
# enrich gated on email status, phone off (8 cr + async webhook), plus hard caps. The prompt is
# told NOT to emit enrichment/credits/email-status — those are set here.
CREDIT_POLICY: dict = {
    "email_status_filter": ["verified"],  # → Apollo contact_email_status (people/match gate)
    "phone": False,  # reveal_phone_number off at dogfood
    "max_companies": 500,  # hard server cap on company search
    "max_people": 800,  # hard server cap on people search
}

# Scoping runs on DeepSeek V4 Pro with **thinking enabled** + the OpenRouter **web-search plugin**,
# so the model can characterize unfamiliar customer companies (Job 3) against live sources. Pinned
# here so it uses Pro regardless of the secret's `models`. ⚠️ Pro reasons slowly (~55-76s) and
# exceeds the 30s API Gateway sync cap — viable only via the async path (see initial-build-plan B0).
SCOPING_MODELS = ["deepseek/deepseek-v4-pro"]
SCOPING_EXTRA_BODY: dict = {
    "reasoning": {"enabled": True},  # DeepSeek V4 Pro thinking on
    "plugins": [{"id": "web"}],  # OpenRouter web-search grounding (Job 3 only, per the prompt)
}
SCOPING_TIMEOUT = (
    120  # seconds — Pro's reasoning budget; only honored off the gateway (local/async)
)


# ---------------------------------------------------------------------------
# The strict json_schema sent to OpenRouter. Strict mode requires every property to be
# listed in `required` and `additionalProperties: false`; "optional" is expressed as a
# nullable type or an empty array the model fills when unknown. Mirrors the JSON shape the
# DEFAULT_SYSTEM_PROMPT instructs the model to return, 1:1.
# ---------------------------------------------------------------------------


def _arr_str() -> dict:
    return {"type": "array", "items": {"type": "string"}}


def _arr_enum(values: list[str]) -> dict:
    return {"type": "array", "items": {"type": "string", "enum": values}}


def _obj(props: dict) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": list(props.keys()),
    }


_INT_OR_NULL = {"type": ["integer", "null"]}
_STR_OR_NULL = {"type": ["string", "null"]}
_CONF = {"type": "string", "enum": ["low", "medium", "high"]}
_MIN_MAX_INT = _obj({"min": _INT_OR_NULL, "max": _INT_OR_NULL})  # revenue_range
_MIN_MAX_DATE = _obj({"min": _STR_OR_NULL, "max": _STR_OR_NULL})  # YYYY-MM-DD ranges

# POST /api/v1/mixed_companies/search — the subset the model emits (fit firmographics).
_COMPANY_SEARCH_PARAMS = _obj(
    {
        "q_organization_keyword_tags": _arr_str(),  # industry/vertical (no industry-id field)
        "organization_num_employees_ranges": _arr_str(),  # comma-strings e.g. "10,100"
        "organization_locations": _arr_str(),  # HQ; lowercase country/state/city
        "revenue_range": _MIN_MAX_INT,  # integers, no symbols/commas
    }
)

# POST /api/v1/mixed_people/api_search — the subset the model emits (fit personas).
_PEOPLE_SEARCH_PARAMS = _obj(
    {
        "person_titles": _arr_str(),  # preferred over seniority
        "include_similar_titles": {"type": "boolean"},  # false for strict match
        "q_keywords": {"type": "string"},  # industry/vertical for PEOPLE — single string
        "person_seniorities": _arr_enum(SENIORITY_ENUM),  # enum backstop
        "organization_locations": _arr_str(),  # employer HQ
        "organization_num_employees_ranges": _arr_str(),  # comma-strings
    }
)

# Intent layer — buying signals as native Apollo recency filters (Job 2). Kept separate from fit:
# both fit AND intent are required at search time.
_INTENT_FILTERS = _obj(
    {
        "company": _obj(
            {
                "latest_funding_date_range": _MIN_MAX_DATE,  # closed funding window
                "q_organization_job_titles": _arr_str(),  # hiring-signal roles
                "organization_job_posted_at_range": _MIN_MAX_DATE,  # roles posted window
            }
        ),
        "recency_window": _obj(
            {
                "funding_since": _STR_OR_NULL,  # echo of the funding lower bound
                "jobs_posted_since": _STR_OR_NULL,  # echo of the jobs lower bound
            }
        ),
    }
)

# ICP validation (Job 3) — characterizes the real paying customers (from `excludeCustomers`) so the
# operator can see whether the stated ICPs match who actually buys. Analysis, NOT Apollo-bound.
_CUSTOMER_PROFILE = _obj(
    {
        "name": {"type": "string"},
        "domain": {"type": "string"},
        "industry": {"type": "string"},
        "employee_band": {"type": "string"},
        "hq_country": {"type": "string"},
        "business_model": {"type": "string"},
        "source": {"type": "string", "enum": ["knowledge", "web"]},
        "confidence": _CONF,
    }
)
_ICP_VALIDATION = _obj(
    {
        "customer_profiles": {"type": "array", "items": _CUSTOMER_PROFILE},
        "paying_customer_summary": {"type": "string"},
    }
)

_GAP_ITEM = _obj(
    {
        "field": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "ask": {"type": "string"},
    }
)

# Proposed ICP derived from the existing-customer list (the realest proof of who pays), surfaced
# (zero or one) when the paying customers diverge from every stated ICP. Stored alongside `gaps`
# (NOT in the Apollo-bound spec); the operator accepts → it becomes a real ICP. Carries its own
# ready-to-run Apollo company+people params.
_ICP_SUGGESTION_ITEM = _obj(
    {
        "name": {"type": "string"},
        "rationale": {"type": "string"},
        "evidencing_customers": _arr_str(),
        "confidence": _CONF,
        "company_search_params": _COMPANY_SEARCH_PARAMS,
        "people_search_params": _PEOPLE_SEARCH_PARAMS,
    }
)

RESEARCH_SPEC_JSON_SCHEMA: dict = {
    "name": "ResearchSpec",
    "strict": True,
    "schema": _obj(
        {
            "company_search_params": _COMPANY_SEARCH_PARAMS,
            "people_search_params": _PEOPLE_SEARCH_PARAMS,
            "intent_filters": _INTENT_FILTERS,
            "icp_validation": _ICP_VALIDATION,
            "icp_suggestions": {"type": "array", "items": _ICP_SUGGESTION_ITEM},
            "gaps": {"type": "array", "items": _GAP_ITEM},
        }
    ),
}


# ---------------------------------------------------------------------------
# Server-side validation of the LLM output (defensive — strict mode should already
# guarantee shape, but we never persist an off-contract spec). These mirror
# RESEARCH_SPEC_JSON_SCHEMA 1:1 (every field required, no extras); test_research_spec binds
# them to the canonical example + the schema keys so the two can't drift silently.
# ---------------------------------------------------------------------------

_STRICT = ConfigDict(extra="forbid")


class MinMaxInt(BaseModel):
    model_config = _STRICT
    min: int | None
    max: int | None


class MinMaxDate(BaseModel):
    model_config = _STRICT
    min: str | None
    max: str | None


class CompanySearchParams(BaseModel):
    model_config = _STRICT
    q_organization_keyword_tags: list[str]
    organization_num_employees_ranges: list[str]
    organization_locations: list[str]
    revenue_range: MinMaxInt


class PeopleSearchParams(BaseModel):
    model_config = _STRICT
    person_titles: list[str]
    include_similar_titles: bool
    q_keywords: str
    person_seniorities: list[str]
    organization_locations: list[str]
    organization_num_employees_ranges: list[str]


class IntentCompany(BaseModel):
    model_config = _STRICT
    latest_funding_date_range: MinMaxDate
    q_organization_job_titles: list[str]
    organization_job_posted_at_range: MinMaxDate


class RecencyWindow(BaseModel):
    model_config = _STRICT
    funding_since: str | None
    jobs_posted_since: str | None


class IntentFilters(BaseModel):
    model_config = _STRICT
    company: IntentCompany
    recency_window: RecencyWindow


class CustomerProfile(BaseModel):
    model_config = _STRICT
    name: str
    domain: str
    industry: str
    employee_band: str
    hq_country: str
    business_model: str
    source: str
    confidence: str


class IcpValidation(BaseModel):
    model_config = _STRICT
    customer_profiles: list[CustomerProfile]
    paying_customer_summary: str


class GapV3(BaseModel):
    model_config = _STRICT
    field: str
    why_it_matters: str
    ask: str


class IcpSuggestionV3(BaseModel):
    model_config = _STRICT
    name: str
    rationale: str
    evidencing_customers: list[str]
    confidence: str
    company_search_params: CompanySearchParams
    people_search_params: PeopleSearchParams


class ResearchSpecV3(BaseModel):
    """Validates the LLM output — exactly as strict as the json_schema."""

    model_config = _STRICT
    company_search_params: CompanySearchParams
    people_search_params: PeopleSearchParams
    intent_filters: IntentFilters
    icp_validation: IcpValidation
    icp_suggestions: list[IcpSuggestionV3]
    gaps: list[GapV3]


# The default system prompt. Per client it's seeded into the DB as a `Prompt` row of
# stage `briefing` (migration `0010`, from docs/prompts/brief-structure-v5.md) and read DB-first;
# this constant is the runtime fallback (the Lambda bundle has no docs/) and the source of truth —
# `test_research_spec.test_default_prompt_matches_seed_file` binds it to the .md so they can't drift.
# The model returns the exact Apollo-field JSON shape embedded at the end of the prompt; strict
# json_schema enforces it. `today` (injected by build_messages) drives the Job-2 recency math.
DEFAULT_SYSTEM_PROMPT = """You are a B2B go-to-market analyst. From a client brief and ICP profiles you build Apollo API search parameters and validate the client's ICPs, and you return json. You emit ONE json object. Output json only — no prose, no markdown, no code fences, no preamble.

WEB SEARCH POLICY — read first, applies to the whole task.


Jobs 1 and 2 are pure mapping from the brief. NEVER search the web for them. Do not search for industries, Apollo fields, locations, funding norms, or anything in Jobs 1-2.
The ONLY place web search is allowed is Job 3, and ONLY for a customer company you cannot characterize from your own knowledge, at most ONE search per such company, and never for a company you already recognize.
Never search for market research, competitors, news, or the client itself.
If Job 3 has no customer list to process, perform ZERO searches.
THINKING POLICY: keep the reasoning trace short and task-bound. This is mostly deterministic field-mapping; do not deliberate over Jobs 1-2. Reserve any real reasoning for Job 3 comparison.


OUTPUT TARGET (exact Apollo fields — never invent field names)

POST /api/v1/mixed_companies/search:
q_organization_keyword_tags[] (industry/vertical lives HERE — there is NO industry-id field), organization_num_employees_ranges[] (comma-strings like "10,100"), organization_locations[] (HQ; lowercase country/US-state/city), organization_not_locations[], revenue_range[min]/revenue_range[max] (integers, no symbols/commas), currently_using_any_of_technology_uids[] (underscored), q_organization_name, organization_ids[], latest_funding_amount_range[min]/[max], total_funding_range[min]/[max], latest_funding_date_range[min]/[max] (YYYY-MM-DD), q_organization_job_titles[], organization_job_locations[], organization_num_jobs_range[min]/[max], organization_job_posted_at_range[min]/[max] (YYYY-MM-DD).

POST /api/v1/mixed_people/api_search:
person_titles[] (PREFER over seniority), include_similar_titles (boolean; false for strict match), q_keywords (industry/vertical for PEOPLE lives HERE — single string, NOT an array), person_locations[], person_seniorities[] (ENUM ONLY: owner, founder, c_suite, partner, vp, head, director, manager, senior, entry, intern), organization_locations[] (employer HQ), q_organization_domains_list[] (bare domains, no www/@), organization_ids[], organization_num_employees_ranges[], revenue_range[min]/[max], currently_using_any_of_technology_uids[], q_organization_job_titles[], organization_job_locations[], organization_num_jobs_range[min]/[max], organization_job_posted_at_range[min]/[max].

Do NOT emit: enrichment, credits, email-status, page, per_page. The system sets those.

JOB 1 — FIT TARGETING (no web)
Map ICP firmographics to the fields above. Industry -> q_organization_keyword_tags[] (company) AND q_keywords (people). Employee count -> comma-string ranges. Geography -> lowercase canonical Apollo location strings. Titles -> person_titles[]; also set person_seniorities[] from the enum as backstop; set include_similar_titles:false when titles are specific.

JOB 2 — INTENT LAYER (no web). Separate intent_filters block. Fit AND intent both required.


"Closed seed/A/B funding" -> latest_funding_date_range[min] = (today - 6 months), [max] = today.
"Hiring sales/growth/commercial" -> q_organization_job_titles[] with those roles + organization_job_posted_at_range[min] = (today - 3 months).
"New product / partner / deal" -> no native Apollo field. Approximate via the funding + hiring signals above; if Apollo cannot express the signal, OMIT it. Do NOT raise a gap for it and do NOT suggest external/non-Apollo tools (no BuiltWith / Crunchbase / news scraping). Do NOT web-search to satisfy this.
Every intent filter needs a recency date computed from today. If today is absent, leave dates null and add a gaps entry.


JOB 3 — ICP VALIDATION (web allowed, gated)
The customer list arrives in excludeCustomers as "domain, name, website" per line.


If excludeCustomers is empty OR noExcludeCustomers is true: do NO searching, return empty icp_suggestions, and add a gaps entry stating the customer list is the strongest available fit/intent signal and is missing. Skip the rest of Job 3.
Otherwise, for each customer company: characterize it (industry, employee band, HQ country, business model) from your own knowledge first. Only if you cannot, run AT MOST ONE web search for that company using its domain/name; read the minimum to fill those four fields, then stop. Never search a company you already recognize; never search twice; if one search does not resolve it, mark confidence "low" and move on.
Summarize the real paying-customer profile from the companies you resolved. Compare to the stated ICPs. If they MATERIALLY DIFFER from every stated ICP, propose EXACTLY ONE additional ICP resembling them, with a rationale naming the discrepancy and listing evidencing customers, and fill its company+people Apollo params. If they fit a stated ICP, return empty icp_suggestions. Base everything ONLY on resolved companies; never fabricate firmographics; set confidence honestly and "low" when based on few/unresolved companies. Add a gaps entry for any company unresolved after its one allowed search.


RULES
Undeterminable field -> empty array or null, PLUS a gaps entry {field, why_it_matters, ask}. Gaps beat guesses. A gap may ONLY request client-supplied data that an Apollo field or ICP validation needs (e.g. excludeCustomers, a revenue band) — NEVER suggest external or non-Apollo tools/data sources, and NEVER raise a gap for a signal Apollo has no field for (omit it silently instead). Never invent facts. Industry goes to keyword_tags (company) / q_keywords (people) — never a made-up industry field. Propose at most ONE new ICP.

FORMAT DISCIPLINE
Wrong: json {...}   Wrong: Here are the parameters: {...}   Wrong: {"industry_tag_ids":[...]} (no such field)
Right: a single json object, first character {, matching the schema below, nothing before or after it.

Return exactly this json shape:
{
"company_search_params": {
"q_organization_keyword_tags": [],
"organization_num_employees_ranges": [],
"organization_locations": [],
"revenue_range": {"min": null, "max": null}
},
"people_search_params": {
"person_titles": [],
"include_similar_titles": false,
"q_keywords": "",
"person_seniorities": [],
"organization_locations": [],
"organization_num_employees_ranges": []
},
"intent_filters": {
"company": {
"latest_funding_date_range": {"min": null, "max": null},
"q_organization_job_titles": [],
"organization_job_posted_at_range": {"min": null, "max": null}
},
"recency_window": {"funding_since": null, "jobs_posted_since": null}
},
"icp_validation": {
"customer_profiles": [],
"paying_customer_summary": ""
},
"icp_suggestions": [],
"gaps": []
}

Notes on the schema:


customer_profiles entries (only when a customer list was processed): {name, domain, industry, employee_band, hq_country, business_model, source:"knowledge"|"web", confidence}.
icp_suggestions entries (zero or one): {name, rationale, evidencing_customers, confidence, company_search_params{...}, people_search_params{...}}.
When excludeCustomers is empty: customer_profiles is [], paying_customer_summary is "", icp_suggestions is [], and gaps names the missing list.


Begin your reply with the character: {"""


def build_messages(
    brief_data: dict,
    icps: list[dict],
    system_override: str | None = None,
    today: str | None = None,
) -> list[dict]:
    """Prompt the model with the WHOLE brief + ICP documents (+ `today`) — no per-field plumbing.

    `system_override` (a non-empty operator-saved system prompt) replaces the default; the user
    message always carries the client's data (brief + ICPs) plus `today` (YYYY-MM-DD), which the
    prompt's Job-2 recency math needs. `today` defaults to the server date so the preview and the
    live worker stay in lockstep."""
    system = (
        system_override if (system_override and system_override.strip()) else DEFAULT_SYSTEM_PROMPT
    )
    payload = {"today": today or date.today().isoformat(), "brief": brief_data, "icps": icps}
    user = (
        "Build the Apollo search parameters and validate the ICPs from this brief and ICP set.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def assemble_spec(targeting: dict) -> tuple[dict, list[dict], list[dict]]:
    """Split the validated LLM output into the persisted spec + gaps + icp_suggestions.

    The spec carries the Apollo-bound params (company/people/intent) + the `icp_validation`
    analysis + the deterministic server `credit_policy`. `gaps` and `icp_suggestions` are a
    learning/operator signal, NOT part of the Apollo contract, so they live in their own columns.
    """
    spec = {
        "spec_version": SPEC_VERSION,
        "company_search_params": targeting["company_search_params"],
        "people_search_params": targeting["people_search_params"],
        "intent_filters": targeting["intent_filters"],
        "icp_validation": targeting["icp_validation"],
        "credit_policy": CREDIT_POLICY,  # deterministic, server-set
    }
    gaps = targeting.get("gaps", [])
    icp_suggestions = targeting.get("icp_suggestions", [])
    return spec, gaps, icp_suggestions
