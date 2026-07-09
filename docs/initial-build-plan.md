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
> classifier, B2B/B2C market gate, thinking-OFF fit scoring, async-scoring zombie reaper. **Next: the
> prospect-scope alignment build (D+, approved 2026-07-08 — §below) — completes BEFORE Phase E**; then
> **Phase E (outreach + Smartlead)**, still gated on warmed inboxes (warm-up running since 2026-06-17).
> The only thing left on A–D is the three **founder operational acceptance rounds** (S1/S2/S3) — the D+
> UAT rounds double as S1/S2.

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
| **D+** | Scope alignment | ⬜ **approved 07-08** | Probe loop + scope lineage (`0019`) · `person_titles` + strict ladder · page-cursor recycling of known rows · vocabulary grounding (· optional spec-v6 portfolio) | C · Apollo | KPI gate: ≥3× rows/find · ≥2× Strong+Good share · <5% dupes on re-find · UAT rounds 0–4 |
| **E** | S4/S5 Outreach | ⬜ **planned** | Approved batch → Smartlead campaign, A/B/C, webhook funnel, cross-campaign Reply Queue, reply-to-thread | **D+** · warm domains · Smartlead | Live sending; replies triaged in one queue |
| **F** | S6 Book+Meeting | ⬜ **planned** | Booking link → Calendar/Meet event + invites; held+duration; qualify rule | E · Google | Prospect self-books; held/duration recorded; auto-qualify |
| **G** | Run & close | ⬜ **human** | Meeting → pitch live product → close → onboard signup (= new tenant, reuse A) | F | **6 signups over H1** |

**Critical path:** A → B → C → D → **D+ (scope alignment)** → E → F → G.
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
| **One spec reader** | `targeting_for_icp(spec, icp_id)` — find-company resolves the picked ICP's block (multi-ICP + no/unknown ICP → 400, never a silent merge; single-block resolves + labels automatically); find-people resolves **per company** from `company.icp_id` (a mixed selection searches ICP by ICP in one call); fit scoring slices the row's own block into the v3 shape the rubrics read (fewer tokens, sharper targeting). **v3 specs keep working** via the fallback until the next regenerate — backend deploys first with zero downtime. |
| **UI** | Prospect Scope panel: per-ICP **coverage chips** + an **ICP dropdown** next to View prompt (drives the rendered block AND the prompt preview's `?icp_id=` input); gaps carry their ICP tag; legacy/missing-scope callouts. Prospect list: **ICP dropdown** (both stages — filters the tables AND picks the Find Company target; single ICP auto-picked, multi without a pick = guard toast + warn flash mirroring the server 400), **ICP badge under the company name** in both tables, Find-Settings modal gets an **ICP switcher** seeding from that ICP's block (override saved per ICP in localStorage, legacy key read as fallback). |
| **Job hygiene** | The `research_job` **zombie reaper** (`MAX_JOB_AGE_SECONDS=360`, same pattern as scoring) — a worker killed mid-run no longer wedges the brief page in "Generating…" forever; stale jobs flip to a named timeout error on read/enqueue. |

Out of scope (follow-ups): per-ICP *persisted* scope overrides in the DB (`by_icp` keying, no
migration needed) · per-ICP partial regenerate · auto-seeding a block when a suggested ICP is
accepted · ICP-level credit budgets.

---

## Prospect-scope alignment build (D+) — ✅ APPROVED 2026-07-08 · ⬜ not built · completes BEFORE Phase E

Founder verdict on live B/C output: **too few rows, majority low-fit.** Root-caused 2026-07-08 (code
read + verification against Apollo's official OpenAPI spec) to six pipeline causes — ours, not
Apollo's data:

1. **Width cap wastes paid pages** — `MAX_COMPANIES_PER_FIND=15` keeps 15 of every 100-row org-search
   page, and org search is **charged per page** (confirmed) → ~85% of every paid page discarded.
2. **No feedback signal** — the find path discards Apollo's `pagination.total_entries` +
   `breadcrumbs` + `partial_results_only`; queries fly blind (0 vs 2M matches, never known up front).
3. **Ungrounded vocabulary** — free-text `q_organization_keyword_tags` with no validation vocab;
   facets AND across params, so one bad keyword sinks the query. (Technologies DO have a canonical
   CSV vocabulary — unused today.)
4. **Query ≠ rubric** — the people query sends seniority×department but never `person_titles`, while
   the fit rubric scores a *title* dimension; org-scoped people search drops `q_keywords`/locations/
   size that the scorer still judges against → low fit partly **by construction**.
5. **Departments param unverified** — `person_department_or_subdepartments` is NOT in Apollo's
   documented API; if silently ignored, "strict" people search is far broader than believed.
6. **One query per ICP** — no variants; relax ladder exists on people only, not companies.

**Exclusion reality (→ Stage 3).** Apollo has NO exclude-by-id/keyword/industry — only
`organization_not_locations` + `currently_not_using_any_of_technology_uids`. Known-bad rows can't be
sent back to Apollo; the equivalent effect is built pipeline-side: a **query-keyed page cursor**
(repeat find with an unchanged body resumes at the next page + known `apollo_org_id`s skipped —
stop re-buying page 1), **negative-evidence feedback** into Regenerate Scope (keywords correlated
with Below/`market_excluded` rows get dropped by the LLM), the two real exclude params when bad rows
cluster, and **lookalikes of Strong rows** for positive reuse. Stored `business_model` labels already
make a returning bad row spend $0 — Stage 3 pins that invariant with tests.

**Token posture:** zero new per-row LLM calls anywhere. Scoping stays ONE call per regenerate;
probe/relax/cursor/resolvers/correlation are deterministic code; prompt feedback is a ≤300-token
aggregate; fit scoring stays thinking-OFF on-demand; wider intake touches only the token-minimal
stage-0 classifier, and gated rows still never reach paid scoring or enrich.

### Stages (each: build → pytest fixture tests, existing `apollo_map` style → live dev smoke → UAT round)

| Stage | Builds | Tests | Accepts when (dev) |
|---|---|---|---|
| **1a · Telemetry + safe widen** (~1d) ✅ **BUILT 2026-07-08 (backend, on `dev` branch — undeployed)** | **`0019`** — `research_run.filter_body` + `scope_source` (`ai`/`custom`/`lookalike`) + `result_meta{total_entries, breadcrumbs, pages_fetched, relax_level, body_hash}` (**absorbs the 2026-07-06 scope-lineage design**: executed-body snapshot at the moment of send, override-proof) · apollo `search_companies_meta` reads `total_entries`+`breadcrumbs` off the SAME fetch response (**no extra call**; `_paginate` returned `(rows, meta)`) · threaded into the `ResearchRun` insert + exposed on `ResearchRunOut` (`icp_id`/`scope_source`/`filter_body`/`result_meta`) · **cap 15 → env-tunable `FIND_COMPANY_LIMIT` (default 25)**, `_SCORE_WORKERS` **decoupled** into its own env knob (stays 15) so widening never fans out unbounded LLM calls. **Tests:** `search_companies_meta` first-page-signal capture · rows-only wrapper intact · `0019` model-parity + head bump · updated integration monkeypatches — **all non-DB tests green + ruff clean**. **Left for deploy:** `alembic upgrade` on dev Aurora + Lambda publish, then `test_prospects_apollo` on dev | ✅ `search_companies_meta` capture · `0019` columns/head · env knobs — **passing** | rows land with `filter_body`/`result_meta` populated; a find returns up to `FIND_COMPANY_LIMIT` rows |
| **1b · Async find + relax + drawer** (~1d) ✅ **BUILT + DEPLOYED 2026-07-08 (Lambda v61)** | find-company path **async** (like `scoring_job`: return fast, run enrich+classify+score in a background worker) so width safely reaches 50–100 and hits the ≥3× KPI — **the current 30s-gateway ceiling on sync classify+enrich is why 1a caps at ~25** · **fetch-page-1-then-assess** auto-relax on empty/thin (drop `revenue_range` → widen size ranges → drop weakest keyword; write `relax_level` into `result_meta`) → `>100k` total flagged over-broad · **Find-history drawer** (read UI over `/research-runs`, now lineage-rich: when · source · ICP badge · spec vN · ai/custom chip · rows · `total_entries` · View-filters popover) + honest Find-Settings badge · **one-time live A/B on the departments param** | relax state-machine (order deterministic, terminal) · async job lifecycle + reaper parity · drawer render | drawer shows filters + `total_entries` + relax level per run · a forced 0-result self-relaxes (drawer proof) · one find returns ~50–100 rows |
| **2 · Query = rubric** (~1d) ✅ **BUILT 2026-07-08 (backend, on `dev` — undeployed)** | `person_titles[]` (multi-variant per ICP, Apollo's own guide) + `include_similar_titles` toggle · ladder becomes `titles_strict → titles_fuzzy → seniority×dept → seniority_only` (folding the Stage-1 departments verdict) · APAC broadening: `email_status` never constrains people **search** (confirmed — it's a `people/match` gate only) · drop `revenue_range` up front for APAC (`_is_apac`, comma-token country match) · broaden-on-empty = the new ladder (people search 0 cr — width is free). **Spec v6** (`person_titles` added; prompt teaches emit-titles-AND-facets) + **migration `0020`** re-seeds the briefing prompt to `brief-structure-v8` for tenants on a shipped default. **Tests:** titles+toggle per ladder level · ladder order/skip (titles-first, facet fallback) · titles-hit-stops-descent · APAC trigger · org-scoped drop regression (titles don't resurrect q_keywords/locations/size) — **142 passed / ruff clean.** | `map_people_filter` emits titles+toggle per ladder level ✅ · ladder ordering ✅ · APAC trigger ✅ · dropped-field regression ✅ | 10-row title spot-check matches ICP · APAC ICP returns non-empty people where baseline was thin |
| **3 · Recycle negative signal** (~1d) ✅ **BUILT 2026-07-08 (backend + FE, on `dev` — undeployed)** | query-keyed **page cursor** (`_paginate` gains `start_page`; `_resume_page` reads the latest same-scope run's `result_meta.page_cursor`; resume at +1; `scope_exhausted` when `end_page ≥ total_pages`; reset-on-param-change is inherent in the `body_hash` key) · **known-org skip** (`skip_known` drops orgs already stored BEFORE enrich/classify/upsert — the $0 invariant + page-overlap safety net) · Below/`market_excluded` ↔ keyword correlation → **`avoid_keywords`** negative block in the Regenerate prompt (`feedback.negative_keywords`; **prompt v9** + migration **`0021`**) · conditional **`organization_not_locations`** emission (`feedback.cluster_exclusions`; **tech-UID not-using-tech deferred to Stage 4** — needs the tech→UID resolver) · lookalike-of-Strong recovery CTA · **FE:** scope-exhausted notice + drawer "page N / total" + "scope exhausted" chip | **Tests:** `_paginate` resume · `_cursor_decision` (resume/reset/exhaust) · `feedback.negative_keywords` (rank/floor/keeps-mixed/industry/top-k) · `cluster_exclusions` (dominant/spared/floor) · `build_messages` avoid-block · DB-gated re-find (cursor advances, org skipped, **NOT re-classified** — $0 pinned) — **153 passed / ruff clean** | identical find twice → 2nd returns only NEW rows, drawer shows page advanced · B2C row stays pinned + labelled, run-2 shows no re-classify spend |
| **4 · Vocabulary grounding** (~1d) ✅ **BUILT 2026-07-08 (backend + FE, on `dev` — undeployed)** | tech→UID resolver `prospects/tech_vocab` off `auth/supported_technologies_csv` (client `supported_technologies_csv()`, lru-cached; three-valued hit/ambiguous/miss so a UID is never guessed) → emits **`currently_using_any_of_technology_uids`** (from the scoped ICP's `technologies`) + **`currently_not_using_any_of_technology_uids`** (from `feedback.negative_technologies`; **clears the Stage-3 deferral**), merged AI-scope-only in `_find_company_core` · **`feedback.keyword_yield`** (per-keyword won-share + Apollo `total_entries` breadth via `structuring.keyword_yield_for`) → the ≤300-token `keyword_yield[]` feedback block · **customer-anchor grounding** (`briefs/anchors.py` enriches `excludeCustomers` domains, bounded to 8, best-effort → `apollo_map.parse_org_anchor` industry/keywords/size band; `industry_tag_id` parsed but experiment-only, NOT model-fed) → `customer_anchors[]` payload (worker only — preview stays no-spend) · **prompt v10** (`build_messages` gains `keyword_yield`/`customer_anchors`; teaches yield-drop + anchor-grounding + tech-UIDs-are-server-set) + migration **`0022`** · **FE:** drawer labels the tech/exclusion filter keys | **Tests:** `tech_vocab` hit/ambiguous/miss + slug fallback · `supported_technologies_csv` raw+cached · `feedback.negative_technologies` + `keyword_yield` (win-share/thin-floor/breadth) · `parse_org_anchor` + `_employee_band` · `anchors.customer_domains`/`customer_anchors` (bounded/strip-tag/degrade) · `build_messages` carries both blocks only when present + teaches them · migration head `0022` — **176 passed / ruff clean; FE tsc+eslint clean** | View-prompt shows the feedback block · regenerated keywords drop the worst performer · a tech-filtered find proven in the drawer |
| **5 · Spec-v6 portfolio** (optional ~0.5d) | 2–3 keyword-synonym variant sets per ICP in the scoping schema; execute variants with domain dedupe until the scored-good target is met (still ONE LLM call; output grows a few hundred tokens) | schema validation · variant execution/dedupe | ONLY if the KPI gate below still fails after Stages 1–4 |

**Path (re-sequenced 2026-07-09, founder):** 1a ✅ → 1b ✅(deployed) → **build tiering v2 (addendum
below)** → deploy Stages 2+3+4 **together with** v2 (`0020`→`0025` + one publish) → **one combined UAT in
label terms** → **KPI gate** (→ Stage 5?) → V2-4 contraction (`0026`, second publish after sign-off).
Stages 2+3+4 sit undeployed on `dev` until then.
**~4.5–5 days.** Backend-before-frontend per the ops rule; `data-schema.md` carries `0019` (updated first, done).
New FE surfaces: only the **Find-history drawer** (Stage 1b) + **scope-exhausted notice** (Stage 3) — everything
else rides existing tabs/chips/filters.

> **Build status (2026-07-08):** **Stages 1a + 1b are DEPLOYED to dev** (Lambda v61, `live` alias → 61,
> migration `0019` live) — telemetry, async find, the fetch-then-relax company ladder, the Find-history
> drawer, and the departments A/B (verdict: FILTERS — keep the `seniority×dept` rung). **Stages 2 + 3 +
> 4 are code-complete on the `dev` branch, undeployed.** Stage 2: `person_titles` (spec v6), the
> titles-first people ladder (`titles_strict → titles_fuzzy → seniority×dept → seniority_only`), APAC
> revenue-drop, migration `0020` (prompt → `brief-structure-v8`). Stage 3: the query-keyed page cursor
> (`start_page`/`_resume_page`/`scope_exhausted`), the known-org skip ($0 invariant), `feedback.py`
> (negative-keyword `avoid_keywords` block + `organization_not_locations` clustering), prompt
> `brief-structure-v9` + migration `0021`, and the FE scope-exhausted notice + lookalike-of-Strong CTA
> + drawer page cursor. Stage 4: the `tech_vocab` tech→UID resolver (`supported_technologies_csv`) →
> `currently_using`/`currently_not_using_any_of_technology_uids` (clears the Stage-3 tech deferral),
> `feedback.keyword_yield` + `briefs/anchors.py` customer-anchor enrichment → the `keyword_yield[]` +
> `customer_anchors[]` prompt blocks, prompt `brief-structure-v10` + migration `0022`, and the drawer
> tech-filter labels. **176 passed / 14 skipped, ruff clean; FE tsc + eslint clean.** Deploying 2+3+4
> needs migrations `0020`+`0021`+`0022` on dev Aurora + a Lambda publish back-to-back (prompt-seed
> migrations + matching code), then the frontend. **UAT Round 0 baseline was not captured before 1a/1b
> deployed** — the founder should decide whether to re-baseline on a fresh tenant.

### Business UAT — actual website (dev Amplify); rounds double as the pending S1/S2 founder rounds

Actor = founder, real brief + ≥2 ICPs (one APAC-located). **Round 0 runs BEFORE any build** (the baseline).
Only off-site glance allowed: the Apollo credit dashboard.

> **Superseded 2026-07-09 (decision ① in the v2 addendum):** rounds 1–4 collapse into **one combined round
> after the v2 deploy**, measured in labels (`contact_now`+`contact_soon` share). The per-round checks
> below still run — in one sitting — plus the Step-2 people-label gut-check (risk ⑦). **No baseline round**
> (founder 2026-07-09): results are reviewed as absolutes **after the whole of D+ completes**; the
> baseline-relative multipliers in the KPI gate below are reference targets, not a measured gate.

| Round | Where (UI) | Do | Record / expect |
|---|---|---|---|
| **0 · Baseline** | Brief tab (Regenerate Scope) → Prospect list (Find Company → score → select → Find People → score) | today's flow once per ICP | **baseline card:** rows/find · Strong/Good/Moderate/Below (filter chips) · #market-excluded · zero-result finds · titles gut-check /10 · Apollo credits (dashboard) |
| **1** (after Stage 1) | Prospect list + Find-history drawer + Find Settings | normal find · read the drawer · sabotage test (absurd constraint) | ~100 rows (**≥3× baseline**) · drawer answers "what did this search actually ask?" · no empty screen — auto-relax shown |
| **2** (after Stage 2) | Prospect list step 2 · APAC ICP end-to-end | spot-check 10 prospect titles vs ICP · run the APAC ICP | title match **≥7/10** · APAC non-empty · Strong+Good share vs baseline |
| **3** (after Stage 3) | Prospect list | same Find twice · click through to exhaustion · watch a known B2C row | **<5% dupes** on re-find, drawer shows page advanced · "scope exhausted" notice appears · B2C row pinned + labelled, no re-classify spend on run 2 |
| **4** (after Stage 4) | Brief tab → View prompt → fresh find | check the feedback block · keywords changed · run the new spec | Strong+Good share vs round 1 (the loop's before/after) · founder verdict: "the scope learned" |

**KPI gate** ("more rows that score higher", measured in-app): rows/find **≥3×** baseline · Strong+Good
share **≥2×** (or ≥30% absolute) · zero-result finds **<10%** (all auto-relaxed) · dupes on re-find **<5%**
(≈100% today) · title match **≥7/10** · re-classification spend on known rows **$0**.

### D+ addendum — Company tiering v2 (4-label scoring) · planned 2026-07-09 · 🟡 V2-1 + V2-2 core built (undeployed)

#### Remaining build (consolidated 2026-07-09 — this table supersedes the per-stage detail below)

| Step | Status | What's left |
|---|---|---|
| V2-1 · Contract + deterministic gates | ✅ built + tested | — |
| V2-2 core · score calls + rescore cutover | ✅ built + tested | — |
| V2-2 tail · find-path | ✅ built + tested | ⑧-B `filter_companies` keep+tag `client_excluded` (kept-and-enriched, labeled `rule: client exclusion` by find-time labeling) · `_label_companies_deterministic` after `classify_companies` in find + manual-add (excluded/low_fit show at find, no rescore) · people avoid-title gate reads **per-ICP** `avoidTitles` (matches `filter_people`) · `test_find.py` updated |
| V2-3a · UI foundation | ✅ built + green | additive, independently-compiling: `ScoreLabel`/`Subscores` + v2 fields on `CompanyApi`/`ProspectApi` (lib/api.ts) · `LABEL_META`/`labelRank`/`compareByLabel`/`groupByLabel`/`COLLAPSED_LABELS`/`AXIS_LABEL` (lib/workspace/constants.ts) · `LabelChip`/`SubscoreBar`/`FlagMarker` (components/workspace/spec.tsx) · label-chip + subscore-bar + flag-marker CSS (workspace.css, class-selectors only) — tsc + eslint clean, page untouched |
| **V2-3b · page rewiring** | ✅ built + green | `list/page.tsx` fully cut over to v2 (tsc + eslint clean, no `fit_*` reference left): **Step-1 label-grouped call sheet** — `groupByLabel` over `compareByLabel`-sorted `coVisible`, rendered in `BUCKET_ORDER`; action buckets (`contact_now`/`contact_soon`/`unscored`) expanded, footnotes (`low_fit`/`excluded_by_rules`) collapsed to a one-line count row that expands (`expandedBuckets`); each row's Fit cell = `LabelChip`+score · `FlagMarker` · `SubscoreBar(COMPANY_AXES)` · one-line reason · trigger line (contact_* only); Apollo blurb stays behind `CompanyStudy` · **label filter** `coLabel` (drops `coFit`/`UNSCORED_FIT`) + `fLabel` for people · **override gate ④** `maySelect()` — excluded checkbox `disabled`, low_fit behind a `window.confirm`, select-all bulk-ticks only non-gated rows (`coBulkSelectable`) · lookalike-of-best seeds on `contact_now`/`contact_soon` · **Step 2** people sorted `compareByLabel`, Fit cell = `LabelChip`+`SubscoreBar(PROSPECT_AXES)`+`FlagMarker`+reason, same gating · "AI Score" header → "Fit" both steps · **no verified** · dead `targetMarket`/`coExcluded`/`getBrief` removed. **Deviation:** Step-2 footnote people are NOT sub-collapsed inside each company (the company-row collapse already controls density + person counts are small) — a deliberate simplification vs the "same bucket treatment" wording |
| #4 · Combined deploy + re-score wave | 🟡 backend LIVE · FE + re-score are founder-gated | **Backend DEPLOYED 2026-07-09 (claude_code):** dev Aurora was already at `0023` (D+ 1-4 migrations pre-applied) → `alembic upgrade head` applied **`0024` labels + `0025` rubrics** (both additive/expand, no backfill) · **Lambda v67 published + `live` alias shifted** (`build-and-deploy.sh`) · verified `/health` ok, v2 columns present, `company_score`/`prospect_score` rubrics seeded, **68 companies + 20 prospects all label=NULL** (no backfill, as designed). **Remaining (founder):** (1) **`git push origin dev`** → Amplify autoBuild ships the V2-3b FE (claude_code can't push) · (2) **paid re-score wave** — needs an authenticated session; claude_code must NOT mint from prod secrets (a 3-row canary via a minted token 401'd on the key boundary and was abandoned — **0 rows scored, 0 spend**). Run via the new UI ("Update AI Score", ≤15/batch) **or** the login-based driver `scratchpad/rescore_wave.py` (`HOLDSLOT_EMAIL`/`HOLDSLOT_PASSWORD` env → drives `rescore-async` in 15-row batches). Order: FE push → re-score → #5 review |
| #5 · Founder review | ⬜ | one combined round in label terms, absolute results · collapsed-bucket spot-check · 10-person Step-2 gut-check |
| V2-4 · Contraction | ⬜ (after #5) | migration `0026` + dead-code sweep (drop v1 `fit_*` + indexes, `reason_tags`, sync twin endpoints, `outreach_outcome`, `status` default) + second publish |
| #7 · Stage 5 · spec portfolio | ⬜ conditional | only if #5 says row quality is still short |

**Locked answers folded in (2026-07-09):** **A** tail-first (find-path data before UI) · **B** `verified`
removed from DB/API/UI (not meaningful — the liveness call runs every rescore, so it'd be true for
almost every row; the liveness verdict still lives in `fit_components.liveness`) · **C** size ceiling =
client-wide max employee-range (conservative; never over-fires "too large") · **D** people avoid-title
source verified in code at tail-build time.

---

Adopts the founder scoring spec v2 (`holdslot-scoring-spec-v2.md`): the **company-tier 0–100 AI Score is
replaced by four labels** (the spec's per-row `verified` flag is NOT adopted — decision B). Driving insight
(from hand-verifying 4
of the 66 live rows — **3 of the first 4 moved buckets**): enrichment data lags reality by months — Apollo
showed CXA Group healthy at 65 staff / $63M while nine months into voluntary liquidation. So v2 adds a
**liveness gate** (nothing else catches a defunct company), redefines **outbound_gap around distribution
model** (partner-led = already solved distribution; word-of-mouth = our best buyer) instead of headcount,
and **demotes headcount from gate to signal** (sources disagree up to 4×).

**Confirmed with founder 2026-07-09 — four locked decisions:**
① **Build v2 NOW** — D+ Stages 2–4 deploy **together with** v2 (migrations `0020`→`0026` back-to-back +
one Lambda publish, then FE); the interim Strong+Good UAT rounds are dropped for **one combined round
measured in labels**. Trade-off accepted: sourcing-fix vs scoring-fix attribution is lost.
② **No backfill** — existing rows start `label = NULL` ("needs re-score"); the first post-deploy action is
a full web-grounded re-score wave (doubles as live acceptance). A tier-mapped backfill would have put CXA
(Good·55, nine months into liquidation) into `contact_soon` — the exact failure v2 exists to stop.
③ **BOTH tiers adopt labels** — Step 2 (people) gets a people-shaped axis set (design below); +~1d, folded
into V2-2/V2-3.
④ **Overrides** — `low_fit` is selectable behind a confirm ("our judgment says no; client may override");
`excluded_by_rules` is **locked** — unblocking means changing the rule or re-scoring, never a
click-through.

**The v2 contract** (server-computed; the LLM never picks its own label — same posture as `collapse()`):

| Piece | v2 | today (fit-rubric-v1) |
|---|---|---|
| Label | `contact_now` / `contact_soon` / `low_fit` / `excluded_by_rules` — two actions, two footnotes; **never delete a row** | `fit_tier` Strong/Good/Moderate/Below + `market_excluded` |
| Score | 4 subscores 1–5 (`deal_fit` · `outbound_gap` · `trigger` · `reachability`), sum 4–20 → **≥16 `contact_now` · ≥10 `contact_soon` · else `low_fit`** | 0–100 grid, tiers at 75/55/40 |
| Reason | short enum-ish string, **always populated** (`"company defunct"` · `"rule: B2B only"` · `"wrong vertical"` · `"fits ICP A — <clause>"`…) | free-prose `fit_reason` |
| Flags | non-blocking array: `hq_mismatch` · `headcount_uncertain` · `revenue_implausible` · `founding_date_conflict` · `competitor_adjacent` · `partner_led` · `stale_record` | none |
| Verified | bool, `false` until web evidence (or a human) confirms | none (email_valid is people-tier) |

**Processing order** — stop at first match, but **free deterministic gates run before the paid web call**
(deliberate re-order of spec §3: rules/data/ICP cost $0 and need no search; liveness needs the web. A row
killed by rules is never liveness-checked — a defunct B2C company reads `"rule: B2B only"`, acceptable):

1. **Rules** (deterministic, at find/classify time — extends the live market gate into a rules engine) →
   `excluded_by_rules`: `targetMarket` × stage-0 `business_model` (existing) · **geography** — brief/ICP
   geographies vs **description-derived HQ, not Apollo's HQ field** (Gateway Search: field=SG,
   description=Pennsylvania; disagreement → trust description + flag `hq_mismatch`) · client exclusions
   (existing suppression `ExclusionSet`). **B2C-tag guard:** a B2C-tagged company with a B2B line (Luma) is
   `Complex`-equivalent — never market-gated; `Complex` in source data is B2B.
2. **Data check** (deterministic) → `low_fit "data_unusable"`: industry null/`—` · hq_country null ·
   website is a wire service/aggregator. **Headcount is NOT a gate** (feeds `reachability` only).
3. **ICP sanity** — `icp_id` comes from the targeted find; the score call re-confirms from the
   *description* (not the industries field — Blackpanda is tagged "network security", is a Lloyd's
   coverholder = insurance) and returns `icp_match:false` → `low_fit "wrong vertical"`.
4. **Liveness + score = ONE web-grounded LLM call** per surviving row (`company_score_v2` purpose,
   DeepSeek V4 Pro **with web search** — the scoping-class config, ~50–80s/row, async `scoring_job`
   waves ≤ `ASYNC_BATCH_MAX`): searches `"{company} liquidation OR acquired OR shut down"` first —
   defunct/absorbed/dead-site → `excluded_by_rules` (`"company defunct"` / `"acquired — no longer
   independent"` / `"no active web presence"`); news >24mo → flag `stale_record` only. Then emits the 4
   subscores + reason + flags + a **trigger line (the email hook)**; server sums → label, sets
   `verified=true` when the verdict cites web evidence. `outbound_gap` anchors: 5=word-of-mouth only ·
   4=inbound/PLT · 3=conference-led · 2=broker/reseller · 1=named channel partners or
   investor-as-distributor; hiring sales roles scores DOWN (building in-house).

**Stage-0 classify extended (not replaced):** same token-minimal call now emits `business_model` +
`hq_country` (from description) + `has_b2b_line` — feeds gates 1–2 so every row is labeled/ruled **before**
any paid web-grounded call; gated rows still never spend. Zero new per-row calls: v2 swaps the
`company_fit` call for `company_score_v2` (1:1, web-grounded, only on gate survivors).

**People tier (Step 2) — same labels, people-shaped axes, NO per-person web search** (liveness is a
company property; people ≫ companies makes per-person search a cost explosion). `prospect_score_v2`
judges enrichment data only: `persona_fit` (title/role vs the ICP persona the targeting asked for) ·
`authority` (seniority / decision power) · `trigger` (person-level: new-in-role, promotion, hiring for
their function) · `reachability` (verified email · contact-data quality). Same sum 4–20 → 16/10
thresholds, same reason/flags posture. **The company label caps the person** (the meeting is with the
company): a person at an `excluded_by_rules` company inherits `excluded_by_rules "parent company
excluded"`; a person never ranks above its company. Deterministic gates first, mirroring companies:
`avoidTitles` → `excluded_by_rules` · missing title/contact → `low_fit "data_unusable"`. Net token WIN vs
today: the 12-line grid re-judges the company dims for **every person** (a 10-person company re-scores its
company context 10×) — v2 drops the company dims and inherits the company result, so the people call gets
cheaper despite richer output.

| Stage | Builds | Tests | Accepts when (dev) |
|---|---|---|---|
| **V2-1 · Contract + deterministic gates** (~1d, additive) | migration **`0024`** — `label` str32 + `score_total` int on **company AND prospect** + label index `(tenant_id, label, score_total DESC)` on both · **NO backfill (decision ②)** — labels start NULL, the UI reads it as "needs re-score" · `reason` reuses the `fit_reason` column (enum-ish strings); `subscores`/`flags`/`trigger_line`/`liveness` live in `fit_components` JSONB (**no extra columns**) · rules engine (geography + exclusion + market, reading extended stage-0 output) + data check + **size rule** (→ `low_fit "too large"`; ICP `company_size`/`stage` confirmed in DB 2026-07-09; `headcount_uncertain` suppresses) + `label_from_score` · vendor `holdslot-scoring-spec-v2.md` into `docs/` (first task) · `CompanyOut`/`ProspectOut` emit new fields **alongside** legacy `fit_score`/`fit_tier` (FE untouched) | 66-row fixture (spec §12 — *test fixture, not ground truth*): 5 verified rows land exactly (Bytesforce/Pro5.ai `contact_now`, Blackpanda/Luma `contact_soon`, CXA `excluded_by_rules "company defunct"`) · gate units: desc-vs-field HQ, B2C-with-B2B-line spared, stop-at-first-match · NULL-label render | migration up/down clean · rules fire at find time with $0 spend · old rows read "needs re-score" |
| **V2-2 · Score calls, both tiers** (~2d) | `company_score_v2` strict schema `{liveness, deal_fit, outbound_gap, trigger, reachability, reason, flags[], trigger_line, icp_match}` (web-grounded) · `prospect_score_v2` `{persona_fit, authority, trigger, reachability, reason, flags[]}` (no web; company dims dropped — inherits + is capped by the company label) · **wire the built `labeling.assign_label` into the find/score path** — feed it the liveness verdict + `icp_match` + `subscores`, then persist the `Verdict`: `label`/`score_total`→columns, `reason`→`fit_reason`, `subscores`/`flags`/`icp`/`trigger_line`/`liveness`→`fit_components` · **build `RulesConfig` from the brief/ICP** (`market`=`targetMarket`, `geographies`=spec `company_search_params.organization_locations`, `excluded_*`=`anchors.customer_domains` + customer names) — the V2-1 engine is pure and takes the config; this extraction is the unbuilt wiring · **Step-1 Flow-A becomes a labeler, not a filter** (decision ⑧-B): client-excluded companies are created + labeled `excluded_by_rules "rule: client exclusion"` instead of dropped by `filter_companies`; the Step-2 people/enrich hard-block is untouched · **new `labeling.assign_person_label`** for people (reuses `label_from_score` + `collapse_subscores(SUBSCORE_AXES_PEOPLE)`; company-label cap → `excluded_by_rules "parent company excluded"`, avoidTitles → excluded, missing title/contact → `low_fit "data_unusable"`) — `assign_label` is company-shaped (liveness/rules/data/size gates), **not** reusable for people · prompt-seed migration **`0025`** (per-tenant `company_fit` + `prospect_fit` prompts → v2 rubrics, axis anchors verbatim from the spec) · **build-start probe:** the web plugin must ride the non-US host pin, else liveness needs its own search seam (re-plan the stage) | schema/collapse units, both tiers · liveness→exclusion mapping · icp_match→`low_fit` · company-cap inheritance · flag emission · drift log parity | re-score of the live 66 on dev reproduces §12 buckets (5 verified rows exact) · CXA lands defunct · a `partner_led` flag shows on Blackpanda · people re-score is cheaper/row than the 12-line grid (telemetry) |
| **V2-3 · UI — 4-bucket tables, both steps** (~1.5d) | Step-1 table grouped by label: `contact_now`/`contact_soon` **expanded** (Company · headcount · geo · ICP badge · **4-segment subscore bar** · one-sentence reason · **trigger line**; Apollo blurb stays behind the `CompanyStudy` click) · `low_fit`/`excluded_by_rules` **collapsed one-liners with counts**, expandable (excluded shows its rule) · flags = small warn marker + tooltip · label filter replaces the `coFit` tier filter · sort = label rank → `score_total` desc (replaces the market-excluded pinning comparator) · business-model chip stays · **Step 2 gets the same 4-bucket treatment** inside the existing company grouping (persona subscore bar; the "AI Score" header dies on both steps) · **overrides (decision ④):** `low_fit` selectable behind a confirm; `excluded_by_rules` locked out of select / find-people / batches | tsc + eslint (never `next build`) · bucket render / expand / filter states · override gating | founder reads both steps top-to-bottom as a call sheet · collapsed buckets carry counts · an excluded row cannot be selected · no row ever deleted |
| **V2-4 · Contraction — the removal pass** (~0.5d, **after UAT sign-off**) | migration **`0026`** drops dead DB weight + deletes dead code/API per the inventory below | migration parity · full suite green after deletions · api.ts types pruned, tsc clean | live dev serves the list with the old columns gone |

**As built — V2-1 (2026-07-09, undeployed; deploys with #4):** spec vendored to
`docs/holdslot-scoring-spec-v2.md`. Migration `0024` adds `label`/`score_total` (company + prospect)
+ the label-bucketed indexes, no backfill; v1 `fit_*` untouched (0026 drops it).
New pure engine `domains/prospects/labeling.py` — `label_from_score`, `collapse_subscores`, the
gate ladder (`liveness`/`rules`/`data`/`size`/`icp`) + `assign_label` orchestrator; the two paid
signals (liveness verdict, icp_match+subscores) are inputs so the whole ladder is fixture-testable
at $0. Stage-0 classifier extended to emit `hq_country` + `has_b2b_line` (prompt `company-model-v2`),
both persisted into `fit_components` at find/classify time. `CompanyOut`/`ProspectOut` carry the v2
fields alongside v1. Tests: `tests/test_labeling.py` (26 cases inc. the §12 five-verified fixture,
CXA→defunct, Luma guard, gate order) + migration guards; full suite 197 green, ruff clean.
**Deferred to V2-2 (deliberate):** the live `assign_label` call at find time — it joins the score
call there, since the liveness/ICP/score gates it needs are the V2-2 paid signals; wiring it now
would stamp only partial labels and be rewired next stage.

**As built — V2-2 core (2026-07-09, undeployed; deploys with #4):** **Probe PASSED** — the web-search
plugin already rides the non-US host pin in production (scoping runs `deepseek/deepseek-v4-pro` +
`plugins:[{id:"web"}]` on the Fireworks pin, [research_spec.py](../apps/api/app/domains/briefs/research_spec.py)),
so liveness folds into one web-grounded `company_score_v2` call — **no separate search seam, stage not
re-planned.** Built: `fit.company_score_v2` (web-grounded liveness + 4 axes + icp_match + flags +
trigger_line, ~120s async-only) and `fit.prospect_score_v2` (no-web people axes); `labeling.assign_person_label`
(company-label cap → `parent company excluded`; avoid-title substring gate; missing-title/contact →
`data_unusable`), `labeling.build_rules_config` + `size_ceiling_from_spec` (market=`targetMarket`,
geographies=spec `organization_locations`, size ceiling=max employee-range, excluded=exclusion-set
domains). **Rescore cutover:** the async handlers `run_rescore_companies`/`run_rescore_prospects` now
call `_score_companies_v2`/`_score_prospects_v2` — deterministic gates (free) → paid score on
survivors → `Verdict` persisted to `label`/`score_total` + `fit_components` (v1 `fit_*`
untouched; sync twins stay on v1, they'd time out on the web call and are deleted in V2-4). New prompt
stages `company_score`/`prospect_score` seeded by **migration `0025`** from `docs/prompts/company-score-v1.md`
+ `prospect-score-v1.md` (v1 rubrics stay intact). Tests: `test_scoring_v2.py` + people/config cases
in `test_labeling.py` (25 new — schema shapes, signal normalization, `icp:none`→null, company-band
cap, avoid-title, rules/size extraction); full suite **211 green**, ruff clean.
**▶ V2-2 tail — the find-path chunk (⑧-B + find-time labeling), credit question RESOLVED 2026-07-09:**
Apollo **company org-enrich DOES cost credits** — but the founder confirms **keep-and-enrich** is fine
(current consumption is low), so a client-excluded company is kept, enriched, classified, and labeled
`excluded_by_rules "rule: client exclusion"` (NOT skip-enriched). This is now the next build (a short
V2-2 tail, before V2-3):
  1. `find.filter_companies` — stop dropping excluded-domain rows; keep + carry them to upsert (Step-2
     people/enrich hard-block is untouched). Update `test_find.py` (excluded rows now kept+labeled).
  2. Find-time deterministic labeling — after `classify_companies` stamps the stage-0 fields, run
     `labeling.assign_label` (deterministic only) per row and persist the gate verdict, so
     excluded/low_fit show at find without a rescore click. `skip_known` still protects the $0
     invariant (a re-find never re-enriches/re-labels an already-stored excluded row → no repeat
     spend). Rescore already produces every label, so this is a "show sooner" step, not a correctness
     fix.
  3. Note the small find-time credit rise (excluded rows now enriched) — accepted; see the Apollo
     credit memory correction (org-enrich is a spend, not free as previously recorded).

**Removal method** — *expand → cutover → contract*: V2-1/2 only add; V2-3 switches the UI; nothing is
dropped until UAT accepts, then V2-4 deletes in one sweep (single revert point). Inventory (from the
2026-07-09 dead-code audit):

| Unused thing | Where | Removed in |
|---|---|---|
| `fit_score` / `fit_tier` on **company AND prospect** + both fit-sort indexes (incl. `ix_prospect_tenant_fit`) | superseded by `label`/`score_total` | `0026` |
| `prospect.outreach_outcome` — zero writers/readers anywhere | `models.py` | `0026` |
| `prospect.status` default `"new"` — never a live value | `models.py` | `0026` (default→`found`) |
| `reason_tags` — written, **never rendered** | `fit.py` → `CompanyOut`/`ProspectOut` → `api.ts` | V2-4 code (stop exposing; stored history untouched) |
| 5 sync twin endpoints (web calls only `-async`): `find-company` · `companies/rescore` · `update-fields` · `find-lookalikes` · `prospects/rescore` | `prospects/router.py` | V2-4 — routes deleted, their tests re-pointed at the core fns (`_find_company_core`, `_score_companies`…) |
| `UNSCORED_FIT` sentinel + `FIT_CHIP`/`FitScore` (both steps) + tier filter options | `list/page.tsx`, `constants.ts`, `spec.tsx` | V2-3 |
| LLM self-emitted `fit_tier`/`fit_score` (company + prospect schemas) | replaced by the v2 schemas | V2-2 |

**Known gaps / risks (carry to build):** ① spec §7 gap **RESOLVED 2026-07-09** — founder confirms
`company_size`/`stage` are populated in the DB for both ICPs, so the **size rule is active from V2-1**:
exceeding the ICP band → `low_fit "too large"` (never a hard exclusion — headcount data can't carry one);
a `headcount_uncertain` flag (sources disagree >2×) suppresses the gate for that row. ②
Web-grounded scoring cost/latency: 1 search-enabled call per gate-survivor (~150 rows/mo at Launch tier —
priced in by the spec; the alternative is emailing a company in liquidation under the client's brand). ③
KPI-gate language shifts: "Strong+Good share" reads as **`contact_now`+`contact_soon` share** in the
combined round. ④ Sourcing is the real bottleneck — 5 contactable of 66 sourced; v2 makes that visible, the
D+ Stage 1–4 loop is what fixes it. ⑤ `data-schema.md` gains `0024`–`0026` at build time. ⑥ Errors
concentrate in collapsed buckets (nobody reads them) — UAT must spot-check `low_fit`/`excluded_by_rules`,
not just the call sheet. ⑦ The people axes (`persona_fit`/`authority`/`trigger`/`reachability`) are OUR
extrapolation — the founder spec is company-tier only — so the combined round includes a 10-person
gut-check on Step-2 labels; if the axes read wrong, only the `0025` prospect rubric changes (schema and
thresholds hold). **⑧ RESOLVED 2026-07-09 — option B (create-and-label at Step 1):** Step-1 company
find today **drops** client-excluded domains before the row is created
([find.py](../apps/api/app/domains/prospects/find.py) `filter_companies`, router `_find_company_core`),
contradicting spec §5 ("never delete a row"). Company **search** is free, and while company
**org-enrich DOES cost credits** (founder confirm 2026-07-09 — correcting the earlier "only
people/match spends" note), the founder accepts **keep-and-enrich** (current consumption is low). So
the V2-2 tail switches Step-1 to **create + enrich + label the row `excluded_by_rules "rule: client
exclusion"`** instead of dropping it — spec-faithful, and known customers now show as collapsed
excluded rows rather than vanishing silently. `skip_known` bounds the cost: a re-find never
re-enriches an already-stored excluded row (no repeat spend). The **people/enrich suppression stays a
hard block** unchanged (never source/enrich an excluded person; the manual-add block at
`router.py:2040` and the Step-2 enrich gate are untouched). Scope note: this flips find.py Flow-A from
a filter into a labeler — the excluded set feeds `RulesConfig.excluded_domains`, and the
already-scored dedupe/known-skip path is unaffected. **⑨** The `0024`
label index `(tenant_id, label, score_total DESC)` orders `label` **alphabetically**
(`contact_now` · `contact_soon` · `excluded_by_rules` · `low_fit`) — **not** the UI priority (excluded is
last). So the V2-3 feed fetches each collapsed bucket as a **per-label query** (`WHERE label=? ORDER BY
score_total DESC` — fully index-served) or orders by a CASE rank in-app; there is no single
globally-label-ranked index scan.

---

## Model selection — Pro vs Flash live A/B (2026-07-10) · ✅ classifier switched · ⛔ scorer held

Both v2 LLM calls were A/B'd `deepseek-v4-pro` (the locked model) vs `deepseek-v4-flash` on the dogfood
tenant via a **read-only in-Lambda harness** — it ran the *exact* production path with one model swapped and
never persisted a verdict (the OpenRouter key is Lambda-only, so a local script can't make the call; the
harness was direct-invoked off the auth path, diffed against stored baselines, then removed once the
decision was recorded here — git-recoverable at `eaf7060:apps/api/app/domains/prospects/model_compare.py`).
**Split verdict — the two calls have opposite cost/reliability trade-offs:**

| Call | Verdict | Evidence |
|---|---|---|
| **`classify_business_model`** (stage-0, web-free, coarse 4-way label) | **✅ SWITCHED to Flash** — live, Lambda **v74** | 239-row run, **no web-drift confound** (inputs are static): **90.8% exact** `business_model` and — the metric that matters — **94.6% market-GATE-outcome** agreement (keep vs exclude). Errors are **safe-direction**: 12 recoverable false-*includes* (a wrongly-kept row just scores `low_fit` at stage 1) vs 1 debatable false-exclude. `hq_country` noisier (71% raw match) but flipped **0/239 geo gates** — Apollo `field_country` backstops it; `has_b2b_line` gates nothing (Luma guard already removed). Flash **21× cheaper** ($0.000063 vs $0.001348/call) + **2.3× faster** (1.7s vs 4.0s). |
| **`company_score_v2`** (paid, web-grounded, 4-axis ranking) | **⛔ KEEP Pro** | 66-row run: 82% label agreement, score MAE 1.52 (Flash biases ~0.45 lower). A fresh-Pro control on the 12 flips split them **5 web-drift / 7 real model-divergence** — Flash under-rates strong 18–20 rows and once collapsed to all-1s (talentusgroup, Δ−10 = a reliability gap). Flash is 3.3× cheaper / 2.6× faster, but the saving is **cents** per call. |

**Why they split — the decision rule:** switch the call whose errors are *recoverable* and whose inputs are
*cheap + static* (the classifier — accuracy parity + 21× savings ⇒ switch); hold the call whose errors are
*terminal* (a downgraded strong lead is never contacted). At HoldSlot's **$500/qualified-meeting** unit
economics, reliability on the paid ranking call outranks a cent-level model saving, so the scorer stays on
Pro. Re-run this A/B whenever the model list changes.

---

## Locked context you MUST carry (non-obvious; carry into every phase)

| Topic | Rule |
|---|---|
| **OpenRouter HK geo-block** | OpenAI / Anthropic / Google providers return **403 ToS** for this account (Hong Kong), account-wide. **Route every LLM call to non-US providers only** (DeepSeek / Qwen / Mistral; Llama dropped 2026-06-22). Scoping = `deepseek/deepseek-v4-pro` (thinking + web-search, ~55–76s) on the **async** path — exceeds the 30s API-GW sync cap. Fit scoring = `deepseek/deepseek-v4-pro` **thinking OFF** on both stages (`company_fit` + `prospect_fit`; A/B'd 2026-07 — the trace was ~98% of output and drove the timeouts) at `temperature=0`; still runs in the **background** via `scoring_job` (never on the find request). **Stage-0 `classify_business_model` = `deepseek/deepseek-v4-flash`** (switched 2026-07-10 after a live A/B — see §Model selection; the paid scorer stays on Pro). |
| **Apollo credits** | **BOTH searches are FREE — 0 credits** (founder Apollo-dashboard confirm 2026-07-08; the public "charged per page" pricing doc does NOT apply to this Professional + master-key account). **`people/match` (enrich) = the ONLY spend: 1 cr/email** (8/phone, `PHONE_ENABLED=false`), human-gated at Gate 2. So find-width is **not** credit-bound — it's bound by **sync find-path latency** (stage-0 classify + company-enrich run synchronously at find, vs the 30s API-GW cap); widening past ~25 needs the find path to go async (D+ Stage 1b). Never `people/match` before Gate 2; suppression/exclusions are DB-side. |
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
| Founder Brief→Scope round (dev) | S1 | ⏳ operational — folds into D+ UAT rounds 0/4 |
| Founder live Apollo round (find→enrich→batch; reads real `cost_usd`) | S2 | ⏳ operational — folds into D+ UAT rounds 0–3 (+ Apollo credit-dashboard glance) |
| Founder live batch round (create→send masked link→approve) | S3 | ⏳ operational — infra live (0018 applied, v59) |
| **D+ prospect-scope alignment build** (5 stages · UAT rounds 0–4 · KPI gate, §above — absorbs the scope-lineage design) | pre-E | ✅ approved 2026-07-08 · ⬜ build |
| Warmed inboxes ready (~early Jul'26) | E0 | running since 06-17 |
| **A follow-ups (non-blocking):** custom MAIL FROM ✅ (D0) · prod isolation deferred (Amplify `main`→dev until cutover) · manual deploy (CI/CD later) · Aurora scale-to-zero vs 30s timeout (prod sets min ACU ≥0.5) · S3 state bucket public-access-block (prod) · refresh-token rotation doesn't re-check `UserStatus` | — | tracked |
| **Deferred ICP inputs (search-side; already used for *scoring*):** `technologies`→Apollo tech-UIDs (**resolver BUILT in D+ Stage 4** — `tech_vocab` → `currently_using_any_of_technology_uids`) · `revenue_range` (no ICP form field) · funding-stage key **confirmed absent from the documented API** (2026-07-08) | — | post-MVP / D+ |
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
