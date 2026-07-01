// Live API client (A5 cutover). Base URL comes from NEXT_PUBLIC_API_BASE_URL; defaults to
// the local API for `pnpm dev`. Tokens are kept in localStorage for this phase.

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

const ACCESS_KEY = "holdslot_access";
const REFRESH_KEY = "holdslot_refresh";

type ApiClient = { slug: string; name: string; role: string };
export type Me = { id: string; email: string; full_name: string | null; clients: ApiClient[] };
export type LoginResult = {
  access_token: string;
  refresh_token: string;
  user: { id: string; email: string; full_name: string | null };
};

// Token changes are broadcast so the console's SessionGuard can re-arm its expiry timer
// (a silent refresh extends the session) or react to a session that's over.
function emit(event: "holdslot:tokens" | "holdslot:auth-expired") {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(event));
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
  emit("holdslot:tokens");
}
export function getAccess(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY);
}
function getRefresh(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY);
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  emit("holdslot:tokens");
}

/** Epoch-ms expiry of the current access token (from its JWT `exp`), or null if absent/unreadable. */
export function accessExpiresAt(): number | null {
  const t = getAccess();
  if (!t) return null;
  try {
    const payload = t.split(".")[1];
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof json.exp === "number" ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

// Three outcomes, deliberately distinct so a transient failure never logs the user out:
//   ok      — got a fresh pair; retry the request
//   expired — refresh token missing/rejected (401); the session is genuinely over → log out
//   error   — network blip / 5xx; tokens kept, surface the error and let the user retry
export type RefreshResult = "ok" | "expired" | "error";

// Single-flight: concurrent 401s (and the SessionGuard timer) share one in-flight call to
// /auth/refresh, so the single-use refresh token is rotated exactly once.
let refreshing: Promise<RefreshResult> | null = null;

/** Exchange the stored refresh token for a fresh pair. See RefreshResult for the outcomes. */
export function refreshAccess(): Promise<RefreshResult> {
  if (!refreshing) {
    refreshing = (async (): Promise<RefreshResult> => {
      if (!getRefresh()) return "expired";
      try {
        const r = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ refresh_token: getRefresh() }),
        });
        if (r.status === 401) {
          clearTokens(); // refresh token expired/revoked — the session is over
          return "expired";
        }
        if (!r.ok) return "error"; // 5xx etc — transient, keep tokens
        const pair = await r.json();
        setTokens(pair.access_token, pair.refresh_token);
        return "ok";
      } catch {
        return "error"; // network blip — keep tokens, let the caller surface it
      }
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

async function detail(r: Response): Promise<string> {
  return r
    .json()
    .then((b) => b?.detail ?? `request failed (${r.status})`)
    .catch(() => `request failed (${r.status})`);
}

// Cold-start aware login (W6). Aurora Serverless auto-pauses to 0-ACU in dev; the first login after
// an idle period can come back 503 (the backend's "database is waking up" signal) or fail at the
// network/gateway layer while the cluster resumes. We retry ONLY those cold-start signals — never a
// 401 (bad credentials must fail fast) — backing off up to ~45s, calling `onWaking` so the UI can
// show a "waking the database…" message. Resolves once the cluster is up (resume takes ~15-30s).
const LOGIN_COLD_START_CAP_MS = 45_000;

function isColdStartStatus(status: number): boolean {
  return status === 503 || status === 504 || status === 502;
}

export async function login(
  email: string,
  password: string,
  onWaking?: () => void
): Promise<LoginResult> {
  const deadline = Date.now() + LOGIN_COLD_START_CAP_MS;
  for (let attempt = 1; ; attempt++) {
    let r: Response;
    try {
      r = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
    } catch (e) {
      // Network error / gateway timeout — treat as a cold-start signal and retry within the cap.
      if (Date.now() < deadline) {
        onWaking?.();
        await coldStartBackoff(attempt, deadline);
        continue;
      }
      throw e instanceof Error ? e : new Error("login failed");
    }
    if (r.ok) return r.json();
    if (r.status === 401) throw new Error(await detail(r)); // real auth failure — never retry
    if (isColdStartStatus(r.status) && Date.now() < deadline) {
      onWaking?.();
      await coldStartBackoff(attempt, deadline);
      continue;
    }
    throw new Error(await detail(r));
  }
}

// Backoff between cold-start retries: grows 2s→6s, never sleeping past the overall deadline.
function coldStartBackoff(attempt: number, deadline: number): Promise<void> {
  const wait = Math.min(2000 + (attempt - 1) * 1500, 6000);
  return new Promise((res) => setTimeout(res, Math.max(0, Math.min(wait, deadline - Date.now()))));
}

export async function forgot(email: string): Promise<void> {
  // Best-effort; the endpoint always 202s so account existence isn't revealed.
  await fetch(`${API_BASE}/auth/forgot`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email }),
  }).catch(() => undefined);
}

export async function reset(token: string, newPassword: string): Promise<void> {
  const r = await fetch(`${API_BASE}/auth/reset`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  if (!r.ok) throw new Error(await detail(r));
}

export async function getMe(): Promise<Me> {
  const r = await authFetch(`/me`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// --- Phase B (S1) — Brief, ICP, ResearchSpec --------------------------------

// Every authenticated request goes through here. On a 401 it makes ONE silent refresh attempt
// and replays the request with the new token — so an active user whose 8h access token lapsed
// mid-session never sees an "invalid token" error. Headers are rebuilt per attempt so the replay
// carries the refreshed token. A failed refresh emits `holdslot:auth-expired`, which the
// SessionGuard turns into a redirect to /login.
async function authFetch(
  path: string,
  opts: { method?: string; json?: boolean; body?: string } = {}
): Promise<Response> {
  const send = () => {
    const h: Record<string, string> = {};
    const token = getAccess();
    if (token) h["authorization"] = `Bearer ${token}`;
    if (opts.json) h["content-type"] = "application/json";
    return fetch(`${API_BASE}${path}`, { method: opts.method, headers: h, body: opts.body });
  };
  let r = await send();
  if (r.status === 401) {
    const res = getRefresh() ? await refreshAccess() : "expired";
    if (res === "ok") r = await send();
    else if (res === "expired") emit("holdslot:auth-expired");
    // "error": leave the 401 to surface as a normal failure — tokens kept, no forced logout.
  }
  return r;
}

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
  gaps: { field: string; why_it_matters: string; ask: string }[];
  icp_suggestions: IcpSuggestion[];
  model: string | null;
  llm_call_id: string | null;
  created_at: string | null;
};
export type ResearchSpecList = { latest: ResearchSpecResult | null; versions: number[] };

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

export async function structureBrief(client: string): Promise<ResearchJob> {
  const r = await authFetch(`/${client}/brief/structure`, { method: "POST", json: true });
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

export async function getScopingPrompt(client: string): Promise<ScopingPrompt> {
  const r = await authFetch(`/${client}/brief/structure/preview`);
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

// --- Phase C (S2) — Prospects: Apollo find + enrich --------------------------

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
  fit_score: number | null;
  fit_tier: string | null;
  fit_reason: string;
  reason_tags: string[];
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
  fit_score: number | null;
  fit_tier: string | null;
  fit_reason: string;
  business_model: string; // "B2B" | "B2C" | "Complex" | "Unknown" | "" (unscored / pre-label)
  market_excluded: boolean; // B2B/B2C gate fired (opposite-market) → pinned to the bottom of Step 1
  reason_tags: string[];
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
export type EnrichResult = {
  confirmed: number;
  enriched: number;
  credits_spent: number;
  failed: number; // rows whose Apollo match errored / had no match (spend counts are still returned)
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

// --- List feeds — cursor-paged (W5) ------------------------------------------
// The server caps each response (≤ LIST_CEILING). The client auto-loads every page on mount with
// no "load more" action, up to LIST_CEILING total. Past that we stop and flag `truncated` so the UI
// can say "showing first N". FEED_PAGE divides LIST_CEILING so we fetch exactly the ceiling, never
// overfetch a partial extra page.
export const LIST_CEILING = 250;
const FEED_PAGE = 100;

type CursorPage<T> = { items: T[]; next_cursor: string | null };
export type Feed<T> = { items: T[]; truncated: boolean };

async function pageThrough<T>(path: string): Promise<Feed<T>> {
  const items: T[] = [];
  let cursor: string | null = null;
  do {
    const limit = Math.min(FEED_PAGE, LIST_CEILING - items.length);
    const qs = new URLSearchParams({ limit: String(limit) });
    if (cursor) qs.set("cursor", cursor);
    const r = await authFetch(`${path}?${qs.toString()}`);
    if (!r.ok) throw new Error(await detail(r));
    const page = (await r.json()) as CursorPage<T>;
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor && items.length < LIST_CEILING);
  // cursor still set ⇒ the server has more rows than we loaded (we stopped at the ceiling).
  return { items, truncated: cursor != null };
}

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
  kind: string | null;
  status: string; // idle | queued | running | done | error
  result: Record<string, unknown>;
  error: string | null;
};

// "Get AI score" / "Update Field" batch ceiling — must match the backend ASYNC_BATCH_MAX (one
// concurrent scoring wave, so the batch finishes well inside the Lambda timeout).
export const SCORE_BATCH_MAX = 15;

const JOB_POLL_MS = 2000;
const JOB_POLL_MAX = 200; // ~6.5-min ceiling; the Lambda-bounded worker terminates well before this

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
export async function awaitScoringJob(
  client: string,
  jobId: string,
  alive: () => boolean = () => true
): Promise<ScoringJobApi> {
  for (let i = 0; i < JOB_POLL_MAX && alive(); i++) {
    const job = await getScoringJob(client, jobId);
    if (job.status === "done" || job.status === "error") return job;
    await new Promise((res) => setTimeout(res, JOB_POLL_MS));
  }
  return getScoringJob(client, jobId);
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

// Persisted Step-2 Find Settings (people scope) — stored server-side per tenant so a saved tuning
// follows the operator across browsers/devices. `null` → none saved (Workspace shows the AI scope).
export async function getPeopleScopeOverride(
  client: string
): Promise<Record<string, unknown> | null> {
  const r = await authFetch(`/${client}/people/scope-override`);
  if (!r.ok) throw new Error(await detail(r));
  const j = (await r.json()) as { people_search_params: Record<string, unknown> | null };
  return j.people_search_params;
}
// Returns the persisted scope after the save: `null` when the server treated an empty payload as a
// revert (no facets chosen → fall back to the AI scope), else the saved params. Callers reflect
// this so the UI never disagrees with what the server stored.
export async function putPeopleScopeOverride(
  client: string,
  peopleSearchParams: Record<string, unknown>
): Promise<Record<string, unknown> | null> {
  const r = await authFetch(`/${client}/people/scope-override`, {
    method: "PUT",
    json: true,
    body: JSON.stringify({ people_search_params: peopleSearchParams }),
  });
  if (!r.ok) throw new Error(await detail(r));
  const j = (await r.json()) as { people_search_params: Record<string, unknown> | null };
  return j.people_search_params;
}
export async function deletePeopleScopeOverride(client: string): Promise<void> {
  const r = await authFetch(`/${client}/people/scope-override`, { method: "DELETE" });
  if (!r.ok) throw new Error(await detail(r));
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

// The enrich gate — Apollo people/match on the confirmed rows (the only credit spend); returns the
// confirmed/enriched counts + credits spent.
export async function enrichProspects(
  client: string,
  identityKeys: string[]
): Promise<EnrichResult> {
  const r = await authFetch(`/${client}/prospects/enrich`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ identity_keys: identityKeys }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// --- Phase D (S3) — Sendout batch + client approval --------------------------
// Counts (total/approved/removed/pending) are DERIVED server-side from prospect_approval, never
// stored. `status` walks draft → sent → approved | changes_requested.
export type BatchApi = {
  id: string;
  name: string;
  icp: string;
  status: string;
  total: number;
  approved: number;
  removed: number;
  pending: number;
  created_at: string | null;
  sent_at: string | null;
  decided_at: string | null;
};
// One prospect inside the console (FULL, operator-owned) batch detail — NOT masked. Composed into
// BatchDetailApi (the exported parent); not imported standalone.
type BatchProspectApi = {
  approval_id: string;
  prospect_id: string;
  full_name: string;
  title: string;
  seniority: string;
  fit_tier: string | null;
  fit_reason: string;
  decision: string; // pending | approved | removed
};
type BatchCompanyGroupApi = {
  company: string;
  domain: string;
  industry: string;
  size: string;
  country: string;
  fit_tier: string | null;
  fit_reason: string;
  prospects: BatchProspectApi[];
};
export type BatchDetailApi = BatchApi & { companies: BatchCompanyGroupApi[] };
export type ApprovalTemplateApi = { subject: string; body: string; cta: string };

export async function listBatches(client: string): Promise<BatchApi[]> {
  const r = await authFetch(`/${client}/batches`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function createBatch(
  client: string,
  body: { prospect_ids: string[]; name?: string; icp_id?: string | null }
): Promise<BatchApi> {
  const r = await authFetch(`/${client}/batches`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function getBatch(client: string, id: string): Promise<BatchDetailApi> {
  const r = await authFetch(`/${client}/batches/${id}`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function sendApproval(
  client: string,
  id: string,
  email: string
): Promise<BatchApi> {
  const r = await authFetch(`/${client}/batches/${id}/send`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ email }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
// Step-3 human fallback — the operator records the client decision by hand.
export async function decideBatch(
  client: string,
  id: string,
  body: { approved_ids?: string[]; removed_ids?: string[]; request_changes?: boolean }
): Promise<BatchApi> {
  const r = await authFetch(`/${client}/batches/${id}/decide`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
// Hard-delete a batch; the server cascades its prospect_approval + approval_link rows. 204, no body.
export async function deleteBatch(client: string, id: string): Promise<void> {
  const r = await authFetch(`/${client}/batches/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error(await detail(r));
}
export async function getApprovalTemplate(client: string): Promise<ApprovalTemplateApi> {
  const r = await authFetch(`/${client}/approval-template`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function saveApprovalTemplate(
  client: string,
  body: ApprovalTemplateApi
): Promise<ApprovalTemplateApi> {
  const r = await authFetch(`/${client}/approval-template`, {
    method: "PUT",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// --- Phase D external (public, token-only — NO auth) -------------------------
// The MASKED client view: fit context only, never a clear-text identity/contact vector. Composed
// into ApprovalViewApi (the exported parent); not imported standalone.
type ApprovalProspectApi = {
  id: string; // the opaque decide handle (prospect_approval id)
  name: string; // "Sarah K."
  company_descriptor: string; // "SaaS · 200–500 · US" (not the exact company)
  title: string;
  seniority: string;
  fit_tier: string | null;
  fit_reason: string;
  decision: string;
};
export type ApprovalViewApi = {
  state: "valid" | "expired" | "used";
  batch_name: string;
  client_name: string;
  count: number;
  expires_at: string | null;
  prospects: ApprovalProspectApi[];
};
export type ApprovalDecisionApi = { status: string; approved: number; removed: number };

export async function getApproval(token: string): Promise<ApprovalViewApi> {
  // No auth — the token is the credential. The endpoint always 200s with a `state` so the page
  // can pick its pane; it never reveals tenant existence.
  const r = await fetch(`${API_BASE}/approve/${encodeURIComponent(token)}`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function decideApproval(
  token: string,
  body: { removed_ids?: string[]; approved_ids?: string[]; request_changes?: boolean }
): Promise<ApprovalDecisionApi> {
  const r = await fetch(`${API_BASE}/approve/${encodeURIComponent(token)}/decide`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r)); // 410 once expired/used/decided
  return r.json();
}
