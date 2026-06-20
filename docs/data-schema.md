# HoldSlot — Data Schema (Clay table + internal database)

> ⭐ **This is the single source of truth for ALL data schema across the whole HoldSlot product** — the
> one Clay enrichment table and every internal Postgres (Aurora) table, all phases, built or planned. If
> any other doc (incl. [`initial-build-plan.md`](initial-build-plan.md) /
> [`backend-development-plan.md`](backend-development-plan.md)) shows a table or column differently, **this
> doc wins**, and schema changes are recorded **here first**.
>
> **A & B are built** (verified against [`apps/api/app/models.py`](../apps/api/app/models.py) + the
> Alembic migrations); **C is planned.** Research behind the Clay design:
> [`clay-architecture.md`](research/clay-architecture.md).

## The governing boundary

> **Clay is stateless enrichment compute. The HoldSlot DB is the only system of record.**

Rows flow *through* Clay (push → enrich → pull → clear); Clay holds no durable state we depend on.
Tenant ownership, dedup, suppression, fit scoring, lineage, and outreach status all live in Postgres.

| | **Clay table** | **HoldSlot DB (Aurora/Postgres)** |
|---|---|---|
| Nature | Stateless buffer / compute | Durable system of record |
| Row lifespan | Transient (cleared after ingest) | Permanent |
| Knows tenants? | ❌ (only `run_id` / `identity_key`) | ✅ `tenant_id` on every business row |
| Authoritative for | enrichment + validation only | everything else |

**Conventions (built tables):** PKs are `uuid` (`gen_random_uuid()`); `tenant_id` is a FK to `tenant`
(`ON DELETE CASCADE`) and **is the spec's `client_id`** (same value, two names); timestamps are
`timestamptz`; `created_at`/`updated_at` default to `now()` (`updated_at` via `onupdate`). Status fields
that may grow new values are **plain strings, not DB enums**, to avoid migrations.

---

# Part 1 — The Clay table (one, shared, stateless)

**One generic enrichment table, reused for all tenants / industries / runs — never cloned per client.**
(Clay has no table-creation API on any tier; agencies run 80+ clients from one table — see
[`clay-architecture.md`](research/clay-architecture.md).) Rows are pushed in via the webhook source,
enriched by the waterfall, pulled out (CSV on Free/Launch; HTTP API column on Growth), then cleared.
**It carries no `tenant_id`** — tenant fan-out is pure DB logic, which is what makes "enrich once, reuse
across N tenants" free.

**C2 push auth (verified 2026-06-19):** header **`x-clay-webhook-auth: <webhook_authentication_token>`**
to `inbound_webhook_url` — both in `holdslot/prod/clay`. The legacy `api_key` field is **stale** (not the
token for this webhook); C2 must use `webhook_authentication_token`.

### Push inputs (what HoldSlot POSTs per row → webhook source columns; all Text)
| Column | Required | Notes |
|---|---|---|
| `run_id` | ✅ | correlation → our `research_run.run_id`; never enriched |
| `identity_key` | ✅ | normalized LinkedIn slug / `domain\|last\|first` / email — the dedupe key both sides share; **auto-dedupe column** |
| `full_name` | ✅ | person name we discovered |
| `first_name`, `last_name` | optional | help providers; not in the CSV-out contract |
| `company`, `domain` | ✅ | company name + bare website domain (`acme.com`) |
| `linkedin_url` | optional | person LinkedIn, when known |
| `email` | optional | **gate** — if supplied, the Work Email waterfall is skipped (0 credits) |
| `company_industry` | optional | **gate** — if supplied, Enrich Company is skipped (0 credits) |
| `target_titles`, `target_seniority` | company-mode only | per-row params for an optional Find People column |

### As-built Clay enrichment columns (Option A — gate ≠ output; C3 coalesces)
The gate inputs (`email`, `company_industry`) and the enrichment **outputs** are **separate** columns;
C3 coalesces them on ingest (gate value wins if supplied, else the enriched value). No Clay-side
formula/rename needed.

**Run condition (decided 2026-06-19): all "only run if empty" gates are OFF — every enrichment runs
unconditionally on each pushed row** (guaranteed enrichment, simpler/reliable at dogfood volume). Credit
conservation therefore relies on **dedup, not per-row gating** (see below). The `email`/`company_industry`
columns are still optional inputs + coalesce sources, just no longer run-conditions.

| Clay enrichment | Output column(s) | Run condition |
|---|---|---|
| **Work Email** (10+ provider waterfall + Findymail validation) | `Work Email`, `Work Email Data Provider`, validation result | **always run** |
| **Enrich person** | `Title` (+ `Name`, `Org`; `Seniority` if added) | **always run** |
| **Enrich Company** | `Industry`, `Website`, `Employee Count`/`Size`, `Country`, `Locality`, `Annual Revenue` | **always run** |
| *(phone — off at dogfood)* | — | — |

### CSV export contract (verified against a real export, 2026-06-19)
Actual export header order: `Webhook, run_id, identity_key, full_name, first_name, last_name, company,
company_industry, domain, linkedin_url, target_titles, target_seniority, email, Work Email Data Provider,
Work Email, Enrich person, Name, Title, Org, Enrich Company, Name (2), Website, Employee Count, Industry,
Size, Country, Locality, Annual Revenue`. C3 ingests **by header name** (order-independent):

| CSV column(s) | → our field |
|---|---|
| `run_id`, `identity_key`, `full_name`, `company`, `linkedin_url` | (same) |
| `domain` | `domain` **and** `company_domain` (use input domain, not enriched `Website` which can be a subdomain) |
| `email` (gate) **+** `Work Email` (output) | `email` = **coalesce(gate, output)** → e.g. `snadella@microsoft.com` |
| `Work Email Data Provider` | `provider` (e.g. `Findymail`) |
| `Validate Findymail` (hidden under the email enrichment — **unhide so it exports**) | `email_valid` |
| `Title` | `title` |
| `target_seniority` (input) | `seniority` (Enrich person has no Seniority output — the pushed `target_seniority` is the source) |
| `Size` (band) / `Employee Count` (int) | `company_size` |
| `company_industry` (gate) **+** `Industry` (output) | `company_industry` = **coalesce(gate, output)** |
| `Country`, `Locality`, `Annual Revenue`, `Website`, `Employee Count` | → `enrichment` JSONB (extras) |
| `Webhook`, `Enrich person`, `Enrich Company`, `Name`, `Name (2)`, `Org`, `first_name`, `last_name`, `target_titles` | **ignored** (group cells / duplicates / unused inputs) |

> **`email_valid` source:** the Work Email waterfall's **`Validate Findymail`** column (hidden by default
> under the email enrichment). Unhide it so it lands in the CSV export; C3 reads it directly as `email_valid`.
> **`seniority` source:** the pushed input **`target_seniority`** (there is no person-level Seniority
> enrichment output).

**Credit discipline (dedup-based, since per-row gates are OFF):** the safeguard against paying twice is
**deduplication, not gating** —
1. **HoldSlot dedup *before push*** (primary): an identity already in the `person` cache / existing
   prospects is never pushed → 0 credits.
2. **Clay auto-dedupe on `identity_key`, keep-oldest** (backstop): a re-pushed identity reuses the
   already-enriched row instead of enriching a new one.

Work Email validates per-provider (Findymail, Conservative). *Trade-off of gates-off:* a row that
slips past both dedup layers is re-enriched (a few cents); acceptable at dogfood volume. Re-enable the
`only run if empty` gates at scale if credit spend warrants.

**Lifecycle / scale:** webhook submissions cap at **50k lifetime per webhook** (non-resettable) → when
near, add a **new webhook to the same table** and update the one config value (rare, volume-driven).
Free ≤200 rows/table, Launch/Growth ≤50k; Enterprise adds auto-delete (passthrough). The table is a
buffer, so rows are cleared after ingest and the caps rarely bite.

**Per-tier transport (downstream code is identical across all):**

| Tier | Rows IN | Rows OUT |
|---|---|---|
| Free / Launch | programmatic webhook push | **manual CSV export** → `POST …/prospects/import` |
| Growth | same | **HTTP API column** auto-POSTs each `email_valid` row → `POST /clay/results` (+SQS) |
| Enterprise | same | + auto-delete / passthrough for unlimited throughput |

---

# Part 2 — Internal database

## Phase A (S0) — Identity & tenancy core ✅ BUILT
Migration `20260611_0001_baseline` (+ `0002_seed`). Identity tables are **global**; a user joins tenants
via `membership`. Today `tenant` holds exactly HoldSlot (#0); a paying client later is one `INSERT`.

### `tenant`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `slug` | varchar(63) **unique** | drives `holdslot.com/<slug>` |
| `name` | varchar(255) | |
| `status` | enum `tenant_status` (`active`/`suspended`) | |
| `created_at`, `updated_at` | timestamptz | |

### `app_user`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `email` | varchar(320) **unique** | stored lowercase (no citext) |
| `password_hash` | varchar(255) | argon2 |
| `full_name` | varchar(255) nullable | |
| `status` | enum `user_status` (`active`/`disabled`) | |
| `last_login_at` | timestamptz nullable | |
| `created_at`, `updated_at` | timestamptz | |

### `membership` — the tenant↔role join (build single, design multi)
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → `app_user` (CASCADE) | idx |
| `tenant_id` | uuid FK → `tenant` (CASCADE) | idx |
| `role` | enum `membership_role` (`owner`/`member`) | role is on the membership, not the user |
| `created_at` | timestamptz | |
| | | **unique(`user_id`,`tenant_id`)** |

### `refresh_token`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → `app_user` (CASCADE) | idx |
| `token_hash` | varchar(64) **unique** | |
| `expires_at` | timestamptz | |
| `revoked_at` | timestamptz nullable | |
| `created_at` | timestamptz | |

### `password_reset`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → `app_user` (CASCADE) | idx |
| `token_hash` | varchar(64) **unique** | |
| `expires_at` | timestamptz | |
| `used_at` | timestamptz nullable | one-click reset link flow |
| `created_at` | timestamptz | |

## Phase B (S1) — Targeting: Brief & ICP → ResearchSpec ✅ BUILT
Migrations `20260612_0003_phase_b_targeting` (+ `0004_icp_suggestions`). Form documents are **opaque
JSONB** (a form change is a frontend edit, never a migration); `research_spec` is the locked v1 Clay
contract, append-only versioned, each linked to the `llm_call` that produced it.

### `brief` — one per tenant
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK (CASCADE) | **unique per tenant**; idx |
| `data` | JSONB (default `{}`) | the opaque form document |
| `created_at`, `updated_at` | timestamptz | |

### `icp` — many per tenant
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK (CASCADE) | idx |
| `name`, `tag` | varchar(255) | card header |
| `data` | JSONB (default `{}`) | the opaque form document |
| `created_at`, `updated_at` | timestamptz | |

### `llm_call` — the one-seam LLM telemetry (append-only)
Written by the B3 OpenRouter adapter on **every** call; every later AI feature (fit scoring, sourcing,
recaps) writes through it.
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK (CASCADE) | idx |
| `purpose` | varchar(64) | `brief_structure` today; `prospect_fit`/`sourcing_round`/… in C; idx |
| `model` | varchar(128) nullable | model actually served |
| `prompt_version` | varchar(64) nullable | the loop's instrument |
| `status` | varchar(32) | `ok`/`parse_error`/`timeout`/`error` (string, not enum) |
| `input_tokens`, `output_tokens` | int nullable | |
| `cost_usd` | numeric(14,8) nullable | OpenRouter usage/cost |
| `latency_ms` | int nullable | |
| `retries` | int (default 0) | |
| `raw` | JSONB nullable | raw completion — top debugging signal; parse failures recorded before retry |
| `created_at` | timestamptz | |

### `research_spec` — append-only versioned v1 Clay contract
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK (CASCADE) | idx |
| `version` | int | **unique(`tenant_id`,`version`)**; re-run inserts the next version |
| `spec` | JSONB | v1 targeting (company_search/people_search/exclusions + server-merged credit policy) |
| `gaps` | JSONB (default `[]`) | value-loop prompts |
| `icp_suggestions` | JSONB (default `[]`) | proposed ICPs from the existing-customer list (added `0004`) |
| `model` | varchar(128) nullable | |
| `llm_call_id` | uuid FK → `llm_call` (SET NULL) nullable | traces spec → exact model/cost/raw output |
| `created_at` | timestamptz | |

## Phase C (S2) — Prospects: Clay seed + AI sourcing loop ✅ MVP BUILT (dev)
Follows the same conventions; all carry `tenant_id` (= `client_id`), scoped by the A4 guard. **MVP ships
the three tables below (migration `0005`, verified against `apps/api/app/models.py`); the two SCALE
tables are the additive multi-tenant step (no rewrite), not built.**

### `prospect` ⬜ MVP — per-(identity × tenant) targeting record
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK (CASCADE) | idx |
| `icp_id` | uuid FK → `icp` (SET NULL) nullable | which ICP sourced it |
| `spec_version` | int nullable | `research_spec.version` used |
| `run_id` | uuid/str | = `research_run.run_id` + Clay correlation |
| `identity_key` | varchar **idx** | normalized domain+name / LinkedIn / email — **dedupe + future `person` FK seam** |
| `enrichment` | JSONB | raw enriched row (the CSV/callback row); no S3 at MVP volume |
| `email_valid` | bool | |
| `fit_score` | int nullable | |
| `fit_tier` | varchar | Strong/Good/Moderate/Below |
| `fit_components` | JSONB | the 12 rubric line-items + reason tags; `fit_reason` is client-facing copy (→ Phase D) |
| `source` | varchar | `clay` \| `ai_loop` (origin, not transport) |
| `source_lineage` | JSONB | round + prompt/rubric versions |
| `status` | varchar | pipeline status (string, not enum) |
| `outreach_outcome` | varchar nullable | null until Phase E writes it (closes the self-improve loop) |
| `last_enriched_at` | timestamptz nullable | TTL-gates re-enrichment (~90d); Clay's durable-column pattern |
| `created_at` | timestamptz | |
| | | dedupe: re-import the same `identity_key` is idempotent |

### `research_run` ⬜ MVP — one per sourcing round / import
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK (CASCADE) | idx |
| `run_id` | uuid/str **unique** | the Clay correlation handle |
| `spec_version` | int nullable | |
| `icp_id` | uuid FK → `icp` nullable | |
| `source` | varchar | `clay` \| `ai_loop` |
| `prompt_version`, `rubric_version` | varchar nullable | which `sourcing_doc` versions ran |
| `rows_pushed`, `rows_accepted` | int | the loop's scoreboard |
| `cost_usd` | numeric nullable | LLM spend → per-source $/accepted (Clay credit cost not stored — no Clay API) |
| `created_at` | timestamptz | |

### `sourcing_doc` ⬜ MVP — append-only founder-edited prompts
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK (CASCADE) | idx |
| `kind` | varchar | `sourcing_prompt` \| `fit_rubric` |
| `version` | int | **unique(`tenant_id`,`kind`,`version`)**; append-only |
| `body` | text | seed v1 from `docs/prompts/*-v1.md` in the migration |
| `created_at` | timestamptz | |

### `person` ⬜ SCALE — tenant-AGNOSTIC enrichment cache (the enrich-once seam)
Built when the 2nd tenant lands. Lets a prospect wanted by N clients be enriched once (one Clay push,
paid once) and referenced by N `prospect` rows.
| Column | Type | Notes |
|---|---|---|
| `identity_key` | varchar **PK** | the shared key |
| `email`, `phone`, `title`, `seniority` | varchar nullable | person enrichment |
| `company_domain`, `company_industry`, `company_size` | varchar nullable | company enrichment |
| `providers` | JSONB | waterfall provenance |
| `last_enriched_at` | timestamptz | re-enrich TTL |
| `created_at`, `updated_at` | timestamptz | |
| | | on SCALE, `prospect` gains FK `identity_key` → `person` and drops the embedded `enrichment` |

### `enrichment_request` ⬜ SCALE — the fan-out + dedup-before-push map
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `run_id` | uuid/str | |
| `identity_key` | varchar FK → `person` | |
| `tenant_id` | uuid FK (CASCADE) | which tenant(s) requested this identity |
| `requested_at` | timestamptz | |
| `status` | varchar | pending/enriched/skipped(cache-hit) |

---

## Migration history (Alembic, `infra/alembic/versions/`)
| Revision | Phase | Tables / change |
|---|---|---|
| `20260611_0001_baseline` | A | `tenant`, `app_user`, `membership`, `refresh_token`, `password_reset` |
| `20260611_0002_seed` | A | seed HoldSlot tenant #0 + two founder owners |
| `20260612_0003_phase_b_targeting` | B | `brief`, `icp`, `llm_call`, `research_spec` |
| `20260617_0004_icp_suggestions` | B | `research_spec.icp_suggestions` column |
| `20260619_0005_phase_c_prospects` ✅ | C | `prospect`, `research_run`, `sourcing_doc` (MVP) + seed `sourcing_doc` v1 (sourcing prompt + fit rubric) for tenant #0 from `docs/prompts/*-v1.md` |
| *(later)* `phase_c_person_cache` | C | `person`, `enrichment_request` (SCALE) |
