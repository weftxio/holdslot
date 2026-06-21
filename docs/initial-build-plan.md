# HoldSlot — Initial Build Plan (dogfood MVP)

> **Status (2026-06-21):** Phases **A (S0)** + **B (S1)** **built, reviewed & live on `dev`** — backend on
> the `dev` API (alias `live`), Workspace web on Amplify `dev`. **Phase C (S2) is being rebuilt
> Apollo-only.** The Clay-based Phase C (seed push → CSV ingest + fit scoring → AI sourcing loop) was built
> and ran on `dev`, but **Clay has no programmatic Find Company / Find People API on any tier** —
> discovery stayed operator-run in Clay's UI with a CSV bridge. **Apollo.io is a headless REST search +
> enrichment API** (company search, people search, `people/match`, static key), so Phase C moves to
> **Apollo only**: Apollo does discovery *and* enrichment; the LLM only (a) scopes the Apollo filter and
> (b) scores rows. No Clay, no webhooks, no CSV. See **Phase C** for the rebuild plan; schema deltas in
> [`data-schema.md`](data-schema.md). **The Apollo find/enrich loop is the one gate left to tick S2.**

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
  contract** (the interface to the prospecting search — now Apollo, at **v2**). A provider/contract change
  is a deliberate version bump (v1→v2), not silent drift. Spec versions are append-only JSONB.

### The `ResearchSpec` v2 format (v1 locked 2026-06-12; **revised to v2 for Apollo, 2026-06-21**)

**Why v2 (deep-researched against Apollo's live API, 2026-06-21):** v1 was authored Clay-aligned. The
Apollo parameter audit (both REST calls, see Phase C → *Apollo parameter contract*) showed (a) several v1
fields have **no Apollo request filter** and must move DB-side, and (b) Apollo exposes **high-value
targeting the brief already implies but v1 dropped on the floor** — most importantly **funding signals**
and **active-job-posting (hiring) signals**, which are exactly the brief's *buying signals* made
machine-actionable. v2 captures them so the brief's intent reaches Apollo. The spec is append-only and
`spec` is JSONB, so v2 is **a prompt + schema revision, zero migration** (`research_spec.version` simply
inserts the next row; the panel renders whatever `spec_version` it loads).

`apollo_map` (C3, pure + fixture-tested) is the only thing that consumes the spec; it maps each field to a
concrete Apollo param or to a DB-side post-filter. Under Apollo there is **no operator transcription and no
callback** — both searches are programmatic; only `people/match` (the human-selected set) spends enrich
credits. **⚠️ Company search itself may consume Apollo plan credits** (Apollo's current docs list it as
credit-consuming — confirm at C0; this corrects v1's "0-credit search" assumption).

```jsonc
{
  "spec_version": 2,
  "company_search": {                          // → apollo_map → POST mixed_companies/search
    "industry_keywords_include": [],           // → q_organization_keyword_tags (FREE TEXT; Apollo org search has NO free-text industry filter — keyword tags are the documented path)
    "industry_keywords_exclude": [],           // ⊘ DB-side post-filter (no Apollo keyword/industry exclude)
    "description_keywords_include": [],         // → merged into q_organization_keyword_tags
    "semantic_description": "",                 // prose intent → distilled to keyword tags
    "employee_count": { "min": null, "max": null },   // → organization_num_employees_ranges: ["min,max"]
    "revenue_usd":    { "min": null, "max": null },    // → revenue_range[min]/[max]
    "founded":       { "after": null, "before": null },// ⊘ DB-side post-filter (no Apollo founded-year request filter)
    "company_types": [],                               // ⊘ DB-side post-filter (no Apollo public/private filter)
    "locations_include": [],                           // → organization_locations (flat free-text: "City, ST, Country")
    "locations_exclude": [],                           // → organization_not_locations
    "funding": {                                       // NEW — Apollo-native funding filters
      "latest_amount_usd": { "min": null, "max": null },   // → latest_funding_amount_range[min]/[max]
      "total_usd":         { "min": null, "max": null },   // → total_funding_range[min]/[max]
      "latest_round_after": null                           // "YYYY-MM-DD" → latest_funding_date_range[min]
    },
    "hiring_signals": {                                // NEW — timing signal from active job postings
      "job_titles": [],                                 // → q_organization_job_titles
      "min_open_roles": null,                           // → organization_num_jobs_range[min]
      "posted_after": null                              // "YYYY-MM-DD" → organization_job_posted_at_range[min]
    },
    "technographics": { "enabled": false, "vendors": [] }, // → currently_using_any_of_technology_uids (FIXED Apollo tech UIDs)
    "max_results": 500
  },
  "people_search": [{                          // one per ICP → scoped to SELECTED orgs at Flow B
    "icp_id": "",
    "job_title_keywords": [],                  // → person_titles (FREE TEXT, fuzzy)
    "include_similar_titles": true,            // → include_similar_titles (replaces v1 job_title_match_mode)
    "job_title_exclude": [],                   // ⊘ DB-side post-filter (no Apollo title-exclude)
    "seniority": [],                           // → person_seniorities — FIXED enum: owner|founder|c_suite|partner|vp|head|director|manager|senior|entry|intern
    "departments": [],                         // ⊘ DB-side post-filter on returned departments[] (Apollo search has NO dept/function param — UI-only)
    "person_locations": [],                    // → person_locations (free text)
    "max_per_company": 2,                      // ⊘ DB-side cap (no Apollo per-company param)
    "max_total": 800
  }],
  "exclusions": { "domains": [], "company_linkedin_urls": [], "emails": [] },  // ⊘ DB-side suppression (never Apollo params)
  "gaps": [{ "field": "", "why": "", "ask": "" }]                              // the value-loop prompts
}
```

**Legend:** `→` = mapped to an Apollo request param · `⊘` = DB-side (post-filter or suppression; Apollo
has no request param). **Industry note:** Apollo org search has no free-text industry filter — v2 routes
industry intent through `q_organization_keyword_tags` (free text). A curated `industry → Apollo
industry_tag_id` map is a later precision lever (the tag-ID list is not API-published).

**Division of labour:** the LLM emits **targeting only** (`company_search`, `people_search`,
`exclusions`, `gaps`) — now including funding + hiring signals distilled from the brief's *signals*/
*maturity* prose. The **credit policy** (email-status gate, phone off, caps) is **deterministic server
config merged at save time** — never LLM-inferred. v2 `credit_policy` adds `email_status_filter`
(default `["verified"]` → people/match deliverability gate). Suppression is applied HoldSlot-side
*before* any Apollo call.

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
  - **Model choice (scoping):** DeepSeek V4 Flash is the best-value reasoning model that fits the 30s sync
    Lambda budget (~18s). The flagship `deepseek-v4-pro` reasons for 55–76s → would time out behind API Gateway.
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
- **B6 — ResearchSpec v2 (Apollo enrichment of the brief; 2026-06-21).** No migration (JSONB, append-only).
  Three sub-edits, all in `domains/briefs`:
  1. `research_spec.py` strict `json_schema` + Pydantic validator → the **v2 shape** above (flat
     `locations_*`; add `funding`, `hiring_signals`, `include_similar_titles`; `industries_*` →
     `industry_keywords_*`; keep `founded`/`company_types`/`departments`/`job_title_exclude` as carried
     fields the mapper routes DB-side). Bump `SPEC_VERSION = 2`, `PROMPT_VERSION = "brief-structure-v3"`.
  2. `DEFAULT_SYSTEM_PROMPT` → **de-Clay + Apollo-aware**: drop "Clay parameters / LinkedIn industry
     labels"; instruct the model to (a) emit industry intent as free-text **keyword tags**, (b) translate
     the brief's *buying signals* into `funding` + `hiring_signals`, (c) constrain `seniority` to Apollo's
     fixed enum, (d) express `maturity` as employee/revenue/funding ranges (no standalone Apollo filter).
  3. `CREDIT_POLICY` → add `email_status_filter: ["verified"]`; keep `phone: false`.
  - **DoD:** Generate Scope produces a v2 spec; the *Prospect Scope* panel renders the new sections (no
    new CSS — reuse the `.icp-grid` grammar); old v1 rows still load. Re-run = `version+1`.
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
| **`apollo_map`** (pure, fixture-tested) | `ResearchSpec` v2 → Apollo request params (deterministic — no LLM); routes the `⊘` fields DB-side | — |
| **LLM** (OpenRouter, built) | **only** batched `score_rows` (company/person fit). *(All Brief→targeting judgment now lives in the B LLM that wrote the v2 spec — no second `design_filter` LLM pass; see below.)* | OpenRouter $ (small) |
| **HoldSlot DB** (Aurora) | system of record: dedupe, suppression, DB-side post-filters, scores, lineage, status | — |

> **Architecture refinement (2026-06-21):** v1's plan had a second LLM (`design_filter`, purpose
> `apollo_filter`) re-distilling the brief into Apollo params at C3. With **ResearchSpec v2** carrying
> Apollo-aligned targeting (keyword tags, ranges, funding/hiring signals, enum seniority), that mapping is
> now **deterministic** — `apollo_map` (pure, fixture-tested) replaces the LLM. This removes a drift
> surface (two LLMs distilling the same brief could disagree), an LLM cost, and makes the whole Flow A/B
> request build unit-testable. The `apollo_filter` purpose is **dropped**; fit scoring is the only Phase-C LLM.

### End-to-end flow (two gates · no CSV · no operator)
```
FLOW A — Find Company
  apollo_map.map_company_filter(spec.company_search) ─▶ Apollo mixed_companies/search (paginate; plan credits)
        └─ DB-side post-filter (founded/company_types/kw-exclude) + exclusion/existing-customer drop
        └─ upsert company on apollo_org_id (discovered) ─▶ auto batched score_rows("company") ─▶ fit_score + reason
  GATE 1: review + PATCH companies/select  (status=selected) — scopes Flow B
FLOW B — Find People
  apollo_map.map_people_filter(spec.people_search, org_ids=selected apollo_org_ids)
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
The Brief→targeting LLM ran in **B** (writing the v2 spec); **`apollo_map` is deterministic (no LLM)**. So
Phase C's only LLM is the fit scorer:
| `llm_call.purpose` | Where | Function | Model | Notes |
|---|---|---|---|---|
| `company_fit` / `prospect_fit` | C3 `score_rows` | batched 50–100 rows → `[{id, ai_score, reason}]` | `qwen/qwen3.5-flash-02-23` (fallback `meta-llama/llama-3.3-70b-instruct`), `temp=0`, thinking off | **auto-run per arriving batch**; cached, re-score on ICP edit |

> **Region rule (see B0):** OpenAI / Anthropic / Google providers are geo-blocked (403 ToS) for this HK account — every purpose routes to non-US providers only (Qwen / Llama / DeepSeek / Mistral).

The killed AI-loop purposes (`sourcing_round`, `candidate_validate`) **and the planned `apollo_filter`
purpose** are removed. Filter-building + dedupe are deterministic (no LLM).

### Apollo parameter contract (deep-researched 2026-06-21 — the `apollo_map` spec)
The authoritative request-param mapping. `apollo_map` (C3, pure) builds exactly these from `ResearchSpec`
v2; everything marked **DB-side** is a post-filter because Apollo has no request param for it. **Confirm
exact keys + the company-search credit cost against a live master-key call at C0** before hard-coding.

**Flow A — `POST mixed_companies/search`** (auth `X-Api-Key`; **credit-consuming — confirm at C0**)
| Apollo request param | Type / vocabulary | ← ResearchSpec v2 source |
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
| Apollo request param | Type / vocabulary | ← ResearchSpec v2 source |
|---|---|---|
| `organization_ids[]` | Apollo org ids | **selected** `company.apollo_org_id` (the Flow A→B scope link — required) |
| `person_titles[]` | free text, fuzzy | `job_title_keywords` |
| `include_similar_titles` | bool | `include_similar_titles` |
| `person_seniorities[]` | **fixed enum:** owner·founder·c_suite·partner·vp·head·director·manager·senior·entry·intern | `seniority` (B emits enum values) |
| `person_locations[]` | free text | `person_locations` |
| `contact_email_status[]` | enum: verified·unverified·likely to engage·unavailable | `credit_policy.email_status_filter` |
| `page` · `per_page` | int · **≤100** | paginate to `max_total` (cap: 500 pages = 50k) |
| **DB-side post-filter (no Apollo param):** | | `job_title_exclude`, `departments` (filter on returned `departments[]`), `max_per_company` (group by `organization_id`, cap) |

**Enrich — `POST people/match`** (the only enrich spend): `id`=`apollo_person_id`, `reveal_personal_emails=true`
(1 cr), `reveal_phone_number=PHONE_ENABLED` (8 cr, **async → requires `webhook_url`**, off at MVP). Returns
`email`, `email_status`, `phone_numbers[]`, provider.

### Tasks (by dependency; all `[MVP]`)

**C0 — Validation gate (no code; blocks everything).**
1. **👤 Founder: upgrade Apollo to Professional + master key** in `holdslot/prod/apollo` (`{"key": …}`).
   Until done, every Search/Match call 403s on the free key — only `organizations/enrich` works.
2. **Smoke-test the 3 endpoints** (`mixed_companies/search`, `mixed_people/api_search`, `people/match`) at
   `per_page:1`; read 200 / 403 / 401 / 429. **Stop the build if people-search ≠ 200.** Save each JSON to
   `apps/api/tests/fixtures/apollo/` — adapters are built + unit-tested against these (no field guessing).
3. **Confirm the company-search credit cost** against the live plan's *About Credits* page + a real call
   (the param contract assumes it consumes credits). Capture the per-call cost → feeds *MVP running cost*.
4. **Verify the ambiguous keys against the live response** (research flagged these): the funding-**stage**
   filter key + its code values; `street_address`/`postal_code` vs `raw_address`; that live `people[]` rows
   carry `last_name`/`linkedin_url`/`departments[]` (the docs stub obfuscates them). Lock `apollo_map` to
   what the fixtures actually return.

**C1 — Data model (migration `0009`).** `add company.apollo_org_id` (nullable, unique per tenant — feeds
Find People's `organization_ids`) · `add prospect.apollo_person_id` (nullable — the `people/match` key) ·
`drop tenant.seed_limit` (was AI-loop seed anchoring). **DoD:** models gain the two ids; `0008 → 0009`
head; up/down clean on dev.

**C2 — Apollo transport + adapters.**
- `integrations/apollo/client.py` (lazy secret, SnapStart-safe, mirrors the B3 discipline; header
  `X-Api-Key`, 429 backoff + pagination, `per_page` ≤100, 500-page hard cap): `search_companies`
  (`mixed_companies/search`, **credit-consuming**) · `search_people` (`mixed_people/api_search`, 0 cr, no
  email/phone, **master key**; **never** legacy `mixed_people/search` → 422) · `match_person`
  (`people/match`, the enrich spend; `reveal_phone_number` ← `PHONE_ENABLED` → requires `webhook_url`).
- `domains/prospects/apollo_map.py` (pure, fixture-tested): `map_company_filter(company_search)`,
  `map_people_filter(people_search_item, org_ids)`, `parse_company`, `parse_person` — **exactly the
  *Apollo parameter contract* tables above**, incl. the deterministic transforms (employee→ranges,
  enum-seniority, locations-flatten) and the DB-side `⊘` post-filter set. **DoD:** builders + parsers
  unit-tested against the C0 fixtures, no network.

**C3 — Deterministic filter build + LLM fit scoring.**
- **No `design_filter.py`, no `apollo_filter` LLM.** Filter building is `apollo_map` (C2, pure) consuming
  the v2 spec — the brief→targeting judgment already ran in B6. The DB-side post-filters (`⊘` rows) live
  next to `suppression.py` and run on each search's results before upsert.
- `fit.py` — add the batched `score_rows(rows, inputs, mode) → [{id, ai_score, reason}]` scorer
  (50–100/call, cached), auto-invoked per arriving batch. Keep the `fit_rubric` `sourcing_doc`; drop `sourcing_prompt`.

**C4 — Flow A (Find Company).** `POST /{client}/companies/find-company` (A.1):
`search_companies(map_company_filter(spec.company_search))` (paginate, cap at `max_results`) → DB-side
post-filter + exclusion / existing-customer drop → upsert on `apollo_org_id` (`discovered`) → auto
`score_rows("company")` → return rows + a `research_run` (`source="apollo"`). `PATCH
/{client}/companies/select` (A.3): `status=selected`. **DoD:** companies land scored; selection scopes
Flow B; `GET /companies` feeds the table.

**C5 — Flow B (Find People + enrich).** `POST /{client}/people/find-people` (B.1):
`search_people(map_people_filter(spec.people_search[i], org_ids=selected apollo_org_ids))` (0 cr, no email)
→ DB-side post-filter + exclusion drop → upsert on `apollo_person_id`, link `company_id` directly,
`status=found` → auto `score_rows("people")`. (Empty selected-org set → `400 "select companies first"`.)
`POST /{client}/prospects/enrich` (B.3, reworked): Apollo `people/match` on the **selected** rows only →
write `email` / `email_valid` / `phone` / `provider`, `status=scored` (the only credit spend, human-gated).
B.4 sets selection/status; no `batches` table (Phase D). **DoD:** find → score → select → enrich runs end
to end on live Apollo; only selected people cost credits.

**C6 — Frontend wiring + Clay/AI-loop teardown.**
- `lib/api.ts`: add `findCompanies`, `selectCompanies`, `findPeople`, reworked `enrichProspects`; **drop**
  `importProspectsCsv`, `importCompaniesCsv`, `runSourcingRound`, `acceptCandidates`, `saveSourcingSettings`.
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
upgraded plan. **Depends on B6** (the v2 spec `apollo_map` consumes). **MVP cost:** Apollo Professional
(master key — see *MVP running cost*) + LLM <$10/mo; **people search is 0 credits**, but **company search
consumes plan credits** (confirm at C0) and the gate-2 enriched set spends 1 cr/email.

### Cross-phase
- **From A:** the central guard scopes every table; **MVP adds ZERO AWS resources** (`find-company` /
  `find-people` / `enrich` are routes on the existing `$default` proxy).
- **From B:** `ResearchSpec` **v2** (`company_search` / `people_search` / `exclusions`, now carrying
  funding + hiring signals + enum seniority) is the `apollo_map` input — consumed **deterministically**
  into Apollo params (no second LLM). Exclusion lists + the B3 adapter + `llm_call` + `prompt_version` are
  reused as-is for fit scoring.
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
| `holdslot/prod/openrouter` | ✅ | Key valid; $50 spend cap. **`models` must be non-US providers** — gemini/gpt are geo-blocked (403 ToS) for HK; set to `[deepseek/deepseek-v4-flash, meta-llama/llama-3.3-70b-instruct]` 2026-06-21 |
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
