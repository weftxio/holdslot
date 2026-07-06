# HoldSlot — Initial Build Plan (dogfood MVP)

> **Stop buying sales tools. Start buying meetings.** Done-for-you, pay-per-qualified-meeting B2B outbound.
> This plan is the **dogfood MVP**: the single-tenant outbound → booked-meeting loop, pointed at HoldSlot's
> own market, so HoldSlot sells itself. Scoped cut of the full spec in
> [`backend-development-plan.md`](backend-development-plan.md).

> **Status (2026-07-06): A–D BUILT & LIVE on `dev`.** Backend **Lambda v59** (deployed) · Aurora
> **head `0018`** (20 tables) · web **Amplify `dev`**. The Apollo **find → score → select → enrich →
> batch → masked client-approval** loop is live end-to-end. Latest (2026-07-06, this push): **multi-ICP
> scoping** — **ResearchSpec v5** emits one targeting block PER ICP (the v3 single-block contract was
> why a 2nd ICP crashed Regenerate Scope), find-company/find-people run ICP by ICP, ICP labels + filters
> across both prospect tables — and the **funding/jobs-posted date windows removed end-to-end** (they
> silently over-constrained every company search). Prior pushes (v55–v56, live): stage-0 business-model
> classifier, B2B/B2C market gate, thinking-OFF fit scoring, async-scoring zombie reaper. **Next: Phase E
> (outreach + Smartlead)** — gated on warmed inboxes (warm-up running since 2026-06-17). The only thing
> left on A–D is the three **founder operational acceptance rounds** (S1/S2/S3).

**Source-of-truth split (read these for depth; this doc is the plan, not the spec):**
- **Schema** — [`data-schema.md`](data-schema.md) governs every table/column (Apollo contract + all 20 DB tables, head `0018`). Update it first on any schema change.
- **Full spec** — [`backend-development-plan.md`](backend-development-plan.md): architecture, domain model, stages S0–S7, cost/growth model.
- **Live API** — `/docs` (Swagger) on `api.tryholdslot.com` is the authoritative endpoint inventory.

---

## Scope & Definition of Done

- **Scope:** the single-tenant outbound → booked-meeting loop. **HoldSlot is tenant #0.** Defer all
  multi-client *operations* (onboarding, self-signup, billing, analytics) — but **design the schema
  multi-tenant + role-aware from day 0** (every row carries `tenant_id`; one central access guard). *Build
  single; design multi.*
- **DoD:** land **6 signups in H1 (Oct'26 → Mar'27)** — the dogfood run *is* H1.
- **Timeline:** build → Sept'26 (~4 mo); loop runs live Oct'26 → Mar'27.
- **The long pole is not code:** cold-email **domain warm-up (~3 weeks)** gates every meeting — started
  **2026-06-17**. All external keys provisioned + verified 2026-06-10.

---

## Roadmap (A → G)

| Ph | Stage | Status | Builds | Dep | Gate to tick / DoD |
|---|---|---|---|---|---|
| **A** | S0 Foundation | ✅ **live** | Founder login (JWT), seed tenant #0, multi-tenant + role schema, Aurora + deploy, console on live data | — | ✅ both founders log in; schema admits a 2nd tenant/role w/o migration |
| **B** | S1 Targeting | ✅ **live** | Brief → OpenRouter **ResearchSpec v5** (async, **per-ICP** targeting blocks, date-window-free) + ICP profiles | A | ⏳ **S1**: founder Brief→Scope round on dev |
| **C** | S2 Prospects+Apollo | ✅ **live** | Apollo find → fit-score → select → enrich loop, in-app, no CSV (C0–C10) | B · Apollo | ⏳ **S2**: founder live Apollo round |
| **D** | S3 Batch+Approval | ✅ **live** | Batch → masked tokenized approval link → record decision; delete / re-send-reopen / attendee dropdown | C | ⏳ **S3**: founder live batch round (create→send→approve) |
| **E** | S4/S5 Outreach | ⬜ **planned** | Approved batch → Smartlead campaign, A/B/C, webhook funnel, cross-campaign Reply Queue, reply-to-thread | D · warm domains · Smartlead | Live sending; replies triaged in one queue |
| **F** | S6 Book+Meeting | ⬜ **planned** | Booking link → Calendar/Meet event + invites; held+duration; qualify rule | E · Google | Prospect self-books; held/duration recorded; auto-qualify |
| **G** | Run & close | ⬜ **human** | Meeting → pitch live product → close → onboard signup (= new tenant, reuse A) | F | **6 signups over H1** |

**Critical path:** A → B → C → D → E → F → G.
**Parallel since day 0:** domain warm-up (started 2026-06-17, the schedule driver) · keys (done 2026-06-10) · ICP + cold-email copy.
**Simplification principle:** one env (`dev`) to start (Terraform is workspace-parameterised → prod is a new workspace, not a rewrite); one modular FastAPI service; manual one-command deploy; JWT auth. Never shortcut: `tenant_id` on every row + one central access guard.

---

## Current state snapshot

| Thing | State |
|---|---|
| Backend | **Lambda v59** (alias `live`), `api.tryholdslot.com`, **47+ endpoints** across `auth·clients·briefs·icps·prospects·batches·approvals` |
| Database | Aurora Serverless v2 + Data API · **head `0018`** · **20 tables** (verified live 2026-07-06) |
| Web | Amplify `dev` (autoBuild on this push); `main`/`tryholdslot.com` points at the **dev** API/DB until prod cutover |
| LLM | OpenRouter, non-US providers only (HK geo-block) — scoping + fit = `deepseek/deepseek-v4-pro`, both async/background |
| Deploy | `apps/api/scripts/build-and-deploy.sh` (build → publish version → SnapStart wait → shift `live`); Amplify autoBuild on push to `dev`/`main`; **backend-before-frontend** |
| Gate left on A–D | the 3 founder operational rounds (S1/S2/S3) — infra is live |

---

## Built phases A–D — digest (deep detail → code + `data-schema.md`)

| Ph | Key sub-stages (all ✅ live) | Net result |
|---|---|---|
| **A** | A0 inputs · A1 scaffold · A2 Terraform (Aurora+DataAPI, Lambda+SnapStart, IAM, SES, budget) · **A3 schema+seed** · A4 JWT + central guard + auth/clients API · A5 live-auth UI · A6 acceptance | Observable, cold-start-resilient foundation |
| **B** | B0 OpenRouter gate · B1–B4 brief/ICP/spec/LLM-adapter (`llm_call` telemetry) · B5 FE · **B6 ResearchSpec v3 (Apollo-native) + async structuring** (`research_job`) | Brief→spec is deterministic into Apollo, off the 30s cap |
| **C** | C0 Apollo gate · C1–C6 model/transport/`apollo_map`/FlowA/FlowB/FE · **C7 lookalike + async scoring · C8 persona facets · C9 persisted people-scope · C10 fit-rubric split** (`company_fit`+`prospect_fit`) | Live find→enrich MVP; people search 0 cr, enrich is the only spend |
| **W0–W8** | enrich double-spend fix · perf indexes (`0014`) · **async scoring** (`scoring_job`, `0015`, 5 surfaces) · cursor pagination · login cold-start retry · LLM token trim · warm-container caching | A–C hardened — no new product scope |
| **D** | D1 schema (`0016`) · D2 `domains/batches` · D3 template+send · **D4 masked external `domains/approvals`** · D5 FE · D6 tests · +06-30 review-hardening · +07-01 refinements | Masked approval loop; `prospect_approval` = append-only billing evidence |

**Phase D feature set (as shipped):** Sendout Batch tab (do-not-contact list from Brief · derived counts · expandable company-grouped detail · Send/Follow-Up/Re-send via Brief attendee-email dropdown · re-send reopens a rejected batch · modal-confirmed delete that FK-cascades approval records) · List-approval tab (live chips · per-tenant sendout-template editor · status log) · external `approve/[token]` (masked fit-context-only list · per-prospect Reject/Undo · single adaptive CTA "Approve N & start outreach" / "Reject the list" · valid/success/expired panes). Backend: `domains/batches` (JWT+owner) + `domains/approvals` (public token-only, the masking allow-list serializer + atomic single-use decide). **Schema + masking spec: [`data-schema.md`](data-schema.md) → Phase D.**

---

## Phase B/C refinement — partner feedback (2026-07): B2B/B2C targeting + Asia depth

Partner review of B/C raised two issues: **(1)** exclude B2C / direct-to-consumer companies (e.g. the
HK/SG/TH digital insurers surfacing today) — irrelevant to a B2B client; **(2)** Apollo's *Find People*
under-surfaces the right **Asia** targets.

**(1) B2B/B2C exclusion — ✅ BUILT & LIVE (code-only, no migration).** Apollo's API has **no** B2B/B2C
search filter (UI-only, beta) and **no** exclude-industry param — so exclusion lives in *our* pipeline, at
the company tier, **before the only paid step (enrich)**:

| Piece | What |
|---|---|
| Brief | new **`targetMarket`** field (B2B / B2C / Both; opaque `brief.data` JSONB → **no migration**); required, reaches the scorer via `_SCORING_BRIEF_FIELDS` |
| Business-model classifier | The **`business_model`** label (B2B / B2C / **Complex** / Unknown — `Complex` = marketplace / B2B2C / platform serving both sides, e.g. Amazon) is set by a **dedicated stage-0 call** (`company_model` purpose · its own minimal split prompt — no rubric, no targeting, single-enum output, DeepSeek V4 Pro thinking-OFF) run at **find / lookalike / manual-add** time, so EVERY row is labelled BEFORE any (on-demand, paid) AI scoring — not just scored rows (2026-07-01 split out of `company_fit`). Judged from description/industries/keywords — Apollo's own recommended method (a post-search LLM *label*, not a filter). Token-minimal, so the extra call is cheap. Stored in `company.fit_components` + surfaced as the Step-1 model chip. `company_fit` no longer classifies — it just reads the stored label. |
| Hard gate | `targetMarket` vs `business_model` mismatch (only when **both** are a clean B2B/B2C, e.g. B2B client × B2C company) → force `fit_score = 0` / tier **Below** + stamped reason, `market_excluded` stored for audit + surfaced on `CompanyOut`. Now fires at **find/classify time** (opposite-market rows are buried into Below·0 up-front, before scoring — never consuming a paid score); `company_fit` re-applies it from the stored label so a re-score can't un-exclude. `Complex` / `Unknown` / `Both` / absent **never gate**. Gated companies are never selected for people-search → **no contact sourced, no enrich spend**, and the Step-1 table **pins them to the bottom regardless of sort** (+ a Step-1 **Business-model filter** and a **Pending · unscored** fit filter). |

**Fit-scoring hardening shipped alongside (2026-07):**
- **Thinking OFF on both stages** (`company_fit` + `prospect_fit`). Telemetry showed the reasoning trace was
  ~98% of a `company_fit` call's output and drove ~50s (p95 137s) latency + the batch timeouts. A/B on the 15
  live companies: **~12× faster, ~34× fewer tokens, ~34% cheaper**, quality sanity-passed (the B2C gate caught
  all 8 insurers; DeepSeek's structured-output grid is *cleaner* without the trace). Knobs live in
  `fit.COMPANY_FIT_EXTRA_BODY` / `PROSPECT_FIT_EXTRA_BODY`.
- **Async-scoring zombie reaper.** A worker hard-killed by the Lambda timeout used to leave its `scoring_job`
  `running` forever — wedging the surface (enqueue coalesces onto it). Fixed three ways: (a) a **reaper**
  (`scoring.MAX_JOB_AGE_SECONDS = 360`) flips any non-terminal job older than a worker could live → `error` on
  every read/enqueue; (b) the selection batch is capped to **one concurrent wave** (`ASYNC_BATCH_MAX =
  _SCORE_WORKERS = 15`, was 20 → 2 waves); (c) the Lambda **timeout is 300s** (`lambda.tf`, applied). No
  migration.

**(2) Asia depth — PLANNED (additive fallback + bake-off).** Research verdict: **no single DB exceeds ~35%
APAC accuracy; a provider waterfall is the standard APAC play.** Apollo is strong in **Singapore / Philippines**,
weakest in **Thailand / Vietnam** — a *recall* gap, worsened by over-narrow search (verified-email + revenue
filters that are sparse in Asia). Since the company is *already* selected from Apollo, the fix is **purely
additive at Flow B / enrich**: a second data adapter behind the existing `integrations/` seam, fired only when
Apollo returns no verified contact (or the company sits in an APAC-thin country). No change to discovery,
scoring, or the B2C gate.

| Decision | Verdict |
|---|---|
| A single "Asia silver-bullet" source | ❌ none exists (>35% cap) — **fallback/waterfall** is the pattern |
| Recommended secondary (APAC-native) | **AroundDeal** — 29M+ APAC incl. **Thailand**; API maps **1:1** (company-scoped contact search + people-enrich at **1 cr / verified email**, same model as Apollo); **$49/mo** self-serve, no lock-in |
| Alternatives | SMARTe (APAC phone, enterprise) · ContactOut (SG + personal email) · FullEnrich (one-API waterfall, APAC 50–60%). ~~Cognism~~ (EMEA-first, costly) · ~~Proxycurl~~ (service shut down) |
| Choose on evidence | 1-day **bake-off**: same HK/SG/TH companies through Apollo *vs* AroundDeal → measure contacts/company + verified-email rate **per country**; set the fallback trigger + order from the numbers |
| Also broaden Apollo for Asia | relax `email_status = verified` at search time · drop `revenue_range` for APAC · broaden-on-empty retry in Flow B (people search is 0 cr) — **measure the funnel first** |

**Principle:** Apollo's API can't exclude, so being surgical *in the query* both lets B2C in *and* starves Asia
recall. Invert it — **search wide in Apollo, exclude precisely in our own pipeline (the B2C gate), and fall
back to an APAC-native source for contacts.** **Compliance is a green light:** B2B cold email to corporate
addresses is permitted in **SG (PDPA) · HK (PDPO/UEMO) · TH (PDPA)** — business contact info is carved out of
personal-data consent given lawful sourcing + sender ID + purpose + working opt-out (SG: unsub ≤ 5 days); favour
lawfully-sourced DBs (AroundDeal / SMARTe / Apollo) over pure LinkedIn-scrapers.

---

## Multi-ICP scoping + spec v5 — founder feedback (2026-07-06): ✅ BUILT

Founder test: a second ICP broke Regenerate Scope. **Root cause was structural, not a glitch** —
the ResearchSpec **v3** contract held exactly ONE `company_search_params` + ONE
`people_search_params` per tenant while the scoping worker fed ALL ICPs into one prompt, so with
two divergent ICPs the LLM had to **merge** them (Apollo ANDs across facets → over-constrained to
zero, or ORed mush), **drop one** (the founder's "could not pick up the second"), or emit an
off-contract shape that failed strict validation (the "crash"). Everything downstream was already
ICP-aware (`icp_id` FKs on company/prospect/research_run, per-ICP fit targeting + `avoidTitles`,
`icp_docs` narrowing, `fIcp` state in the list page) — the spec was the only missing link.

**Design chosen: ONE LLM call with an array-of-blocks schema** — rejected alternatives: one call
per ICP (N× cost + N× ~60–76s latency, Job 3's web-search re-runs) and one spec ROW per ICP
(migration + N jobs + poll-contract rework). The strict schema makes "one block per ICP" a
*contract*, so the original bug is structurally impossible to recur; a model echo-typo on `icp_id`
is repaired by name match, and a genuinely missed ICP fails the job **by name** — never silently.

| Piece | What shipped |
|---|---|
| **ResearchSpec v4→v5** | `spec.icp_targeting[]` — **one Apollo block per ICP** (`icp_id`/`icp_name` echoed + company/people/intent params), emitted in ONE LLM call (Job 3 still runs once). `reconcile_icp_targeting` verifies coverage post-call. No schema migration — `spec` is JSONB, append-only versioned (same as v2→v3). **v5** (same day, founder feedback) then **removed the funding/jobs-posted date windows entirely** — they silently over-constrained every company search; intent = `q_organization_job_titles` (hiring signal) only. Prompt bumped **brief-structure-v6 → v7**; data-only migrations **`0017`/`0018`** re-seed the `briefing` prompt for tenants still on a shipped default (custom edits untouched — gotcha: Postgres `trim()` strips spaces only, so the match uses `btrim(body, ' \t\r\n')`). `map_company_filter` **never forwards the date fields** even when present, killing them from old specs + stale overrides too. |
| **One spec reader** | `targeting_for_icp(spec, icp_id)` — find-company resolves the picked ICP's block (multi-ICP + no/unknown ICP → 400, never a silent merge; single-block resolves + labels automatically); find-people resolves **per company** from `company.icp_id` (a mixed selection searches ICP by ICP in one call); fit scoring slices the row's own block into the v3 shape the rubrics read (fewer tokens, sharper targeting). **v3 specs keep working** via the fallback until the next regenerate — backend deploys first with zero downtime. |
| **UI** | Prospect Scope panel: per-ICP **coverage chips** + an **ICP dropdown** next to View prompt (drives the rendered block AND the prompt preview's `?icp_id=` input); gaps carry their ICP tag; legacy/missing-scope callouts. Prospect list: **ICP dropdown** (both stages — filters the tables AND picks the Find Company target; single ICP auto-picked, multi without a pick = guard toast + warn flash mirroring the server 400), **ICP badge under the company name** in both tables, Find-Settings modal gets an **ICP switcher** seeding from that ICP's block (override saved per ICP in localStorage, legacy key read as fallback). |
| **Job hygiene** | The `research_job` **zombie reaper** (`MAX_JOB_AGE_SECONDS=360`, same pattern as scoring) — a worker killed mid-run no longer wedges the brief page in "Generating…" forever; stale jobs flip to a named timeout error on read/enqueue. |

Out of scope (follow-ups): per-ICP *persisted* scope overrides in the DB (`by_icp` keying, no
migration needed) · per-ICP partial regenerate · auto-seeding a block when a suggested ICP is
accepted · ICP-level credit budgets.

---

## Scope lineage — link every find result to its exact Apollo filters (DESIGN LOCKED · not built)

Founder ask: *"link back each generated result in step 1 find company setting apollo API filter
parameter"* — today the forward chain (spec → find) is solid but the backward chain leaks: a
localStorage override or a find-people relax level changes *what was sent* without any record.
Design locked 2026-07-06 (v2, simplified — run snapshots alone satisfy every requirement; moving
overrides into the DB was dropped as a dependency and deferred). **~half a day when green-lit.**

- **Schema (next free migration, `0019`):** `research_run` gains `filter_body` JSONB (the exact
  `mixed_companies/search` body; find-people stores `{"per_org": {domain: {body, relax}}}`, ≤8
  orgs/run) + `scope_source` varchar(16) (`ai` · `custom` = any operator-supplied params · `lookalike`
  · NULL for non-Apollo runs). No other table changes.
- **Backend (one concept — snapshot at the moment of send):** `_run_company_find` already receives
  the final body — thread `{filter_body, scope_source}` into its `ResearchRun` insert; find-people
  collects per-org body + relax in its existing loop; expose `icp_id`/`icp_name`/`scope_source`/
  `filter_body` on `ResearchRunOut`.
- **Frontend:** a **Find history drawer** on the Prospect list (read side of the existing but
  UI-orphaned `/research-runs` endpoint) — when · source · ICP badge · `spec vN` · `ai/custom` chip ·
  rows found · cost, with a per-row "View filters" popover (`scopeSummary()` humanizer + raw-JSON
  toggle). Plus an **honest Find-Settings badge**: `AI scope · v<N> · <ICP>` vs `custom · saved`.
- **Why this design:** the snapshot records the **executed** body, so it is override-proof (AI
  block, saved tuning, or one-off edit — lineage is identical) and absorbs the deferred DB-override
  follow-up with zero migration rework.

---

## Locked context you MUST carry (non-obvious; carry into every phase)

| Topic | Rule |
|---|---|
| **OpenRouter HK geo-block** | OpenAI / Anthropic / Google providers return **403 ToS** for this account (Hong Kong), account-wide. **Route every LLM call to non-US providers only** (DeepSeek / Qwen / Mistral; Llama dropped 2026-06-22). Scoping = `deepseek/deepseek-v4-pro` (thinking + web-search, ~55–76s) on the **async** path — exceeds the 30s API-GW sync cap. Fit scoring = `deepseek/deepseek-v4-pro` **thinking OFF** on both stages (`company_fit` + `prospect_fit`; A/B'd 2026-07 — the trace was ~98% of output and drove the timeouts) at `temperature=0`; still runs in the **background** via `scoring_job` (never on the find request). |
| **Apollo credits** | **People search (`mixed_people/api_search`) = 0 credits** (no email/phone, needs master key). **`people/match` = the spend: 1 cr/email** (8/phone, `PHONE_ENABLED=false`), human-gated at Gate 2. **Company search** looks request-metered (50k/day) but Apollo's current docs list it as credit-consuming — *founder dashboard glance to confirm $-cost.* Never `people/match` before Gate 2; suppression/exclusions are DB-side. |
| **Ops** | AWS uses `AWS_PROFILE=holdslot` (acct **138743894336**), never the default. `claude_code` IAM is **read-only** on `holdslot/prod/*` (founder writes all secrets). Deploy = `build-and-deploy.sh`. **git push needs the `weftxio` gh account** (`checkafy` lacks write). **Commit/push only when asked.** |
| **Posture** | Build single / design multi · **zero new AWS resources** added through D (every route rides the `$default` proxy) · token validity is **expiry-on-read, no scheduler** (mirrors `password_reset`) · webhook ingest (E) = **synchronous insert** at dogfood volume. |

---

## Phase E — Outreach + Smartlead (S4/S5) — NEXT

Turns an **approved batch** into a live Smartlead cold-email campaign and makes the **Campaign** tab real: a
7-stage funnel (*Initial outreach → Follow-up → Positive reply → Meeting → No show → Qualified billable →
Drop*), each sending stage carrying **A/B/C variants** with live open/reply metrics, plus a **cross-campaign
Reply Queue**. E lights the top half (outreach→reply→drop) + KPI plumbing; **F lights** the meeting half.
**Posture:** Smartlead = the dumb sender, we own funnel state; webhook ingest = sync insert, **zero new AWS
resources** ([SCALE] = SQS+worker at volume). Reply classification is **human, not LLM**, at MVP.

| Task | What | Flag |
|---|---|---|
| **E0** | Gates (no code): **warmed inboxes ⭐** (running since 06-17, ~early Jul'26) · Smartlead secret (`webhook_signing_secret` + `sending_account_ids`) · A/B/C copy + sequence authored · compliance (unsub/suppression/CAN-SPAM/GDPR/HK-PDPO) | schedule risk |
| **E1** | Schema: `campaign` · `message_variant` (A/B/C, open/reply, `is_winner`) · `campaign_lead` (**`stage`** = funnel SoT) · `outreach_event` (conversation-log source + stage driver) | dedupe on Smartlead event id |
| **E2** | Smartlead adapter ⭐ (lazy/SnapStart-safe): create campaign · add leads · A/B/C sequence · start/pause/resume · **reply-to-thread** (master inbox) · register webhook | |
| **E3** | "Confirm & lock" → `POST /campaigns` (idempotent on `batch_id`) → create campaign → add leads (chosen variant) → push sequence → start (respects daily caps) | ⭐ |
| **E4** | Webhook ingest → `outreach_event` → advance stage ⭐. `LEAD_OPENED`→variant count · `LEAD_REPLIED`→log+flag · `UNSUBSCRIBED`/`BOUNCED`/neg→drop. **No `EMAIL_SENT` event** → derive contacted/followup server-side. Capture `reply_message_id` for threading | ⭐ |
| **E5** | Reply Queue — cross-campaign triage inbox ⭐ (read over `outreach_event`+`campaign_lead`; filters: campaign / triage state) | ⭐ |
| **E6** | Reply-to-thread (send booking msg back into the thread) + per-variant open/reply scoreboard + `is_winner` | |
| **E7** | Wire Campaign tab + Reply Queue + acceptance → tick **S4/S5** (replaces mocks `SAMPLE_FUNNEL`/`INITIAL_REPLIES`/`RECAPS`; `replied→meeting` calls the F3 Meet hook) | |

**Funnel ↔ Smartlead:** `contacted` = lead-add 200 + sequence start (derived; no send-webhook) · `followup` = derived from elapsed steps · `replied` = `LEAD_REPLIED` + founder classifies positive · `drop` = `LEAD_REPLIED`(neg)/`UNSUBSCRIBED`/`BOUNCED`. **Verified campaign-webhook events:** `LEAD_REPLIED·OPENED·CLICKED·BOUNCED·UNSUBSCRIBED` (auth = `?api_key=` query param, V1 paths).

**Integration risks (confirm at E0):** **R1** Smartlead auth is query-param `api_key` only → keep out of logs. **R2** no documented webhook HMAC → defend with high-entropy secret-path token + re-fetch-before-mutate. **R3** no `EMAIL_SENT` event → derive sent/followup server-side. **R4** reply-to-thread needs the captured `reply_message_id`. **R5** A/B variants are sequence-step-scoped, not stage-scoped (booking/drop replies are manual threaded, HoldSlot-tracked). **R6** only Email is Smartlead-fed (LinkedIn=[SKIP], Calendar=F, Stripe=G). **R7** daily send caps vs warm-up ramp — surface the schedule, don't imply instant send.

**Path:** E0(inboxes) → E1 → E2 → E3 → E4 → {E5·E6} → E7. **E3/E4 = highest-leverage code; E5 = where the founder works replies.** **Cost:** Smartlead Basic **$32/mo**; no LLM in E at MVP.

---

## Phase F — Book + meeting (S6 min)

Lights the funnel's bottom half by making booking + the meeting real (Calendar event + Meet link + invites;
held + duration via **Meet REST v2**) and wiring the two terminal stages to the *Billing ledger* + *Meeting
recaps* tabs. **Locked billing rule (the hinge):** a meeting is **Qualified billable iff (a) the prospect has
a client approval AND (b) Meet metadata shows held ≥ 10 min** — else **No show**. **Posture:** build the
meeting connection + data seam; **defer Stripe + LLM recaps** ([SKIP→later]) — the "$X · Stripe" chip is a
computed amount, not a charge, until G.

| Task | What | Flag |
|---|---|---|
| **F0** | Gates: Google Workspace + Meet REST conference-records scope · booking-link lifetime/reminders · qualified-meeting def reconfirmed | |
| **F1** | Schema: `booking_link` · `meeting` (`google_event_id`, `meet_link`, `scheduled_at`, `held`, `duration_min`, **`conference_record_id`**, **`qualified`**, **`amount`**, outcome) | |
| **F2** | Google adapter: create Calendar event + Meet link + invites; read Meet REST v2 conference records (held/duration/attendees) | |
| **F3** | Booking link → event → `stage=meeting`. **Same hook fires on the funnel `replied→meeting` stage-move** (Calendar `events.insert`, `conferenceDataVersion=1`, `hangoutsMeet`, `sendUpdates=all`) — one code path | |
| **F4** | Held+duration → qualify ⭐: **approved AND held ≥10 min → `qualified`, `stage=billable`** + compute `amount` (§7); else `noshow`. Idempotent on re-poll | ⭐ |
| **F5** | Ledger + Recaps seam (rows now; **Stripe push + LLM `meeting_summary` = SKIP→later**). Recaps shows **Upcoming** (`held IS NULL AND scheduled_at>=now`, Meet join link) + **Past** (held=true). `GET /meetings?when=upcoming\|past` | |
| **F6** | Wire Workspace + acceptance → tick **S6** (+ read-only **S7**) | |

**One `meeting` row feeds three surfaces:** Campaign funnel (stage), Billing ledger (qualified/amount/won-lost; Stripe later), Meeting recaps (upcoming + past; LLM summary later). **Path:** F0→…→F6. **F4 = highest-leverage** (the one billing rule). **Cost:** Google Workspace ~**$15/mo**; $0 Stripe until G.

---

## Phase G — Run & close (human)

Work the live loop: meeting → pitch the live product (the product *is* the demo) → close → onboard signup
(= a new tenant, reuse A's `INSERT`). **DoD: 6 signups over H1.** No new build.

---

## Open gates & pending register

| Item | Ticks | Status |
|---|---|---|
| Founder Brief→Scope round (dev) | S1 | ⏳ operational |
| Founder live Apollo round (find→enrich→batch; reads real `cost_usd`) | S2 | ⏳ operational (+ optional Apollo credit-dashboard glance) |
| Founder live batch round (create→send masked link→approve) | S3 | ⏳ operational — infra live (0018 applied, v59) |
| Scope-lineage build (`research_run.filter_body` + Find-history drawer, §above) | — | design locked, awaiting go-ahead |
| Warmed inboxes ready (~early Jul'26) | E0 | running since 06-17 |
| **A follow-ups (non-blocking):** custom MAIL FROM ✅ (D0) · prod isolation deferred (Amplify `main`→dev until cutover) · manual deploy (CI/CD later) · Aurora scale-to-zero vs 30s timeout (prod sets min ACU ≥0.5) · S3 state bucket public-access-block (prod) · refresh-token rotation doesn't re-check `UserStatus` | — | tracked |
| **Deferred ICP inputs (search-side; already used for *scoring*):** `technologies`→Apollo tech-UIDs (no resolver) · `revenue_range` (no ICP form field) · funding-stage key unverified | — | post-MVP |
| **Backlog:** step-3 console decide UI (the `decide_batch` endpoint + `decideBatch` client fn exist, tested; no UI) · `person` enrich-once cache (lands with tenant #2) · move `reloadBatches` onto the TanStack-Query cache | — | optional |

---

## After A–G complete

- **Production isolation** (cutover, not rewrite — Terraform is workspace-parameterised). `terraform workspace new prod` → `apply` → prod `aurora_min_acu ≥ 0.5` → fresh prod JWT keys → `alembic upgrade head` + seed → SES prod sandbox-exit → point Amplify `main` at prod → harden (S3 PAB, CI/CD). Trigger: Phase G DoD met.
- **LLM usage rollup** — aggregate `llm_call` across every phase/`purpose` into a tenant×purpose×model×month panel + spend alarm. `llm_call` stays the single source; the rollup is derived. Valuable only once calls span every phase.

---

## MVP running cost (actual plan prices)

| Item | Plan | $/mo |
|---|---|---|
| **Apollo** | Professional (master key) — ~50% of total, the lever | ~99 |
| **Smartlead** | Basic (warm-up free, both inboxes fit) | 32 |
| **Google Workspace** | 2 × Business Starter @ $7.20 | 14 |
| **OpenRouter** | pay-per-use (Brief→spec, fit, drafts) | ~5–30 |
| **Aurora SLv2** | min ACU (near-$0 idle) | ~5–30 |
| Lambda · API GW · SES · S3 · SSM · EventBridge · CloudWatch · R53 · Amplify · domain | | ~4–11 |

**Total: ~$195/mo typical** (low ~$160, high ~$235; ≈1,520 HKD). **Honest floor before Apollo Pro** (warm-up phase, no live sourcing): **~$55–65/mo.** Apollo is the cost lever — cap company search with `max_results`, reuse cached rows, enrich only the selected set, phone off.

---

## Accounts, keys & sending infrastructure

**Secrets** in AWS Secrets Manager (`138743894336`), one JSON per platform under `holdslot/prod/*`; verified by [`verify_keys.py`](../apps/api/scripts/verify_keys.py) (`--strict` at the phase that needs them).

| Secret | Status | Confirms |
|---|---|---|
| `holdslot/prod/app` | ✅ | JWT signing+refresh, ≥32 chars, distinct |
| `holdslot/prod/openrouter` | ✅ | key valid; $50 cap; **non-US models only** (each call site pins its own list) |
| `holdslot/prod/apollo` | ✅ | **Professional + master key**; all 3 endpoints 200 |
| `holdslot/prod/smartlead` | ◑ | `api_key` valid; `webhook_signing_secret` + `sending_account_ids` → **E** |
| `holdslot/prod/google` | ✅ | SA + domain-wide delegation + Calendar + Meet REST all 200 |

**Sending infra (the long pole, gates E):** Smartlead-native warm-up + Google Workspace mailboxes on a
dedicated lookalike domain **`getholdslot.com`** (cold mail never goes from `tryholdslot.com`). 2 mailboxes
(`jason.tse@`, `jason.wong@`), all DNS verified (MX/SPF/DKIM/DMARC), Smartlead warm-up enabled (40/day ceiling,
+5/day ramp). **Clock: started 2026-06-17** → first real sends ~early Jul'26 (5–10/inbox/day → ~25). MVP =
**one domain** ([SCALE] adds a 2nd). Still to do: do-not-email suppression list · A/B/C copy (before week-3 sends).

---

## API surface (live · Lambda v59)

Auth = JWT Bearer; tenant scope via `require_membership()` on every `/{client}/…` route (non-members → **404**).
`+Owner` = owner-gated. Live inventory at **`/docs`**. Routers + the routes that matter per phase:

| Router | Routes (key) |
|---|---|
| `auth` | `POST /auth/{login,refresh,forgot,reset}` (public) |
| `clients` | `GET /me·/clients` · `POST /clients` · `GET /{client}/context` |
| `briefs` | brief GET/PUT · `POST /{client}/brief/structure` (async) + status/preview · `GET /research-spec` |
| `icps` | CRUD `/{client}/icps` |
| `prospects` | **(largest, ~29)** list `/prospects`·`/companies` (cursor ≤250) · `find-company`·`find-lookalikes`·`select`·`rescore`·`update-fields` · `find-people`·`facets`·`scope-override` · **`enrich` (only credit spend)** · 6 `…-async` scoring + poll · `research-runs` · `sourcing-docs` (rubrics) |
| `batches` (**D**) | `GET/POST /{client}/batches` · `GET /{id}` (company-grouped) · `POST /{id}/decide` (owner step-3) · `DELETE /{id}` (cascade) · `GET/PUT /approval-template` · `POST /{id}/send` (mint link + SES) |
| `approvals` (**D**, public token-only) | `GET /approve/{token}` (masked) · `POST /approve/{token}/decide` |
