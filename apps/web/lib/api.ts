// Live API client (A5 cutover) — barrel.
//
// Phase-2.1 split: the 1500-line single file became the `lib/api/` package (core + one module per
// phase). This barrel re-exports every module so all ~24 callers + the route-mocked Playwright suite
// keep importing from `@/lib/api` unchanged — a deploy-neutral refactor (no route/behavior change).
//   core       — API_BASE, tokens/refresh, ApiError, authFetch, cursor paging, auth (login/me/…)
//   briefs     — Phase B: Brief · ICP · ResearchSpec · scoping/fit prompts
//   prospects  — Phase C: Apollo find + enrich, scoring jobs, scope overrides
//   batches    — Phase D: sendout batch + approval template (authed console side)
//   campaigns  — Phase E: outreach campaigns · reply queue · performance summary
//   meetings   — Phase F: meetings · bookings · feedback (authed console reads)
//   external   — token-only public pages: approval · booking · feedback
//   billing    — Phase G: dormant Stripe billing status

export * from "./api/core";
export * from "./api/briefs";
export * from "./api/prospects";
export * from "./api/batches";
export * from "./api/campaigns";
export * from "./api/meetings";
export * from "./api/external";
export * from "./api/billing";
