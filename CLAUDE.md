# HoldSlot — agent guide

Stop buying sales tools. Start buying meetings.

Done-for-you B2B service: turns a client brief into qualified, booked sales meetings; bills
only for meetings that qualify. **Multi-client.** Phases A–F are **built and shipped to dev**
(A–D+ also on prod FE): `apps/web` is a live-wired console + external pages on a deployed
FastAPI backend (`api.tryholdslot.com`). The mock-fixture Phase 1 is history — the only mock
residue is the homepage stats strip. **Read `docs/initial-build-plan.md` first** — its status
header is the current state of record; `docs/data-schema.md` governs every table/column.

By positioning HoldSlot as a done-for-you, pay-per-qualified-meeting engine,
you are positioning yourself at the terminal state of this value chain.
You aren’t selling the hammer (ZoomInfo), nor the workshop (Clay);
you are selling the finished house.

## Golden rules
- **The design IS the spec for look & feel.** `design/` (8 HTML pages + `holdslot.css`) is the
  visual source of truth. Match it; don't redesign. Behavior/data now follow the live API and
  `initial-build-plan.md` where they've moved past the mock.
- **Least code wins.** Reuse `design/holdslot.css` near-verbatim as the global stylesheet; emit its
  existing class names from thin components. Don't re-author CSS that already exists.
- **Plain CSS** (globals + co-located page styles). No Tailwind. Tokens live once in `globals.css`.
- Copy is exact; separators are middot `·` only (no em/en dashes). Keep `.sample`/`.ph` markers.
- Homepage stats strip is still placeholder; everything else renders live data.
- **Security exception to "match exactly":** some `design/` JS concatenates user input into
  `innerHTML` (client-switch.js, workspace.html). Never port that — render names/labels via JSX or
  `textContent`; no `dangerouslySetInnerHTML`/`innerHTML` for any user-entered value.
- **Deploy/ops rules live in `initial-build-plan.md` §Locked context** (OpenRouter non-US models
  only · Apollo enrich is the only credit spend · backend-before-frontend · commit/push only when asked).

## Stack
Web: Next.js 16 (App Router, TS) · React 19 · TanStack Query (root `app/providers.tsx`) ·
react-big-calendar + date-fns · Playwright e2e (`apps/web/e2e`, route-mocked, no live API) ·
pnpm workspace. Fonts: Fraunces (display) + Archivo (body).
Backend: FastAPI on one Lambda (SnapStart) · Aurora Serverless v2 via Data API · SQLAlchemy +
Alembic (`infra/alembic`, head `0031`) · Terraform (`infra/terraform`). LLM = OpenRouter
(DeepSeek; HK geo-block — non-US providers only). Integrations: Apollo · Smartlead · Google
(Calendar/Meet) · Stripe (dormant).

## Layout
```
apps/web/         the UI. app/ routes · components/ · lib/ (api.ts = the API seam) · e2e/
apps/api/         FastAPI backend. app/domains/* (13 routers) · app/integrations/* · tests/ · scripts/
infra/            alembic migrations + terraform (applied; dev workspace live)
design/           vendored Claude Design bundle (READ-ONLY visual reference)
docs/             initial-build-plan.md (status of record) · data-schema.md · backend-development-plan.md · business-plan.md
```

## Routes (client slug = `[client]`)
| Route | Design source | Shell | Data |
|---|---|---|---|
| `/` | `home.html` | marketing | mock stats strip |
| `/login` | `login.html` | marketing | live auth (login/forgot/reset → first membership) |
| `/privacy` · `/terms` | — | marketing | static (`components/LegalPage`) |
| `/[client]/performance-summary` | `overview.html` | console | live |
| `/[client]/workspace/{brief,list,batches,campaign,replies,summaries,billing}` | `workspace.html` | console | live |
| `/[client]/client-status/{approval,booking,feedback}` | `external-status.html` | console | live |
| `/[client]/approve/[token]` | `client-approval.html` | external | live |
| `/[client]/book/[token]` | `booking.html` | external | live |
| `/[client]/feedback/[token]` | `feedback.html` | external | live |

Workspace/client-status tabs are **nested routes** (not hash tabs); each index route only
translates legacy `#hash` links (`lib/nav.ts useHashRedirect`). Tab bars are portaled into the
console topbar (`TopbarSlotCtx`). `app/[client]/(console)/layout.tsx` and `(external)/layout.tsx`
provide the two shells.

## Three shells
- **marketing** — standalone; home keeps its own page styles.
- **console** — dark sidebar (logo, client switcher, nav groups "Get Meeting" =
  Workspace/Performance Summary, "Client Action" = List Approval/Booking Status/Meeting Feedback →
  `client-status` routes) + topbar (breadcrumb, portal slot, mobile toggle) + scrim. `ConsoleShell`
  provides `ToastProvider` + `MeProvider` + `SessionGuard` (JWT, refresh, cold-start retry in
  `lib/api.ts`). CSS `.app/.side/.topbar/.content`.
- **external** — cerulean `.ext-body` + `.ext-card`; valid / success / expired states are
  **API-driven** (`?state=expired` survives only as a demo override). Class `.ext-*`.

## Design system (holdslot.css `:root`)
Accent cerulean `#9BB7D6` · deep `#5E7C9E` · wash `#EEF3F9` · ink `#0E1116` · line `#E4E7EC`.
Status (low-chroma): ok `#3E8E6E` · warn `#C08A3E` · danger `#C25B53` · info `#5E7C9E` (+ `*-wash`).
Components already in CSS: `.btn`(primary/ghost/accent/danger, -sm/-xs) · `.badge`(ok/warn/danger/
info/neutral) · `.panel` · `.tbl` · `.tabs/.tab` · `.field/.input/.textarea/.select` · `.toast` ·
console shell · external card · `.ph`/`.sample` markers.

## Client switcher
Live memberships from `GET /me` (no localStorage client list — N45); `lib/client.ts` holds the
single-tenant default `{HoldSlot, holdslot}` + slug helpers. Switching navigates to
`/[client]/workspace` (the default page).

## Workspace tabs (live)
Client Brief (form + completeness ring + ICP profiles + async Regenerate Scope) · Prospect List
(find → 4-label buckets → select → **Reveal & score** = the only credit spend → batch) · Approval
Batches (send masked link · owner "Record client decision") · Outreach Campaigns (Smartlead launch,
A/B/C, funnel) · Reply Queue (cross-campaign triage) · Meeting Recaps (held/qualify · Deal-won
toggle) · Billing Ledger (derived rows + dormant Stripe status line).

## As built (apps/web)
- `app/globals.css` = `design/holdslot.css` **verbatim**; page styles co-located per page,
  **class selectors only** (see gotcha). Fonts via the design's Google Fonts `<link>`.
- Data flows through `lib/api.ts` (typed client, auth/refresh, cursor pagination) +
  `components/workspace/WorkspaceProvider` (TanStack Query loaders; `reload*` = invalidate).
- `lib/workspace/fixtures.ts` + `lib/fixtures/client-status.ts` are **dead** (zero importers) —
  delete on the next cleanup pass, don't add new fixture files.
- **CSS gotcha:** plain `.css` imports are GLOBAL in Next and persist across client-side navigation.
  Page CSS must use **class selectors only** — never bare element selectors (`nav`, `header`, `h1`…),
  or they leak onto other routes. `home.css` (the one page with element selectors) is scoped under a
  `.home` wrapper; reset/base lives in globals.

## Commands
`pnpm install` · `pnpm dev` (apps/web) · `pnpm build` (typecheck + prod build) ·
`pnpm exec playwright test` (in apps/web; spawns its own server, API mocked).
Backend (in apps/api): `.venv/bin/python -m pytest -q` · `.venv/bin/ruff check app tests` ·
deploy via `scripts/build-and-deploy.sh` (founder-authorized).
