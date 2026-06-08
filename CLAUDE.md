# HoldSlot — agent guide

Stop buying sales tools. Start buying meetings.

Done-for-you B2B service: turns a client brief into qualified, booked sales meetings; bills
only for meetings that qualify. **Multi-client.** Phase 1 = build the mock UI in `apps/web`,
ported pixel-faithfully from the Claude Design bundle, backed by mock fixtures (no backend).

By positioning HoldSlot as a done-for-you, pay-per-qualified-meeting engine, 
you are positioning yourself at the terminal state of this value chain. 
You aren’t selling the hammer (ZoomInfo), nor the workshop (Clay); 
you are selling the finished house.

## Golden rules
- **The design IS the spec.** `design/` (8 HTML pages + `holdslot.css` + `client-switch.js`) is
  the source of truth. Match it exactly. Don't redesign. Read `design/<page>.html` before porting.
- **Least code wins.** Reuse `design/holdslot.css` near-verbatim as the global stylesheet; emit its
  existing class names from thin components. Don't re-author CSS that already exists.
- **Plain CSS** (globals + co-located page styles). No Tailwind. Tokens live once in `globals.css`.
- Copy is exact; separators are middot `·` only (no em/en dashes). Keep `.sample`/`.ph` markers.
- All data is placeholder in this phase (incl. homepage "meetings booked" count) — wire later.

## Stack
Next.js 15 (App Router, TS) · React 19 · pnpm workspace. Fonts: Fraunces (display) + Archivo
(body) via `next/font`. `apps/api` (FastAPI) + `infra/` are later-phase placeholders.

## Layout
```
apps/web/         the UI. app/ routes · components/ · lib/ · globals.css
design/           vendored Claude Design bundle (READ-ONLY reference)
apps/api/ infra/  placeholders, not built yet
```

## Routes (client slug = `[client]`, drives holdslot.com/<slug>)
| Route | Source file | Shell |
|---|---|---|
| `/` | `home.html` | marketing (self-contained) |
| `/login` | `login.html` | marketing |
| `/[client]/overview` | `overview.html` | console |
| `/[client]/workspace` | `workspace.html` | console |
| `/[client]/client-status` | `external-status.html` | console |
| `/[client]/approve/[token]` | `client-approval.html` | external |
| `/[client]/book/[token]` | `booking.html` | external |
| `/[client]/feedback/[token]` | `feedback.html` | external |

`app/[client]/(console)/layout.tsx` and `app/[client]/(external)/layout.tsx` provide the two shells.

## Three shells
- **marketing** — standalone; home keeps its own page styles.
- **console** — dark sidebar (logo, client switcher, nav groups "Get Meeting" = Overview/Workspace,
  "Client Action Status" = List approval/Booking links/Feedback forms → all to `client-status`
  tabs) + topbar (breadcrumb w/ client name, mobile toggle) + scrim. Shared by overview/workspace/
  client-status. CSS class `.app/.side/.topbar/.content` in holdslot.css.
- **external** — cerulean `.ext-body` + `.ext-card`; each page renders valid / success / expired
  (read `?state=expired`). Class `.ext-*` in holdslot.css.

## Design system (holdslot.css `:root`)
Accent cerulean `#9BB7D6` · deep `#5E7C9E` · wash `#EEF3F9` · ink `#0E1116` · line `#E4E7EC`.
Status (low-chroma): ok `#3E8E6E` · warn `#C08A3E` · danger `#C25B53` · info `#5E7C9E` (+ `*-wash`).
Components already in CSS: `.btn`(primary/ghost/accent/danger, -sm/-xs) · `.badge`(ok/warn/danger/
info/neutral) · `.panel` · `.tbl` · `.tabs/.tab` · `.field/.input/.textarea/.select` · `.toast` ·
console shell · external card · `.ph`/`.sample` markers.

## Client switcher (`client-switch.js` → port to `lib/client.ts` + context)
Clients + selection persist in localStorage; name → slug; updates `[data-client-name]`. Defaults:
Northwind, Acme Robotics. Switching navigates to `/[client]/overview`.

## Page interactions (all client-side, mock)
- **home**: sticky nav + mobile menu · pinned 300vh "how it works" scroll (progress fill + active
  step) · trust parallax · pricing formula · lead-form validation→success · IntersectionObserver
  reveals · honor `prefers-reduced-motion`.
- **login**: 3 views (sign-in / forgot / reset-sent), email+pw validation, show/hide pw, mock submit
  → `/[client]/overview`.
- **overview**: headline band · needs-attention (links to client-status tabs) · weekly stats ·
  animated funnel bars.
- **workspace**: 7 tabs synced to URL hash — Business brief (form+completeness ring+ICP profiles),
  Prospect list (filter table, select, create batch), Sendout Batch, Campaign (send controls + A/B/C
  variants), Reply queue (approve/edit/send, status, empty state, count pips), Billing ledger,
  Meeting summaries. New batch reactively appears in Sendout Batch + Campaign select.
- **client-status**: 3 tabs (approval/booking/feedback) synced to hash + sidebar highlight +
  breadcrumb + back-button; summary chips, email-template preview, status logs.
- **external** (approve/book/feedback): row-remove / slot-picker / star+chips; consent notices;
  valid→success transitions; expired state.

## As built (apps/web)
- `app/globals.css` = `design/holdslot.css` **verbatim** (root layout, applies everywhere). Each page's
  original `<style>` block is extracted to a co-located plain `.css` (e.g. `home.css`, `workspace.css`,
  `approve.css`) imported by that page. No CSS modules — exact class names preserved. Fonts via the
  design's Google Fonts `<link>` in `app/layout.tsx`.
- Shells: `components/console/ConsoleShell` (+ `Sidebar`, `ClientSwitcher`) wraps console pages and
  provides `ToastProvider`; `components/external/ExternalShell` wraps the 3 external pages (valid/
  success/expired, `?state=expired`). Shared bits: `components/Toast`, `Sample`, `StateToggle`.
- `lib/client.ts` (multi-client storage/slug). Data-model types/taxonomy live in the spec doc, not
  in code, until the API needs them (avoids unused contract files).
- **Mock data is co-located** with each page as clearly-named consts (the data/view split is the seam);
  move behind an accessor returning `lib/types` shapes when the API lands. `apps/web` is self-contained.
- **CSS gotcha:** plain `.css` imports are GLOBAL in Next and persist across client-side navigation.
  Page CSS must use **class selectors only** — never bare element selectors (`nav`, `header`, `h1`…),
  or they leak onto other routes. `home.css` (the one page with element selectors) is scoped under a
  `.home` wrapper (`app/page.tsx` wraps content in `<div className="home">`); reset/base lives in globals.

## Commands
`pnpm install` · `pnpm dev` (runs apps/web). `pnpm build` to typecheck + production build.
