// Live API client (A5 cutover). Base URL comes from NEXT_PUBLIC_API_BASE_URL; defaults to
// the local API for `pnpm dev`. Tokens are kept in localStorage for this phase.

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

const ACCESS_KEY = "holdslot_access";
const REFRESH_KEY = "holdslot_refresh";

export type ApiClient = { slug: string; name: string; role: string };
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

export async function login(email: string, password: string): Promise<LoginResult> {
  const r = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
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
export type ApolloCompanyParams = {
  q_organization_keyword_tags: string[];
  organization_num_employees_ranges: string[];
  organization_locations: string[];
  revenue_range: { min: number | null; max: number | null };
};
// Apollo people-search params (a subset of mixed_people/api_search).
export type ApolloPeopleParams = {
  person_titles: string[];
  include_similar_titles: boolean;
  q_keywords: string;
  person_seniorities: string[];
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
  reason_tags: string[];
  source: string; // "apollo" | "manual"
  status: string; // "discovered" | "people_found" | ...
  created_at: string | null;
};
export type EnrichResult = {
  confirmed: number;
  enriched: number;
  credits_spent: number;
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
  fit_scoring: SourcingDocApi | null;
  rubric_versions: number[];
};

export async function listProspects(client: string): Promise<ProspectApi[]> {
  const r = await authFetch(`/${client}/prospects`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function getSourcingDocs(client: string): Promise<SourcingDocList> {
  const r = await authFetch(`/${client}/sourcing-docs`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function saveSourcingDoc(
  client: string,
  stage: "fit_scoring",
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

export async function listCompanies(client: string): Promise<CompanyApi[]> {
  const r = await authFetch(`/${client}/companies`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
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

// Flow A — Apollo company search from the latest ResearchSpec → suppress → upsert → score.
export async function findCompanies(
  client: string,
  body: { limit?: number; icp_id?: string | null } = {}
): Promise<FindResult> {
  const r = await authFetch(`/${client}/companies/find-company`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
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

// Flow B — find people across the SELECTED companies (one Apollo api_search per org), 0 credits.
export async function findPeople(
  client: string,
  body: { per_company?: number; icp_id?: string | null } = {}
): Promise<FindResult> {
  const r = await authFetch(`/${client}/people/find-people`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
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
