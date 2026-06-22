# HoldSlot — Initial Build Plan (dogfood MVP)

> **Status (2026-06-22):** Phases **A (S0)** + **B (S1)** **built, reviewed & live on `dev`** — backend on
> the `dev` API (alias `live`, **Lambda v21**), Workspace web on Amplify `dev`. **B6 is now built &
> deployed**: async **ResearchSpec v3** (Apollo-native — the LLM emits exact Apollo request fields;
> `SPEC_VERSION=3`, `PROMPT_VERSION="brief-structure-v5"`), the `research_job` async-structuring tracker
> (migration `0009`), and the `sourcing_doc`→`prompt` table rename + `stage` column (migration `0010`,
> seeds `briefing` v1). 37 backend tests green; ruff/tsc clean. Last *committed*: `023be68` on
> `origin/dev`; the B6/v3 work is deployed to dev but **uncommitted** (this commit lands it). **Phase C
> (S2) is being rebuilt Apollo-only.** The Clay-based Phase C (seed push → CSV
> ingest + fit scoring → AI sourcing loop) was built and ran on `dev`, but **Clay has no programmatic Find
> Company / Find People API on any tier** — discovery stayed operator-run in Clay's UI with a CSV bridge.
> **Apollo.io is a headless REST search + enrichment API** (company search, people search, `people/match`,
> static key), so Phase C moves to **Apollo only**: Apollo does discovery *and* enrichment; the LLM only
> scores rows (the Brief→targeting LLM already ran in B; the B→C param mapping is **deterministic**, no
> second LLM). No Clay, no webhooks, no CSV. See **Phase C** for the rebuild plan; schema deltas in
> [`data-schema.md`](data-schema.md). **The Apollo find/enrich loop is the one gate left to tick S2.**

> ## ▶ NEXT SESSION — START HERE
> **Phase C (Apollo find→enrich loop) is a LIVE FUNCTIONAL MVP (2026-06-22).** C0–C6 built; deployed and
> proven end-to-end on the cloud stack. The four operational steps are done:
> - ✅ **(1) Migration `0011` applied to dev Aurora** (DB at `0011 (head)`; `apollo_org_id`/`apollo_person_id`
>   present, `seed_limit` dropped). **All 59 tests pass on Aurora** — the 9 previously-skipped DB-gated tests
>   now run green (`test_migrations`, `test_prospects_apollo` full find→select→find→enrich, real-LLM briefs).
> - ✅ **(2) Lambda deployed** — `holdslot-dev-api` **version 23**, `live` alias shifted, `/health` 200.
>   v23 adds the 10 code-review fixes (credit-safety: per-row commit, idempotent enrich, `enrich_failed`;
>   sync-budget caps) **and** the B→C linkage fixes (GAP 0 ICP-docs→fit context, GAP 1 `avoidTitles` drop).
>   **All Phase C is committed to `dev` (`db1749c`)** — git, disk, and the live Lambda now agree.
> - ⚠️ **(3) Credit cost — determined as far as the API allows; one founder dashboard glance still wanted.**
>   Apollo exposes **no credit-balance endpoint** (only `auth/health`); search responses carry only
>   request-rate headers (50k/day), no credit field, and withhold firmographics — all consistent with
>   **company search being request-metered, not credit-metered**. **Enrich = 1 credit/email is empirically
>   confirmed** (the live smoke spent exactly 1). *Founder: glance at Apollo → Settings → Usage/Credits before
>   vs. after a find run to confirm the monthly pool is untouched by search → lock into MVP running cost.*
> - ✅ **(4) Live 1-row end-to-end smoke PASSED** on the deployed stack (ephemeral tenant, torn down):
>   find-company (8 found, scored) → select → find-people (3 real people, `company_id` linked from the loop)
>   → enrich (`people/match`, **1 credit**, returned a verified email `manmeet.saluja@saaslabs.co`,
>   `email_valid=true`, status→`scored`). The full loop works on Lambda v22 + live Apollo + live LLM + Aurora.
>
> **Next:** the loop is ready to run for real outreach (Phase E warm-up is the gating long pole). Optionally
> revisit the *⚠️ Post-C review* deferred ICP inputs (`avoidTitles` first) now that the MVP is proven.
>
> **Built this session (all green: backend 50 pure tests + ruff, web tsc + build; 9 DB-gated tests pending
> Aurora):**
> - **C1 — migration `0011`** + models: `company.apollo_org_id` (unique/tenant), `prospect.apollo_person_id`,
>   `DROP tenant.seed_limit`. Single alembic head; `test_migrations` guards it. *(up/down on Aurora pending.)*
> - **C2 — `integrations/apollo/client.py`** (lazy `X-Api-Key`, 429 backoff, pagination, the 3 endpoints) +
>   pure **`domains/prospects/apollo_map.py`** (request builders + parsers). Parsers tested against the live
>   C0 fixtures; request builders **live-verified 200** (company w/ revenue+funding+hiring, people scoped).
> - **C3** — folded in: the post-filter is the existing `suppression` (exclusion + existing-customer-domain
>   drop) + per-row `fit.score`/`score_company`; **no new module** (simplest path, reuses tested code).
> - **C4 — Flow A** `POST /{client}/companies/find-company` + `PATCH …/companies/select` (map→search→
>   suppress→upsert on `apollo_org_id`→score→`research_run`).
> - **C5 — Flow B** `POST /{client}/people/find-people` (**loops one `organization_ids` per selected org** —
>   C0: search rows have no org id, so `company_id` comes from the loop) + reworked `POST …/prospects/enrich`
>   (real `people/match`, the only credit spend, writes email/last-name/linkedin/departments, → `scored`).
> - **C6 — frontend**: the two "Find Companies / Find People" stub buttons are now **live** (`findCompanies`,
>   `selectCompanies`, `findPeople`, reworked `enrichProspects` in `lib/api.ts`); enrich toast shows credits.
> - **B6 — `ResearchSpec` v3 (done earlier)** is the B→C contract that all of the above consumes.
>
> **Coverage note:** the B6→C study confirmed the fit+intent+exclusion spine forwards end-to-end; four ICP
> inputs (`avoidTitles`, `departments`, `technologies`, `revenue_range`) are collected but not yet wired —
> **deliberately deferred**, see *⚠️ Post-C review* at the end of Phase C.
>
> **⚠️ Context you MUST carry (non-obvious; the rest of the doc has the detail):**
> - **OpenRouter HK geo-block.** OpenAI / Anthropic / Google providers return **403 ToS** for this account
>   (Hong Kong) — account-wide, not content-driven. **Route every LLM call to non-US providers only**
>   (DeepSeek / Qwen / Mistral — Llama dropped 2026-06-22). Scoping model = `deepseek/deepseek-v4-pro`
>   with **thinking + the web-search plugin** (pinned in `research_spec.SCOPING_*`). ⚠️ Pro reasons
>   55–76s → **exceeds the 30s API Gateway sync cap**: viable only via a local backend or an async
>   structuring path; behind the gateway it 504s. Fit scoring stays on fast Qwen. (B0.)
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
| **D** | Batch (S3 min) | Batch from selected prospects, mark approved internally | C | P1 | Approved batch ready to send |
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
    Pro no longer times out. Fit scoring stays on fast Qwen (it runs batched, behind the sync path).
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

## Phase C — Prospects: Apollo find + enrich (S2) ⏳ REBUILD (Apollo-only · supersedes the Clay build)

> **Direction change (locked 2026-06-21):** the Clay-based Phase C (seed push + CSV ingest + AI sourcing
> loop) was built and ran on `dev`, but **Clay has no programmatic Find Company / Find People API on any
> tier** — discovery stayed operator-run in Clay's UI with a CSV bridge. **Apollo.io is a true headless
> REST search + enrichment API** (company search, people search, `people/match`, one static key), so
> Phase C is rebuilt **Apollo-only**: Apollo does discovery **and** enrichment; the LLM only (a) scopes the
> Apollo filter and (b) scores rows. No Clay, no webhooks, no CSV import/export, no AI row-generation. All
> tables in [`data-schema.md`](data-schema.md). **No code until C0's gate clears (the plan upgrade).**

### The one idea that drives everything

> **Apollo is headless discovery + enrichment compute. The HoldSlot DB is the only system of record.**

Apollo returns rows on a REST call; tenant ownership, dedup, suppression, fit scoring, lineage, and
outreach status all live in Postgres — exactly as before. The only thing that changes is the *source*: a
programmatic Apollo call replaces the operator's Clay UI + CSV round-trip. The suppression gate, the
`fit.py` scoring door, `identity_key` dedupe, and the one central tenant guard are **reused unchanged**.

### Why Apollo replaces Clay
- **Clay:** no Find API on any tier → discovery was operator labour in the UI, bridged by manual CSV import.
- **Apollo:** `mixed_companies/search` + `mixed_people/api_search` are **programmatic REST** with one static
  key (`X-Api-Key`) — the whole find → score → select → enrich loop becomes in-app, no CSV, no operator.
- **⚠️ Credit model (corrected 2026-06-21, deep research):** **People search (`mixed_people/api_search`) is
  0-credit** and returns no email/phone. **Company search (`mixed_companies/search`) is listed as
  credit-consuming in Apollo's current docs** (the old "search is free" model is retired) — *confirm the
  exact cost against the live plan's credit page at C0.* `people/match` is the heavy paid step (1
  credit/email · 8/phone, phone async via webhook).
- **Cost:** Apollo Professional (master key) replaces Clay Launch; net MVP cost still drops vs Clay (see
  *MVP running cost*), but **company-search credits are a real line item** — budget + monitor.

### Locked decisions (founder, 2026-06-21)
| Decision | Choice | Why |
|---|---|---|
| Discovery + enrichment engine | **Apollo only** (replaces Clay entirely) | Clay has no Find API; Apollo is headless REST |
| Plan | **Professional + master API key**, upgraded *once this plan is ready to execute* | Search/Match are paid-plan-gated (free key 403s) |
| AI sourcing loop | **Killed.** The LLM never generates rows | Apollo generates rows; LLM only scopes the filter + scores |
| LLM scoring | **Lighter batched scorer** — 50–100 rows/call → `[{id, ai_score, reason}]`, **auto-run** on each arriving batch | Find returns 100s of rows; per-row scoring is too slow/costly. Drops the 12-line rubric components for the list view |
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
| **LLM** (OpenRouter, built) | **only** batched `score_rows` (company/person fit). *(All Brief→targeting judgment now lives in the B LLM that wrote the v3 spec — no second `design_filter` LLM pass; see below.)* | OpenRouter $ (small) |
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
        └─ upsert company on apollo_org_id (discovered) ─▶ auto batched score_rows("company") ─▶ fit_score + reason
  GATE 1: review + PATCH companies/select  (status=selected) — scopes Flow B
FLOW B — Find People
  apollo_map.map_people_filter(spec.people_search_params, org_ids=selected apollo_org_ids)
        ─▶ Apollo mixed_people/api_search (0 cr, NO email/phone)
        └─ DB-side post-filter (title-exclude/departments/max_per_company) + exclusion drop
        └─ upsert prospect on apollo_person_id, link company_id directly (found, unenriched)
        └─ auto batched score_rows("people")
  GATE 2 (enrich gate): review scores + select ─▶ POST prospects/enrich
        └─ Apollo people/match on selected ONLY (1 cr/email — the ONLY enrich spend; phone off) ─▶
           email / email_valid / phone / provider, status=scored
  CREATE BATCH (B.4) ─▶ selection/status only ─▶ Phase D approval (the real batches table is Phase D)
```
**Cost rules (enforced in code):** people search is 0 credits; **company search consumes plan credits**
(confirm cost at C0) — paginate only to `max_results`; never `people/match` before gate 2;
exclusion/existing-customer/post-filter is DB-side (no extra API calls); scoring batched + cached; enrich
only user-selected rows; phone off by default (8× + async webhook).

### Model usage — ONE LLM service in Phase C (`llm_call.purpose`)
The Brief→targeting LLM ran in **B** (writing the v3 spec); **`apollo_map` is deterministic (no LLM)**. So
Phase C's only LLM is the fit scorer:
| `llm_call.purpose` | Where | Function | Model | Notes |
|---|---|---|---|---|
| `company_fit` / `prospect_fit` | C3 `score_rows` | batched 50–100 rows → `[{id, ai_score, reason}]` | `qwen/qwen3.5-flash-02-23` (`FIT_MODELS`; Llama fallback dropped 2026-06-22), `temp=0`, thinking off | **auto-run per arriving batch**; cached, re-score on ICP edit |

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
post-filter + exclusion / existing-customer drop → upsert on `apollo_org_id` (`discovered`) → auto
`score_rows("company")` → return rows + a `research_run` (`source="apollo"`). `PATCH
/{client}/companies/select` (A.3): `status=selected`. **DoD:** companies land scored; selection scopes
Flow B; `GET /companies` feeds the table.

**C5 — Flow B (Find People + enrich). ✅ BUILT.** `POST /{client}/people/find-people` (B.1): **loop the selected orgs**,
one `search_people(map_people_filter(spec.people_search_params, org_ids=[<one apollo_org_id>]))` call each
(0 cr, no email) — C0: search rows carry no `organization_id`, so the per-org loop is how `company_id` is
known and `max_per_company` = the per-call `per_page` cap → DB-side post-filter (`job_title_exclude` on
`title`; **no `departments` filter here — absent at search**) + exclusion drop → upsert on `apollo_person_id`,
link `company_id` from the loop, `status=found` → auto `score_rows("people")`. (Empty selected-org set →
`400 "select companies first"`.)
`POST /{client}/prospects/enrich` (B.3, reworked): Apollo `people/match` on the **selected** rows only →
write `email` / `email_valid` / `phone` / `provider`, `status=scored` (the only credit spend, human-gated).
B.4 sets selection/status; no `batches` table (Phase D). **DoD:** find → score → select → enrich runs end
to end on live Apollo; only selected people cost credits.

**C6 — Frontend wiring + Clay/AI-loop teardown. ✅ BUILT** (wiring done; teardown done earlier). *(The teardown half — all the **Delete** items below —
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
- **Delete (dead under Apollo-only):** backend `clay.py`, `sourcing.py`; endpoints
  `POST /icps/{id}/research`, `/prospects/import`, `/companies/import`, `/sourcing-rounds`,
  `/prospects/accept`, `PUT /sourcing-settings`; `SourcingDoc` kind `sourcing_prompt`; `Tenant.seed_limit`
  + the Sourcing-settings modal; schemas `SourcingRound*` / `AcceptIn` / `*ImportResult` / `EnrichExportRow`
  / `SourcingSettings*`. Founder retires the `holdslot/prod/clay` secret.

**Critical path:** C0 → C1 → C2 → C3 → C4 → C5 → C6. **C1/C2/C3 can be built in parallel against the C0
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
- ⏳ **Apollo plan upgrade (founder action).** Professional + master key in `holdslot/prod/apollo`; until
  then C0.2's smoke test and the C4/C5 end-to-end runs are blocked.
- ⏳ **Founder end-to-end round on Apollo.** From the live Workspace: Trigger Find Companies → review/score
  → select → Trigger Find People → review/score → confirm-enrich (Apollo `people/match`) → create batch —
  all in-app, no CSV; the scoreboard shows real `cost_usd`. **The last gate before S2 is ticked done.**

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

| Stage (`Stage.id`) | Enters when | Smartlead source |
|---|---|---|
| Initial outreach (`contacted`) | batch locked → leads added, sequence started | `lead added` + `EMAIL_SENT` |
| Follow-up (`followup`) | step ≥2 sent, no reply | `EMAIL_SENT` (step n) |
| Positive reply (`replied`) | reply arrives **and founder classifies positive** | `EMAIL_REPLY` → manual move |
| Drop/DNC (`drop`) | negative/unsub reply, bounce, manual drop | `EMAIL_REPLY`(neg) · `LEAD_UNSUBSCRIBED` · `EMAIL_BOUNCE` |
| Meeting / No show / Qualified billable | **Phase F** | — |

**MVP line: reply classification is human, not LLM.** A reply lands as an `OutreachEvent`, shows in the
prospect's conversation log **and** the **Reply Queue** (cross-campaign triage). Founder reads it and uses
the **stage-move control**. AI drafting/classification stays **[SKIP] until paying signups**; **[SCALE]**
`reply_classify`/`reply_draft` purposes drop into the same queue, no redesign.

**Variant fidelity:** campaign variants map 1:1 to Smartlead **sequence-step** A/B/C variants; per-variant
open/reply syncs back; the per-prospect selector assigns at lead-add time and **locks once sent**. Editing
after send creates the next version (append-only).

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

**E4 — [MVP] Webhook ingest → events → stages ⭐.** `POST /smartlead/webhook` (signature-verified, fast
2xx, idempotent) → write `outreach_event` → advance stage: `EMAIL_SENT` → contacted/followup; `EMAIL_OPEN`
→ variant count; `EMAIL_REPLY` → log + flag for review (no auto-classify); unsub/bounce/negative → drop.
Founder moves positives to `replied`. **[SCALE]** API-GW→SQS→worker + `reply_classify`/`reply_draft` suggestions.

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
the mocks; "Confirm & lock" calls E3. **DoD:** founder locks a batch, watches real sends, triages a reply
from the Reply Queue, advances to Positive reply, sends a threaded booking message — all live; tick **S4/S5**.

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
| Meeting recaps tab | `meet_link`, `conference_record_id`, attendees, transcript ref | scaffold YES · LLM summary [SKIP→later] |

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
post-meeting poll (F4).

**F4 — Held + duration → qualify (the billing trigger) ⭐.** EventBridge poll reads the conference record →
set held/duration/attendees → apply the rule: **approved AND duration ≥10 → `qualified=true`,
`stage=billable`** + compute `amount` (§7); else → `stage=noshow`. Idempotent on re-poll.

**F5 — Ledger + Recaps seam (rows now, engines later).** Read endpoints serve `meeting`-derived rows to the
Billing ledger (qualified/no-show, held/duration, `recId`, amount, won/lost) and Meeting recaps (Meet link,
conference id, attendees, won/lost toggle). **[SKIP→later]:** Stripe invoice push + LLM `meeting_summary`.
**DoD:** both tabs render real rows; won/lost persists; no Stripe/LLM call.

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
| `holdslot/prod/openrouter` | ✅ | Key valid; $50 spend cap. **`models` must be non-US providers** — gemini/gpt are geo-blocked (403 ToS) for HK. The secret `models` is only the default fallback now: each call site pins its own list in code — **scoping** = `SCOPING_MODELS` (`deepseek/deepseek-v4-pro`, async path), **fit** = `FIT_MODELS` (`qwen/qwen3.5-flash-02-23`); Llama dropped 2026-06-22 |
| `holdslot/prod/apollo` | ◑ | `key` stored but **free-tier** (Search/Match 403) — upgrade to Professional + master key → C0. (`holdslot/prod/clay` retired) |
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
