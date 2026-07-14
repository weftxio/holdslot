// --- Phase B (S1) — Brief, ICP, ResearchSpec --------------------------------

import { authFetch, detail } from "./core";

export type BriefDoc = Record<string, unknown>;
export type BriefResult = {
  data: BriefDoc;
  completeness: number;
  missing: string[];
  updated_at: string | null;
};
export type IcpApi = {
  id: string;
  name: string;
  tag: string;
  data: Record<string, unknown>;
  updated_at: string | null;
};
// Apollo company-search params (a subset of mixed_companies/search), emitted verbatim by the LLM.
type ApolloCompanyParams = {
  q_organization_keyword_tags: string[];
  organization_num_employees_ranges: string[];
  organization_locations: string[];
  revenue_range: { min: number | null; max: number | null };
};
// Apollo people-search params (a subset of mixed_people/api_search). Personas are Apollo's two
// native facets — Management Level (person_seniorities) × Department/Job Function — never free-text
// titles (exact-title matching AND's to zero against orgs with different title wording).
type ApolloPeopleParams = {
  person_seniorities: string[];
  person_department_or_subdepartments: string[];
  q_keywords: string;
  organization_locations: string[];
  organization_num_employees_ranges: string[];
};
export type IcpSuggestion = {
  name: string;
  rationale: string;
  evidencing_customers: string[];
  confidence: "low" | "medium" | "high";
  company_search_params: ApolloCompanyParams;
  people_search_params: ApolloPeopleParams;
};
export type ResearchSpecResult = {
  version: number;
  spec: Record<string, unknown>;
  // `icp_name` (spec v4) names the ICP a gap concerns; "" or absent (v3 specs) = whole-brief gap.
  gaps: { field: string; why_it_matters: string; ask: string; icp_name?: string }[];
  icp_suggestions: IcpSuggestion[];
  model: string | null;
  llm_call_id: string | null;
  created_at: string | null;
};
export type ResearchSpecList = { latest: ResearchSpecResult | null };

// One find run's scope lineage (D+ Stage 1) — the Find-history drawer's row shape. `filter_body` is
// the EXACTLY-executed Apollo body (override-proof, post-relax); `result_meta` carries the search
// signal: `total_entries` (full match count), `breadcrumbs` (Apollo's echo of each filter), the
// relax trail (`relax_level`/`relax_steps`), and the `over_broad` flag. All null for pre-0019 runs.
export type ResearchRunApi = {
  run_id: string;
  source: string; // apollo · lookalike · rescore · enrich
  prompt_version: string | null;
  rows_pushed: number;
  cost_usd: number | null;
  icp_id: string | null;
  scope_source: string | null; // ai · custom · lookalike · null (non-Apollo run)
  filter_body: Record<string, unknown> | null;
  result_meta: {
    total_entries?: number | null;
    breadcrumbs?: { label?: string; signal_field_name?: string; value?: string; display_name?: string }[];
    pages_fetched?: number | null;
    relax_level?: number | null;
    relax_steps?: string[];
    over_broad?: boolean;
    apac?: boolean; // Stage 2 — APAC scope, revenue_range dropped up front
    // Stage 3 page cursor: this run fetched pages resume_page..page_cursor; scope_exhausted once the
    // cursor reaches total_pages; known_skipped = rows already stored, skipped ($0 invariant).
    resume_page?: number | null;
    page_cursor?: number | null;
    total_pages?: number | null;
    scope_exhausted?: boolean;
    known_skipped?: number;
    body_hash?: string;
    cache_hit?: boolean;
    // U2 people-find lineage (source apollo, filter_body = {per_org}): the merged stage→find threads
    // its chunked calls under `group_id`; the counts summarize the run.
    group_id?: string | null;
    orgs_searched?: number | null;
    people_found?: number | null;
    dropped?: number | null;
  } | null;
  created_at: string | null;
};

// The find-run ledger, newest first — the Find-history drawer reads this to answer "what did this
// search actually ask, and how broad was it?" (source · ICP · spec vN · ai/custom · rows · matches).
export async function listResearchRuns(client: string): Promise<ResearchRunApi[]> {
  const r = await authFetch(`/${client}/research-runs`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function getBrief(client: string): Promise<BriefResult> {
  const r = await authFetch(`/${client}/brief`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function putBrief(client: string, data: BriefDoc): Promise<BriefResult> {
  const r = await authFetch(`/${client}/brief`, {
    method: "PUT",
    json: true,
    body: JSON.stringify({ data }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function listIcps(client: string): Promise<IcpApi[]> {
  const r = await authFetch(`/${client}/icps`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

type IcpBody = { name: string; tag: string; data: Record<string, unknown> };

export async function createIcp(client: string, body: IcpBody): Promise<IcpApi> {
  const r = await authFetch(`/${client}/icps`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function updateIcp(client: string, id: string, body: IcpBody): Promise<IcpApi> {
  const r = await authFetch(`/${client}/icps/${id}`, {
    method: "PUT",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function deleteIcp(client: string, id: string): Promise<void> {
  const r = await authFetch(`/${client}/icps/${id}`, { method: "DELETE" });
  if (!r.ok && r.status !== 404) throw new Error(await detail(r));
}

// Structuring is ASYNC: scoping runs DeepSeek V4 Pro (thinking + web search, ~1 min) on a
// background worker, off the 30s API Gateway cap. `structureBrief` kicks it off (202) and returns
// the job; the UI polls `getStructureStatus` until `done`/`error`, then reloads the spec.
export type ResearchJob = {
  job_id: string | null;
  status: "idle" | "queued" | "running" | "done" | "error";
  spec_version: number | null;
  error: string | null;
};

// `icpIds` restricts the run to those ICP profiles (a selective re-scope) — the worker regenerates
// only their targeting and splices it into the latest spec. Omit / empty → scope every ICP.
export async function structureBrief(client: string, icpIds?: string[]): Promise<ResearchJob> {
  const r = await authFetch(`/${client}/brief/structure`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ icp_ids: icpIds && icpIds.length ? icpIds : null }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function getStructureStatus(client: string): Promise<ResearchJob> {
  const r = await authFetch(`/${client}/brief/structure/status`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function getResearchSpec(client: string): Promise<ResearchSpecList> {
  const r = await authFetch(`/${client}/research-spec`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// The exact LLM prompt `structureBrief` would send — for the prompt-preview popup. No LLM spend.
// `system` is the effective prompt (operator override if saved, else default); `user` is always
// read-only (the client brief + ICPs).
export type ScopingPrompt = {
  system: string;
  user: string;
  system_is_custom: boolean;
  model: string[];
  purpose: string;
  prompt_version: string;
};

// `icpId` narrows the input prompt's ICP set to one profile (the scope panel's ICP filter) —
// a review lens only; the live Generate always sends every ICP.
export async function getScopingPrompt(client: string, icpId?: string): Promise<ScopingPrompt> {
  const url = `/${client}/brief/structure/preview${
    icpId ? `?icp_id=${encodeURIComponent(icpId)}` : ""
  }`;
  const r = await authFetch(url);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// The two fit-scoring rubrics, one per stage: company buying-intent (Step 1) vs people
// reply-potential / decision-power (Step 2). The names match the backend prompt stages + LLM
// purposes 1:1.
export type FitStage = "company_fit" | "prospect_fit";

// The exact system + input prompt a fit-score call would send (preview, no LLM spend). The `user`
// message carries the REAL targeting context (this client's brief + research spec + the sample row's
// ICP docs) so the Fit-rubric modal mirrors what reaches the model. `sampleId` picks the sample row
// (a company id for `company_fit`, a prospect id for `prospect_fit`); omitted → the most recent.
export type FitPrompt = {
  system: string;
  user: string;
  company: string | null; // the sample row's label (company name, or person name for prospect_fit)
  model: string[];
  purpose: string;
  prompt_version: string;
};

export async function getFitPrompt(
  client: string,
  stage: FitStage,
  sampleId?: string
): Promise<FitPrompt> {
  const qs = new URLSearchParams({ stage });
  if (sampleId) qs.set("sample_id", sampleId);
  const r = await authFetch(`/${client}/fit-prompt?${qs.toString()}`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Save an operator-edited scoping system prompt for this client (versioned, used by the next
// Generate Scope). Saving the default text verbatim resets to default (is_custom=false).
export type SavedSystemPrompt = { system: string; version: number; is_custom: boolean };

export async function saveScopingSystemPrompt(
  client: string,
  system: string
): Promise<SavedSystemPrompt> {
  const r = await authFetch(`/${client}/brief/structure/system-prompt`, {
    method: "PUT",
    json: true,
    body: JSON.stringify({ system }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
