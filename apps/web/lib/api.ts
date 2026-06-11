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

export async function getMe(): Promise<Me> {
  const r = await fetch(`${API_BASE}/me`, {
    headers: { authorization: `Bearer ${getAccess()}` },
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
