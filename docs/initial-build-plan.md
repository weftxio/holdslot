# HoldSlot — Initial Build Plan (dogfood MVP)

> Planning only — no backend code yet. This is the **first build**: make HoldSlot's own product real
> enough that the company runs its own outbound on it and lands its first signups. Scoped cut of the
> full spec in `backend-development-plan.md`.

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
- **Domain registrar / DNS access** — prerequisite for the warm-up below (SPF/DKIM/DMARC). Needed **now**.
- **OpenRouter** — confirm the Claude model(s) we'll use are **HK-accessible** (the whole reason for
  OpenRouter over Bedrock); a valid key doesn't prove model access → before **Phase B**.
- **Clay** — credit/enrichment plan sized to dogfood volume (drives the §6 enrichment cap) → before **Phase C**.
- **Smartlead** — plan tier with enough mailbox capacity for 2–3 domains × ~2 mailboxes → before **Phase E**.
- **Google Workspace** — confirm host-seat count (1–2 / pooled) and that the tier enables **Meet
  recording/transcripts**; provision an **OAuth client** if any phase needs user-consent (vs delegation) → **Phase F**.
- **AWS** — budget alarm before prod. *(Stripe — not this phase.)*

**Sending infrastructure (start now — ~3-week warm-up)**
- 2–3 alternate sending domains (e.g. `getholdslot.com`, `tryholdslot.com`), ~2 mailboxes each.
- SPF / DKIM / DMARC records; sender names + signatures; do-not-email suppression list.

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
