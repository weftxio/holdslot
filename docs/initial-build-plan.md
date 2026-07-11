# HoldSlot — Initial Build Plan (dogfood MVP)

> **Stop buying sales tools. Start buying meetings.** Done-for-you, pay-per-qualified-meeting B2B outbound.
> This plan is the **dogfood MVP**: the single-tenant outbound → booked-meeting loop, pointed at HoldSlot's
> own market, so HoldSlot sells itself. Scoped cut of the full spec in
> [`backend-development-plan.md`](backend-development-plan.md).

> **Status (2026-07-11): A–D live on `dev`; D+ complete through V2-4 (review #5 signed off).** Aurora
> **head `0027` applied to `dev`** · backend deployed to `dev` (find-path Stages 1–4 +
> Scoring v2 + **V2-4 contraction** + classifier→Flash) · web **Amplify `dev`**. The Apollo **find → score → select → enrich → batch → masked
> client-approval** loop is live end-to-end. **Phase D+** (the pre-E hardening block — §below) folds three
> workstreams into one: **scope alignment** (sourcing width, Stages 1–4), **Scoring v2** (the 0–100 AI Score
> replaced by 4 labels `contact_now`/`contact_soon`/`low_fit`/`excluded_by_rules` + a liveness gate — this
> doc now carries the whole spec, the standalone `holdslot-scoring-spec-v2.md` was folded in + deleted; **V2-4
> retired the v1 `fit_score`/`fit_tier` path entirely** — 5 sync twin endpoints + the v1 fit module deleted,
> columns dropped in `0026`), and the **Find-flow UX rebuild** (U1–U4 + the merged **Reveal & score** action).
> **What's left before Phase E:** nothing in the fix backlog — both hardening waves are **DONE + deployed**.
> The **§D+.5 code-review fix wave** (executed 2026-07-10 across F1–F7; all 31 resolved bar
> R21/R27-queries/R30-tests) and the **final pre-production review (2026-07-11)** — 56 findings (3 P1 · 19 P2
> · 34 P3), phases **G1–G7** — are built, committed, and **deployed across two pushes** (dev Lambda **v78** +
> migration **`0027`** applied + Amplify prod FE job 52); see **§D+.6** below (both `final-fix-plan.md` and
> `prod-cutover-checklist.md` were folded in here + deleted). The **Q7 re-score candidate list is empty**
> (confirmed 2026-07-11 against dev Aurora — 0 geo-excluded rows; the one divergence-prone tenant has 0
> companies; no data remediation needed). Only the **prod-cutover register** (deferred infra hardening —
> §After A–G) remains. Then **Phase E (outreach +
> Smartlead)**, still gated on warmed inboxes (warm-up running since 2026-06-17). S3 (batch round) is the
> only untouched A–D gate (S1/S2 folded into review #5 ✅).

**Source-of-truth split (read these for depth; this doc is the plan, not the spec):**
- **Schema** — [`data-schema.md`](data-schema.md) governs every table/column (Apollo contract + all DB tables, head `0027` applied to dev). Update it first on any schema change.
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
| **D+** | Sourcing + Scoring + UX | ✅ **built + deployed (dev)** · re-score wave on demand | Scope alignment (Stages 1–4) + **Scoring v2** (4-label + liveness gate, v1 retired in V2-4) + **UX rebuild** (U1–U4 + Reveal & score) — migrations `0019`→`0026` | C · Apollo | KPI gate (≥3× rows/find · ≥2× `contact_now`+`contact_soon` share · <5% dupes) — review #5 ✅ |
| **E** | S4/S5 Outreach | ⬜ **planned** | Approved batch → Smartlead campaign, A/B/C, webhook funnel, cross-campaign Reply Queue, reply-to-thread | **D+** · warm domains · Smartlead | Live sending; replies triaged in one queue |
| **F** | S6 Book+Meeting | ⬜ **planned** | Booking link → Calendar/Meet event + invites; held+duration; qualify rule | E · Google | Prospect self-books; held/duration recorded; auto-qualify |
| **G** | Run & close | ⬜ **human** | Meeting → pitch live product → close → onboard signup (= new tenant, reuse A) | F | **6 signups over H1** |

**Critical path:** A → B → C → D → **D+ (sourcing + scoring + UX)** → E → F → G.
**Parallel since day 0:** domain warm-up (started 2026-06-17, the schedule driver) · keys (done 2026-06-10) · ICP + cold-email copy.
**Simplification principle:** one env (`dev`) to start (Terraform is workspace-parameterised → prod is a new workspace, not a rewrite); one modular FastAPI service; manual one-command deploy; JWT auth. Never shortcut: `tenant_id` on every row + one central access guard.

---

## Current state snapshot

| Thing | State |
|---|---|
| Backend | Lambda alias `live`, `api.tryholdslot.com`, **~50 endpoints** across `auth·clients·briefs·icps·prospects·batches·approvals`; D+ Stages 1–4 + Scoring v2 deployed to `dev` |
| Database | Aurora Serverless v2 + Data API · **head `0027` applied** (D+ migrations `0019`→`0027` applied to `dev`; `0027` = scoring-v2 + D+.5/final-fix indexes/constraints, deployed at push #1) |
| Web | Amplify `dev` (autoBuild on push); the V2-3 + UX + G1–G7 frontend is **committed + pushed** (head `97f4725`; Amplify job 52 SUCCEED) — Amplify build rides it. `main`/`tryholdslot.com` points at the **dev** API/DB until prod cutover |
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
- ✅ **Final fix wave (pre-production) — DONE + deployed** — the 2026-07-11 final review: **G1–G7**, 56 findings N1–N56 (3 P1 — the R8 skip-set crash, the `stageForPeople` excluded-row leak, Aurora deletion protection), §F founder decisions Q1–Q8. Built + committed (7 commits) + **deployed across two pushes** (dev Lambda **v78** + migration **`0027`** applied + Amplify prod FE job 52). Full digest → **§D+.6** below.
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
clean + **playwright 18 passed**. **`dev` is 7 commits ahead; NOT merged `dev`→`main`** (that ships the prod
FE — a separate founder call). Remaining = the **prod-cutover register** (§After A–G complete).

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

## Phase E — Outreach + Smartlead (S4/S5) — after D+

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
| Founder Brief→Scope round (dev) | S1 | ✅ folded into D+ review #5 (signed off 2026-07-10) |
| Founder live Apollo round (find→enrich→batch; reads real `cost_usd`) | S2 | ✅ folded into D+ review #5 (signed off 2026-07-10; Apollo credit-dashboard glance rides the next enrich round) |
| Founder live batch round (create→send masked link→approve) | S3 | ⏳ operational — infra live |
| **D+ (sourcing + scoring + UX)** — §D+ above; shipped end-to-end (review #5 ✅ · V2-4 ✅); **§D+.5 fix wave (F1–F7) ✅** + **final fix wave G1–G7 (56 findings) ✅ built + deployed** (two pushes → dev Lambda **v78** + migration `0027` + Amplify job 52; §D+.6); Q7 re-score list confirmed empty | pre-E | ✅ built + shipped · ✅ both fix waves done + deployed |
| Warmed inboxes ready (~early Jul'26) | E0 | running since 06-17 |
| **A follow-ups (non-blocking):** custom MAIL FROM ✅ (D0) · prod isolation deferred (Amplify `main`→dev until cutover) · manual deploy (CI/CD later) · Aurora scale-to-zero vs 30s timeout (prod sets min ACU ≥0.5) · S3 state bucket public-access-block (prod) · refresh-token rotation now re-checks `UserStatus` + is single-use guarded (N9/N33 ✅) | — | tracked |
| **Deferred ICP inputs (search-side; already used for *scoring*):** `technologies`→Apollo tech-UIDs (**resolver BUILT in D+ Stage 4** — `tech_vocab` → `currently_using_any_of_technology_uids`) · `revenue_range` (no ICP form field) · funding-stage key **confirmed absent from the documented API** (2026-07-08) | — | post-MVP / D+ |
| **Backlog:** step-3 console decide UI (the `decide_batch` endpoint + `decideBatch` client fn exist, tested; no UI) · `person` enrich-once cache (lands with tenant #2) · move `reloadBatches` onto the TanStack-Query cache | — | optional |

---

## After A–G complete

- **Production isolation** (cutover, not rewrite — Terraform is workspace-parameterised). `terraform workspace new prod` → `apply` → prod `aurora_min_acu ≥ 0.5` → fresh prod JWT keys → `alembic upgrade head` + seed → SES prod sandbox-exit → point Amplify `main` at prod → harden (S3 PAB, CI/CD). Trigger: Phase G DoD met.
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
| `holdslot/prod/smartlead` | ◑ | `api_key` valid; `webhook_signing_secret` + `sending_account_ids` → **E** |
| `holdslot/prod/google` | ✅ | SA + domain-wide delegation + Calendar + Meet REST all 200 |

**Sending infra (the long pole, gates E):** Smartlead-native warm-up + Google Workspace mailboxes on a
dedicated lookalike domain **`getholdslot.com`** (cold mail never goes from `tryholdslot.com`). 2 mailboxes
(`jason.tse@`, `jason.wong@`), all DNS verified (MX/SPF/DKIM/DMARC), Smartlead warm-up enabled (40/day ceiling,
+5/day ramp). **Clock: started 2026-06-17** → first real sends ~early Jul'26 (5–10/inbox/day → ~25). MVP =
**one domain** ([SCALE] adds a 2nd). Still to do: do-not-email suppression list · A/B/C copy (before week-3 sends).

---

## API surface (live on `dev`)

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
