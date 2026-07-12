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
          fit_reason: "Right seniority and category.",
          decision: "pending",
        },
      ],
    };
  }

  // Public booking view (F3) — no /{client} prefix. A valid state keeps the page on its live card;
  // the slots are two future UTC instants the FE groups by local day.
  if (path.startsWith("/book/")) {
    const now = Date.now();
    const day2 = now + 2 * 86400000;
    return {
      state: "valid",
      client_name: "HoldSlot",
      duration_min: 30,
      slots: [
        new Date(day2).toISOString(),
        new Date(day2 + 1800000).toISOString(),
        new Date(now + 3 * 86400000).toISOString(),
      ],
      expires_at: null,
    };
  }
  // Public feedback view (F5) — no /{client} prefix.
  if (path.startsWith("/feedback/")) {
    return { state: "valid", client_name: "HoldSlot", expires_at: null };
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

    // List route — the client cursor-pages these, reading `.items` + `.next_cursor` (pageThrough in
    // lib/api.ts). Returning a bare [] made `page.items` undefined → a swallowed TypeError, so e2e
    // passed while the list rendered nothing (R17). One page, no next cursor.
    case "/prospects":
      return { items: [], next_cursor: null };
    case "/companies":
      return { items: [], next_cursor: null };

    // Approval batches (BatchApi[]). The workspace LAYOUT mounts WorkspaceProvider, which calls
    // listBatches on every workspace route — returning the catch-all `{}` made `batches.map`/`.reduce`
    // throw and every workspace + client-status route hit its error boundary (the stale-mock bug the
    // whole suite tripped on). Seed three named batches so the batches tab + status log have rows.
    case "/batches":
      return [1, 2, 3].map((n) => ({
        id: `batch-${n}`,
        name: `Batch ${n}`,
        icp: "ICP A",
        status: n === 1 ? "sent" : "draft",
        total: 5,
        approved: n === 1 ? 2 : 0,
        removed: 0,
        pending: n === 1 ? 3 : 5,
        created_at: "2026-07-10T00:00:00",
        sent_at: n === 1 ? "2026-07-10T01:00:00" : null,
        decided_at: null,
      }));
    // Campaigns (CampaignApi[]) — WorkspaceProvider loads these on mount for the campaign pip + tab.
    // One sending campaign linked to Batch 1.
    case "/campaigns":
      return [
        {
          id: "camp-1",
          batch_id: "batch-1",
          batch_name: "Batch 1",
          name: "Campaign 1",
          icp: "ICP A",
          status: "sending",
          smartlead_campaign_id: "900123",
          lead_total: 5,
          stages: { contacted: 2, replied: 1, meeting: 1, billable: 1 },
          created_at: "2026-07-10T00:00:00",
          updated_at: "2026-07-11T00:00:00",
        },
      ];
    // Reply queue (ReplyApi[]) — the WorkspaceProvider loads this on mount and the workspace LAYOUT's
    // reply pip does `replies.filter(r => !r.handled_at)`, so this MUST be an array. A bare `{}` from
    // the catch-all (this case missing) crashed EVERY workspace route with a reply-pip TypeError. One
    // open (unhandled) reply so the pip shows a count.
    case "/replies":
      return [
        {
          id: "rep-1",
          campaign_id: "camp-1",
          campaign_name: "Campaign 1",
          campaign_lead_id: "lead-1",
          prospect_name: "Dana Reyes",
          prospect_role: "VP Ops",
          stage: "replied",
          reply_body: "Sounds interesting — could you share a couple of times?",
          subject: "Re: quick intro",
          occurred_at: "2026-07-11T09:00:00Z",
          triage: "positive",
          handled_at: null,
          response_body: null,
        },
      ];
    case "/approval-template":
      // ApprovalTemplateApi — the client-status approval page does `tmpl.body.split("\n\n")` on
      // load, so the catch-all `{}` (no `body`) crashed it. Return a valid template.
      return {
        subject: "Prospects for your review",
        body: "Hi there,\n\nHere are this week's prospects.\n\nApprove or request changes.",
        cta: "Review prospects",
      };
    // Phase F console reads. `/meetings` is hit by the WorkspaceProvider on every workspace route
    // (recaps loader) + the billing ledger — MUST be an array or `.filter`/`.map` throws.
    case "/meetings":
      return [
        {
          id: "m1",
          prospect_name: "Dana Reyes",
          company_name: "Acme",
          campaign_name: "Campaign 1",
          batch_name: "Batch 1",
          scheduled_at: "2026-07-10T10:00:00Z",
          meet_link: "https://meet.google.com/abc-defg-hij",
          held: true,
          duration_min: 32,
          outcome: "qualified",
          amount: 500,
          billing_chip: "Billed",
          dispute_window_ends_at: "2026-07-12T10:32:00Z",
          disputed: false,
          feedback_state: "Received",
          feedback_rating: 4,
          won: true,
        },
        {
          id: "m2",
          prospect_name: "Lee Park",
          company_name: "Globex",
          campaign_name: "Campaign 1",
          batch_name: "Batch 1",
          scheduled_at: "2026-07-11T14:00:00Z",
          meet_link: null,
          held: true,
          duration_min: 7,
          outcome: "short_call",
          amount: null,
          billing_chip: "Not billable",
          dispute_window_ends_at: null,
          disputed: false,
          feedback_state: "None",
          feedback_rating: null,
          won: null,
        },
      ];
    case "/bookings":
      return [
        {
          id: "b1",
          prospect_name: "Dana Reyes",
          company_name: "Acme",
          campaign_name: "Campaign 1",
          status: "Confirmed",
          invitation_preview: "Pick a time: https://tryholdslot.com/holdslot/book/xyz",
          reply_event_id: "ev1",
          sent_at: "2026-07-08T00:00:00Z",
          expires_at: "2026-07-15T00:00:00Z",
        },
        {
          id: "b2",
          prospect_name: "Sam Cole",
          company_name: "Initech",
          campaign_name: "Campaign 1",
          status: "Expired",
          invitation_preview: "Pick a time: https://tryholdslot.com/holdslot/book/abc",
          reply_event_id: "ev2",
          sent_at: "2026-06-20T00:00:00Z",
          expires_at: "2026-06-27T00:00:00Z",
        },
      ];
    case "/feedback":
      return [
        {
          id: "m1",
          prospect_name: "Dana Reyes",
          company_name: "Acme",
          state: "Received",
          overdue: false,
          rating: 4,
          chips: ["Well prepared"],
          comment: "Useful, relevant call.",
          feedback_at: "2026-07-11T00:00:00Z",
          scheduled_at: "2026-07-10T10:00:00Z",
        },
        {
          id: "m3",
          prospect_name: "Jo Vance",
          company_name: "Umbrella",
          state: "None",
          overdue: true,
          rating: null,
          chips: [],
          comment: "",
          feedback_at: null,
          scheduled_at: "2026-06-30T10:00:00Z",
        },
      ];
    case "/performance-summary":
      return {
        funnel: [
          { label: "Sourced", n: 120 },
          { label: "Approved", n: 60 },
          { label: "Contacted", n: 50 },
          { label: "Replied", n: 20 },
          { label: "Positive", n: 12 },
          { label: "Meeting booked", n: 4 },
        ],
        new_positive_replies: 3,
        replies_awaiting_review: 2,
        approvals_pending: 1,
        meetings_booked: 4,
        qualified_last_30d: 3,
        qualified_delta: 1,
        meetings_held_week: 2,
        show_up_rate: 0.75,
        awaiting_this_week: 1,
        billable_this_cycle: 1000,
        open_booking_links: 2,
        held_without_feedback: 1,
        calendar: [
          {
            id: "m1",
            scheduled_at: "2026-07-10T10:00:00Z",
            prospect_name: "Dana Reyes",
            outcome: "qualified",
          },
        ],
      };
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
