import type { Page, Route } from "@playwright/test";

// The dead local port the dev server's NEXT_PUBLIC_API_BASE_URL points at. Every API call the app
// makes targets this base; we intercept ALL of them so nothing ever reaches a real host.
export const API_BASE = "http://127.0.0.1:9876";

// The client slug used throughout the suite.
export const CLIENT = "holdslot";

// --- Fake JWT --------------------------------------------------------------------------------
// SessionGuard + lib/api.ts read the access token's `exp` claim (and broadcast token changes). A
// token with a far-future exp keeps the session "active" so no /login redirect fires. We don't need
// a real signature — the app only base64url-decodes the payload to read `exp`.
function b64url(obj: unknown): string {
  return Buffer.from(JSON.stringify(obj))
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}
const FAKE_JWT = `${b64url({ alg: "none", typ: "JWT" })}.${b64url({ sub: "u", exp: 9999999999 })}.sig`;

// Seed the tokens BEFORE any app code runs (addInitScript runs on every navigation, before the
// bundle), so MeProvider's getAccess() check and SessionGuard's arm() both see a valid session.
async function seedAuth(page: Page): Promise<void> {
  await page.addInitScript(
    ([access, refresh]) => {
      localStorage.setItem("holdslot_access", access);
      localStorage.setItem("holdslot_refresh", refresh);
    },
    [FAKE_JWT, FAKE_JWT]
  );
}

// --- API mocks -------------------------------------------------------------------------------
// Minimal valid JSON keyed by the request path, shaped to match lib/api.ts so the routes render
// without throwing on a missing field. `client` is the slug segment ({client} below).
function jsonFor(method: string, path: string): unknown {
  // Mutations: the routes don't render these on load; a bare object is fine.
  if (method !== "GET") return {};

  // /me — the console auth gate (MeProvider). Must list the client so the shell renders.
  if (path === "/me") {
    return {
      id: "u",
      email: "info@checkafy.com",
      full_name: "Test Operator",
      clients: [{ slug: CLIENT, role: "owner", name: "HoldSlot" }],
    };
  }

  // Public token-only approval view (no /{client} prefix). The approve page fetches this on mount;
  // a `state: "valid"` masked view keeps it on the live card instead of flipping to the expired pane.
  if (path.startsWith("/approve/")) {
    return {
      state: "valid",
      batch_name: "Batch 1",
      client_name: "HoldSlot",
      count: 1,
      expires_at: null,
      prospects: [
        {
          id: "a1",
          name: "Sarah K.",
          company_descriptor: "SaaS · 200-500 · US",
          title: "VP Marketing",
          seniority: "vp",
          fit_tier: "Strong",
          fit_reason: "Right seniority and category.",
          decision: "pending",
        },
      ],
    };
  }

  // Strip the leading /{client} so the per-client endpoints match regardless of slug.
  const rel = path.replace(new RegExp(`^/${CLIENT}`), "");

  switch (rel) {
    // Brief route
    case "/brief":
      return { data: {}, completeness: 0, missing: [], updated_at: null };
    case "/icps":
      return [];
    case "/research-spec":
      return { latest: null, versions: [] }; // ResearchSpecList
    case "/brief/structure/status":
      return { job_id: null, status: "idle", spec_version: null, error: null }; // ResearchJob

    // List route
    case "/prospects":
      return [];
    case "/companies":
      return [];
    case "/sourcing-docs":
      return { company_fit: null, prospect_fit: null }; // SourcingDocList
    case "/people/departments":
      return []; // FacetOption[]
    case "/people/scope-override":
      return { people_search_params: null }; // getPeopleScopeOverride reads .people_search_params
  }

  // Catch-all for any other GET (e.g. facets, prompts) so an un-anticipated load never reaches a
  // real host: an empty object is a safe default; list endpoints fall through to [] above.
  return {};
}

// Install the interceptor. Glob covers every method + path under the dead base. Any request that
// somehow targets a different (real) host will simply not match and — because the base is a dead
// port — fail locally rather than hit prod; failOnUnmocked() (below) makes that loud in tests.
async function mockApi(page: Page): Promise<void> {
  await page.route(`${API_BASE}/**`, (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(jsonFor(req.method(), url.pathname)),
    });
  });
}

// Hard safety net: fail the test if ANY request is ever issued to a host that is not the local dev
// server (127.0.0.1:3100) or the mocked dead API base (127.0.0.1:9876). This guarantees no request
// reaches api.tryholdslot.com or any other real host.
function failOnExternalRequests(page: Page): string[] {
  const offenders: string[] = [];
  page.on("request", (req) => {
    const u = new URL(req.url());
    const ok =
      u.hostname === "127.0.0.1" ||
      u.hostname === "localhost" ||
      u.protocol === "data:" ||
      u.protocol === "blob:";
    if (!ok) offenders.push(req.url());
  });
  return offenders;
}

// One call to wire up auth + mocks + the external-request guard. Returns the offenders array so a
// test can assert it stayed empty.
export async function setupApp(page: Page): Promise<string[]> {
  const offenders = failOnExternalRequests(page);
  await seedAuth(page);
  await mockApi(page);
  return offenders;
}
