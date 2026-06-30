# HoldSlot — Initial Build Plan (dogfood MVP)

> **Status (2026-06-25):** Phases **A (S0)** + **B (S1)** + **C (S2)** **built, reviewed & live on `dev`** —
> backend on the `dev` API (alias `live`, **Lambda v46**, commit `196a31e`), web on Amplify `dev` (build #38).
> The single-tenant **Apollo find → score → select → enrich loop is a live functional MVP**: Apollo does
> discovery *and* enrichment (company search, people search, `people/match`, static key); the LLM only scores
> rows (the Brief→targeting LLM ran in B; the B→C param mapping is **deterministic**). No CSV.
> **Since v37** the Step-2 surface was rebuilt **company-centric** with **persona facets** (Management Level ×
> Department + live Apollo facet sidebar), a **persisted people-scope override** (`0012`), the **fit rubric
> split** into `company_fit` + `prospect_fit` (`0013`), an **Enrichment column + on-demand Update Field**, and
> two UX fixes (the async "Scoring…" reconciliation — no Pending flash — and the Accepted/Enriched sort rules).
> See Phase C → **C8–C10**. Schema deltas in [`data-schema.md`](data-schema.md).
> **Latest (2026-06-25) — frontend modularization + W0–W8 backend hardening shipped to `dev`** (full record in
> *Modularization + W0–W8* below): the workspace/client-status monoliths split into **7 + 3
> nested routes**; the backend gained the enrich double-spend fix, perf indexes (`0014`), **async scoring**
> (`scoring_job`, `0015`, all 5 surfaces), cursor pagination, login cold-start retry, an LLM token trim,
> request-id logging, and warm-container caching → **47 endpoints · 16 tables · head `0015`**. See
> *Modularization + W0–W8 (landed 2026-06-25)* below + the per-phase **Δ** table. **Phase D (batch + approval) is
> BUILT 2026-06-25 (D1–D6: `domains/batches` + `domains/approvals`, Alembic `0016`, 3 web surfaces live; tests +
> build green) + REVIEWED/HARDENED 2026-06-30 (re-decide guard, tenant-scoped ICP, mask hardening, prior-link
> revocation on resend, no-leak expired view, atomic decide claim, UI date/id/refresh fixes — see *★ Review
> hardening 2026-06-30*) — pending `0016` apply to dev Aurora + redeploy, then the live end-to-end.** → **20
> tables · head `0016`** once applied.
> **S2 ticks once the founder runs one live end-to-end round** (the one operational gate left).

> ## ▶ NEXT SESSION — START HERE
> **Phase C (Apollo find→enrich loop) is a LIVE FUNCTIONAL MVP on Lambda v46** (commit `196a31e`, all pushed
> to `origin/dev`). C0–C10 built, deployed, and proven end-to-end on the cloud stack (ephemeral-tenant smoke:
> find-company → select → find-people → `people/match` returned a verified email, **1 credit**). Migrations
> through `0015` applied (DB at head). **Frontend modularization + W0–W8 backend hardening landed on `dev`
> 2026-06-25** (Lambda v46) — see *Modularization + W0–W8* below and the per-phase **Δ** table.
>
> **Shipped since v37 — Step-2 rebuild (C8–C10) + UX fixes** (all green: backend tests + ruff, web tsc +
> build):
> - **C8 · company-centric Step-2 + persona facets** — find/score/enrich people *per company*; persona
>   targeting by **Management Level × Department** with a **live Apollo facet sidebar** (free people-search
>   counts); row/column alignment + 0-people over-constraint fix + Remove action.
> - **C9 · persisted people-scope override** (migration `0012`) — Find Settings saved server-side per tenant.
> - **C10 · fit rubric split** (migration `0013`) — `fit_scoring` → **`company_fit`** (Step 1) + **`prospect_fit`**
>   (Step 2), each its own system + input prompt; stage-aware Fit-rubric modal (`purpose · prospect_fit` on Step 2).
> - **Enrichment column + on-demand Update Field** (credit-frugal single-org `organizations/enrich`); company
>   score is verdict-only (`fit_score`+reason, tier derived).
> - **UX fixes** — async "Scoring…" now reconciles from the DB (no Pending flash, Step-1 *and* Step-2); sort
>   rules: Step-1 Accepted-on-top, Step-2 Enriched-first.
>
> **Next:** Phase D (batch + client approval) is **BUILT 2026-06-25 + REVIEWED/HARDENED 2026-06-30** (see *Phase
> D — Sendout Batch + Client Approval*; D1–D6 code complete + tested, backend 100 pass/10 skip + ruff clean, web
> tsc + eslint + knip clean, 6 external e2e green). The code is review-clean and ready to deploy.
>
> **▶ Remaining plan (in order):**
> 1. **Ship D (deploy-time, ~1 session).** `alembic upgrade head` (0015 → 0016) on dev Aurora → redeploy the
>    Lambda → set `HOLDSLOT_DB_*` + run the DB-gated e2e (`test_batch_end_to_end_create_send_view_decide`) →
>    founder live round: create batch → send masked link → approve → confirm `prospect_approval` rows. **This
>    ticks S2** (the one operational gate) and makes the find→approve loop live for real outreach.
> 2. **Phase E — Outreach + reply handling (S4, the gating long pole).** Warm-up inbox(es), Smartlead lead-add
>    from `prospect_approval.decision = approved` (backend-only clear-text — never through D's masked serializer),
>    A/B/C campaign send, reply queue → meeting. Phase E warm-up lead time is the schedule driver — start the
>    inbox warm-up clock as soon as D ships.
> 3. **Phase F — Booking + qualified-meeting confirmation (S5/S7).** `book/[token]`, the ≥10-min + 48h-dispute
>    qualified-meeting rule, post-booking contact reveal; closes the S7 billing loop (`prospect_approval` is leg
>    (a)). Then **G — billing/ledger**.
> 4. **Backlog / optional:** the *⚠️ Post-C review* deferred ICP inputs; a **step-3 console decide UI** for the
>    `decide_batch` endpoint (built + tested, no console UI yet); the `person` enrich-once cache (lands with
>    tenant #2); converting `WorkspaceProvider.reloadBatches` onto the repo's TanStack-Query cache (consistency,
>    not a bug).
>
> **⚠️ Context you MUST carry (non-obvious; the rest of the doc has the detail):**
> - **OpenRouter HK geo-block.** OpenAI / Anthropic / Google providers return **403 ToS** for this account
>   (Hong Kong) — account-wide, not content-driven. **Route every LLM call to non-US providers only**
>   (DeepSeek / Qwen / Mistral — Llama dropped 2026-06-22). Scoping model = `deepseek/deepseek-v4-pro`
>   with **thinking + the web-search plugin** (pinned in `research_spec.SCOPING_*`). ⚠️ Pro reasons
>   55–76s → **exceeds the 30s API Gateway sync cap**: viable only via a local backend or an async
>   structuring path; behind the gateway it 504s. **Fit scoring** = `deepseek/deepseek-v4-pro` (reasoning
>   `medium`) — also too slow for the sync path, so it runs in the **background** (chunked `/rescore`), never
>   on the find request (see *Step-1 scoring is async*, C7). (B0.)
> - **Apollo credit model (live-measured 2026-06-22).** **People search (`mixed_people/api_search`) = 0
>   credits.** **`people/match` = the spend: 1 credit/email** — empirically confirmed (the live smoke spent
>   exactly 1; 8 cr/phone async, `PHONE_ENABLED=false` at MVP), human-gated at Gate 2. **Company search**
>   surfaces only request-rate headers (50k/day), no credit field, and withholds firmographics ⇒ it looks
>   **request-metered, not credit-metered** (the API has no balance endpoint to prove it — one founder
>   dashboard glance closes this). All three calls are governed by the 50k/day request quota.
> - **Apollo plan gate — ✅ CLEARED (C0 smoke-tested 2026-06-22).** `holdslot/prod/apollo` is now
>   **Professional + master key**; all three endpoints return **200** (`mixed_companies/search`,
>   `mixed_people/api_search`, `people/match`). Live fixtures saved in `apps/api/tests/fixtures/apollo/`.
>   Header is `X-Api-Key`. Build C2/C4/C5 against these fixtures.
> - **C0 ambiguous keys — RESOLVED (fixtures overturned two research assumptions; `apollo_map` must follow
>   the fixtures, not the old notes):**
>   - **People SEARCH (`api_search`) is obfuscated by design — it does NOT carry `last_name`/`linkedin_url`/
>     `departments`/`organization_id`.** A row returns only `id`, `first_name`, `title`,
>     `last_name_obfuscated` (`"Sc***i"`), nested `organization.name`, and presence flags
>     (`has_email`, `has_direct_phone`). **All of that is revealed only by `people/match`** (enrich returns
>     `last_name`, `linkedin_url`, `departments:["master_sales"]`, real `organization.id`, `email`,
>     `email_status`). ⇒ **two design corrections:** (a) the **`departments` DB-side post-filter cannot run
>     pre-enrich** (field absent at search) — drop it or apply post-enrich; (b) **`max_per_company` / the
>     `company_id` link can't use `organization_id` from search** (null there) — **Flow B must loop one
>     `organization_ids:[<one>]` call per selected org** so the company is known from the loop.
>   - **Company SEARCH returns identity only, NOT firmographics/address.** Present: `id`, `name`,
>     `website_url`, `primary_domain`, `founded_year`, `organization_revenue`, `linkedin_url`, naics/sic,
>     headcount-growth. **Absent: `estimated_num_employees`, `industry`, and every address field** — so the
>     `street_address`/`postal_code` vs `raw_address` question is **moot for search** (address is enrich-only).
>     The employee/revenue **filters still work** (they constrained results); the values just aren't returned.
>   - **Still open (non-blocking):** the funding-**stage** filter key + codes (untested — needs a
>     funding-scoped query); confirm at C2 when building the intent-filter mapping.
>   - **Credits:** response headers are **request-rate quotas, not credit balances** (search 200/min · 6k/hr ·
>     50k/day; match 1000/min). Search withholds firmographics for free ⇒ consistent with **search = 0
>     credits, reveal/enrich = credits**; the smoke spent **1 enrich credit** (one `people/match`).
>     **$-cost confirmation still needs the founder's Apollo dashboard credit counter** (read before/after).
> - **Ops facts.** AWS access uses `AWS_PROFILE=holdslot`; founder writes ALL secrets (claude_code IAM is
>   read-only on `holdslot/prod/*`). Deploy = `apps/api/scripts/build-and-deploy.sh`. **git push needs the
>   `weftxio` gh account** (`gh auth switch --hostname github.com --user weftxio`, push, then switch back to
>   `checkafy`) — `checkafy` lacks write to `weftxio/holdslot`. Commit/push only when asked.

**The first build:** make HoldSlot's own product real enough to run our own outbound on it and land our
first signups. Scoped cut of the full spec in `backend-development-plan.md`.

> 📐 **Data schema — single source of truth:** every table (Apollo + internal DB, Phases A–C, built or
> planned) is defined in **[`data-schema.md`](data-schema.md)**. That doc governs all column/table
> definitions for the whole HoldSlot product. Any schema shown inline in this plan is **illustrative
> context only** — when the two differ, `data-schema.md` wins. Update `data-schema.md` first when the
> schema changes.

## Scope & Definition of Done

- **Scope:** the **single-tenant outbound → booked-meeting loop**, pointed at HoldSlot's own market.
  **HoldSlot is tenant #0.** Defer all multi-client *operations* (onboarding, self-signup, billing,
  analytics) — but **design the schema multi-tenant + role-aware from day 0.** Build single; design multi.
- **DoD:** land **6 signups in H1 (Oct'26 → Mar'27)** — the dogfood run *is* H1.
- **Timeline:** build now → Sept'26 (~4 mo); loop runs live Oct'26 → Mar'27.
- **Already live (not in scope):** marketing site + all 8 mock UI pages on Amplify (`138743894336`). This
  build replaces the mock data behind the loop's screens with a live API. UI defaults to tenant `holdslot`.

**The long pole is not code.** Cold-email **domain warm-up (~3 weeks)** gates every meeting and is the
critical path; **started 2026-06-17** (see *Sending infrastructure*). All external keys are provisioned
+ verified (2026-06-10).

## Tenancy & access model (build single, design multi)

Seed exactly one tenant + two users now, but make tenancy and roles first-class so adding a tenant is an
`INSERT`, never a migration.

- **One tenant** — HoldSlot itself (#0, slug `holdslot`), created by seed, not a feature.
- **Two users** — the founders, both `owner` of #0 with full access. Login is JWT (argon2 + refresh).
- **Clients don't log in** — they use tokenized approve/book/feedback links (separate expiring-token mechanism).

**Schema must support from day 0:** every domain row carries `tenant_id`; users↔tenants via a
`Membership` row with a `role` enum (`owner` + a lower-privilege `member`); access = **tenant scope ×
role**, enforced by one central guard. JWT signing keys → `holdslot/prod/app` secret; users, hashes,
tenants, memberships → Aurora.

## Build vs. skip

| Capability | This phase |
|---|---|
| Auth (JWT, 2 founders) · multi-tenant + role-aware schema (seed 1 tenant) · deploy | **BUILD** |
| Brief → ICP → ResearchSpec (LLM via OpenRouter) | **BUILD** |
| Prospect storage + filter/select · **Apollo connection** (design filter → search → score → enrich) | **BUILD** |
| Batch + internal approve · **Smartlead** (campaign, A/B/C, send, reply-to-thread) | **BUILD** |
| **Meeting** (booking → Calendar/Meet event + invites; capture held + duration via Meet REST) | **BUILD** |
| Sending domains + warm-up | operate (manual, start now) |
| AI reply drafting · summaries/transcripts · feedback links · masking · billing/Stripe · analytics · multi-tenant **operations** | **SKIP** (return when onboarding paying signups) |

## Phases (dependency- and priority-ordered)

| # | Phase | Must-build | Depends on | Pri | DoD |
|---|---|---|---|---|---|
| **A** | Foundation (S0) | Founder login; seed tenant #0; multi-tenant + role-aware schema; Aurora + deploy; console on live data | — | P0 | Both founders log in (full access); schema admits a 2nd tenant/non-owner role w/o migration |
| **B** | Targeting (S1) | Brief → OpenRouter `ResearchSpec`; ICP record | A | P0 | ResearchSpec saved, search-ready |
| **C** | Prospects + Apollo (S2) | design filter → Apollo search → fit-scored `Company`/`Prospect` rows; select → enrich | B · Apollo | P0 | Find→score→select→enrich runs in-app (no CSV) |
| **D** ✅ built | Batch + approval (S3 min) | Batch from enriched prospects → tokenized **masked** client-approval link → record per-prospect decision; approved set ready for E | C | P1 | Client approves a masked batch; `prospect_approval` rows exist (the S7 billing precondition) — **code complete + tested 2026-06-25; `0016` pending Aurora apply + live round** |
| **E** | Outreach + Smartlead (S4/S5) | Batch → campaign; A/B/C; send controls; webhook sync; cross-campaign Reply Queue; reply-to-thread | D · warm domains · Smartlead | P0 | Live sending; replies triaged in one queue |
| **F** | Book + meeting (S6 min) | Booking link → Calendar/Meet event + invites; capture held + duration | E · Google | P0 | Prospect self-books; held/duration recorded |
| **G** | Run & close (human) | Meeting → pitch live product → close → onboard signup (= new tenant, reuse A) | F | P0 | **6 signups over H1** |

**Critical path:** A → B → C → D → E → F → G.
**Parallel from day 0:** domain warm-up (**started 2026-06-17**, ready ~early Jul'26) · account setup (**keys done 2026-06-10**) · ICP + cold-email copy.
**After G:** stand up isolated `prod` (`terraform workspace new prod`) — see *Production isolation*.

**Simplification principle (simple now, scalable later):** one env (`dev`) to start (Terraform is
workspace-parameterised → prod is a new workspace, not a rewrite); one modular FastAPI service; manual
one-command deploy; JWT auth. The two things never shortcut (expensive to retrofit): `tenant_id` on every
row + a single central access guard.

---

## Modularization + W0–W8 backend hardening (landed 2026-06-25)

> A cross-phase hardening pass on the **built** stack (A–C), planned + executed 2026-06-25 (full as-built
> record below — formerly the standalone `modularization-plan.md`, now consolidated into this plan). **Two
> tracks, both merged to `dev` and deployed:** **(1) frontend modularization** — the workspace + client-status
> monoliths split into real nested App-Router routes; **(2) W0–W8 backend simplification** — nine waves from a
> money-bug fix to async scoring + caching. Live: backend **Lambda v46** (`196a31e`), frontend **Amplify dev
> build #38**, DB **head `0015`**. Gate green (backend `ruff` + 89 pass / 9 skip; FE typecheck + knip + build +
> 11 Playwright e2e). **No new product scope — this hardens what A–C already shipped; Phase D is still next.**

**Frontend modularization (PART 1).** Workspace → **7 nested routes**
(`brief`/`list`/`batches`/`campaign`/`replies`/`summaries`/`billing`) under a `WorkspaceProvider` layout
(cross-tab mock state preserved); client-status → **3 routes** (`approval`/`booking`/`feedback`). The hash-tab
apparatus is deleted; sidebar highlight + breadcrumb + back-button are now `usePathname()`-derived. A
**typed-API foundation** (`openapi-typescript` + `pnpm gen:api`) is in place — the full
`lib/api.ts`→`openapi-fetch` swap is **deferred** (staged, dev-QA'd, paid endpoints last; §1.7 there). First FE
test harness added (**Playwright route-smoke**). Rule #1 held: no copy / CSS / behaviour change.

**W0–W8 backend (PART 4), per wave.** W0 enrich double-spend fix · W1 perf composite indexes + `prospect.fit_reason`
(`0014`) · W2 dead-code removal + `fit_reason` populated · W3 request-id + access/exception logging + auth audit
(hashed email) + email redaction · W4 **async scoring** (`scoring_job` `0015`; 5 `*-async` kick-offs + poll;
`ASYNC_BATCH_MAX=20`) · W5 cursor pagination + auto-load (≤250) · W6 login cold-start retry (Aurora resume→**503**
under the 30s cap + FE backoff) · W7 LLM token trim (8 fit fields, PII dropped) · W8 warm-container `TTLCache`
(facet sidebar 300s, company search 90s).

**Per-phase Δ — what each phase's surface gained:**

| Phase | Δ from modularization + W0–W8 | Net effect |
|---|---|---|
| **A · Foundation** | W3 request-id middleware + access/exception/auth-audit logging (hashed email, body redaction); W6 Aurora cold-start retry (`ensure_awake`→503 under the 30s cap + FE backoff) — **partly closes A-follow-up #4** (scale-to-zero vs timeout). FE gained `SessionGuard` (pre-existing; 2 known ESLint warns, build unaffected). | Foundation now observable + cold-start-resilient |
| **B · Targeting** | W7 trims the **fit**-scoring prompt to the 8 fit-relevant brief fields (+ spec − `credit_policy` + ICP profiles); 13 operational/PII fields no longer reach the paid scorer. *Scoping (Brief→spec) still gets the full brief.* FE: brief tab is its own route. | Cheaper, PII-safe fit scoring — **founder score-diff QA owed** before relying on the trim |
| **C · Prospects/Apollo** | W0 enrich double-spend money-bug fixed (gate on `last_enriched_at`); W1 hot-path indexes + `fit_reason`; W4 **async scoring supersedes the C7 chunked `/rescore`** (now `scoring_job` + poll, 5 surfaces, ≤20/batch); W5 cursor pagination + auto-load on `/prospects`+`/companies`; W8 caches the facet sidebar + company search. FE: list tab is its own route. | Find→score→enrich is faster, credit-safe, off the 30s gateway cap |
| **D · Batch** | No backend yet. FE: the *Sendout/Approval Batches* surface is now `workspace/batches` (its own route); the 3 mock D surfaces still need replacing (audit unchanged). | Build target unchanged; cleaner FE seam to wire |
| **E · Outreach** | No backend yet. FE: campaign/replies/summaries are their own routes. **R1 (Smartlead `api_key` must stay out of logs) now has a home** — W3's request-path logger + redaction is where to enforce it. | Logging/redaction framework ready for E |
| **F · Book/meeting** | Unaffected (no FE/BE touched). | — |
| **G · Run & close** | Unaffected (human). | — |

**Still owed (founder dev-QA — needs paid runs):** W4 async-scoring click-throughs on all 5 surfaces · W7
score-diff validation · the C live end-to-end round (the S2 gate). *(Doc drift closed 2026-06-25:
[`data-schema.md`](data-schema.md) now extends through `0014`/`0015`.)*

### W0–W8 as-built (per wave)

The authoritative as-built record of the backend hardening (was `modularization-plan.md` PART 4; folded here
2026-06-25). Final pre-deploy gate: backend `ruff` clean · **89 passed + 9 skipped**; FE typecheck + knip +
build + 11 Playwright e2e green.

| Wave | Delivered (as-built) | DB | Verified |
|---|---|---|---|
| **W0** Stop the bleeding | Enrich gate now keys on `p.last_enriched_at is not None` (was `email_valid`/`email` — the active Apollo double-spend on a matched-but-no-email row); interim spend logging in `confirm_enrich` | — | unit |
| **W1** Schema migration | `(tenant_id, fit_score↓ NULLS LAST, created_at↓)` composite on `prospect`+`company`; 4 redundant single-col indexes dropped; `scope_override` `updated_at` trigger; `prospect.fit_reason` column | **`0014`** | applied + introspected on dev |
| **W2** Backend consolidation | Dead code removed (`suppress()`/`SuppressionResult`, `to/from_enrichment`, `configured_models`, `c_suite` collapse); `fit_reason` populated on score; `_parse_ids` bad-UUID→400 | — | ruff + unit |
| **W3** Logging framework | Request-id middleware (`X-Request-ID`) + access + global exception logging; `%(asctime)s` + `request_id` formatter; auth/authz audit at WARNING (hashed email); email-body redaction | — | middleware test |
| **W4** Async scoring (5 surfaces) | `scoring_job` table + `scoring.py` job infra (enqueue / env-aware dispatch / worker, single-in-flight per tenant×kind); 5 reusable cores shared by the kept **sync** endpoints (additive) + worker handlers; `SCORING_HANDLERS` registry; 5 kick-offs (`…-async`, 202) + poll `GET /scoring-jobs/{job_id}`; **`ASYNC_BATCH_MAX = 20`**. FE: `awaitScoringJob` poll + 5 `*Async` kick-offs, shared `runScoringJob`; >20 selection refused with a message | **`0015`** | applied; live empty-batch worker round-trip (zero spend) |
| **W5** Cursor pagination + auto-load | Opaque offset-cursor codec (`core/pagination.py`); `ProspectPage`/`CompanyPage` envelopes; `/prospects`+`/companies` take `?cursor`+`?limit` (default 100, ≤250) ordered by the W1 index **+ `id` tiebreaker** (a find batch shares one `created_at`). FE auto-loads to `LIST_CEILING=250` + "showing first 250" notice | — | live two-page dev smoke (overlap=none) |
| **W6** Login cold-start retry | BE: `get_db` wakes Aurora on a ~18s budget (`ensure_awake` attempts=3, delay=6s) under the 30s gateway cap; global `DBAPIError` handler maps Aurora-resume → retryable **503**, else logged 500. FE: `login()` retries only 503/502/504/network (never 401), backoff 2→6s to a 45s cap, "Waking the database…" button + `.hint` | — | resuming→503 / other→500 tests |
| **W7** LLM token trim | `_build_targeting` ships only the **8 fit-relevant** brief fields + spec **minus `credit_policy`** + ICP profiles; 13 operational/messaging/exclusion fields dropped; PII (emails/contact) no longer reaches the prompt. Scoping still gets the full brief; `/fit-prompt` preview reflects it | — | pure-fn tests |
| **W8** Caching | `core/cache.py` `TTLCache` (warm-container memo, bounded+TTL): people-facet sidebar memoized per (tenant, org-set) **300s** (~26 free Apollo probes → 1); company search cached **90s** by filter so a re-run of the same scope doesn't re-spend; find log marks `(cached)` | — | get/set/expiry/eviction tests |

**Folded, not skipped.** W2's structural moves (a `prospects/service.py` module, `_record_run`, the `db.refresh`
N+1, load-brief-once) and W3's integration-client failure logging (Apollo `_request`, OpenRouter `_execute`)
were **absorbed into W4** — those same endpoints were restructured into jobs there. `rows_accepted` /
`cost_per_accepted` stays **deferred** (dormant column): no meetings/billing domain yet to source a
qualified-meeting count. **Behaviour preserved:** find/lookalike still land rows **unscored** (no auto-trigger);
the worker scores in waves; the 20-row cap keeps a worst-case batch well under the Lambda timeout. **Back-compat:**
the legacy **sync** scoring endpoints (`/companies/{rescore,find-company,find-lookalikes,update-fields}`,
`/prospects/rescore`) are kept but unused by the web app — removable once async is dev-QA'd.

**Founder decisions that gated this work (all executed 2026-06-25):**

| # | Decision | Built as |
|---|---|---|
| #1 | `rows_accepted` | **Deferred** (dormant column) — no billing domain yet; `cost_per_accepted` wired tenant-level when it lands |
| #2 | Rescore slow path | **Full async** — background job + poll, all 5 scoring surfaces (W4) |
| #3 | `sourcing` value + `outreach_outcome` seams | **Kept** (cheap Phase-E seams) |
| #4 | `suppress()` primitive | **Deleted** (W2; revivable from git) |
| #5 | `fit_reason` shape | **`prospect.fit_reason` column** (W1) + populated on score (W2) |
| #6 | List endpoints | **Cursor pagination + auto-load-all** to a 250-row ceiling (W5) |
| #7 | LLM token trim | **Trimmed** to 8 fit fields + spec−`credit_policy` (W7); founder score-diff QA owed |
| #8 | Request-id + global exception handler | **Adopted** — `X-Request-ID` echoed to the client (W3) |
| #9 | Auth audit + login cold-start | **WARNING + hashed email** (W3) + retry-on-503 login, 45s cap (W6) |
| #10 | Log format | **Prose + fixed context keys** + `asctime` / `request_id` (W3) |
| #11 | Email body in non-prod | **Redacted** body, kept to/subject (W3) |

**Preserve (already good — don't "fix"):** `_new_survivors` new-only enrich dedup (credit safeguard) ·
single-in-flight structuring job · caps that **reject not truncate** · OpenRouter geo-routing (no US providers;
HK 403) · JSONB-as-opaque document (no path queries → no index pressure) · `llm_call`/`research_run`/`research_job`
are genuinely distinct (don't merge) · no schema↔ORM drift · clean `print()`-only-in-`scripts/` split.

### Frontend modularization — route map + deferred follow-ups

**Routes as built** (`apps/web/app/[client]/(console)/`): **workspace** → `brief` · `list` · `batches` ·
`campaign` · `replies` · `summaries` · `billing` (7), under a `WorkspaceProvider` layout that holds the
cross-tab **mock** state (`batches`/`campaigns`/`replies`) so the batch→campaign demo reactivity survives
sub-route navigation; the two API-backed tabs (`brief`/`list`) refetch on mount (no shared state).
**client-status** → `approval` · `booking` · `feedback` (3). Each `layout.tsx` renders its tab bar into the
topbar slot and derives highlight/breadcrumb/back-link from `usePathname()`. The hash-tab apparatus
(`useStatusTab`, `popstate`/`hashchange` effects, manual `pushState`) is **deleted**; legacy `#hash` links
redirect from the shrunk base `page.tsx`. CSS split by class-prefix into per-route files (class-selectors-only
→ zero leakage). Rule #1 held: no copy / token / CSS-class / behaviour change.

**Deferred follow-ups (planned, NOT yet built — the modularization backlog):**
- **Typed-API migration.** The foundation shipped (`lib/api-types.ts` generated from the live `openapi.json`;
  `pnpm gen:api`). The **full `lib/api.ts` → `openapi-fetch` swap is deferred** — it owns auth-token storage,
  refresh-before-401, single-flight refresh, the session events, and drives the **paid** Apollo endpoints, so
  the ~70-fn rewrite can't be safely big-banged here. Staged order when resumed: (1) add `openapi-fetch` +
  `lib/api-client.ts` middleware that calls the *existing* token helpers (auth byte-for-byte identical); (2)
  read-only GETs first; (3) mutations (icp/brief/company-people), each dev-QA'd; (4) **paid endpoints last, one
  at a time, manual dev-site QA** (`enrich` is the only credit spend); (5) delete the hand-written `authFetch`.
  Net: −~20K bundle, ~70 fewer hand-written fns, full end-to-end types.
- **Safe package swaps (founder-gated, behaviour-equivalent):** `components/Modal.tsx` → `@radix-ui/react-dialog`
  (keep all CSS classes; better focus-trap; +~4K); the `fmtShortDate`/`daysAgoLabel`/`MONTHS` helpers →
  `date-fns` (already installed, 0 bundle). **Keep (don't swap):** `Toast`, `useCountUp`, `tmpl.tsx`,
  `csv.ts` tokenizer (each ships own CSS or is tighter than the package).
- **Pure perf (zero behaviour risk):** memoize `toEnrich`/`enrichedSel`/`canBatch`/`rowsForCompany` + the
  People-Scope facet-options array; `React.memo` `FitScore`/`CompanyStudy`/`SpecChips`. **Parallelization
  (founder sign-off — changes error/ordering semantics):** initial 6-`reload*` load → `Promise.all`;
  `persist()` ICP updates/deletes; `confirmEnrich()` enrich+reload (preserve create-then-assign-id).
- **Dead-code:** un-export the 6 module-private `lib/csv.ts` helpers (`parseCsv`/`isDomain`/`normalizeDomain`/
  `normalizeUrl`/`rowsToText`/`ExclParseResult`); `knip` is in CI to catch future cruft.

---

## Phase A — Foundation (S0) ✅ BUILT & VERIFIED (dev)

Infra via Terraform (Aurora SLv2 + Data API, Lambda + SnapStart, HTTP API + `api.tryholdslot.com` w/ ACM,
SES, budget); schema + seed in Aurora; auth/clients API + central guard live (alias `live`); `/login` on
the live API; sidebar shows the signed-in user. Acceptance: both founders log in as owners; an ephemeral
2nd tenant + `member` role scopes correctly with **no schema change**; `verify_keys --strict` green for
app + google. 10/10 tests pass; ruff/black clean; no Terraform drift.

**Steps (as built):** A0 inputs locked (region us-east-1; founders both `owner`; build-stage password
seeded as argon2 hash from a secret, never committed; roles `owner`/`member` enum) → A1 scaffold
`apps/api`+`infra`+remote state → A2 one `terraform apply` (Aurora Data API, Lambda+SnapStart, IAM, SES,
CloudWatch, budget) → A3 ⭐ schema + Alembic + seed (`Tenant`/`User`/`Membership`/`RefreshToken`/
`PasswordReset`, every domain row `tenant_id`) → A4 core plumbing + JWT + the one central guard +
auth/clients API → A5 cut UI to live auth → A6 acceptance gate. **A3 is the highest-leverage step.**

**Known follow-ups (none block B):**
1. **SES — done for dogfood.** DKIM + DMARC verified; `no-reply@tryholdslot.com` sends; one-click
   password-reset flow live. *Deferred:* custom MAIL FROM + sandbox-exit (needed for client-facing mail at C+).
2. **Prod env** — decided: true prod isolation **deferred until after A→G** (see *Production isolation*).
   *Interim:* Amplify `main` points at the **dev** API/DB until cutover.
3. **CI/CD** — manual `apps/api/scripts/build-and-deploy.sh`; add a pipeline when B churn justifies it.
4. **Aurora scale-to-zero vs 30s Lambda timeout** — cold resume can approach the timeout; for prod set min
   ACU ≥ 0.5 or raise the timeout.
5. **S3 state bucket** public-access-block — add at prod hardening.
6. **OpenRouter `default_model`** — set in B0 (done).
7. **Refresh-token rotation** doesn't re-check `UserStatus` — harmless today (no deactivation flow).

---

## Phase B — Targeting (S1) ✅ COMPLETE (dev, Lambda v8)

Turns a client's free-text **Business Brief** into a research-ready, versioned **`ResearchSpec`** (the
bridge into the prospecting search) + curated **ICP** profiles. **First use of the LLM** (OpenRouter).

**DoD:** founder fills the Brief in the live Workspace → completeness ring reflects saved data →
"Generate Scope" produces a saved versioned `ResearchSpec` + gap prompts → one or more ICPs exist.
Search-ready; nothing sourced yet (that's C).

### The seam — one LLM job: the translator

The Brief is free text in the client's language; the prospecting API (Apollo) needs machine-actionable search params. That
translation is otherwise per-client operator labour. So the LLM sits at **one seam only: Brief (+ICPs) →
`ResearchSpec` + gap prompts.** It does *not* score fit (C), draft email (E), or converse.

**Value loop:** low-friction intake → versioned spec → Apollo search (C) → outreach (E) → meetings (F); each
completion returns **gap prompts** (what's too vague) to sharpen the Brief *before* credits are spent;
outcomes feed the next revision → spec vN+1 > vN. Versions are append-only = the loop's memory. Gap
prompts protect the two costliest resources (Apollo enrich credits, warmed inboxes) for a few cents of LLM.

### Design rule: the form churns — the backend must not care

- **Brief and each ICP are one JSONB document** — not typed columns. Only consumers are the form (opaque
  round-trip) and the LLM prompt (schema-tolerant). A form change = a frontend edit + maybe one entry in
  the required-fields list. **Zero migrations, zero API churn.**
- **Promote-on-demand:** promote a field to a validated column only when it becomes load-bearing for
  backend logic (e.g. exclusion lists in C).
- **Two stability profiles:** the form documents churn freely; the **`ResearchSpec` is a versioned
  contract** (the interface to the prospecting search — now Apollo, at **v3**). A provider/contract change
  is a deliberate version bump (v1→v2→v3), not silent drift. Spec versions are append-only JSONB.

### The `ResearchSpec` v3 format (v1 locked 2026-06-12 → v2 Apollo-mapped 2026-06-21 → **v3 Apollo-native 2026-06-22**)

**Why v3 (built 2026-06-22):** v2 still carried an intermediate vocabulary (`industry_keywords_*`,
`locations_*`, `funding`, `hiring_signals`) that `apollo_map` had to translate into Apollo's real field
names. v3 removes that layer — **the LLM emits the exact Apollo request fields by name**
(`q_organization_keyword_tags`, `organization_num_employees_ranges` comma-strings like `"10,100"`,
`person_seniorities` from Apollo's fixed enum, `latest_funding_date_range`, …), so `apollo_map` is a near
pass-through and the prompt can't drift from Apollo's contract. The spec is append-only JSONB, so v3 is **a
prompt + schema revision, zero migration** (`research_spec.version` inserts the next row; the *Prospect
Scope* panel renders whatever `spec_version` it loads — old v1/v2 rows still open).

**The full v3 field contract is documented once, authoritatively, in
[`data-schema.md`](data-schema.md) → *`research_spec.spec` — the v3 JSON contract*** (company/people search
params · intent filters · ICP validation · server-merged credit policy · `gaps` · `icp_suggestions`). It is
deliberately **not** re-listed here, to avoid the two copies drifting. Three structural facts drive the rest
of this plan:

- **Buying signals are native Apollo filters** in a separate `intent_filters` block — a closed-funding
  window (`latest_funding_date_range`) + active-hiring roles/dates (`q_organization_job_titles` +
  `organization_job_posted_at_range`), recency computed from an injected `today`. Fit **and** intent both apply.
- **`icp_validation`** characterizes the real paying customers (from the brief's `excludeCustomers` list) so
  the operator sees whether the stated ICPs match who actually buys; a material divergence surfaces **exactly
  one** `icp_suggestions[]` entry carrying its own ready-to-run company/people params (operator accepts → ICP).
- **Suppression feeds from the brief text, not the spec** — `excludeCustomers`/`excludeDeals`/`doNotContact`
  are applied HoldSlot-side *before* any Apollo call; v3 emits **no `exclusions` block**.

`apollo_map` (C2/C3, pure + fixture-tested) is the only consumer; it forwards each param to its Apollo slot
(`mixed_companies/search` / `mixed_people/api_search`) or to a DB-side `⊘` post-filter. **⚠️ Company search
itself may consume Apollo plan credits** (confirm at C0). **Division of labour:** the LLM emits targeting +
ICP validation only; the **credit policy** (email-status gate, phone off, hard caps) is **deterministic
server config merged at save time** — never LLM-inferred.

### LLM observability (built into the one seam)

One door for every LLM call = observability lives there once; every later feature inherits it. Right-sized
for dogfood:
- One append-only **`llm_call`** table (tenant-scoped, written per call): `purpose` · `model` ·
  **`prompt_version`** · in/out tokens · `cost_usd` · latency · `status` (`ok|parse_error|timeout|error`)
  · retries · **raw completion** (JSONB) · `created_at`.
- **`research_spec` links its `llm_call_id`** → every spec traceable to model/prompt/cost/raw output.
- **`prompt_version`** makes "spec vN+1 > vN" observable (compare gap counts, edit rate).
- **Cost control:** hard stop = the $50 OpenRouter spend cap (provider-side); soft = `SELECT sum(cost_usd)`.
- **Parse failures recorded before the bounded retry** — the top signal for prompt iteration.
- **Cut:** Langfuse/LangSmith/Helicone, OTel, eval harnesses — a queryable table + CloudWatch beats a vendor at this volume.

### UI: the spec review panel (existing classes only)

A "Structure research spec" `.btn-accent` by the brief progress bar; a read-only `.panel` ("Prospect
Scope") with a `.badge-info` version chip + older versions as `.badge-neutral`, the spec rendered in the
ICP-card `.icp-grid` grammar (exclusions as `.icp-chip.warn`), gap prompts in a `.brief-callout`, and the
`.est` line for caps. No new CSS.

### Tasks (as built)

- **B0 (gates cleared)** — real strict-`json_schema` completion through OpenRouter from HK:
  `default_model = deepseek/deepseek-v4-flash`, `models` fallback `[deepseek-v4-flash, llama-3.3-70b-instruct]`,
  `provider.require_parameters = true` (~$0.00015/call, ~18s). `verify_keys --strict openrouter` green.
  Required-fields rubric frozen from the UI Required/Optional tags.
  - ⚠️ **Region constraint (fixed 2026-06-21):** the OpenAI / Anthropic / Google providers return HTTP 403
    "violation of provider Terms Of Service" for this account's jurisdiction (Hong Kong — the same restriction
    that drove the Bedrock→OpenRouter override). It is account-wide, not content-driven (a bare "hi" 403s), and
    not a credits/key issue. **All model routing must use non-US providers** (DeepSeek / Qwen / Llama / Mistral).
    The original gemini/gpt-5 defaults caused `brief/structure` to 502; swapped to DeepSeek V4 Flash + Llama.
  - **Model choice (scoping):** B0 shipped on DeepSeek V4 Flash to fit the 30s sync Lambda budget (~18s).
    **B6 then moved scoping to the flagship `deepseek/deepseek-v4-pro`** (deeper reasoning + the web-search
    plugin, ~55–76s) by running it on the **async** `research_job` path — past the 30s API Gateway cap, so
    Pro no longer times out. Fit scoring also moved to `deepseek/deepseek-v4-pro` (reasoning `medium`); being
    ~15–25s/call it runs **off the request path** in the background (see *Step-1 scoring is async*, C7).
  - **Model routing override:** `HOLDSLOT_OPENROUTER_MODELS` (comma-separated) env var beats the secret's
    `models` — lets ops repoint models via a Lambda env var (or local dev) without a Secrets Manager write.
  - **Prompt-preview:** `GET /{client}/brief/structure/preview` returns the exact system + input prompt
    (same `build_messages`) with no LLM spend; the workspace "View prompt" popup renders it.
- **B1–B2** — tables `brief`/`icp`/`research_spec`/`llm_call` (Alembic `0003_phase_b`, up/down clean), all
  tenant-scoped; Brief+ICP JSONB document endpoints (`GET/PUT /clients/{c}/brief`, CRUD `/icps`); server-side
  completeness scorer + `missing[]`.
- **B3–B4 (the one LLM seam)** — single SnapStart-safe OpenRouter adapter (strict json_schema, models
  fallback, timeout + bounded retry, key-cache invalidation on 401/403) with built-in telemetry (every
  call → `llm_call` row + CloudWatch line; parse failures recorded before retry).
  `POST /clients/{c}/brief/structure` → versioned v1-valid `ResearchSpec` + gaps + server-merged credit policy.
- **B5 (frontend)** — Workspace *Business brief* + *ICP* tabs on the live API; **Prospect Scope** review
  panel (loading state, per-section x/N required counters, green Done labels, **"nothing to exclude"
  attestation checkbox** on each required exclusion list, gap callout); **Generate Scope** gated on all 6
  sections complete.
- **Quality:** 31 backend tests pass; ruff/black clean; 2-reviewer issues all fixed.
- **B6 — ResearchSpec v3 + async structuring (built 2026-06-22).** The B→C contract, now Apollo-native and
  run off the request path. Three parts:
  1. **v3 schema** (`research_spec.py`): strict `json_schema` + Pydantic validator → **exact Apollo request
     fields** (`company_search_params`, `people_search_params`, `intent_filters`, `icp_validation`,
     `icp_suggestions`, `gaps`). `SPEC_VERSION = 3`, `PROMPT_VERSION = "brief-structure-v5"`;
     `DEFAULT_SYSTEM_PROMPT` is seeded from / kept in lockstep with `docs/prompts/brief-structure-v5.md`
     (a drift test binds the constant to the seed file).
  2. **Async path** (`research_job`, migration `0009`): `POST /brief/structure` inserts a `queued` row and
     dispatches a background worker (Lambda **self async-invoke**; a daemon thread locally) on **DeepSeek V4
     Pro** (thinking + web-search plugin, ~55–76s); the UI polls `GET /brief/structure/status` until
     terminal. One in-flight job per tenant → a double-click can't double-spend.
  3. **Prompt store** (migration `0010`): `sourcing_doc`→`prompt` with a `stage` column
     (`briefing`/`sourcing`/`fit_scoring`); the `briefing` prompt is read **DB-first per client** (seeded
     v1), code-constant fallback. `CREDIT_POLICY` stays server-merged (`email_status_filter:["verified"]`,
     `phone:false`, caps) — never LLM-set.
  - **DoD (met):** Generate Scope produces a v3 spec asynchronously; the *Prospect Scope* panel renders
    every Apollo field for operator review; old v1/v2 spec rows still load. Re-run = `version+1`. 37 backend
    tests green; ruff/tsc clean; deployed to dev as Lambda v21.
- **Open item (doesn't block C):** founder end-to-end acceptance test on dev. Tick **S1** once run.

**Critical path:** B0 → B1 → B2 → {B3 → B4} → B5 → **B6**. After B, a Brief/ICP form change costs a
frontend edit + a rubric entry — no migration. **Cost:** ~$5–20/mo LLM; **no enrichment credits in B.**

---

## Phase C — Prospects: Apollo find + enrich (S2) ✅ BUILT & LIVE (Apollo-only, Lambda v46)

> **Architecture (locked 2026-06-21):** Phase C is **Apollo-only**. **Apollo.io is a true headless REST
> search + enrichment API** (company search, people search, `people/match`, one static key), so the whole
> find → score → select → enrich loop runs **in-app**: Apollo does discovery **and** enrichment; the LLM only
> (a) scopes the Apollo filter and (b) scores rows. No CSV import/export, no AI row-generation, no operator
> hand-off. All tables in [`data-schema.md`](data-schema.md).

### The one idea that drives everything

> **Apollo is headless discovery + enrichment compute. The HoldSlot DB is the only system of record.**

Apollo returns rows on a REST call; tenant ownership, dedup, suppression, fit scoring, lineage, and
outreach status all live in Postgres. The `suppression` gate, the `fit.py` scoring door, `identity_key`
dedupe, and the one central tenant guard are **reused across both flows unchanged**.

### Why Apollo
- **Programmatic REST.** `mixed_companies/search` + `mixed_people/api_search` use one static key
  (`X-Api-Key`) — the whole find → score → select → enrich loop is in-app, no CSV, no operator hand-off.
- **⚠️ Credit model (corrected 2026-06-21, deep research):** **People search (`mixed_people/api_search`) is
  0-credit** and returns no email/phone. **Company search (`mixed_companies/search`) is listed as
  credit-consuming in Apollo's current docs** (the old "search is free" model is retired) — *confirm the
  exact cost against the live plan's credit page at C0.* `people/match` is the heavy paid step (1
  credit/email · 8/phone, phone async via webhook).
- **Cost:** Apollo Professional (master key) — **company-search credits are a real line item** (budget +
  monitor); see *MVP running cost*.

### Locked decisions (founder, 2026-06-21)
| Decision | Choice | Why |
|---|---|---|
| Discovery + enrichment engine | **Apollo only** | Headless programmatic REST search + enrichment (one static key) |
| Plan | **Professional + master API key**, upgraded *once this plan is ready to execute* | Search/Match are paid-plan-gated (free key 403s) |
| AI sourcing loop | **Killed.** The LLM never generates rows | Apollo generates rows; LLM only scopes the filter + scores |
| LLM scoring | Per-row fit scorer on `deepseek/deepseek-v4-pro`, **run in the background** (chunked `/rescore`), never on the find request | Reasoning scorer is ~15–25s/call → a synchronous batch blows the 30s gateway cap (see *Step-1 scoring is async*, C7) |
| Real `batches` table | **Deferred to Phase D**; B.4 sets selection/status only | Avoid overlapping the next phase |
| Selection | Reuse existing `company.status` / `prospect.status` (no new `selected` columns) | Same meaning, fewer columns |
| Phone enrichment | **`PHONE_ENABLED=false`** default (8× email cost) | Off at dogfood |

### Endpoints map to the existing tenant — no new `campaigns` table
HoldSlot already has the "campaign": `Brief.data` + `Icp` + `ResearchSpec.spec` + the brief-derived
`ExclusionSet`. All Flow A/B endpoints stay **per-client (tenant)** and read the latest of those — exactly
as the old `import_companies` did. No new tenancy, no campaign table.

### Division of labor
| Actor | Job | Cost |
|---|---|---|
| **Apollo** (REST, headless) | company search (credit-consuming — confirm at C0) + people search (**0 cr**); `people/match` enriches the selected set | company search: plan credits · people search $0 · enrich 1 cr/email (8/phone) |
| **`apollo_map`** (pure, fixture-tested) | `ResearchSpec` v3 → Apollo request params (near pass-through — v3 already emits Apollo field names; no LLM); routes the `⊘` fields DB-side | — |
| **LLM** (OpenRouter, built) | **only** per-row `fit.score`/`score_company` (company/person fit), run in the background. *(All Brief→targeting judgment now lives in the B LLM that wrote the v3 spec — no second `design_filter` LLM pass.)* | OpenRouter $ (small) |
| **HoldSlot DB** (Aurora) | system of record: dedupe, suppression, DB-side post-filters, scores, lineage, status | — |

> **Architecture refinement (2026-06-21):** v1's plan had a second LLM (`design_filter`, purpose
> `apollo_filter`) re-distilling the brief into Apollo params at C3. With **ResearchSpec v3** emitting the
> exact Apollo request fields directly (keyword tags, comma-string ranges, funding/hiring signals, enum
> seniority), that mapping is
> now **deterministic** — `apollo_map` (pure, fixture-tested) replaces the LLM. This removes a drift
> surface (two LLMs distilling the same brief could disagree), an LLM cost, and makes the whole Flow A/B
> request build unit-testable. The `apollo_filter` purpose is **dropped**; fit scoring is the only Phase-C LLM.

### End-to-end flow (two gates · no CSV · no operator)
```
FLOW A — Find Company
  apollo_map.map_company_filter(spec.company_search_params + intent_filters) ─▶ Apollo mixed_companies/search (paginate; plan credits)
        └─ DB-side post-filter (founded/company_types/kw-exclude) + exclusion/existing-customer drop
        └─ upsert company on apollo_org_id (discovered), return UNSCORED ─▶ web app scores in background (chunked /rescore) ─▶ fit_score + reason
  GATE 1: review + PATCH companies/select  (status=selected) — scopes Flow B
FLOW B — Find People
  apollo_map.map_people_filter(spec.people_search_params, org_ids=selected apollo_org_ids)
        ─▶ Apollo mixed_people/api_search (0 cr, NO email/phone)
        └─ DB-side post-filter (title-exclude/departments/max_per_company) + exclusion drop
        └─ upsert prospect on apollo_person_id, link company_id directly (found, unenriched, scored in background)
  GATE 2 (enrich gate): review scores + select ─▶ POST prospects/enrich
        └─ Apollo people/match on selected ONLY (1 cr/email — the ONLY enrich spend; phone off) ─▶
           email / email_valid / phone / provider, status=scored
  CREATE BATCH (B.4) ─▶ selection/status only ─▶ Phase D approval (the real batches table is Phase D)
```
**Cost rules (enforced in code):** people search is 0 credits; **company search consumes plan credits**
(confirm cost at C0) — paginate only to `max_results`; never `people/match` before gate 2;
exclusion/existing-customer/post-filter is DB-side (no extra API calls); fit scoring runs in the background
(chunked `/rescore`, never on the find request — see *Step-1 scoring is async*, C7); enrich
only user-selected rows; phone off by default (8× + async webhook).

### Model usage — ONE LLM service in Phase C (`llm_call.purpose`)
The Brief→targeting LLM ran in **B** (writing the v3 spec); **`apollo_map` is deterministic (no LLM)**. So
Phase C's only LLM is the fit scorer:
| `llm_call.purpose` | Where | Function | Model | Notes |
|---|---|---|---|---|
| `company_fit` / `prospect_fit` | `fit.score`/`score_company` | per-row fit → `{ai_score, reason}` | **`deepseek/deepseek-v4-pro`** (`FIT_MODELS`), reasoning `medium`, `temp=0`, no web-search | ~15–25s/call → **run in the background, never on the find request** (see *Step-1 scoring is async*, C7); re-score on ICP/rubric edit |

> **Region rule (see B0):** OpenAI / Anthropic / Google providers are geo-blocked (403 ToS) for this HK account — every purpose routes to non-US providers only (Qwen / Llama / DeepSeek / Mistral).

The killed AI-loop purposes (`sourcing_round`, `candidate_validate`) **and the planned `apollo_filter`
purpose** are removed. Filter-building + dedupe are deterministic (no LLM).

### Apollo parameter contract (deep-researched 2026-06-21 — the `apollo_map` spec)
The authoritative request-param mapping. `apollo_map` (C2/C3, pure) builds exactly these from `ResearchSpec`
**v3**. **Because v3 already emits Apollo's field names**, the *source* column is now a **near-identity
forward** — `apollo_map` mostly copies each param straight across; the brief concept each field captures is
named below for reference (these are the pre-v3 names; in v3 the spec key matches the Apollo key). The real
work that remains is the comma-string/range packing and the `⊘` **DB-side** post-filters (Apollo has no
request param for those). **Confirm exact keys + the company-search credit cost against a live master-key
call at C0** before hard-coding.

**Flow A — `POST mixed_companies/search`** (auth `X-Api-Key`; **credit-consuming — confirm at C0**)
| Apollo request param | Type / vocabulary | ← ResearchSpec v3 (brief concept it captures) |
|---|---|---|
| `q_organization_keyword_tags[]` | free-text keywords | `industry_keywords_include` + `description_keywords_include` + distilled `semantic_description` |
| `organization_num_employees_ranges[]` | array of `"min,max"` strings (arbitrary bounds) | `employee_count {min,max}` |
| `revenue_range[min]` / `[max]` | int (plan-gated) | `revenue_usd {min,max}` |
| `organization_locations[]` | free text ("City, ST, Country") | `locations_include[]` |
| `organization_not_locations[]` | free text | `locations_exclude[]` |
| `latest_funding_amount_range[min]/[max]` · `total_funding_range[min]/[max]` · `latest_funding_date_range[min]` | int · int · `YYYY-MM-DD` | `funding.*` |
| `q_organization_job_titles[]` · `organization_num_jobs_range[min]` · `organization_job_posted_at_range[min]` | free text · int · date | `hiring_signals.*` |
| `currently_using_any_of_technology_uids[]` | **fixed Apollo tech UIDs** | `technographics.vendors` (when `enabled`) |
| `page` · `per_page` | int · **≤100** | paginate to `max_results` (Apollo hard cap: 500 pages = 50k rows) |
| **DB-side post-filter (no Apollo param):** | | `industry_keywords_exclude`, `founded`, `company_types` |
| `q_organization_keyword_tags` notes | no exclude variant; no free-text industry filter | (industry → keyword tags; tag-IDs are a later precision lever) |

**Flow B — `POST mixed_people/api_search`** (auth `X-Api-Key`, **master key**; **0 credits**, no email/phone)
| Apollo request param | Type / vocabulary | ← ResearchSpec v3 (brief concept it captures) |
|---|---|---|
| `organization_ids[]` | Apollo org ids | **selected** `company.apollo_org_id` — **pass ONE per call, loop over selected orgs** (C0: search rows carry no `organization_id`, so this is the only way to know each person's company). The Flow A→B scope link — required. |
| `person_titles[]` | free text, fuzzy | `job_title_keywords` |
| `include_similar_titles` | bool | `include_similar_titles` |
| `person_seniorities[]` | **fixed enum:** owner·founder·c_suite·partner·vp·head·director·manager·senior·entry·intern | `seniority` (B emits enum values) |
| `person_locations[]` | free text | `person_locations` |
| `contact_email_status[]` | enum: verified·unverified·likely to engage·unavailable | `credit_policy.email_status_filter` |
| `page` · `per_page` | int · **≤100** | paginate to `max_total` (cap: 500 pages = 50k) |
| **DB-side post-filter (no Apollo param):** | | `job_title_exclude` (on `title`); **`max_per_company` = per-call `per_page` cap** (one org per call). ⚠️ **`departments` is NOT in search output** (C0) — drop the pre-enrich departments filter, or apply it post-enrich. |
| **C0 reality — search row is obfuscated** | only `id`·`first_name`·`title`·`last_name_obfuscated`·`organization.name`·presence flags (`has_email`) | `parse_person` (search) maps `apollo_person_id`←`id`, `first_name`, `title`; rank by `has_email` |

**Enrich — `POST people/match`** (the only enrich spend; **reveals everything search hides**): `id`=`apollo_person_id`,
`reveal_personal_emails=true` (1 cr), `reveal_phone_number=PHONE_ENABLED` (8 cr, **async → requires `webhook_url`**,
off at MVP). Returns `email`, `email_status`, `last_name`, `linkedin_url`, `departments[]`, real
`organization.id`, `phone_numbers[]`, provider — `parse_person` (enrich) maps the full contact + `company_id`.

### Tasks (by dependency; all `[MVP]`)

**C0 — Validation gate (no code; blocks everything). ✅ DONE 2026-06-22.**
1. ✅ **Founder upgraded Apollo to Professional + master key** in `holdslot/prod/apollo` (`{"key": …}`).
2. ✅ **Smoke-tested the 3 endpoints** (`mixed_companies/search`, `mixed_people/api_search`, `people/match`)
   at `per_page:1` — **all 200**; `people/match` revealed a verified email. Fixtures saved to
   `apps/api/tests/fixtures/apollo/` (`companies_search.json`, `people_search.json`, `people_match.json`;
   `_smoke_test*.sh` regenerate them — they read the secret at runtime, store none). Build proceeds.
3. ⚠️ **Credit cost — partially confirmed.** Response headers are request-rate quotas only; search withholds
   firmographics for free (⇒ likely **search = 0 cr, enrich = the spend**). **$-cost still needs the founder's
   Apollo dashboard credit counter** read before/after → feeds *MVP running cost*.
4. ✅ **Ambiguous keys locked to the fixtures — see the NEXT SESSION banner for the full resolution.** Net:
   people SEARCH obfuscates `last_name`/`linkedin_url`/`departments`/`organization_id` (revealed only at
   `people/match`); company SEARCH returns identity but no firmographics/address. Two design corrections fall
   out: **drop the pre-enrich `departments` post-filter**, and **Flow B loops one `organization_ids:[<org>]`
   call per selected company** (search rows carry no org id). Funding-**stage** key still open (verify at C2).

**C1 — Data model (migration `0011`). ✅ BUILT.** `add company.apollo_org_id` (nullable, unique per tenant — feeds
Find People's `organization_ids`) · `add prospect.apollo_person_id` (nullable — the `people/match` key) ·
`drop tenant.seed_limit` (was AI-loop seed anchoring). **DoD:** models gain the two ids; `0010 → 0011`
head; up/down clean on dev.

**C2 — Apollo transport + adapters. ✅ BUILT** (parsers tested vs C0 fixtures; bodies live-verified 200).
- `integrations/apollo/client.py` (lazy secret, SnapStart-safe, mirrors the B3 discipline; header
  `X-Api-Key`, 429 backoff + pagination, `per_page` ≤100, 500-page hard cap): `search_companies`
  (`mixed_companies/search`, **credit-consuming**) · `search_people` (`mixed_people/api_search`, 0 cr, no
  email/phone, **master key**; **never** legacy `mixed_people/search` → 422) · `match_person`
  (`people/match`, the enrich spend; `reveal_phone_number` ← `PHONE_ENABLED` → requires `webhook_url`).
- `domains/prospects/apollo_map.py` (pure, fixture-tested): `map_company_filter(company_search_params,
  intent_filters)`, `map_people_filter(people_search_params, org_ids)`, `parse_company`, `parse_person` —
  **exactly the *Apollo parameter contract* tables above**. Since v3 emits Apollo field names, this is
  mostly a pass-through; the real transforms left are range-packing + the DB-side `⊘` post-filter set.
  **DoD:** builders + parsers
  unit-tested against the C0 fixtures, no network.

**C3 — Deterministic filter build + LLM fit scoring. ✅ BUILT (simplified).**
- **No `design_filter.py`, no `apollo_filter` LLM.** Filter building is `apollo_map` (C2, pure) consuming
  the v3 spec — the brief→targeting judgment already ran in B6.
- **Simplification (vs the original plan):** no new batched `score_rows`. The post-filter is the existing
  **`suppression`** (exclusion + existing-customer-domain drop, in `find.py`) and scoring reuses the
  already-tested per-row **`fit.score`/`score_company`** in the Flow A/B loops. Pure `find.filter_companies`
  / `filter_people` are unit-tested (`test_find`). The `departments` post-filter is **dropped** (C0: absent
  at search). Keep the `fit_scoring` `prompt`; the retired `sourcing` stage prompt is unused.

**C4 — Flow A (Find Company). ✅ BUILT.** `POST /{client}/companies/find-company` (A.1):
`search_companies(map_company_filter(spec.company_search_params + intent_filters))` (paginate, cap at `max_results`) → DB-side
post-filter + exclusion / existing-customer drop → upsert on `apollo_org_id` (`discovered`) → return rows
**unscored** + a `research_run` (`source="apollo"`); the web app fit-scores them in the background (see
*Step-1 scoring is async*, C7). `PATCH /{client}/companies/select` (A.3): `status=selected`. **DoD:**
companies land fast and fill in scores; selection scopes Flow B; `GET /companies` feeds the table.

**C5 — Flow B (Find People + enrich). ✅ BUILT.** `POST /{client}/people/find-people` (B.1): **loop the selected orgs**,
one `search_people(map_people_filter(spec.people_search_params, org_ids=[<one apollo_org_id>]))` call each
(0 cr, no email) — C0: search rows carry no `organization_id`, so the per-org loop is how `company_id` is
known and `max_per_company` = the per-call `per_page` cap → DB-side post-filter (`job_title_exclude` on
`title`; **no `departments` filter here — absent at search**) + exclusion drop → upsert on `apollo_person_id`,
link `company_id` from the loop, `status=found` (scored in the background). (Empty selected-org set →
`400 "select companies first"`.)
`POST /{client}/prospects/enrich` (B.3, reworked): Apollo `people/match` on the **selected** rows only →
write `email` / `email_valid` / `phone` / `provider`, `status=scored` (the only credit spend, human-gated).
B.4 sets selection/status; no `batches` table (Phase D). **DoD:** find → score → select → enrich runs end
to end on live Apollo; only selected people cost credits.

**C6 — Frontend wiring + legacy AI-loop teardown. ✅ BUILT** (wiring done; teardown done earlier). *(The teardown half — all the **Delete** items below —
was executed 2026-06-22 ahead of the rebuild; see the NEXT SESSION banner. What remains for C6 is the
**wiring** half: add the real Apollo client calls and turn the two disabled "Find" stub buttons into live
fetches.)*
- `lib/api.ts`: add `findCompanies`, `selectCompanies`, `findPeople`, reworked `enrichProspects`; **drop**
  `importProspectsCsv`, `importCompaniesCsv`, `runSourcingRound`, `acceptCandidates`, `saveSourcingSettings`.
  *(the four `drop`s already done; `enrichProspects` already trimmed to `{confirmed}`.)*
- Workspace `#list`: **"Trigger Find Companies" / "Trigger Find People"** go from CSV file-inputs to plain
  buttons → API fetch → table populates (layout/columns unchanged — the **AI Score** column already
  exists). Delete the **"copy seeds"** clipboard bridge (selection scopes Find People server-side) and the
  **enrich-export modal** (enrich is a real Apollo call now). Create-batch stays mock until Phase D.
- **Delete (dead under Apollo-only):** backend `sourcing.py` + the CSV/AI-loop transport; endpoints
  `POST /icps/{id}/research`, `/prospects/import`, `/companies/import`, `/sourcing-rounds`,
  `/prospects/accept`, `PUT /sourcing-settings`; `SourcingDoc` kind `sourcing_prompt`; `Tenant.seed_limit`
  + the Sourcing-settings modal; schemas `SourcingRound*` / `AcceptIn` / `*ImportResult` / `EnrichExportRow`
  / `SourcingSettings*`. Retire the now-unused CSV-import sourcing secret.

**C7 — Find Lookalike (find similar companies). ✅ BUILT & LIVE (Lambda v37, 2026-06-23).** A second discovery
door on Flow A: instead of scoping from the v3 spec, **the operator selects ≥1 row in the Step-1 table and
HoldSlot finds the next batch of peers**, mirroring Apollo's "Lookalikes · Powered by Apollo AI" panel.

> **API reality:** **Apollo has NO lookalike / similarity API.** The Lookalikes panel is a UI-only Apollo-AI
> feature; [`mixed_companies/search`](https://docs.apollo.io/reference/organization-search) exposes
> `organization_ids[]` (*include*) but **no `organization_not_ids`** and **no seed/similar param**. So
> "lookalike" is **synthesized HoldSlot-side** from the selected rows' firmographics (deterministic, no LLM,
> no extra credit), then run through the existing Flow A search.

**Locked decisions (founder, 2026-06-23):** synthesis = **deterministic aggregation** over the seeds' evidence,
spanning/union across a multi-select · **fetch cap 10** (`per_page≤10`, one page); seeds + known domains drop
post-fetch via existing suppression → net new batch **≤10, often fewer** (no over-fetch) · new rows keep
**`source="apollo"`**, but the `research_run` lineage row carries **`source="lookalike"`** so the cost
scoreboard separates seeded from scoped finds.

**The aggregator** ([`lookalike.build_lookalike_filter(seeds) → company_search_params`](../apps/api/app/domains/prospects/lookalike.py),
pure, 7 fixture-tests) maps the seeds' evidence onto the four Flow-A firmographic axes:
- `q_organization_keyword_tags[]` — **union** of each seed's `evidence.keywords` + `industries` + `industry`,
  deduped case-insensitively, capped at 10 (Apollo ORs tags — too many over-broadens).
- `organization_num_employees_ranges[]` — a **single band** spanning min→max headcount across all seeds,
  widened 0.5×–2× so same-size-band peers surface (falls back to the `size` string when evidence is absent).
- `revenue_range[min/max]` — **min→max** of seeds' `annual_revenue`, widened 0.5×–2×.
- `organization_locations[]` — **union** of seeds' `country` (HQ city is too narrow for "lookalike").
- All-sparse selection → **empty filter `{}`** → the endpoint refuses (400), never searching wide.
- **No** intent/funding block (lookalike is firmographic, not timing) · **no** tech UIDs (deferred resolver) ·
  `icp_id` = explicit → seeds' common → null (fit scores against the ICP union, exactly as Flow A).

**Reuses the Flow-A tail** — the only new code is the endpoint + the pure aggregator. The tail was extracted as
[`_run_company_find`](../apps/api/app/domains/prospects/router.py) (shared by Find Company and Find Lookalike):
search → suppress/dedupe → enrich new → upsert → optional score → `research_run`, with per-stage timing logs
that flag any request crossing the 30s gateway cap. The seeds drop out because Find Lookalike passes
`seen_domains` (all existing tenant domains) into `find.filter_companies` — domain dedupe excludes them with no
`organization_not_ids`.

- **Endpoint:** `POST /{client}/companies/find-lookalikes` · `CompanyLookalikeIn {company_ids, icp_id?}` →
  `FindResult`. Empty `company_ids` → `400`; all-sparse seeds → `400 "enrich them first"`.
- **Web:** ghost button **"Find Lookalike"** in the Step-1 toolbar (before "Update Enrichment"), disabled
  unless `coSelCount`, label shows the seed count (`Find Lookalike 3`) → `findLookalikes(client, …)` → reload →
  toast that tells the outcomes apart (new peers found / all already listed / seeds too sparse). Found rows
  scored in the background (see below). No input box — selection is the seed.
- **DoD (met):** select rows → Find Lookalike → ≤10 peers land, seeds excluded, `source="apollo"` /
  `research_run.source="lookalike"`; scored in the background; aggregator unit-tested (no network).

#### Step-1 scoring is async — fit scoring never blocks the find request (2026-06-23)
> **⚠️ Superseded 2026-06-25 (W4).** The chunked client-driven `/rescore` described below was replaced by a
> server-side **async scoring job** (`scoring_job` table, `0015`) + poll across all 5 scoring surfaces — see
> *Modularization + W0–W8* → **W4** above. The "never blocks the find request" intent is unchanged; the
> mechanism is now a real job, not 3-row chunks.

Built this session across **all three Step-1 buttons** (Find Company, Find Lookalike, Update AI Score). The
driver: fit scoring is **`deepseek/deepseek-v4-pro`** (reasoning effort `medium`, `temp=0`, no web-search;
[`fit.FIT_MODELS`/`FIT_EXTRA_BODY`](../apps/api/app/domains/prospects/fit.py)) — deep reasoning at ~15–25s/call
(25s timeout + 1 retry → a slow call nears ~50s). A fresh batch scored synchronously **blew the 30s
API-Gateway sync cap** → 503. *(This was the root cause of the field report "no company returned, still 15 in
the list": CloudWatch showed a 95s Lambda → gateway 503 — not an empty result, not an Apollo error.)*

**Architecture:** separate the fast find from the slow score.
- **Find/Lookalike return rows UNSCORED** (`_run_company_find(score=False)`) — search + enrich only, always
  well under 30s.
- The **web app scores in the background**: `scoreInBackground(ids)` fires chunked `POST …/companies/rescore`
  calls (**3 rows/chunk**, each safely under 30s) and shows a per-row **"Scoring…"** spinner in the AI Score
  column until each chunk lands, then the fit chip fills in. The table stays visible throughout (no full-list
  overlay); **Update AI Score** reads "Scoring…" and is disabled while a pass runs.
- **Never blocks the UI, never fails the request on a slow LLM.** A failed chunk just clears its status (rows
  stay unscored, recoverable by re-clicking Update AI Score); switching clients stops the loop.
- **Cost attribution:** scoring spend is now booked under **`research_run.source="rescore"`**; the
  `apollo`/`lookalike` find-runs show `cost_usd=0` (search/enrich only). Total unchanged — it just maps to the
  scoring step, matching the async model. `/rescore` is capped at `MAX_COMPANIES_PER_FIND` (15) per request and
  rejects (not truncates) a larger selection.

**C8 — Company-centric Step-2 + persona facets. ✅ BUILT & LIVE (Lambda v44, 2026-06-24).** Step-2 (Find
People) was reworked from a flat people list into a **company-centric** flow — find / score / enrich people
**per company** — and gained a **persona-targeting** layer over Apollo's people search:
- **Persona targeting by Management Level × Department.** The Find Settings modal exposes Apollo's
  `person_seniorities` (11-value enum, "Management Level") × `person_department_or_subdepartments` (14 master
  departments + subs) as the operator's persona selector. A **live facet sidebar** shows per-value people
  counts in scope (`POST /{client}/people/facets`, `PeopleFacetsIn/Out`) — counts come from Apollo people
  search, which is **0 credits**, so the sidebar refreshes freely (one `organization_ids` array across the
  selected orgs; 11 seniority + 14 department probes, subs are selection-only/no count to bound the calls).
- **Fixes folded in:** row/column alignment in the company-grouped table; a **0-people over-constraint** fix
  (settings that returned nobody); a **Remove** action; band-button order → Find Settings · Find People ·
  Confirm enrich · Remove.
- **DoD (met):** operator scopes a persona, sees live counts, runs Find People per selected company, scores +
  enriches in-app; no credit spend until `people/match`.

**C9 — Persisted people-scope override (migration `0012`). ✅ BUILT & LIVE.** The Step-2 Find Settings persist
**server-side per tenant** as a people-scope override, so the persona scope survives reloads and is reused on
the next find — exactly mirroring the Step-1 Settings override, but stored (not per-call). `PeopleScopeOverrideIn/Out`;
`GET/PUT/DELETE /{client}/people/scope-override` (empty/`DELETE` reverts to the AI scope from the v3 spec).
Hardened in a code-review follow-up (`d26dc55`). **DoD (met):** saved scope reloads and drives the next
people search; clearing it reverts to the spec scope.

**C10 — Fit rubric split: `company_fit` + `prospect_fit` (migration `0013`). ✅ BUILT & LIVE.** The single
`fit_scoring` prompt stage was split into **two editable rubrics** so each LLM purpose has its own system +
input prompt:
- **`company_fit` (Step 1)** — scores a company's *buying intent* (verdict-only: `fit_score` + reason, tier
  derived; `build_company_messages`/`score_company`).
- **`prospect_fit` (Step 2)** — scores a *person's* reply potential × decision-making power, fed the selected
  prospect's metadata (`_prospect_payload`: name/title/seniority/departments/email + the parent company's
  firmographics and its stage-1 `company_fit` verdict) alongside the client brief (`build_messages`/`score`).
- **Frontend:** the Fit-rubric modal is **stage-aware** — Step 1 shows "Fit rubric · Step 1 · Companies" /
  `purpose · company_fit`, Step 2 shows "… Step 2 · People" / `purpose · prospect_fit`; each saves its own
  versioned doc. Unified preview route `GET /{client}/fit-prompt?stage=…&sample_id=…`; `getFitPrompt(client,
  stage, sampleId)` / `saveSourcingDoc(client, stage, body)`; `SourcingDocList{company_fit, prospect_fit}`.
- **Migration `0013`** renamed the existing `fit_scoring` prompt rows to `company_fit` and seeded
  `prospect_fit` from the same body (append-only; up/down clean). **DoD (met):** two independently-editable
  rubrics; Step-2 scoring receives prospect metadata; modal badge reads the correct purpose per step.

**Critical path:** C0 → C1 → C2 → C3 → C4 → C5 → C6 (→ **C7/C8/C9/C10 additive**, no dependency past C5).
**C1/C2/C3 can be built in parallel against the C0
fixtures** before the live key is integration-ready; only C0's smoke test + C4/C5 end-to-end need the
upgraded plan. **Depends on B6** (the v3 spec `apollo_map` consumes — built). **MVP cost:** Apollo Professional
(master key — see *MVP running cost*) + LLM <$10/mo; **people search is 0 credits**, but **company search
consumes plan credits** (confirm at C0) and the gate-2 enriched set spends 1 cr/email.

### Post-C review — B→C leverage gaps (re-studied + partly CLOSED 2026-06-22)
The B6→C coverage study confirmed the **fit + intent + exclusion** spine forwards end-to-end. A deeper
re-study found the real gap was NOT in the Apollo search params but in the **fit-scoring context**: the
rubric grades `maturity`/`tech` (§2) and `department`/`economic-buyer` (§3) **directly off the ICP doc**, but
`_build_targeting` passed only `{brief, spec}` — no ICP rows. By the rubric's own "Unknown policy" those 16
points scored **0 on every prospect** (a structural tier ceiling), and `avoidTitles` had no consumer at all.

**CLOSED (no migration, no prompt-version bump, no spec-schema change — pure context alignment):**
- **GAP 0 — ICP docs → fit context.** One shared `icps.icp_docs(db, tenant, icp_id=None)` helper (the exact
  construction B's scoping already used — de-duplicated from `briefs/structuring.py` + `briefs/router.py`) is
  now threaded into `_build_targeting` at all four fit call sites (`add_company`, `find_company`,
  `add_prospect`, `find_people`). ICP-scoped when the run carries `icp_id`, else the union of all profiles.
  Recovers maturity/department/economic-buyer/tech scoring AND makes `technologies`/`departments` visible to
  the scorer for ranking — so they no longer need a search-param to be leveraged.
- **GAP 1 — `ICP.avoidTitles[]`.** Read straight from the ICP doc GAP 0 already loads and applied as a
  case-insensitive `title` **pre-score drop** in `find.filter_people` (Apollo people search has no native
  exclude-title field). Keyed per ICP so a run spanning ICPs never over-drops. No `job_title_exclude` spec
  field, no prompt edit — the earlier plan over-built this. Activates when the find run is ICP-scoped (the
  workspace already passes `icp_id`).

**Still deferred (now correctly — each is leveraged for *scoring* via GAP 0, only the Apollo *query*-side is open):**
- **`ICP.technologies[]` (search-side)** — `currently_using_any_of_technology_uids[]` needs Apollo's fixed
  tech UIDs (a resolver we don't have). Scorer already sees the names. Post-MVP.
- **`ICP.departments[]` (search-side)** — C0 proved search output carries no `departments` (revealed only at
  `people/match`); native `person_department_or_subdepartments[]` is untested. Titles cover it. Post-MVP.
- **`revenue_range`** — present in the spec but **no ICP form field feeds it** → LLM-guessed/null. Add a
  revenue band to the ICP form, or accept null (employee bands already constrain size). Low priority.

Also note (C0-derived, not a gap to close — just behavior to honor in C4/C5): company-search rows are
**sparse** (`industry`/`size`/address null — fit scores on name/domain/revenue); people-search rows are
**obfuscated** (full name/linkedin/email/departments appear only at `people/match`), so person-level
`doNotContact` suppression can only run **post-enrich**, and Flow B must **loop one org per call** to know each
person's `company_id`.

### Cross-phase
- **From A:** the central guard scopes every table; **MVP adds ZERO AWS resources** (`find-company` /
  `find-people` / `enrich` are routes on the existing `$default` proxy).
- **From B:** `ResearchSpec` **v3** (`company_search_params` / `people_search_params` / `intent_filters` /
  `icp_validation`, in exact Apollo field names with funding + hiring signals + enum seniority) is the
  `apollo_map` input — consumed **deterministically** into Apollo params (no second LLM). Suppression feeds
  from the brief text (no `exclusions` block). The B3 adapter + `llm_call` + `prompt_version` are reused
  as-is for fit scoring.
- **To D:** `fit_reason` + score are client-facing on the approval page; create-batch hands the selected
  enriched set to Phase D, which builds the real `batches` table.
- **To E:** `outreach_outcome` (schema present, written by E) closes the self-improve loop; the fit bar is
  a deliverability control. **Domain warm-up runs in parallel** (already started — see *Sending infrastructure*).

### Operational sign-off — what's left to tick S2 (not code)
- ✅ **Apollo plan upgrade (done).** Professional + master key in `holdslot/prod/apollo`; all 3 endpoints 200.
- ⏳ **Founder end-to-end round on Apollo** — the one gate left. From the live Workspace: Find Companies →
  review/score → select → Find People → review/score → confirm-enrich (Apollo `people/match`) → create batch
  — all in-app, no CSV; the scoreboard shows real `cost_usd`. **Tick S2 once run.**
- ⚠️ **Credit-cost dashboard glance (optional confirm).** Founder reads Apollo → Settings → Usage/Credits
  before vs. after a find run to confirm company search doesn't draw the monthly pool (enrich = 1 cr/email is
  already empirically confirmed). Feeds *MVP running cost*.

---

## Open items across A–C (the pending register, 2026-06-24)

A consolidated list of everything still open in the **built** phases. None block forward progress to D; the
two ⏳ acceptance rounds are the only gates that tick S1/S2. Code is current at **Lambda v46 / `196a31e`**
(dev), DB at migration `0015` — modularization + W0–W8 hardening landed (see that section).

**Phase A — Foundation (7 known follow-ups; all non-blocking):**
1. **SES** — DKIM/DMARC verified + reset flow live; *deferred:* custom MAIL FROM + sandbox-exit (needed for
   **client-facing** mail at D+ — the approval/booking emails go out in D, so this is now D's gating SES item).
2. **Prod env** — true isolation deferred until after A→G; Amplify `main` points at **dev** API/DB until cutover.
3. **CI/CD** — manual `apps/api/scripts/build-and-deploy.sh`; add a pipeline when churn justifies it.
4. **Aurora scale-to-zero vs 30s Lambda timeout** — cold resume can near the timeout; prod sets min ACU ≥ 0.5.
5. **S3 state bucket** public-access-block — add at prod hardening.
6. **Refresh-token rotation** doesn't re-check `UserStatus` — harmless today (no deactivation flow).
7. **OpenRouter `default_model`** — set (B0). *(Resolved; listed for completeness.)*

**Phase B — Targeting (1 open):**
- ⏳ **Founder end-to-end acceptance test on dev** — the only gate to tick **S1**. (Brief → Generate Scope →
  v3 spec saved → ICPs exist.)

**Phase C — Prospects (1 gate + confirms + deferred ICP inputs):**
- ⏳ **Founder live end-to-end round on Apollo** — the one operational gate to tick **S2** (see *Operational
  sign-off* above).
- ⚠️ **Apollo credit-cost dashboard glance** — confirm company search doesn't draw the monthly pool.
- **Deferred ICP inputs (search-side only — each is already leveraged for *scoring* via Post-C review GAP 0):**
  - `ICP.technologies[]` → `currently_using_any_of_technology_uids[]` needs Apollo's fixed tech-UID resolver
    (we don't have one). Post-MVP.
  - `ICP.departments[]` *search-side* — C8 now exposes Apollo's native `person_department_or_subdepartments[]`
    in the persona facet sidebar, so the operator can refine by department at search time; the old "drop the
    pre-enrich departments filter" caveat applies only to the *DB-side post-filter*, not the facet selector.
  - **`revenue_range`** — no ICP form field feeds it → LLM-guessed/null. Add a revenue band to the ICP form, or
    accept null (employee bands already constrain size). Low priority.
- **Funding-stage filter key** — still unverified (needs a funding-scoped Apollo query); non-blocking.

**Cross-cutting:**
- **Doc/schema drift — closed (2026-06-25).** Plan banner + Phase C + this register are in sync with `196a31e`
  (Lambda v46, DB head `0015`); the modularization + W0–W8 record is consolidated into this plan (see
  *Modularization + W0–W8* — `modularization-plan.md` retired), and [`data-schema.md`](data-schema.md) now
  extends through `0014` (perf indexes + `prospect.fit_reason`) + `0015` (`scoring_job`).

---

## Phase D — Sendout Batch + Client Approval (S3): the revenue precondition ✅ BUILT 2026-06-25 (code complete + tested; `0016` pending Aurora apply)

> **BUILT 2026-06-25** — D1–D6 all landed (backend `domains/batches` + `domains/approvals`, Alembic `0016`,
> `apps/web` 3 surfaces live). Backend **100 pass / 10 skip** + ruff clean; web typecheck + lint + `next build`
> all clean. **Remaining to ship:** (1) `alembic upgrade head` (0015 → 0016) on dev Aurora, then redeploy the
> Lambda; (2) the DB-gated end-to-end (`tests/test_batches.py::test_batch_end_to_end_*`) + the founder smoke
> (enrich → Create batch → send → open masked link → approve) run against the live env. All five decisions
> founder-confirmed (see *Locked decisions*); scope = exactly the three surfaces in *Surfaces covered*.
> **D0 gate cleared 2026-06-25** — SES production access live (200→50,000/day) + custom MAIL FROM
> `mail.tryholdslot.com`.

Phase D = **S3 · Sendout batch & client approval** — the **revenue precondition**: a `prospect_approval` row is
the billable agreement S7 charges against. It groups the enriched Phase-C prospects into a **batch**, sends the
client a **tokenized, expiring approval link** showing each prospect with enough *fit context* to approve in one
click **but with identity + contact vectors masked**, records the per-prospect decision, and hands the approved
set to Phase E. Builds the **real `batches` table** C deliberately deferred (B.4 set selection/status only), and
replaces all three mock D surfaces with live API. Source of truth: [`backend-development-plan.md`](backend-development-plan.md) §S3.

> **★ Posture: simplest full function — reuse what A/B/C already shipped; add NO new infrastructure.** The four
> primitives D needs already exist: the **password-reset opaque-token pattern** (mint `secrets.token_urlsafe` →
> store SHA-256 hash → single-use `used_at` → **expiry checked on read**), the **SES `send_email()` adapter**, the
> **`require_membership` guard**, and **ad-hoc `_out()` serializers**. So D needs **NO EventBridge** (expiry is a
> read-time check, not a scheduled flip — the established pattern), **NO async worker** (a batch send is one SES
> call, well under the 30s cap), **NO new "signed-token service"** (the opaque-hash token is it), and **NO new AWS
> resources** — every route rides the existing `$default` proxy. The §S3 "EventBridge (expiry/reminders)" line is
> the one place this plan **simplifies the spec**: expiry-on-read + **operator-driven** reminders (the UI's
> *Follow-Up Approval* button resends the live link); automated reminder scheduling is **[SCALE]**.

### The one idea that drives everything

> **Approved prospects are the billable agreement; the client never sees clear-text contact data.** Masking is an
> **allow-list** serializer on the *public* approval endpoint (emit only the pre-approval fields, never the row) —
> not a deny-list or a regex over the blob. Once a prospect is `approved`, its clear-text email/phone routes
> **backend-only** into Smartlead (E). `prospect_approval` is **append-only billing evidence** — "removed" is a
> decision value, never a delete.

### Locked decisions (all founder-confirmed 2026-06-25)

| # | Decision (was open) | Resolved as | Why |
|---|---|---|---|
| 1 | Link lifetime + reminders | **3-step escalation ladder, all expiry-on-read (no scheduler):** (1) link live **7 days** → (2) operator *Follow-Up Approval* **resends for another 7 days** (mints a fresh 7-day link once the first lapses) → (3) still no response → **human manual follow-up**: the operator records the decision by hand in-console (`POST /{client}/batches/{id}/decide`, owner) / contacts the client offline. Automated reminders = [SCALE] | Mirrors `password_reset` expiry-on-read; **no EventBridge**; the human step needs no infra |
| 2 | Sendout email template | **Seed the default from the existing *Sendout template*** already authored on the **List approval** page (`client-status/approval` — subject/body/cta with `{{client_name}}`/`{{count}}`); per-tenant **editable override** (`approval_template`, one JSONB row, mirrors `brief`). **No founder copy owed** — the live UI template *is* the copy; D1/D3 lift it verbatim | The editor + copy already exist; reuse, don't re-author |
| 3 | Masking field set | **Hide ALL prospect enrichment / contact data** (LinkedIn URL, email, phone) — emit **fit context only** (name + initial, company *descriptor*, title/seniority, fit reason); **no raw vectors and no verified-presence badges** (matches `design/client-approval.html`). Post-booking reveal **deferred to F** | Founder "hide all enrich data"; also the design-faithful set |
| 4 | Batch model scope | **Build the real three tables now** (`batch` + `prospect_approval` + `approval_link`) + the tiny `approval_template`. Counts derived, not stored | The mock surfaces need all three; deriving counts avoids drift |
| 5 | Async send? | **No** — synchronous SES call per batch send (low volume, <30s). No `research_job`-style worker | Simpler than B/C; a send is one email |

### Schema (inline context — canonical defs land in [`data-schema.md`](data-schema.md) at D1)

All tenant-scoped, same conventions (uuid PK, `tenant_id` CASCADE, `timestamptz`, string status — no DB enum).

- **`batch`** — `id` · `tenant_id` · `name` · `icp_id?` (SET NULL) · `status` (`draft`→`sent`→`approved` |
  `changes_requested`) · `created_at` · `sent_at?` · `decided_at?`. *(total/approved counts are **derived** from
  `prospect_approval`, not stored.)*
- **`prospect_approval`** ⭐ **the billable record** — `id` · `tenant_id` · `batch_id` (CASCADE) · `prospect_id`
  (CASCADE) · `decision` (`pending`→`approved` | `removed`; `request_changes` is a batch-level state) ·
  `created_at` · `decided_at?`. **Append-only** (one per prospect-in-batch); `unique(batch_id, prospect_id)`.
- **`approval_link`** — mirrors `password_reset` — `id` · `tenant_id` · `batch_id` (CASCADE) · `recipient_email`
  · `token_hash` (SHA-256, unique; raw token only in the emailed link) · `expires_at` · `used_at?` · `created_at`.
- **`approval_template`** — one JSONB doc per tenant (mirrors `brief`) — `id` · `tenant_id` (unique) ·
  `data` (`{subject, body, cta}` with `{{client_name}}`/`{{count}}` tokens) · `updated_at`. *(Thinnest slice — a
  code default serves until the founder edits it.)*

### Tiered masking — the security-critical serializer (`GET /approve/{token}` `_out`)

**Allow-list only** — the external serializer emits exactly these and nothing else (a deny-list would leak on a
new field). Per founder direction ("hide all enrich data"), it emits **fit context only — zero enrichment/contact
vectors**:

| Client sees (pre-approval — fit context ONLY) | Derived from |
|---|---|
| First name + last initial — "Sarah K." | `enrichment.full_name` |
| Company **descriptor** — "SaaS · 200–500 · US" (*not* the exact company) | `company.industry`/`size`/`country` |
| Title · seniority | `enrichment.title`/`seniority` |
| Fit tier + `fit_reason` (already client-facing copy) | `prospect.fit_tier`/`fit_reason` |

Plus batch name, live count, client name, and an `expires_at`/state (`valid`/`expired`/`used`) so the page picks
its pane. **Withheld — ALL enrichment / contact data:** email, phone, **LinkedIn URL**, full last name, exact
company `name` + `domain`, `fit_components` internals — **and no verified-presence badges** (the design shows
none). This is byte-for-byte what `design/client-approval.html` renders (name · title·company · why — nothing
else). **Post-booking reveal (full name + exact company + LinkedIn) is Phase F** — the serializer gains a `tier`
param then; D ships pre-approval only.

### End-to-end flow (two surfaces · one tokenized gate · no clear-text to the client)
```
CONSOLE (operator, JWT + owner)
  POST /{client}/batches {prospect_ids[]}  ─▶ batch(status=draft) + prospect_approval(pending) per prospect
  PUT  /{client}/approval-template          ─▶ edit the sendout copy (seeded from the List-approval template)
  POST /{client}/batches/{id}/send {email}  ─▶ mint approval_link (token+hash, 7d expiry), status=sent, sent_at,
                                               send_email() via SES with {{token}} link
  POST /{client}/batches/{id}/send  (again) ─▶ STEP 2: Follow-Up resends; if the link lapsed, mint a fresh 7d link
  POST /{client}/batches/{id}/decide {...}  ─▶ STEP 3: human fallback — operator records the decision by hand
EXTERNAL (client, token only — NO auth)
  GET  /approve/{token}                      ─▶ verify (valid | expired | used) ─▶ MASKED batch + prospect list
  POST /approve/{token}/decide {approved_ids[] | removed_ids[] | request_changes}
        ─▶ write prospect_approval decisions, approval_link.used_at, batch.status=approved|changes_requested, decided_at
APPROVED SET ─▶ Phase E reads approved prospect_approval rows; clear-text email routes backend-only into Smartlead
```

### Reuse (what already exists — copy, don't rebuild)
- **Token:** `core/security.py` `new_opaque_token()` + `hash_token()` (the password-reset pattern) — verbatim.
- **Email:** `core/email.py` `send_email(to, subject, body_text)` (SES v2, `no-reply@tryholdslot.com`).
- **Guard:** `require_membership(MembershipRole.owner)` on console mutations; external routes take **no guard** —
  the token is the only credential (return a uniform expired/invalid state; never leak tenant existence).
- **Models/migrations:** `_uuid_pk()`/`_tenant_fk()`/`_created_at()` helpers in `models.py`; `YYYYMMDD_NNNN_*` Alembic files (next: `0016`+).
- **Serializer:** the per-router `_out()` convention (e.g. `icps/router.py`) — the masking `_out` is just an allow-list one.

### Tasks (by dependency; all `[MVP]`)

**D0 — Gate (no code) ✅ DONE 2026-06-25.** ⭐ **SES sandbox-exit + custom MAIL FROM** (Phase A follow-up #1) —
the approval email goes to an **external** client address, so SES had to leave the sandbox. **Cleared:** production
access granted (account `138743894336`, us-east-1 — quota **200 → 50,000/day**, rate **1 → 14/sec**); custom MAIL
FROM **`mail.tryholdslot.com`** registered (MX `10 feedback-smtp.us-east-1.amazonses.com` + SPF TXT live and
resolving; `MailFromDomainStatus` `PENDING → SUCCESS` on SES's async check, `USE_DEFAULT_VALUE` fallback so **no
send breakage** meanwhile). Domain + DKIM were already verified. *(Expiry ladder, template seed, and masking are
all founder-confirmed — see Locked decisions; nothing else is owed.)* **No remaining external gate — D can start at D1.**

**D1 — Schema (Alembic `0016`). ✅ BUILT.** `batch`, `prospect_approval`, `approval_link`, `approval_template` — tenant-scoped,
helpers + indexes per the existing pattern; add the four models to `models.py`; record canonical defs in
[`data-schema.md`](data-schema.md). **DoD:** `0015 → 0016+` head, up/down clean on dev; ORM matches.

**D2 — Batches domain (internal, JWT). ✅ BUILT.** New `domains/batches/` (router + thin service + schemas). `POST
/{client}/batches` (owner) builds a batch + `prospect_approval(pending)` rows from the posted enriched
`prospect_ids`; `GET /{client}/batches` lists with **derived** total/approved counts + status; `GET
/{client}/batches/{id}` returns the company-grouped prospect detail; **`POST /{client}/batches/{id}/decide`**
(owner) is the **STEP-3 human fallback** — the operator records approve/remove decisions by hand when the link
route is exhausted (same `prospect_approval` write path as the external decide). **DoD:** create from selected →
list/detail feed the Sendout Batch tab; counts reconcile from `prospect_approval`; manual decide works.

**D3 — Template + send (the resend ladder). ✅ BUILT.** `GET/PUT /{client}/approval-template` — the override seeded
**verbatim from the existing List-approval *Sendout template*** (subject/body/cta). `POST /{client}/batches/{id}/send`
(owner): mint `approval_link` (7-day expiry), set `status=sent`/`sent_at`, render the template, `send_email()` the
`{{token}}` link. **Resend ladder (built):** each send mints a **fresh 7-day link** — we store only the token *hash*,
so the raw token can't be re-emailed; double-decide is prevented by gating link validity on `batch.status == sent`
(a decided batch makes every link read `used`), not by reusing a token. **DoD:** "Send to client" emails a real link;
the template editor saves; Follow-Up resends without orphaning tokens.

**D4 — External approval (public, tokenized) ⭐. ✅ BUILT.** New `domains/approvals/` (**no auth**). `GET /approve/{token}`
→ verify (valid/expired/used) → the **masked allow-list serializer** (D's security core). `POST
/approve/{token}/decide` → record per-prospect decisions, `used_at` (single-use, no replay), roll up
`batch.status` + `decided_at`. **DoD:** the masked page renders valid/expired/used; approve/remove writes
`prospect_approval`; **no clear-text vector is ever in the response** (asserted by test).

**D5 — Frontend wiring. ✅ BUILT.** Replace the three mocks with live calls (exact classes, no new CSS): *Sendout Batch* tab
(`workspace/batches`) ← D2/D3; external *approve/[token]* (valid/success/expired panes) ← D4; *client-status ·
List approval* (summary chips + template editor + status log) ← D2/D3. Add `lib/api.ts` fns (`listBatches`,
`createBatch`, `sendApproval`, `decideBatch`, `getApprovalTemplate`/`saveApprovalTemplate`, `getApproval`,
`decideApproval`); **drop the `WorkspaceProvider` mock `batches`** (now loaded live + refreshable via
`reloadBatches`) and **re-point the Campaign tab's approved-batch selector at live `listBatches`** (free — it filters
the live batches to `Approved`). Also wired: the Prospect-List **Create batch** button → `createBatch` (infers a
shared ICP); the Sendout-Batch **Send/Follow-Up** button prompts for the client email → `sendApproval`. **DoD:** all
three surfaces live; the external link round-trips; the Campaign selector lists real approved batches. *(Built; the
`?state=expired` demo toggle is kept and OR'd with the live `state` via a new `forceExpired` prop on ExternalShell.)*

**D6 — Acceptance (tick S3). ✅ TESTS BUILT (live round pending).** Pure tests (`tests/test_batches.py`, no DB, in
CI) lock D's security core: the masking serializer emits **zero** clear-text vector (asserted on the serialized
JSON), and `apply_decision` writes the right approve/remove/request-changes outcomes; a DB-gated
`test_batch_end_to_end_create_send_view_decide` drives one real batch (create → send → masked view → decide) against
dev Aurora (skipped without the env). **Founder live round still owed:** enrich a set in C → **Create batch** →
send → open the masked link → remove one + **Approve** → approved rows queryable by E. **DoD:** one real batch
approved end-to-end; `prospect_approval` rows exist as the S7 billing precondition.

**Critical path:** ~~D0(SES)~~ ✅ → ~~D1~~ ✅ → {~~D2~~ · ~~D3~~} ✅ → ~~D4~~ ✅ → ~~D5~~ ✅ → D6 (tests ✅; live round pending).
**D4 was the highest-leverage + highest-risk code** (the masking serializer is the anti-theft control — now
allow-list + test-asserted). **Cost:** **~$0** — no new AWS resources; SES is fractions of a cent per approval email.

> **★ Build outcome 2026-06-25.** Backend: `app/domains/batches` (router·service·schemas) + `app/domains/approvals`
> (router·schemas), config `approval_ttl_seconds = 7d`, Alembic `0016` (+ guard tests), 4 ORM models; `core/email`,
> `core/security` token helpers, and `require_membership` reused **as-is** (no new infra). Frontend: `lib/api.ts`
> +9 fns/types, live `WorkspaceProvider`, and the 3 surfaces. Gates green: **backend 100 pass / 10 skip + ruff
> clean**; **web tsc + eslint + `next build` clean**. **Two deviations from the plan, both simplifications:**
> (1) the resend ladder mints a fresh link per send (hash-only storage ⇒ can't re-emit a raw token; double-decide
> blocked by the `batch.status` gate); (2) on `client-status/approval` the "Send to client" button is a **link to
> the Sendout Batch tab** (where the per-batch send + recipient prompt live) rather than a send in place. **Not yet
> done (deploy-time):** apply `0016` to dev Aurora + redeploy; run the DB-gated e2e + founder smoke on the live env.

> **★ Review hardening 2026-06-30.** A multi-angle review of the Phase D diff produced fixes (no scope
> change, all gates still green — backend 100 pass/10 skip + ruff clean, web tsc + eslint + knip clean,
> 6 external e2e green): **(integrity)** `decide_batch` now 409s on an already-decided batch (re-decide
> could overwrite the client's recorded approve/remove choices). **(tenancy)** `create_batch` validates
> an explicit `icp_id` is the tenant's own and `_icp_name_map` is tenant-scoped (no cross-tenant ICP-name
> leak). **(masking)** `mask_name` strips an "@"-bearing value to its name tokens so an email/handle can't
> leak through the public view. **(links)** `send_approval` now **expires any prior live link** on resend
> (only the latest send works — a mistyped earlier recipient is revoked); the resend ladder note above is
> updated accordingly. **(no-leak)** `view_approval` returns only `{state, expires_at}` for expired/used
> links (no client/batch name). **(race)** `decide_approval` claims the link with an atomic
> `UPDATE … WHERE used_at IS NULL` before writing, closing the double-decide window. **(UI)** a
> `changes_requested` batch no longer renders "Approved &lt;date&gt;"; live batch ages use the real
> current date (the mock `TODAY_ISO` now drives only the reply fixtures via `MOCK_TODAY`); batch
> expand/deep-link/status-log are keyed by **id** not name; the Sendout detail refetches on expand (no
> stale cache); and the approval template's Edit is gated until the saved copy loads. **Cleanup:** dead
> `A_LOG`/`ApprovalRow` mock removed (approval log is live), `TODAY_ISO` un-exported, the stale e2e
> "pages don't call the API" comment + missing `/approve/{token}` mock fixed.

### Cross-phase
- **From C:** reads the enriched `prospect` rows (status `scored`) + their `company` firmographics (for the
  descriptor) + `fit_tier`/`fit_reason`. The central guard scopes every batch; **MVP adds ZERO AWS resources**.
- **To E:** Phase E reads `prospect_approval.decision = approved` rows; clear-text contact data routes
  backend-only into Smartlead (E3's lead-add) — **never** through D's external serializer.
- **S7 billing:** `prospect_approval` is leg (a) of the qualified-meeting rule (approved **AND** held ≥10 min
  **AND** cleared the 48h dispute window — F4 + S7). D writes the approval; F/G close the loop.

### Surfaces covered + cross-page impact (which pages Phase D touches)

**Fully built in Phase D** (mock removed → live API):

| Page | Source | Built by | Coverage |
|---|---|---|---|
| **`/{client}/workspace/batches`** *(Sendout Batch)* | [workspace/batches/page.tsx](../apps/web/app/[client]/(console)/workspace/batches/page.tsx) (`batches` in `WorkspaceProvider`: mock `Batch 1/2/3` + per-company rows + pinned exclusion list) | D2 (list/detail) · D3 (send) · D5 | ✅ **fully covered** |
| **`/{client}/client-status/approval`** *(List approval)* | [client-status/approval/page.tsx](../apps/web/app/[client]/(console)/client-status/approval/page.tsx) (`A_LOG` mock + `tmpl`/`draft` editor; "Send to client" = `toast` only) | D2 (status log/chips) · D3 (template + send) · D5 | ✅ **fully covered** |
| **`/{client}/approve/[token]`** *(external, client-facing)* | [approve/[token]/page.tsx](../apps/web/app/[client]/(external)/approve/[token]/page.tsx) (`removed`/`done` `useState` + `<Sample>` copy; valid/success/expired panes mock) | D4 (masked GET + decide) · D5 | ✅ **fully covered** (the client half — not a console URL, but core to D) |

> ⤷ **Both pages you named are fully covered**, plus the external `approve/[token]` page (D's client-facing half).

**Lightly touched (bounded — not rebuilt):**
- **`/{client}/workspace/campaign`** *(Campaign tab)* — its **"select an approved batch" dropdown** reads the mock
  `batches` from `WorkspaceProvider`. D5 removes that mock, so the selector re-points at the live `listBatches`
  (a read-only GET). **The rest of the Campaign tab stays mock until Phase E.** This is the only ripple from
  dropping the provider's mock `batches`.

**Out of scope / NOT affected by Phase D:**
- **`/{client}/performance-summary`** *(overview)* — **explicitly excluded from Phase D** (founder, 2026-06-25);
  its approval-related counts stay placeholder until a later pass. Phase D is **exactly the three pages above**.
- `workspace/replies` + `workspace/summaries` — read mock `campaigns` (untouched; Phase E).
- `client-status/booking` (Phase F) · `client-status/feedback` ([SKIP]) — the other two client-status tabs.
- external `book/[token]` (Phase F) · `feedback/[token]` ([SKIP]).

**`WorkspaceProvider`:** D5 removes the mock `batches`; keeps `campaigns`/`replies` (still mock until E). The
**only** cross-tab consumer of `batches` is the Campaign batch selector (lightly-touched, above).

**Gating dependency from A:** the **SES sandbox-exit + custom MAIL FROM** (Phase A follow-up #1) — the D0 gate for
the client-facing approval email — is **✅ cleared 2026-06-25** (production access live + `mail.tryholdslot.com`
MAIL FROM configured). D3's client-facing send is unblocked.

---

## Phase E — Outreach + Smartlead (S4/S5): the campaign funnel made real

Turns an **approved batch** (D) into a **live Smartlead cold-email campaign** and makes the rebuilt
**Campaign** tab real — a **7-stage funnel** (*Initial outreach → Follow-up → Positive reply → Meeting
schedule → No show → Qualified billable → Drop/DNC*) where each prospect is a card moving stage→stage,
each sending stage carries **A/B/C variants** with live open/reply metrics + a "leading" winner, and each
prospect carries a **conversation log**. Four KPIs (Prospects · Replies · Meetings · Billable) are funnel
roll-ups. **E lights the first half** (Initial outreach, Follow-up, Positive reply, Drop) + KPI plumbing;
**F lights** Meeting schedule / No show / Qualified billable (one funnel, two phases). **No code until
E0's gates clear — the real gate is warmed inboxes.**

> **★ Posture: lean, webhook-driven, one Smartlead adapter.** Smartlead = the dumb sender; we own funnel
> state. At dogfood volume webhook ingest is **synchronous insert, ZERO new AWS resources** (a signed
> route on the `$default` proxy). **[SCALE]** SQS + worker enter only at volume.

### Funnel ↔ Smartlead mapping

| Stage (`Stage.id`) | Enters when | Smartlead source (verified event names) |
|---|---|---|
| Initial outreach (`contacted`) | batch locked → leads added, sequence started | lead-add response + sequence start (Smartlead has **no `EMAIL_SENT` campaign-webhook** — see risk R3; "sent" is inferred from the lead-add 200 + the sequence schedule, or polled via the message-history endpoint) |
| Follow-up (`followup`) | step ≥2 sent, no reply | derived server-side from elapsed sequence steps (same R3 caveat) |
| Positive reply (`replied`) | reply arrives **and founder classifies positive** | **`LEAD_REPLIED`** → manual move |
| Drop/DNC (`drop`) | negative/unsub reply, bounce, manual drop | `LEAD_REPLIED`(neg) · **`LEAD_UNSUBSCRIBED`** · **`LEAD_BOUNCED`** |
| Meeting / No show / Qualified billable | **Phase F** (entry into `meeting` fires the Google Meet invite — see *Meeting-schedule hook* below) | — |

> **Verified Smartlead campaign-webhook events** (`POST /api/v1/campaigns/{id}/webhooks`, 2026-06-24):
> **`LEAD_REPLIED` · `LEAD_OPENED` · `LEAD_CLICKED` · `LEAD_BOUNCED` · `LEAD_UNSUBSCRIBED`**. There is **no
> per-send (`EMAIL_SENT`) event** in the campaign-webhook set (R3). Open → `LEAD_OPENED` rolls the variant
> open-rate; reply → `LEAD_REPLIED` drives the Reply Queue + drop.

**MVP line: reply classification is human, not LLM.** A reply lands as an `OutreachEvent`, shows in the
prospect's conversation log **and** the **Reply Queue** (cross-campaign triage). Founder reads it and uses
the **stage-move control**. AI drafting/classification stays **[SKIP] until paying signups**; **[SCALE]**
`reply_classify`/`reply_draft` purposes drop into the same queue, no redesign.

**Variant fidelity:** campaign variants map 1:1 to Smartlead **sequence-step** A/B/C variants; per-variant
open/reply syncs back; the per-prospect selector assigns at lead-add time and **locks once sent**. Editing
after send creates the next version (append-only).

### UI → feature → Smartlead API map (the built UI is the spec)

The Campaign tab ([`CampaignTab.tsx`](../apps/web/app/[client]/(console)/workspace/CampaignTab.tsx)), Reply
Queue + Meeting Recaps ([`workspace/page.tsx`](../apps/web/app/[client]/(console)/workspace/page.tsx)) are
already built as fully-interactive **client-side mock**. Phase E replaces the mock state with these live
calls — layout/classes unchanged. **Smartlead auth is `?api_key=…` (query param) on every call; no
OAuth/Bearer** (R1). All paths are V1 (`/api/v1/...`).

| UI affordance (current mock) | HoldSlot endpoint | Smartlead call |
|---|---|---|
| **"Confirm & lock"** (top bar, draft campaign) | `POST /{client}/campaigns` (idempotent on `batch_id`) | `POST /api/v1/campaigns/create` `{name, client_id}` → `POST /api/v1/campaigns/{id}/schedule` `{timezone, days_of_the_week, start_hour, end_hour, min_time_btw_emails, max_leads_per_day}` → `POST /api/v1/campaigns/{id}/settings` |
| **A/B/C variant panel** (per stage: copy + Leading) | folded into campaign create | `POST /api/v1/campaigns/{id}/sequences` — array of `{seq_number, seq_delay_details, variant_distribution_type, variants:[{subject, email_body, variant_label}]}`; HoldSlot `{{token}}` grammar → Smartlead merge tags |
| **Company cards → people → variant select + Send** | leads pushed at lock | `POST /api/v1/campaigns/{id}/leads` `{lead_list:[{email, first_name, last_name, company_name, linkedin_profile, custom_fields}], settings:{ignore duplicates}}` — chosen variant is the lead's sequence assignment |
| **Funnel rail counts** (Prospects/Replies/Meetings/Billable KPIs) | `GET /{client}/campaigns/{id}/funnel` (read over `campaign_lead.stage`) | none — derived from `outreach_event` rows (webhook-fed), not a Smartlead read |
| **Stage-move dropdown** (forward/back/Drop) | `PATCH /{client}/campaign-leads/{id}/stage` | none for back-moves; `replied→meeting` triggers the Meet invite (Phase F); `→drop` may call pause/remove-lead |
| **Send controls** (implicit: start/pause/resume) | `POST /{client}/campaigns/{id}/{start\|pause\|resume}` | `PATCH /api/v1/campaigns/{id}/status` `{status: START\|PAUSED\|STOPPED}` |
| **Conversation Log** (per-person thread: out/in/Email/LinkedIn/Calendar) | read over `outreach_event` | fed by webhooks; LinkedIn/Calendar rows are HoldSlot-authored (Smartlead is email-only) |
| **Reply Queue** (cross-campaign; classify; Edit/Send draft) | `GET /{client}/replies` + `POST /{client}/replies/{id}/send` | inbound = `LEAD_REPLIED` webhook; send = `POST /api/v1/campaigns/{id}/reply-email-thread` `{lead_id, email_body, reply_message_id, reply_email_time}` (**reply-to-thread, master inbox**) |
| **Variant open/reply % + "Leading"** | `GET /{client}/campaigns/{id}/variants` | `LEAD_OPENED`/`LEAD_REPLIED` counts per variant; `is_winner` computed HoldSlot-side |
| **Webhook registration** (per campaign at lock) | internal, on campaign create | `POST /api/v1/campaigns/{id}/webhooks` `{name, webhook_url, event_types:[LEAD_REPLIED, LEAD_OPENED, LEAD_CLICKED, LEAD_BOUNCED, LEAD_UNSUBSCRIBED]}` |

### Meeting-schedule hook + Recaps = future meetings + summaries (NEW requirement, 2026-06-24)

Two requirements that bridge the Campaign funnel into the booking/meeting surface (the E→F seam):

1. **Every move into "Meeting schedule" (`replied → meeting`) provisions a Google Meet invitation.** The
   stage-move is not just a status change — entering `meeting` calls the **Google Calendar API**
   `events.insert` with `conferenceDataVersion=1` + `conferenceData.createRequest{conferenceSolutionKey:
   "hangoutsMeet"}` to mint a Meet link, sets `attendees[]` (prospect + host), and `sendUpdates=all` to email
   the invite. The returned `hangoutLink`/`conferenceData` + `google_event_id` persist on the `meeting` row
   (Phase F `F2`/`F3`). *(Built in F; the funnel's stage-move control is the trigger — wire the hook in F3 so
   the Campaign tab's "Move → Meeting schedule" is the single entry point.)* The conversation Log already
   renders a `Calendar` channel row for this.
2. **The "Meeting Recaps" tab shows BOTH future meetings AND past summaries** (today it renders past
   summaries only — `RECAPS`). Reshape the tab into two groups:
   - **Upcoming meetings** — scheduled, not-yet-held `meeting` rows: prospect, company, `scheduled_at`, the
     **Meet link** (join), attendees, stage = *Meeting schedule*. Source: `meeting` rows where
     `held IS NULL AND scheduled_at >= now`.
   - **Meeting summaries** (existing) — held meetings: recording link, attendees, discussed, next step,
     sentiment, final conversion (Deal won / No deal). Source: `held = true` rows; the LLM `meeting_summary`
     stays **[SKIP→later]** (placeholder copy until paying signups), but the **future-meeting list, Meet
     link, attendees, and held/duration are real** from Calendar + Meet REST v2.
   - **New read:** `GET /{client}/meetings?when=upcoming|past`. Held/duration/attendees for the past group
     come from **Meet REST v2** `conferenceRecords` + `conferenceRecords.participants` (duration derived from
     the record's start/end + participant sessions) — the same source `F4` uses to qualify.

### Integration risks (flag before E build)

- **R1 · Smartlead auth is query-param `api_key` only** — no OAuth/Bearer. The key rides in the URL on every
  call → keep it out of logs/CloudWatch (the request-path logger must redact `api_key`), and it can't be
  scoped per-campaign. Lazy-load from `holdslot/prod/smartlead`, never interpolate into a logged URL.
- **R2 · Webhook authenticity is not a documented HMAC signature.** Smartlead's campaign-webhook docs expose
  `webhook_url` + `event_types` but **no signing-secret/signature scheme** was found. The plan's
  `webhook_signing_secret` assumption (E0) may not exist. **Mitigation:** treat the webhook as
  unauthenticated and defend with (a) a **high-entropy secret path token** (`/smartlead/webhook/{random}`),
  (b) optional Smartlead source-IP allowlist, (c) **idempotency + re-validation** — on any event, re-fetch the
  lead/campaign state from Smartlead before mutating, so a spoofed payload can't move a stage. Confirm the
  real mechanism with Smartlead support at E0; do **not** assume HMAC.
- **R3 · No `EMAIL_SENT` campaign-webhook event.** The verified event set is `LEAD_REPLIED/OPENED/CLICKED/
  BOUNCED/UNSUBSCRIBED` only. "Sent" and per-step follow-up progress can't be driven by a send-webhook →
  **derive `contacted`/`followup` server-side** from the lead-add 200 + the sequence schedule (elapsed
  steps), or poll the message-history endpoint. The funnel's Initial-outreach/Follow-up counts are
  HoldSlot-computed, not Smartlead-pushed.
- **R4 · Reply-to-thread needs `reply_message_id`.** `reply-email-thread` requires the original message id to
  thread correctly; that id must be captured from the inbound `LEAD_REPLIED` payload (or message history) and
  stored on the `outreach_event`, or the booking reply starts a new thread (hurts deliverability + breaks the
  master-inbox conversation).
- **R5 · A/B variant fidelity is sequence-step-scoped, not stage-scoped.** Smartlead variants live on a
  **sequence step**, but the UI shows variants **per funnel stage** (outreach, follow-up, booking, re-book,
  drop). Only the *sending* stages (contacted/followup) map cleanly to Smartlead steps; the booking/re-book/
  drop messages are **manual threaded replies** (`reply-email-thread`), not sequence steps — their "variants"
  + open/reply metrics are HoldSlot-tracked, not Smartlead-synced. Don't promise Smartlead A/B stats on the
  reply-driven stages.
- **R6 · LinkedIn / Calendar / Stripe log rows are not Smartlead.** The conversation Log renders Email +
  LinkedIn + Calendar + Stripe channels; **only Email is Smartlead-fed.** LinkedIn is out of scope at MVP
  (the mock shows it — don't wire it), Calendar comes from Phase F (Google), Stripe from G. Scope the live
  Log to Email + Calendar; leave LinkedIn as a [SKIP] visual.
- **R7 · Daily send caps vs warm-up ramp.** Start respects the 15/day campaign cap + the warm-up ramp
  (5–10→25/inbox/day). Pushing all leads at lock then `START` is fine (Smartlead throttles), but the funnel's
  "Prospects ready" count ≠ "sent today" — surface the schedule, don't imply instant send.

### Tasks (`[MVP]` now; `[SCALE]` at volume)

**E0 — Gates (no code).** (1) **[MVP] Warmed inboxes ready ⭐** — `getholdslot.com` warm-up started
2026-06-17 → real sends ~early Jul'26; build E1–E3 against the clock. (2) Smartlead secret complete
(`webhook_signing_secret` + `sending_account_ids`) → `verify_keys --strict smartlead`. (3) Cold-email A/B/C
copy + sequence authored (token grammar matches the UI). (4) Compliance confirmed (unsubscribe +
suppression owner + CAN-SPAM/GDPR/HK-PDPO).

**E1 — [MVP] Schema** (tenant-scoped). `campaign` (batch_id, `smartlead_campaign_id`, status) ·
`message_variant` (stage, A/B/C, body, `smartlead_variant_id`, version, open/reply counts, `is_winner`) ·
`campaign_lead` (prospect_id, `smartlead_lead_id`, **`stage`** = funnel single source of truth, variant) ·
`outreach_event` (type, channel, payload JSONB, occurred_at — conversation-log source + stage driver).
**DoD:** funnel stage + event log reconstruct from rows; re-delivered webhook is idempotent (dedupe on Smartlead event id).

**E2 — [MVP] Smartlead adapter ⭐** (lazy/SnapStart-safe, mirrors B3 discipline): create campaign · add
leads · set A/B/C sequence · start/pause/resume · **reply-to-thread** (master inbox) · register webhook.

**E3 — [MVP] Confirm & lock → campaign ⭐.** UI "Confirm & lock" → `POST /clients/{c}/campaigns`
(idempotent on batch_id) → create Smartlead campaign → add leads (chosen variant) → push A/B/C sequence →
start (respecting daily caps). Leads land in Initial outreach (`stage=contacted`). Pause/resume proxy to E2.

**E4 — [MVP] Webhook ingest → events → stages ⭐.** `POST /smartlead/webhook/{secret-path-token}` (R2: no
documented HMAC — defend with the high-entropy path token + re-fetch-before-mutate; **confirm the real
mechanism at E0**), fast 2xx, idempotent on Smartlead event id → write `outreach_event` → advance stage:
`LEAD_OPENED` → variant open count; `LEAD_REPLIED` → log + flag for review (no auto-classify);
`LEAD_UNSUBSCRIBED`/`LEAD_BOUNCED`/negative reply → drop. **No `EMAIL_SENT` event (R3)** → `contacted`/
`followup` are **derived server-side** from the lead-add + sequence schedule, not webhook-driven. Capture the
inbound `reply_message_id` for E6 threading (R4). Founder moves positives to `replied`. **[SCALE]**
API-GW→SQS→worker + `reply_classify`/`reply_draft` suggestions.

**E5 — [MVP] Reply Queue — cross-campaign triage inbox ⭐.** Aggregates **every replied conversation
across all the tenant's campaigns** into one inbox (a read over E1's `outreach_event` + `campaign_lead`, no
new schema). Each row: prospect, campaign + stage, latest snippet, full thread on expand. **Filters:** by
campaign, by triage state (Needs review / Positive / Negative / Handled), reply-status pips. Triage: read →
classify → move lead to Positive reply or Drop → approve/edit/send the threaded reply (E6). **[SCALE]**
`reply_classify` pre-sorts; `reply_draft` pre-fills.

**E6 — [MVP] Reply-to-thread + variant scoreboard.** From Positive reply, send the booking message back
**into the thread** via E2; roll open/reply per variant into the metric bars; compute `is_winner` ("Leading").

**E7 — [MVP] Wire Campaign tab + Reply Queue + acceptance.** Live campaigns, funnel stages + counts,
per-stage variants (live metrics), conversation log + stage-move, KPIs (Prospects=contacted ·
Replies=replied · Meetings/Billable=F), cross-campaign Reply Queue — exact class names, no new CSS. Replace
the mocks (`SAMPLE_FUNNEL`, `INITIAL_REPLIES`, `RECAPS`); "Confirm & lock" calls E3. The `replied → meeting`
stage-move calls the Phase F Meet-invite hook (F3). **DoD:** founder locks a batch, watches real sends,
triages a reply from the Reply Queue, advances to Positive reply, sends a threaded booking message — all
live; tick **S4/S5**.

**Critical path:** E0(inboxes) → E1 → E2 → E3 → E4 → {E5 · E6} → E7. **E0 is the schedule risk** (warm-up,
running); **E3/E4 is the highest-leverage code**; **E5 is where the founder works the replies.** **Cost:**
Smartlead Basic $32/mo covers the whole MVP; LLM stays out of E at MVP.

---

## Phase F — Book + meeting (S6 min): the billable seam into Ledger + Recaps

Lights the **bottom half of the same funnel** (*Meeting schedule → No show → Qualified billable*) by
making booking + the meeting real (Calendar event + Meet link + invites; held + duration via **Meet REST
v2**), and wires the two terminal stages to the *Billing ledger* + *Meeting recaps* tabs. **Locked billing
rule (the hinge):** a meeting is **Qualified billable iff (a) the prospect has a client approval AND (b)
Meet metadata shows held ≥ 10 minutes** — else **No show**. **No code until F0's gates clear.**

> **★ Posture: build the meeting connection + the data seam; defer Stripe + LLM recaps.** Per *Build vs.
> skip*, billing/Stripe and transcript summaries are **[SKIP] until paying signups.** F builds the
> `meeting` record both future tabs read, and renders the Ledger + Recaps tabs from real meeting data — but
> the ledger's **Stripe push** and the recap's **LLM summary** are explicit **[SKIP→later]** seams. The
> "$X · Stripe" chip is a **computed amount**, not a real charge, until G onboards a payer.

### The seam: one `meeting` row feeds three surfaces

| Consumer | Reads | Built in F? |
|---|---|---|
| Campaign funnel (Meeting / No show / Qualified billable) | `scheduled_at`, `held`, `duration_min`, `qualified` → `campaign_lead.stage` | YES |
| Billing ledger tab | `qualified`, `amount`, `held`, `duration_min`, `conference_record_id` (→ UI `recId`), won/lost | rows YES · Stripe push [SKIP→later] |
| Meeting recaps tab (**upcoming** + past) | upcoming: `scheduled_at`, `meet_link`, attendees · past: `conference_record_id`, attendees, transcript ref | **upcoming list + Meet link YES** · LLM summary [SKIP→later] |

### Tasks

**F0 — Gates (no code).** (1) Google Workspace host seat(s) + Meet REST conference-records scope — verified
in `holdslot/prod/google` (Business Starter exposes the held-≥10-min read; recording/transcripts need
Standard, only for the [SKIP] recap engine). (2) Booking-link lifetime/expiry + reminder cadence (drives
EventBridge). (3) Qualified-meeting definition reconfirmed = approved AND held ≥10 min (F4 encodes verbatim).

**F1 — Schema** (tenant-scoped). `booking_link` (token, `expires_at`, status valid/booked/expired) ·
`meeting` (campaign_id, prospect_id, `google_event_id`, `meet_link`, `scheduled_at`, `held`,
`duration_min`, `attendee_count`, **`conference_record_id`**, **`qualified`**, **`amount`**, `outcome`
won/lost/null, status). **DoD:** a `meeting` resolves to its lead + campaign + future ledger/recap fields
with no further schema change.

**F2 — Google adapter extension** (reuse the existing client): create Calendar event + Meet link + invites;
read Meet REST v2 conference records for held/duration/attendees. SnapStart-safe.

**F3 — Booking link → event → Meeting schedule.** The tokenized external booking page exists; on confirm →
F2 creates the event → lead → `stage=meeting`. EventBridge schedules a pre-meeting reminder + the
post-meeting poll (F4). **The Campaign tab's stage-move into "Meeting schedule" is the same trigger** (see
Phase E → *Meeting-schedule hook*): moving `replied → meeting` calls Calendar `events.insert`
(`conferenceDataVersion=1`, `conferenceData.createRequest{hangoutsMeet}`, `attendees[]`, `sendUpdates=all`) →
mints the **Google Meet** link + invite, persists `google_event_id`/`hangoutLink` on the `meeting` row. Wire
this hook once here so both the external booking page **and** the funnel stage-move are one code path.

**F4 — Held + duration → qualify (the billing trigger) ⭐.** EventBridge poll reads the conference record →
set held/duration/attendees → apply the rule: **approved AND duration ≥10 → `qualified=true`,
`stage=billable`** + compute `amount` (§7); else → `stage=noshow`. Idempotent on re-poll.

**F5 — Ledger + Recaps seam (rows now, engines later).** Read endpoints serve `meeting`-derived rows to the
Billing ledger (qualified/no-show, held/duration, `recId`, amount, won/lost) and Meeting recaps. **The
Recaps tab renders TWO groups** (NEW — see Phase E → *Meeting-schedule hook*): **Upcoming meetings**
(`held IS NULL AND scheduled_at >= now` → prospect, company, `scheduled_at`, Meet **join** link, attendees)
+ **Meeting summaries** (`held = true` → recording, attendees, discussed, next step, sentiment, won/lost).
Read: `GET /{client}/meetings?when=upcoming|past`. **[SKIP→later]:** Stripe invoice push + LLM
`meeting_summary` (placeholder summary copy); the **future-meeting list, Meet link, attendees, held/duration
are real** (Calendar + Meet REST v2 `conferenceRecords`). **DoD:** Recaps shows upcoming + past; won/lost
persists; no Stripe/LLM call.

**F6 — Wire Workspace + acceptance.** Drive Meeting/No show/Qualified billable stages + Meetings/Billable
KPIs from real `meeting` rows; external booking, Ledger, Recaps tabs on live data. **DoD:** a founder
watches a positive-reply lead self-book → attend → auto-qualify into Qualified billable, reflected in KPIs,
Ledger, Recaps — no Stripe/LLM; tick **S6** (+ read-only **S7**).

**Critical path:** F0 → F1 → F2 → F3 → F4 → F5 → F6. **F4 is the highest-leverage code** (the one billing
rule the model rests on). **Cost:** Google Workspace ~$15/mo; $0 Stripe until G.

---

## Production isolation (post-build — run AFTER A→G complete)

**Decision (2026-06-17):** build the whole loop on `dev` first; stand up isolated `prod` only once it's
proven end-to-end. A **cutover, not a rewrite** — Terraform is already workspace-parameterised.

**Trigger:** Phase G DoD met. **Rollout (one ordered pass):**
1. `terraform workspace new prod` → `apply` (separate Aurora/Lambda/`live` alias/HTTP API/domain/budget,
   isolated by `name_prefix`).
2. Set **`aurora_min_acu ≥ 0.5` on prod** (no scale-to-zero); `dev` stays at 0.
3. Fresh prod values for `jwt_signing_key`/`jwt_refresh_key`; external keys shared or split. Founder writes
   all secrets. Pick the prod path namespace deliberately (dev currently reads `holdslot/prod/*`).
4. `alembic upgrade head` + seed on prod. Default to **clean prod** (dev becomes staging) unless real
   signup data must carry over.
5. Exit the SES sandbox for prod (client-facing mail — the Phase-A follow-up #1 deferral).
6. Point Amplify `main`'s `NEXT_PUBLIC_API_BASE_URL` at prod; verify CORS lists the prod origin.
7. Harden: S3 state public-access-block (#5); add CI/CD (#3).

**DoD:** prod fully isolated (separate DB/Lambda/secrets); `main`/`tryholdslot.com` serves prod; `dev`
remains staging; prod Aurora doesn't scale to zero.

---

## Post-MVP — LLM usage consolidation & cost monitoring (run AFTER A→G complete)

**Why this is deferred:** every LLM call already writes one append-only `llm_call` row (tenant ·
`purpose` · `model` · `prompt_version` · in/out tokens · `cost_usd` · latency · `status`) through the
single B3 adapter, so Phases B–F inherit per-call telemetry from day one. The MVP's cost control is the
provider-side $50 cap + ad-hoc `SELECT sum(cost_usd)` — enough to run the dogfood loop. Consolidation
is the **monitoring layer on top**, valuable only once there are calls across every phase to roll up.

**Task — consolidate all LLM token usage across all phases for monitoring.** Aggregate `llm_call`
across **every phase and `purpose`** (`brief→spec` (B), `prospect_fit` / `sourcing_round` /
`candidate_validate` (C), and the later `reply_classify` / `reply_draft` (E) / `meeting_summary` (F))
into a rollup keyed by **tenant × purpose × model × month**: token totals, `cost_usd`, call counts,
parse/timeout/error rates, p50/p95 latency. Surface it as a read-only console panel (existing classes,
no new CSS) + a CloudWatch alarm when monthly spend or error rate crosses a threshold.
- **`llm_call` stays the single source of truth**; the rollup is **derived** (a SQL view or a
  scheduled-refresh table) — define its shape in [`data-schema.md`](data-schema.md) before building.
- **DoD:** one query/panel shows month-to-date token + $ spend per purpose across every phase, and an
  alarm fires before the OpenRouter spend cap is hit.

---

## Materials to prepare

### Accounts & keys — provisioned + verified 2026-06-10

All keys in **AWS Secrets Manager** (`138743894336`), one JSON secret per platform under `holdslot/prod/*`;
non-secret config in SSM. `claude_code` IAM user has read-only `GetSecretValue` on `holdslot/prod/*`.
Verified by [`apps/api/scripts/verify_keys.py`](../apps/api/scripts/verify_keys.py) (phase-aware: later-phase
fields show `PEND`, not `FAIL`; use `--strict` at the phase that needs them).

| Secret | Status | Verifier confirms |
|---|---|---|
| `holdslot/prod/app` | ✅ | JWT signing+refresh present, ≥32 chars, distinct |
| `holdslot/prod/openrouter` | ✅ | Key valid; $50 spend cap. **`models` must be non-US providers** — gemini/gpt are geo-blocked (403 ToS) for HK. The secret `models` is only the default fallback now: each call site pins its own list in code — **scoping** = `SCOPING_MODELS` (`deepseek/deepseek-v4-pro`, async path), **fit** = `FIT_MODELS` (`deepseek/deepseek-v4-pro`, reasoning `medium`, background-scored); Qwen/Llama dropped 2026-06-23 |
| `holdslot/prod/apollo` | ◑ | `key` stored but **free-tier** (Search/Match 403) — upgrade to Professional + master key → C0. |
| `holdslot/prod/smartlead` | ◑ | `api_key` valid; sending accounts + `webhook_signing_secret` → E |
| `holdslot/prod/google` | ✅ | SA + domain-wide delegation + Calendar + Meet REST all 200, one seat (`info@tryholdslot.com`) |

**Remaining secret fields (added at their phase):** Apollo — upgrade to Professional + master key (C0) ·
Smartlead — `webhook_signing_secret` + `sending_account_ids` (E) · Google — optional re-wrap of the SA JSON.

**Account/plan decisions still open:** OpenRouter HK model access (B0 — the one true gate, done) · Apollo
plan tier (C0 — Professional + master key) · Smartlead plan tier (E) · Workspace seat count + Meet recording tier (F) · AWS budget
alarm (set). *(Stripe — not this phase.)* DNS access — **have it** (`tryholdslot.com` in Route 53; SES
DKIM+DMARC published 2026-06-11).

### Sending infrastructure — warm-up STARTED 2026-06-17 (the long pole; gates E)

**Decision:** Smartlead-native warm-up + Google Workspace mailboxes on a **dedicated lookalike domain**.
Cold mail goes **only** from `getholdslot.com`, never `tryholdslot.com` (the clean transactional domain).
Smartlead bundles unlimited warm-up at $0/inbox (saves ~$120/mo vs standalone tools).

**As built (domain #1, live):**
- **Domain:** `getholdslot.com` (Route 53 `Z03649691ONFGOKEILOAK`), secondary domain on the existing single
  Workspace org.
- **Mailboxes (2):** `jason.tse@`, `jason.wong@getholdslot.com`.
- **DNS (all verified):** MX `1 smtp.google.com` · SPF `v=spf1 include:_spf.google.com ~all` · DKIM
  `google._domainkey` (single TXT, two concatenated strings — fixed via UPSERT; Google = active) · DMARC
  `_dmarc` `v=DMARC1; p=none; rua=mailto:dmarc@tryholdslot.com`.
- **Smartlead warm-up (both, Enabled):** 40/day ceiling · rampup +5/day · randomise 3–40 · reply 30% ·
  weekdays-only · campaign daily limit 15.
- **Clock:** started 2026-06-17 → first real cold sends ~week 3 (early Jul'26) at 5–10/inbox/day → scale
  toward ~25/inbox/day.
- **Cost:** ~$15/mo (2 Google seats ~$14 + domain ~$1); Smartlead sub paid for sending anyway.

**MVP scope: ONE domain only.** A 2nd lookalike domain is **[SCALE]** (capacity/redundancy when volume
justifies it). `claude_code` has Route 53 write → a 2nd domain's records can be scripted in one pass.

**Still to do (non-blocking):** do-not-email suppression list (→ C2/C4) · cold-email A/B/C copy (before
week-3 sends) · Smartlead secret capture (before E).

### Content & assets (our own GTM)
HoldSlot's own **ICP** (→ Brief→spec) · **cold-email copy** (A/B/C + sequence) · **sales pitch/demo** (the
live product is the demo) + booking availability + landing CTA → booking flow.

### Decisions needed before the relevant phase
Auth/access — **resolved** (2 founder owners; multi-tenant schema; clients on tokenized links) ·
**Fit-scoring rubric** — done (blocks C) · **cold-outreach compliance** + unsubscribe + suppression owner
(gates E) · booking-link lifetime/expiry (F) · AWS region/residency (A — us-east-1).

## MVP running cost (actual plan prices, 2026-06-17)

Scoped to what the dogfood MVP runs: single tenant, one domain, 2 inboxes, low volume. (The 10-tenant
model in `backend-development-plan.md` Tables 2/4 remains authoritative for Growth.)

| Item | Plan | $/mo |
|---|---|---|
| **Apollo** | Professional (master key; confirm live price) | ~99.00 |
| **Smartlead** | Basic (warm-up free, both inboxes fit) | 32.00 |
| **Google Workspace** | 2 × Business Starter @ $7.20 | 14.40 |
| **OpenRouter** | pay-per-use (Brief→spec, fit, drafts) | ~5–30 |
| **`getholdslot.com`** | ~$15/yr amortized | ~1.25 |
| **Aurora Serverless v2** | min ACU (near-$0 idle, ~0.5 ACU under use) | ~5–30 |
| Lambda · API GW · SES · S3 · SSM · SQS · EventBridge · CloudWatch · R53 · Amplify | | ~3–10 |

**Total: ~$195/mo typical** (low ~$160, high ~$235) · ≈ 1,520 HKD/mo at 7.8.

**Cost levers:**
- **Apollo (~50% of total) is the lever.** **People search is 0 credits; company search consumes plan
  credits** (Apollo's current docs — confirm the per-call cost + included monthly credits at C0), and the
  heavy spend is **enrich credits** at `people/match` (1 credit/email, per person enriched, not per
  meeting), spent only on the human-selected set. Cap company search with `max_results` and reuse cached
  rows to contain search-credit burn. **Phone is 8× email + async webhook — off by default
  (`PHONE_ENABLED=false`).**
- **Smartlead $32 covers the whole MVP**; **Workspace Starter ($7.20) suffices** (bump to Standard only for
  native Meet recording); **Stripe = $0** until a signup pays (G).
- **Honest floor before Apollo Professional** (warm-up phase, no live sourcing yet): Smartlead $32 +
  Workspace ~$15 + AWS/LLM/domain ~$10 ≈ **$55–65/mo.** Once dogfood sourcing starts (Apollo on): **~$195/mo.**

---

## Appendix — API surface (47 endpoints, as built · Lambda v46)

> The live FastAPI inventory (was `modularization-plan.md` PART 2; folded here 2026-06-25). Auth = JWT Bearer
> (`HTTPBearer`); tenant scope via `require_membership()` on every `/{client}/…` route (non-members → **404**,
> not 403). `+Owner` = owner-role-gated. Swagger at `/docs`, ReDoc at `/redoc`. CORS via `HOLDSLOT_CORS_ORIGINS`.
> **Routers:** `auth`, `clients`, `briefs`, `icps`, `prospects` (largest, ~29 routes) in
> `apps/api/app/domains/<x>/router.py`. **FE coverage:** the API serves only the workspace **Brief + List**
> tabs today — batches/campaign/replies/summaries/billing + all of client-status are still mock (where the
> backend grows next: Phases D–F).

| Feature | Method | Path | Purpose | Auth |
|---|---|---|---|---|
| Health | GET | `/health` | Liveness | Public |
| Auth | POST | `/auth/login` | Email/pw → access+refresh | Public |
| Auth | POST | `/auth/refresh` | Rotate access token | Public |
| Auth | POST | `/auth/forgot` | Begin pw reset (202) | Public |
| Auth | POST | `/auth/reset` | Complete pw reset | Public |
| Clients | GET | `/me` | Current user + memberships | JWT |
| Clients | GET | `/clients` | Tenants user belongs to | JWT |
| Clients | POST | `/clients` | Create tenant (→ owner) | JWT |
| Clients | GET | `/{client}/context` | Resolve + authorize tenant | +Member |
| Brief | GET | `/{client}/brief` | Get brief | +Member |
| Brief | PUT | `/{client}/brief` | Upsert brief | +Member |
| Brief | GET | `/{client}/brief/structure/preview` | Preview structuring prompt (free) | +Member |
| Brief | PUT | `/{client}/brief/structure/system-prompt` | Edit scoping prompt | +Member |
| Brief | POST | `/{client}/brief/structure` | Kick async structuring (LLM) | +Member |
| Brief | GET | `/{client}/brief/structure/status` | Poll structuring job | +Member |
| Brief | GET | `/{client}/research-spec` | Latest ResearchSpec + history | +Member |
| ICP | GET | `/{client}/icps` | List ICPs | +Member |
| ICP | POST | `/{client}/icps` | Create ICP | +Member |
| ICP | PUT | `/{client}/icps/{icp_id}` | Update ICP | +Member |
| ICP | DELETE | `/{client}/icps/{icp_id}` | Delete ICP | +Member |
| List (read) | GET | `/{client}/prospects` | People, sorted by fit (cursor, ≤250) | +Member |
| List (read) | GET | `/{client}/companies` | Companies (Stage 1), by fit (cursor, ≤250) | +Member |
| Companies | POST | `/{client}/companies` | Manually add one | +Owner |
| Companies | POST | `/{client}/companies/find-company` | Flow A: Apollo search→suppress→enrich→score | +Owner |
| Companies | POST | `/{client}/companies/find-lookalikes` | Lookalike peers (≤10 net-new) | +Owner |
| Companies | PATCH | `/{client}/companies/select` | Stage into Step 2 / remove | +Owner |
| Companies | POST | `/{client}/companies/rescore` | Re-run fit (≤15/req) | +Owner |
| Companies | POST | `/{client}/companies/update-fields` | Re-enrich firmographics (≤15/req) | +Owner |
| Companies | GET | `/{client}/fit-prompt` | Preview fit rubric prompt (free) | +Member |
| People | POST | `/{client}/people/find-people` | Flow B: people across orgs (free, ≤250) | +Owner |
| People | POST | `/{client}/people/facets` | Live seniority/dept counts (free) | +Owner |
| People | GET | `/{client}/people/scope-override` | Get saved Find Settings | +Member |
| People | PUT | `/{client}/people/scope-override` | Save Find Settings | +Owner |
| People | DELETE | `/{client}/people/scope-override` | Reset Find Settings | +Owner |
| People | GET | `/{client}/people/departments` | 14 master departments (static) | +Member |
| Prospects | POST | `/{client}/prospects` | Manually add one person | +Owner |
| Prospects | POST | `/{client}/prospects/rescore` | AI score people (≤15/req) | +Owner |
| Prospects | POST | `/{client}/prospects/enrich` | **Only credit spend**: Apollo people/match (≤15/req) | +Owner |
| Scoring (W4) | POST | `/{client}/companies/find-company-async` | Async kick-off → 202 + job | +Owner |
| Scoring (W4) | POST | `/{client}/companies/find-lookalikes-async` | Async kick-off → 202 + job | +Owner |
| Scoring (W4) | POST | `/{client}/companies/rescore-async` | Async kick-off → 202 + job (≤20) | +Owner |
| Scoring (W4) | POST | `/{client}/companies/update-fields-async` | Async kick-off → 202 + job (≤20) | +Owner |
| Scoring (W4) | POST | `/{client}/prospects/rescore-async` | Async kick-off → 202 + job (≤20) | +Owner |
| Scoring (W4) | GET | `/{client}/scoring-jobs/{job_id}` | Poll an async scoring job | +Member |
| Research | GET | `/{client}/research-runs` | Cost/credit scoreboard | +Member |
| Research | GET | `/{client}/sourcing-docs` | Get rubrics (company_fit + prospect_fit) | +Member |
| Research | POST | `/{client}/sourcing-docs` | Save rubric edit (append-only) | +Owner |

**W4 added 6 async-scoring endpoints** (5 kick-offs → 202 + 1 poll); the matching **sync** endpoints are kept
for back-compat but are no longer called by the web app.
