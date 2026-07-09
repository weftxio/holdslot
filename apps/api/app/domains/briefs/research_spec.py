"""ResearchSpec v4 — the per-ICP Apollo-mapped Brief→targeting contract + the LLM seam (B4/B6).

Two halves with different stability profiles (see docs/initial-build-plan.md → Phase B):
  * **The LLM emits per-ICP targeting + ICP validation** — `icp_targeting` (ONE entry per input
    ICP: `icp_id`/`icp_name` echoed + `company_search_params`/`people_search_params`/
    `intent_filters`), plus brief-level `icp_validation`, `icp_suggestions`, `gaps` — via a strict
    `json_schema` so the structure can't drift. It is fed the *whole* Brief + ICP documents
    (no per-field plumbing → churn-proof prompt), plus `today` for date context.
  * **The credit policy is deterministic server config** (`CREDIT_POLICY`), merged in at save
    time — never LLM-inferred. Credit rules are policy, not judgment.

The persisted spec = `{spec_version, icp_targeting, icp_validation, credit_policy}`; `gaps` +
`icp_suggestions` are stored in their own columns on the `ResearchSpec` row.

**v5 (no intent date windows, 2026-07-06):** founder verdict — the funding/jobs-posted date
ranges (`latest_funding_date_range`, `organization_job_posted_at_range`, `recency_window`) always
over-constrained the company search, so they are removed from the contract entirely. The intent
layer is now just the hiring-titles signal (`q_organization_job_titles`). `apollo_map` also stops
forwarding the date fields from OLD stored specs, so they are dead everywhere, not just absent
from new generations.

**v4 (multi-ICP, 2026-07-06):** v3 forced ONE merged targeting block per tenant, so a second ICP
was silently dropped or crashed the strict-schema validation. v4 makes "one block per ICP" the
contract: `reconcile_icp_targeting` verifies every input ICP got a block (repairing echo typos by
name), and `targeting_for_icp` resolves the block a find/score call should use — with a v3
single-block fallback so pre-multi-ICP specs keep working until the next regenerate. No migration —
`spec` is JSONB, append-only (same as the v2→v3 transition).

**v3 (Apollo-native, 2026-06-22):** the LLM emits **exact Apollo request fields** by name
(`q_organization_keyword_tags`, `organization_num_employees_ranges` comma-strings,
`person_seniorities` enum, …) — no intermediate vocabulary to translate. `apollo_map` (Phase C)
forwards them straight to `mixed_companies/search` / `mixed_people/api_search`. Buying signals live
in a separate `intent_filters` block (funding date + hiring titles/dates). `icp_validation`
characterizes the real paying customers (from the brief's `excludeCustomers` list) for the ICP-vs-
reality check.
"""

from __future__ import annotations

import json
from datetime import date

from pydantic import BaseModel, ConfigDict

SPEC_VERSION = 6  # v6 = v5 + person_titles (D+ Stage 2: query the titles the rubric scores)
# v10 = v9 + the keyword-yield table + customer-anchor grounding blocks (D+ Stage 4); the tech-UID
# filters are server-resolved, never model-emitted. OUTPUT schema is unchanged (still spec v6).
PROMPT_VERSION = "brief-structure-v11"
PURPOSE = "brief_structure"

# Apollo's fixed `person_seniorities` enum = the app's "Management Level" facet (the only accepted
# values, in Apollo's own order). The LLM is constrained to these at generation; `apollo_map` passes
# them straight through to `mixed_people/api_search`. Verified live against Apollo (2026-06-24): the
# per-value `total_entries` counts reproduce Apollo's UI sidebar exactly.
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

# Apollo's `person_department_or_subdepartments` taxonomy = the app's "Departments & Job Function"
# facet. Two tiers: 14 master departments → their subdepartments. NOT in Apollo's public API docs;
# reconstructed from cross-agreeing community mirrors + verified live (a valid value returns a real
# count, a bogus one silently returns 0 — never an error, so we constrain the LLM to this enum).
# ⚠️ `workforce_mangement` and `opthalmology` are misspelled in Apollo's own taxonomy — keep verbatim.
DEPARTMENT_TAXONOMY: dict[str, list[str]] = {
    "c_suite": [
        "executive", "finance_executive", "founder", "human_resources_executive",
        "information_technology_executive", "legal_executive", "marketing_executive",
        "medical_health_executive", "operations_executive", "sales_executive",
    ],
    "product_management": ["product_development", "product_management"],
    "master_engineering_technical": [
        "artificial_intelligence_machine_learning", "bioengineering", "biometrics",
        "business_intelligence", "chemical_engineering", "cloud_mobility", "data_science", "devops",
        "digital_transformation", "emerging_technology_innovation", "engineering_technical",
        "industrial_engineering", "mechanic", "mobile_development", "project_management",
        "research_development", "scrum_master_agile_coach", "software_development",
        "support_technical_services", "technician", "technology_operations",
        "test_quality_assurance", "ui_ux", "web_development",
    ],
    "design": ["all_design", "product_ui_ux_design", "graphic_design"],
    "education": ["teacher", "principal", "superintendent", "professor"],
    "master_finance": [
        "accounting", "finance", "financial_planning_analysis", "financial_reporting",
        "financial_strategy", "financial_systems", "internal_audit_control", "investor_relations",
        "mergers_acquisitions", "real_estate_finance", "financial_risk", "shared_services",
        "sourcing_procurement", "tax", "treasury",
    ],
    "master_human_resources": [
        "compensation_benefits", "culture_diversity_inclusion", "employee_labor_relations",
        "health_safety", "human_resource_information_system", "human_resources",
        "hr_business_partner", "learning_development", "organizational_development",
        "recruiting_talent_acquisition", "talent_management", "workforce_mangement",
        "people_operations",
    ],
    "master_information_technology": [
        "application_development", "business_service_management_itsm", "collaboration_web_app",
        "data_center", "data_warehouse", "database_administration", "ecommerce_development",
        "enterprise_architecture", "help_desk_desktop_services", "hr_financial_erp_systems",
        "information_security", "information_technology", "infrastructure", "it_asset_management",
        "it_audit_it_compliance", "it_operations", "it_procurement", "it_strategy", "it_training",
        "networking", "project_program_management", "quality_assurance", "retail_store_systems",
        "servers", "storage_disaster_recovery", "telecommunications", "virtualization",
    ],
    "master_legal": [
        "acquisitions", "compliance", "contracts", "corporate_secretary", "ediscovery", "ethics",
        "governance", "governmental_affairs_regulatory_law", "intellectual_property_patent",
        "labor_employment", "lawyer_attorney", "legal", "legal_counsel", "legal_operations",
        "litigation", "privacy",
    ],
    "master_marketing": [
        "advertising", "brand_management", "content_marketing", "customer_experience",
        "customer_marketing", "demand_generation", "digital_marketing", "ecommerce_marketing",
        "event_marketing", "field_marketing", "lead_generation", "marketing",
        "marketing_analytics_insights", "marketing_communications", "marketing_operations",
        "product_marketing", "public_relations", "search_engine_optimization_pay_per_click",
        "social_media_marketing", "strategic_communications", "technical_marketing",
    ],
    "medical_health": [
        "anesthesiology", "chiropractics", "clinical_systems", "dentistry", "dermatology",
        "doctors_physicians", "epidemiology", "first_responder", "infectious_disease",
        "medical_administration", "medical_education_training", "medical_research", "medicine",
        "neurology", "nursing", "nutrition_dietetics", "obstetrics_gynecology", "oncology",
        "opthalmology", "optometry", "orthopedics", "pathology", "pediatrics", "pharmacy",
        "physical_therapy", "psychiatry", "psychology", "public_health", "radiology", "social_work",
    ],
    "master_operations": [
        "call_center", "construction", "corporate_strategy", "customer_service_support",
        "enterprise_resource_planning", "facilities_management", "leasing", "logistics",
        "office_operations", "operations", "physical_security", "project_development",
        "quality_management", "real_estate", "safety", "store_operations", "supply_chain",
    ],
    "master_sales": [
        "account_management", "business_development", "channel_sales",
        "customer_retention_development", "customer_success", "field_outside_sales", "inside_sales",
        "partnerships", "revenue_operations", "sales", "sales_enablement", "sales_engineering",
        "sales_operations", "sales_training",
    ],
    "consulting": ["consultant"],
}
# The 14 master values (the top-level facet rows shown with live counts in Find Settings).
MASTER_DEPARTMENTS = list(DEPARTMENT_TAXONOMY.keys())
# Flat set of every accepted value (masters + subs) — the enum the LLM and server validate against.
# Order-preserving dedupe: `product_management` is both a master and a sub in Apollo's own taxonomy.
DEPARTMENT_ENUM = list(
    dict.fromkeys(
        MASTER_DEPARTMENTS + [sub for subs in DEPARTMENT_TAXONOMY.values() for sub in subs]
    )
)

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
_CONF = {"type": "string", "enum": ["low", "medium", "high"]}
_MIN_MAX_INT = _obj({"min": _INT_OR_NULL, "max": _INT_OR_NULL})  # revenue_range

# POST /api/v1/mixed_companies/search — the subset the model emits (fit firmographics).
_COMPANY_SEARCH_PARAMS = _obj(
    {
        "q_organization_keyword_tags": _arr_str(),  # industry/vertical (no industry-id field)
        "organization_num_employees_ranges": _arr_str(),  # comma-strings e.g. "10,100"
        "organization_locations": _arr_str(),  # HQ; lowercase country/state/city
        "revenue_range": _MIN_MAX_INT,  # integers, no symbols/commas
    }
)

# POST /api/v1/mixed_people/api_search — the subset the model emits (fit personas). D+ Stage 2:
# personas now lead with `person_titles` (the precise buying-role wordings) BECAUSE the fit rubric
# scores a 14-pt title dimension — querying titles aligns the search with what we score ("Query =
# rubric"). The two native facets — Management Level (`person_seniorities`) × Department/Job Function
# (`person_department_or_subdepartments`) — stay as the AND-free broadening fallback: the relax
# ladder tries titles (strict→fuzzy) first, then drops to the facets so an org whose people use
# non-standard title wording still yields people (the Luma over-constraint is now a fallback, not a
# dead end). `include_similar_titles` is NOT model-emitted — the ladder toggles it per rung.
_PEOPLE_SEARCH_PARAMS = _obj(
    {
        "person_titles": _arr_str(),  # exact buying-role titles; ladder queries these first
        "person_seniorities": _arr_enum(SENIORITY_ENUM),  # Management Level facet (fallback)
        "person_department_or_subdepartments": _arr_enum(
            DEPARTMENT_ENUM
        ),  # Departments & Job Function facet (fallback)
        "q_keywords": {"type": "string"},  # industry/vertical for PEOPLE — single string
        "organization_locations": _arr_str(),  # employer HQ (broad search only)
        "organization_num_employees_ranges": _arr_str(),  # comma-strings (broad search only)
    }
)

# Intent layer — the hiring buying-signal as a native Apollo filter (Job 2). Kept separate from
# fit. v5 removed the funding/jobs-posted DATE windows entirely (they always over-constrained the
# search — founder verdict 2026-07-06); hiring titles are the one intent signal that stays.
_INTENT_FILTERS = _obj(
    {
        "company": _obj(
            {
                "q_organization_job_titles": _arr_str(),  # hiring-signal roles
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
        "icp_name": {"type": "string"},  # the ICP the gap concerns; "" = whole-brief gap
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

# One per-ICP targeting entry (v4). `icp_id`/`icp_name` are echoed from the input ICP documents
# so every block is attributable; `reconcile_icp_targeting` verifies the echo after the call.
_ICP_TARGETING_ITEM = _obj(
    {
        "icp_id": {"type": "string"},
        "icp_name": {"type": "string"},
        "company_search_params": _COMPANY_SEARCH_PARAMS,
        "people_search_params": _PEOPLE_SEARCH_PARAMS,
        "intent_filters": _INTENT_FILTERS,
    }
)

RESEARCH_SPEC_JSON_SCHEMA: dict = {
    "name": "ResearchSpec",
    "strict": True,
    "schema": _obj(
        {
            "icp_targeting": {"type": "array", "items": _ICP_TARGETING_ITEM},
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


class CompanySearchParams(BaseModel):
    model_config = _STRICT
    q_organization_keyword_tags: list[str]
    organization_num_employees_ranges: list[str]
    organization_locations: list[str]
    revenue_range: MinMaxInt


class PeopleSearchParams(BaseModel):
    model_config = _STRICT
    person_titles: list[str]  # D+ Stage 2 — the titles the ladder queries first (rubric-aligned)
    person_seniorities: list[str]
    person_department_or_subdepartments: list[str]
    q_keywords: str
    organization_locations: list[str]
    organization_num_employees_ranges: list[str]


class IntentCompany(BaseModel):
    model_config = _STRICT
    q_organization_job_titles: list[str]


class IntentFilters(BaseModel):
    model_config = _STRICT
    company: IntentCompany


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


class GapV4(BaseModel):
    model_config = _STRICT
    field: str
    why_it_matters: str
    ask: str
    icp_name: str  # "" = whole-brief gap


class IcpSuggestionV4(BaseModel):
    model_config = _STRICT
    name: str
    rationale: str
    evidencing_customers: list[str]
    confidence: str
    company_search_params: CompanySearchParams
    people_search_params: PeopleSearchParams


class IcpTargetingV4(BaseModel):
    model_config = _STRICT
    icp_id: str
    icp_name: str
    company_search_params: CompanySearchParams
    people_search_params: PeopleSearchParams
    intent_filters: IntentFilters


class ResearchSpecV4(BaseModel):
    """Validates the LLM output — exactly as strict as the json_schema."""

    model_config = _STRICT
    icp_targeting: list[IcpTargetingV4]
    icp_validation: IcpValidation
    icp_suggestions: list[IcpSuggestionV4]
    gaps: list[GapV4]


# The default system prompt. Per client it's seeded into the DB as a `Prompt` row of
# stage `briefing` (migration `0010`, from docs/prompts/brief-structure-v5.md) and read DB-first;
# this constant is the runtime fallback (the Lambda bundle has no docs/) and the source of truth —
# `test_research_spec.test_default_prompt_matches_seed_file` binds it to the .md so they can't drift.
# The model returns the exact Apollo-field JSON shape embedded at the end of the prompt; strict
# json_schema enforces it. `today` (injected by build_messages) is date context only since v5 dropped the date windows.
DEFAULT_SYSTEM_PROMPT = """You are a B2B go-to-market analyst. From a client brief and ICP profiles you build Apollo API search parameters for EACH ICP separately and validate the client's ICPs, and you return json. You emit ONE json object. Output json only — no prose, no markdown, no code fences, no preamble.

WEB SEARCH POLICY — read first, applies to the whole task.


Jobs 1 and 2 are pure mapping from the brief. NEVER search the web for them. Do not search for industries, Apollo fields, locations, funding norms, or anything in Jobs 1-2.
The ONLY place web search is allowed is Job 3, and ONLY for a customer company you cannot characterize from your own knowledge, at most ONE search per such company, and never for a company you already recognize.
Never search for market research, competitors, news, or the client itself.
If Job 3 has no customer list to process, perform ZERO searches.
THINKING POLICY: keep the reasoning trace short and task-bound. This is mostly deterministic field-mapping; do not deliberate over Jobs 1-2. Reserve any real reasoning for Job 3 comparison.


OUTPUT TARGET (exact Apollo fields — never invent field names)

POST /api/v1/mixed_companies/search:
q_organization_keyword_tags[] (industry/vertical lives HERE — there is NO industry-id field), organization_num_employees_ranges[] (comma-strings like "10,100"), organization_locations[] (HQ; lowercase country/US-state/city), organization_not_locations[], revenue_range[min]/revenue_range[max] (integers, no symbols/commas), currently_using_any_of_technology_uids[] (underscored), q_organization_name, organization_ids[], q_organization_job_titles[], organization_job_locations[]. Funding-date and job-posted-date window filters are NOT used in this system — never emit them.

POST /api/v1/mixed_people/api_search:
person_seniorities[] = Management Level (ENUM ONLY: owner, founder, c_suite, partner, vp, head, director, manager, senior, entry, intern). person_department_or_subdepartments[] = Departments & Job Function (ENUM; 14 master departments: c_suite, product_management, master_engineering_technical, design, education, master_finance, master_human_resources, master_information_technology, master_legal, master_marketing, medical_health, master_operations, master_sales, consulting — each with finer subdepartments, e.g. master_sales→business_development/account_management/partnerships, master_marketing→demand_generation/product_marketing, master_finance→accounting/treasury; use a master for breadth or subdepartments for precision). person_titles[] = the exact buying-role titles the person holds (e.g. "VP of Sales", "Head of Revenue", "Chief Revenue Officer") — emit 3-6 common wording variants of the SAME role so the search matches local title styles. q_keywords (industry/vertical for PEOPLE lives HERE — single string, NOT an array), organization_locations[] (employer HQ), organization_num_employees_ranges[]. Emit person_titles AND the two facets together: the system queries titles first (they map 1:1 to the fit rubric's title dimension) and falls back to Management Level × Department automatically, so both must be populated. Do NOT emit include_similar_titles — the system toggles strict/fuzzy title matching itself.

Do NOT emit: enrichment, credits, email-status, page, per_page, or the technology-UID filters (currently_using_any_of_technology_uids / currently_not_using_any_of_technology_uids). The system sets those — it resolves the ICP's technologies and prior-outcome tech to Apollo UIDs itself.

PER-ICP STRUCTURE — the core output rule.
The input carries an icps array. Emit EXACTLY ONE icp_targeting entry PER input ICP: echo that ICP's id into icp_id and its name into icp_name byte-for-byte as given. NEVER merge two ICPs into one entry, NEVER skip an ICP, NEVER invent an entry for an ICP not in the input. Each entry carries its own company_search_params, people_search_params and intent_filters built from THAT ICP (plus shared brief context). If the icps array is empty, emit exactly one entry derived from the brief alone with icp_id "" and icp_name "Brief-derived".

JOB 1 — FIT TARGETING, once per ICP (no web)
For each ICP, map THAT ICP's firmographics to the fields above. Industry -> q_organization_keyword_tags[] (company) AND q_keywords (people). Employee count -> comma-string ranges. Geography -> lowercase canonical Apollo location strings. Persona/titles -> map the BUYING-ROLE intent to BOTH (a) person_titles[] — 3-6 exact-wording variants of the role, AND (b) the two facets person_seniorities[] (Management Level) AND person_department_or_subdepartments[] (Department/Job Function). E.g. "Head of Sales / CCO / VP Revenue" -> person_titles ["VP of Sales", "Head of Sales", "Chief Revenue Officer", "Sales Director", "VP Revenue"] + seniorities [c_suite, vp, head, director] + departments [master_sales]; "Head of Marketing" -> person_titles ["Head of Marketing", "VP Marketing", "Marketing Director", "CMO"] + seniorities [vp, head, director] + departments [master_marketing]; a founder-led SMB -> person_titles ["Founder", "Co-Founder", "CEO", "Owner"] + seniorities [owner, founder, c_suite] + the relevant department. Pick a master department for breadth, subdepartments for precision. The system queries titles first (precise, rubric-aligned) and falls back to the facets automatically. Within person_titles list common synonyms of ONE role (they OR together); within each facet keep a SHORT list of the levels/functions that actually buy — over-listing one facet is fine (OR), but a needless second facet narrows (AND). Two ICPs may legitimately produce very different params — that divergence is the point; do not average them.
KEYWORD YIELD: the payload may carry keyword_yield[] — a per-keyword scoreboard from PRIOR finds for this client: {keyword, good (Strong/Good rows it produced), total (scored rows carrying it), yield_pct, optional total_entries (Apollo match breadth)}. This is measured outcome data and the ONLY keyword-feedback signal (it supersedes any bare avoid list — a 0%-yield keyword IS a negative, a high-yield one is a keeper). Prefer keywords with a HIGH yield_pct when building q_organization_keyword_tags / q_keywords. Treat a 0% (or very low) yield_pct over a meaningful total as a signal to AVOID: do NOT place that keyword in q_organization_keyword_tags (company) or q_keywords (people) — replace it with a more precise alternative that still captures the ICP. This is guidance, not an absolute ban — if such a term is genuinely essential to the ICP, keep it but tighten the other filters around it. A very large total_entries with low yield_pct means the term is too broad — narrow it. Do not chase yield off-ICP: never add a high-yield keyword that does not describe THIS ICP. Never echo keyword_yield back in the output.
CUSTOMER ANCHORS: the payload may carry customer_anchors[] — the REAL enriched firmographics of the client's existing paying customers: {domain, industry, industries[], keywords[], employee_band}. This is the strongest ground truth for who actually buys. Use it to ground Job 1: bias q_organization_keyword_tags / q_keywords toward the anchors' recurring industry + keyword language, and set organization_num_employees_ranges to span the anchors' employee_bands when the brief does not fix a size. Use it in Job 3 to characterize the paying-customer profile and to decide whether the stated ICPs match reality. Ground, do not narrow blindly — the anchors are a few examples, so widen a band or keyword set they clearly under-cover rather than overfitting to them. Never echo customer_anchors back in the output.

JOB 2 — INTENT LAYER, once per ICP (no web). Each icp_targeting entry carries its own intent_filters block with EXACTLY ONE field: q_organization_job_titles[]. The hiring signal usually comes from the brief and may be identical across entries — that is fine; tailor the titles to an ICP when a signal names roles specific to it.


"Hiring sales/growth/commercial" -> q_organization_job_titles[] with those roles.
Any other signal ("closed funding", "new product / partner / deal", ...) -> date/window filters are NOT used in this system. If a signal cannot be expressed as hiring job titles, OMIT it silently: do NOT emit funding or job-posted date ranges, do NOT raise a gap for it, and do NOT suggest external/non-Apollo tools (no BuiltWith / Crunchbase / news scraping). Do NOT web-search to satisfy this.


JOB 3 — ICP VALIDATION (web allowed, gated)
The customer list arrives in excludeCustomers as "domain, name, website" per line.


If excludeCustomers is empty OR noExcludeCustomers is true: do NO searching, return empty icp_suggestions, and add a gaps entry stating the customer list is the strongest available fit/intent signal and is missing. Skip the rest of Job 3.
Otherwise, for each customer company: characterize it (industry, employee band, HQ country, business model) from your own knowledge first. Only if you cannot, run AT MOST ONE web search for that company using its domain/name; read the minimum to fill those four fields, then stop. Never search a company you already recognize; never search twice; if one search does not resolve it, mark confidence "low" and move on.
Summarize the real paying-customer profile from the companies you resolved. Compare to the stated ICPs. If they MATERIALLY DIFFER from every stated ICP, propose EXACTLY ONE additional ICP resembling them, with a rationale naming the discrepancy and listing evidencing customers, and fill its company+people Apollo params. If they fit a stated ICP, return empty icp_suggestions. Base everything ONLY on resolved companies; never fabricate firmographics; set confidence honestly and "low" when based on few/unresolved companies. Add a gaps entry for any company unresolved after its one allowed search.


RULES
Undeterminable field -> empty array or null, PLUS a gaps entry {field, why_it_matters, ask, icp_name} — icp_name is the name of the ICP the gap concerns, or "" when it concerns the whole brief. Gaps beat guesses. A gap may ONLY request client-supplied data that an Apollo field or ICP validation needs (e.g. excludeCustomers, a revenue band) — NEVER suggest external or non-Apollo tools/data sources, and NEVER raise a gap for a signal Apollo has no field for (omit it silently instead). Never invent facts. Industry goes to keyword_tags (company) / q_keywords (people) — never a made-up industry field. Propose at most ONE new ICP.

FORMAT DISCIPLINE
Wrong: json {...}   Wrong: Here are the parameters: {...}   Wrong: {"industry_tag_ids":[...]} (no such field)   Wrong: one merged icp_targeting entry for two ICPs
Right: a single json object, first character {, matching the schema below, nothing before or after it.

Return exactly this json shape:
{
"icp_targeting": [
{
"icp_id": "",
"icp_name": "",
"company_search_params": {
"q_organization_keyword_tags": [],
"organization_num_employees_ranges": [],
"organization_locations": [],
"revenue_range": {"min": null, "max": null}
},
"people_search_params": {
"person_titles": [],
"person_seniorities": [],
"person_department_or_subdepartments": [],
"q_keywords": "",
"organization_locations": [],
"organization_num_employees_ranges": []
},
"intent_filters": {
"company": {
"q_organization_job_titles": []
}
}
}
],
"icp_validation": {
"customer_profiles": [],
"paying_customer_summary": ""
},
"icp_suggestions": [],
"gaps": []
}

Notes on the schema:


icp_targeting has EXACTLY one entry per input ICP (or the single "Brief-derived" entry when icps is empty), echoing id and name verbatim.
customer_profiles entries (only when a customer list was processed): {name, domain, industry, employee_band, hq_country, business_model, source:"knowledge"|"web", confidence}.
icp_suggestions entries (zero or one): {name, rationale, evidencing_customers, confidence, company_search_params{...}, people_search_params{...}}.
When excludeCustomers is empty: customer_profiles is [], paying_customer_summary is "", icp_suggestions is [], and gaps names the missing list.


Begin your reply with the character: {"""


def build_messages(
    brief_data: dict,
    icps: list[dict],
    system_override: str | None = None,
    today: str | None = None,
    keyword_yield: list[dict] | None = None,
    customer_anchors: list[dict] | None = None,
) -> list[dict]:
    """Prompt the model with the WHOLE brief + ICP documents (+ `today`) — no per-field plumbing.

    `system_override` (a non-empty operator-saved system prompt) replaces the default; the user
    message always carries the client's data (brief + ICPs) plus `today` (YYYY-MM-DD) as date
    context. `today` defaults to the server date so the preview and the live worker stay in
    lockstep. The learning blocks ride in the payload ONLY when non-empty (no empty blocks): D+
    Stage 4 `keyword_yield` (the per-keyword win-rate scoreboard — the sole keyword-feedback signal,
    it supersedes the old bare avoid list) + `customer_anchors` (enriched real paying-customer
    firmographics to ground targeting). The prompt teaches the model how to read each."""
    system = (
        system_override if (system_override and system_override.strip()) else DEFAULT_SYSTEM_PROMPT
    )
    payload = {"today": today or date.today().isoformat(), "brief": brief_data, "icps": icps}
    if keyword_yield:
        payload["keyword_yield"] = keyword_yield
    if customer_anchors:
        payload["customer_anchors"] = customer_anchors
    user = (
        "Build the Apollo search parameters PER ICP (one icp_targeting entry each) and validate "
        "the ICPs from this brief and ICP set.\n\n" + json.dumps(payload, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def assemble_spec(targeting: dict) -> tuple[dict, list[dict], list[dict]]:
    """Split the validated LLM output into the persisted spec + gaps + icp_suggestions.

    The spec carries the per-ICP Apollo-bound blocks (`icp_targeting`) + the `icp_validation`
    analysis + the deterministic server `credit_policy`. `gaps` and `icp_suggestions` are a
    learning/operator signal, NOT part of the Apollo contract, so they live in their own columns.
    """
    spec = {
        "spec_version": SPEC_VERSION,
        "icp_targeting": targeting["icp_targeting"],
        "icp_validation": targeting["icp_validation"],
        "credit_policy": CREDIT_POLICY,  # deterministic, server-set
    }
    gaps = targeting.get("gaps", [])
    icp_suggestions = targeting.get("icp_suggestions", [])
    return spec, gaps, icp_suggestions


def targeting_for_icp(spec_blob: dict | None, icp_id) -> dict | None:
    """Resolve the Apollo targeting block one find/score call should use — the ONE spec reader.

    v4 (`icp_targeting` list): match `icp_id` by string compare. `icp_id=None` resolves only when
    the spec has exactly one block (single-ICP convenience); a multi-block spec with no/unknown
    `icp_id` returns None and the caller decides the 400 ("pick an ICP" / "regenerate"). An id
    that matches no block also returns None — never silently hand back another ICP's targeting.
    v3 and earlier (single top-level block): always returns that block, whatever the `icp_id`, so
    pre-multi-ICP specs keep working until the next regenerate.
    """
    blob = spec_blob or {}
    blocks = blob.get("icp_targeting")
    if blocks is None:  # v3 fallback — the legacy single merged block
        if not blob:
            return None
        return {
            "company_search_params": blob.get("company_search_params") or {},
            "people_search_params": blob.get("people_search_params") or {},
            "intent_filters": blob.get("intent_filters") or {},
        }
    if not blocks:
        return None
    if icp_id is None:
        return blocks[0] if len(blocks) == 1 else None
    key = str(icp_id)
    for b in blocks:
        if str(b.get("icp_id")) == key:
            return b
    return None


def reconcile_icp_targeting(
    blocks: list[dict], expected: dict[str, str]
) -> tuple[list[dict], str | None]:
    """Post-validate the LLM's per-ICP blocks against the input ICP set → (repaired, error).

    The model must emit one block per input ICP with `icp_id` echoed verbatim. An echo typo is
    repaired by exact (case-insensitive) `icp_name` match; leftover unmatched blocks are dropped;
    a still-missing ICP is a hard error naming the profile — the original multi-ICP bug (a
    silently ignored second ICP) can never recur silently. Output order follows the input order.
    With no input ICPs (`expected` empty, brief-only tenant) any non-empty list passes through.
    """
    if not expected:
        return (blocks, None) if blocks else ([], "the model returned no targeting blocks")
    by_id: dict[str, dict] = {}
    unmatched: list[dict] = []
    for b in blocks:
        bid = str(b.get("icp_id") or "")
        if bid in expected and bid not in by_id:
            by_id[bid] = b
        else:
            unmatched.append(b)
    for iid, name in expected.items():  # repair echo typos by name
        if iid in by_id:
            continue
        for b in unmatched:
            if (b.get("icp_name") or "").strip().lower() == (name or "").strip().lower():
                b["icp_id"], b["icp_name"] = iid, name
                by_id[iid] = b
                unmatched.remove(b)
                break
    missing = [name or iid for iid, name in expected.items() if iid not in by_id]
    if missing:
        return [], "scope generation missed ICP(s): " + ", ".join(missing)
    return [by_id[iid] for iid in expected], None


def merge_targeting(prior_spec: dict, new_blocks: list[dict], doc_order: list[str]) -> list[dict]:
    """Splice freshly-generated per-ICP blocks into the prior spec for a SELECTIVE re-scope (the
    operator re-ran AI Scoping for only some ICPs). For each ICP in the current input order, use the
    block this run produced when present, else fall back to the prior spec's block for that ICP.

    ICPs with neither a fresh nor a prior block are omitted (the UI shows them as 'no AI scope yet');
    an ICP dropped from the brief falls out because it is absent from `doc_order`. Output order
    follows the current input order. Only the selected ICPs' targeting changes — every other ICP's
    block is carried over verbatim, so a per-ICP regenerate never disturbs the untouched profiles.
    """
    prior = {str(b.get("icp_id")): b for b in (prior_spec.get("icp_targeting") or [])}
    fresh = {str(b.get("icp_id")): b for b in new_blocks}
    out: list[dict] = []
    for iid in doc_order:
        block = fresh.get(str(iid)) or prior.get(str(iid))
        if block is not None:
            out.append(block)
    return out
