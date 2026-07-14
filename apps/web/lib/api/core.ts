// Live API client (A5 cutover). Base URL comes from NEXT_PUBLIC_API_BASE_URL; the localhost fallback
// is a `pnpm dev` convenience ONLY — deployed builds must set it, and amplify.yml's preBuild fails
// the build if it is unset (N53) so a misconfigured deploy can't silently ship this default. Tokens
// are kept in localStorage for this phase.
//
// This is the shared core of the `lib/api/` package: the base URL, token lifecycle, refresh,
// `ApiError`, the authenticated `authFetch` workhorse, and the cursor-paging helper. Domain modules
// (briefs/prospects/batches/campaigns/meetings/external/billing) import from here; `lib/api.ts` is a
// barrel that re-exports every module so all callers keep importing from `@/lib/api` unchanged.

export const API_BASE =
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

export async function detail(r: Response): Promise<string> {
  return r
    .json()
    .then((b) => b?.detail ?? `request failed (${r.status})`)
    .catch(() => `request failed (${r.status})`);
}

/**
 * An HTTP error that carries the response `status`, so a caller can distinguish a definitive
 * server "no" (401 auth · 409 conflict · 410 gone) from a transient one (502/503/504 cold-start,
 * network) and react differently — the M1/M4/M5 fixes. Extends `Error`, so every existing
 * `catch (e) { e.message }` / `e instanceof Error` path keeps working unchanged.
 */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Throw an ApiError carrying the response status + server detail. */
export async function fail(r: Response): Promise<never> {
  throw new ApiError(r.status, await detail(r));
}

/** Public-token pages are never-404: a genuinely dead link comes back as a 200 `state`, so the ONE
 *  error that means "this link is now gone" on submit is a 410. Everything else (409 slot-taken,
 *  503 cold-start, network) is transient — keep the page and offer a retry (M1/M5). */
export function isLinkGoneError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 410;
}

/** A booking slot-taken race on the POST (recoverable — refresh the times, keep the picker; M1). */
export function isSlotTakenError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409;
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
    if (r.status === 401) throw new ApiError(401, await detail(r)); // bad credentials — never retry
    if (isColdStartStatus(r.status) && Date.now() < deadline) {
      onWaking?.();
      await coldStartBackoff(attempt, deadline);
      continue;
    }
    // Any other status (400/429/5xx past the cold-start cap) carries its status so the login page
    // can tell "server error, try again" from "bad credentials" (M25).
    throw new ApiError(r.status, await detail(r));
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

// L14 — cold-start aware + status-carrying, mirroring login(). The old version threw a bare Error on
// any non-2xx, so the page showed "invalid or expired" even on a 503/network blip (routine on
// auto-pausing dev Aurora). Retry the cold-start signals within the cap; otherwise throw an ApiError
// so the page can tell a genuinely dead link (400/410) from a transient backend hiccup.
export async function reset(
  token: string,
  newPassword: string,
  onWaking?: () => void
): Promise<void> {
  const deadline = Date.now() + LOGIN_COLD_START_CAP_MS;
  for (let attempt = 1; ; attempt++) {
    let r: Response;
    try {
      r = await fetch(`${API_BASE}/auth/reset`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
    } catch (e) {
      if (Date.now() < deadline) {
        onWaking?.();
        await coldStartBackoff(attempt, deadline);
        continue;
      }
      throw e instanceof Error ? e : new Error("reset failed");
    }
    if (r.ok) return;
    if (isColdStartStatus(r.status) && Date.now() < deadline) {
      onWaking?.();
      await coldStartBackoff(attempt, deadline);
      continue;
    }
    throw new ApiError(r.status, await detail(r));
  }
}

export async function getMe(): Promise<Me> {
  const r = await authFetch(`/me`);
  if (!r.ok) return fail(r); // ApiError carries the status — MeProvider clears tokens only on 401
  return r.json();
}

// N45 — create a real tenant (POST /clients also enrolls the caller as owner) and return it, incl.
// the server-assigned slug (which may be suffixed on a name collision). The caller refetches /me.
export async function createClient(name: string): Promise<ApiClient> {
  const r = await authFetch(`/clients`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ name }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Every authenticated request goes through here. On a 401 it makes ONE silent refresh attempt
// and replays the request with the new token — so an active user whose 8h access token lapsed
// mid-session never sees an "invalid token" error. Headers are rebuilt per attempt so the replay
// carries the refreshed token. A failed refresh emits `holdslot:auth-expired`, which the
// SessionGuard turns into a redirect to /login.
export async function authFetch(
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

// --- List feeds — cursor-paged (W5) ------------------------------------------
// The server caps each response (≤ FEED_PAGE). The client auto-loads EVERY page on mount, with no
// "load more" action and no ceiling — it follows the cursor until the server runs out of rows, so
// the whole list is always in hand. FEED_PAGE is the server's per-request max (fewest round-trips).
const FEED_PAGE = 250;

type CursorPage<T> = { items: T[]; next_cursor: string | null };
export type Feed<T> = { items: T[] };

export async function pageThrough<T>(path: string): Promise<Feed<T>> {
  const items: T[] = [];
  let cursor: string | null = null;
  do {
    const qs = new URLSearchParams({ limit: String(FEED_PAGE) });
    if (cursor) qs.set("cursor", cursor);
    const r = await authFetch(`${path}?${qs.toString()}`);
    if (!r.ok) throw new Error(await detail(r));
    const page = (await r.json()) as CursorPage<T>;
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor); // follow the cursor to the end — load the whole list, no ceiling
  return { items };
}
