# MVP-checker review round — 2026-07-12 · findings register (M-register)

> **Read-only planning/review session — zero code changes.** Post-G-NF full-repo audit: plan-vs-code gap
> analysis · phase-status confirmation · code review (backend + frontend, priority-sorted) · simplify check.
> Per the §D+.6 closure rule ("anything discovered from here belongs to a NEW register"), this is that
> register — it covers mostly **E/F/G-NF-era code** (the A–D+ cycle stays closed). Method: 5 parallel
> full-file reviewers (BE gap · FE gap · BE review · FE review · simplify) + local gate re-runs; every P2
> was independently re-verified against the code path before landing here.

## 0 · Session verdict

- **No P1 anywhere.** Money paths verified sound: per-row enrich double-spend stamp, atomic job claims +
  DB-unique one-per-tenant×kind, tenant guard mechanically present on every `/{client}` route, token
  claims idempotent, Stripe HMAC/idempotency/pinned-version correct, meter emission idempotent, no
  `innerHTML`/XSS, paid FE actions ref-guarded against double-click.
- **The code is AHEAD of the docs, not behind** — every material build claim (A–F + G-NF Wave 1+2)
  verified present in code; zero plan-claimed features missing. The gaps were all *doc staleness*
  (fixed this session — §1) plus **10 P2s and ~35 P3s** concentrated in the newest, least-reviewed
  code (campaigns/meetings/billing + their FE surfaces) — §3.
- **Gates re-verified this session:** pytest **358✓/23 skipped** · ruff clean · `tsc` clean · `eslint`
  clean · **Playwright 26✓ (run fresh — closes the "not yet run" open item)** · `dev` == `origin/dev`
  at `a978b36` (the "FE not pushed" claim was stale) · `cutover-prep` local-only at `cd0dca2` ✓.

## 1 · Plan accuracy (task 1) — reconciliation APPLIED this session

`initial-build-plan.md` had accreted status in four places that disagreed (header said v87/`0030`/338
tests · snapshot said v86/`0029`/~60 endpoints · G-NF log said v89/`0031`/358 — the log was right).
**All fixed in-place this session:**

| Doc | Fixed |
|---|---|
| `initial-build-plan.md` | Status header + source-of-truth line + Current-state snapshot → **v89 · head `0031` · 83 routes/13 routers · dev Amplify `a978b36`**; roadmap G row records G-NF Wave 1+2 shipped-dormant; "Still open" block updated (FE pushed · Playwright 26✓ this session); S3 gate row rephrased (E7 shipped); **§API surface table extended** with the 6 missing routers (campaigns · smartlead-webhooks · meetings · meetings-public · billing · stripe-webhook) + `llm-usage`; §D+.3 U3 sentence corrected to as-built (literal checked⊆visible NOT implemented; shipped = N11 prune-on-reload + R13 whole-selection counts) |
| `data-schema.md` | Internal contradiction fixed (`0001→0030` → `0001→0031`) |
| `CLAUDE.md` | **Rewritten** — was a full phase behind ("Phase 1 mock UI, no backend"); now records the live-wired console (auth/SessionGuard, nested-route tabs + portaled tab bars, TanStack Query, live API seam), real backend/infra layout, dead fixture files, test/deploy commands |

Residual doc nuances (recorded, not fixed — historical text): NF-6's "doc-fixtures" are inline in
`test_stripe.py` (no `fixtures/stripe/` dir) · plan F6 lines still describe `B_LOG`/`F_LOG` fixtures as
"today the mocks" (historical; files are now dead — M-D below).

## 2 · Phase status + remaining (task 2) — confirmed against code + git

| Ph | Verified status | Remaining |
|---|---|---|
| A–C | ✅ live (dev + prod FE), matches plan | none (S1/S2 signed off in review #5) |
| D | ✅ live | **founder S3 live batch round** (= G0-2; feeds the E acceptance campaign) |
| D+ | ✅ shipped dev+prod; review cycle closed | 3 standing carve-outs only (R21 · R27-dups · R30-tests) |
| E | 🟢 shipped dev (`d8aef2b`, `0028`/`0029`) | **founder S4/S5 acceptance run** (= G0-1; consumes the S3 batch) |
| F | 🟢 shipped dev (`44b761b`, `0030`), live-verified | **founder F0 real held-Meet (`--meeting-code`) + FA acceptance → tick S6** |
| G | ⬜ human; **G-NF Wave 1+2 code SHIPPED** (v89, `0031` dormant; NF-7 on `cutover-prep`) | founder register FR-1…FR-12; trigger-fired NF-8 (GS deploy ← FR-7) · NF-9 (cutover ← FR-11) · NF-10 (SCALE ← 2nd tenant) |

**Critical path to DoD is now 100% founder-gated:** S3 round → S4/S5 acceptance → F0/FA → G0 all-✓ → run
the loop. No code blocks any gate. This M-register is the only open build backlog (none of it gate-blocking).

## 3 · Code-review findings (task 3) — priority-sorted, with fixes

**P1 — none.**

### P2 — fix in the next build wave (ordered by business impact)

| # | Where | Finding | Suggested fix |
|---|---|---|---|
| **M1** | `web app/[client]/(external)/book/[token]/page.tsx:57-69` (+ load `:42-48`) | Booking-page catch conflates EVERY failure with "link used": a 409 (slot just taken), 503 cold-start, or network blip flips a **valid booking link to a permanent dead-end → meeting lost** (the product's unit of revenue). Load-time catch renders "expired" on transient errors too. | Flip to used/expired only on 409/410; other failures → inline "couldn't book — try again", keep the slot picker; retry/backoff on public GETs |
| **M2** | `api domains/meetings/public.py:59-64` `_read_busy` | On `GoogleError` returns `[]` = "no busy intervals" → **full slot grid offered + `slot_is_free` passes** during a Google outage → double-booked calendar, later swept as a real meeting. Contradicts its own docstring (FT3-9 "offer no slots"). | Return `None` sentinel on error; `view_booking` → `slots=[]`, `book_meeting` → 503-and-release |
| **M3** | `api domains/campaigns/webhooks.py:181-185` `_ingest` | `_unsub_writeback` only runs inside `if target and record_stage_move(...)` — an unsubscribe from a lead already at `drop` (bounced/negative-triaged first) or an unresolvable lead **never lands in the Brief `doNotContact` list**, breaking the documented SG-PDPA ≤5-day honor every future find/enrich/batch relies on. | Call `_unsub_writeback` whenever `internal == LEAD_UNSUBSCRIBED`, resolving the email off the payload, independent of the stage move |
| **M4** | `web components/console/MeContext.tsx:25-31` | Any `/me` failure (Aurora cold-start 503, network blip) → `clearTokens()` + forced re-login. Dev Aurora auto-pauses, so this fires **routinely** on first console open. | Retry cold-start statuses (reuse `isColdStartStatus`); clear tokens only on 401; 5xx/network → keep tokens + retry state |
| **M5** | `web` all 3 external token pages (`approve:16-37` · `feedback:31-52` · `book` load) | Same class as M1 across the other public pages: load-time `.catch()` renders "expired", submit catch flips to "used", on ANY error — prospect/client told a live link is dead after one cold-start hiccup. | Distinguish 410/409 from transient; add a retry affordance (shared helper with M1) |
| **M6** | `api domains/campaigns/router.py:65` `_iso` + `web replies/page.tsx:27` · `CampaignTab.tsx:67` | Campaigns serializes naive ISO (no `Z`; Data API returns naive UTC) and the FE parses with bare `new Date()` → **UTC digits rendered as local dates** — in HK (+8) a reply at 20:00 UTC Jul 11 shows "Jul 11" when it's Jul 12 04:00 local. Meetings domain does it right (`iso_z`). | BE: use `iso_z` in campaigns (mirrors meetings); FE: parse via `parseUtc`/`whenLabel` from `lib/dates.ts` (built for exactly this — R16 lesson) |
| **M7** | `web performance-summary/page.tsx:32-40` | `getPerformanceSummary(...).catch(() => undefined)` silently strands the page: hard "0" qualified meetings + zero needs-attention + "Loading funnel…" forever — **real-looking wrong numbers on the client-facing surface**. | Keep an error state (retry link / "couldn't load" panel) instead of zero-defaults |
| **M8** | `api models.py:838` `CampaignLead.variant_key` + `campaigns/router.py:94-113` | **No code path ever writes `variant_key`** → `_variant_metrics` always returns `{}` → the E6 A/B scoreboard shows 0/0/0 forever and `set_variant_winner` decides on blank data. In-code comment acknowledges it; the plan never surfaced it. | **✅ DECIDED (build):** ingest Smartlead's per-lead variant (webhook/statistics field) onto the lead so the scoreboard shows real counts |
| **M9** | `web workspace/billing/page.tsx:47-62` | Ledger "Refresh" runs the server sweep but never invalidates `["meetings", client, "past"]` → Meeting Recaps shows stale outcome/`won` indefinitely after a sweep flips a meeting to Billed. | After `refreshMeetings`, `invalidateQueries(["meetings", client, "past"])`; ideally read the ledger from that same query (also kills the duplicate fetch — S-note) |
| **M10** | `api domains/batches/router.py:282-295` `delete_batch` | Deleting a batch with a `Campaign` (FK RESTRICT) or billed-evidence `Meeting.approval_id` → unhandled FK violation → **raw 500 on a first-class console button**. | Pre-check (or catch FK error) → 409 "batch has a campaign / billed evidence" |

### P3 — backend (fold into the M-wave where cheap)

| # | Where | Finding · fix |
|---|---|---|
| **M11** | `meetings/service.py:78-85,126-145` | Founder-authored `brief.data.availability` unvalidated (`meeting_minutes:"abc"` → ValueError; malformed window → IndexError) and `availability_of` runs on EVERY meetings-surface read + the public booking page → one bad Brief edit 500s the whole surface. Fix: try/except per field → FD-1 defaults |
| **M12** | `billing/router.py:162-170` | `billing_status` never applies `_rollover` → in a new UTC month the GS6 line shows last month's usage until an enrich call. Fix: apply rollover read-only (no commit) |
| **M13** | `billing/router.py:104-141` | `reserve_enrichment` usage bump is read-modify-write (not `SET usage = usage + n`) + a mid-flow `db.commit()` commits the caller's dirty session. Shielded today only by the one-job invariant in another domain. Fix: atomic increment; drop mid-flow commit |
| **M14** | `billing/router.py:173-211` | Re-POST subscription with a different plan updates local caps but never touches Stripe prices → silent divergence (dormant today). Fix: 409 on plan change or call Stripe update |
| **M15** | `campaigns/router.py:599-621` | `triage_reply` stores `body.triage` unvalidated → typo'd class marks handled, no stage move, pollutes summary counts. Fix: 400 unless in `TRIAGE_CLASSES` |
| **M16** | `meetings/schemas.py:61-64` | Public `FeedbackIn.chips/comment` unbounded → a token holder can store MBs on the meeting row. Fix: max_length/count caps |
| **M17** | `campaigns/router.py:624-701` | `respond_reply`: booking-link row persisted only after the Smartlead send → DB failure post-send emails a URL that 410s forever; `SmartleadError` escapes as raw 500. Fix: catch → 502; accept-or-document the dead-link window |
| **M18** | `meetings/router.py:217-255` | `correct_outcome` works on unswept future meetings (`held IS NULL`) → accidental pre-meeting "qualified" becomes billable. Fix: 409 unless held/past |
| **M19** | `integrations/google/client.py:258-291` | `create_event` retries POST on transport timeout → duplicate calendar events + invites. Fix: no retry on that POST (or check-before-retry) |
| **M20** | `prospects/router.py:1025` | `add_company` raw `uuid.UUID(body.icp_id)` → 500 (siblings 400). Fix: reuse `_validate_icp_id` |
| **M21** | perf | `list_bookings` N+1 (2 event queries per link → 100 RTs at 50 links; use the `_lead_rows` bucket pattern) · `list_replies` unpaginated/unbounded (add cursor/cap) · `performance_summary` ~18 sequential counts (merge into conditional aggregates) · `pause/resume` serialize full `_detail()` then discard (return `_campaign_out`) |
| **M22** | design | Owner-gating divergence: briefs (`PUT /brief`, `POST /brief/structure` = paid DeepSeek call) + icps accept any member while every other write/spend door is owner-only — **✅ DECIDED: keep open** to all members (document as deliberate, no gating change) · malformed-id → 400 vs 404 varies by domain (pick 404, share helper) · `billing/webhooks.py:37` sole `async def` route doing sync DB I/O (make sync) · `ix_outreach_event_tenant_type_created` indexes `created_at` but consumers filter/order `occurred_at`; `Subscription.stripe_customer_id` unindexed (note) |

### P3 — frontend

| # | Where | Finding · fix |
|---|---|---|
| **M23** | `list/page.tsx:1093-1113` | `runUpdateFields` (Apollo credit spend) lacks the synchronous ref guard its sibling paid actions carry (async `disabled` only flips post-render). Fix: same `rescoringCoRef`-style guard |
| **M24** | `billing/page.tsx:53-62` | sweep `refresh()` has no catch → failure = unhandled rejection, zero feedback. Fix: catch → warn toast |
| **M25** | `login/page.tsx:115-120` | Any failure (500/network) shows "Invalid email or password." Fix: branch on status → "server unreachable — try again" variant |
| **M26** | `CampaignTab.tsx:280-309` | Variant save/add/delete toasts success + clears the edit buffer BEFORE the PUT resolves → on failure, false "saved" + draft lost. Fix: toast/clear after resolve |
| **M27** | `summaries/page.tsx:59-62` + `replies/page.tsx:104-106` | Campaign filters keyed/valued by `name` → same-named campaigns collide (both minted from batch names). Fix: filter by `campaign_id` |
| **M28** | `summaries/page.tsx:120-145` | NF-3 won toggle is one-way — no path back to `null` though the API accepts it. Fix: clicking the active button sends `null` |
| **M29** | `batches/page.tsx:89-106` | `?batch=` deep-link effect re-fires on `batches.length` change → deleting another batch re-expands + scroll-jumps. Fix: consume once (ref) or strip the param |
| **M30** | `client-status/approval/page.tsx:27` | `day()` renders the UTC day while the batches tab renders local (`localCalendarDate`, the N38 fix) → same batch shows different "Sent" dates. Fix: reuse `localCalendarDate` |
| **M31** | ui | `list/page.tsx:112-114` low-fit confirm uses `window.confirm` vs the design-system Modal everywhere else · `performance-summary:100` "3 open" chip hardcoded next to live counts · `client-status/feedback:81-84` "Forms sent" counts `state:"None"` rows · booking/feedback failure toasts omit `"warn"` kind (render green) · `batches:518-522` Brief-query error asserts "No attendee emails on your Brief yet" (false claim; distinguish `isError`) · em-dash separators in new FE copy vs the middot rule (one sweep) |
| **M32** | `ClientSwitcher.tsx:39-42` | A non-member slug renders as a normal-looking current client; every call then 403/404-toasts. Fix: once `me` resolves, redirect to `me.clients[0]` / access notice |

### M-D · Dead-code inventory (delete on the M-wave; all grep-verified zero callers)

- **BE:** `smartlead.sending_account_ids()` (superseded by `0029` DB pool) · `smartlead.fetch_analytics()` ·
  `meetings/service.participant_duration_min()` + `event_meeting_code()` (test-only) · campaigns
  `IllegalMove` · `CAMPAIGN_STARTED` (mapped, never written) · launch `COMPLETED` status (no transition
  sets it; docstring promises it) · `Meeting.summary` JSONB (no reader/writer — the deferred
  `meeting_summary` seam; keep only if the LLM recap is imminent) · `Subscription.icp_limit`/
  `plan_icp_limit` (serialized, enforced nowhere) · new dup helpers: `_brief_data`×2 · `_iso`×4 ·
  `is_unique_violation` living in `prospects/scoring` but imported by 5 domains (→ `core/db.py`) ·
  cross-module private imports (`meetings/public._brief_attendee` ← router; `launch._fail` ← router)
- **FE:** `lib/workspace/fixtures.ts` (whole file, 140 LOC) · `lib/fixtures/client-status.ts` (whole file,
  102 LOC, + the empty dir) · `lib/workspace/types.ts:64-95` `Campaign`/`Reply`/`LedgerRow` ·
  `constants.ts` `MOCK_TODAY`/`TODAY_ISO` + needless exports (`localCalendarDate`·`UNSCORED_RANK`·
  `labelRank`) · `WorkspaceProvider.setReplies` (zero consumers; NF-2 comment stale) · `api.ts`
  `FunnelStageApi` export · unused `Sample` import in `book/[token]` · ~~`api.ts correctOutcome`~~ —
  **✅ DECIDED: keep** — no longer dead; it's the wiring for the new M33 outcome-correction/dispute UI
  (backend door exists, `meetings/router.py:217`)

## 4 · Simplify register (task 4) — same output, same UI flow, ~500+ LOC less

From the dedicated simplify pass (S1–S25, all claims grep/read-verified; SAFE = mechanical zero-behavior-
change, CAREFUL = pin with a test first) **plus** the review-pass duplication notes (S26–S31). Biggest
safe wins first:

| # | Risk | What · where · est. LOC |
|---|---|---|
| S1 | SAFE | Dead CSS rule blocks — `workspace.css` (`.sum-card .sv .rec-link`·`.icp-foot .est`·`.cmp-name-input`·`.cmp-drop`·`.cmp-chip*`·`.cmp-send`·`.cmp-logch.calendar/.stripe`·`.cmp-logmeta`) + `performance-summary.css` `.ph-inline` + `home.css` `.ph-tag` · **~115** |
| S2 | CAREFUL | U1.6 localStorage scope-migration shim (`constants.ts:448-485` + its `list/page.tsx:630-660` effect) — inert once every founder browser carries the done-flag; verify no un-migrated `holdslot_scope_*` keys first · **~70** |
| S3 | SAFE | Dead-serialized meeting fields FE never reads (`MeetingOut.meet_link/duration_min/disputed/dispute_window_ends_at` · `FeedbackRowOut.chips` · `BookingConfirm` body) — schema+serializer+api.ts types only; columns/logic untouched · **~25** |
| S4 | CAREFUL | `<Field>` wrapper for the 17× identical `div.field>label+input` blocks in list-page modals · **~40-55** |
| S5 | CAREFUL | `ConfirmFooter` for the 9 identical Cancel-ghost + primary-busy modal footers (list ×5 · batches ×3 · spec ×1) · **~50-70** |
| S6 | CAREFUL | Shared two-pane prompt editor (spec.tsx:799-847 ≈ list/page.tsx:2445-2511) · **~30-35** |
| S7 | SAFE | `toggleId` Set-toggle helper (idiom ×8-9 across list/spec/CampaignTab) · **~25-30** |
| S8 | CAREFUL | CampaignTab detail fetch → `useQuery(["campaign", client, id])` (kills hand-rolled `reqRef` staleness guard) · **~25-30** |
| S9 | SAFE | Dead-serialized campaign/report fields (`CampaignOut.smartlead_campaign_id/updated_at` · `ReplyOut.campaign_lead_id` · `ScoringJobOut.kind` · `PerformanceSummaryOut.meetings_booked`) · **~12** |
| S10 | SAFE | `get_research_spec` fetches ALL spec rows (full JSONB) for a `versions` list no FE reads (+ unread `model`/`llm_call_id`) → `LIMIT 1` latest-spec read · **~10 + real query win** |
| S11 | SAFE | Batch-detail fields never rendered (`BatchProspectOut.seniority/fit_reason` · `BatchCompanyGroup.size/country/fit_reason`) · **~12** |
| S12 | SAFE | Approval external view over-serializes (`seniority`/`decision`/`count`/`expires_at`; decide-response counts discarded) — masking allow-list gets *smaller* · **~8** |
| S13 | SAFE | Secret-fetch boilerplate ×5 integrations → one `fetch_secret_json` (exists as `core/config._get_secret_json`) · **~15** |
| S14 | SAFE | Dead endpoint `GET /clients` (FE uses `/me`; no test/script hits it) · **~7** |
| S15 | SAFE | `CompanyOut.trigger_line` never rendered (close-out push unrendered it) — drop serialization; stays in `fit_components` · **~4** |
| S16 | SAFE | `ResearchRunOut.rows_accepted` (never written — always 0) + `.rubric_version` (zero FE reads) — drop from Out shape; keep DB lineage columns · **~6** |
| S17 | SAFE | Dead campaigns-service constants `TRIAGE_CLASSES`\* + `STAGES` (\*wire M15 first — M15 makes `TRIAGE_CLASSES` load-bearing) · **~9** |
| S18 | CAREFUL | `<FitCell>` for the two three-state score cells (company :849-878 ≈ person :2312-2330) + dup `list-overlay`/spinner spans · **~30** |
| S19 | CAREFUL | `<FacetRow>` (mapped identically ×3) + the duplicated ICP-filter `<select>` (Step-1 ≈ Step-2) · **~25** |
| S20 | SAFE | `stageForPeople` ≈ `runFindPeople` byte-identical bar the toast string → `runPeopleFind(ids, msg)` · **~10** |
| S21 | SAFE | Single-valued props + micro-dupes (`SpecChips.warn` · `Section.extra` · `safeHref`×2 · `isStep2`×3 · "source · manual" badge ×2 · `groupByCompany().meta` always `""`) · **~15** |
| S22 | CAREFUL | v3-spec fallback (`research_spec.py:598-604` + FE mirror) — removable once every tenant's latest spec is v4+ (one SQL check) · **~13** |
| S23 | CAREFUL | Legacy flat (pre-`by_icp`) scope-override payload fallback (`prospects/router.py:202-203`) — one SQL check first · **~4** |
| S24 | CAREFUL | `apollo.search_companies` production-dead (real path = `search_companies_meta`; callers are tests) — retarget the paginate test, delete · **~22** |
| S25 | SAFE | `STATUS_LABEL` = `Object.fromEntries(STATUS_TABS)` (StatusTab.tsx restates the tuples) · **~4** |
| S26 | SAFE | Date formatting 6× duplicated (`fmt`/`fmtWhen`/`fmtDate` one-offs) → one `fmtDay(iso)` in `lib/dates.ts` — **fixes the M6/M30 tz bug class and the dup together** · **~25** |
| S27 | SAFE | OUTCOME badge map ×3 (summaries · billing · MeetingCalendar) → `lib/workspace/constants` · **~10** |
| S28 | SAFE | billing page re-fetches `listMeetings(client,"past")` the provider caches; approval page raw `listBatches` bypasses `["batches"]` — share query keys (also fixes M9 for free) · **~15** |
| S29 | SAFE | billing hand-rolled CSV quoting → `lib/csv.ts` helper serving both · **~15** |
| S30 | — | `list/page.tsx` (3005 LOC) split: Step-1 table · Step-2 table · 5 modals separable with existing state lifted; `SEL_CSS`/`SE_CSS` strings → workspace.css. Not LOC-saving, but the single biggest reviewability win |
| S31 | SAFE | `useParams<{client}>` → `useClient()` in billing/booking/feedback pages (consistency) · **~5** |

**Do-not-touch (looks removable, isn't):** `rbc-*` CSS (react-big-calendar runtime classes) ·
`bucket-dot--*` (template string) · `globals.css` (design bundle verbatim by golden rule) ·
`GET /{client}/llm-usage` no FE caller **by design** (NF-4 Swagger surface) · FE `MOVES`/`PER_MEETING_USD`
mirrors (deliberate sync copies; server still enforces) · `useHashRedirect` (legacy links in old emails) ·
`smartlead.add_leads(settings=…)` (tested compliance guard) · `list_email_accounts` (used by
`e_smoke_live.py`) · all Stripe/billing code (dormant ≠ dead) · `core/pagination`/`cache`/`email` (≥2 real
callers each) · every `Settings` field is read · converting list/brief `useState` mirrors to `useQuery`
(refetch/loading semantics would change — fails the provably-identical bar).

## 5 · Suggested execution order (one M-wave, backend-before-frontend)

1. **M-wave P2 pass** — M2/M3/M8-BE-half/M10 (backend) then M1/M4/M5/M6/M7/M9 (frontend; M6 needs the
   BE `iso_z` half first). M1+M5 share one "distinguish 410 from transient + retry" helper. *Money-path
   rule applies: each gets a non-Aurora unit test (the N1 lesson).*
2. **P3 sweep** — M11 first (public-page 500 risk), then M12-M22 backend · M23-M32 frontend, cheapest-first.
3. **Dead-code + SAFE simplify** — M-D + S1/S3/S7/S9-S17/S20/S21/S25-S29/S31 ride the same commits as
   the files they touch; CAREFUL items (S2/S4-S6/S8/S18/S19/S22-S24) behind their pin-tests, only if slack.
4. Founder decisions **RESOLVED 2026-07-12** (§6) — no forks remain: **M8** = build variant ingestion (P2) ·
   **M33** = build the outcome-correction/dispute UI, keep `correctOutcome` (new P3, pairs w/ M18) ·
   **M22** = Brief/ICP stay open to all members (document only, no gate).

Exit gates: the standing protocol (pytest+ruff+tsc+eslint+build+Playwright green · founder-authorized push).

## 6 · Consolidated build plan (task 3 + task 4 merged, execution-ordered)

One flat backlog of every fix (M) and simplify (S) item, ordered by the §5 waves. `Kind`: fix · perf ·
design · ui · dead · simplify · refactor. `P/R`: P2/P3 priority for fixes, SAFE/CAREFUL risk for simplify.
LOC only tracked for simplify. Nothing here gates a founder acceptance gate.

### Wave 1 — P2 fixes (backend-first, then FE; each gets a non-Aurora unit test) — ✅ BUILT + GATED 2026-07-13 (see §7; awaiting founder push)

| # | Kind | P/R | Side | Where · what → fix |
|---|---|---|---|---|
| M2 | fix | P2 | BE | `meetings/public.py:59-64` · `_read_busy` returns `[]` on GoogleError → double-booking → return `None` sentinel; view=`slots[]`, book=503+release |
| M3 | fix | P2 | BE | `campaigns/webhooks.py:181-185` · unsub write-back nested under stage-move guard → PDPA skip → call whenever `LEAD_UNSUBSCRIBED`, resolve email off payload |
| M8 | fix | P2 | BE+FE | `models.py:838` + `campaigns/router.py:94-113` · `variant_key` never written → E6 A/B scoreboard blank → **✅ DECIDED (build):** ingest Smartlead's per-lead variant onto the lead so the scoreboard shows real per-A/B/C sent/reply/meeting counts |
| M10 | fix | P2 | BE | `batches/router.py:282-295` · `delete_batch` FK RESTRICT → raw 500 → pre-check/catch → 409 |
| M1 | fix | P2 | FE | `book/[token]/page.tsx:57-69` · catch flips valid link to dead-end → used/expired only on 409/410, else inline retry + keep picker |
| M4 | fix | P2 | FE | `MeContext.tsx:25-31` · `/me` failure clears session on cold-start → clear only on 401; 5xx/net → keep+retry |
| M5 | fix | P2 | FE | `approve` · `feedback` · `book` load · same class as M1 on all public pages → shared 410-vs-transient + retry helper (with M1) |
| M6 | fix | P2 | BE+FE | `campaigns/router.py:65` + `replies`/`CampaignTab` · naive ISO → wrong local date in HK → `iso_z` (BE) + `parseUtc`/`whenLabel` (FE) |
| M7 | fix | P2 | FE | `performance-summary/page.tsx:32-40` · silent zero-defaults on client surface → error/retry state |
| M9 | fix | P2 | FE | `billing/page.tsx:47-62` · refresh doesn't invalidate meetings → stale recaps → `invalidateQueries(["meetings",client,"past"])` |

### Wave 2 — P3 backend sweep (M11 first: public-page 500 risk)

| # | Kind | P/R | Side | Where · what → fix |
|---|---|---|---|---|
| M11 | fix | P3 | BE | `meetings/service.py:78-145` · unvalidated `brief.availability` 500s the whole surface + booking page → try/except per field → FD-1 defaults |
| M12 | fix | P3 | BE | `billing/router.py:162-170` · no `_rollover` → stale prior-month usage → read-only rollover (no commit) |
| M13 | fix | P3 | BE | `billing/router.py:104-141` · read-modify-write usage + mid-flow `db.commit()` → atomic `SET usage=usage+n`; drop commit |
| M14 | fix | P3 | BE | `billing/router.py:173-211` · plan change skips Stripe prices → 409 or Stripe update (dormant) |
| M15 | fix | P3 | BE | `campaigns/router.py:599-621` · `triage_reply` stores unvalidated class → 400 unless in `TRIAGE_CLASSES` (makes S17's const load-bearing) |
| M16 | fix | P3 | BE | `meetings/schemas.py:61-64` · unbounded public `FeedbackIn.chips/comment` → max_length/count caps |
| M17 | fix | P3 | BE | `campaigns/router.py:624-701` · booking-link persisted after Smartlead send → catch→502; accept/document dead-link window |
| M18 | fix | P3 | BE | `meetings/router.py:217-255` · `correct_outcome` on unswept future meeting → billable → 409 unless held/past |
| M19 | fix | P3 | BE | `google/client.py:258-291` · `create_event` retries POST on timeout → dup events → no retry / check-before-retry |
| M20 | fix | P3 | BE | `prospects/router.py:1025` · raw `uuid.UUID(icp_id)` → 500 → reuse `_validate_icp_id` |
| M21 | perf | P3 | BE | `list_bookings` N+1 · `list_replies` unpaginated · `performance_summary` 18 seq counts · `pause/resume` full `_detail()` discarded |
| M22 | design | P3 | BE | Brief/ICP editing → **✅ DECIDED (keep open):** stays available to all members by design; add a code comment + plan note, **no gating change**. Remaining M22 work: 400-vs-404 helper · async route doing sync IO · index `created_at`-vs-`occurred_at` |

### Wave 3 — P3 frontend sweep (cheapest-first)

| # | Kind | P/R | Side | Where · what → fix |
|---|---|---|---|---|
| M23 | fix | P3 | FE | `list/page.tsx:1093-1113` · `runUpdateFields` (credit spend) no sync ref guard → `rescoringCoRef`-style guard |
| M24 | fix | P3 | FE | `billing/page.tsx:53-62` · sweep `refresh()` no catch → warn toast |
| M25 | fix | P3 | FE | `login/page.tsx:115-120` · all failures show "invalid email or password" → branch on status |
| M26 | fix | P3 | FE | `CampaignTab.tsx:280-309` · toast/clear buffer before PUT resolves → toast/clear after resolve |
| M27 | fix | P3 | FE | `summaries:59-62` + `replies:104-106` · filter keyed by `name` collides → filter by `campaign_id` |
| M28 | fix | P3 | FE | `summaries/page.tsx:120-145` · won toggle one-way → clicking active sends `null` |
| M29 | fix | P3 | FE | `batches/page.tsx:89-106` · `?batch=` effect re-fires on length change → consume once (ref) |
| M30 | fix | P3 | FE | `client-status/approval/page.tsx:27` · UTC day vs batches' local → reuse `localCalendarDate` |
| M31 | ui | P3 | FE | `window.confirm` vs Modal · hardcoded "3 open" · em-dash vs middot · toast kinds · false Brief-error copy |
| M32 | fix | P3 | FE | `ClientSwitcher.tsx:39-42` · non-member slug renders live → redirect to `me.clients[0]`/notice |
| M33 | build | P3 | FE+BE | **✅ NEW (decided): outcome-correction / dispute UI** — backend door already exists (`meetings/router.py:217`); build the console surface to correct a mis-marked held/qualified/won meeting before it bills. **Pairs with M18** (409-guard so a future/unswept meeting can't be corrected into a bill) |

### Wave 4 — dead-code + SAFE simplify (ride the same commits as touched files)

| # | Kind | P/R | Side | What · where · LOC |
|---|---|---|---|---|
| M-D | dead | — | BE+FE | Delete all grep-verified zero-caller code (§M-D). **BE:** smartlead dead fns · `IllegalMove` · `CAMPAIGN_STARTED` · `Meeting.summary` · dup helpers → `core/db`. **FE:** `fixtures.ts` · `client-status.ts` · dead types/consts. **NOTE:** `correctOutcome` is **no longer dead** — it's now the wiring for M33 (keep the export) |
| S1 | simplify | SAFE | FE | dead CSS rule blocks (workspace/perf/home) · ~115 |
| S3 | simplify | SAFE | BE | dead-serialized meeting fields (`meet_link`/`duration_min`/`disputed`/…) · ~25 |
| S7 | simplify | SAFE | FE | `toggleId` Set-toggle helper ×8-9 · ~25-30 |
| S9 | simplify | SAFE | BE | dead-serialized campaign/report fields · ~12 |
| S10 | simplify | SAFE | BE | `get_research_spec` → `LIMIT 1` latest-spec · ~10 + query win |
| S11 | simplify | SAFE | BE | batch-detail fields never rendered · ~12 |
| S12 | simplify | SAFE | BE | approval external view over-serialize · ~8 |
| S13 | simplify | SAFE | BE | secret-fetch boilerplate ×5 → `fetch_secret_json` · ~15 |
| S14 | simplify | SAFE | BE | dead endpoint `GET /clients` · ~7 |
| S15 | simplify | SAFE | BE | `CompanyOut.trigger_line` never rendered · ~4 |
| S16 | simplify | SAFE | BE | `ResearchRunOut.rows_accepted`/`.rubric_version` · ~6 |
| S17 | simplify | SAFE | BE | dead campaigns constants (`STAGES`; `TRIAGE_CLASSES` **after M15**) · ~9 |
| S20 | simplify | SAFE | FE | `stageForPeople`≈`runFindPeople` → `runPeopleFind(ids,msg)` · ~10 |
| S21 | simplify | SAFE | FE | single-valued props + micro-dupes · ~15 |
| S25 | simplify | SAFE | FE | `STATUS_LABEL` = `Object.fromEntries(STATUS_TABS)` · ~4 |
| S26 | simplify | SAFE | FE | date fmt 6× → `fmtDay(iso)` — **also fixes M6/M30 tz bug class** · ~25 |
| S27 | simplify | SAFE | FE | OUTCOME badge map ×3 → constants · ~10 |
| S28 | simplify | SAFE | FE | share query keys — **also fixes M9** · ~15 |
| S29 | simplify | SAFE | FE | billing CSV → `lib/csv.ts` helper · ~15 |
| S31 | simplify | SAFE | FE | `useParams` → `useClient()` (billing/booking/feedback) · ~5 |

### Wave 5 — CAREFUL simplify (behind pin-tests, only if slack)

| # | Kind | P/R | Side | What · where · LOC |
|---|---|---|---|---|
| S2 | simplify | CAREFUL | FE | localStorage scope-migration shim (verify no un-migrated keys) · ~70 |
| S4 | simplify | CAREFUL | FE | `<Field>` wrapper ×17 list-modal blocks · ~40-55 |
| S5 | simplify | CAREFUL | FE | `ConfirmFooter` ×9 modal footers · ~50-70 |
| S6 | simplify | CAREFUL | FE | shared two-pane prompt editor (spec≈list) · ~30-35 |
| S8 | simplify | CAREFUL | FE | `CampaignTab` detail → `useQuery` (kills `reqRef` guard) · ~25-30 |
| S18 | simplify | CAREFUL | FE | `<FitCell>` ×2 three-state score cells · ~30 |
| S19 | simplify | CAREFUL | FE | `<FacetRow>` ×3 + dup ICP `<select>` · ~25 |
| S22 | simplify | CAREFUL | BE+FE | v3-spec fallback (SQL check first) · ~13 |
| S23 | simplify | CAREFUL | BE | legacy flat scope-override fallback (SQL check) · ~4 |
| S24 | simplify | CAREFUL | BE | `apollo.search_companies` prod-dead (retarget test) · ~22 |
| S30 | refactor | — | FE | `list/page.tsx` (3005 LOC) split — reviewability, not LOC · — |

**Totals:** 33 fixes/builds (0 P1 · 10 P2 · 23 P3, incl. M33) + M-D dead-code + 31 simplify (~500+ LOC).
**All 3 founder decisions RESOLVED 2026-07-12 — the plan now has zero human dependencies:**

| Decision | Resolution | Effect on plan |
|---|---|---|
| **M8** · A/B scoreboard | **Build** variant ingestion | stays P2; now a concrete build (ingest Smartlead per-lead variant), not a build-vs-hide fork |
| **`correctOutcome`** · dispute UI | **Build** the surface | becomes **M33** (new P3 build); `correctOutcome` export kept, removed from dead-code |
| **M22** · Brief/ICP access | **Keep open** to all members | no gating change; document as deliberate — the only work left in M22 is the 3 unrelated cleanups |

Do-not-touch list (§4) still governs.

## 7 · Wave 1 — BUILT + GATED (2026-07-13)

All 10 P2 items shipped to the working tree (backend-before-frontend, per §5). **Not yet
committed/pushed** — the standing "commit/push only when asked · founder-authorized" gate holds.
Gates re-run locally after the wave: **backend pytest 365✓ / 25 skipped** (was 358✓/23 — **+7 new
non-Aurora units**; +2 Aurora-gated skips) · **ruff clean** · **tsc clean** · **eslint clean (0
warnings)** · **next build ✓** · **Playwright 26✓**. The three `docs/*.md` edits in the tree are the
prior-session doc reconciliation (§1), not this build; the build touched only `apps/api` + `apps/web`
(+ one new FE component).

### 7.1 · What shipped, per item

| # | Side | Built (file) | Test proof |
|---|---|---|---|
| M2 | BE | `meetings/public.py` — `_read_busy` returns a `None` sentinel on `GoogleError` (was `[]` = "all free"); `view_booking` → `slots=[]`, `book_meeting` → 503 **+ releases the claim** during an outage | non-Aurora `test_read_busy_returns_none_sentinel_on_google_error`; Aurora `test_freebusy_outage_offers_no_slots_and_503_releases` |
| M3 | BE | `campaigns/webhooks.py` — the `_unsub_writeback` (PDPA `doNotContact`) now runs whenever `internal == LEAD_UNSUBSCRIBED`, **independent of the stage move** (was nested under it → a drop/unresolvable unsub silently skipped the list) | non-Aurora `test_unsub_writeback_*` (list+string forms · noop guards); Aurora funnel test extended with an unresolvable-lead unsub → DNC write |
| M6 | BE | `campaigns/router.py` — `_iso` routes through `msvc.iso_z` → `…Z` (mirrors meetings); fixes the naive-ISO → wrong-HK-day bug on reply/campaign timestamps | non-Aurora `test_campaign_iso_serializer_pins_utc_z` |
| M8 | BE | `campaigns/service.py` `variant_label()` (tolerant per-lead A/B/C read) + `webhooks._ingest` stamps `CampaignLead.variant_key` first-seen → the E6 scoreboard now derives real per-variant counts | non-Aurora `test_variant_label_*`; Aurora funnel test asserts the send event stamps `variant_key="A"` |
| M10 | BE | `prospects/scoring.py` `is_fk_violation()` (mirrors `is_unique_violation`, driver-drift-proof) + `batches/router.delete_batch` catches it → **409** (was a raw 500 on a first-class button) | non-Aurora `test_is_fk_violation_*`; Aurora `test_delete_batch_with_campaign_reference_409s` |
| M1 | FE | `book/[token]/page.tsx` — load error → retry (never a fake "expired"); submit branches: **410 → used pane · 409 → keep picker + refresh times ("pick another") · else inline retry** | Playwright 26✓ (route-mocked); classifiers unit-safe |
| M4 | FE | `MeContext.tsx` — `/me` failure clears tokens **only on 401**; a cold-start 5xx / network blip keeps the session + shows a full-pane retry (`MeLoadError`); true expiry still flows via `holdslot:auth-expired` | Playwright 26✓ |
| M5 | FE | `approve` + `feedback` + `book` share `isLinkGoneError`/`isSlotTakenError`/`isTransientStatus` (lib/api) + `RetryNotice` (new component): 410 → dead pane, everything else → keep the page + retry | Playwright 26✓ |
| M6 | FE | `replies/page.tsx` `fmtDate` + `CampaignTab.tsx` `fmtWhen` parse via `parseUtc` (lib/dates) — belt-and-suspenders with the BE `iso_z` half | Playwright 26✓ |
| M7 | FE | `performance-summary/page.tsx` — a load failure now shows a retry panel instead of silent hard-zeros + a permanent "Loading funnel…" on the client-facing surface | Playwright 26✓ |
| M9 | FE | `billing/page.tsx` — after the sweep, `refresh()` also `reloadMeetings()` (invalidates `["meetings",client,"past"]`) so Meeting Recaps isn't stale | Playwright 26✓ |
| M8 | FE | **No change needed** — `CampaignTab` already reads `v.sent/opens/replies`; M8-BE populating `variant_key` lights the scoreboard up | verified in-code (`CampaignTab.tsx:611-612`) |

### 7.2 · Cross-cutting additions (the shared enablers)

- **`ApiError extends Error`** (`lib/api.ts`) — carries the HTTP `status`, thrown by `getMe` +
  every public-token endpoint (`getBookingView`/`submitBooking`/`getApproval`/`decideApproval`/
  `getFeedbackView`/`submitFeedback`). Backward-compatible (extends `Error`), so every existing
  `catch (e) { e.message }` path is unchanged. This is the M1/M4/M5 enabler.
- **`RetryNotice`** (`components/external/RetryNotice.tsx`, new) — the one retry affordance the three
  public pages share (design-system classes only, no new CSS).
- **`is_fk_violation`** (`prospects/scoring.py`) — a sibling of the existing `is_unique_violation`,
  matching SQLSTATE 23503 across the psycopg / RDS-Data-API driver drift.

### 7.3 · Deliberate deviations from the plan text (with rationale)

1. **Booking 409 is NOT flipped to "used/expired."** §3 M1 read "flip to used/expired only on
   409/410," but a 409 on `book` means *the slot was just taken* — the link is still valid. Flipping
   it to a dead "used" pane would lose the meeting on a slot race — the exact harm M1 exists to stop.
   Shipped behavior: **410 → dead pane; 409 → keep the picker, refresh the times, "pick another."**
   Approve/feedback have no 409 path, so there it's simply 410 → dead, else retry.
2. **M8 frontend is a no-op** (see table) — recorded so the wave reads as complete, not skipped.
3. **Aurora-gated flow tests were added but not run here** (no Aurora env). They execute on the
   founder's live-gate run; the runnable proof this session is the **7 non-Aurora units** (all green).

### 7.4 · Not in this wave / next

- **M22-doc** (the "Brief/ICP open to all members — document as deliberate" note) is a §6 Wave-2
  item, not P2 — deferred with the rest of Wave 2.
- **Remaining to close Wave 1:** founder-authorized `git` commit + push to `dev` (Amplify autobuild),
  then the standing live smoke. Suggested first commit = the whole wave on a `hardening-m-wave`
  branch off `dev` (the §5 "start with BE, pause for sign-off" split is now moot — all 10 are built
  and green together).
