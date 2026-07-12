# HoldSlot — Initial Build Plan (dogfood MVP)

> **Stop buying sales tools. Start buying meetings.** Done-for-you, pay-per-qualified-meeting B2B outbound.
> This plan is the **dogfood MVP**: the single-tenant outbound → booked-meeting loop, pointed at HoldSlot's
> own market, so HoldSlot sells itself. Scoped cut of the full spec in
> [`backend-development-plan.md`](backend-development-plan.md).

> **Status (2026-07-12): A–E SHIPPED (A–D+ dev AND prod; E dev).** Aurora **head `0029` applied** · backend Lambda
> **v86** on the one shared backend (`api.tryholdslot.com`; find-path Stages 1–4 +
> Scoring v2 + **V2-4 contraction** + classifier→Flash) · web on **both Amplify branches at `b36b61d`**
> (dev job 53 · prod job 20 — the **first public prod-FE release**, 2026-07-11; `tryholdslot.com` rides the
> shared dev-tier backend until the prod cutover). The Apollo **find → score → select → enrich → batch → masked
> client-approval** loop is live end-to-end. **Phase D+** (the pre-E hardening block — §below) folds three
> workstreams into one: **scope alignment** (sourcing width, Stages 1–4), **Scoring v2** (the 0–100 AI Score
> replaced by 4 labels `contact_now`/`contact_soon`/`low_fit`/`excluded_by_rules` + a liveness gate — this
> doc now carries the whole spec, the standalone `holdslot-scoring-spec-v2.md` was folded in + deleted; **V2-4
> retired the v1 `fit_score`/`fit_tier` path entirely** — 5 sync twin endpoints + the v1 fit module deleted,
> columns dropped in `0026`), and the **Find-flow UX rebuild** (U1–U4 + the merged **Reveal & score** action).
> **The A→D+ review cycle is CLOSED** — nothing left in the fix backlog; both hardening waves are **DONE +
> deployed**. The **§D+.5 code-review fix wave** (executed 2026-07-10 across F1–F7; all 31 resolved bar
> R21/R27-queries/R30-tests) and the **final pre-production review (2026-07-11)** — 56 findings (3 P1 · 19 P2
> · 34 P3), phases **G1–G7** — are built, committed, and **deployed across two pushes** (dev Lambda **v78** +
> migration **`0027`** applied + Amplify dev job 52), followed by the **close-out push** (Lambda **v79** ·
> Step-2 trigger-line unrendered · wheel-only compile · docs consolidation) that shipped **dev + prod**; see
> **§D+.6** below (both `final-fix-plan.md` and
> `prod-cutover-checklist.md` were folded in here + deleted). The **Q7 re-score candidate list is empty**
> (confirmed 2026-07-11 against dev Aurora — 0 geo-excluded rows; the one divergence-prone tenant has 0
> companies; no data remediation needed). Only the **prod-cutover register** (deferred infra hardening —
> §After A–G) remains. **Phase E is BUILT + E0-probe CLOSED + SHIPPED (2026-07-12)** — commit `d8aef2b` ·
> Lambda **v86** · Amplify dev **job 55**; `0028`+`0029` applied; all 5 Smartlead webhook payloads captured
> live + all 3 contract verdicts confirmed (5 adapter bugs the probe caught, all fixed) + the per-email
> unsubscribe link enforced; **only the founder S4/S5 acceptance run remains**.
> **Phase F (book + meeting + feedback) — 🟢 BUILT code-complete (2026-07-12)** — F1–F6 written, local
> gates green (backend `pytest` 336✓/22 Aurora-skipped · `ruff` clean · FE `tsc`+`eslint` clean); remaining
> = apply `0030` + push #1 deploy + F0 founder Meet + push #2 FE + FA acceptance (see the §Phase F BUILT
> callout). §Phase F below is the build plan + the researched execution sections (Google contract · FD
> defaults · seams · build table · **per-step test-case register** + FA acceptance)
> (**EF-Q9** places the last three mock console surfaces — performance-summary v1 rides E7, its meeting half +
> the client-status Booking/Feedback tabs land in F5/F6). The inbox warm-up (running since 2026-06-17) has
> **elapsed** — E0 confirmed warm-up health in-dashboard. S3 (batch round) is the only untouched A–D gate
> (S1/S2 folded into review #5 ✅).

**Source-of-truth split (read these for depth; this doc is the plan, not the spec):**
- **Schema** — [`data-schema.md`](data-schema.md) governs every table/column (Apollo contract + all DB tables, **head `0029` applied** — Phase E `0028` outreach + `0029` `sending_account`; **Phase F tables planned as `0030`**). Update it first on any schema change.
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
| **D+** | Sourcing + Scoring + UX | ✅ **shipped (dev + prod FE)** · re-score wave on demand | Scope alignment (Stages 1–4) + **Scoring v2** (4-label + liveness gate, v1 retired in V2-4) + **UX rebuild** (U1–U4 + Reveal & score) — migrations `0019`→`0027` | C · Apollo | KPI gate (≥3× rows/find · ≥2× `contact_now`+`contact_soon` share · <5% dupes) — review #5 ✅ |
| **E** | S4/S5 Outreach | 🟢 **built + SHIPPED (2026-07-12)** — commit `d8aef2b` · Lambda **v86** · Amplify dev job 55; `0028`+`0029` applied; E0 probe CLOSED (5 payloads real, 3 verdicts confirmed, unsub link enforced) · only the founder **acceptance run** remains | Approved batch → Smartlead campaign, A/B/C, webhook funnel, cross-campaign Reply Queue, reply-to-thread | D+ ✅ · warm domains (ramp elapsed — E0 confirms health) · Smartlead | Live sending; replies triaged in one queue |
| **F** | S6 Book+Meeting | ⬜ **planned — finalized 2026-07-11** | Booking link → Calendar/Meet event + invites; held+duration; qualify rule; feedback loop | E · Google | Prospect self-books; held/duration recorded; auto-qualify; ledger row lands |
| **G** | Run & close | ⬜ **human** | Meeting → pitch live product → close → onboard signup (= new tenant, reuse A) | F | **6 signups over H1** |

**Critical path:** A → B → C → D → **D+ (sourcing + scoring + UX)** → E → F → G.
**Parallel since day 0:** domain warm-up (started 2026-06-17, the schedule driver) · keys (done 2026-06-10) · ICP + cold-email copy.
**Simplification principle:** one env (`dev`) to start (Terraform is workspace-parameterised → prod is a new workspace, not a rewrite); one modular FastAPI service; manual one-command deploy; JWT auth. Never shortcut: `tenant_id` on every row + one central access guard.

---

## Current state snapshot

| Thing | State |
|---|---|
| Backend | Lambda **v86** alias `live` (2026-07-12), `api.tryholdslot.com` — the **one shared backend serving BOTH sites** until prod cutover; **~60 endpoints** across `auth·clients·briefs·icps·prospects·batches·approvals·campaigns·webhooks` |
| Database | Aurora Serverless v2 + Data API · **head `0029` applied** (`0028` Phase-E outreach + `0029` `sending_account`) |
| Web | Amplify autoBuild on push: **dev at `d8aef2b`** (job 55, Phase-E tabs live) · **prod at `b36b61d`** (job 20 — the first public prod-FE release, 2026-07-11). `main`/`tryholdslot.com` points at the **dev** API/DB until prod cutover |
| LLM | OpenRouter, non-US providers only (HK geo-block) — scoping + `company_score_v2` = `deepseek-v4-pro`; **stage-0 classifier = `deepseek-v4-flash`** (A/B-switched 2026-07-10); all async/background |
| Deploy | `apps/api/scripts/build-and-deploy.sh` (build → publish version → SnapStart wait → shift `live`); Amplify autoBuild on push to `dev`/`main`; **backend-before-frontend** |
| Gate left on A–D | S3 (founder batch round) — S1/S2 folded into D+ review #5 ✅ (2026-07-10) |

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
| Business-model classifier | The **`business_model`** label (B2B / B2C / **Complex** / Unknown — `Complex` = marketplace / B2B2C / platform serving both sides, e.g. Amazon) is set by a **dedicated stage-0 call** (`company_model` purpose · its own minimal split prompt — no rubric, no targeting; output = the enum + two description-derived facts `hq_country`/`has_b2b_line` since V2-1; **DeepSeek V4 Flash**, A/B-switched 2026-07-10 — §D+.4) run at **find / lookalike / manual-add** time, so EVERY row is labelled BEFORE any (on-demand, paid) AI scoring — not just scored rows (2026-07-01 split out of `company_fit`). Judged from description/industries/keywords — Apollo's own recommended method (a post-search LLM *label*, not a filter). Token-minimal, so the extra call is cheap. Stored in `company.fit_components` + surfaced as the Step-1 model chip. The paid scorer (`company_score_v2` since V2-4) never re-classifies — it reads the stored label. |
| Hard gate | `targetMarket` vs `business_model` mismatch (only when **both** are a clean B2B/B2C, e.g. B2B client × B2C company) → `label = excluded_by_rules` + stamped reason via `labeling.rules_gate` *(v2 — the v1 `fit_score = 0`/tier-Below/`market_excluded` columns were dropped in `0026`)*. Fires at **find/classify time** (opposite-market rows are labeled up-front, before scoring — never consuming a paid score); the rescore path re-applies it from the stored label so a re-score can't un-exclude. `Complex` / `Unknown` / `Both` / absent **never gate**. Gated companies are never selected for people-search → **no contact sourced, no enrich spend**; the Step-1 table collapses them into the `excluded_by_rules` bucket. |

**Fit-scoring hardening shipped alongside (2026-07):**
- **Thinking OFF on both stages** *(historical — v1 `company_fit`/`prospect_fit`)*. Telemetry showed the
  reasoning trace was ~98% of a `company_fit` call's output and drove ~50s (p95 137s) latency + the batch
  timeouts. A/B on the 15 live companies: **~12× faster, ~34× fewer tokens, ~34% cheaper**, quality
  sanity-passed. *Superseded by V2-4: the v1 stages + their `EXTRA_BODY` knobs are deleted; v2's knobs are
  `fit.COMPANY_SCORE_V2_EXTRA_BODY` (reasoning ON + web plugin) / `PROSPECT_SCORE_V2_EXTRA_BODY` (reasoning
  off — the A/B posture, kept).*
- **Async-scoring zombie reaper.** A worker hard-killed by the Lambda timeout used to leave its `scoring_job`
  `running` forever — wedging the surface (enqueue coalesces onto it). Fixed three ways: (a) a **reaper**
  (`scoring.MAX_JOB_AGE_SECONDS = 480`, raised from 360 in D+.5/R3 — ≥ 120s async-queue age + 300s run +
  buffer) flips any non-terminal job older than a worker could live → `error` on every read/enqueue; (b) the selection batch is capped to **one concurrent wave** (`ASYNC_BATCH_MAX =
  _SCORE_WORKERS = 15`, was 20 → 2 waves); (c) the Lambda **timeout is 300s** (`lambda.tf`, applied). No
  migration.

**(2) Asia depth — 2nd data source SKIPPED (decision 2026-07-08).** The research verdict stands (**no
single DB exceeds ~35% APAC accuracy; a waterfall is the standard APAC play**) but the recommended
secondary fell through: **AroundDeal's API is Enterprise-only (~$10k entry); the $49/mo plan has NO API**
— the earlier price read was wrong (their `/docs` page now 404s; endpoints/auth/credits/rate limits are
sales-gated). An 11-provider vetting (PDL · RocketReach · ContactOut · SMARTe · FullEnrich · Coresignal ·
Crustdata · Lusha · Adapt.io · Snov.io · APAC-native scan) found **no Apollo-like APAC-focused search API
at self-serve prices** — the market splits into APAC-strong-but-gated (AroundDeal, SMARTe, Ampliz) and
self-serve-but-US-skewed (PDL $98/mo, RocketReach ~$175/mo — real search APIs that duplicate Apollo's
APAC weakness rather than fixing it).

| Decision | Verdict |
|---|---|
| 2nd source now | ❌ **skipped** — no viable candidate at sane cost |
| **Unlock condition** | AroundDeal offers **monthly (non-enterprise) API pricing** → revive the provider-seam design. Verified adapter facts for that day: `company_search` (keyword · ISO country · numeric industry IDs · employee-range letter codes A–I; **size ≤ 10/page**; no stable company id → dedupe on website/LinkedIn) · company-scoped contacts = `company_contact_discovery` (domain/LinkedIn + function/job-level enums, returns emails) · `people_enrichment` ~1 cr/verified email · fixed enums need mapping tables |
| Non-blocking doors | **ContactOut / Adapt.io sales calls** (right API shape, price unknown, plausibly ≪$10k) · **FullEnrich** $69/mo enrich-only waterfall later (~1 day thin adapter at the enrich step — rescues emails for people already found; can**not** fix find-people recall) |
| Apollo-side Asia broadening | folded into the **D+ alignment build, Stage 2** (relax `email_status = verified` at search · drop `revenue_range` for APAC · broaden-on-empty in Flow B — people search is 0 cr) |

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
| **One spec reader** | `targeting_for_icp(spec, icp_id)` — find-company resolves the picked ICP's block (multi-ICP + no/unknown ICP → **400**, never a silent merge; single-block resolves + labels automatically); find-people resolves **per company** from `company.icp_id` (a mixed selection searches ICP by ICP in one call) and, for an **unknown-ICP company, deliberately falls back to `icp_targeting[0]`** — NOT a 400 — since people search is FREE and a reviewable near-miss beats a hard fail (R29e; the 400 is a find-**company** rule only); fit scoring slices the row's own block into the v3 shape the rubrics read (fewer tokens, sharper targeting). **v3 specs keep working** via the fallback until the next regenerate — backend deploys first with zero downtime. |
| **UI** | Prospect Scope panel: per-ICP **coverage chips** + an **ICP dropdown** next to View prompt (drives the rendered block AND the prompt preview's `?icp_id=` input); gaps carry their ICP tag; legacy/missing-scope callouts. Prospect list: **ICP dropdown** (both stages — filters the tables AND picks the Find Company target; single ICP auto-picked, multi without a pick = guard toast + warn flash mirroring the server 400), **ICP badge under the company name** in both tables, Find-Settings modal gets an **ICP switcher** seeding from that ICP's block (override saved per ICP in localStorage, legacy key read as fallback). |
| **Job hygiene** | The `research_job` **zombie reaper** (`MAX_JOB_AGE_SECONDS=480` — imported from `prospects/scoring` since D+.5/R3, one shared constant; same pattern as scoring) — a worker killed mid-run no longer wedges the brief page in "Generating…" forever; stale jobs flip to a named timeout error on read/enqueue. |

Follow-ups then out of scope: **per-ICP *persisted* scope overrides** (`by_icp` keying) — since **built
as D+ UX Stage U1** (§D+.3). Still deferred: per-ICP partial regenerate · auto-seeding a block when a
suggested ICP is accepted · ICP-level credit budgets.

---

## Phase D+ — Sourcing + Scoring + UX hardening (pre-E block) · one summary

D+ is the pre-Phase-E hardening block that fixes the one problem live B/C output exposed: **too few
rows, and the majority low-fit.** Three interlocking workstreams, all on the `dev` branch:

1. **Scope alignment** (Stages 1–4) — widen + ground the Apollo query so a find returns *more, better-targeted* rows. *Fixes "too few rows."*
2. **Scoring v2** (the 4-label system) — replace the 0–100 AI Score with `contact_now`/`contact_soon`/`low_fit`/`excluded_by_rules` + a **liveness gate**. *Fixes "which rows are actually good."* (This folds in the former `holdslot-scoring-spec-v2.md` — that file is now deleted; its core value lives in §D+.2 below.)
3. **Find-flow UX rebuild** (U1–U4 + Reveal & score) — reorder the toolbar to the funnel's cost gradient; merge the Step-2 reveal + score into one action.

**Sequencing (founder 2026-07-09):** the sourcing fix (1) and the scoring fix (2) deploy **together** and are reviewed in **one combined UAT round measured in labels** — the interim per-stage Strong+Good rounds were dropped (attribution of sourcing-fix vs scoring-fix is traded away for speed). The UX rebuild (3) rides the same review (#5). **Token posture across all of D+: zero new per-row LLM calls** — scoping stays ONE call per regenerate; probe/relax/cursor/resolvers/correlation are deterministic code; v2 swaps the old `company_fit` call 1:1 for the web-grounded `company_score_v2`, only on gate survivors; gated rows never reach paid scoring or enrich.

### D+ status at a glance (2026-07-10)

| Workstream | Piece | Status |
|---|---|---|
| **Scope 1** | 1a telemetry + safe widen (`0019` scope-lineage; `search_companies_meta` reads `total_entries`/`breadcrumbs` off the same fetch; `FIND_COMPANY_LIMIT` env cap, `_SCORE_WORKERS` decoupled) | ✅ **built + deployed** (dev) |
| **Scope 1** | 1b async find + fetch-then-relax company ladder + Find-history drawer + departments-param A/B (verdict: **FILTERS** — keep the `seniority×dept` rung) | ✅ **built + deployed** (dev) |
| **Scope 2** | Query = rubric — `person_titles[]` + `include_similar_titles`; titles-first people ladder (`titles_strict → titles_fuzzy → seniority×dept → seniority_only`); APAC revenue-drop (`_is_apac`); spec **v6** + prompt `brief-structure-v8` (`0020`) | ✅ **built + deployed** (dev) |
| **Scope 3** | Recycle negative signal — query-keyed **page cursor** (`_resume_page`, `scope_exhausted`) + **known-org skip** ($0 invariant) + negative-keyword feedback + `organization_not_locations` clustering; prompt `v9` (`0021`) | ✅ **built + deployed** (dev) |
| **Scope 4** | Vocabulary grounding — `tech_vocab` tech→UID resolver (`supported_technologies_csv`) → `currently_using`/`currently_not_using_any_of_technology_uids`; `keyword_yield` per-keyword win-share; customer-anchor grounding (`briefs/anchors.py`); prompt `v10`→**`v11`** (single keyword-feedback signal, `0022`→`0023`) | ✅ **built + deployed** (dev) |
| **Scoring v2** | V2-1 contract + deterministic gates (`labeling.py`, `0024` `label`/`score_total`, extended stage-0 classifier emitting `hq_country`/`has_b2b_line`) | ✅ **built + deployed** (dev) |
| **Scoring v2** | V2-2 the two paid score calls (`company_score_v2` web-grounded, `prospect_score_v2` no-web) + rescore cutover + find-time labeling + `0025` v2 rubrics | ✅ **built + deployed** (dev) |
| **Scoring v2** | V2-3 UI — 4-bucket call-sheet tables both steps (label chip + subscore bar + reason + trigger; footnote buckets collapsed w/ counts + per-reason sub-groups; override gate) | ✅ **built** (dev) |
| **Scoring v2** | V2-4 contraction — `0026` drops v1 `fit_*`/indexes + dead code (5 sync twin endpoints + v1 fit path, `reason_tags`, `outreach_outcome`, `status` default); feedback/batches/approvals migrated to `label`/`score_total` | ✅ **built + deployed (dev)** |
| **Model A/B** | Stage-0 `classify_business_model` → **DeepSeek V4 Flash** (switched, live); paid `company_score_v2` → **KEEP Pro** | ✅ **decided + deployed** (dev) |
| **UX U1** | Per-ICP scope overrides (server-side `ScopeOverride.params` keyed `by_icp` for people + new `kind="company"`; precedence = body → per-ICP → AI spec) | ✅ **built + checked** |
| **UX U2–U4** | People-find lineage · toolbar rebuild (cost-gradient order) · Find-history drawer v2 | ✅ **built + checked** |
| **UX (new)** | **Reveal & score merge** + Step-2 reason-line removal + frontend 250-row ceiling removed (2026-07-10, this session) | ✅ **built + pushed** (`2838d85`) |

**What's left before Phase E (the pending register):**
- ✅ **Founder review #5** — signed off 2026-07-10 (v2 labels + the new toolbar in one sitting).
- ✅ **V2-4 contraction** shipped — `0026` applied to dev, code committed + pushed (`2838d85`).
- ✅ **Code-review fix wave** — the §D+.5 wrap-up register (7 P1 · 16 P2 · P3 cleanup, 2026-07-10). **Executed 2026-07-10 across F1–F7** (per-item result log → **§D+.6** below): all 31 resolved except R21 (deferred — MVP list < 1 page), the R27 cross-module query dups, and R30's two integration-test gaps (accepted, documented). Backend 228 passed/ruff clean · FE build+tsc+eslint clean.
- ✅ **Final fix wave (pre-production) — DONE + deployed** — the 2026-07-11 final review: **G1–G7**, 56 findings N1–N56 (3 P1 — the R8 skip-set crash, the `stageForPeople` excluded-row leak, Aurora deletion protection), §F founder decisions Q1–Q8. Built + committed (7 commits) + **deployed across two pushes** (dev Lambda **v78** + migration **`0027`** applied + Amplify dev job 52), then shipped to **prod** with the close-out push (v79 · Amplify prod job 20). Full digest → **§D+.6** below.
- ✅ **Paid re-score wave — not needed** — the **Q7 candidate list is empty** (confirmed 2026-07-11 against dev Aurora: 0 geo-excluded rows; the one N6-divergence-prone tenant has 0 companies). N4/N6 are forward-looking. Rows never scored still carry `label = NULL`; run "Update AI Score" (≤15/batch) on demand for a fresh web-grounded pass. Non-blocking (NULL renders "Needs score").

**KPI gate** ("more rows that score higher", measured in-app, baseline-relative targets are reference not a hard gate — no baseline round was captured): rows/find **≥3×** · `contact_now`+`contact_soon` share **≥2×** (or ≥30% absolute) · zero-result finds **<10%** (all auto-relaxed) · dupes on re-find **<5%** (≈100% today) · title match **≥7/10** · re-classification spend on known rows **$0**.

---

### D+.1 · Scope alignment — the sourcing fix (Stages 1–4)

Root-caused 2026-07-08 (code read + verification against Apollo's official OpenAPI spec) to six pipeline causes — **ours, not Apollo's data:**

1. **Width cap wastes work** — the old `MAX_COMPANIES_PER_FIND=15` kept 15 of every 100-row page.
2. **No feedback signal** — the find path discarded `pagination.total_entries` + `breadcrumbs` + `partial_results_only`; queries flew blind.
3. **Ungrounded vocabulary** — free-text `q_organization_keyword_tags` with no validation vocab; facets AND, so one bad keyword sinks the query. (Technologies have a canonical CSV vocabulary — was unused.)
4. **Query ≠ rubric** — the people query sent seniority×department but never `person_titles`, while the fit rubric scores a *title* dimension → low fit partly by construction.
5. **Departments param unverified** — `person_department_or_subdepartments` isn't in Apollo's documented API (live A/B verdict: it **does** filter — keep the rung).
6. **One query per ICP** — no variants; the relax ladder existed on people only, not companies.

**Exclusion reality.** Apollo has NO exclude-by-id/keyword/industry — only `organization_not_locations` + `currently_not_using_any_of_technology_uids`. Known-bad rows can't be sent back to Apollo; the equivalent is built pipeline-side: a **query-keyed page cursor** (repeat find resumes at the next page + skips known `apollo_org_id`s — stop re-buying page 1), **negative-evidence feedback** into Regenerate Scope (keywords correlated with excluded/low-fit rows get dropped by the LLM), the two real exclude params when bad rows cluster, and **lookalikes of `contact_now`/`contact_soon` rows** for positive reuse. Stored `business_model` labels make a returning bad row spend $0 — pinned with tests.

**As built (all deployed to dev):** Stage 1a = `research_run.filter_body`/`scope_source`/`result_meta` telemetry (absorbs the 2026-07-06 scope-lineage design — executed-body snapshot, override-proof). Stage 1b = the async find path (return-fast, enrich+classify+score on a background `scoring_job` worker — the 30s API-GW ceiling on sync classify+enrich is why width can't grow on the sync path) + a fetch-page-1-then-assess relax ladder (drop `revenue_range` → widen size ranges → drop weakest keyword; `>100k total` flagged over-broad) + the read-only Find-history drawer. Stage 2 = titles-first people ladder + APAC broadening (`email_status` never constrains people *search* — it's a `people/match` gate only). Stage 3 = the page cursor + known-org skip + the negative-keyword/`organization_not_locations` feedback blocks. Stage 4 = the tech-UID resolver + `keyword_yield` + customer-anchor grounding. Migrations `0019`–`0023`, Lambda published. **Tests: `apollo_map`-style fixtures across all stages, full suite green, ruff clean.**

New FE surfaces: only the **Find-history drawer** (1b) + **scope-exhausted notice** (3) — everything else rides existing tabs/chips/filters (revised again in the U1–U4 rebuild, §D+.3).

---

### D+.2 · Scoring v2 — the 4-label system (folds in the deleted scoring spec)

**Driving insight** (from hand-verifying 4 of the 66 live rows — 3 of the first 4 moved buckets): **enrichment data lags reality by months.** Apollo showed CXA Group healthy at 65 staff / $63M while it was nine months into voluntary liquidation. So v2 adds three things v1 lacked:
- a **liveness gate** (nothing else catches a defunct/absorbed/dead-site company);
- **`outbound_gap` redefined around distribution model** (partner-led = already solved distribution = our hardest sell; word-of-mouth = our best buyer) instead of headcount;
- **headcount demoted from gate to signal** (sources disagree up to 4× — Bytesforce reads 46 / 60 / 200–500 / 1,300 / 2,700+ depending on source).

**The four labels** — two actions, two footnotes; **never delete a row** (every sourced company gets a label + a reason):

| Label | Meaning | UI |
|---|---|---|
| `contact_now` | Strong fit, contact this cycle | expanded |
| `contact_soon` | Fits, but a gap or unknown | expanded |
| `low_fit` | Our judgment says no — client may override | collapsed (counts) |
| `excluded_by_rules` | A rule removed it | collapsed, shows the rule |

**Processing order** — stop at first match, but **free deterministic gates run before the paid web call** (a deliberate re-order of the spec: rules/data/size cost $0 and need no search — the ICP verdict rides the paid call, step 4; only liveness+score needs the web — a row killed by a rule is never liveness-checked, so a defunct B2C company just reads `"rule: B2B only"`):

1. **Rules** (deterministic, at find/classify time) → `excluded_by_rules`: `targetMarket` × stage-0 `business_model` (the live market gate; `Complex`→B2B) · **geography — either-country in-target:** a row is kept if EITHER its description-derived HQ OR Apollo's `field_country` is in the brief/ICP geographies (the search was geo-filtered, so Apollo's country is authoritative even when the description names a founding/parent country elsewhere); excluded only when ≥1 country is known and NONE is in-target; a description↔field disagreement still flags `hq_mismatch` · client exclusions (`ExclusionSet`). *(The former B2C-with-a-B2B-line "Luma guard" carve-out was **removed 2026-07-10** — a B2B line no longer rescues a primarily-B2C company.)*
2. **Data check** (deterministic) → `low_fit "data_unusable"`: industry null/`—` · hq_country null · website is a wire service/aggregator. **Headcount is NOT a gate.**
3. **Size** (deterministic, when the ICP band is filled, runs **before** the ICP check) → `low_fit "too large"` above the client-wide max employee band. Never a hard exclusion — headcount data can't carry one. *(The `headcount_uncertain` suppression was **removed in D+.5/R11** — only one headcount source exists in the data, Apollo `estimated_num_employees`, so the "sources disagree >2×" flag was never producible.)*
4. **ICP match** — rides the **paid `icp_match` signal** from the score call (step 5), NOT a free deterministic check: the web-grounded scorer reads the **description**, not the `industries` field (Blackpanda is tagged "network security" but is a Lloyd's coverholder underwriting cyber insurance = ICP A), and assigns the ICP; no match → `low_fit "wrong vertical"`. So a row reaches this verdict only after the free gates AND the paid call — evaluated in the same `assign_label` pass, gate order `rules → data → size → icp`.
5. **Liveness + score = ONE web-grounded LLM call** per surviving row (`company_score_v2`, DeepSeek V4 Pro **with web search**, ~50–120s, async `scoring_job` waves ≤ `ASYNC_BATCH_MAX`): searches `"{company} liquidation OR acquired OR shut down"` first → defunct/absorbed/dead-site → `excluded_by_rules` (`"company defunct"` / `"acquired — no longer independent"` / `"no active web presence"`); news >24mo → flag `stale_record` only. Then emits the 4 subscores + reason + flags + a **trigger line (the email hook)**; the server sums → label.

**Score = 4 axes, 1–5, sum 4–20** → `label_from_score`: **≥16 `contact_now` · ≥10 `contact_soon` · else `low_fit`**. The LLM never picks its own label (same posture as the deterministic `collapse()` — server-computed).

**Company axes:**
- **`deal_fit`** — does ACV support $500/meeting? `5` = enterprise six-figure · `3` = mid-ticket (Blackpanda IR-1 ≈ USD 8k/yr) · `1` = self-serve ($49/mo).
- **`outbound_gap`** — do they need us? scored on **how they acquire customers today**: `5` = word-of-mouth/referral only · `4` = inbound/product-led · `3` = conference/event-led · `2` = broker/reseller · `1` = named channel partners or investor-as-distributor. **Score down if hiring sales roles** (building in-house). A partner-led company has already solved distribution — the hardest outbound sell.
- **`trigger`** — in-market now? `5` = raise / exec change / new market / rebrand / >20% growth · `1` = flat.
- **`reachability`** — can we reach the buyer? `5` = founder-led small team · `1` = 1000+ layered. **Headcount feeds here and only here** (approximate).

**People tier (Step 2) — same labels, people-shaped axes, NO per-person web search** (liveness is a company property; people ≫ companies makes per-person search a cost explosion). `prospect_score_v2` judges enrichment only: `persona_fit` (title/role vs the ICP persona) · `authority` (seniority / decision power) · `trigger` (person-level: new-in-role, promotion, hiring for their function) · `reachability` (verified email · contact quality). Same 4–20 sum, same 16/10 thresholds. **The company label caps the person** (the meeting is with the company): a person at an `excluded_by_rules` company inherits `excluded_by_rules "parent company excluded"`; a person never ranks above its company. Deterministic gates first: `avoidTitles` (per-ICP) → `excluded_by_rules` · missing title/contact → `low_fit "data_unusable"`. **Net token WIN vs v1**: the old grid re-judged the company dims for *every* person (10× for a 10-person company) — v2 drops them and inherits the company result.

**Reason strings** — always populated. Gate verdicts use the canonical `labeling.py` constants: `"company defunct"` · `"acquired — no longer independent"` · `"no active web presence"` · `"rule: B2B only"`/`"rule: B2C only"` · `"rule: outside target geography"` · `"rule: client exclusion"` · `"data_unusable"` · `"wrong vertical"` · `"too large"` · `"parent company excluded"` (people). Scored rows carry a **model-authored one-sentence reason** (e.g. `"fits ICP A — <one clause>"`), not an enum.

**Flags** — non-blocking, small warn marker + tooltip: `hq_mismatch` · `revenue_implausible` (>10× off description) · `founding_date_conflict` · `competitor_adjacent` · `partner_led` · `stale_record`. *(`headcount_uncertain` was removed in D+.5/R11 — never producible; see step 3.)*

**The v2 contract vs v1** (what changed):

| Piece | v2 | v1 (fit-rubric-v1) |
|---|---|---|
| Label | 4 labels above; never delete a row | `fit_tier` Strong/Good/Moderate/Below + `market_excluded` |
| Score | 4 subscores 1–5, sum 4–20 → 16/10 thresholds | 0–100 grid, tiers at 75/55/40 |
| Reason | short enum-ish string, always populated | free-prose `fit_reason` |
| Flags | the non-blocking array above | none |
| Verified | **NOT adopted (decision B)** — the liveness call runs every rescore so it'd be true for almost every row; the liveness verdict still lives in `fit_components.liveness` | — |

**Four locked decisions (founder 2026-07-09):** ① **build v2 NOW**, deploy with Stages 2–4, one combined label-measured round (interim Strong+Good rounds dropped). ② **No backfill** — rows start `label = NULL` ("needs re-score"); a tier-mapped backfill would have put CXA (Good·55, in liquidation) into `contact_soon` — the exact failure v2 exists to stop. ③ **Both tiers adopt labels** (people get the people-shaped axes above). ④ **Overrides** — `low_fit` is selectable behind a confirm; `excluded_by_rules` is **locked** (unblock only by changing the rule or re-scoring, never a click-through). Plus **⑧-B create-and-label at Step 1**: Flow-A no longer *drops* client-excluded domains — it keeps + enriches + labels them `excluded_by_rules "rule: client exclusion"` (company org-enrich costs credits, but the founder accepts keep-and-enrich at current low volume; `skip_known` bounds re-find cost to $0; the Step-2 people/enrich hard-block stays).

**Storage (no new columns beyond `0024`):** `label` + `score_total` are columns (index `(tenant_id, label, score_total DESC)`); `reason` reuses `fit_reason`; `subscores`/`flags`/`trigger_line`/`liveness` live in `fit_components` JSONB. **⑨ index-ordering gotcha:** the `0024` label index orders `label` *alphabetically* (not UI priority), so the feed fetches each collapsed bucket as a per-label query or orders by a CASE rank in-app — there is no single globally-label-ranked index scan.

**The 66-row fixture** (spec §12) is preserved as a **test fixture, not ground truth**, in `tests/test_labeling.py` — 5 web-verified anchors (Bytesforce/Pro5.ai `contact_now`; Blackpanda/Luma `contact_soon`; CXA `excluded_by_rules "company defunct"`) + gate-order units. **Sourcing is the real bottleneck: only ~5 contactable of 66 sourced — v2 makes that visible; the §D+.1 loop is what fixes it. A better rubric surfaces the problem; it does not fix the query.**

**V2-4 removal inventory** (the contraction pass, `0026` + code, after UAT): drop `fit_score`/`fit_tier` on company AND prospect + both fit-sort indexes · `prospect.outreach_outcome` (no writers) · `prospect.status` default `"new"` → `"found"` · `reason_tags` (written, never rendered) · the 5 **sync twin endpoints** (web calls only `-async`: `find-company` · `companies/rescore` · `update-fields` · `find-lookalikes` · `prospects/rescore` — tests re-pointed at the core fns).

---

### D+.3 · Find-flow UX rebuild (U1–U4) + Reveal & score

Founder toolbar review (2026-07-10): buttons weren't ordered by business logic, filters were redundant, Find history was a flat unusable list, and Step-2 Find Settings silently broke the per-ICP persona auto-resolution (one global `ScopeOverride` row clobbered every ICP).

**Design rule:** the toolbar mirrors the funnel's **cost gradient** — widen (FREE) → label (FREE) → score (PAID LLM) → select → find people (FREE) → **reveal & score people** (the PAID step — see below) → batch. One funnel-advancing primary per step; config/observability demoted; the cost shown exactly where money is spent.

**Founder decisions (2026-07-10):** ① Step-1 header select-all **removed** (rows ticked individually). ② paid scoring becomes a **bucket CTA** ("Score next 15" on the Needs-score header, both steps) + **auto-chain** with a live cost counter + Stop (one ≤15-row job/wave; the one-job-per-tenant×kind rule chains waves). ③ **stage→find merged** — the Step-1 "Find people for N →" stages AND runs find-people via FE chunking (`MAX_ORGS_PER_FIND=8`/call). ④ **both scope overrides go server-side, per-ICP** (U1). ⑤ filter rows shrink to **search + ICP (view-only) + More ▾** ("Any label"/"All Business" deleted, "All status" into More ▾). ⑥ **Find-history full redesign** (day groups · type chips · same-scope threading · summary strip · people-find lineage). ⑦ **"Find Companies ▾" split button** absorbs Lookalike + Manual add, target ICP moves onto the button face (the filter-row ICP becomes view-only); S1 "Enrichment" → "Refresh company data" (⋯ overflow); "Fit Rubric" → ⋯ "Edit scoring rubric". ⑧ **build now** — review #5 covers v2 labels AND the new toolbar in one sitting.

**As-built (2026-07-10 — R18 reconciliation, review #5 signed off).** Several of the toolbar decisions above were **descoped during the build** and are recorded here as the real shipped behavior; each is **deferred — revisit only if operating pain shows up**, not a bug:
- **Paid scoring** ships as a **manual "Score next 15 →"** on the Needs-score bucket header, **Step-1 only** — the operator clicks again for the next wave. The planned **auto-chain + live cost counter + Stop** (decision ②) and the **Step-2 bucket CTA / 4-bucket call sheet** were **not built**. (One ≤15-row job per click; the one-job-per-(tenant,kind) rule still prevents overlap.)
- The filter row stays **search + status + ICP**; the **"More ▾" overflow** (decision ⑤) was **not built**.
- Company actions stay as discrete buttons; the **"Find Companies ▾" split button + ⋯ overflow** (decision ⑦) were **not built** (Lookalike / Manual add / Refresh / Edit-rubric remain their own controls).

What DID ship: ① individual row ticks · ③ stage→find merge · ④ per-ICP server-side overrides (U1) · ⑥ Find-history v2 (U4) · the **Reveal & score** merged paid action (below) · **checked-set invariants** (D+.5/R6+R13 hardened them).

**Stages (backend-before-frontend):** **U1** per-ICP scope overrides — `ScopeOverride.params` keyed `by_icp` (people) + new `kind="company"` rows; GET/PUT/DELETE gain kind+icp params; find precedence = body override → per-ICP override → AI spec; FE write-through migration of the localStorage company override (no migration — `params` is JSONB). **U2** people-find lineage (`filter_body`/`scope_source`/`result_meta` on people runs; `group_id` threads the chunked stage→find). **U3** toolbar rebuild (Find ▾ split + ICP-on-button, selection bar at ≥1 tick, bucket CTA + auto-chain, filter shrink, **checked ⊆ visible** invariant — fixes the "Score 3 but ran 9" mismatch). **U4** Find-history drawer v2 (day groups · type chips · body_hash/`group_id` threading · spend summary).

**Reveal & score — the merged Step-2 paid action (founder 2026-07-10, this session; supersedes decision ⑦'s separate "Reveal emails" dock button).** The Step-2 "Get AI score" + "Reveal emails" buttons are merged into **one** async job (`enrich_score_prospects`): it **reveals verified emails (Apollo `people/match` — the only credit spend) THEN scores on the revealed row, in one worker run.** Reveal-first is the fix — Apollo obfuscates seniority/department/email until match, so scoring a pre-reveal person gated on missing contact and landed a degraded label. The button label adapts: `Reveal & score N · N credits` when rows still need a reveal, plain `Score N` when the selection is already revealed (idempotent — a re-run just re-scores, no spend). Capped at 15/wave. `_enrich_prospects` is the shared credit-safe, idempotent reveal path — now committed **per row** (D+.5/R10) so a concurrent door or a re-run can't double-charge. *(The v1 sync `/prospects/enrich` twin was **retired in D+.5/R10** — the async Reveal & score door is the only reveal path now.)* Also this session: the free-text fit-reason prose was **removed from the Step-2 people fit cell** (label chip + subscore breakdown only), and the frontend **250-row list ceiling was removed** (the UI now loads the whole list, so bucket counts match the DB).

**Deploy:** U1+U2 = one Lambda publish (no migration) → then the FE push (Amplify autoBuild). UAT folds into review #5. Unchanged invariants: `excluded_by_rules` locked out of selection, `low_fit` behind the confirm, enrich human-gated ≤15/call, scoring ≤15/job.

---

### D+.4 · Model selection — Pro vs Flash live A/B (2026-07-10)

Both v2 LLM calls were A/B'd `deepseek-v4-pro` vs `deepseek-v4-flash` on the dogfood tenant via a read-only in-Lambda harness (the exact production path, one model swapped, never persisted; removed after — git-recoverable at `eaf7060:apps/api/app/domains/prospects/model_compare.py`). **Split verdict — opposite cost/reliability trade-offs:**

| Call | Verdict | Evidence |
|---|---|---|
| **`classify_business_model`** (stage-0, web-free, coarse label) | **✅ SWITCHED to Flash** (live) | 239-row run, static inputs (no web-drift): **90.8% exact** label, **94.6% market-gate-outcome** agreement; errors are safe-direction (a wrongly-kept row just scores `low_fit`). Flash **21× cheaper** + **2.3× faster**. |
| **`company_score_v2`** (paid, web-grounded ranking) | **⛔ KEEP Pro** | 66-row run: 82% label agreement, score MAE 1.52 (Flash biases ~0.45 lower, under-rates strong rows, once collapsed to all-1s). Flash is 3.3× cheaper but the saving is **cents**/call. |

**Decision rule:** switch the call whose errors are *recoverable* and whose inputs are *cheap + static* (the classifier); hold the call whose errors are *terminal* (a downgraded strong lead is never contacted). At **$500/qualified-meeting** economics, reliability on the paid ranking call outranks a cent-level saving. Re-run this A/B when the model list changes.

---

### D+.5 · Code-review wrap-up (2026-07-10) — findings register

Full-pass D+ review (DB `0019`–`0026` · backend `prospects`/`briefs` domains · web list flow · cross-file
contracts), investigation only. Every P1 was hand-verified against the code.
**Execution plan was `docs/dplus-fix-plan.md`** (deleted) — executed 2026-07-10; its per-item result log
+ carve-outs are consolidated in **§D+.6** below. Both the dplus-fix-plan and the final-fix-plan docs were
folded in here + deleted — this doc is now the single surviving plan/record.

> **✅ FIX WAVE EXECUTED (2026-07-10) — all 7 phases (F1–F7) complete; per-item result log in **§D+.6**
> below.** All **31 findings resolved** except **three documented carve-outs**: **R21**
> deferred (job result carries counts not rows → the row-merge needs a backend row-return; F1/R5's index
> already removed the per-page cost it "compounds", and at `FEED_PAGE=250` the MVP list is one request —
> revisit past 250 rows); the **R27** `_latest_spec`×2 / `_feedback_rows`↔`_scored_company_rows` cross-module
> query dups left in place (no clean shared home without polluting the pure `feedback.py` or risking an
> import cycle; ~10-line identical queries, zero behaviour benefit); and **R30**'s two residual integration
> tests (research-runs endpoint · per-ICP people-precedence HTTP) recorded as **accepted gaps** — both are
> Aurora-gated and overlap existing coverage (`test_multi_icp_find_runs_icp_by_icp` exercises the per-ICP
> find; the R22b resume test + FindHistoryDrawer exercise `research_run` reads). **Backend: 228 passed / 18
> skipped, ruff clean. Frontend: `pnpm build` + `tsc` + `eslint` clean.** Migration `0027` + the deploy-to-dev
> smokes were then done under the G-phase pushes (§D+.6). The register rows below are
> historical (pre-fix findings); **§D+.6** below is the authoritative result log.
> **Final pre-production review (2026-07-11):** six parallel full-file reviewers re-swept Phase A→D+ (backend ·
> frontend · infra/migrations/scripts · docs + a live dev-Aurora read-only check + an executed e2e run) →
> **56 new findings (N1–N56: 3 P1 · 19 P2 · 34 P3)** incl. six regressions/incomplete spots from the fix wave
> itself (N1 = the R8 skip-set crashes; N17 = the R17 e2e test fails as written). Resolved with pre-made
> decisions (§F Q1–Q8) across **G1–G7 — built + deployed (§D+.6 below).**
**Verdict:** the pure cores (label engine, relax ladders, feedback/vocab, migrations) are clean and well-
tested; the risk concentrates in **concurrency seams, pagination/cursor math, selection-gate edges, and one
hot-read index regression** from the `0026` contraction. Fix **R1–R7 before Phase E** (R2/R8/R10 are
money/compliance-adjacent); fold P2s into the same pass where cheap; P3s are the wrap-up sweep.

**P1 — fix before E:**

| # | Where | Finding | Fix |
|---|---|---|---|
| **R1** | `apollo/client.py:145` | `_paginate` varies `per_page` per page (`min(100, remaining)`) — any `limit > 100` (client-suppliable; `FIND_COMPANY_LIMIT` env) makes page 2 re-read rows 51–100 and never fetch 101–150; cursor `end_page` recorded in mixed page units. Latent only because default limit = 100. `test_apollo.py:180-194` pins the bug as expected. | Always request `per_page=100`, trim client-side; store `per_page` beside the cursor + invalidate on change; rewrite the test |
| **R2** | `router.py:2793-2812` + `find.py:14-16` | **Post-enrich do-not-contact check never runs** — the revealed email/LinkedIn is written back with no `ExclusionSet.blocks()` pass (find.py's own docstring promises it happens post-enrich). A DNC person flows enrich→`scored`→batchable. | After `parse_match`, run `blocks(email/linkedin/domain)`; hit ⇒ `excluded_by_rules "rule: client exclusion"`, never batchable |
| **R3** | `scoring.py:60,185,205` · `lambda.tf:43,82` | Reaper window (360s from `created_at`) < worst-case worker life (120s async-queue max age + 300s run = 420s), AND `run_scoring_job` never checks it was reaped: falsely-reaped job + re-click ⇒ **two workers on the same rows (double paid batch)**; first worker resurrects the `error` job to `done`. Same pattern in `briefs/structuring.py`. | `MAX_JOB_AGE_SECONDS ≥ 480`; worker aborts unless `status=="queued"`; terminal writes guarded `WHERE status='running'` |
| **R4** | `router.py:1237-52,1470-77` | Stage-3 cursor key = hash of the **resolved** body — feedback-derived filters (negative tech/keywords flip on every rescore) + the live relax rung are inside the hash ⇒ cursor churns, repeat find restarts at page 1, all rows known-skipped ⇒ `found=0`. Defeats the "never re-buy page 1" invariant. | Hash the stable scope (AI/override block, pre-merge pre-relax); volatile parts → `result_meta` only; add a `_body_hash` stability test |
| **R5** | `router.py:458-72,986-1001` · `0024`/`0026` | Both list feeds `ORDER BY score_total DESC NULLS LAST, created_at, id` — the surviving composite leads `(tenant_id, label, …)` so it can't serve the sort, and `0026` dropped the v1 index that did. Every page = full tenant sort; FE walks ALL pages on mount. Comment `:454-56` + `data-schema.md:425-29` claim coverage that no longer exists. | Add `(tenant_id, score_total DESC NULLS LAST, created_at DESC)` (or per-label feed queries per gotcha ⑨); fix both stale claims |
| **R6** | `list/page.tsx:990-99,743-48,700-07,2090-97` | Selection-gate trap ×2: a checked row re-scored to `excluded_by_rules` stays selected (wave scoring/reloads never prune checked sets) with a disabled checkbox that can't be unticked — "Find people for N →" then **stages an excluded company into Step 2** (LOCKED invariant violated); twin: an excluded company already in Step 2 can never be removed (remove works off ticks; `maySelect` blocks the tick). | Prune checked sets of excluded ids on every reload; gate only funnel-advancing actions (allow tick-for-remove) |
| **R7** | `router.py:1796-98` | `GET fit-prompt?stage=prospect_fit` 500s (AttributeError) for a tenant with zero prospects — `prospect.enrichment` deref'd outside the `if prospect` guard. | One-line guard fix |

**P2 — fold into the same pass:**

| # | Where | Finding | Fix |
|---|---|---|---|
| **R8** | `router.py:1903-04` | Reveal & score **spends before the free gate**: people under an `excluded_by_rules` company are enriched at 1 cr each, then instantly labeled `parent company excluded` (server never blocks selecting them — FE-only). | Drop parent-excluded rows pre-enrich in `run_enrich_score_prospects` + `confirm_enrich` |
| **R9** | `scoring.py:106-26` | One-in-flight job rule is check-then-insert (no DB constraint) — concurrent posts both dispatch; two find workers then race `_upsert_company` (IntegrityError kills a whole batch). | Partial unique index `(tenant_id, kind) WHERE status IN ('queued','running')` |
| **R10** | `router.py:2752-2812` | Enrich credit gate is read-then-write with one end-of-batch commit, across three doors serialized per-kind only (sync `/prospects/enrich` · reveal-worker · rescore) ⇒ concurrent doors double-spend ≤15 cr. The sync endpoint is FE-unused post-merge. | Per-row stamp/commit (or `FOR UPDATE`); delete or lock the unused sync door |
| **R11** | `labeling.py:58-73,259` | `headcount_uncertain` suppression is **inert** — nothing sets the flag (`deterministic_flags` computes only `hq_mismatch`/`stale_record`; `MODEL_FLAGS` excludes it; only the unit test injects it). The §D+.2 suppression sentence is dead. | Compute it in `deterministic_flags` (sources disagree >2×) or delete suppression + spec claim |
| **R12** | `api.ts:673-84` · `list/page.tsx:873-88` | Job-poll leak: `alive()` never flips on unmount ⇒ orphan loops (2s × 200) + full-list refetch + toasts after leaving the page; one transient poll 5xx abandons tracking (rows stuck "Pending"); poll-ceiling on a running job reads as success ("Scored 0"). | Unmount ref in `useEffect` cleanup; retry transient errors; non-terminal at ceiling = still running |
| **R13** | `list/page.tsx:526,2251-62,656-59` | "checked ⊆ visible" not enforced: Step-2 countrow shows visible∩checked while the dock + Reveal & score run on ALL checked ("2 selected" vs "Reveal & score 5"; hidden rows acted on). | Prune checked sets on filter change, or one selection source everywhere |
| **R14** | `list/page.tsx:536-39` · `constants.ts:63` | Credit estimate drifts at status edges: revealed-but-score-failed rows counted as spend; `enrich_failed` shows "no credits" though a re-match can spend. | Estimate spend by `!p.email`, include `enrich_failed` |
| **R15** | `list/page.tsx:566-604` | U1.6 localStorage→server override migration PUTs without GET-first — a stale pre-U1 browser silently clobbers a newer server override (once). | GET first; skip PUT when a server row exists |
| **R16** | `FindHistoryDrawer.tsx:143-71` | Naive ISO parsed as browser-local (Data API strips the offset; `spec.tsx` pins `+"Z"` for exactly this) — HK day-groups/summary window off by 8h. | Reuse spec.tsx's UTC-pinning helper (kills the dup too) |
| **R17** | `e2e/_mock.ts:91-93,68` | `/prospects`/`/companies` mocks return `[]` but `pageThrough` expects `{items,next_cursor}` ⇒ TypeError swallowed as a warn toast — **e2e passes while the list renders nothing**; approve mock still emits retired `fit_tier`. | `{items:[],next_cursor:null}`; drop `fit_tier` |
| **R18** | §D+.3 vs `list/page.tsx` | **Doc-vs-built gap:** auto-chain + live cost counter + Stop (decision ②), Step-2 4-bucket call sheet + bucket CTA ("both steps"), More ▾, "Find Companies ▾" split button, ⋯ overflow — none built ("Score next 15 →" is Step-1-only, "operator clicks again"). Review #5 signed off the as-built behavior. | Decide per item: build as a U5 pass or amend §D+.3 to as-built (recommended, given sign-off) |
| **R19** | `fit.py:203` · `router.py:650-54` | Company-score schema hard-codes `icp` enum `["A","B","none"]` — a 3rd ICP is structurally forced to `"none"` → `low_fit "wrong vertical"` AFTER the paid call. | Derive the enum from the tenant's ICPs at prompt-build time |
| **R20** | `router.py:2520-84,1517-31,292-305` | Data-API round-trip waste (per-statement HTTP): sync find-people does per-person single-row SELECT + per-row `refresh` (≈500 sequential RTs worst case on the 30s route) + 8 orgs × 4 rungs serial Apollo; `_upsert_company` 2 SELECTs/row; `_resolve_tech` re-parses the tech CSV every call; workers `refresh` rows nobody reads. | Batch `IN()` pre-loads, drop refresh loops, memoize `parse_vocab`, fan out per-org (or async the route like 1b) |
| **R21** | `list/page.tsx:1028-43` · `api.ts:561-79` | Every ≤15-row wave triggers a full uncapped-list serial cursor-walk (⌈N/250⌉ requests/wave; compounds R5). | Merge `job.result` rows into state; full walk on mount only |
| **R22** | `router.py:1282,1300-17` | `_resume_page` scans only the latest 50 runs across ALL sources (rescore/enrich/people runs evict find rows) ⇒ cursor silently lost ⇒ page-1 re-buy; no `(tenant_id, created_at)` index on `research_run` for the scan or the history endpoint. | Filter scan to company-find sources + add the composite index |
| **R23** | `scripts/c_smoke_live.py:87-91` | Live smoke calls the deleted sync `find-company` + reads dropped `fit_score` — can never pass post-V2-4. | Re-point at `find-company-async` + job poll; read `label`/`score_total` |

**P3 — wrap-up sweep (grouped):**

| # | Theme | Contents |
|---|---|---|
| **R24** | Dead BE code | `SYNC_FIND_COMPANY_LIMIT` + `MAX_PEOPLE_PER_FIND` (zero readers) · `_find_company_core` unused `ceiling` param · ~8 stale docstrings citing deleted sync routes / the removed Luma guard / v1 gates (`router.py:9,1172-77,2144-45` · `schemas.py:97-98,202-06` · `models.py:371` · `fit.py:9-10`) |
| **R25** | Dead FE code | `FitScore` + `FIT_CHIP` + the `.fit-*` CSS block (`workspace.css:2637-2910`) · `constants.ts` `loadScopeOverride`/`saveScopeOverride`/`UNSCORED_LABEL`/`dateRange`/`LabeledCompany`/`SubscoreMap` · fixtures `SCORE_TIERS`/`SAMPLE_INDUSTRIES`/`SAMPLE_CONNECTIONS`/`STAFF_ROLES` · `api.ts` `enrichProspects`+`EnrichResult` (all grep-verified zero refs) |
| **R26** | Missing render | `trigger_line` typed (`api.ts:514`) but never rendered — the V2-3 "trigger" call-sheet element is absent; render it or drop the field |
| **R27** | Duplication | `scoreCompaniesJob`/`revealScoreJob`/`scorePeopleJob` triplet · `runLookalike` vs `runLookalikeOfStrong` (~80%) · `whenLabel` ×2 (one is R16's bug) · avoid-title match `find.py:66` vs `labeling.py:398` (normalization drift) · `_feedback_rows` vs `_scored_company_rows` · `_latest_spec` ×2 · `MAX_JOB_AGE_SECONDS` ×2 |
| **R28** | Telemetry | `research_run.rubric_version` stamps the static constant, not the founder-edited prompt version actually used (`router.py:739,898,…`) · `scope_source="custom"` over-claims when a saved override row exists but resolved to nothing (`:2569-73`) |
| **R29** | Minor | `_is_apac` misses city-only APAC scopes (`:1408-24`) · find-people silently falls back to `icp_targeting[0]` for unknown-ICP companies vs the doc'd 400 (`:2453-58`, deliberate — align the doc) · FE chunk failure skips the final reload (`list/page.tsx:1265-79` → `finally`) · unused prefix-covered indexes `ix_company_tenant_id`/`ix_prospect_tenant_id` · retired `sourcing` prompt rows |
| **R30** | Test gaps | No tests: `run_scoring_job` lifecycle · `_enrich_prospects` re-spend gate · enqueue race · 4 of 6 worker fns (registry-wired only) · research-runs endpoint · `_body_hash`/`_resume_page` · per-ICP people precedence (HTTP-level). `test_apollo.py:180-94` pins R1 as expected behavior |
| **R31** | Doc drift | `data-schema.md`: head "`0025`" lines (L9/19/173/697-98) → `0026` · `ASYNC_BATCH_MAX = 20` (L562) → 15 · the label-index feed claim (L425-29, = R5) · `scoring_job` kind vocab (L568) · `market_excluded` description (L475) · `PHONE_ENABLED` documented as an env knob but hardcoded off · masking "fit tier+reason" (L583) · `prompt.stage` vocabulary missing `company_score`/`prospect_score` (L533/711-13). This doc: §D+.2 gate ladder drifted from the founder-amended code (geography = either-country in-target; Luma B2B-line guard removed 2026-07-10; ICP gate rides the paid `icp_match` signal, not a free check; size runs before ICP) — amend §D+.2 on the fix pass |

---

### D+.6 · Final pre-production fix wave (G1–G7) — DONE + deployed (2026-07-11)

The last hardening wave before Phase E — **the consolidation of the deleted `final-fix-plan.md` +
`prod-cutover-checklist.md`** (both folded in here). Six parallel full-file reviewers (backend · frontend ·
infra/migrations/scripts · docs + a live dev-Aurora read-only check + an executed e2e run) produced **56
findings N1–N56 (3 P1 · 19 P2 · 34 P3)**, six of them regressions from the D+.5 wave itself (N1←R8 skip-set
crash · N5←R1 guard order · N6←R19 letter derivation · N17←R17 e2e test · N18←R16 · N29←R9 catch). All
resolved; **built, committed (7 commits), and deployed across two founder-authorized pushes.**

**§F founder decisions (2026-07-11) — binding:**

| # | Decision |
|---|---|
| **Q1** | Checkpoint commit made · **one local commit per G-phase** · pushes per the Q1×Q2 reconciliation. |
| **Q2** | **G1–G4 (all P1+P2) → push #1 + deploy + dev smoke → G5–G6 → push #2.** Two pushes (Amplify only deploys on push, and the G4 smoke needs the FE up); backend deploys first within each. |
| **Q3** | N10 masking — deterministic redaction in `_masked` now + a "never name them" rubric line at the next prompt version. |
| **Q4** | N27 — free-gate `low_fit "parent company low fit"` (skip the paid call); override→rescore recovers the text. |
| **Q5** | N45 — wire "create client" to the real `POST /clients` (complete onboarding), not local create; switcher reads `me.clients`. |
| **Q6** | N3 deletion-protection applies with push #1; N20 DLQ+alarm / N52 IAM narrowing / N54 throttling → **prod cutover** (zero-new-resources). |
| **Q7** | Produce the re-score candidate list post-deploy; **founder** re-scores in the UI. **Result: list empty** (confirmed below). |
| **Q8** | e2e = mandatory manual G7 gate now; wire into the deploy script at cutover. |

**Phase → findings, and the delivered commits (all on `dev`):**

| Phase | Commit | Findings | What |
|---|---|---|---|
| G1 | `7e97c1b` | N1 · N2 · N3 | P1 blockers — Reveal&score skip-set crash · `stageForPeople` excluded-row leak · Aurora `deletion_protection` |
| G2 | `510d479` | N4–N10 (+N48/N49 folded into `0027`) | money/label path — geo-gate city segments · exhausted-cursor · ICP letter map · sync refresh-loop trim · `research_job` race + partial-unique · refresh-rotation status guard · masked-reason redaction |
| G3 | `085b11b` | N11–N19 | FE selection/state integrity + **e2e 7-red → 18/18 green** (N17 was a stale `_mock.ts`, not one test) |
| G4 | `843b86a` | N20(record) · N21 · N22 (+N55) | deploy-chain safety — random smoke pw · deps resolved from `pyproject.toml` (wheel-only compile) · never shift `live` off a non-Active version |
| G5 | `813398e` | N23–N54 · N56 | P3 sweep (backend N23–N37 · frontend N38–N47 · infra/docs N50–N56) |
| G6 | `b88cb6d` | §5 dead code + §6 perf | dead-code deletions · `list_research_runs` LIMIT 50 |
| G7 | `97f4725` | — | consolidation/checklist (now this section) |

**Standing carve-outs (from D+.5, still accepted):** R21 (post-wave full-list reload — revisit past 250
rows) · R27 (`_latest_spec`×2 / `_feedback_rows`↔`_scored_company_rows` query dups — no clean shared home) ·
R30 (research-runs endpoint + per-ICP people-precedence HTTP tests — Aurora-gated, overlap existing
coverage). New rule from the N1 lesson: **money-path branches get a non-Aurora unit test** (an Aurora-gated
integration test that skips locally is not enough — it let N1's crash through).

**Deploy record (both founder-authorized):**
- **Push #1 (G1–G4)** — **deploy-first** order (`0027` ADDS `uq_research_job_active_tenant`, a constraint old
  live code doesn't catch, so deploy-first has no bad window): `build-and-deploy.sh` → Lambda **v77** ·
  `alembic upgrade head` → **`0027`** (indexes verified via Data API) · push `dev` → Amplify job **51** · smoke
  green. The N3 `terraform apply` rode this deploy. Mid-deploy gotcha (now in the script comment + fixed to a
  wheel-only compile): without it `uv` pins an `argon2-cffi-bindings` with no manylinux2014 wheel and the
  `--only-binary` install fails.
- **Push #2 (G5–G6, no migration)** — Lambda **v78** · push `dev` → Amplify job **52** (also confirms N53's
  preBuild env-guard) · Aurora batch/approval smoke green (3 transient "Resuming" cold-start fails → green on
  warm retry).

**Q7 re-score list — EMPTY (confirmed 2026-07-11, dev Aurora read-only):** `excluded_by_rules` rows carry
only non-geo reasons (`rule: B2B only` ×37 · `acquired — no longer independent` ×12) → **0** geo-excluded
rows (real specs used country-level geo — the N4 bug was latent). The one N6-divergence-prone tenant
(`b4-17d76e96`, letterless ICP names) has **0 companies**; the only tenant with data (`holdslot`, 396
companies) uses clean "ICP A/B" names + **0** paid rows with a null ICP. No existing label is wrong; N4/N6 are
forward-looking → **no re-score wave needed.**

**Baselines at close:** apps/api ruff clean + **pytest 242 passed / 18 skipped**; apps/web tsc+eslint+build
clean + **playwright 18 passed**.

**Close-out push + prod ship (2026-07-11, founder: "deploy api, database and website to dev and prod").**
Three commits on top of the G-wave: `66dd619` (fix(web) — the Step-2 company-cell **trigger line
unrendered**, founder call; this finally *resolves R26* the other way — `trigger_line` stays a stored/API
field, the FE renders it nowhere) · `e2108c0` (chore(build) — compile flag `--no-build` →
`--only-binary=:all:`, so compile and install share one wheel-only constraint) · `b36b61d` (docs —
this consolidation). Backend rebuilt → **Lambda v79** (no migration; head stays `0027`), `/health` ok.
Pushed `dev` → Amplify job **53** SUCCEED; then **`main` FF-merged `79bf86a..b36b61d`** (20 commits — all of
D+/Scoring-v2/G1–G7) → Amplify job **20** SUCCEED = the **first public prod-FE release**; `tryholdslot.com`
HTTP 200. **Prod FE rides the SHARED dev-tier backend** (`api.tryholdslot.com` + the one Aurora) — the
isolated prod backend remains the deferred cutover (§After A–G register).

**★ REVIEW CYCLE CLOSED (2026-07-11).** The Phase A→D+ code-review round is final: D+.5 (R1–R31) + the
final pre-production review (N1–N56) are all resolved, deployed, and verified, with exactly three standing
carve-outs (R21 · R27-dups · R30's two Aurora-gated tests — above). No open findings remain against A–D+
code. Anything discovered from here belongs to a **new** register opened by the phase that finds it.

---

## Locked context you MUST carry (non-obvious; carry into every phase)

| Topic | Rule |
|---|---|
| **OpenRouter HK geo-block** | OpenAI / Anthropic / Google providers return **403 ToS** for this account (Hong Kong), account-wide. **Route every LLM call to non-US providers only** (DeepSeek / Qwen / Mistral; Llama dropped 2026-06-22). Scoping = `deepseek/deepseek-v4-pro` (thinking + web-search, ~55–76s) on the **async** path — exceeds the 30s API-GW sync cap. Fit scoring (v2) = `deepseek/deepseek-v4-pro` — `company_score_v2` **reasoning ON + web plugin** (~50–120s) · `prospect_score_v2` **reasoning OFF** (the v1 thinking-OFF A/B posture, kept; the trace was ~98% of output and drove the timeouts); both `temperature=0`, always **background** via `scoring_job` (never on the find request). **Stage-0 `classify_business_model` = `deepseek/deepseek-v4-flash`** (switched 2026-07-10 after a live A/B — see §Model selection; the paid scorer stays on Pro). |
| **Apollo credits** | **BOTH searches are FREE — 0 credits** (founder Apollo-dashboard confirm 2026-07-08; the public "charged per page" pricing doc does NOT apply to this Professional + master-key account). **`people/match` (enrich) = the ONLY spend: 1 cr/email** (8/phone — phone reveal **hardcoded off**, no env knob), human-gated at Gate 2. So find-width is **not** credit-bound — since Stage 1b the company-find path is **async** (`find-company-async`, bounded by the worker's 300s Lambda timeout; `FIND_COMPANY_LIMIT` env, default 100). Never `people/match` before Gate 2; suppression/exclusions are DB-side. |
| **Apollo API levers (verified vs OpenAPI spec 2026-07-08)** | **No exclusion params** except `organization_not_locations` + `currently_not_using_any_of_technology_uids` (no exclude-by-id/keyword/industry/title) → negative signal recycles pipeline-side (D+ Stage 3). `person_titles[]` is fuzzy by default — `include_similar_titles=false` = strict (D+ Stage 2). `person_department_or_subdepartments` is **not in the documented API** — live-verify (D+ Stage 1). Canonical tech vocabulary: `auth/supported_technologies_csv` (D+ Stage 4). Org-search responses carry `pagination.total_entries` + `breadcrumbs` — the probe loop's feedback signal (D+ Stage 1). |
| **2nd data source** | **Skipped (2026-07-08)** until **AroundDeal offers monthly API pricing** (API today = Enterprise-only ~$10k; 11-provider vetting found no self-serve Apollo-like APAC search API). FullEnrich $69/mo = enrich-only door later. See §Phase B/C refinement (2). |
| **Ops** | AWS uses `AWS_PROFILE=holdslot` (acct **138743894336**), never the default. `claude_code` IAM is **read-only** on `holdslot/prod/*` (founder writes all secrets). Deploy = `build-and-deploy.sh`. **git push needs the `weftxio` gh account** (`checkafy` lacks write). **Commit/push only when asked.** |
| **Posture** | Build single / design multi · **zero new AWS resources** added through D (every route rides the `$default` proxy) · token validity is **expiry-on-read, no scheduler** (mirrors `password_reset`) · webhook ingest (E) = **synchronous insert** at dogfood volume. |

---

## Phase E — Outreach + Smartlead (S4/S5) — the current front · **plan finalized 2026-07-11**

> **Build status (2026-07-12): E0–E7 COMPLETE + E0 LIVE-PROBE CLOSED + SHIPPED — backend + BOTH
> interactive FE tabs live on the shared dev backend. `0028` + `0029` applied to dev Aurora; DB
> integration green against Aurora. All 5 Smartlead webhook payloads captured LIVE + all 3 contract
> verdicts CONFIRMED; the per-email unsubscribe link is now enforced. The ship landed 2026-07-12:
> commit `d8aef2b` (Phase-E backend + fixtures + unsub link) · Lambda **v86** published + `live`-shifted
> (`build-and-deploy.sh`; `/health` OK) · `git push origin dev` → Amplify dev **job 55 SUCCEED**. Only
> the founder acceptance run remains (below).**
>
> **Backend (E0–E7, built + tested + DEPLOYED):** `app/integrations/smartlead/` (the 11-method adapter —
> sliding-window throttle + 429 backoff + `api_key` redaction), `app/domains/campaigns/` (`service.py`
> funnel state-machine + normalize/dedupe/launch/inbox/statistics + `describe_event` pure core ·
> `launch.py` async worker riding the `scoring_job` reaper pattern, no new job table · `router.py`
> console create/list/detail (incl. **per-lead cards `leads[]`** + **manual `…/leads/{id}/move`**) +
> launch/variants + **E5** reply queue (list/triage/respond, R4-b handle recovery) + **E6** winner/
> pause/resume/sync + **E7** `GET /performance-summary` · `webhooks.py` public token-authed ingest),
> migration **`0028`** (four tables, matches `data-schema.md`) — **applied to dev Aurora 2026-07-11**,
> `scripts/e_smoke_live.py` (E0 live probe), `tests/fixtures/smartlead/` (**all 5 webhook payloads now
> real** + real API responses + `_VERDICTS.md`). Wired into `app/main.py` (router + public webhook route +
> `campaign_launch` job). **Deployed to `holdslot-dev-api` — live alias now v86 (2026-07-12), the shared
> dev backend both FEs use; the unsubscribe-link change (below) is live in v86.**
>
> **⭐ Launch bug found + fixed during Aurora integration (2026-07-11):** the launch worker's tenant
> guard compared `campaign.tenant_id != tid` where the fresh worker session loads the UUID column as a
> **`str`** (RDS Data API) and `tid` is a `UUID` object → the guard was ALWAYS true, so **every launch
> would have silently self-aborted** ("campaign vanished") and been reaped to `error`. Fixed to a
> string-coerced compare (`str(...) != str(...)`); the previously-never-run `test_campaigns_db.py`
> launch→webhook→triage→respond→controls integration now passes against dev Aurora (2×, self-cleaning).
>
> **⭐ Sending inboxes moved to the DB (2026-07-11, founder decision "even for MVP"):** the Smartlead
> sending-account ids left the `holdslot/prod/smartlead` secret for a tenant-scoped **`sending_account`**
> table (migration **`0029`**, applied to dev; seeds tenant #0 `holdslot` = `20084486`,`20084475`). The
> launch worker now reads `active_sending_account_ids(db, tenant_id)` instead of `sl.sending_account_ids()`
> — **per-client isolation, a new client's inboxes are one INSERT** (no global-secret edit + Lambda
> cache-bust + redeploy). An inbox id is a reference, not a credential — the shared `api_key` stays the
> one secret. Model `SendingAccount` + N1 unit + integration seed added; backend redeployed **v83**.
>
> **⭐ E0 live-contract probe RUN (2026-07-11) — three more launch-blocking bugs found + fixed.** Ran
> `e_smoke_live.py` against a scratch campaign (id 3623750) on the founder's inbox via a throwaway
> request-bin. `create`/`schedule`/`settings`/`save_sequences` (A/B/C — **variant shape verdict 3
> CONFIRMED**)/`add_email_accounts` all passed live, then the probe caught: **(1)** `add_leads` rejects
> a top-level `return_lead_ids` (`400 "not allowed"`) → removed; **(2)** the `add_leads` response is
> **counts-only, no lead ids** — the worker read ids from it (`parse_add_leads`) so it would have
> inserted **zero `campaign_lead` rows** while Smartlead queued the leads (silent broken funnel) → new
> `fetch_campaign_leads` + `parse_campaign_leads` resolve `email→lead.id` from `GET /campaigns/{id}/leads`;
> **(3)** `register_webhook` requires a **non-empty `categories`** (`400`) → default to the seven standard
> lead categories. Then the **real `EMAIL_SENT` webhook payload was captured** (widened the scratch
> schedule → the send fired; caught off the request-bin) and it exposed **two more ingest bugs**:
> **(4)** the webhook lead-id field is **`sl_email_lead_id`** (== our stored `smartlead_lead_id`), not
> `lead_id`/`sl_lead_id` — `_resolve_lead` would have fallen back to slow email-matching every event;
> **(5)** `message_id` was a dedupe `_EVENT_ID_FIELDS` key, but it's the email's RFC Message-ID (shared
> across sent/open/click) → an OPEN/CLICK would be silently `ON CONFLICT`-dropped as a dup of the SENT
> row. Both fixed; verified live (200 / integration green), backend redeployed **v85**.
>
> **⭐ E0 CLOSED (2026-07-12) — all 5 webhook payloads real + all 3 verdicts CONFIRMED.** The deliverable
> round: the first send bounced off `jason@getholdslot.com` (a **non-existent** address → a real
> `EMAIL_BOUNCE` captured for free — `normalize→lead_bounced`, `is_bounced`, `bounce_reply_*`); the probe
> was reset (bin cleared, scratch senders narrowed to `jason.wong@` so it isn't a self-send, deliverable
> lead `jason.tse@` added), the founder opened + replied → the **real `EMAIL_REPLY` carries BOTH `stats_id`
> and `message_id` → verdict 2 CONFIRMED** (`reply_to_thread` path-a works directly; master-inbox R4-b is
> the fallback), then master-inbox-unsubscribed → the **real `LEAD_UNSUBSCRIBED`**, which pinned two more
> shape facts: it carries **no `sl_email_lead_id`** (resolve by email) and a **`Z`-suffixed timestamp**
> (`parse_occurred_at` still lands UTC). Identity pinned: sending inboxes `20084486 = jason.wong@`,
> `20084475 = jason.tse@`. Real fixtures + regression tests (`test_real_bounce_fixture_ingest_fields`,
> `…_reply_confirms_verdict2`, `…_unsub_fixture_ingest_fields`); `_VERDICTS.md`/`_README.md` finalized.
> **Total 5 contract/ingest bugs the probe caught + fixed — the adapter was built from docs; ALWAYS run
> the live probe before trusting a provider adapter.**
>
> **⭐ Unsubscribe link enforced on every email (2026-07-12, founder request).** `launch._smartlead_settings`
> now sets Smartlead's campaign-level **`unsubscribe_text`** (a top-level settings field, verified live:
> `update_settings` accepted it and `GET` echoed it back) to `DEFAULT_UNSUBSCRIBE_TEXT` unless an operator
> overrides the wording — Smartlead auto-appends it as the clickable opt-out link on **every** sequence
> step/variant, so no launch can ship an email without a working unsubscribe (CAN-SPAM / SG-PDPA floor).
> A recipient click → `LEAD_UNSUBSCRIBED` → `doNotContact` write-back (the loop the fixtures now prove
> end-to-end). Unit tests + the `e_smoke_live.py` probe both assert it. **Live since Lambda v86
> (2026-07-12).**
>
> **Frontend (E7 — LIVE):** full Phase-E API client (`apps/web/lib/api.ts`); the **Campaign** tab
> (`CampaignTab.tsx`) rewired to live detail — funnel counts / A-B-C variants (edit on draft · winner
> toggle) / per-company cards from `leads[]` with the derived event log / create · launch · pause ·
> resume · sync · per-lead **Move stage** (server allowed-moves guard, 409 on illegal); the **Reply
> queue** (`workspace/replies`) rewired to live `listReplies` + human triage + threaded `respond`; the
> `WorkspaceProvider` seam loads `campaigns`/`replies` live (tab pips derive from them). **`performance-
> summary` v1 LIVE** (Leads funnel + reply stats + needs-attention ① — meeting cells stay `.ph` until
> F5/F6 per EF-Q9). FE `MOVES` reconciled to add **`contacted → replied`**. FE **build + tsc + eslint
> clean.**
>
> **Tests: pytest 300 passed / 18 skipped locally, ruff clean; the Aurora-gated integration tests
> pass against dev Aurora (2×, self-cleaning)** — `test_smartlead.py` (adapter URL/body pins + R1 redaction + backoff),
> `test_campaigns.py` (pure funnel / normalize / dedupe / launch / inbox / statistics / `describe_event`
> — the N1 money-path units), `test_campaigns_db.py` (create→launch→webhook→triage→respond→controls,
> Smartlead fully mocked). Web build green. (Pre-existing `test_openrouter`/`test_prospects_apollo`
> live-API tests flake only under the concurrent full-suite run — real Apollo/OpenRouter rate limits +
> founder-only secrets — and pass in isolation; unrelated to E.)
>
> **Founder-gated (the only remainder):** the **acceptance run** (one real campaign from
> a real approved batch → replies triaged in-app) ticks **S4/S5**. ~~The ship~~ — ✅ **DONE 2026-07-12**:
> commit `d8aef2b`, Lambda **v86** (`build-and-deploy.sh`, `_smartlead_settings` live, `/health` OK),
> `git push origin dev` (weftxio) → Amplify dev **job 55 SUCCEED**. The `{prefix}/smartlead` secret is
> **complete** (`api_key` + `webhook_path_token`, set 2026-07-11; sending-inbox ids in `sending_account`
> `0029`). The E0 live probe is **CLOSED** — every webhook payload + verdict is captured; the disposable
> scratch campaign `3623750` can be deleted (`e_smoke_live.py --delete-id 3623750`).

Turns an **approved batch** into a live Smartlead cold-email campaign and makes the **Campaign** +
**Reply queue** tabs real: the 7-stage funnel with **A/B/C variants** + live open/reply metrics, and a
**cross-campaign reply-triage inbox**. E lights the funnel's top half (contacted→replied→drop) + KPI
plumbing; **F lights the meeting half** (meeting/noshow/billable). That same split places the console's
three remaining mock surfaces (**EF-Q9**): **`performance-summary`** wires in two passes — the Leads
funnel + reply stats (v1) ride E7, the meeting half completes at F5/F6 — while the **client-status
Booking + Feedback tabs** are wholly Phase-F workload (every element derives from `0030` rows). All three
are derived reads — no tables beyond E's `0028`/`0029` + F's `0030`. Table-level schema for E is
**specified in [`data-schema.md`](data-schema.md) → Phase E (`0028` + `0029`, applied)** — schema changes
are recorded there first, per the source-of-truth split.

**EF founder decisions (2026-07-11) — binding** (the §F Q-table pattern; each is carried into the task
rows below — follow these, not older defaults):

| # | Decision |
|---|---|
| **EF-Q1** | **E deploys in two pushes** — push #1 after E4 (migration `0028` + adapter + launch + webhook; deploy + scratch-campaign dev smoke), push #2 after E7 (reply queue + scoreboard + FE tabs). e2e + pytest gate both pushes (Q8 rule). |
| **EF-Q2** | **First live campaign = the FULL approved batch** — no pilot-size rule; exposure is bounded by the daily cap, not list size. The batch comes from the pending S3 founder round (the last A–D gate) — **schedule the S3 round before E7** (2026-07-11), so the acceptance campaign has a real approved batch to consume; it can run in parallel with E0–E6. |
| **EF-Q3** | **Daily cap = the 40/inbox warm-up ceiling from day 1** — premised on the E0 dashboard health check reading excellent; a weak read **degrades the cap, never skips the check**. |
| **EF-Q4** | **Send window = prospect-local business hours** (per-campaign Smartlead schedule, carried in `campaign.settings`). |
| **EF-Q5** | **Booking availability = per-tenant weekly windows ∩ host-calendar free/busy** at slot render (Phase F). |
| **EF-Q6** | **Booking-link TTL = 7 days** — one shared external-token TTL family with `approval_link`; **no automated reminders at MVP** (no scheduler) — the operator re-send from the reply thread IS the reminder. |
| **EF-Q7** | **F0 gates run in parallel with the E build** (no-code founder work: Meet REST conference-records proof on the pooled seats + the availability-windows doc) so F1 starts unblocked the day S4/S5 ticks. |
| **EF-Q8** | **Prod cutover stays at G DoD** — shared dev-tier backend through E/F, per the §After A–G register. |
| **EF-Q9** | **The three remaining mock console surfaces are placed by data dependency (2026-07-11):** `performance-summary` wires in **two passes** — v1 (Leads funnel + reply stats + needs-attention ①) rides **E7 / push #2**; the meeting half (headline band · Meetings held · Billable · calendar · attention ②③) completes at **F5/F6**. The client-status **Booking** + **Feedback** tabs are **wholly Phase-F workload** (F5 read seams + F6 wiring — their data is `0029`-shaped). **G adds no page build** — the completed summary page is the weekly ops read + the live demo surface. All three are pure derived reads; `0028`/`0029` stand unchanged (zero new tables/columns). |

**Posture (locked):**
- **Smartlead = the dumb sender; the HoldSlot DB owns funnel state.** `campaign_lead.stage` is the single
  source of truth; Smartlead events are *inputs* to it, never the record. `prospect.status` is untouched by
  E (funnel state never overloads the sourcing status).
- **Webhook ingest = synchronous insert on the existing `$default` proxy — zero new AWS resources**
  ([SCALE] = SQS+worker at volume).
- **Reply classification is human at MVP** — no LLM anywhere in E (the A–D+ LLM inventory is unchanged).
- **E builds on a live public product** (prod FE rides the shared backend since 2026-07-11): every push
  follows the deploy runbook (expand → migrate-first; contract/constraint → deploy-first), stays
  backward-compatible, and passes the Q8 gates (pytest + 18-e2e green before every push). **Money-path
  branches get a non-Aurora unit test** (the N1 rule).
- **Pattern reuse over new machinery:** the async launch rides the `scoring_job` dispatch pattern
  (Lambda self-invoke + reaper semantics) with `campaign.status` as the job state — **no new job table**;
  the webhook route reuses the approvals public-route posture (high-entropy token, never a 5xx to the
  caller); the adapter mirrors `integrations/apollo`/`openrouter` (lazy secret `{prefix}/smartlead`,
  SnapStart-safe, bounded retry).

**The funnel contract (locked to the FE mock — the design IS the spec).** `campaign_lead.stage` vocabulary
= the mock's `SAMPLE_FUNNEL` ids (`CampaignTab.tsx`): `contacted` (Initial outreach) → `followup`
(Follow-up) → `replied` (Positive reply) → `meeting` → `noshow` → `billable` → `drop` (Drop/DNC).
Transitions run through a **server-side allowed-moves map** mirroring the FE `MOVES` table (an illegal move
= 409); **every move writes an `outreach_event` (`stage_moved`)** so the per-lead log timeline derives from
the ledger, and counts/metrics are **always derived, never stored** (the Phase-D rule). Cross-campaign
**ever-reached** counts (the performance-summary funnel) also derive from the `stage_moved` ledger, never
from current `stage` — a lead now at `meeting` still counts under Replied/Positive. Stage derivation —
Smartlead **does publish `EMAIL_SENT`** (doc-verified 2026-07-11, §API contract below — the old "no
EMAIL_SENT webhook" premise behind risk R3 was wrong); it is used as a *signal*, never as the money-path
record (`contacted` stays worker-set):

| Stage | Derived from |
|---|---|
| `contacted` | set by the launch worker as each lead-add + campaign-start succeeds (a `campaign_lead` row is **inserted only on successful push** — the funnel never shows a lead that wasn't actually sent to Smartlead; relaunch-resume = approved prospects minus existing rows) |
| `followup` | the `EMAIL_SENT` webhook with **`sequence_number ≥ 2`** (the field is documented on every sent/open/click/reply event; the E0 fixture pins it) · fallback = the E6 campaign-statistics poll |
| `replied` | `EMAIL_REPLY` (normalized → internal `lead_replied`, §E4) lands in the Reply queue → **operator triages positive** → `replied`. Negative / OOO / not-interested → `drop`, triage class recorded |
| `drop` | auto on `LEAD_UNSUBSCRIBED` / `EMAIL_BOUNCE` (normalized → `lead_unsubscribed`/`lead_bounced`) · manual on negative triage. **Unsub write-back ⭐:** the address is appended to the brief's `doNotContact` list (the one `ExclusionSet` source), so every future find/enrich/batch excludes it — the SG-PDPA ≤5-day unsub honor rides this (compliance, not a nicety) |
| `meeting`/`noshow`/`billable` | Phase-F writers, riding the same allowed-moves map |

### Smartlead API contract — doc-verified 2026-07-11 (fills in E2; ⚠ = the E0 probe pins it)

Base **`https://server.smartlead.ai/api/v1`** · auth = **`?api_key=` query-param only** (no header option —
R1 redaction is mandatory) · rate limit **~10 req / 2 s** → client-side throttle + exponential backoff on
429, bounded retry (the apollo transport posture). The adapter wraps **exactly these 11 methods, nothing
more**:

| Adapter fn | Smartlead endpoint | Verified detail |
|---|---|---|
| `create_campaign` | `POST /campaigns/create` | `{name, client_id?}` → `{ok, id}`; a fresh campaign can't send until sequences + accounts + leads exist |
| `update_schedule` | `POST /campaigns/{id}/schedule` | `timezone` · `days_of_the_week[]` · `start_hour`/`end_hour` · `min_time_btw_emails` · **`max_new_leads_per_day` = the EF-Q3 cap (40)**; the EF-Q4 prospect-local window lands here |
| `update_settings` | `POST /campaigns/{id}/settings` | tracking / stop-on-reply / unsubscribe text |
| `save_sequences` | `POST /campaigns/{id}/sequences` | `sequences[]`: `{id: null, seq_number, subject, email_body, seq_delay_details: {delay_in_days}}`; **blank `subject` on a follow-up = same-thread "Re:"** (how step 2+ threads); **sequences are locked while the campaign is ACTIVE**; the A/B/C variant sub-structure is under-documented ⚠ (probe pins the `seq_variants`/distribution fields) |
| `add_email_accounts` | `POST /campaigns/{id}/email-accounts` | `{email_account_ids: [...]}` — the tenant's `active` numeric ids from the **`sending_account` table** (`0029`; originally looked up via `GET /email-accounts`), read by `active_sending_account_ids(db, tenant_id)` |
| `add_leads` | `POST /campaigns/{id}/leads` | `lead_list` ≤ **400/req** (`email` required · `first_name`/`last_name`/`company_name`/`custom_fields`…) + `settings` flags — **every `ignore_*` flag stays `false`** (Smartlead's global block + unsubscribe lists are a compliance floor, never bypassed) · `return_lead_ids: true` → store `campaign_lead.smartlead_lead_id`; response count field-names vary across doc pages ⚠ (parse tolerantly) |
| `set_status` | `POST /campaigns/{id}/status` | start / pause / resume (exact enum casing ⚠) |
| `register_webhook` | `POST /campaigns/{id}/webhooks` | `{id: null, name, webhook_url, event_types[], categories[]}`; **event-type strings are inconsistent across Smartlead's own docs** (`EMAIL_REPLY` vs `LEAD_REPLIED` vs `EMAIL_REPLIED`…) ⚠ — the probe records the accepted enum; ingest normalizes via one map (R3) |
| `reply_to_thread` | `POST /campaigns/{id}/reply-email-thread` | `{lead_id, email_body, reply_message_id, email_stats_id, reply_email_time, cc?/bcc?}` — the E5 respond door + the F3 booking-link carrier |
| `fetch_analytics` / `fetch_statistics` | `GET /campaigns/{id}/analytics` · `GET /campaigns/{id}/statistics` | top-level + per-lead rows — the E6 on-read poll (followup fallback + webhook-drift check) |
| `fetch_inbox_replies` | `POST /master-inbox/inbox-replies` | body `offset`/`limit ≤ 20` + `?fetch_message_history=true` → per-message ids + `message_history[]` with direction — **the recovery path for a missing thread handle (R4-b)** |

**Webhook facts (doc-verified):** `EMAIL_SENT` **exists** (+ a `FIRST_EMAIL_SENT` variant) and — like
open/click/reply — carries **`sequence_number`**; the documented `EMAIL_REPLY` payload is `{event_type,
from_email, subject, to_email, to_name, time_replied, reply_body, preview_text, campaign_name, campaign_id,
client_id, sequence_number}` — **no `stats_id`/`message_id` in the documented shape** ⚠ (R4) and **no unique
event id on any event** → the dedupe key is derived (below). **No HMAC/signature exists** (R2 confirmed —
the high-entropy path token IS the auth). **Retries: ≤ 5 attempts, 300 s apart, on any non-2xx** — why
"always 2xx once stored" is load-bearing. Bounce = `EMAIL_BOUNCE` (payload undocumented ⚠ — fixture it).

**Dedupe key (E1/E4):** `smartlead_event_id` = the provider's event id **if the E0 probe finds one in real
payloads**, else a **derived hash** `sha256(campaign_id · to_email · event_type · sequence_number ·
provider timestamp)` computed at ingest — same column, same partial-unique, `0028` unchanged (noted in
`data-schema.md`).

**Reply-handle plan (R4, two paths) — ✅ path (a) CONFIRMED LIVE (2026-07-12):** the real `EMAIL_REPLY`
payload carries **both `stats_id` and `message_id`** (verdict 2), so (a) store them on the event row, done.
(b) absent → recover per reply via `fetch_inbox_replies(fetch_message_history=true)` matched on campaign +
lead email, cache the ids onto the event row — retained as the fallback. Either way **E5 reads the handle
off the stored event row** — the respond door is source-agnostic.

**Simplifications locked by this research:** internal `outreach_event.event_type` keeps OUR lowercase
vocabulary (`lead_replied`/`lead_bounced`/…) with one `_normalize_event()` map absorbing provider-name
drift · `contacted` stays launch-worker-set (the money path never depends on a webhook) · one probe script
(`e_smoke_live.py`) doubles as the post-deploy live smoke · the E0 fixtures are the single test-data source
for E2/E3/E4/E6 units.

| Task | What | Flag |
|---|---|---|
| **E0** | ✅ **RAN + CLOSED 2026-07-12** — all 5 webhook payloads captured live, 3 verdicts CONFIRMED, 5 adapter bugs fixed, unsub link enforced (full digest → the build-status callout above). Original gate spec: Gates (no code): **warm-up health check** — the ~3-week ramp (started 06-17) has **elapsed**; confirm inbox reputation in the Smartlead dashboard, not the calendar — **this check is the hard gate for the EF-Q3 40/inbox cap** (a weak read degrades the cap, never skips the check) · Smartlead secret `{prefix}/smartlead` (`api_key` + **`webhook_path_token`** high-entropy — both set 2026-07-11) + the tenant's **warmed sending inboxes seeded into the `sending_account` table** (`0029`, not the secret; tenant #0 = `20084486`,`20084475`) · A/B/C copy + sequence authored (unsub link + sender identity + suppression honored in-copy; **follow-up steps leave `subject` blank** = same-thread "Re:") · **live-contract probe** ⭐: **`scripts/e_smoke_live.py`** (the `verify_keys`/`c_smoke_live` pattern, idempotent, deletes its scratch campaign) drives the §API-contract table end-to-end on a **scratch campaign against the founder's own inbox**: create → schedule (cap 40 · window) → settings → sequences (2 steps × A/B variants — pins the variant sub-structure ⚠) → add accounts → add 1 lead (founder-owned address) → register webhook → start → reply from the founder's inbox; **capture URL = a throwaway request-bin** (✅ **founder-approved 2026-07-11** — internal testing usage, no risk: the scratch campaign carries only the founder's own identity — "Phase E Test Batch" · HoldSlot · `getholdslot.com` · Jason Tse, Founder — never prospect rows; the real E4 route doesn't exist yet). **Deliverables committed to `tests/fixtures/smartlead/`:** `email_sent_seq1.json` · `email_sent_seq2.json` · `email_reply.json` · `email_bounce.json` (send to a known-bad address) · `lead_unsubscribed.json` · `add_leads_response.json` · `webhook_register_response.json` — plus three recorded verdicts: the **accepted event-type enum** (R3) · the **R4 handle verdict** (does the real reply payload carry `stats_id`/`message_id`?) · the **variant sub-structure** | ⭐ contract risk |
| **E1** | Schema `0028` (expand → migrate-first): `campaign` (1:1 approved batch; **`batch_id` unique + FK RESTRICT** — a campaign-bearing batch becomes undeletable, closing the cascade hole) · `message_variant` (A/B/C copy; `is_winner`; metrics derived) · `campaign_lead` (**`stage` = funnel SoT**; unique(campaign, prospect); carries **`approval_id`** so the billable-evidence chain `prospect_approval → campaign_lead → meeting` stays explicit at every hop) · `outreach_event` (append-only ledger; **partial-unique `smartlead_event_id`** = webhook dedupe — the provider event id if the E0 probe found one, else the §contract derived hash; reply-triage columns). Column detail → `data-schema.md` | |
| **E2** | Smartlead adapter ⭐ `integrations/smartlead` (lazy `{prefix}/smartlead`, SnapStart-safe, bounded retry): **exactly the 11 §API-contract methods, nothing more** · client-side throttle ≤ 10 req/2 s + exponential backoff on 429 · request bodies pinned to the E0 fixtures. **Auth is `?api_key=` query-param — redact the URL in every log/telemetry line** (R1, assert-tested) | ⭐ |
| **E3** | Launch ⭐: `POST /{client}/campaigns` (owner; **409 unless `batch.status = approved`** — the mock's "Approved batches only" rule, server-enforced; **idempotent on `batch_id`** — re-POST returns the existing campaign) creates the draft + variants; `POST /campaigns/{id}/launch` flips `status=launching` and fires the **async worker** (self-invoke; stale `launching` >480s flips `error` on read — reaper semantics, no job table): create Smartlead campaign → add the `decision=approved`, verified-email leads — **the FULL approved batch (EF-Q2, no pilot rule)**, chunked ≤ 400/req (one call at MVP sizes) — **NO `return_lead_ids`** (the live API rejects it; the response is counts-only), so `smartlead_lead_id` is resolved `email→lead.id` from `GET /campaigns/{id}/leads` (E0 bug #2), **every `ignore_*` flag false** — (each success inserts its `campaign_lead` @ `contacted`) → push sequence → set campaign settings incl. **`unsubscribe_text`** (`_smartlead_settings` — the per-email opt-out link Smartlead auto-appends to every step/variant; compliance floor, operator-overridable wording only) → schedule per **EF-Q3/Q4** (`max_new_leads_per_day = 40` · prospect-local `days_of_the_week`/`start_hour`/`end_hour`) → set status start → `sending`. Partial failure = `error` + per-lead results in the event ledger; **re-launch resumes idempotently** (only missing leads are pushed) | ⭐ |
| **E4** | Webhook ingest ⭐ `POST /webhooks/smartlead/{token}` (public; constant-time token compare; **always answers 2xx once the raw event is stored** — a 5xx would trigger Smartlead retry storms): store raw first, then `INSERT outreach_event … ON CONFLICT (smartlead_event_id) DO NOTHING` (key = provider id or the §contract derived hash) → the duplicate does nothing downstream; **`_normalize_event()`** — one map from the probe's accepted provider enum to our internal `event_type` vocabulary (absorbs R3 naming drift) — then the stage move through the allowed-moves map. Unknown campaign/lead → stored + logged, never an error. `EMAIL_OPEN`→variant tally (derived) · `EMAIL_SENT` seq ≥ 2→`followup` · `EMAIL_REPLY`→queue + store the thread handle per the R4 plan · `LEAD_UNSUBSCRIBED`/`EMAIL_BOUNCE`→`drop` + **unsub write-back** | ⭐ |
| **E5** | Reply Queue ⭐ — cross-campaign triage inbox: `GET /{client}/replies` (reads `outreach_event(lead_replied)` ⋈ `campaign_lead`; filters campaign/state; **pip = unhandled count** `handled_at IS NULL`, mirroring the mock) · `POST /replies/{id}/triage` (class + its stage effect: positive→`replied`, negative→`drop`; classes seed from the mock vocabulary — positive / objection-timing / referral / nudge — as strings, never enums) · `POST /replies/{id}/respond` (operator-authored text → `reply_to_thread` with `lead_id` + `email_stats_id` + `reply_message_id` **read off the stored event row** — source-agnostic per the R4 plan → stored `response_body` + a `reply_sent` event; **this is also the F3 booking-link carrier**) | ⭐ |
| **E6** | Variant scoreboard + controls: per-variant open/reply **derived from the event ledger** (no stored counters — same rule as batch counts) · `is_winner` manual toggle (**HoldSlot-side metadata only** — sequences are locked while ACTIVE, no Smartlead write) · pause/resume via `set_status` · a `fetch_statistics`/`fetch_analytics` poll **on console read** (the `followup` fallback + a webhook-drift check) | |
| **E7** | Wire the Campaign + Reply queue tabs (swap `SAMPLE_FUNNEL` / `INITIAL_REPLIES` / `NUDGE_COPY` mocks behind the existing `WorkspaceProvider` seam) · **performance-summary v1 (EF-Q9)** — new derived-on-read **`GET /{client}/performance-summary`** (no stored counters, the Phase-D rule): the **Leads-funnel** block goes fully live (Sourced = `prospect` rows · Approved = approved `prospect_approval` decisions · Contacted = `campaign_lead` rows · Replied = distinct leads with a `lead_replied` event · Positive = ever-reached `replied` via the `stage_moved` ledger · Meeting booked reads **0 until F** writes `meeting` moves) + Weekly-stats **New positive replies** + **Replies awaiting review** (= the E5 pip) + needs-attention **①** client-approval pending (batch sent, undecided — D data, live today); the meeting-dependent cells (headline band · Meetings held · Billable this cycle · Meeting Calendar · attention ②③) **keep their `.ph` placeholders until F5/F6** · e2e additions (campaign create→launch→funnel render · reply triage flow · summary funnel renders live counts) · founder acceptance = **one real campaign from a real approved batch, replies triaged in-app** → tick **S4/S5** | |

**Integration risks (doc-researched 2026-07-11; E0 confirms the ⚠ residue):** **R1** query-param auth
(**confirmed — no header option**) → redact URLs in logs/telemetry, assert-tested. **R2** no webhook HMAC
(**confirmed — none exists**) → high-entropy path token + re-fetch-before-mutate on anything
money-adjacent; retries are ≤ 5 × 300 s on any non-2xx, which makes the always-2xx-once-stored rule
load-bearing. **R3 (re-scoped)** ~~no `EMAIL_SENT` event~~ — it **exists**, with `sequence_number`; the
residual risk is **event-name drift across Smartlead's own docs** (`EMAIL_REPLY`/`LEAD_REPLIED`/
`EMAIL_REPLIED`…) → one `_normalize_event()` map seeded from the probe's accepted enum; `contacted` stays
worker-set regardless. **R4 (RESOLVED 2026-07-12)** — the real `EMAIL_REPLY` payload carries **both
`stats_id` and `message_id`** (verdict 2 CONFIRMED live), so path (a) is the primary: store them on the
event row; `master-inbox/inbox-replies` recovery stays as the fallback. E5 always reads the handle off the
stored event row. **R5** A/B variants are
sequence-step-scoped, not stage-scoped (booking/drop replies are manual threaded sends, HoldSlot-tracked);
the variant sub-structure is the one under-documented request shape ⚠. **R6** only Email is Smartlead-fed
(LinkedIn = [SKIP] — the mock's LinkedIn log channel stays empty at MVP; Calendar = F; Stripe = G). **R7**
daily caps vs the warm-up ramp — `max_new_leads_per_day` + the schedule live in campaign `settings`; never
imply instant send. **R8** webhook payload shape is version-fragile + **no unique event id documented** →
store raw first, dedupe on the derived hash, derive defensively, ignore unknown fields.

### Step-gate test & confirmation matrix (E0→E7) — every step exits through its gate before the next starts

Money-path branches get a non-Aurora unit test (the N1 rule); all units run off the **E0 fixtures** —
one test-data source for the whole phase. One Aurora-gated integration (skips locally, the D pattern):
campaign-from-decided-batch end-to-end.

| Step | Build-time tests (fixtures, no Aurora) | Confirmation gate (observe, then proceed) |
|---|---|---|
| **E0** | — (no code; the probe is idempotent + deletes its scratch campaign) | ✅ **PASSED 2026-07-12** — secret complete on `{prefix}/smartlead` · **all 5 webhook fixtures + 3 API-response fixtures real** + the 3 verdicts recorded (event enum ✅ · R4 handle ✅ path-a · variant shape ✅) + 5 adapter bugs fixed · unsub link enforced. (Warm-up health confirmed in-dashboard.) |
| **E1** | model round-trip units · migration up/down (the `test_migrations.py` pattern) · **dedupe pin**: same `smartlead_event_id` twice → 1 row (partial-unique) · FK pin: deleting a campaign-bearing batch → RESTRICT error | migration `0028` written + reviewed against `data-schema.md`; **the dev-Aurora apply rides push #1** (expand → migrate-first) |
| **E2** | `test_smartlead.py` (the `test_apollo.py` pattern): every method's URL + body pinned to fixtures · **redaction asserts** — no `api_key` in any log/telemetry/exception string (R1) · 429 → backoff → bounded-retry · tolerant parse of the add-leads response variants | `e_smoke_live.py` re-run **through the adapter** against a scratch campaign — all 11 §contract calls succeed |
| **E3** | launch worker off fixtures: **409 unless `batch.status = approved`** · idempotent re-POST (same campaign returned) · **partial-failure resume** — add fails at lead k → re-launch pushes only the gap [money] · `campaign_lead` inserted **only on successful add** [money] · schedule body carries cap 40 + prospect-local window (EF-Q3/Q4) · chunking ≤ 400 · reaper: stale `launching` > 480 s → `error` | pytest + ruff green (no live send yet — E4's smoke is the live proof) |
| **E4** | ingest units off fixtures: constant-time token compare (bad token → 404, no body echo) · **always-2xx once stored** (unknown campaign/lead → 2xx + logged row) · dedupe end-to-end (same event twice = 1 row, 1 stage move) · `_normalize_event()` covers the probe enum + unknown names → stored-not-moved · **the allowed-moves map: every legal AND illegal pair** · `EMAIL_SENT` seq 2 → `followup` · `LEAD_UNSUBSCRIBED`/`EMAIL_BOUNCE` → `drop` + **unsub write-back appends to `doNotContact`** [money/compliance] | **PUSH #1** (migrate `0028` → deploy Lambda → pytest/e2e re-green) then the **live scratch smoke**: re-point the scratch campaign's webhook at the real route → founder's inbox receives seq-1 → sent/open rows land in `outreach_event` → founder replies → `EMAIL_REPLY` row lands **with a usable thread handle** → lead still `contacted` (replied requires triage) |
| **E5** | queue units: pip = `lead_replied AND handled_at IS NULL` count · triage positive → `replied` / negative → `drop` through the moves map · respond stores `response_body` + `reply_sent` event · respond calls `reply_to_thread` with the stored handle [money-adjacent] | triage the scratch reply via dev Swagger → the threaded response **arrives in the founder's inbox, in-thread** |
| **E6** | scoreboard derivation off ledger fixtures (per-variant open/reply, no stored counters) · drift-check unit: a statistics fixture with a webhook-missed `followup` → the poll writes the move | pause → resume the scratch campaign through the console API; the scoreboard renders the scratch events |
| **E7** | summary **ever-reached** unit (a lead at `meeting`/`drop` counts in every stage it passed; a bounced-out lead never reached `replied`) · FE `pnpm build` + tsc + eslint · e2e additions: campaign create→launch→funnel render · reply-triage flow · summary funnel live counts — **baseline 18 + new, all green** | **PUSH #2** → founder acceptance: **one real campaign from the S3-round approved batch, replies triaged in-app** → tick **S4/S5**; delete the scratch campaign |

**Path:** E0 → E1 → E2 → E3 → E4 → **push #1 (migrate + deploy + scratch-campaign smoke)** → {E5·E6} → E7 →
**push #2** (EF-Q1). F0's no-code gates run in parallel throughout (EF-Q7). **E3/E4 = highest-leverage
code; E5 = where the founder works replies daily.** **Cost:** Smartlead Basic **$32/mo**; $0 LLM in E.

---

## Phase F — Book + meeting + feedback (S6 min) · **plan finalized 2026-07-11**

> 🟢 **BUILT — code-complete (2026-07-12), local gates green; deploy + founder gates remain.**
> The full F1–F6 stack is written and passing every non-Aurora gate:
> - **F1** — migration [`20260712_0030_phase_f_meeting`](../infra/alembic/versions/20260712_0030_phase_f_meeting.py)
>   + `BookingLink`/`Meeting`/`FeedbackLink` in `models.py`; `test_migrations.py::test_0030_…` green
>   (head assert bumped to `0030`; FK ondelete money-pins asserted). **Not yet applied to dev Aurora.**
> - **F2** — `app/integrations/google/client.py` (the 6 contract methods, JWT/token-cache/401-remint/
>   backoff/redaction) + `pyproject.toml` gains **`cryptography`** + `tests/test_google.py` (15 cases,
>   FT2-1…12) + `tests/fixtures/google/` (doc-built; overwritten by the probe) + `scripts/f_smoke_live.py`.
> - **F3** — `app/domains/meetings/{service,schemas,public}.py` (booking slots · never-404 state · atomic
>   claim → create_event → meeting row → stage move; feedback token routes) + the `respond_reply`
>   `include_booking_link` carrier. Public routes mounted in `main.py`.
> - **F4** — `sweep_meetings` (on-read poll) + `POST /meetings/refresh` + the `POST /meetings/{id}/outcome`
>   owner-correction door; the whole qualify/billing rule is pure in `service.py` (unit-tested off the F2
>   fixtures) — held/duration/`amount`/dispute-window/`is_billable`, idempotent `WHERE held IS NULL` claim.
> - **F5** — `GET /meetings?when=` · `/bookings` · `/feedback` · feedback-send · inform-client (all sweep
>   first); public feedback GET/POST; the grown `GET /performance-summary` (headline · held · billable ·
>   show-up · attention ②③ · calendar feed; funnel "Meeting booked" = ever-reached).
> - **F6** — all 8 FE surfaces wired to `lib/api.ts` (book · feedback · client-status booking/feedback ·
>   billing ledger · recaps via `WorkspaceProvider.reloadMeetings` · performance-summary + `MeetingCalendar`)
>   + the reply-queue "Include booking link" checkbox; `e2e/meetings.spec.ts` (FE-1…9) + the `_mock.ts`
>   fixtures. **`tsc` + `eslint` clean.**
>
> **Local gates green:** backend `pytest` **336 passed / 22 skipped** (the 22 Aurora-gated =
> `test_meetings_db.py` + the E DB tests); `ruff` clean (app/tests + `f_smoke_live.py`); FE `tsc` + `eslint`
> clean. **Deviations from the plan (flagged per "be flexible"):**
> 1. **Test split** — the DB-flow FT3/FT4/FTI money cases (claim atomicity, release-on-fail, approval
>    snapshot, sweep-qualify, feedback single-use) live in **`test_meetings_db.py`** (Aurora-gated,
>    `_FakeGoogle`/SL/SES mocked), not `test_meetings.py`, because the codebase has **no non-Aurora DB
>    harness** (PG-specific `PgUUID`/`JSONB`); the pure branches (slots, qualify, billing matrix, link
>    state, derivations — the bulk of FT3-8/FT4/FT5) ARE non-Aurora in `test_meetings.py` (20 cases).
> 2. **FD-1 default TZ** = `Asia/Singapore` (UTC+8, the existing campaign-schedule default) when
>    `brief.data.availability.tz` is absent; the founder authors the real one at F0.
> 3. **Link TTL** reuses `config.approval_ttl_seconds` (7 days) for booking + feedback links — no new
>    config const (the EF-Q6 family).
> 4. **Booking-link carrier** — the primary path is the **reply-queue "Include booking link" checkbox**
>    (an operator replies to an interested prospect), plus the client-status **Propose-new-time** re-send.
>
> **Remaining (deploy + human gates — NOT run this session):** apply `0030` to dev Aurora → **push #1**
> (deploy Lambda w/ `cryptography` → `f_smoke_live.py` → run `test_meetings_db.py` against dev) · **F0**
> founder real-Meet + availability doc + FD sign-off · **push #2** (FE + `pnpm build` + Playwright 18+9 in
> a clean env — a dev server currently holds the workspace) · **FA** whole-phase acceptance → tick **S6**.

> **Kickoff readiness (2026-07-12, post-E-ship): NEXT FRONT — plan finalized + execution-researched; F1 is unblocked.**
> - ✅ **E is SHIPPED** (2026-07-12): commit `d8aef2b` pushed · Lambda **v86** live (`_smartlead_settings`
>   unsub link included; `/health` OK) · Amplify dev **job 55 SUCCEED** at `d8aef2b`. Only the founder
>   **S4/S5 acceptance run** remains (real campaign off the S3-round batch) — it does NOT gate F1 code.
> - ✅ **Google creds ready** — `holdslot/prod/google` verified (SA + domain-wide delegation + Calendar +
>   Meet REST v2 all 200, 2026-06-10). F2's adapter has its secret; no new AWS resources (on-read poll).
> - ✅ **Schema pre-specified** — `data-schema.md` → Phase F carries the `0030` tables (`booking_link` ·
>   `meeting` · `feedback_link`); F1 is expand→migrate-first, same pattern as `0028`/`0029`.
> - ✅ **All EF decisions locked** — billing rule (approval + ≥10 min + 48h dispute), booking-link TTL
>   (7 days, no reminders — EF-Q6), availability source (per-tenant weekly windows ∩ Calendar free/busy —
>   EF-Q5), qualified-meeting definition. Derived-on-read throughout (no stored counters/`billable`).
> - ✅ **Execution research DONE (2026-07-12)** — the §Google API contract, §repo seams, §FD defaults,
>   §execution build table and §step-gate matrix below were researched (official Google docs + full repo
>   inventory) so the F build has **zero unresearched external dependencies**.
> - ✅ **Test cases DESIGNED (2026-07-12)** — the §test-case register below gives every step a binary
>   pass gate (FT/FP/FTI/FE blocks + the FA whole-phase acceptance). **The build rule: a step exits only
>   when its register block is green; the next step does not start before.**
> - ⏳ **F0 founder gates only (no-code, EF-Q7):** one real Meet → read its `conference-records` on the
>   pooled seats + author the availability-windows doc + confirm the §FD defaults (F0-C1…C5).
> - **Step 1 = F1** (`0030` migration) → F2 (Google adapter) → F3 (booking flow). **Cost:** +$0 (Google
>   Workspace already in the floor; Stripe deferred to G). **One new runtime dep: `cryptography`** (RS256
>   for the SA JWT — see §Google contract).

Lights the funnel's bottom half: booking + the meeting become real (Calendar event + Meet link + invites;
held + duration via **Meet REST v2**), the two terminal stages feed the *Billing ledger* + *Meeting recaps*
tabs, and the **feedback loop** (missing from the earlier F cut — the ledger's Feedback column and the
external `feedback/[token]` page both need it) closes qualification context. F also owns the console's
remaining client-facing reads (**EF-Q9**): the **client-status Booking + Feedback tabs** (today the
`B_LOG`/`F_LOG` mocks) and the **performance-summary completion** (headline band · Meetings held ·
Billable this cycle · Meeting Calendar · needs-attention ②③ — the meeting half the E7 v1 left as `.ph`).
All are derived reads off `0028`/`0029` rows — **zero new tables/columns**. Table-level schema →
[`data-schema.md`](data-schema.md) → Phase F (planned, `0030`).

**Locked billing rule (the hinge):** a meeting's outcome derives once from Meet metadata — **client
approval (the E1 `campaign_lead.approval_id` chain) AND held ≥ 10 min → `qualified`, stage `billable`,
`amount` = $500** · held < 10 min → `short_call` · never held → `noshow` (the mock ledger's exact vocabulary
Qualified / Short call / No-show). The full spec adds a **48-hour dispute window** before the $500 bills
(backend-development-plan §7): the *columns* land at F1 (`dispute_window_ends_at = ended + 48h`,
`disputed`), but **`billable` is never stored — it is derived on read** (`qualified AND window passed AND
NOT disputed`), the same expiry-on-read posture as every token. The ledger's billing chip = **Held** inside
the window · **Billed** past it (a computed amount, not a charge — Stripe = [SKIP→G]) · **Not billable**
otherwise.

**Posture (locked):**
- **Zero new AWS resources.** Meet ingest is an **on-read poll**: any console read of Recaps/Ledger (plus a
  Refresh button) sweeps meetings past their scheduled end with `held IS NULL` through the Meet REST read —
  no Pub/Sub, no EventBridge ([SCALE] = Workspace Events → Pub/Sub at volume).
- **Token pattern reuse:** `booking_link` + `feedback_link` mirror `approval_link`/`password_reset`
  exactly — SHA-256 `token_hash` only · expiry checked on read (no scheduler) · atomic single-use claim
  (`UPDATE … WHERE used_at IS NULL`). Feedback answers (rating 1–5 · chips · comment — the mock's exact
  fields) live **on the `meeting` row** (1:1) — no separate feedback table.
- **Google adapter mirrors apollo/openrouter** (lazy `{prefix}/google` — SA + domain-wide delegation +
  Calendar + Meet REST all verified ✅ 2026-06-10). Meetings are hosted by the **pooled HoldSlot operator
  seats** (§cost) so Meet REST yields conference records.
- **HK timezone discipline:** every Google timestamp is parsed UTC-pinned (the R16/N18 lesson — naive ISO
  parsed browser-local shifted day-groups by 8h); slots render in the prospect's timezone, stored UTC.

| Task | What | Flag |
|---|---|---|
| **F0** | Gates (no code — **runs in parallel with the E build, EF-Q7**): Meet REST `conference-records` scope proven on the pooled seats (one real meeting → read its record) · booking-link lifetime = **7 days, no automated reminders** (✅ decided EF-Q6 — operator re-send is the reminder) · availability source = **per-tenant weekly windows (an `approval_template`-style doc) ∩ Calendar free/busy at slot render** (✅ decided EF-Q5), feeding the mock's day-tabs × slots grid with `taken` masking · qualified-meeting definition reconfirmed (approval + ≥10 min + 48h window) | |
| **F1** | Schema `0030` (expand → migrate-first): `booking_link` (per replied `campaign_lead`) · `meeting` (`google_event_id` · `meet_link` · `scheduled_at` · `conference_record_id` · **`held` NULL = not-yet-ingested (the poll's claim guard)** · `duration_min` · `outcome` · `amount` · `dispute_window_ends_at` · `disputed` · feedback cols · `won` · **`approval_id` snapshot** — billing evidence stays explicit end-to-end) · `feedback_link` | |
| **F2** | Google adapter ⭐ `integrations/google`: Calendar `events.insert` (`conferenceDataVersion=1`, `hangoutsMeet`, `sendUpdates=all` — invites buyer + client) · free/busy read (F0 slots) · Meet REST v2 conference-records read (held / duration / participants) | ⭐ |
| **F3** | Booking flow: mint + send the booking link on a `replied` lead (threaded through E5's respond door — one carrier) → public `GET /book/{token}` (slots from the F0 source; valid/expired states) + `POST /book/{token}` (**atomic single-use claim** → Calendar event → `meeting` row → stage `meeting`). **The same hook fires on a manual `replied→meeting` funnel move** — one code path | ⭐ |
| **F4** | Ingest + qualify ⭐ — **the one billing rule, unit-tested off Meet fixtures (the N1 rule)**: the on-read poll fills `held`/`duration_min`/`conference_record_id`, then derives outcome/stage/`amount`/`dispute_window_ends_at` exactly once (**idempotent — guarded `WHERE held IS NULL`**, the same claim shape as the token pattern); a later correction is an explicit owner action, not a re-derive | ⭐ |
| **F5** | Ledger + Recaps + feedback seams: `GET /{client}/meetings?when=upcoming\|past` (**Upcoming** = `held IS NULL AND scheduled_at ≥ now` with the Meet join link · **Past** = ingested) · ledger rows **derived** from `meeting` ⋈ `campaign_lead` ⋈ `campaign`/`batch` (Date · Meeting with · Campaign/Batch · Outcome · Feedback · Status · Amount — the mock's columns; feedback state = Received / Pending (live link) / None) · post-meeting: mint `feedback_link` → public `GET/POST /feedback/{token}` (stars + chips + comment onto the meeting row; single-use). **LLM `meeting_summary` = [SKIP→later]** — recap detail fields render as pending until it lands. **Status/summary read seams (EF-Q9):** `GET /{client}/bookings` (`booking_link` ⋈ `meeting` ⋈ `campaign_lead` — chips Invites sent / Meetings accepted / Expired unused; per-row status **derived on read**: Confirmed = meeting row exists · Awaiting confirm = live unused link · Expired = past-TTL unused, the expiry-on-read posture; the invitation preview renders the stored `response_body` of the `reply_sent` event that carried the link — one carrier) · the feedback feed derives off `meeting` feedback cols + `feedback_link` (Forms sent / Responses / Average rating · Awaiting vs Received · **overdue = pending > 5 days, computed on read** — no scheduler) · the E7 summary endpoint **grows its meeting fields**: headline (**Qualified meetings booked** last-30d + delta vs prior-30d · **show-up rate** = held ÷ ingested · **awaiting this week** = `held IS NULL AND scheduled_at` in-week) · **Meetings held** (week) · **Billable this cycle** (sum of derived-`billable` amounts) · needs-attention **②** open/expired booking links **③** feedback pending · the calendar month feed off `meeting.scheduled_at` (UTC-pinned, the R16/N18 lesson) | |
| **F6** | Wire Meeting recaps + Billing ledger tabs (swap `RECAPS`/`LEDGER` mocks) + the external **book**/**feedback** pages (their first real backend — today they are pure client-side mocks) + **client-status Booking tab** (swap `B_LOG`: the F5 feed drives the chips + status-log cards + invitation preview; **Propose new time** on an Expired row = revoke-prior + re-mint through F3's one carrier, threaded on the stored `reply_message_id`) + **client-status Feedback tab** (swap `F_LOG`: chips + history table; **Send Follow-Up** re-sends the live feedback link · **Inform client** = a low-rating SES note to the Brief's attendee email — both reuse the D send door, operator-manual, no scheduler) + **performance-summary completion** (swap the `FUNNEL` const + placeholder cells + the `MEETINGS` calendar mock; needs-attention ②③ live; **copy reconciliation:** ②'s "one reminder is scheduled" + ③'s "feedback gates billing" mock lines are amended — no scheduler exists (EF-Q6) and billing is gated by the held-≥10-min + 48h-window rule, feedback is context) · e2e (book valid→success→expired · feedback submit · ledger render · booking/feedback status tabs + completed summary render) · founder acceptance: **self-book a real Meet, hold it 10 min, watch it qualify + land on the ledger AND the performance summary** → tick **S6** (+ read-only **S7** ledger) | |

**One `meeting` row feeds every read surface:** Campaign funnel (stage) · Billing ledger (outcome/amount/billing
chip; Stripe later) · Meeting recaps (upcoming/past · feedback · `won`; LLM summary later) · the EF-Q9 reads
(booking-tab status · feedback history · summary headline/calendar). **Path:**
F0→F1→F2→F3→F4→F5→F6. **F4 + the booking-token claim are the only [money] branches — both unit-tested
without Aurora.** **Cost:** Google Workspace ~**$15/mo** (already in the floor); $0 Stripe until G.

### Google API contract — doc-verified 2026-07-12 (fills in F2; ⚠ = the F2 live probe pins it)

Two Google surfaces, ONE adapter (`app/integrations/google/`): **Calendar v3** (event + Meet create ·
free/busy) and **Meet REST v2** (conference records — held/duration evidence). Auth = **service-account
JWT (RS256) + domain-wide delegation** — no OAuth consent flow, no Google client library. Secret
`holdslot/prod/google` (✅ all-200 2026-06-10 via `verify_keys.py --only google`): envelope
`{service_account_json, delegated_subject, scopes}` (or a raw SA JSON — `verify_keys.check_google`
accepts both; fallback subject `info@tryholdslot.com`). The **DWD grant in the Workspace admin console is
frozen to exactly two scopes** — `https://www.googleapis.com/auth/calendar` +
`https://www.googleapis.com/auth/meetings.space.readonly` — and they cover ALL of F (events.insert ·
freeBusy · conferenceRecords · participants). Adding any scope string = founder admin-console
re-authorization (propagation up to 24h) — don't.

**Token flow (per Google's service-account HTTP/REST doc; `verify_keys.google_access_token` is the
working reference, but it signs via an `openssl` subprocess — a script trick, NOT the app pattern):**
JWT header `{"alg":"RS256","typ":"JWT"}` · claims `iss=client_email · sub=delegated_subject (the
impersonated host seat) · scope="<the two scopes, space-joined>" · aud="https://oauth2.googleapis.com/token"
· iat=now−60 · exp≤iat+3600 (1h hard max)` → `POST https://oauth2.googleapis.com/token` with
`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=<jwt>` → `{access_token, expires_in≈3600}`
→ `Authorization: Bearer` on every call. **In-app signing = `pyjwt` (already a dep) + `cryptography`
(the ONE new runtime dep — pyjwt's RS256 backend; manylinux2014 wheels exist so the wheel-only
`build-and-deploy.sh` compile picks it up from `pyproject.toml` automatically, N22).** Cache the token
module-level with an expiry-refresh (~60s early); **never `@lru_cache`** (tokens expire); never log the
token or `private_key` (R1-style redaction asserts).

| Adapter fn | Endpoint | Verified contract |
|---|---|---|
| `access_token()` | `POST oauth2.googleapis.com/token` | flow above; bounded retry on 5xx; 401 at an API call → drop cache, re-mint once |
| `create_event` | `POST /calendar/v3/calendars/primary/events?conferenceDataVersion=1&sendUpdates=all` | `primary` = the impersonated `delegated_subject`'s calendar (the host seat). Body: `summary` · `description` · `start`/`end` = `{dateTime: RFC3339, timeZone}` · `attendees: [{email}]` (prospect + Brief attendee — **populating attendees REQUIRES DWD, confirmed in the reference**; `sendUpdates=all` makes Google send the invite emails) · `conferenceData: {createRequest: {requestId: <uuid4, idempotency key>, conferenceSolutionKey: {type: "hangoutsMeet"}}}`. Response: `id` → `meeting.google_event_id` · `hangoutLink` → `meeting.meet_link` · `conferenceData.conferenceId` = **the 10-char meeting code `abc-defg-hij`** (== Meet REST `space.meeting_code` — THE correlation key; also the last path segment of `hangoutLink`) · `conferenceData.status.statusCode`: **`pending` → `success` (conference creation is async ⚠)** — if `pending`, re-read via `get_event` (bounded, ~3×) before trusting `hangoutLink`/`conferenceId` |
| `get_event` | `GET /calendar/v3/calendars/primary/events/{eventId}` | the pending re-read |
| `freebusy` | `POST /calendar/v3/freeBusy` | body `{timeMin, timeMax (RFC3339), timeZone: "UTC", items: [{id: delegated_subject}]}` → `calendars.<id>.busy: [{start, end}]` (start inclusive, end exclusive); per-calendar `errors[]` (`notFound`…) — treat a calendar error as "no availability", never 500 |
| `list_conference_records` | `GET meet.googleapis.com/v2/conferenceRecords?filter=space.meeting_code = "abc-defg-hij"` | filterable: `space.meeting_code` · `space.name` · `start_time` · `end_time`; record fields: `name` = `conferenceRecords/{id}` → `meeting.conference_record_id` · `startTime` (**always set**) · `endTime` (**unset while the conference is ongoing** — the sweep must skip) · `expireTime` (**records auto-delete 30 days after end** — GR4) · `space`. A record exists **iff someone actually joined** — no record = the no-show signal |
| `list_participants` | `GET meet.googleapis.com/v2/conferenceRecords/{id}/participants` | per participant: `earliestStartTime` · `latestEndTime` (null while active) · union `signedinUser {user: "users/{id}", displayName}` / `anonymousUser` / `phoneUser` — the held/duration evidence (⚠ probe pins whether the host seat is identifiable via `signedinUser`) |

**Scope semantics (why `.readonly`):** `meetings.space.created` is principal-scoped — it only sees spaces
the token's user created and **silently returns empty** otherwise; `.readonly` reads any record the
impersonated user can access (host or attendee). We impersonate the host seat AND create the events as it,
so either would work — `.readonly` is what's verified + granted; keep it.

### FD defaults — micro-decisions the locked plan left open (recommended defaults; founder confirms at F0, none blocks the build start)

| # | Question | Recommended default (build this unless F0 overrides) |
|---|---|---|
| **FD-1** | Where do the per-tenant availability windows live? (`0030` is locked at 3 tables — no new table) | **`brief.data.availability`** (opaque JSONB, no migration — the `targetMarket` precedent): `{tz, meeting_minutes: 30, windows: {mon: [["10:00","18:00"]], …}}`; **code default Mon–Fri 10:00–18:00 host TZ** when absent. Edited via the existing brief PUT |
| **FD-2** | What counts as **held**? (a host who waits alone 15 min must NOT bill $500) | `held = a conference record exists AND ≥2 participants`. `duration_min = ceil((record.endTime − record.startTime)/60)`; ⚠ if the probe shows the host is identifiable (`signedinUser`), refine `duration_min` to the **non-host** participant's presence (`latestEndTime − earliestStartTime`) — the money-safe measure |
| **FD-3** | When is a no-show decided? (a record may not exist *yet*) | sweep verdicts `noshow` only past `scheduled_at + 24h` with no record; between scheduled-end and +24h the row stays `held IS NULL` ("awaiting" on the summary) |
| **FD-4** | Does a **manual** `replied→meeting` console move create a `meeting` row? | **No** — a bare stage move (it already works via `moveLeadStage`); the public booking claim is the ONLY `meeting`-row writer at MVP. Recaps/Ledger/Calendar derive from `meeting` rows only |
| **FD-5** | Slot geometry | next **5 weekdays** starting ≥24h out (min-notice) · slots = FD-1 windows cut into `meeting_minutes` steps ∖ free/busy `busy[]` · returned as **UTC ISO instants**; the FE groups by the *viewer's* local day (the mock's "Times shown in your local timezone") |
| **FD-6** | Booking claim vs Google failure ordering | claim the token FIRST (`UPDATE … WHERE used_at IS NULL` — blocks a double-book race), then `create_event`; on a Google hard-fail **release the claim** (`used_at = NULL`) + 503 so the prospect can retry — mirrors N31's "don't persist what didn't send" |
| **FD-7** | `feedback_link` TTL | same **7-day** token family (EF-Q6 / `approval_ttl_seconds` precedent) |
| **FD-8** | Recap "Recording" link | stays `.ph` placeholder at MVP — real recording files need the **Restricted** `drive.meet.readonly` scope (app-verification friction) + a Drive read; deliberate [SKIP→later] alongside the LLM `meeting_summary` |

### Repo seams — as-built inventory (2026-07-12) the F build touches

**Backend patterns to copy (exact carriers):**

| Pattern | Where (verbatim) |
|---|---|
| Token mint/hash | `core/security.py` — `new_opaque_token()` (`secrets.token_urlsafe(32)`) · `hash_token()` (SHA-256 hex) · `as_utc()` for every expiry compare |
| Atomic single-use claim | `approvals/router.py::decide_approval` — `update(ApprovalLink).where(id==, used_at.is_(None)).values(used_at=now)`; `rowcount == 0` → **410 GONE**. View endpoint **never 404s** — returns `state: valid\|expired\|used` (no tenant-existence leak) |
| Send-before-persist (N31) | `batches/router.py::send_approval` — render → mint token → `send_email` (SES via `core/email.py`, returns bool) → only on accept: revoke prior live links → insert the new link row |
| Public router | `approvals/router.py` (no prefix, no `{client}`, no auth dep) + `campaigns/webhooks.py` (path-token, `hmac.compare_digest`, 404); mounted plainly in `main.py` |
| Adapter shape | `integrations/smartlead/client.py` — stdlib `urllib` transport (NO httpx/requests at runtime) · `@lru_cache` `_secret()` reading `{prefix}/google` w/ env override (`HOLDSLOT_GOOGLE_SA`) · `_RETRYABLE={429,500,502,503,504}` + exp backoff · non-default `USER_AGENT` · redaction (`_redact` + `Error.__init__` scrub) · `reset_secret()` |
| Adapter tests | `tests/test_smartlead.py` — layer (a) `monkeypatch _request` → URL/body pins per method; layer (b) fake `urlopen` → retry/redaction/log asserts (caplog at DEBUG) |
| Stage move writer | `campaigns/router.py::record_stage_move(db, lead, target, via=…)` — checks `svc.is_legal_move` (`MOVES`: `REPLIED→[FOLLOWUP, MEETING, DROP]` · `MEETING→[REPLIED, BILLABLE, NOSHOW, DROP]` · `NOSHOW→[MEETING, REPLIED, DROP]` · `BILLABLE→[MEETING, DROP]`), writes the `stage_moved` event; `move_lead_or_409` = the console 409 wrapper |
| Booking-link carrier | `campaigns/router.py::respond_reply` (`POST /{client}/replies/{event_id}/respond`) — reads the thread handle off the stored event (`svc.reply_handle`), calls `sl.reply_to_thread`, stores `response_body` + a `reply_sent` event. **F3 extends THIS door** |
| Money constants | module-level in the owning domain (`launch.DEFAULT_DAILY_CAP=40`, `scoring.MAX_JOB_AGE_SECONDS=480` — the precedent for `PER_MEETING_USD=500` in `domains/meetings/service.py`); NOT `config.Settings` |
| Migration 0030 | mirror `0028` (`op.create_table` + `_tenant_fk()` helper + `UUID/PK/NOW` aliases; raw `op.execute` only needed for partial-uniques — F has none, `token_hash` is a plain unique); bump `tests/test_migrations.py::test_single_alembic_head` → `["0030_…"]` + add `test_0030_…_match_migration` column/constraint asserts |
| Aurora-gated integration | `tests/test_campaigns_db.py` — `pytest.mark.skipif(not HOLDSLOT_DB_CLUSTER_ARN)` + fully-mocked provider (`_FakeSmartlead` via monkeypatch) + self-cleaning ephemeral tenant |
| Live-probe script | `scripts/e_smoke_live.py` (the pattern for `f_smoke_live.py`); `verify_keys.py --only google` already 200s both APIs |

**Frontend seams (F6 wiring map — file → mock to swap → wire to):**

| Surface | File | Swap | Wire to |
|---|---|---|---|
| External book | `app/[client]/(external)/book/[token]/page.tsx` | `DAYS`/`SLOTS`/`TAKEN` consts; **token is never read today** | `useParams` token → `getBookingView(token)`; pass `forceExpired = view.state !== "valid"` to `ExternalShell` (the `approve/[token]` page is the exact wiring exemplar); slots grouped by viewer-local day; confirm → `submitBooking` |
| External feedback | `app/[client]/(external)/feedback/[token]/page.tsx` | keep `LABELS`/`CHIPS` (they ARE the design vocab); token never read today | `getFeedbackView(token)` + `submitFeedback(token, {rating, chips, comment})`; `forceExpired` |
| Client-status Booking | `app/[client]/(console)/client-status/booking/page.tsx` + `lib/fixtures/client-status.ts` | `B_LOG`/`BookingRow` | `GET /{client}/bookings` — chips (Invites sent/Accepted/Expired unused) + per-row derived status + invitation preview = the stored `response_body`; **Propose new time** (Expired rows) → `respondReply(…, {include_booking_link: true})` — the one carrier, so the feed must return each lead's latest reply-event id |
| Client-status Feedback | `…/client-status/feedback/page.tsx` + same fixtures | `F_LOG`/`FeedbackRow` | `GET /{client}/feedback` — chips + history rows + `overdue` (>5d, computed on read); **Send Follow-Up** → `sendFeedbackForm(meetingId)`; **Inform client** → `informClient(meetingId)` |
| Billing ledger | `…/workspace/billing/page.tsx` + `lib/workspace/fixtures.ts` | `LEDGER` const **+ the page's hardcoded Date/"Meeting with"/Campaign-Batch cells** (they're not in `LedgerRow`) | `GET /{client}/meetings?when=past` rows; Amount renders `amount` when the derived chip = Billed; CSV export goes live; `PER_MEETING_USD=500` (`lib/workspace/constants.ts`) stays the display const |
| Meeting recaps | `…/workspace/summaries/page.tsx` + `components/workspace/WorkspaceProvider.tsx` | provider `recaps: useState(RECAPS)` — the ONLY mock left in the provider | add a meetings loader (`reloadMeetings`) → recap cards derive (feedback · `won` · Qualified badge); detail fields (Attendees/Discussed/Next step/Sentiment/Recording) stay pending per FD-8/[SKIP→later] |
| performance-summary | `…/performance-summary/page.tsx` | the `.ph` cells (headline ×3 · Meetings held · Billable · attention ②③) — **the funnel is already live from E7**, there is no FUNNEL const here | the grown `getPerformanceSummary` fields; **copy amendments (locked):** ② drop "one reminder is scheduled" (no scheduler, EF-Q6) · ③ drop "feedback gates billing" (billing gates on held-≥10-min + 48h window) |
| Meeting calendar | `…/performance-summary/MeetingCalendar.tsx` | `MEETINGS` const (react-big-calendar) | month feed off `meeting.scheduled_at` — parse ISO **with the Z suffix** (the R16/N18 UTC lesson); viewer-local render is then correct |
| API client | `lib/api.ts` | — | public fns mirror `getApproval`/`decideApproval` (bare `fetch`, `state` discriminator); console fns mirror `listCampaigns`/`respondReply` (`authFetch`); `PerformanceSummaryApi` grows the meeting fields |

### Phase F execution build table (the build-session checklist; every row exits through its §step-gate)

| Step | Builds | Key spec (carry verbatim) | Flag |
|---|---|---|---|
| **F1** | Migration `20260712_0030_phase_f_meeting` + models `BookingLink`/`Meeting`/`FeedbackLink` in `models.py` | The 3 tables EXACTLY per `data-schema.md` → Phase F (`booking_link` · `meeting` incl. outcome/amount/dispute/feedback/`won`/`summary` cols · `feedback_link`); FKs: `meeting.approval_id → prospect_approval` **no cascade** (the evidence snapshot) · `campaign_lead_id`/`prospect_id` SET NULL nullable; model conventions = `_uuid_pk()`/`_tenant_fk()`/`_created_at()`; statuses plain strings. **Expand → migrate-first**: apply `0030` to dev Aurora before the push-#1 deploy | |
| **F2** | `app/integrations/google/client.py` (+ `pyproject.toml` gains **`cryptography`**) + `tests/test_google.py` + fixtures + **`scripts/f_smoke_live.py`** | Exactly the 6 §contract methods, nothing more; token cache w/ expiry refresh; redaction asserts (no Bearer/private_key in any log/error string); throttle/backoff = the apollo posture. **The live probe (the E0 lesson — 5 bugs came from doc-built adapters):** create a scratch event on the host seat (founder as attendee) → assert `statusCode`/`conferenceId`/`hangoutLink` → freebusy read → after the F0 real meeting: records + participants read → **fixtures committed to `tests/fixtures/google/`** (`event_insert_response.json` · `event_insert_pending.json` if seen · `freebusy_response.json` · `conference_records_response.json` · `participants_response.json`) + recorded verdicts: ① is `statusCode` ever `pending` in practice ② is the host identifiable in `participants[].signedinUser` (drives FD-2's refinement) ③ can one meeting code carry >1 record (GR5). Probe deletes its scratch event | ⭐ |
| **F3** | `app/domains/meetings/` (`service.py` + `router.py` console + `public.py` token-only, mounted in `main.py`) + the `respond_reply` extension | **Mint+send (one carrier):** `RespondIn` gains `include_booking_link: bool` — server revokes the lead's prior live links (approval resend ladder), mints (`new_opaque_token`/`hash_token`, TTL 7d = EF-Q6), URL `{web_base_url}/{slug}/book/{token}`, appends/substitutes into the reply text, sends via the EXISTING `reply_to_thread` path, **link row persists only after Smartlead accepts** (N31). **Public:** `GET /book/{token}` → never-404 view `{state, host/duration display bits, slots[]}` (slots per FD-1/FD-5: windows ∩ `freebusy`, UTC ISO). `POST /book/{token} {slot}` → **atomic claim → re-check slot free → `create_event` (attendees = prospect + Brief attendee; `sendUpdates=all` sends the invites) → pending re-read → insert `meeting` row (`approval_id` snapshotted OFF `campaign_lead.approval_id`; `scheduled_at` UTC) → `record_stage_move(lead, MEETING, via="booking")`** — `book_meeting()` is the one meeting-row writer (FD-4); Google hard-fail after claim → release claim + 503 (FD-6). Illegal-state rules: link's lead not in a bookable stage → still bookable (the operator sent it deliberately); expired/used → 410 on POST, `state` on GET | ⭐ |
| **F4** | `service.sweep_meetings(db, tenant)` + `POST /{client}/meetings/refresh` + the owner-correction door `POST /{client}/meetings/{id}/outcome` | **The one billing rule, unit-tested off the F2 fixtures (N1):** sweep = rows `held IS NULL AND scheduled_at + meeting_minutes < now()`: meeting code = last path segment of `meet_link` → `list_conference_records`; ongoing (`endTime` unset) → skip; ended → `list_participants` → **held per FD-2** → ONE guarded claim `UPDATE meeting SET held, duration_min, conference_record_id, outcome, amount, dispute_window_ends_at WHERE id = ? AND held IS NULL` (idempotent — the token-claim shape); no record + past FD-3 grace → `held=false, outcome='noshow'` + stage→`noshow`. **Outcome:** `held AND duration_min ≥ 10` → `qualified` (+ stage→`billable` via the moves map); `held AND < 10` → `short_call` (stage stays); **`amount = PER_MEETING_USD (500)` + `dispute_window_ends_at = record.endTime + 48h` stamp ONLY when `approval_id` is present** — no approval evidence, no amount, never billable. **`billable` never stored** — `is_billable(m) = outcome=='qualified' AND amount IS NOT NULL AND dispute_window_ends_at < now() AND NOT disputed`; ledger chip Held (in-window) / Billed (past) / Not billable. Correction = the explicit owner door (re-derives amount/window; never the sweep) | ⭐ |
| — | **PUSH #1** | apply `0030` → deploy Lambda (picks up `cryptography`) → `f_smoke_live.py` against dev → pytest + 18-e2e green (Q8) | |
| **F5** | Read seams: `GET /{client}/meetings?when=upcoming\|past` · `GET /{client}/bookings` · `GET /{client}/feedback` · `POST /{client}/meetings/{id}/feedback/send` · `POST /{client}/meetings/{id}/inform-client` · public `GET/POST /feedback/{token}` · the grown `GET /{client}/performance-summary` | Every console meetings/bookings/feedback/summary read **runs the F4 sweep first** (the on-read poll — zero new AWS resources). Shapes per the §F5 task row above + the FE wiring map: meetings rows carry prospect/company/campaign/batch names + `meet_link`/held/duration/outcome/amount/billing-chip/dispute/feedback-state/`won`; bookings rows carry derived status (Confirmed = meeting exists · Awaiting = live unused · Expired = past-TTL unused) + invitation preview (`response_body`) + the lead's latest reply-event id; feedback feed computes `overdue = pending > 5 days` on read; feedback-send = mint `feedback_link` (FD-7) + SES to the prospect (send-before-persist), operator-manual — needs-attention ③ is the nudge surface, no scheduler; inform-client = SES to the Brief attendee (low-rating context). Public feedback POST = atomic claim → write `feedback_rating/chips/comment/feedback_at` onto the meeting row. Summary grows: headline (qualified last-30d + delta vs prior-30d · show-up rate = held ÷ ingested · awaiting this week) · Meetings held (week) · Billable this cycle (Σ `is_billable` amounts) · attention ② (open/expired unused links) ③ (held meetings w/o feedback) · calendar month feed (`scheduled_at` UTC ISO) | |
| **F6** | The FE wiring map above, end-to-end + e2e additions | All 8 surfaces + `lib/api.ts` fns; e2e adds: book valid→success + expired · feedback submit + expired · ledger renders live rows · booking/feedback status tabs render · summary meeting cells render (mock-routed via `e2e/_mock.ts` — baseline 18 + new, all green) | |
| — | **PUSH #2** | FE + read seams live → **founder acceptance: self-book a real Meet through a real reply thread, hold it 10 min, watch it auto-qualify + land on the ledger AND the performance summary** → tick **S6** (+ read-only **S7** ledger) | |

### Step-gate test & confirmation matrix (F0→F6)

| Step | Build-time tests (fixtures, no Aurora) | Confirmation gate (observe, then proceed) |
|---|---|---|
| **F0** | — (no code) | founder: one real Meet on the pooled seat → its `conference-records` + `participants` read 200 (probe verdict ② lands here) · availability-windows doc authored (FD-1 shape) · FD-1…FD-8 confirmed or overridden · qualified-rule reconfirmed (approval + ≥10 min + 48h) |
| **F1** | model↔migration match test (`test_0030_…`) · head assert bumped · FK pins: `meeting.approval_id` survives batch/campaign deletes (no cascade); `booking_link → campaign_lead` CASCADE | `0030` applied to dev Aurora (expand → migrate-first); `alembic heads` = `0030` |
| **F2** | `test_google.py`: every method URL/query/body pinned · JWT claims pin (iss/sub/scope/aud/exp≤1h) · token-cache expiry refresh · 401→re-mint-once · 429/5xx backoff bounded · **redaction asserts** (no token/private_key in logs/errors) · pending-statusCode re-read | `f_smoke_live.py` all-green against the real host seat; fixtures + 3 verdicts committed |
| **F3** | booking units: mint revokes prior live links [money-adjacent] · link row only after send accepts (N31) · GET never-404 state machine (valid/expired/used) · slot math off freebusy fixtures (windows ∩ busy, UTC, min-notice) · **POST claim atomicity — second POST → 410, one meeting row** [money] · claim-release on Google failure (FD-6) · `approval_id` snapshot correctness [money] · stage move `replied→meeting` writes `stage_moved` · illegal-move 409 untouched | dev Swagger round: respond-with-link on the scratch reply → link lands in-thread → self-book → Calendar event + invite emails arrive + `meeting` row + stage `meeting` |
| **F4** | qualify units off the F2 fixtures (N1): held/FD-2 branches (record+2 participants ≥10min → qualified+500+window · <10 → short_call, no amount-stamp without `approval_id` [money] · no record past grace → noshow · ongoing → skipped) · **sweep idempotence — second sweep changes nothing** (`WHERE held IS NULL`) [money] · `is_billable` window/dispute matrix · stage effects through the moves map | **PUSH #1** → `f_smoke_live` re-run through the deployed Lambda; the F0 real meeting's row qualifies correctly on a console read |
| **F5** | derivation units: bookings status triple (Confirmed/Awaiting/Expired — expiry-on-read) · feedback overdue >5d · summary ever-reached meeting fields (show-up rate ÷ ingested; Σ billable) · feedback POST claim single-use · calendar feed UTC-pinned | dev Swagger: all reads render the F0/F3 real rows; feedback-send email arrives; public feedback submit lands on the meeting row |
| **F6** | FE `pnpm build` + tsc + eslint · e2e baseline 18 + the new book/feedback/ledger/status/summary specs green | **PUSH #2** → founder acceptance (the S6 tick, §above); prod FE follows at the usual cadence |

### Phase F test-case register (designed 2026-07-12 — the per-step pass gates)

**The rule: a step EXITS only when its whole block below is green (plus its §matrix observation gate);
the next step does not start before.** IDs: `FT<step>-n` = build-time tests (fixtures, no Aurora) ·
`FP-n` = `f_smoke_live.py` live-probe assertions · `FTI-n` = Aurora-gated integration
(`test_meetings_db.py`, Google/Smartlead/SES fully mocked — proves OUR logic, the `test_campaigns_db.py`
posture) · `FE-n` = Playwright e2e (mock-routed via `e2e/_mock.ts`) · `FA-n` = the whole-phase founder
acceptance. Test files: `tests/test_migrations.py` (FT1) · `tests/test_google.py` (FT2) ·
`tests/test_meetings.py` (FT3/FT4/FT5) · `tests/test_meetings_db.py` (FTI) · `apps/web/e2e/meetings.spec.ts`
(FE). `[money]` rows are the N1-rule branches — they may never ship untested.

**F0 — founder confirmations (no code; recorded, not automated):**

| ID | Check |
|---|---|
| F0-C1 | one real Meet held on the pooled host seat; `verify_keys.py --only google` still all-200 |
| F0-C2 | that meeting's `conferenceRecords` read returns ≥1 record with `startTime` + `endTime` set |
| F0-C3 | its `participants` read shows every joiner; **record verdict ②** — is the host identifiable via `signedinUser`? |
| F0-C4 | availability-windows doc authored in the FD-1 shape (`tz` · `meeting_minutes` · `windows.mon…fri`) |
| F0-C5 | FD-1…FD-8 each confirmed or overridden in writing; qualify rule reconfirmed (approval + ≥10 min + 48h) |

**F1 — migration `0030` + models:**

| ID | Case (Given → When → Then) |
|---|---|
| FT1-1 | alembic script dir → `get_heads()` → exactly `["0030_phase_f_meeting"]` (bump the existing head assert) |
| FT1-2 | `BookingLink.__table__` columns → compare → EXACT `data-schema.md` column set (id · tenant_id · campaign_lead_id · token_hash · expires_at · used_at · created_at) |
| FT1-3 | `Meeting.__table__` → EXACT column set incl. outcome/amount/dispute_window_ends_at/disputed/feedback_*/won/summary |
| FT1-4 | `FeedbackLink.__table__` → EXACT column set |
| FT1-5 | FK semantics pins: `meeting.approval_id` ondelete **RESTRICT/no-cascade** · `meeting.campaign_lead_id`+`prospect_id` **SET NULL** · `booking_link.campaign_lead_id` **CASCADE** · `feedback_link.meeting_id` **CASCADE** |
| FT1-6 | unique constraints present: `booking_link.token_hash` · `feedback_link.token_hash` |
| FT1-7 | `downgrade()` drops exactly the 3 tables in reverse-FK order (script structural pin) |

**F2 — Google adapter (`test_google.py`; transport monkeypatched, the `test_smartlead.py` two-layer pattern):**

| ID | Case |
|---|---|
| FT2-1 | JWT claim pin: decoded assertion carries `iss`=client_email · `sub`=delegated_subject · `scope`= the two scopes space-joined · `aud`=token URL · `exp−iat ≤ 3600` |
| FT2-2 | token POST body pin: `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer` + `assertion`; response parses `access_token` |
| FT2-3 | token cache: 2nd call inside expiry → NO 2nd token POST; forced-expired cache → re-mints |
| FT2-4 | API call returns 401 → cache dropped → ONE re-mint + replay → then raise (no retry storm) |
| FT2-5 | `create_event` pin: `POST …/calendars/primary/events?conferenceDataVersion=1&sendUpdates=all`; body carries `start/end{dateTime,timeZone}` · `attendees[{email}×2]` · `createRequest{requestId, hangoutsMeet}` |
| FT2-6 | response parse: `id`/`hangoutLink`/`conferenceId`/`statusCode`; **`pending` fixture → bounded `get_event` re-reads (≤3) → `success`; still pending → typed error** |
| FT2-7 | `freebusy` pin: body `{timeMin,timeMax,timeZone:"UTC",items:[{id:subject}]}`; parses `busy[]`; a per-calendar `errors[]` fixture → typed "no availability" result, never an exception escape |
| FT2-8 | `list_conference_records` pin: `filter=space.meeting_code = "…"` URL-encoded; parses records; `endTime`-absent (ongoing) fixture handled |
| FT2-9 | `list_participants` parse: `earliestStartTime`/`latestEndTime` + all three user-union arms (signedin/anonymous/phone) |
| FT2-10 | **redaction [compliance]**: no `access_token`/`private_key` fragment in ANY log line (caplog DEBUG) or exception string |
| FT2-11 | 429/5xx → exponential backoff → bounded retries (`_MAX_RETRIES+1` calls) → typed error |
| FT2-12 | secret shapes: env override `HOLDSLOT_GOOGLE_SA` wins; envelope `{service_account_json, delegated_subject, scopes}` AND raw-SA JSON both parse (the `verify_keys.check_google` contract) |

**F2 live probe (`f_smoke_live.py` — run before ANY code trusts the adapter; the E0 lesson):**

| ID | Assertion |
|---|---|
| FP-1 | token mint 200 on the real secret |
| FP-2 | `freebusy` 200; `busy[]` present for the host seat |
| FP-3 | scratch event created (founder attendee, +2 days) → `statusCode` reaches `success` · `conferenceId` == `hangoutLink` tail → **fixture `event_insert_response.json`** (+ `event_insert_pending.json` if seen — verdict ①) |
| FP-4 | `get_event` re-read 200, same ids |
| FP-5 | the F0 meeting's records read → ≥1 record → **fixture `conference_records_response.json`**; note if >1 record for one code (verdict ③ / GR5) |
| FP-6 | its participants read → **fixture `participants_response.json`**; record verdict ② (host identifiable?) |
| FP-7 | probe cleans up: script-local `DELETE …/events/{id}?sendUpdates=none` on its scratch event (delete stays OUT of the 6-method adapter) |

**F3 — booking flow (`test_meetings.py`; Smartlead/Google/SES mocked):**

| ID | Case |
|---|---|
| FT3-1 | respond w/ `include_booking_link` → token minted · URL = `{web_base_url}/{slug}/book/{token}` · `{{booking_link}}` placeholder substituted (no placeholder → appended) |
| FT3-2 | re-mint revokes the lead's prior live links (approval resend ladder) → ≤1 live link per lead |
| FT3-3 | **[money-adjacent]** `reply_to_thread` raises → NO `booking_link` row persisted (N31 ordering) |
| FT3-4 | respond WITHOUT the flag → byte-identical E5 behavior, no link row (regression pin) |
| FT3-5 | GET unknown token → 200 `{state: "expired"}`-class view; NO 404, NO tenant/prospect data (the approvals never-404 posture) |
| FT3-6 | GET valid → `state:"valid"` + slots + display bits (duration · host); response carries nothing beyond the allow-list |
| FT3-7 | GET past-`expires_at` → `expired`; `used_at` set → `used` |
| FT3-8 | slot math off freebusy+windows fixtures: windows ∖ busy · ≥24h min-notice · 5 weekdays · UTC instants; HK-TZ windows convert correctly (the R16/N18 pin) |
| FT3-9 | freebusy typed-error → `slots: []`, page state stays `valid` (never 500) |
| FT3-10 | **[money]** claim atomicity: two POSTs, same token → 1st 200 + ONE meeting row · 2nd **410** · still ONE row |
| FT3-11 | **[money]** Google hard-fail AFTER claim → `used_at` released back to NULL + 503 → a retry then succeeds (FD-6) |
| FT3-12 | POSTed slot no longer free on the re-check → 409 + claim released + no event created |
| FT3-13 | **[money]** meeting row: `approval_id` == the lead's `campaign_lead.approval_id` snapshot · `scheduled_at` stored UTC · `google_event_id`/`meet_link` from the response |
| FT3-14 | stage: lead at `replied` → moves to `meeting` (`stage_moved` written, `via="booking"`); lead at a stage where the move is illegal → **booking still succeeds, move skipped + logged** (the operator sent the link deliberately) |
| FT3-15 | **[money]** tampered slot (ISO not in the offered set / outside windows) → 400, no event, claim released |

**F4 — sweep + qualify (the money branch; every case runs off the FP fixtures):**

| ID | Case |
|---|---|
| FT4-1 | rows not yet due (`scheduled_at + meeting_minutes` in future) → untouched |
| FT4-2 | ongoing record (`endTime` unset) → skipped; `held` stays NULL |
| FT4-3 | **[money]** ended record · ≥2 participants · 47 min · `approval_id` set → `held=true · duration_min=47 · outcome=qualified · amount=500 · dispute_window_ends_at=end+48h` · stage `meeting→billable` + `stage_moved` |
| FT4-4 | duration 7 min → `short_call` · amount NULL · NO stage move |
| FT4-5 | **[money]** boundary: exactly 10 min → `qualified` (≥, not >) |
| FT4-6 | ended record with ONE participant (host alone) → NOT held (FD-2); before FD-3 grace → stays NULL; past grace → `noshow` |
| FT4-7 | no record + past 24h grace → `held=false · outcome=noshow` · stage→`noshow` |
| FT4-8 | no record + before grace → stays NULL ("awaiting") |
| FT4-9 | **[money]** qualified duration but `approval_id` NULL → `outcome=qualified` · **amount NULL · never billable** |
| FT4-10 | **[money]** idempotence: same sweep twice → 2nd run changes NOTHING (`WHERE held IS NULL` claim) |
| FT4-11 | `is_billable` matrix: qualified+amount+window-passed+undisputed → true · in-window → false (chip **Held**) · `disputed` → false · short_call/noshow → false |
| FT4-12 | multi-record code (GR5 fixture) → deterministic pick = longest-duration record overlapping `[sched−60min, sched+24h]` |
| FT4-13 | *(conditional on verdict ②)* host identifiable → `duration_min` = the non-host participant's presence |
| FT4-14 | owner-correction door: overrides outcome → amount/window re-derived + audit event; **the sweep never touches a row with `held` already set** |
| FT4-15 | duration rounding: `ceil((end−start)/60)` across an hour boundary |

**F5 — read seams:**

| ID | Case |
|---|---|
| FT5-1 | `?when=upcoming` = `held IS NULL AND scheduled_at ≥ now` (join link present) · `past` = ingested; both invoke the sweep first (spy assert) |
| FT5-2 | ledger row derivation: prospect/company/campaign/batch names joined · billing chip derived (Held/Billed/Not billable) · amount present only when stamped |
| FT5-3 | bookings status triple off one fixture set: meeting exists → **Confirmed** · live unused → **Awaiting confirm** · past-TTL unused → **Expired** (computed on read); chips == row counts |
| FT5-4 | bookings row carries the invitation preview (= the `reply_sent` `response_body` that carried the link) + the lead's latest reply-event id (the Propose-new-time handle) |
| FT5-5 | feedback feed: Awaiting (live link, no `feedback_at`) vs Received; `overdue` flips at pending > 5 days exactly |
| FT5-6 | feedback-send door: mints `feedback_link` (7d TTL) · revokes prior live · **SES fail → no row** (N31) · re-send re-mints |
| FT5-7 | inform-client door: SES to the Brief attendee email w/ rating context; no state change |
| FT5-8 | public feedback GET state machine = FT3-5/6/7 shapes |
| FT5-9 | **[money-adjacent]** public feedback POST: atomic claim (2nd POST 410) · writes `feedback_rating/chips/comment/feedback_at` onto the meeting · rating 0/6 → 422 |
| FT5-10 | summary growth off a cross-window fixture: qualified last-30d + delta vs prior-30d · show-up rate = held ÷ ingested · awaiting-this-week · Meetings held (week) · Billable this cycle = Σ `is_billable` amounts · ② open+expired unused links · ③ held w/o feedback · calendar feed = UTC-`Z` ISO strings |
| FT5-11 | funnel "Meeting booked" = **ever-reached** `meeting` via the `stage_moved` ledger (a lead now at `billable` still counts) |

**F5/F3 integration (`test_meetings_db.py`, Aurora-gated, self-cleaning, runs 2×):**

| ID | Case |
|---|---|
| FTI-1 | seed tenant → approved batch → campaign_lead @`replied` w/ approval → respond+link (fake SL) → GET book (slots) → POST book (fake Google) → meeting row + stage `meeting` |
| FTI-2 | …sweep w/ fake records (qualified path) → ledger/bookings/feedback/summary reads all render the row with derived chips/counts |
| FTI-3 | …feedback-send (fake SES) → public feedback GET/POST → rating lands on the meeting row; 2nd POST 410 |

**F6 — e2e additions (`e2e/meetings.spec.ts`, mock-routed; baseline 18 must stay green):**

| ID | Case |
|---|---|
| FE-1 | book valid: mocked view+slots → day tabs render viewer-local · pick slot · confirm → success pane echoes the slot |
| FE-2 | book expired **via API state** (not just `?state=`) → expired pane (`forceExpired` wiring proof) |
| FE-3 | feedback: no rating → inline error; rating+chips+comment → success pane |
| FE-4 | feedback expired via API state |
| FE-5 | billing ledger renders live rows (Amount only on Billed) + CSV export non-empty |
| FE-6 | recaps render from provider meetings; detail fields show pending (FD-8) |
| FE-7 | client-status Booking: chips + rows + **Propose new time only on Expired rows** → fires the respond carrier (mock asserted) |
| FE-8 | client-status Feedback: chips + **Send Follow-Up gated on overdue** + **Inform client gated on rating ≤3** |
| FE-9 | performance-summary meeting cells render mocked numbers + the calendar renders the month feed |
| FE-10 | full suite: baseline 18 + FE-1…9 green · `pnpm build` + tsc + eslint clean |

### Final whole-phase confirmation (FA — the S6 acceptance run, founder + build session together)

Run AFTER push #2, on the live dev stack, as one scripted sitting; every row must pass. SQL nudges (via
rds-data on the scratch rows) stand in for waiting out real clocks — never code changes.

| # | Step | Pass = |
|---|---|---|
| FA-1 | respond to a real reply thread w/ booking link | email arrives **in-thread**, link resolves |
| FA-2 | open the link (incognito) + pre-place a busy block on the host calendar | valid pane; the busy slot is **masked**; times render viewer-local |
| FA-3 | book a slot | success pane · Calendar event on the host seat · **invite emails arrive** (prospect + Brief attendee) · Meet link joins |
| FA-4 | console after booking | lead stage `meeting` · Upcoming pane shows the row + join link · summary "awaiting this week" ticks |
| FA-5 | hold the Meet ≥10 min, 2 participants, then leave | — |
| FA-6 | console read (or Refresh) | row: held ✓ · duration ≥10 · outcome **Qualified** · amount **$500** · chip **Held** · stage `billable` · funnel + headline update |
| FA-7 | client-status Booking tab | row **Confirmed**; invitation preview shows the sent text |
| FA-8 | feedback-send → submit the public form (rating 4 + chips) | email arrives · ledger Feedback → **Received** · avg rating updates |
| FA-9 | re-open both used links | booking → used/expired pane · feedback → used pane (single-use proof) |
| FA-10 | SQL-nudge `dispute_window_ends_at` past | chip flips **Billed** · Billable-this-cycle sums it |
| FA-11 | book a 2nd slot, never join; SQL-nudge `scheduled_at` −25h; read | outcome **No-show** on the ledger · stage `noshow` |
| FA-12 | full gates | pytest (all FT/FTI) green · e2e (18+10) green · ruff clean |

**FA-12 green + FA-1…11 observed → tick S6 (+ read-only S7 ledger). Phase F is DONE; G starts.**

### Integration risks (Google — doc-researched 2026-07-12; GR = carry into the build)

**GR1 scope freeze** — the DWD admin-console grant lists exactly the two verified scopes; any new scope
string (e.g. Drive for recordings) = founder re-auth + up-to-24h propagation → FD-8 skips recordings.
**GR2 async conference create** — `createRequest` may return `status.statusCode = "pending"`; re-read the
event before storing `meet_link`/code (probe verdict ①). **GR3 principal-scoped `.created`** — the
`meetings.space.created` scope silently returns empty for non-creator tokens; we use `.readonly` + the
host-seat subject (F0 proves on the real seats). **GR4 record expiry** — conference records auto-delete
**30 days** after end; the on-read sweep at console cadence beats it by construction, but a >30-day
abandoned tenant would lose evidence → the sweep result is *persisted once* on the `meeting` row (the
claim), never re-read. **GR5 multi-record codes** — one meeting code can in principle yield several
conference records (rejoin after everyone left); deterministic pick = the record with the longest
duration overlapping `[scheduled_at − 60min, scheduled_at + 24h]` (probe verdict ③ pins whether this
occurs). **GR6 attendees need DWD** — confirmed: service accounts can only populate `attendees[]` under
domain-wide delegation; we always impersonate. **GR7 late records** — a prospect may join late; never
verdict `noshow` before the FD-3 24h grace. **GR8 RS256 dep** — `cryptography` is the one new wheel;
`verify_keys`' openssl-subprocess is NOT portable into Lambda code. **GR9 timezone discipline** — every
Google timestamp parses UTC-pinned (the R16/N18 lesson); slots ship as UTC instants; only the FE renders
local.

---

## Phase G — Run & close (human) · **refined 2026-07-11**

Work the live loop: meeting → pitch the live product (**the product IS the demo** — the prospect on the call
is looking at the same console that sourced them, with the **performance-summary page fully live since F as
the proof surface**; per EF-Q9, G adds no page build) → close → onboard. **DoD: 6 signups over H1 (Oct'26 →
Mar'27).** No new build; everything G touches is already live:

- **Onboard = one wired flow:** switcher "Create client" → `POST /clients` (real since G5/N45·Q5) → fill
  Brief + ICPs → Generate Scope → the whole A→F loop runs for the new tenant (schema was multi-tenant from
  day 0). **The 2nd paying tenant is the trigger** for the two deferred SCALE seams: the `person`
  enrich-once cache (data-schema SCALE tables) and real per-tenant masking/billing expectations.
- **Billing stays manual at G:** the F ledger computes amounts (Billed/Held chips); **Stripe** (activation
  $400 + subscription + $500 metered + $3 overage — backend-development-plan §7) lands when the first signup
  needs a real invoice, not before.
- **Ops cadence (the founder's week):** Reply queue daily · **the performance-summary page IS the weekly
  read** (funnel · calendar · billable + the needs-attention queue), alongside the ledger · monthly KPI vs
  the §11 growth model (signups / meetings / adopter-vs-churn mix). Signals: booked-rate per 100 contacted below
  model → revisit copy/ICP before touching code; unsub/bounce spikes → pause + list hygiene (the E4
  write-back is the floor, not the ceiling).

---

## Open gates & pending register

| Item | Ticks | Status |
|---|---|---|
| Founder Brief→Scope round (dev) | S1 | ✅ folded into D+ review #5 (signed off 2026-07-10) |
| Founder live Apollo round (find→enrich→batch; reads real `cost_usd`) | S2 | ✅ folded into D+ review #5 (signed off 2026-07-10; Apollo credit-dashboard glance rides the next enrich round) |
| Founder live batch round (create→send masked link→approve) | S3 | ⏳ operational — infra live; **schedule before E7** (EF-Q2 — the E acceptance campaign consumes this approved batch; runs in parallel with E0–E6) |
| **D+ (sourcing + scoring + UX)** — §D+ above; shipped end-to-end (review #5 ✅ · V2-4 ✅); **§D+.5 fix wave (F1–F7) ✅** + **final fix wave G1–G7 (56 findings) ✅** (two pushes → Lambda v78 + migration `0027`), then the **close-out push shipped dev + PROD** (Lambda **v79** · Amplify dev 53 / prod 20; §D+.6); Q7 re-score list confirmed empty; **review cycle CLOSED** | pre-E | ✅ shipped (dev + prod) · ✅ review closed |
| Warmed inboxes ready | E0 | ramp **elapsed** (started 06-17, ~3 weeks) — E0 confirms reputation/health in the Smartlead dashboard, not the calendar |
| **A follow-ups (non-blocking):** custom MAIL FROM ✅ (D0) · prod isolation deferred (Amplify `main`→dev until cutover) · manual deploy (CI/CD later) · Aurora scale-to-zero vs 30s timeout (prod sets min ACU ≥0.5) · S3 state bucket public-access-block (prod) · refresh-token rotation now re-checks `UserStatus` + is single-use guarded (N9/N33 ✅) | — | tracked |
| **Deferred ICP inputs (search-side; already used for *scoring*):** `technologies`→Apollo tech-UIDs (**resolver BUILT in D+ Stage 4** — `tech_vocab` → `currently_using_any_of_technology_uids`) · `revenue_range` (no ICP form field) · funding-stage key **confirmed absent from the documented API** (2026-07-08) | — | post-MVP / D+ |
| **Backlog:** step-3 console decide UI (the `decide_batch` endpoint + `decideBatch` client fn exist, tested; no UI) · `person` enrich-once cache (lands with tenant #2) · move `reloadBatches` onto the TanStack-Query cache | — | optional |

---

## After A–G complete

- **Production isolation** (cutover, not rewrite — Terraform is workspace-parameterised). `terraform workspace new prod` → `apply` → prod `aurora_min_acu ≥ 0.5` → fresh prod JWT keys → `alembic upgrade head` + seed → SES prod sandbox-exit → point Amplify `main` at prod → harden (S3 PAB, CI/CD). Trigger: Phase G DoD met (**timing reconfirmed 2026-07-11, EF-Q8** — shared dev-tier backend stands through E/F).
- **LLM usage rollup** — aggregate `llm_call` across every phase/`purpose` into a tenant×purpose×model×month panel + spend alarm. `llm_call` stays the single source; the rollup is derived. Valuable only once calls span every phase.

### Production cutover register (deferred hardening — folds in the deleted `prod-cutover-checklist.md`)

Findings deliberately deferred to the prod cutover — not applied on the shared dev-tier backend now, because
most add or tighten AWS resources (zero-new-resources posture) and would risk the running dev Lambda. Each
has an **in-code note pointing here**. Work these when standing up the production workspace:

| # | Where | Do at cutover |
|---|---|---|
| **N20** | `terraform/lambda.tf` (`api_async`) | Add `destination_config { on_failure { destination = <SQS/SNS ARN> } }` + a CloudWatch alarm on `AsyncEventsDropped` + `DestinationDeliveryFailures`, so a silently-dropped background job pages, not just surfaces on a user re-poll. |
| **N52** | `terraform/iam.tf` (`lambda_secrets`) | Replace the `${secrets_prefix}/*` wildcard with the exact secret ARNs the app reads (`.../app`, `.../openrouter`, `.../apollo`); verify the live Lambda still starts. |
| **N54** | `terraform/apigw.tf` (`default` stage) | Add `default_route_settings { throttling_burst_limit, throttling_rate_limit }` sized to expected load, so the gateway sheds excess instead of amplifying it into Lambda concurrency + spend. |

**Other cutover hardening:** **N3** (done — Aurora `deletion_protection = true` + `final_snapshot_identifier`;
confirm it survives the prod-workspace apply — to intentionally destroy, flip protection off in a separate
apply first) · **N53** (done — `amplify.yml` preBuild fails when `NEXT_PUBLIC_API_BASE_URL` is unset; confirm
the prod branch sets it to the real API base) · **e2e in CI** (wire `pnpm exec playwright test` as a blocking
deploy gate — currently a manual pre-push gate, Q8; baseline 18/18) · **Aurora min-ACU** (scale-to-zero is a
dev cost choice; prod may want a warm floor ≥ 0.5 to avoid the "Resuming" first-call latency) · **S3 PAB**
(confirm public-access-block on any bucket introduced at cutover — none today) · **fresh prod JWT keys** (mint
prod-only `jwt_signing_key`/`jwt_refresh_key` — never reuse dev) · **`HOLDSLOT_SEED_PASSWORD`** (needed only to
bootstrap a fresh DB, migration 0002 — see `infra/README.md`, N50).

**Deploy runbook (recap):** backend before frontend; **migration order depends on the change** (see the
`[[deploy-process]]` note): expand → `alembic upgrade` then deploy · contract OR add-a-constraint-old-code-
violates → deploy the Lambda first, then `alembic upgrade`. Push #1 of the G-wave applied `0027` (a constraint
add) with the **deploy-first** order for exactly that reason; push #2 (G5–G6) added no migration.

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

**Total: ~$195/mo typical** (low ~$160, high ~$235; ≈1,520 HKD). **Honest floor before Apollo Pro** (warm-up phase, no live sourcing): **~$55–65/mo.** Apollo is the cost lever, but **search (company + people) is FREE** — the ONLY credit spend is **`people/match` enrich on the gate-2 selected set** (phone off). So cost control = enrich only the confirmed set + dedup-before-enrich; **find width is free to widen** (bounded only by latency, not credits).

---

## Accounts, keys & sending infrastructure

**Secrets** in AWS Secrets Manager (`138743894336`), one JSON per platform under `holdslot/prod/*`; verified by [`verify_keys.py`](../apps/api/scripts/verify_keys.py) (`--strict` at the phase that needs them).

| Secret | Status | Confirms |
|---|---|---|
| `holdslot/prod/app` | ✅ | JWT signing+refresh, ≥32 chars, distinct |
| `holdslot/prod/openrouter` | ✅ | key valid; $50 cap; **non-US models only** (each call site pins its own list) |
| `holdslot/prod/apollo` | ✅ | **Professional + master key**; all 3 endpoints 200 |
| `holdslot/prod/smartlead` | ● | `api_key` + `webhook_path_token` (set 2026-07-11). Sending-inbox ids do NOT live here — moved to the `sending_account` table (`0029`) |
| `holdslot/prod/google` | ✅ | SA + domain-wide delegation + Calendar + Meet REST all 200 |

**Sending infra (the long pole, gates E):** Smartlead-native warm-up + Google Workspace mailboxes on a
dedicated lookalike domain **`getholdslot.com`** (cold mail never goes from `tryholdslot.com`). 2 mailboxes
(`jason.tse@`, `jason.wong@`), all DNS verified (MX/SPF/DKIM/DMARC), Smartlead warm-up enabled (40/day ceiling,
+5/day ramp). **Clock: started 2026-06-17 → ramp elapsed** (E0 confirms reputation in-dashboard); real sends 5–10/inbox/day → ~25. MVP =
**one domain** ([SCALE] adds a 2nd). Still to do: do-not-email suppression list · A/B/C copy (before week-3 sends).

---

## API surface (live — the one shared backend)

Auth = JWT Bearer; tenant scope via `require_membership()` on every `/{client}/…` route (non-members → **404**).
`+Owner` = owner-gated. Live inventory at **`/docs`**. Routers + the routes that matter per phase:

| Router | Routes (key) |
|---|---|
| `auth` | `POST /auth/{login,refresh,forgot,reset}` (public) |
| `clients` | `GET /me·/clients` · `POST /clients` · `GET /{client}/context` |
| `briefs` | brief GET/PUT · `POST /{client}/brief/structure` (async) + status/preview · `GET /research-spec` |
| `icps` | CRUD `/{client}/icps` |
| `prospects` | **(largest, ~22)** list `/prospects`·`/companies` (cursor-paged) · `select`·`update-fields` · `find-people`·`facets`·`scope-override` (per-ICP, kind people\|company) · **`enrich-score-async`** (merged Reveal & score — **the only credit spend**) · `…-async` find/scoring + poll (6 job kinds) · `research-runs` · `sourcing-docs` (rubrics) |
| `batches` (**D**) | `GET/POST /{client}/batches` · `GET /{id}` (company-grouped) · `POST /{id}/decide` (owner step-3) · `DELETE /{id}` (cascade) · `GET/PUT /approval-template` · `POST /{id}/send` (mint link + SES) |
| `approvals` (**D**, public token-only) | `GET /approve/{token}` (masked) · `POST /approve/{token}/decide` |
