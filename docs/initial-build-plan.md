# HoldSlot — Initial Build Plan (dogfood MVP)

> **Status:** Phase A (S0) + Phase B (S1) **built & live** — backend on the `dev` API (Lambda v8),
> Workspace web on Amplify `dev`. **Phase C (S2: Clay seed + AI sourcing loop) — full MVP BUILT +
> POST-BUILD REVIEW FINALIZED (2026-06-19, dev): C0.4 → C6 complete** (migration `0005`; the `prospects`
> API domain = suppression gate, Clay push, CSV ingest + fit scoring, usage scoreboard, AI sourcing loop;
> review fixes applied — credit double-spend closed, C4 cost scoreboard live, accept/import accounting
> corrected, owner-gated spend, frontend race fixed; round 2 (2026-06-20) dropped `credits_used` (no Clay
> API), fixed run-attribution double-count, added the seed-limit control, rounded all costs to 6 dp; 37
> backend tests green / web typecheck + ruff clean). **Migration `0005` run on `dev` Aurora 2026-06-20**
> (head `0005_phase_c`; prospect/research_run/sourcing_doc + seed v1 docs verified). **Remaining to tick
> S2 — the one operational gate below: a real founder end-to-end round on Clay free.**

**The first build:** make HoldSlot's own product real enough to run our own outbound on it and land our
first signups. Scoped cut of the full spec in `backend-development-plan.md`.

> 📐 **Data schema — single source of truth:** every table (Clay + internal DB, Phases A–C, built or
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
| Prospect storage + filter/select · **Clay connection** (push spec → enrich → ingest) | **BUILD** |
| Batch + internal approve · **Smartlead** (campaign, A/B/C, send, reply-to-thread) | **BUILD** |
| **Meeting** (booking → Calendar/Meet event + invites; capture held + duration via Meet REST) | **BUILD** |
| Sending domains + warm-up | operate (manual, start now) |
| AI reply drafting · summaries/transcripts · feedback links · masking · billing/Stripe · analytics · multi-tenant **operations** | **SKIP** (return when onboarding paying signups) |

## Phases (dependency- and priority-ordered)

| # | Phase | Must-build | Depends on | Pri | DoD |
|---|---|---|---|---|---|
| **A** | Foundation (S0) | Founder login; seed tenant #0; multi-tenant + role-aware schema; Aurora + deploy; console on live data | — | P0 | Both founders log in (full access); schema admits a 2nd tenant/non-owner role w/o migration |
| **B** | Targeting (S1) | Brief → OpenRouter `ResearchSpec`; ICP record | A | P0 | ResearchSpec saved, Clay-ready |
| **C** | Prospects + Clay (S2) | Spec → Clay → ingest fit-scored `Prospect` rows; filter/select | B · Clay | P0 | Enriched prospects flow in automatically |
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
bridge into Clay) + curated **ICP** profiles. **First use of the LLM** (OpenRouter).

**DoD:** founder fills the Brief in the live Workspace → completeness ring reflects saved data →
"Generate Scope" produces a saved versioned `ResearchSpec` + gap prompts → one or more ICPs exist.
Clay-ready; nothing sent to Clay yet (that's C).

### The seam — one LLM job: the translator

The Brief is free text in the client's language; Clay needs machine-actionable search params. That
translation is otherwise per-client operator labour. So the LLM sits at **one seam only: Brief (+ICPs) →
`ResearchSpec` + gap prompts.** It does *not* score fit (C), draft email (E), or converse.

**Value loop:** low-friction intake → versioned spec → Clay (C) → outreach (E) → meetings (F); each
completion returns **gap prompts** (what's too vague) to sharpen the Brief *before* credits are spent;
outcomes feed the next revision → spec vN+1 > vN. Versions are append-only = the loop's memory. Gap
prompts protect the two costliest resources (Clay credits, warmed inboxes) for a few cents of LLM.

### Design rule: the form churns — the backend must not care

- **Brief and each ICP are one JSONB document** — not typed columns. Only consumers are the form (opaque
  round-trip) and the LLM prompt (schema-tolerant). A form change = a frontend edit + maybe one entry in
  the required-fields list. **Zero migrations, zero API churn.**
- **Promote-on-demand:** promote a field to a validated column only when it becomes load-bearing for
  backend logic (e.g. exclusion lists in C).
- **Two stability profiles:** the form documents churn freely; the **`ResearchSpec` is a locked v1
  contract** (the interface to Clay). The LLM absorbs the difference. Spec versions are append-only JSONB.

### The `ResearchSpec` v1 format (Clay-aligned — locked 2026-06-12)

**Clay reality (verified):** Clay has **no API to create tables/searches** — those are in-app only. The
programmable surface is **webhook sources** (POST rows in; 50k-lifetime cap/webhook) + the **HTTP API
column** (POST enriched rows back). So the spec has two halves:
- **`company_search`** → operator transcribes once into a cloned Clay *Find Companies* search (~10 min).
- **`people_search` + `exclusions`** → fully programmatic via the webhook.
- Enriched rows come back via HTTP API column → `POST /clay/results` (C), gated on `email_valid`.

```jsonc
{
  "spec_version": 1,
  "company_search": {                       // → operator → Clay "Find Companies" (in-app)
    "industries_include": [], "industries_exclude": [],
    "description_keywords_include": [], "description_keywords_exclude": [],
    "semantic_description": "",                                  // Clay AI filter — one sentence
    "employee_count": { "min": null, "max": null },
    "revenue_usd":    { "min": null, "max": null },
    "company_types": [], "founded": { "after": null, "before": null },
    "locations_include": { "countries": [], "states": [], "cities": [] },
    "locations_exclude": { "countries": [], "states": [], "cities": [] },
    "technographics": { "enabled": false, "vendors": [] },       // default OFF — 3 credits/company
    "max_results": 500
  },
  "people_search": [{                       // one per ICP → per-row via webhook (programmatic)
    "icp_id": "", "job_title_keywords": [],                      // titles are the PRIMARY field
    "job_title_match_mode": "is_similar", "job_title_exclude": [],
    "seniority": [], "departments": [], "max_per_company": 2, "max_total": 800
  }],
  "exclusions": { "domains": [], "company_linkedin_urls": [], "emails": [] },
  "gaps": [{ "field": "", "why": "", "ask": "" }]                // the value-loop prompts
}
```

**Division of labour:** the LLM emits **targeting only** (`company_search`, `people_search`,
`exclusions`, `gaps`). The **credit policy** (waterfall order, "only run if" gates, test-batch size,
caps) is **deterministic server config merged in at save time** — never LLM-inferred. Suppression is
applied HoldSlot-side *before* any push. These knobs become real in C; the spec carries them from v1.

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
  `default_model = google/gemini-2.5-flash-lite`, `models` fallback `[gemini-2.5-flash-lite, gpt-5-mini]`,
  `provider.require_parameters = true` (~$0.0009/call). `verify_keys --strict openrouter` green. Required-fields
  rubric frozen from the UI Required/Optional tags.
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
- **Open item (doesn't block C):** founder end-to-end acceptance test on dev. Tick **S1** once run.

**Critical path:** B0 → B1 → B2 → {B3 → B4} → B5. After B, a Brief/ICP form change costs a frontend edit
+ a rubric entry — no migration. **Cost:** ~$5–20/mo LLM; **no Clay credits in B.**

---

## Phase C — Prospects: Clay seed + AI sourcing loop (S2) ✅ BUILT (dev) · ⏳ 1 operational gate

Turns the saved **`ResearchSpec`** + an **AI sourcing loop** into enriched, fit-scored **`Prospect`**
rows. Design finalized 2026-06-19 after Clay architecture research (see
[`research/clay-architecture.md`](research/clay-architecture.md); all tables in
[`data-schema.md`](data-schema.md)). **No code until C0's gates lock.**

### The one idea that drives everything

> **Clay is stateless enrichment *compute*, not a database. The HoldSlot DB is the only system of record.**

Rows flow *through* Clay (**push → enrich → pull → clear**); Clay holds no durable state we depend on.
Tenant ownership, dedup, suppression, fit scoring, lineage, and outreach status all live in Postgres.
This one boundary resolves every hard question (multi-tenant, the 50k caps, shared prospects, industry).
Backed by how Clay is run at scale: agencies run **80+ clients from one table**, and Clay's own guidance
is "one master table, slice with filters/views" — never a table per client/industry.

**Strict division of labour:** the **AI sourcing loop discovers + qualifies** (cheap, fresh, unlimited);
**Clay only enriches** — verifying contact data, the one step that costs real money, and only for
candidates that already passed fit. An email exists only if a waterfall provider returned it and
validation passed (no hallucinated contacts). **Human-in-the-loop:** the founder owns the sourcing prompt
+ fit rubric (locked at C0, in `docs/prompts/`), reviews each round, edits between rounds (versioned).
Auto self-improvement (replies/meetings → sourcing) closes in **E** with zero redesign, because C1's
schema captures source lineage + outcome labels from day one.

**DoD (MVP):** founder builds **one** generic Clay enrichment table (once, ever) → HoldSlot
**programmatically pushes** suppressed, identity-keyed rows into its webhook → Clay enriches → operator
**exports CSV** (one click) → HoldSlot **ingests** → suppress → dedupe → fit-score into the tenant-scoped
`prospect` table; both sources visible / filterable / selectable in the Workspace *Prospect list* with a
Source column. Nothing sent to a client yet (that's D).

### Clay tier strategy — Free → Launch → Growth (decided 2026-06-19)

Free tier (200 rows / 100 credits) is **proof-only** — it validated the pipeline (C0.1 ✅) and nothing
more. **Build + test C1–C6 on the free tier** (small sample batches fit the 200-row cap), then
**subscribe Launch for the first real-volume round**; **Growth** is the automation/scale target.

| Tier | $/mo | Role | Ingest | **Move to it when** |
|---|---|---|---|---|
| **Free** | $0 | pipeline proof (done) | CSV | — (already outgrown) |
| **Launch** | ~$185 | **MVP dogfood run (real volume)** | manual CSV | **the first real-volume sourcing round** — a single run blows free's 200-row / 100-credit cap. *(Build + test C1–C6 on free with small batches; subscribe Launch only when running a real round.)* |
| **Growth** | ~$446–495 | scale / automation | **HTTP API auto-callback** + BYOK | (a) manual CSV export becomes a bottleneck (frequent rounds / multi-client), **or** (b) Launch's 2,500 credits/mo run out and **BYOK** (own provider keys = 0 Clay credits) would save money, **or** (c) hands-off multi-client volume. |

- **Build + test C1–C6 on free** (small sample batches fit the 200-row cap); **subscribe Launch only at
  the first real-volume round** — CSV ingest is byte-identical across tiers, so nothing rebuilds.
- **Growth changes only the ingest *transport*** (CSV → auto-callback) **+ 0-credit BYOK** — suppression,
  dedupe, scoring, schema, and UI are unchanged (that's the C3 `[SCALE]` swap + C0.6 gates).

### Best & simplest way to handle the Clay table (locked decisions)

| Decision | Choice | Why |
|---|---|---|
| How many tables | **Exactly one**, reused for all clients/industries/runs | No table-creation API on any tier; per-table = manual cloning + structure-sync hell |
| What it stores | **Nothing durable** — a passthrough buffer; rows cleared after ingest | Rows are transient compute; our DB is the truth |
| Knows tenants? | **No.** Correlation columns = `run_id` + `identity_key` only | Makes "enrich once, reuse across N tenants" free; tenant fan-out is DB logic |
| Who discovers | **HoldSlot** (AI loop + spec); Clay only enriches | Avoids per-client in-app search config (which has no API) |
| Avoid double-charge | **Dedup before push** vs our identity cache + Clay **auto-dedupe (keep-oldest)** backstop (per-row "only run if empty" gates are OFF — enrichment always runs) | Credits charged per row; dedup, not gating, is the safeguard |
| Tenant & industry | **Columns/attributes, never table boundaries** | More tables = the anti-pattern; both are enrichment data / DB scope |
| Results out | **Free/Launch = manual CSV; Growth = HTTP API column auto-POST; Enterprise = + passthrough** | Automated out is Growth-gated (confirmed) |
| Only recurring manual op | **Webhook rotation** (~every 50k pushes: add a new webhook to the same table, update one config value) | 50k cap is per-webhook lifetime, non-resettable; multiple webhooks/table OK |

**Onboarding a new client touches Clay zero times — it is a DB `INSERT`.**

### Schema (full detail in [`data-schema.md`](data-schema.md))

- **Clay table** — `run_id` + `identity_key` (correlation, no tenant), inputs (name/company/domain/
  linkedin, + titles/seniority when pushing companies), enrichment outputs (email/phone/title/company_*
  incl. `company_industry`), `email_valid` gate.
- **DB MVP** — `prospect` (per-(identity × tenant); `identity_key` + `last_enriched_at` are the seam),
  `research_run`, `sourcing_doc`.
- **DB SCALE (additive, when 2nd tenant lands — no rewrite)** — `person` (tenant-agnostic enrichment
  cache keyed by `identity_key`) + `enrichment_request` (fan-out + dedup-before-push). A prospect wanted
  by 5 clients is **enriched once, paid once**, and exists as 5 fit-scored `prospect` rows.

### Model usage — FINAL (every call through the B3 adapter)

| `llm_call.purpose` | Where | Model (OpenRouter slug) | Config | Volume | Cost |
|---|---|---|---|---|---|
| `prospect_fit` | C3 scoring | **`qwen/qwen3.5-flash`** | `temperature=0`, `enable_thinking=false`, strict schema | 100–1,000/mo | <$1/mo |
| `sourcing_round` | C5 discovery | **`deepseek/deepseek-v4-pro` + OpenRouter web-search plugin** | reasoning effort **Think High** (NOT Think Max); verify tool-calling loop | 2–8/client/mo | ~$0.05–0.20/round |
| `candidate_validate` | C5 validation | deterministic (DNS/HTTP liveness) **first**, then **`qwen/qwen3.5-flash`** on survivors | `temperature=0`, `enable_thinking=false`, strict schema | per candidate | <$1/mo |
| *dedupe* | C2/C3 | **none — deterministic** | exact-key identity logic | — | $0 |

**Why each:** `prospect_fit` is a bounded rubric (not open reasoning) → cheapest schema-reliable flash
(Qwen3.5 ≈ $0.065/M in, $0.26/M out). `sourcing_round` is the **only call site where model quality carries
the outcome** (mistakes burn enrichment credits) → DeepSeek V4 Pro's strong agentic reasoning + live web
research at low cost (≈ $0.435/M in, $0.87/M out, MIT-licensed). `candidate_validate` runs the mechanical
liveness gate first and only spends an LLM call on survivors — narrow, lowest-risk.

**Risks to validate before rollout:** (1) calibrate `prospect_fit` on a **50-prospect sample vs
`deepseek-v4-pro`** — anchor the rubric with in-prompt examples, request score + brief justification for
drift audit; (2) `sourcing_round`'s primary risk is **web-plugin / tool-calling reliability**, not
reasoning — test the agent loop and confirm the plugin returns sufficient context.

**Deploy-time checks (all rows):**
- Confirm exact current slugs + live prices on the OpenRouter model pages (Qwen versions are dated; labs
  reprice ~monthly).
- Account for OpenRouter's flat **5.5% credit-purchase fee**.
- Enable **prompt caching** for reused system prompts/templates (can cut repeated-context cost 60–80%).
- **`enable_thinking` MUST be `false` on both Qwen rows** — Qwen bills thinking tokens at 3–10× the output
  rate and would silently blow the scoring budget.

Web research = OpenRouter's web-search plugin attached to DeepSeek V4 Pro through the same B3 adapter — no
new provider, no new secret at MVP; search is metered by OpenRouter under the existing $50 cap. Per-purpose
routing (`models_by_purpose` config) lands with C5. Dedupe = deterministic, no LLM.

### Founder-edited prompt documents (versioned data, UI = existing classes)

Both v1 **authored & locked**: sourcing prompt+skill ([`prompts/sourcing-prompt-v1.md`](prompts/sourcing-prompt-v1.md))
+ fit rubric ([`prompts/fit-scoring-rubric-v1.md`](prompts/fit-scoring-rubric-v1.md)). Stored append-only
in `sourcing_doc`. UI = one "Sourcing controls" `.panel` in the Prospect list: version chips + two
`.textarea` editors ("Save as vN+1") + "Run sourcing round" + a round-history `.tbl` (Round · Prompt v ·
Candidates · Passed fit · Accepted · $/accepted · Date).

### Cross-phase
- **From A:** the guard scopes every new table; `/clay/results` (SCALE) is a route on the `$default`
  proxy; **MVP adds ZERO AWS resources;** SES production access not needed in C.
- **From B:** `ResearchSpec` v1 is the targeting source; exclusion lists + attestations promote to the
  suppression path; the B3 adapter + `llm_call` + `prompt_version` are the loop's engine (C adds
  purposes, not plumbing). **ICP validation:** B emits `icp_suggestions`; C makes it data-driven once
  enriched (paying-customer centroid vs stated ICP).
- **To D:** `fit_reason` is **client-facing copy** on the approval page; `prospect` stays clear-text (masking is D).
- **To E:** `outreach_outcome` (schema in C1, written by E) closes the self-improve loop; the fit bar is
  a deliverability control. **Start domain warm-up during C** (already running).
- **To F/billing:** C4's $3/prospect overage writes the first `LedgerEntry` rows (SCALE).

### Tasks (`[MVP]` builds/tests on **Clay free**, runs real volume on **Launch**; `[SCALE]` at Growth — see tier strategy above)

**C0 — Gates (no code).**
1. ✅ **[MVP] 👤 Founder: ONE generic enrichment table — BUILT & VERIFIED 2026-06-19.** Table
   `holdslot-enrichment` (workspace 1216451): webhook source + Work Email waterfall (Findymail-validated)
   + Enrich person + Enrich Company; **enrichment runs unconditionally** (the "only run if empty" gates
   were turned OFF — credit conservation is dedup-based, see [`data-schema.md`](data-schema.md)); **auto-dedupe
   on `identity_key`, keep-oldest**. Secret `holdslot/prod/clay` holds `inbound_webhook_url`, `table_id`,
   `webhook_authentication_token` (push auth = header `x-clay-webhook-auth`; the old `api_key` is stale).
   Live test confirmed: push 200, dedupe to 1 row, email/title/industry/size enriched. CSV column contract
   locked in [`data-schema.md`](data-schema.md): `email_valid` ← the `Validate Findymail` column (unhide to
   export), `seniority` ← input `target_seniority`. **C0.1 fully complete.**
2. ✅ **[MVP] Fit-scoring rubric v1 — DONE & locked** ([`prompts/fit-scoring-rubric-v1.md`](prompts/fit-scoring-rubric-v1.md)):
   gates → 4 dims (Company 40 / Persona 30 / Timing 20 / Data 10) → tiers (Strong ≥75 / Good 55–74 /
   Moderate 40–54 / Below <40). `fit_reason` client-readable.
3. ✅ **[MVP] Sourcing prompt + skill v1 — DONE & locked** ([`prompts/sourcing-prompt-v1.md`](prompts/sourcing-prompt-v1.md)):
   mirror of the rubric; cites evidence; never emits contact data.
4. ✅ **[MVP] Promote the exclusion fields (incl. `doNotContact`)** from Brief JSONB to the validated
   suppression path — **BUILT** (`prospects/suppression.py::extract_exclusions`: parses
   `excludeCustomers`/`excludeDeals`/`competitors`/`doNotContact` text + spec `exclusions` →
   normalized domain/email/linkedin-slug sets). Keep `technographics.enabled:false` at dogfood.
5. **[MVP] Discovery decision (locked):** HoldSlot discovers (AI loop + spec); **Clay enriches only** —
   no per-client in-app search config. *(Optional one-time Clay Find Companies for the dogfood seed.)*
6. **[SCALE] Launch → Growth gates** (only at the Growth move-trigger — see tier strategy): verify the
   HTTP API output column in-app, size + re-cost the plan, choose **BYOK** providers + capture keys,
   `verify_keys --strict clay`.

**C1 — [MVP] Schema + migration ✅ BUILT (dev).** Migration `0005_phase_c` + ORM in
`apps/api/app/models.py`: `prospect` (with **`identity_key` + `last_enriched_at`** — the future
`person` seam; unique `(tenant_id, identity_key)` makes re-import idempotent), `research_run`,
`sourcing_doc` (**seeds v1 of both prompt files** for tenant #0 in the migration). All carry
`tenant_id`; A4 scopes them. `person`/`enrichment_request` documented as the additive SCALE step, not
built. **DoD:** revision chain verified (`0004 → 0005` head); up/down + idempotent re-import to verify
against `dev` Aurora when the migration runs.

**C2 — [MVP] Suppression gate + programmatic push to Clay ✅ BUILT (dev).** Suppression =
`prospects/suppression.py::suppress` (a **pure function**: exclusions + `doNotContact` + dedupe on
`identity_key` + already-enriched `seen_keys`; each drop carries an audit reason). `POST
/{client}/icps/{id}/research` → assemble rows → **suppress before any push** → `prospects/clay.py`
pushes survivors to the one webhook tagged `run_id`+`identity_key` (**no tenant**; throttled under
≤10 rows/s; header `x-clay-webhook-auth`). **DoD met:** gate unit-tested independently of transport
(`test_prospects.py`); suppressed/duplicate never pushed. *(A live push to Clay still to run.)*

**C3 — [MVP] CSV ingest + fit scoring ⭐ ✅ BUILT (dev).** `POST /{client}/prospects/import` (base64 or
raw CSV) → `prospects/clay.py::parse_export_csv` parses **by header name** (order-independent) against
the locked column contract + coalesces gate/output → match/upsert on `(tenant, identity_key)` → C2
exclusion re-check → `prospects/fit.py::score` runs **`prospect_fit` via the B3 adapter**
(`qwen/qwen3.5-flash`, `temperature=0`, thinking disabled, strict json_schema, per-purpose routing); the
LLM returns the rubric line-items, **total + tier collapsed deterministically server-side** (thresholds
are policy) → write `fit_score`/`fit_tier`/`fit_components`. No-email rows gate out without an LLM call.
Synchronous; no SQS. **DoD met:** CSV parse + deterministic collapse unit-tested; re-import idempotent
(unique key); each score writes `llm_call` with the rubric version. **[SCALE]** swap *output transport
only*: HTTP API column → `POST /clay/results` (+SQS+S3) feeding the **same** suppression + scoring code.

**C4 — [MVP] Usage tracking + per-source cost scoreboard ✅ BUILT (dev).** `GET
/{client}/research-runs` returns the round history with **derived `cost_per_accepted`** from
`research_run` (rows_pushed/accepted, cost) — observational at free volume, no separate table (the rollup
is the post-MVP consolidation task). **[SCALE]** enforce `enrichment_cap` before dispatch; meter
$3/prospect overage (`LedgerEntry`); EventBridge monthly reset.

**C5 — [MVP] AI sourcing loop v1 (human-in-the-loop) ⭐ ✅ BUILT (dev).**
`POST /{client}/sourcing-rounds` → `prospects/sourcing.py::run_round` makes one `sourcing_round` call
(**DeepSeek V4 Pro at reasoning High + OpenRouter web-search plugin** via B3, per-purpose routing) with
Brief + ResearchSpec + a seed sample (existing Strong/Good prospects) + the current sourcing prompt + an
exclusion summary → candidates **with evidence URLs** → `validate_candidates` (deterministic liveness:
domain + person + ≥1 cited URL) → **C2 suppression** → land as `ai_loop · pending_review`. `POST
/{client}/prospects/accept` pushes accepted ones **through the same C2 path**; they return scored via the
C3 import. `GET`/`POST /{client}/sourcing-docs` = the versioned prompt/rubric editor (append-only
vN+1). **DoD met:** a round yields deduped, evidence-gated candidates traceable to prompt+rubric versions
(validate/map unit-tested). **Simplification (logged):** the `qwen3.5-flash` evidence re-check on
survivors is deferred — the deterministic liveness gate covers the gross cases; it's the next increment.
**[SCALE]** the round-trip becomes hands-off via the HTTP API callback.

**C6 — [MVP] Wire the Workspace Prospect list + acceptance ✅ BUILT (dev).** `apps/web` Prospect List
tab is now live (`lib/api.ts` Phase C client + `workspace/page.tsx`): live table (search + ICP / source /
fit-tier / status filters, **Source ICP** column, **Source chip Clay/AI**, **fit tier + reason**,
select → create batch, **Accept selected (AI)**) + **Import Clay CSV** control + the **Sourcing
controls** panel (prompt/rubric version chips + two `.textarea` editors saving vN+1 + **Run sourcing
round** + the round-history `.tbl` scoreboard) — existing classes, no new CSS. Build + typecheck + lint
green. **DoD:** both sources render with fit context and survive reload; founder runs the full loop end
to end once the migration is on `dev` → tick **S2**.

**Critical path:** C0 → C1 → C2 → C3 → {C4} → C5 → C6. C5 **reuses** C2/C3 (one suppression gate, one
scoring door). **The MVP risk is operational** (the one Clay table + a clean CSV contract), not code — the
spine (adapter, telemetry, tenant guard, proxy) already exists. **MVP cost:** Clay **Launch ~$185/mo**
(free tier was proof-only) + LLM <$10/mo. **The MVP→Growth seam is the ingest transport only**
(CSV → callback) + BYOK, with suppression / dedupe / scoring / schema / UI identical across the swap.

### Post-build review — fixes applied (2026-06-19) ✅ FINALIZED

A deep logic + code review of the C0.4→C6 diff surfaced a credit-leak / data-integrity cluster around
the push/accept paths and a dead C4 KPI. All high- and medium-severity findings were fixed; tests
(37 passed / 7 DB-skipped), web typecheck, and ruff are green.

- **Credit double-spend closed (the core risk).** A C2 push now **records each pushed identity as a
  `prospect` row immediately** (`status=pushed`) — the DB is the system of record, so a paid push is
  visible to `_seen_keys` *before* the CSV round-trips back. This shuts the window where a re-push or an
  AI round in between paid Clay twice. Import upserts those rows on `(tenant, identity_key)`.
- **`accept` no longer creates zombies or double-pays.** It dedupes against **already-pushed**
  identities (`_seen_keys(include_pending=False)` — so the very rows being accepted aren't mistaken for
  dups of themselves), and **only survivors are marked `accepted` + pushed**; suppressed-on-accept rows
  become `suppressed`, never stranded as un-enriched "accepted".
- **C4 scoreboard made real.** Per-call `cost_usd` now flows `StructuredResult → fit.score / sourcing →
  research_run.cost_usd` (accumulated for import, set for a sourcing round). `cost_per_accepted` is a
  live number, not always-null. Re-imports skip re-scoring, so cost isn't double-counted.
- **Import accounting corrected.** `rows_accepted` counts **only scored rows** (gated/errored rows no
  longer inflate it); gated no-email rows get their own **`Gated`** tier bucket (not conflated with a
  genuine "Below"); a re-import of an unchanged, already-scored row **skips the paid LLM call**.
- **Spend/config endpoints gated to `owner`** (research, import, sourcing-round, accept, sourcing-docs);
  reads stay any-member. The dogfood operator is the tenant owner (signup → owner), so no lockout.
- **`identity_key` hardened:** the `dlf:` key now requires **both** first and last name (a bare
  `dlf:dom|last|` over-merged same-surname people and split named-vs-unnamed records) → falls through to
  email.
- **Frontend race + selection bugs fixed:** a client-switch generation guard (`clientRef`) drops stale
  async reloads onto the wrong client; reload failures **surface a toast instead of silently blanking
  the list**; `Accept` has an in-flight guard against double-submit; `accept` / `create batch` act on the
  **full selection**, not just the filtered view.

**Deliberately deferred (noted, low-risk at MVP scale):** SAVEPOINT-per-insert against the unique
constraint (single-operator concurrency ≈ nil; would need verifying Data-API SAVEPOINT support);
a frontend `seed_limit` control (backend default = 20).

#### Review round 2 — hardening + simplification (2026-06-19) ✅

A second multi-angle review (correctness + simplify) of the same diff. Confirmed bugs fixed; two
flagged items verified as false positives (kept as-is with a note); tests/typecheck/ruff green.

- **Partial-push double-pay closed (was deferred).** `clay.push_rows` now returns the rows Clay
  *accepted* and raises `ClayPushError` carrying what landed *before* a mid-batch transport failure.
  A new `_push_to_clay` helper records exactly those accepted identities (and commits them) before
  surfacing the 502 — so a retry never re-pays Clay, and a row that never reached Clay is never
  stranded. `run_research` and `accept` share this one path.
- **`accept` ordering fixed (real money/state bug).** It now pushes to Clay **before** persisting
  status. Previously `accepted`/`suppressed` were committed first, so a 502 left rows permanently
  `accepted`-but-never-enriched and un-re-acceptable (the retry only matches `pending_review`). Now a
  push failure leaves un-landed survivors as `pending_review` (re-acceptable). Also dropped a
  non-tenant-scoped run re-`SELECT` (uses the in-session run object).
- **Import is now atomic.** Removed the per-row `db.commit()` (≈1 commit/row → 1 per import) and the
  N-query attribution loop (→ one `run_id.in_(…)` update). A mid-loop crash rolls back cleanly; a
  re-import (idempotent) redoes it without re-paying for unchanged rows.
- **Re-score guard widened.** The "skip the paid LLM call" guard compared `email` only, so a richer
  re-enrichment (new title/size/industry, same email) kept a stale fit tier. It now compares the whole
  `enrichment` — unchanged → skip, any material change → re-score.
- **Sourcing-round `rows_pushed` corrected.** A sourcing round pushes nothing to Clay (that happens on
  accept), so it now records `rows_pushed = 0` instead of `len(pending)`; `rows_accepted` still carries
  candidates-surfaced for the `$/surfaced` denominator.
- **Frontend client-switch hardened.** The hydrate effect now **resets selection + filters** on a
  client switch (a stale `fIcp`/`checked` leaked across clients, hiding rows / feeding accept) and
  **surfaces load errors via toast** instead of `.catch(()=>[])` silently blanking the list. Added a
  5 MB import-CSV size guard (large Clay exports). 
- **Simplified `router.py`.** One `_latest_spec`/`_latest_brief` pair replaces four hand-rolled "latest
  version" queries; import fetches brief+spec once; a shared `Candidate.to_enrichment` /
  `from_enrichment` mapper replaces four drifting enrichment-dict copies (and fixed an asymmetry where
  accept read back `linkedin_url`/`email` that sourcing never wrote).

**Verified false positives (kept):** identity-key "flip" on re-enrichment — `identity_key` is our
stamped correlation column that Clay echoes back, not recomputed on ingest, so no duplicate row. The
`_decode_csv` raw-vs-base64 heuristic — base64 has no comma/newline, so a real CSV always fails
`validate=True` and is returned raw; misdetection is not constructible. `cost_per_accepted` precision —
already server-rounded to 4dp and usually sub-cent, so it's shown raw (a `toFixed(2)` would mask it as
`$0.00`). **Removed (2026-06-20):** `credits_used` — Clay exposes no API for per-run enrichment-credit
cost (UI dashboard only; an API is an open community feature request), so the field was dropped from the
model, schema, router, migration 0005, and frontend type rather than left as a permanently-null column.
The operator reconciles Clay credit spend manually from the Clay dashboard; `cost_usd` (LLM spend) stays
live. Also: the AI-loop **seed-limit** is now a frontend control (default lowered 20 → 10).

**Fixed (2026-06-20) — run-attribution double-count:** a prospect is now owned by the run that *first*
landed it (`prospect.run_id` is set once and never reassigned on re-import), and each run's
`rows_accepted` is recomputed from the source of truth (its owned, currently-`scored` prospects) rather
than from a per-import delta. A re-import — same run or under a new `run_id` — now converges instead of
tallying one identity under two runs. Scoring `cost_usd` rolls up to the owning run too, so
`cost_per_accepted` stays coherent. **No remaining known C4 scoreboard issues.**

### Operational sign-off — what's left to tick S2 (not code)

The Phase C *code* is built, reviewed (2 rounds), and green. Ticking S2 needs two operational steps,
tracked here in the Phase B style (✅ done / ⏳ pending):

- ✅ **Migration `0005` applied to `dev` Aurora — 2026-06-20.** Run over the RDS Data API
  (`alembic upgrade head`); DB at head `0005_phase_c`. Verified: `prospect`, `research_run`,
  `sourcing_doc` tables present; `research_run` carries **no** `credits_used` column (per the round-2
  removal); seed `sourcing_prompt` v1 + `fit_rubric` v1 rows present.
- ⏳ **Founder end-to-end round on Clay (free tier) — PENDING (operator action, no code).**
  **DoD:** from the live Workspace, founder runs the full loop once on real data —
  **push** suppressed identity-keyed rows to the Clay webhook → Clay **enriches** → operator **exports**
  the CSV (one click) → HoldSlot **imports** → suppress → dedupe → **fit-scores** into `prospect` →
  both Clay + AI-loop rows render in the Prospect list with Source + fit context and survive reload, and
  the C4 scoreboard shows real `cost_usd` / `cost_per_accepted`. Clay credit spend reconciled by hand
  from the Clay dashboard (no API). Free tier (200 rows / 100 credits) is enough to prove the loop.
  *Operator pre-reqs:* unhide the Clay "Validate Findymail" column on the table; delete the `verify-c01`
  test row before the real round. **This is the last gate before S2 is ticked done.**

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
| `holdslot/prod/openrouter` | ✅ | Key valid; $50 spend cap; `default_model` set in B0 |
| `holdslot/prod/clay` | ◑ | `api_key` stored (= the **webhook auth token**, not a REST key); table/webhook fields → C0 |
| `holdslot/prod/smartlead` | ◑ | `api_key` valid; sending accounts + `webhook_signing_secret` → E |
| `holdslot/prod/google` | ✅ | SA + domain-wide delegation + Calendar + Meet REST all 200, one seat (`info@tryholdslot.com`) |

**Remaining secret fields (added at their phase):** Clay — build the free workbook + add
`table_id`/`inbound_webhook_url`/auth token (C0); BYOK keys at Growth · Web research — covered by the
OpenRouter web-search tool (DeepSeek V4 Pro) at MVP, no new secret · Smartlead — `webhook_signing_secret` + `sending_account_ids` (E) · Google — optional re-wrap of
the SA JSON.

**Account/plan decisions still open:** OpenRouter HK model access (B0 — the one true gate, done) · Clay
free vs Growth (C0) · Smartlead plan tier (E) · Workspace seat count + Meet recording tier (F) · AWS budget
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
| **Clay** | Launch | 185.00 |
| **Smartlead** | Basic (warm-up free, both inboxes fit) | 32.00 |
| **Google Workspace** | 2 × Business Starter @ $7.20 | 14.40 |
| **OpenRouter** | pay-per-use (Brief→spec, fit, drafts) | ~5–30 |
| **`getholdslot.com`** | ~$15/yr amortized | ~1.25 |
| **Aurora Serverless v2** | min ACU (near-$0 idle, ~0.5 ACU under use) | ~5–30 |
| Lambda · API GW · SES · S3 · SSM · SQS · EventBridge · CloudWatch · R53 · Amplify | | ~3–10 |

**Total: ~$280/mo typical** (low ~$246, high ~$320) · ≈ 2,180 HKD/mo at 7.8.

**Cost levers:**
- **Clay (~66% of total) is the one lever.** The real constraint is **credits** (per prospect enriched,
  not per meeting). **Free tier was proof-only (C0.1 done); the dogfood runs on Launch (~$185/mo).** At
  scale, **Growth + BYOK** (own provider keys = 0 Clay credits) is the next lever — see the Phase C tier
  strategy for move-triggers.
- **Smartlead $32 covers the whole MVP**; **Workspace Starter ($7.20) suffices** (bump to Standard only for
  native Meet recording); **Stripe = $0** until a signup pays (G).
- **Honest floor before Clay Launch** (warm-up phase, no live sourcing yet): Smartlead $32 + Workspace
  ~$15 + AWS/LLM/domain ~$10 ≈ **$55–65/mo.** Once dogfood sourcing starts (Clay Launch on): **~$280/mo.**
