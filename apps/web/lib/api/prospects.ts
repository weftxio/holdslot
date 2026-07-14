// --- Phase C (S2) — Prospects: Apollo find + enrich --------------------------

import { authFetch, detail, pageThrough, type Feed } from "./core";
import type { FitStage } from "./briefs";

// Scoring v2 (docs/initial-build-plan.md §D+.2) — the 4-label verdict replaces the 0–100 AI Score.
// `null` label = not yet (re)scored ("needs re-score"). Sort/UI priority: now → soon → low → excluded.
export type ScoreLabel = "contact_now" | "contact_soon" | "low_fit" | "excluded_by_rules";
export type Subscores = Record<string, number>; // axis → 1–5 (company: deal_fit/outbound_gap/…)

export type ProspectApi = {
  id: string;
  identity_key: string;
  icp_id: string | null;
  company_id: string | null;
  run_id: string | null;
  full_name: string;
  company: string;
  domain: string;
  linkedin_url: string;
  email: string;
  email_valid: boolean;
  title: string;
  company_industry: string;
  company_size: string;
  fit_reason: string;
  // Scoring v2 — the 4-label verdict (the v1 fit_score/fit_tier fields were retired in V2-4).
  label: ScoreLabel | null;
  score_total: number | null;
  reason: string;
  subscores: Subscores;
  flags: string[];
  icp: string | null;
  source: string; // "apollo" | "manual"
  status: string; // "found" | "confirmed" | "scored" | "score_error" | ...
  created_at: string | null;
};
// Stage-1 company row (company-first two-stage flow).
export type CompanyApi = {
  id: string;
  icp_id: string | null;
  run_id: string | null;
  domain: string;
  website: string;
  linkedin_url: string;
  name: string;
  industry: string;
  size: string;
  country: string;
  fit_reason: string;
  business_model: string; // "B2B" | "B2C" | "Complex" | "Unknown" | "" (unclassified)
  // Scoring v2 — the 4-label verdict (the v1 fit_score/fit_tier/market_excluded fields were retired
  // in V2-4; a market-gated company now carries label `excluded_by_rules`).
  label: ScoreLabel | null;
  score_total: number | null;
  reason: string;
  subscores: Subscores;
  flags: string[];
  icp: string | null;
  enrichment: CompanyEnrichment;
  source: string; // "apollo" | "manual"
  status: string; // "discovered" | "people_found" | ...
  created_at: string | null;
};
// The 8 Apollo-enrich fields surfaced in the workspace "Enrichment" column (normalized server-side
// from Company.evidence). All optional — a manual / un-enriched row carries empty values.
export type CompanyEnrichment = {
  short_description: string;
  industries: string[];
  annual_revenue: number | null;
  founded_year: number | null;
  headcount_growth_12mo: number | null; // fraction: 0.04 = +4%
  technologies: string[];
  keywords: string[];
  hq: string;
};
// Result of an Apollo find run (Flow A companies or Flow B people).
export type FindResult = {
  run_id: string;
  found: number;
  dropped: number;
  companies: CompanyApi[];
  prospects: ProspectApi[];
};
export type SourcingDocApi = {
  stage: string;
  version: number;
  body: string;
  created_at: string | null;
};
export type SourcingDocList = {
  company_fit: SourcingDocApi | null;
  prospect_fit: SourcingDocApi | null;
};

export async function listProspects(client: string): Promise<Feed<ProspectApi>> {
  return pageThrough<ProspectApi>(`/${client}/prospects`);
}

export async function getSourcingDocs(client: string): Promise<SourcingDocList> {
  const r = await authFetch(`/${client}/sourcing-docs`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function saveSourcingDoc(
  client: string,
  stage: FitStage,
  body: string
): Promise<SourcingDocApi> {
  const r = await authFetch(`/${client}/sourcing-docs`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ stage, body }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// --- Phase C stage 1 — Companies (find → review → select) --------------------

export async function listCompanies(client: string): Promise<Feed<CompanyApi>> {
  return pageThrough<CompanyApi>(`/${client}/companies`);
}

export type CompanyManual = {
  domain: string;
  name?: string;
  website?: string;
  linkedin_url?: string;
  industry?: string;
  size?: string;
  country?: string;
  icp_id?: string | null;
};

export async function addCompany(client: string, body: CompanyManual): Promise<CompanyApi> {
  const r = await authFetch(`/${client}/companies`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// --- W4 async scoring jobs (kick-off + poll) ---------------------------------
// The scoring-bearing surfaces (find / lookalike / rescore ×2 / update-fields) run on a background
// worker, past the 30s gateway cap. Each kick-off returns a job; the caller polls /scoring-jobs/{id}
// until terminal, then reloads the affected list. Replaces the old client-driven chunk loops.
export type ScoringJobApi = {
  job_id: string | null;
  status: string; // idle | queued | running | done | error
  result: Record<string, unknown>;
  error: string | null;
};

// "Get AI score" / "Update Field" batch ceiling — must match the backend ASYNC_BATCH_MAX (one
// concurrent scoring wave, so the batch finishes well inside the Lambda timeout).
export const SCORE_BATCH_MAX = 15;

const JOB_POLL_MS = 2000;
const JOB_POLL_MAX = 200; // ~6.5-min ceiling; the Lambda-bounded worker terminates well before this
const JOB_POLL_RETRIES = 3; // consecutive transient poll errors tolerated before we give up (R12)

async function kickScoringJob(
  client: string,
  path: string,
  body: unknown
): Promise<ScoringJobApi> {
  const r = await authFetch(`/${client}/${path}`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

async function getScoringJob(client: string, jobId: string): Promise<ScoringJobApi> {
  const r = await authFetch(`/${client}/scoring-jobs/${jobId}`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Poll a kicked-off job until done/error (or `alive()` turns false, or the ceiling is hit), then
// return the latest job. Callers reload their list on a non-error terminal and surface job.error.
//
// R12: (a) `alive()` lets the caller cancel on unmount / client-switch so an orphan loop can't keep
// polling + toasting after navigating away. (b) A transient poll error (5xx / network blip) is
// retried up to JOB_POLL_RETRIES before we abandon, so one blip doesn't leave rows stuck "Pending".
// (c) If the ceiling is hit (or alive() flips) while the job is still non-terminal, we return it with
// status `running` — never a synthetic terminal — so the caller shows "still running", not a false
// "0 scored" success.
export async function awaitScoringJob(
  client: string,
  jobId: string,
  alive: () => boolean = () => true
): Promise<ScoringJobApi> {
  let lastJob: ScoringJobApi | null = null;
  let transient = 0;
  for (let i = 0; i < JOB_POLL_MAX && alive(); i++) {
    try {
      const job = await getScoringJob(client, jobId);
      transient = 0;
      lastJob = job;
      if (job.status === "done" || job.status === "error") return job;
    } catch (e) {
      if (++transient > JOB_POLL_RETRIES) throw e; // sustained failure → let the caller handle it
    }
    await new Promise((res) => setTimeout(res, JOB_POLL_MS));
  }
  // Ceiling hit / cancelled with no terminal state → report "running" (a fresh read if we can get
  // one, else the last-seen job, else a synthetic marker), so the FE never reads this as success.
  try {
    const job = await getScoringJob(client, jobId);
    return job.status === "done" || job.status === "error" ? job : { ...job, status: "running" };
  } catch {
    return lastJob
      ? { ...lastJob, status: "running" }
      : { job_id: jobId, status: "running", result: {}, error: null };
  }
}

// Flow A — Apollo company search from the latest ResearchSpec (async; rows land UNSCORED).
export function findCompaniesAsync(
  client: string,
  body: {
    limit?: number;
    icp_id?: string | null;
    // Operator override of the saved AI scope (Settings modal); omitted → spec is used as-is.
    company_search_params?: Record<string, unknown>;
    intent_filters?: Record<string, unknown>;
  } = {}
): Promise<ScoringJobApi> {
  return kickScoringJob(client, "companies/find-company-async", body);
}

// "Lookalike" — find the next batch of peers of the selected stage-1 rows (async; rows UNSCORED).
export function findLookalikesAsync(
  client: string,
  body: { company_ids: string[]; icp_id?: string | null }
): Promise<ScoringJobApi> {
  return kickScoringJob(client, "companies/find-lookalikes-async", body);
}

// Select/deselect stage-1 companies — the selected set scopes Flow B (find people).
export async function selectCompanies(
  client: string,
  ids: string[],
  selected = true
): Promise<CompanyApi[]> {
  const r = await authFetch(`/${client}/companies/select`, {
    method: "PATCH",
    json: true,
    body: JSON.stringify({ ids, selected }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Re-run fit scoring for an explicit set of already-sourced companies (async; the "Get AI score"
// button). Capped at SCORE_BATCH_MAX rows per job. Use after the rubric / scoring prompt changes.
export function rescoreCompaniesAsync(client: string, ids: string[]): Promise<ScoringJobApi> {
  return kickScoringJob(client, "companies/rescore-async", { ids });
}

// "Update Field" — re-enrich Apollo firmographics for the selected companies (async; the deliberate
// credit spend; Find Companies enriches only new rows). Capped at SCORE_BATCH_MAX rows per job.
export function updateCompanyFieldsAsync(client: string, ids: string[]): Promise<ScoringJobApi> {
  return kickScoringJob(client, "companies/update-fields-async", { ids });
}

// --- Phase C stage 2 — People (find → review → confirm-enrich) ---------------

export type ProspectManual = {
  full_name?: string;
  company?: string;
  domain?: string;
  linkedin_url?: string;
  email?: string;
  title?: string;
  seniority?: string;
  company_industry?: string;
  company_size?: string;
  icp_id?: string | null;
};

export async function addProspect(client: string, body: ProspectManual): Promise<ProspectApi> {
  const r = await authFetch(`/${client}/prospects`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Flow B — find people across an explicit set of Step-2 companies (one Apollo api_search per org),
// 0 credits. Rows land UNSCORED ("Pending"); score on demand via rescoreProspectsAsync.
export async function findPeople(
  client: string,
  body: {
    company_ids: string[]; // the Step-2 companies to search, by id
    per_company?: number;
    icp_id?: string | null;
    // Operator override of the saved AI scope (Step-2 Settings); omitted → spec is used as-is.
    people_search_params?: Record<string, unknown>;
    // FE-minted uuid threading the chunked calls of one merged stage→find into one history entry.
    group_id?: string;
  }
): Promise<FindResult> {
  const r = await authFetch(`/${client}/people/find-people`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Find-Settings facet sidebar — live per Management-Level / Department people counts across the
// selected Step-2 companies (free, 0 credits). One probe per facet value, server-side.
export type FacetOption = { value: string; label: string };
type FacetCount = FacetOption & { count: number };
type DepartmentFacet = FacetCount & { subs: FacetOption[] };
export type PeopleFacets = {
  total: number;
  seniorities: FacetCount[];
  departments: DepartmentFacet[];
};
export async function peopleFacets(
  client: string,
  companyIds: string[]
): Promise<PeopleFacets> {
  const r = await authFetch(`/${client}/people/facets`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ company_ids: companyIds }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Persisted Find Settings (scope override) — stored server-side per (tenant, kind, ICP) so a saved
// tuning follows the operator across browsers/devices, PER ICP (tuning one ICP never clobbers
// another's). `kind` picks the pipeline step; `icpId` scopes the save to one ICP (omit for an
// ICP-less/global entry). The persisted BLOCK is the step's Apollo shape — people:
// `{people_search_params}`; company: `{company_search_params, intent_filters}`. `null` → none saved
// (Workspace shows the AI scope).
export type ScopeKind = "people" | "company";
function scopeQuery(kind: ScopeKind, icpId?: string): string {
  const p = new URLSearchParams({ kind });
  if (icpId) p.set("icp_id", icpId);
  return p.toString();
}
export async function getScopeOverride(
  client: string,
  kind: ScopeKind,
  icpId?: string
): Promise<Record<string, unknown> | null> {
  const r = await authFetch(`/${client}/scope-override?${scopeQuery(kind, icpId)}`);
  if (!r.ok) throw new Error(await detail(r));
  const j = (await r.json()) as { params: Record<string, unknown> | null };
  return j.params;
}
// Returns the persisted block after the save: `null` when the server treated an empty payload as a
// revert (no facets chosen → fall back to the AI scope), else the saved block. Callers reflect this
// so the UI never disagrees with what the server stored.
export async function putScopeOverride(
  client: string,
  kind: ScopeKind,
  params: Record<string, unknown>,
  icpId?: string
): Promise<Record<string, unknown> | null> {
  const r = await authFetch(`/${client}/scope-override?${scopeQuery(kind, icpId)}`, {
    method: "PUT",
    json: true,
    body: JSON.stringify({ params }),
  });
  if (!r.ok) throw new Error(await detail(r));
  const j = (await r.json()) as { params: Record<string, unknown> | null };
  return j.params;
}
export async function deleteScopeOverride(
  client: string,
  kind: ScopeKind,
  icpId?: string
): Promise<void> {
  const r = await authFetch(`/${client}/scope-override?${scopeQuery(kind, icpId)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(await detail(r));
}
// Step-2 people-scope adapters (unwrap/wrap the block's `people_search_params`). `icpId` optional
// so a save scopes to one ICP; U3's Personas switcher passes it, the current global save omits it.
export async function getPeopleScopeOverride(
  client: string,
  icpId?: string
): Promise<Record<string, unknown> | null> {
  const block = await getScopeOverride(client, "people", icpId);
  return (block?.people_search_params as Record<string, unknown> | undefined) ?? null;
}
export async function putPeopleScopeOverride(
  client: string,
  peopleSearchParams: Record<string, unknown>,
  icpId?: string
): Promise<Record<string, unknown> | null> {
  const block = await putScopeOverride(
    client,
    "people",
    { people_search_params: peopleSearchParams },
    icpId
  );
  return (block?.people_search_params as Record<string, unknown> | undefined) ?? null;
}
export async function deletePeopleScopeOverride(client: string, icpId?: string): Promise<void> {
  await deleteScopeOverride(client, "people", icpId);
}
// The 14 master Department & Job Function options (value + label) — server-owned (Apollo's taxonomy),
// so the Find-Settings panel renders the master list before live counts load without hardcoding it.
export async function getPeopleDepartments(client: string): Promise<FacetOption[]> {
  const r = await authFetch(`/${client}/people/departments`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Step-2 'Get AI score' — re-run people fit scoring for an explicit set of prospects (async; by
// identity key) against the current rubric. Capped at SCORE_BATCH_MAX rows per job.
export function rescoreProspectsAsync(
  client: string,
  identityKeys: string[]
): Promise<ScoringJobApi> {
  return kickScoringJob(client, "prospects/rescore-async", { identity_keys: identityKeys });
}

// Step-2 'Reveal & score' — reveal verified emails for the selected people (Apollo people/match, the
// credit spend) THEN AI-score them on the revealed data, in ONE background job. Capped at
// SCORE_BATCH_MAX rows. Replaces the separate reveal + score clicks: scoring pre-reveal gates on
// missing contact (Apollo obfuscates seniority/dept/email until match), so reveal must come first.
// The job.result carries {requested, enriched, credits_spent, enrich_failed, scored, failed, cost_usd}.
export function enrichScoreProspectsAsync(
  client: string,
  identityKeys: string[]
): Promise<ScoringJobApi> {
  return kickScoringJob(client, "prospects/enrich-score-async", { identity_keys: identityKeys });
}
