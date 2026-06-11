# HoldSlot — Initial Build Plan (dogfood MVP)

> **Status: Phase A (S0) is built & live on `dev`; Phase B (S1) is next — broken out in detail below.**
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
> 1. **SES** — DKIM (3 CNAMEs) + DMARC published in Route 53 (2026-06-11) and resolving; awaiting SES
>    auto-verification, then `no-reply@tryholdslot.com` sends. Founder password-reset works in-sandbox
>    once verified (sandbox blocks only *unverified* recipients). **Deferred:** custom MAIL FROM (SPF
>    alignment) and production-access / sandbox-exit — needed only for client-facing mail at Phase C+.
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

## Phase B — Targeting (S1): step-by-step (planning, pre-code)

Turns a client's raw **Business Brief** into a research-ready **`ResearchSpec`** (the bridge into Clay,
Phase C) and lets the operator create/curate **ICP profiles** — wiring the Workspace *Business brief* and
*ICP* tabs to the live API. This is the **first use of the LLM** (OpenRouter). Grounded in the locked spec
(`backend-development-plan.md` §4 *S1*, §3 domain model) and the UI: `workspace/page.tsx`'s `Brief` and
`Icp`/`IcpFields` types **are** the field spec — match them.

**What Phase B delivers (DoD):** a founder fills the Brief in the live Workspace → the completeness ring
reflects real saved data → "Structure" produces a saved `ResearchSpec` (normalized ICP attributes + the
concrete Clay search/enrichment parameters) → one or more `ICP` profiles exist. **Clay-ready; nothing is
sent to Clay yet** (that's Phase C).

**B0 — Decisions to lock before code (no code until these are set).**
- **OpenRouter model access from HK ⭐ (the one true gate).** Make one *real* completion through the
  intended Claude model from Hong Kong — a valid key ≠ model access, and HK reachability is the whole
  reason for OpenRouter over Bedrock. Then store `default_model` in `holdslot/prod/openrouter` and run
  `verify_keys --strict openrouter`.
- **Brief completeness rubric** — which of the ~27 Brief fields are *required* vs *optional* for
  "complete", and how the ring scores. The UI already tags each field Required/Optional; lift that into
  one shared server-side definition so the ring and any gating agree.
- **`ResearchSpec` shape** — lock the exact JSON the LLM emits, **with Clay's table columns in mind** so
  C is a clean handoff: industries, company sizes, geos, titles/seniority/departments, technologies,
  triggers/signals, exclusions. (The **fit-scoring rubric is a Phase C input, not B.**)
- **Outreach languages** — the Brief captures `languages[]`; confirm the supported set (English +
  Mandarin?) so the spec and prompts localize.

**B1 — Data model + migration (tenant-scoped, mirrors the UI types).** Add `Brief`, `Icp`,
`ResearchSpec`, all `client_id`-scoped:
- `Brief` — the ~27 global fields from the UI `Brief` type (company/offer, value props, proof points,
  signals, objections, competitors, tone, `languages[]`, exclusions/compliance, meeting logistics,
  qualified-meeting definition). One per client.
- `Icp` — `short`, `tag`, `persona` + the per-profile `IcpFields` (industries, companySize, maturity,
  geographies, technologies, jobTitles, seniority, departments, buyerVsChampion, avoidTitles). Many per
  client.
- `ResearchSpec` — the LLM-structured JSON, linked to the Brief + ICP(s) and **versioned** (a re-run
  makes a new spec, never overwrites).
- Seed the `Subscription` quota fields the spec wants initialized at S1 (`enrichment_cap`, `icp_limit`,
  `current_month_usage`) even though enforcement is Phase C/S2 — the single owner tenant runs effectively
  uncapped. **DoD:** migration up/down clean.

**B2 — Brief CRUD API + completeness scoring.** `GET/PUT /clients/{c}/brief` (the A4 central guard already
scopes tenant × role). The server computes completeness from the shared rubric (B0) so the ring and any
gating share one source of truth. **DoD:** brief round-trips; completeness matches the rubric.

**B3 — OpenRouter adapter (one swappable client). ⭐** A single `integrations/openrouter` adapter reading
`holdslot/prod/openrouter` (key, `default_model`, spend cap), **lazy / SnapStart-safe** (no network at
import), with timeout, bounded retry, and structured-output parsing. **Every** later LLM feature (reply
labeling, summaries) reuses this one seam. **DoD:** a test does one real structured completion (auto-
skipped without the key, like the A6 acceptance tests).

**B4 — Brief → `ResearchSpec` structuring.** `POST /clients/{c}/brief/structure` → the adapter prompts
Claude to normalize the Brief into the locked `ResearchSpec` JSON plus **gap prompts** (what's missing for
good research). Persist the spec (versioned). **DoD:** a filled Brief yields a saved, schema-valid
`ResearchSpec`; gaps surface as prompts.

**B5 — ICP CRUD (multi-profile).** `GET/POST/PUT/DELETE /clients/{c}/icps` — create / review / delete ICP
profiles (the UI supports several; `icp_limit` is plan-derived but the owner tenant is effectively
unlimited). The `ResearchSpec` references the ICP attributes. **DoD:** multiple ICPs persist and
round-trip.

**B6 — Wire the Workspace + Phase-B acceptance.** Point the Workspace *Business brief* (form +
completeness ring) and *ICP* tabs at the live API — replace the `sampleBrief`/`sampleFields` mocks with
real calls, keeping the **exact field set + class names**. **DoD:** a founder fills the Brief and an ICP
in the live Workspace, hits Structure, and a `ResearchSpec` is saved server-side (survives reload); tick
**S1** in `backend-development-plan.md`.

**Critical path:** B0 (OpenRouter HK) → B1 → B2 → {B3 → B4} → B5 → B6. **B0 is the only real risk**
(model access); **B3/B4 is the highest-leverage code** — every later AI feature reuses that adapter.
**Cost (dogfood volume):** brief structuring is a handful of cheap-model completions per client
(~$5–20/mo, §5); **no Clay credits are spent in Phase B.**

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
