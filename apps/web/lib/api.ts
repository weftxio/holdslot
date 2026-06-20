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

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}
export function getAccess(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY);
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
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
  const r = await fetch(`${API_BASE}/me`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// --- Phase B (S1) — Brief, ICP, ResearchSpec --------------------------------

function authHeaders(json = false): Record<string, string> {
  const h: Record<string, string> = {};
  const token = getAccess();
  if (token) h["authorization"] = `Bearer ${token}`;
  if (json) h["content-type"] = "application/json";
  return h;
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
export type IcpSuggestion = {
  name: string;
  rationale: string;
  resembles_stated_icp: boolean;
  evidence_companies: string[];
  suggested_industries: string[];
  suggested_titles: string[];
  confidence: "low" | "medium" | "high";
};
export type ResearchSpecResult = {
  version: number;
  spec: Record<string, unknown>;
  gaps: { field: string; why: string; ask: string }[];
  icp_suggestions: IcpSuggestion[];
  model: string | null;
  llm_call_id: string | null;
  created_at: string | null;
};
export type ResearchSpecList = { latest: ResearchSpecResult | null; versions: number[] };

export async function getBrief(client: string): Promise<BriefResult> {
  const r = await fetch(`${API_BASE}/${client}/brief`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function putBrief(client: string, data: BriefDoc): Promise<BriefResult> {
  const r = await fetch(`${API_BASE}/${client}/brief`, {
    method: "PUT",
    headers: authHeaders(true),
    body: JSON.stringify({ data }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function listIcps(client: string): Promise<IcpApi[]> {
  const r = await fetch(`${API_BASE}/${client}/icps`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

type IcpBody = { name: string; tag: string; data: Record<string, unknown> };

export async function createIcp(client: string, body: IcpBody): Promise<IcpApi> {
  const r = await fetch(`${API_BASE}/${client}/icps`, {
    method: "POST",
    headers: authHeaders(true),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function updateIcp(client: string, id: string, body: IcpBody): Promise<IcpApi> {
  const r = await fetch(`${API_BASE}/${client}/icps/${id}`, {
    method: "PUT",
    headers: authHeaders(true),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function deleteIcp(client: string, id: string): Promise<void> {
  const r = await fetch(`${API_BASE}/${client}/icps/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!r.ok && r.status !== 404) throw new Error(await detail(r));
}

export async function structureBrief(client: string): Promise<ResearchSpecResult> {
  const r = await fetch(`${API_BASE}/${client}/brief/structure`, {
    method: "POST",
    headers: authHeaders(true),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function getResearchSpec(client: string): Promise<ResearchSpecList> {
  const r = await fetch(`${API_BASE}/${client}/research-spec`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// --- Phase C (S2) — Prospects: Clay seed + AI sourcing loop ------------------

export type ProspectApi = {
  id: string;
  identity_key: string;
  icp_id: string | null;
  run_id: string | null;
  full_name: string;
  company: string;
  domain: string;
  email: string;
  email_valid: boolean;
  title: string;
  company_industry: string;
  company_size: string;
  fit_score: number | null;
  fit_tier: string | null;
  fit_reason: string;
  reason_tags: string[];
  source: string; // "clay" | "ai_loop"
  status: string;
  created_at: string | null;
};
export type ImportResult = {
  run_id: string | null;
  parsed: number;
  stored: number;
  suppressed: number;
  scored: number;
  score_errors: number;
  by_tier: Record<string, number>;
};
export type ResearchRunApi = {
  run_id: string;
  source: string;
  prompt_version: string | null;
  rubric_version: string | null;
  rows_pushed: number;
  rows_accepted: number;
  cost_usd: number | null;
  cost_per_accepted: number | null;
  created_at: string | null;
};
export type SourcingDocApi = {
  kind: string;
  version: number;
  body: string;
  created_at: string | null;
};
export type SourcingDocList = {
  sourcing_prompt: SourcingDocApi | null;
  fit_rubric: SourcingDocApi | null;
  prompt_versions: number[];
  rubric_versions: number[];
};
export type SourcingCandidate = {
  identity_key: string;
  full_name: string;
  company: string;
  domain: string;
  preliminary_tier: string;
  evidence: Record<string, unknown>;
};
export type SourcingRoundResult = {
  run_id: string;
  returned: number;
  validated: number;
  suppressed: number;
  pending_review: number;
  candidates: SourcingCandidate[];
};

export async function listProspects(client: string): Promise<ProspectApi[]> {
  const r = await fetch(`${API_BASE}/${client}/prospects`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Send the raw CSV text base64-wrapped (the $default proxy path); the API coalesces, suppresses,
// stores, and fit-scores it synchronously.
export async function importProspectsCsv(client: string, csvText: string): Promise<ImportResult> {
  const b64 = btoa(unescape(encodeURIComponent(csvText)));
  const r = await fetch(`${API_BASE}/${client}/prospects/import`, {
    method: "POST",
    headers: authHeaders(true),
    body: JSON.stringify({ csv: b64 }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function getSourcingDocs(client: string): Promise<SourcingDocList> {
  const r = await fetch(`${API_BASE}/${client}/sourcing-docs`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function saveSourcingDoc(
  client: string,
  kind: "sourcing_prompt" | "fit_rubric",
  body: string
): Promise<SourcingDocApi> {
  const r = await fetch(`${API_BASE}/${client}/sourcing-docs`, {
    method: "POST",
    headers: authHeaders(true),
    body: JSON.stringify({ kind, body }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function runSourcingRound(
  client: string,
  icpId: string | null,
  seedLimit: number
): Promise<SourcingRoundResult> {
  const r = await fetch(`${API_BASE}/${client}/sourcing-rounds`, {
    method: "POST",
    headers: authHeaders(true),
    body: JSON.stringify({ icp_id: icpId, seed_limit: seedLimit }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function listResearchRuns(client: string): Promise<ResearchRunApi[]> {
  const r = await fetch(`${API_BASE}/${client}/research-runs`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export async function acceptCandidates(
  client: string,
  identityKeys: string[]
): Promise<{ run_id: string; pushed: number; suppressed: number }> {
  const r = await fetch(`${API_BASE}/${client}/prospects/accept`, {
    method: "POST",
    headers: authHeaders(true),
    body: JSON.stringify({ identity_keys: identityKeys }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
