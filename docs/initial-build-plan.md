# HoldSlot — Initial Build Plan (dogfood MVP)

> **Status: Phase A (S0) + Phase B (S1) are built & live on the `dev` API (Lambda v8); S1 awaits only
> the web deploy to Amplify `dev` + founder acceptance test. Phase C (S2, Clay) is next.**
> This is the **first build**: make HoldSlot's own product real enough that the company runs its own
> outbound on it and lands its first signups. Scoped cut of the full spec in `backend-development-plan.md`.

## Scope & Definition of Done

- **Scope:** build the **single-tenant outbound → booked-meeting loop** and point it at HoldSlot's own
  market. **HoldSlot is tenant #0.** Defer all multi-client *operations* (onboarding, self-signup, billing,
  protection, analytics) — but **design the data model multi-tenant + role-aware from day 0** (see
  *Tenancy & access model* below). Build single; design multi.
- **DoD:** the company uses the flow to land **6 signups in half a year** — i.e. §11's **H1 (Oct'26 →
  Mar'27)** target. The dogfood run *is* H1.
- **Timeline:** build **now → Sept'26** (~4 months); loop runs live **Oct'26 → Mar'27**.
- **Already live (not in scope to build):** the marketing site + all 8 mock UI pages on Amplify
  (account `138743894336`). This build replaces the mock data behind the loop's screens with a live API.
  The mock UI now **defaults to HoldSlot as the active tenant** (slug `holdslot`), so the dogfood loop
  runs on our own tenant from screen one (Phase A then makes that tenant real, served by the API).

**The long pole is not code.** Cold-email **domain warm-up takes ~3 weeks** and gates every meeting.
Account setup (Clay / Smartlead / Google / OpenRouter keys) is **DONE** — keys provisioned in Secrets
Manager and verified 2026-06-10 (see *Accounts & keys*). The remaining day-0 long-lead item is **domain
warm-up** — start it now, in parallel with the build.

## Tenancy & access model (build single, design multi)

This resolves the S0 auth/access decision. The principle: **seed exactly one tenant and two users now,
but make tenancy and roles first-class in the schema** so adding a different tenant with lesser access is
an `INSERT`, never a migration.

**What this build seeds and uses:**
- **One tenant — HoldSlot itself (tenant #0).** No tenant-onboarding UI, no self-signup, no per-tenant
  provisioning flow this phase. The tenant row exists; it is created by seed/migration, not by a feature.
- **Two user accounts — the two founders.** Both are **owners** of tenant #0 with **complete access**
  (every domain object, every action). Login is JWT (argon2 password hashes + refresh) per the stack.
- Clients (prospects' companies) still **do not log in** this phase — they use the existing tokenized
  approve/book/feedback links, signed by the separate expiring-token mechanism, not these user JWTs.

**What the schema must support from day 0 (designed now, not exercised yet):**
- **Every domain row is tenant-scoped** — carries a `tenant_id`; all queries filter by it. No table
  assumes a single tenant. (HoldSlot-as-a-client and a future paying client are the same shape.)
- **Users belong to tenants via membership, with a role** — a `User` ↔ `Tenant` join carrying a role,
  not a role column hardwired on the user. A user can later belong to one tenant with a limited role
  without touching other tables.
- **Roles are an enumerable set, checked on every request** — at minimum `owner` (the founders: full
  access) and at least one **lower-privilege role** reserved for the future tenant/user (e.g.
  `member`/operator with scoped access). The future "another tenant + user with different access" the
  product needs is expressed purely as: new tenant row + new user + membership with a non-owner role.
- **Access control = tenant scope × role**, enforced centrally (a dependency/guard), so a request can
  only touch rows of a tenant the user is a member of, and only actions the role permits.

**Where things live (don't conflate):**
- Signing keys for the login tokens → `holdslot/prod/app` secret (`jwt_signing_key`, `jwt_refresh_key`).
  One shared pair for the whole app; not per-user.
- User records, **argon2 password hashes**, tenant rows, memberships, and roles → **Aurora** (the DB).
  Adding/removing users or changing permissions is DB data; it never touches the secret.

**Concrete S0 acceptance:** both founders log in and have full access to tenant #0; the schema can
represent a second tenant whose user has a non-owner role **without any schema change** (verified by a
seed/test fixture, not by building the onboarding flow).

## Build vs. skip

| Capability | This phase |
|---|---|
| Auth (JWT, 2 founder accounts) · **multi-tenant + role-aware schema** (seed 1 tenant) · deploy | **BUILD** |
| Brief → ICP → ResearchSpec (LLM via OpenRouter) | **BUILD** |
| Prospect storage + filter/select | **BUILD** |
| **Clay connection** — push ResearchSpec → table (webhook-in) → callback → ingest enriched prospects | **BUILD** |
| Batch + internal approve/select | **BUILD** |
| **Smartlead connection** — batch → campaign, leads, A/B/C sequences, send controls, open/reply sync, reply-to-thread | **BUILD** |
| **Meeting connection** — booking link + Google Calendar event + Meet link + invites; capture held + duration via Meet REST | **BUILD** |
| Sending domains + warm-up | operate (manual setup — start now) |
| AI reply drafting · summaries/transcripts · feedback links · anti-theft masking · billing/Stripe · overview analytics · multi-tenant **operations** (onboarding/self-signup — schema is multi-tenant-ready, see *Tenancy & access model*) · automated SmartSenders | **SKIP** → return when onboarding paying signups |

## Phases (dependency- and priority-ordered)

| # | Phase | Must-build | Depends on | Priority | Phase DoD |
|---|---|---|---|---|---|
| **A** | Foundation (S0) | Founder login (JWT) for **2 founder accounts**; seed **HoldSlot tenant #0**; **multi-tenant + role-aware schema** (tenant-scoped rows, User↔Tenant membership w/ role); Aurora DB + deploy; console shell on live data | — | **P0** | Both founders log in w/ full access; schema admits a 2nd tenant/non-owner role w/o migration |
| **B** | Targeting (S1) | Brief intake → OpenRouter structures a ResearchSpec; ICP record | A | **P0** | ResearchSpec saved, Clay-ready |
| **C** | Prospects + Clay (S2) | ResearchSpec → Clay table → callback → ingest `Prospect` rows w/ fit context; filter/select | B · Clay | **P0** | Enriched prospects flow in automatically |
| **D** | Batch (S3 minimal) | Batch from selected prospects, mark approved internally. No external masked page | C | **P1** | Approved batch ready to send |
| **E** | Outreach + Smartlead (S4) | Batch → Smartlead campaign; leads + A/B/C sequences; send controls; webhook sync → `OutreachEvent`; reply-to-thread | D · warmed domains · Smartlead | **P0** | Live campaign sending; replies tracked in-app |
| **F** | Book + meeting (S6 minimal) | Booking link + slot picker → Google Calendar event + Meet link + invites; capture held + duration via Meet REST | E · Google Workspace | **P0** | Prospect self-books a Meet call; held/duration recorded |
| **G** | Run & close (human) | Meeting → founder pitches the live product → close → onboard signup = create their tenant (reuse A) | F | **P0** | **6 signups over H1** |

**Critical path:** A → B → C → D → E → F → G.
**Parallel from day 0 (long-lead):** domain warm-up · ~~account setup~~ **(keys DONE 2026-06-10)** · ICP + cold-email copy.

## Phase A — Foundation (S0): step-by-step (planning, pre-code)

Ordered tasks to take S0 from empty placeholders (`apps/api/`, `infra/`) to **both founders logging
into live `/holdslot/overview`**, on a schema that already admits a second, lesser-privileged tenant.
No app code is written until A0's decisions are locked. Grounded in the locked spec
(`backend-development-plan.md` §2 architecture, §6 decisions 1–11, §8 UI map, §9 repo layout).

> **Status (2026-06-11): A0–A6 BUILT & VERIFIED on the `dev` environment.**
> Infra applied via Terraform (Aurora SLv2 + Data API, Lambda+SnapStart, HTTP API + custom domain
> `api.tryholdslot.com` w/ ACM, SES, budget); schema + seed migrated to Aurora; auth/clients API +
> central guard deployed to Lambda (alias `live`) and smoke-tested through the custom domain; UI
> `/login` cut over to the live API; the console sidebar shows the signed-in user from live `/me`;
> server-side CORS allows the Amplify + localhost origins. Acceptance: both founders log in as owners;
> an ephemeral 2nd tenant + `member` role scopes correctly with no schema change; `verify_keys --strict`
> green for app + google. 10/10 backend tests pass; ruff/black clean; `terraform plan` shows no drift.
>
> **Known follow-ups (none block Phase B; tracked here so they aren't lost):**
> 1. **SES — DONE for dogfood.** DKIM (3 CNAMEs) + DMARC published in Route 53 and **SES-verified**
>    (DKIM=SUCCESS, Verified=true, 2026-06-11); `no-reply@tryholdslot.com` sends. The founder
>    **password-reset is a one-click link flow, live on `dev`** (forgot → emailed link →
>    `/login?reset=<token>` set-new-password screen → sign in). Works in-sandbox because founder
>    recipients are at the verified domain. **Deferred:** custom MAIL FROM (SPF alignment) and
>    production-access / sandbox-exit — needed only for client-facing mail at Phase C+.
> 2. **Prod environment** — single `dev` env today; Terraform is workspace-parameterised, so prod is
>    a later `terraform workspace new prod`, not a rewrite.
> 3. **CI/CD** — deploy is the manual one-command `apps/api/scripts/build-and-deploy.sh`; add a
>    pipeline when Phase B churn justifies it.
> 4. **Aurora scale-to-zero vs 30s Lambda timeout** — a cold resume can approach the timeout on the
>    first request after idle (`ensure_awake` retries). For prod, set min capacity ≥ 0.5 ACU or raise
>    the Lambda timeout.
> 5. **S3 state bucket** — bucket-level public-access-block not set by Terraform (private by default);
>    add the explicit block when prod hardening lands.
> 6. **OpenRouter `default_model`** — set in **Phase B/B0** when the LLM adapter lands (see below).
> 7. **Refresh-token rotation** does not re-check `UserStatus` (only login/`get_current_user` do);
>    harmless today (no deactivation flow), revisit if/when accounts can be disabled.

**Simplification principle (simple now, scalable later).** Phase A ships the *smallest* foundation that
makes the dogfood loop real, with **no design choice that has to be undone to add a paying client**.
Concretely: **one environment** (`dev`) to start — not dev+prod workspaces — but the Terraform is
workspace-parameterised so prod is a later `terraform workspace new prod`, not a rewrite; **one modular
FastAPI service** (split into microservices only if scale ever demands); **manual one-command deploy**
now (full CI/CD deferred to Phase B when there's churn to justify it); **JWT** auth (Cognito only if
SSO/MFA is ever needed). The two things we *do not* shortcut, because retrofitting them is expensive:
`tenant_id` on every row + a single central access guard (A3/A4).

**A0 — Inputs (LOCKED 2026-06-11, no code).**
- **Region → us-east-1** (matches Secrets Manager + Amplify).
- **Founders (both `owner`):** `jason.tse@tryholdslot.com`, `jason.wong@tryholdslot.com`.
- **First password → shared build-stage secret `tryholdslot1!`**, seeded as an argon2 hash. **Build
  stage only** — production forces a reset (the `PasswordReset` flow from A4 exists precisely so this
  temporary credential never reaches a real client). Never commit the plaintext; the seed reads it from
  an env var / Secrets Manager, not source.
- **Roles:** `owner` (founders, full access) + `member` (reserved lower-privilege) — enum, so a third
  role later is one value, not a migration.

**A1 — Scaffold `apps/api` + `infra` + remote state (structure only).** Per §9:
`app/{main.py, core/, domains/, integrations/}`, `pyproject.toml`, `infra/{alembic/, terraform/}` (skip
`workers/`/`webhooks/` until S2 — no async in S0). Mangum-wrapped FastAPI exposing only `GET /health`;
ruff/black/pytest. Terraform: S3 state bucket + DynamoDB lock, single `dev` workspace. **DoD:**
`GET /health` → 200 locally; `terraform plan` clean.

**A2 — Provision the S0 infra in one `terraform apply` (dev).** Aurora Serverless v2 (PostgreSQL) with
the **Data API enabled** (Lambda stays out of the VPC → SnapStart-safe, no NAT) + the **RDS-managed
master secret**; Lambda + API Gateway (HTTP API) + **SnapStart** alias; least-privilege IAM (Data API,
`GetSecretValue` on `holdslot/prod/*`, SES send); SES identity for the reset email; CloudWatch log
groups; **AWS budget alarm** (folded in here, not deferred). External keys already verified
(`holdslot/prod/*`, 2026-06-10). **DoD:** `apply` green; Lambda reachable via API GW; **Aurora
master-secret connection test passes**.

**A3 — Schema + Alembic baseline + seed (the heart of S0). ⭐** The **multi-tenant, role-aware** core:
`Tenant` (slug) · `User` (argon2 hash) · `Membership(user_id, tenant_id, role)` with `role` enum
(`owner`/`member`) · `RefreshToken` · `PasswordReset`. **Every domain row carries `tenant_id` from day
0.** Alembic baseline + a **seed migration**: HoldSlot **tenant #0** (slug `holdslot`) + the two founder
users (build-stage password hash) + `owner` memberships. **DoD:** migrations apply up/down cleanly; seed
produces the dogfood tenant.

**A4 — Core plumbing + auth/clients API (one step).** Config loader (Secrets Manager + SSM, **re-fetched
post-SnapStart-restore**, no secrets/RNG at import); Aurora Data API client; structured logging; **JWT
core** (argon2 verify, access + refresh); and the **one central access guard** — a FastAPI dependency
resolving `request → user → membership` that enforces **tenant scope × role** on every protected route.
Surface (§8): `POST /auth/login·forgot·reset` (SES) + refresh; `GET /me`; `GET/POST /clients` (scoped to
the caller's memberships). **DoD:** unit tests for token round-trip + guard (owner ✓ · non-member ✗ ·
wrong-role ✗); a founder logs in via curl and gets a membership-scoped client list.

**A5 — Cut the UI over to live auth (§8).** Point `apps/web` `/login`, the client switcher
(`lib/client.ts`), and the console-shell session at the live API via `API_BASE_URL`; replace the login
mock + default-client mock with real calls (HoldSlot tenant #0 now comes from the API, not
`DEFAULT_CLIENTS`). Deploy = one command (`terraform apply` + push Lambda version + shift alias + smoke
`GET /health`). **DoD:** logging in at `/login` lands a founder on live `/holdslot/overview`.

**A6 — Phase-A acceptance (the DoD gate).** (1) Both founders log into live `/holdslot/overview` with
full access. (2) An **ephemeral, in-test** fixture (created and rolled back inside the test — never
seeded, never a product client; the build ships with **one tenant, HoldSlot**) inserts a second tenant
whose user has a **non-owner** role and proves the guard scopes access correctly — **with no schema
change**. (3) `verify_keys.py --strict` passes for `app`, `google`, `openrouter`; Clay/Smartlead stay
`PEND` (Phases C/E). **DoD:** all three pass; tick S0 in `backend-development-plan.md`.

**Critical path:** A0 ✅ → A1 → A2 → A3 → A4 → A5 → A6. **A3 is the highest-leverage step** — it makes
"build single, design multi" real; everything downstream filters by `tenant_id` and checks role through
A4's guard.

## Phase B — Targeting (S1)

Turns a client's raw **Business Brief** into a research-ready **`ResearchSpec`** (the bridge into Clay,
Phase C) and lets the operator create/curate **ICP profiles** — wiring the Workspace *Business brief* and
*ICP* tabs to the live API. This is the **first use of the LLM** (OpenRouter). Grounded in the locked spec
(`backend-development-plan.md` §4 *S1*, §3 domain model); the UI `Brief`/`IcpFields` types in
`workspace/page.tsx` define the *form*, but the backend deliberately does **not** mirror them (see the
design rule below).

**What Phase B delivers (DoD):** a founder fills the Brief in the live Workspace → the completeness ring
reflects real saved data → "Structure" produces a saved, versioned `ResearchSpec` + gap prompts → one or
more `ICP` profiles exist. **Clay-ready; nothing is sent to Clay yet** (that's Phase C).

### Why the LLM is here — position + value loop

**Position: one job — the translator at one seam.** The Brief is free text in the client's business
language ("we sell X to teams struggling with Y"); Clay needs machine-actionable search parameters
(industries, size bands, geos, titles/seniority, technologies, trigger signals, exclusions). That
translation is otherwise **operator labour, per client, per revision** — exactly the labour a
done-for-you margin can't afford, and deterministic rules can't read free text. So the LLM sits at one
seam only: **Brief (+ICPs) in → `ResearchSpec` + gap prompts out.** In Phase B it does *not* score fit
(Phase C input), draft email (Phase E), or converse with the client.

**How it compounds (the value loop):**
1. Client states the business **in their own words** — intake stays low-friction; the form never has to
   force clients to think in Clay columns.
2. LLM structures that into a **versioned** `ResearchSpec` → Clay sources prospects (C) → outreach (E)
   → meetings (F).
3. The *same completion* returns **gap prompts** — what's missing or too vague for good research —
   pushing the client to sharpen the Brief **before** credits are spent on bad targeting.
4. Outcomes (which ICP/persona/signal actually converted) feed the next Brief/ICP revision → re-run
   Structure → **spec vN+1 targets better than vN.**

Versioned specs are the loop's **memory**: every re-run appends a new version, so targeting quality is
observable over time and a bad revision is a one-step rollback. Phase B builds arc 1–3; the loop closes
when C–F land — but versioning + gap prompts are designed in *now* because retrofitting loop memory is
expensive.

**Value math:** gap prompts protect the two most expensive downstream resources — Clay enrichment
credits and warmed-inbox sending capacity — at the cheapest possible point: a few cheap-model
completions (~$5–20/mo, §5) versus burned credits and weeks of mis-aimed sending.

### Design rule: the form will churn — the backend must not care

Assume the ~27-field Brief and the ICP form **change often after MVP**. Therefore **no field
mirroring** in the backend:

- **Brief and ICP fields are stored as one JSONB document each**, not as typed columns. Their only
  consumers are the form (round-trip, opaque) and the LLM prompt (schema-tolerant by nature) — neither
  needs the database to know field names.
- A form change costs: **a frontend edit + (maybe) one entry in the required-fields list. Zero
  migrations, zero API churn, prompt unaffected.**
- **Promote-on-demand:** the moment one field becomes load-bearing for backend *logic* (e.g. Phase C
  consumes the exclusion lists), promote **that field** to a validated path/column **then** — never
  pre-emptively.
- **Two stability profiles, deliberately different.** The Brief/ICP *form documents* churn freely
  (JSONB, opaque to the backend). The `ResearchSpec` is the opposite: a **locked v1 contract** (next
  section) — it's the interface to Clay, and Clay's consumable surface is now researched, so its shape
  is stable even while the form churns. The LLM is the shock absorber between the two: whatever the
  form looks like, the prompt's *output* schema stays the spec. Versions are **append-only** JSONB
  rows (`spec`, `gaps`, `model`, `created_at`).

**Cut from the previous Phase-B plan (YAGNI at dogfood volume):**
- ~~Mirror the ~27 `Brief` + `IcpFields` fields as a relational model~~ → JSONB documents (above).
- ~~Seed `Subscription` quota fields (`enrichment_cap`, `icp_limit`, `current_month_usage`)~~ —
  enforcement is C+/billing-era; tenant #0 runs uncapped; adding them later is one ordinary migration.
- ~~Model the ICP↔spec linkage relationally~~ — each spec version snapshots the ICP docs it used inside
  its own JSON; no join tables.
- ~~Lock the outreach-language set in B0~~ — the Brief already captures `languages[]` as data;
  localization matters when *drafting* (Phase E), not when structuring.

### The `ResearchSpec` v1 format (Clay-aligned — locked from research, 2026-06-12)

**Clay integration reality (verified against Clay docs/changelog):** Clay has **no public API to create
tables or configure Find Companies / Find People searches** — those are in-app only. The programmable
surface is: **webhook sources** (POST JSON rows into a pre-built table; note a 50k-lifetime-submissions
cap per webhook) and the **HTTP API column** (per-row POST of enriched results back to our endpoint,
with "only run if" gates). So the spec has two halves with different consumers:

- **`company_search`** → an **operator transcribes it once** into a cloned Clay template workbook's
  *Find Companies* source (~10 min; fields map 1:1 to Clay's modal). No API for this hop exists.
- **`people_search` + `exclusions`** → **fully programmatic**, riding per-row through the webhook into
  the people-build table (Find People can reference row columns dynamically).
- Enriched rows come **back** via an HTTP API column → `POST /clay/results` (Phase C), gated on
  `email_valid` so junk rows never fire the callback.

**The format (what the LLM emits, mapped 1:1 to Clay's filter taxonomies):**

```jsonc
{
  "spec_version": 1,
  "company_search": {                       // → operator → Clay "Find Companies" (in-app)
    "industries_include": [], "industries_exclude": [],          // LinkedIn industry labels
    "description_keywords_include": [], "description_keywords_exclude": [],
    "semantic_description": "",                                  // Clay AI filter — one plain sentence
    "employee_count": { "min": null, "max": null },              // free integers; no fixed bands
    "revenue_usd":    { "min": null, "max": null },
    "company_types": [],                                         // Clay enum (Privately Held | Public …)
    "founded": { "after": null, "before": null },
    "locations_include": { "countries": [], "states": [], "cities": [] },
    "locations_exclude": { "countries": [], "states": [], "cities": [] },
    "technographics": { "enabled": false, "vendors": [] },       // default OFF — 3 credits/company
    "max_results": 500
  },
  "people_search": [{                       // one entry per ICP → per-row via webhook (programmatic)
    "icp_id": "",
    "job_title_keywords": [],                                    // PRIMARY field (Clay's own guidance)
    "job_title_match_mode": "is_similar",                        // is_similar | contains | is_exactly
    "job_title_exclude": [],
    "seniority": [], "departments": [],                          // advisory — titles do the real work
    "max_per_company": 2, "max_total": 800
  }],
  "exclusions": { "domains": [], "company_linkedin_urls": [], "emails": [] },
  "gaps": [{ "field": "", "why": "", "ask": "" }]                // the value-loop prompts
}
```

**Division of labour (important):** the LLM emits **targeting only** — `company_search`,
`people_search`, `exclusions`, `gaps`. The **credit policy** (`enrichment_plan` waterfall order +
"only run if" gates, `test_batch_size` ≈ 10, per-batch caps) is **deterministic server config merged in
at save time**, never LLM-inferred — credit rules are policy, not judgment. Suppression is applied
HoldSlot-side *before* any row is pushed (a row never created costs zero credits); Clay-side exclusion
lists are the backstop. These policy knobs become real in Phase C; the spec carries them from v1 so C
is a consumer, not a redesign.

### Displaying the spec for review (UI plan — existing classes only, no new CSS)

The Workspace Brief tab already has every primitive needed; the review block reuses them verbatim:

- **Trigger:** a "Structure research spec" `.btn .btn-accent` beside the brief progress bar
  (`.brief-top`), enabled when completeness clears the rubric threshold.
- **Review panel** — a read-only `.panel` rendered after the last brief section once a spec exists:
  - Header: title + `.badge-info` version chip (`v2 · 12 Jun`) + re-run button. Older versions listed
    as `.badge-neutral` chips (read-only history — append-only versions made visible).
  - Body: the `.icp-grid` / `.icp-cell` (`.k` label + `.v` value) grid the ICP cards already use —
    one cell per spec group (Industries, Size, Geography, Keywords, per-ICP Titles, Caps), multi-values
    as `.icp-chips`/`.icp-chip`, exclusions as `.icp-chip.warn`.
  - **Gap prompts:** one `.brief-callout` (the existing warn-wash callout) listing each gap's
    field · why · ask — this is the loop's "fix it before credits are spent" surface. Gap count also
    badges the brief header (`.badge-warn`).
  - The existing `.est` line ("estimated matching accounts", `workspace/page.tsx:1390`) is the natural
    home for `max_results`/cap display.
- Until Phase C wires Clay, the panel carries the standard `.sample` marker convention on any
  estimated figure. Nothing here invents new design — it's the ICP card grammar applied to the spec.

### LLM observability (built into the seam, not bolted on)

The whole point of the single B3 adapter is that there is **one door every LLM call walks through** —
so observability lives there once and every later feature (reply labeling, summaries, drafting)
inherits it for free. Right-sized for dogfood volume:

- **One append-only `llm_call` table** (tenant-scoped, written by the adapter on every call):
  `purpose` (`brief_structure` today) · `model` · **`prompt_version`** · input/output tokens ·
  `cost_usd` (OpenRouter returns usage/cost in the response) · latency · `status`
  (`ok | parse_error | timeout | error`) · retry count · the **raw completion** (JSONB) ·
  `created_at`. At a handful of calls per client this is pennies of storage and the entire
  debugging story: when structuring produces a bad spec, the raw completion + prompt version is
  sitting next to the spec row.
- **`research_spec` links its `llm_call_id`** — every spec version is traceable to the exact model,
  prompt version, cost, and raw output that produced it.
- **`prompt_version` is the loop's instrument.** "Spec vN+1 targets better than vN" is only observable
  if each spec records which prompt produced it — prompt iterations become comparable (gap counts,
  operator edit rate after structuring) instead of vibes.
- **Structured CloudWatch log line per call** (same fields, minus raw payload) — this rides the
  existing Lambda logging; failures and latency are greppable today, alarmable later.
- **Cost control, two layers:** hard stop = the **$50 spend cap already set on the OpenRouter key**
  (provider-side, can't be exceeded by a bug); soft signal = `SELECT sum(cost_usd)` over `llm_call`
  by month/purpose — the billing-era per-tenant metering query already exists the day billing lands.
- **Parse failures are data, not just errors:** a completion that fails v1-schema validation is
  recorded (`parse_error` + raw payload) before the bounded retry — the highest-value signal for
  prompt iteration.

**Deliberately cut:** third-party LLM-ops platforms (Langfuse/LangSmith/Helicone), OTel tracing,
eval harnesses — at dogfood volume (tens of calls/month) a queryable table + CloudWatch is strictly
better than another vendor; revisit only when reply-labeling (Phase E) pushes real volume.

### Tasks

> **Status (2026-06-12): B0–B5 BUILT, backend live on dev (Lambda v8).**
> - **B0 cleared** — real strict-`json_schema` completion through OpenRouter from HK
>   (`google/gemini-2.5-flash-lite`, ~$0.00009/call); `default_model` + `models` written to
>   `holdslot/prod/openrouter`; `verify_keys --strict openrouter` = 3 passed, 0 pending.
> - **B1–B4 (backend)** — tables `brief`/`icp`/`research_spec`/`llm_call` (Alembic `0003_phase_b`,
>   up/down clean, `updated_at` triggers); brief+ICP document endpoints, completeness scorer,
>   OpenRouter adapter + telemetry, `POST /brief/structure` (versioned spec + gaps + server-merged
>   credit policy). **31 backend tests pass** against dev Aurora (incl. real structuring + telemetry).
> - **B5 (frontend)** — Workspace *Business brief* + *ICP* tabs wired to the live API + spec review
>   panel/gap callout (web typecheck/lint/build green).
> - **Code review (2 reviewers) issues all fixed:** version-race retry, telemetry isolation +
>   `ensure_awake`, upstream-error surfacing + transient retry + key-cache invalidation on 401/403,
>   strict `ResearchSpecV1` bound to the json_schema, empty-brief gate, frontend persist
>   concurrency-guard + incremental ICP-id assignment.
> - **Remaining before ticking S1:** deploy the web to Amplify `dev` + founder end-to-end test
>   (fill Brief+ICP → Structure → spec survives reload).

**B0 — Gates to clear before code (no code; now only two — the spec format is already locked above).**
- **OpenRouter structured-output access from HK ⭐ (the one true gate).** Make one *real* `json_schema`
  (`strict:true`) completion **through OpenRouter** from Hong Kong — a valid key ≠ working access.
  OpenRouter proxies server-side, so this is model-**agnostic** (HK reaches OpenRouter, not the model
  host directly), which de-risks the gate vs Bedrock. **Model decision (locked 2026-06-12):**
  `default_model = google/gemini-2.5-flash-lite` with `models` fallback array
  `["google/gemini-2.5-flash-lite", "openai/gpt-5-mini"]` and `provider.require_parameters = true`
  (only route to hosts honoring `structured_outputs`). Chosen for native strict `json_schema` support +
  lowest cost (~$0.0009/call); cost is a non-constraint at dogfood volume (<$1/mo). Store `default_model`
  (and the fallback) in `holdslot/prod/openrouter`, then run `verify_keys --strict openrouter`.
- **Required-fields list** — which Brief keys count toward "complete" (lift from the UI's existing
  Required/Optional tags). This is **a list of key names, not a schema** — the whole completeness
  rubric is data, editable without code changes.

**B1 — Thin schema + migration (4 tables, tenant-scoped).**
`brief` (one per client · `data` JSONB) · `icp` (many per client · `name`/`tag` + `data` JSONB) ·
`research_spec` (append-only versions · `spec` + `gaps` JSONB · `llm_call_id` · `created_at`) ·
`llm_call` (append-only telemetry per the observability section: purpose, model, prompt_version,
tokens, cost_usd, latency, status, retries, raw completion). All carry `client_id`; the A4 guard
scopes them. **DoD:** migration up/down clean; a Brief survives adding/removing arbitrary form fields
with no schema change.

**B2 — Document endpoints (one shared pattern).** `GET/PUT /clients/{c}/brief` and
`GET/POST/PUT/DELETE /clients/{c}/icps` are the **same thin "JSON document resource" shape** — store,
return, scope. The brief response also carries `completeness` + `missing[]`, computed server-side from
the B0 required-fields list (single source of truth for the ring and any future gating). **DoD:** brief
+ ICPs round-trip; completeness matches the list; changing the list changes the score with no code edit.

**B3 — OpenRouter adapter (one swappable client) + observability. ⭐** A single
`integrations/openrouter` adapter reading `holdslot/prod/openrouter` (key, `default_model`, `models`
fallback array, spend cap), **lazy / SnapStart-safe** (no network at import). It sends
`response_format: json_schema` (`strict:true`), the `models` fallback array
(`google/gemini-2.5-flash-lite` → `openai/gpt-5-mini`), and `provider.require_parameters:true` so only
schema-honoring hosts serve it; with timeout, bounded retry, and structured-output parsing — and the
**observability duties built in**: every call writes an `llm_call` row (model actually served, tokens,
cost_usd, latency, status, prompt_version, raw completion; parse failures recorded *before* retry) and
emits the structured CloudWatch log line. **Every** later LLM feature (reply labeling, summaries,
drafting) reuses this one seam and inherits the telemetry. **DoD:** a test does one real structured
completion (auto-skipped without the key, like the A6 acceptance tests) **and** the call's `llm_call`
row lands with sane token/cost/latency values + the served model; a forced parse failure records
`parse_error` + raw payload.

**B4 — Brief → `ResearchSpec` structuring.** `POST /clients/{c}/brief/structure` → the adapter prompts
Claude with the **whole Brief + ICP documents** (no per-field plumbing — this is what makes the prompt
churn-proof) to emit the **locked v1 targeting sections + gap prompts**; the server merges the
deterministic credit-policy defaults and validates against the v1 schema (strict on structure, lenient
on string content), then appends a new `research_spec` version **linked to its `llm_call_id`** — every
spec is traceable to the model, prompt version, cost, and raw completion that produced it. **DoD:** a
filled Brief yields a saved, v1-valid spec; gaps surface as prompts; re-running appends v2 without
touching v1; the spec row resolves to its `llm_call` telemetry.

**B5 — Wire the Workspace + Phase-B acceptance.** Point the Workspace *Business brief* (form +
completeness ring) and *ICP* tabs at the live API — the form state serializes to the JSON document
as-is; replace the `sampleBrief`/`sampleFields` mocks with real calls, keeping the **exact field set +
class names** — and render the **spec review panel + gap callout** per the UI plan above (existing
classes only). **DoD:** a founder fills the Brief and an ICP in the live Workspace, hits Structure, and
sees the spec grid + gaps; the spec survives reload; tick **S1** in `backend-development-plan.md`.

**Critical path:** B0 (OpenRouter HK) → B1 → B2 → {B3 → B4} → B5. **B0 is the only real risk** (model
access); **B3/B4 is the highest-leverage code** — every later AI feature reuses that adapter. After
Phase B, the cost of a Brief/ICP form change is a frontend edit + a rubric-list entry — **no migration,
no API change** — and the Clay contract (`ResearchSpec` v1) is unaffected by form churn. **Cost
(dogfood volume):** a handful of cheap-model completions per client (~$5–20/mo, §5); **no Clay credits
are spent in Phase B.** *(Carry to Phase C: operator transcribes `company_search` into the Clay
template; webhook 50k-lifetime cap → one webhook table per client per quarter; suppression filters
rows before push; HTTP-API-column callback gated on `email_valid`.)*

## Materials to prepare

**Accounts & keys** — **keys provisioned + verified 2026-06-10** (account/plan decisions below still open)

All keys live in **AWS Secrets Manager** (account `138743894336`), one JSON secret per platform under
`holdslot/prod/*`. Non-secret config → SSM Parameter Store (free). Read access granted to the
`claude_code` IAM user (`secretsmanager:GetSecretValue` on `holdslot/prod/*`, read-only). All four
external keys + the first-party app secret are created and verified by
[`apps/api/scripts/verify_keys.py`](../apps/api/scripts/verify_keys.py). The verifier is **phase-aware**:
fields a later phase provisions show as `PEND`, not `FAIL`, so a run today exits 0; use `--strict` at the
phase that needs them.

| Secret | Status | What the verifier confirms (2026-06-10) |
|---|---|---|
| `holdslot/prod/app` (first-party) | ✅ key set | JWT signing+refresh keys present, ≥32 chars, distinct (offline checks only) |
| `holdslot/prod/openrouter` | ✅ key set | Key valid; spend cap set ($50). `default_model` not stored → `PEND` (optional) |
| `holdslot/prod/clay` | ◑ key stored | `api_key` **stored** (not API-validated — costs a credit); table/webhook fields → `PEND` (Phase C) |
| `holdslot/prod/smartlead` | ◑ key valid | `api_key` valid (HTTP 200); sending accounts + `webhook_signing_secret` → `PEND` (Phase E) |
| `holdslot/prod/google` | ✅ working | SA key + domain-wide delegation + Calendar + Meet REST all 200, for **one** host seat (`info@tryholdslot.com`) |

Remaining secret fields (downstream **resources**, added to the secret at their phase, not blockers now):
- **Clay** — create the table + inbound-webhook URL/secret; add `table_id` + `inbound_webhook_url` +
  `inbound_webhook_secret` to the secret → **Phase C**.
- **Smartlead** — connect warmed sending accounts; add `webhook_signing_secret` + `sending_account_ids`
  → **Phase E** (gated on the ~3-week warm-up below).
- **Google** — optional: re-wrap the raw SA JSON as `{service_account_json, delegated_subject, scopes}`
  so the app reads subject/scopes from the secret. Functionally already working.

**Account/plan decisions still open (not keys — a valid key doesn't prove these):**
- ~~**Domain registrar / DNS access**~~ **Have it** — `tryholdslot.com` is in Route 53; SES DKIM + DMARC
  published 2026-06-11 (see Phase A follow-up #1). Per-domain records for the *outbound* warm-up domains
  still to add as those domains come online.
- **OpenRouter** — confirm the Claude model(s) we'll use are **HK-accessible** (the whole reason for
  OpenRouter over Bedrock); a valid key doesn't prove model access → **Phase B/B0** (the one true gate).
- **Clay** — credit/enrichment plan sized to dogfood volume (drives the §6 enrichment cap) → before **Phase C**.
- **Smartlead** — plan tier with enough mailbox capacity for 2–3 domains × ~2 mailboxes → before **Phase E**.
- **Google Workspace** — confirm host-seat count (1–2 / pooled) and that the tier enables **Meet
  recording/transcripts**; provision an **OAuth client** if any phase needs user-consent (vs delegation) → **Phase F**.
- **AWS** — budget alarm before prod. *(Stripe — not this phase.)*

**Sending infrastructure (start now — ~3-week warm-up)**
- 2–3 alternate sending domains (e.g. `getholdslot.com`, `tryholdslot.com`), ~2 mailboxes each.
- SPF / DKIM / DMARC records (done for `tryholdslot.com`'s **transactional** SES identity; the *outbound*
  warm-up domains still need their own); sender names + signatures; do-not-email suppression list.

**Content & assets (our own GTM)**
- HoldSlot's own **ICP** (industries, titles, company size, geos, triggers) — consumed by Brief→spec.
- **Cold-email copy** (A/B/C + sequence + personalization angle).
- **Sales pitch / demo** — the live product is the demo. Booking availability. Landing-site CTA → booking flow.

**Decisions needed before the relevant phase**
- ~~Auth/access model — operators vs. client login~~ **Resolved** (see *Tenancy & access model*): 2 founder
  owner accounts on tenant #0 now; schema multi-tenant + role-aware; clients stay on tokenized links.
- **Fit-scoring rubric** (what makes a good HoldSlot prospect) — blocks C.
- **Cold-outreach compliance** (CAN-SPAM / GDPR / HK PDPO) + unsubscribe + suppression owner — gates E.
- Booking-link lifetime / expiry — F. · AWS region / data residency — A.
