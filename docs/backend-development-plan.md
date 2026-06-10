# HoldSlot — Backend Development Plan (v4)

> Planning only. No backend code is written yet. Requirements are derived from the product
> (done-for-you, billed-per-qualified-meeting) and the eight mock pages in `apps/web`.
> v2 incorporated confirmed architecture decisions and per-stage direction.
> v3 folded in three founder revenue-protection directives: anti-burn Clay quota (S1/S2/S7),
> anti-theft tiered masking on client approval (S3), and client-approved SmartSenders lookalike-domain
> provisioning (S4).
> **v4 adopts the new tiered pricing model (USD): Free / Launch ($800/mo) / Growth ($1,600/mo),
> a one-time $400 activation, $500 per qualified meeting, $3/prospect overage, and a 48-hour dispute
> window on the billable event** — replaces the old flat HKD 6,000 + HKD 4,000 model. See §6 (7, 10, 11)
> and the pricing table in §7.

---

## 0. Status & how to use this doc (read first)

**This document is the backend spec and build order. It is approved and ready to execute. No
backend code exists yet — the next session starts at S0.**

**What is already built and live (Phase 1):**
- The full mock UI in `apps/web` (Next.js 15, App Router) — all 8 pages, ported pixel-faithfully
  from `design/`, backed by **co-located mock fixtures** (no backend). See root `CLAUDE.md`.
- Hosted on **AWS Amplify** in account **138743894336**, CI/CD on push:
  - prod (`main`): https://main.d2w95n49ooprjf.amplifyapp.com
  - dev (`dev`):  https://dev.d2w95n49ooprjf.amplifyapp.com
- Ship flow (proven): push `dev` → review on dev URL → fast-forward `main` → prod.

**What is NOT built:** everything in `apps/api` and `infra/` (both are placeholder READMEs).

**How the backend lands behind the existing UI:** the mock data is co-located in each page as
clearly-named consts (the data/view seam). When the API exists, replace those consts with an
accessor that returns the same shapes from the API. Start the UI cutover at the screens whose
stage is complete (see the §8 map).

**To pick up next session:** read §0 → §2 (architecture/decisions, all locked) → §4 S0, then
expand S0 into tasks and build. Use §8 to know exactly which screen each stage unblocks.

---

## 1. Guiding approach

**The pipeline IS the architecture.** Every mock screen is one step of one value chain:

```
Brief → ICP → Prospect research → Sendout batch → Client approval
      → Campaign (outreach) → Reply queue → Booking → Meeting → Feedback → Billing
```

- **Human-in-the-loop first.** HoldSlot is *done-for-you*: operators can run the hardest steps
  (Clay research, Smartlead sending) by hand while the backend records state. Build the **data
  spine + console API first**, automate integrations later.
- **One billable event = a qualified meeting.** Qualified = the prospect was **client-approved**
  (S3 record) **and** the meeting actually happened with **duration ≥ 10 min** (S6 Google Meet
  metadata) **and** it **cleared a 48-hour dispute window** (S7). That gate drives the whole build
  priority. Billed at **$500 per qualified meeting** on top of the plan's monthly fee (§7).

**Launch mode (confirmed): operator-assisted MVP → `S0 → S1 → S3 → S6 → S7`.** This reaches the
billable event with minimal integration surface. S2/S4/S5 (research + outreach + reply automation)
follow as Milestone 2; during the MVP, operators run Clay/Smartlead manually and the backend
stores the results.

---

## 2. Architecture (confirmed decisions)

| Concern | Decision | Notes |
|---|---|---|
| API compute | **AWS Lambda + API Gateway (HTTP API), FastAPI via Mangum, with SnapStart (Python 3.12+)** | Scale-to-zero; SnapStart cuts cold starts to sub-second. Publish versions + alias; keep `init` deterministic (no secrets/RNG at import); re-fetch secrets post-restore |
| Database | **Aurora Serverless v2 (PostgreSQL) + RDS Data API** | Scales to 0 ACU idle; Data API is HTTPS → Lambda runs **outside the VPC (no NAT Gateway)** and the stateless connection is **SnapStart-safe** |
| Migrations | **Alembic** in `infra/` | Schema source of truth |
| IaC | **Terraform** in `infra/terraform/` | Remote state (S3 + DynamoDB lock); dev/prod workspaces |
| Async work | **SQS + Lambda workers** | Research callbacks, Smartlead sync, summary generation |
| Scheduling | **EventBridge Scheduler** | Link expiry/reminders, billing close, Meet ingest polling |
| Eventing | **Google Workspace Events API → Pub/Sub** (or poll) | Fire when a conference ends → ingest Meet metadata |
| Storage | **S3** | Transcripts, inbound payloads, exports |
| Secrets | **AWS Secrets Manager** | One JSON secret per platform (`holdslot/<env>/<platform>`); native rotation + resource policies; fetched post-SnapStart-restore. ~$0.40/secret/mo |
| Non-secret config | **SSM Parameter Store (SecureString)** | Free tier; env/feature flags that aren't credentials |
| Transactional email | **Amazon SES** | Approval/booking/feedback emails, reminders |
| AI / LLM | **OpenRouter (Claude + others) — sole AI billing point**, behind one adapter | Chosen over Bedrock for reliable model access from Hong Kong. All HoldSlot-invoked LLM goes through OpenRouter: brief structuring, reply labeling/drafting, meeting summaries. We do **not** use Google smartNotes/Gemini for summaries (Meet transcript → OpenRouter instead). Clay's internal AI is part of Clay's product cost, separate category. One client adapter so the provider can be swapped without touching domains |
| Auth | **FastAPI + JWT** (argon2, refresh tokens) | Matches the email+pw login mock |
| Frontend | **Amplify** (already live, dev+prod, $0) | CI/CD proven |
| Observability | **CloudWatch** (+ optional Sentry) | |

**Third-party integrations (confirmed):**

| Capability | Vendor | Integration pattern |
|---|---|---|
| Prospect research/enrichment | **Clay** | Push structured ICP/search spec → Clay table **webhook-in**; Clay waterfall + Claygent enrich; Clay **HTTP API action** POSTs enriched prospects back to a HoldSlot callback. Operator-run table in MVP |
| Cold-email outreach | **Smartlead** | REST: create campaign, add leads, sequences, reply-to-thread; webhooks `EMAIL_*`, `LEAD_CATEGORY_UPDATED` |
| Calendar + meeting | **Google Workspace: Calendar API + Google Meet REST API v2** | Calendar creates the event + Meet link and invites buyer + client; Meet API returns `conferenceRecords`, `participants` (duration), `transcripts` |
| Payments | **Stripe** | per-plan **subscription** (Launch/Growth) + one-time **activation** + **metered** per-qualified-meeting + **metered** enrichment overage (§7) |

---

## 3. Core domain model

`Client` (slug) · `Subscription` (**`plan` = free/launch/growth, `activation_paid`, `monthly_rate`,
`enrichment_cap`, `icp_limit`, `current_month_usage`, `admin_quota_override`** — drives the anti-burn
guard, §4 S2, and billing, §7) · `User` · `Brief` · `ResearchSpec` (LLM-structured) · `ICP` ·
`Prospect` (+enrichment; stores **full clear-text** `email`/`phone`/`linkedin_url`/`personal_icebreaker`
— served masked to clients, §4 S3) · `Batch` · `ApprovalLink` · `ProspectApproval` (per-prospect
decision — billing precondition) · `SendingDomain` (lookalike domain:
`proposed→approved→purchased→warming→active`) · `Mailbox` (sender inbox; 2 per domain) · `Campaign` ·
`MessageVariant` · `OutreachEvent` · `Reply` (+label, draft) · `BookingLink` · `Meeting` (+Meet
metadata: duration, participants, transcript ref, summary; **`dispute_window_ends_at`, `disputed`,
`billable`** — §7) · `FeedbackLink`/`Feedback` · `LedgerEntry`/`Invoice` (line kinds: **activation,
subscription, qualified-meeting, enrichment-overage**) · `EmailTemplate` · `AuditLog`. Every row scoped
by `client_id`.

---

## 4. Build stages

### S0 — Core spine & deploy foundation · **P0 (MVP)**
- **Features:** FastAPI skeleton on Lambda+SnapStart; multi-tenant DB + Alembic baseline; JWT auth
  (login, forgot/reset); client CRUD + slug; Secrets Manager + SSM config; structured logging; CI/CD + IaC; health.
- **UI wired:** `login` (real auth), client switcher (real clients), app shell loads live session.
- **Tools/access:** Secrets Manager, SSM, SES (reset email), Aurora Data API, IAM.
- **AWS:** Lambda, API Gateway, Aurora Serverless v2, Secrets Manager, SSM, SES, S3 (artifacts), CloudWatch.

### S1 — Business Brief & ICP → research-ready spec · **P1 (MVP)**
- **Role of LLM (per direction):** OpenRouter (Claude) **structures the client's raw brief input into a
  research-ready spec** — normalized ICP attributes + the concrete search/enrichment parameters S2
  needs (industries, sizes, geos, titles, triggers, exclusions, signals). This is the bridge into
  Clay. Plus completeness scoring and gap prompts.
- **Features:** Brief CRUD; Claude → `ResearchSpec`; ICP CRUD (multi-profile create/review/delete).
- **Anti-burn quota (plan-derived; init here, enforced at S2):** the `Subscription.enrichment_cap`
  is set by the plan tier — **Free: 10 prospects one-time · Launch: 150/mo · Growth: 400/mo** (§7).
  Launch's 150 prospects ≈ ~6,000 Clay credits at ~40 credits each, keeping worst-case (zero-meeting)
  Clay COGS a small fraction of the $800 monthly on a volume Clay rate (~$0.016–0.02/credit). `icp_limit`
  is likewise plan-derived (Launch 1, Growth 3). Beyond the cap, enrichment is **not blocked — it's
  billed as overage at $3/prospect** (S7), never silently absorbed. Enforcement + monthly reset live in
  S2 (where credits are actually spent); S1 only seeds the parameters from the plan.
- **UI wired:** Workspace → *Business brief* (form + completeness ring), *ICP* profiles.
- **Tools/access:** **OpenRouter (Claude)**.

### S2 — Prospect research via Clay · **P1 (Milestone 2)**
- **Features:** `Research prospects from ICP` → send `ResearchSpec` to a **Clay** table (webhook-in)
  → Clay enrichment waterfall + Claygent → Clay HTTP API **POSTs enriched prospects back** to a
  HoldSlot callback → store `Prospect` rows with fit score + **enrichment detail rich enough for the
  client to decide in S3**; filter/search/select.
- **UI wired:** Workspace → *Prospect list* (filters, Source ICP column, select).
- **Anti-burn enforcement (quota seeded in S1):** the research orchestration wrapper checks
  `current_month_usage >= enrichment_cap` **before dispatching any batch to Clay**. At the cap it does
  **not** hard-fail by default — it **meters the excess as $3/prospect overage** (`LedgerEntry`, §7) and
  continues; a hard stop (`403 CreditQuotaExceeded`) applies only when overage is disabled for the tenant
  or `admin_quota_override` is off and a tenant-specific ceiling is hit. An **EventBridge Scheduler**
  monthly job resets `current_month_usage` (reuses the §4 billing-close cadence). *MVP note:* S2 is
  operator-run, so automated metering/suspension only bites once Clay is automated (Milestone 2); the
  cap + usage fields still ship early so usage is tracked from day one.
- **Tools/access:** **Clay** (webhook-in + HTTP API out), SQS worker (callback ingest), OpenRouter
  (fit scoring/dedupe), EventBridge (usage reset). *MVP:* operator runs the Clay table; results flow
  back via webhook.
- **AWS:** + SQS, worker Lambda, API Gateway callback route, S3 (raw payloads), EventBridge.

### S3 — Sendout batch & client approval · **P0 (MVP, revenue precondition)**
- **Features:** Create `Batch` from selected prospects (pending/approved/rejected + approved/total).
  **Client-facing approval built for a smooth decision:** the approval page shows each prospect with
  enough *fit context* to approve/remove one-click — but identity and contact vectors are masked (see
  the anti-theft block below for exactly what is shown vs withheld). **Persist a per-prospect
  `ProspectApproval` record** — this is the agreement that S7 bills against. Tokenized expiring links;
  editable sendout template; "Send to client".
- **Anti-theft masking (tiered identity reveal):** the `Prospect` table holds **full clear-text**
  contact + identity data, but the unauthenticated client-facing `GET /approval/{token}` serializer
  emits a **masked payload** so a client cannot reach a prospect on their own and bypass the $500
  qualified-meeting fee. Masking is a **field-level transform in the serializer** (not regex over the
  blob). Identity unlocks in tiers tied to the billing model:
  - **Approval stage (pre-approval) — fit only, no way to contact or uniquely identify:** show first
    name + last *initial* ("Sarah K."), a **company descriptor** ("Series-B fintech · 200–500 · SG")
    *not* the exact company, title/seniority/function, industry/size/region, fit reason, intent signal,
    and enrichment *highlights*. Withhold raw vectors → email = `verified business email ✓`, phone =
    `direct dial verified ✓`, LinkedIn → boolean `has_verified_linkedin: true`; personal icebreaker,
    socials and personal site are not exposed at all.
  - **After a meeting is booked / qualified:** reveal full name, exact company and LinkedIn to the
    client (they need to know who they're meeting and the $500 is now billable).
  - **Clear-text contact data never reaches the client at any stage** — once a prospect is `APPROVED`
    it routes **backend-only** into Smartlead (S4); HoldSlot does the outreach.
- **UI wired:** Workspace → *Sendout Batch*; external *client-approval* (valid/expired, **masked
  payload**); Client Action Status → *List approval* (batch selector, status log, template, send).
- **Tools/access:** SES (approval request), signed-token service, EventBridge (expiry/reminders).
- **AWS:** + EventBridge Scheduler.

### S4 — Campaign / outreach (Smartlead integration) · **P2 (Milestone 2)**
- **Features (per direction = fast DB↔Smartlead integration):** map approved batch → **Smartlead**
  campaign; push leads + A/B/C sequence variants; send controls (sending/pause, daily cap, split);
  sync send/open status back via webhooks into `OutreachEvent`.
- **Automated lookalike-domain provisioning (Smartlead SmartSenders) — isolates each client's
  deliverability so no shared-IP cross-contamination.** The capability lives here but the **trigger
  runs at onboarding (kicked off in S1, post-Brief), not at campaign-send** — lookalike domains need
  ~2–3 weeks of inbox warm-up, so provisioning must start early or first campaigns send cold.
  - **Domain-mutation resolver:** from the client root domain, derive candidates off the **bare SLD
    label** (`acme`, not `acme.com`): `getacme.com`, `tryacme.com`, `acmehq.com`, `acmesolutions.com`;
    run availability checks. *(Stripping the TLD first matters — `{label}hq.com` not `acme.comhq.com`.)*
  - **Client approval gate (confirmed):** the resolver **proposes** the candidate set as
    `SendingDomain(proposed)`; the **client approves** before any purchase (reuse the tokenized
    approval pattern / a console screen) → `approved`.
  - **Provision:** on approval, request isolated infra via the Smartlead **SmartSenders API**
    (`POST /api/v1/smartsenders/purchase` — *verify path/shape against current Smartlead docs, §6*):
    **3 lookalike domains × 2 mailboxes = 6 decoupled sending addresses.** Smartlead automates the
    underlying Namecheap registration and injects SPF/DKIM/DMARC + link-tracking DNS.
  - **Cost routing (resolved):** the **one-time $400 activation fee** (§7) is exactly this charge —
    building and warming the isolated sending setup (domains + mailboxes). Charged once at onboarding
    via Stripe; the actual SmartSenders/registration cost is HoldSlot's COGS against that fee, so no
    separate per-domain passthrough line is needed. Free tier provisions **no** domains (no outbound).
- **UI wired:** Workspace → *Campaign* (variants, send controls, send button); external/console
  **domain-approval** surface (client approves proposed lookalike domains).
- **Tools/access:** **Smartlead** REST + webhooks + **SmartSenders API**; OpenRouter (variant copy
  assist); SQS; EventBridge.
- **AWS:** + API Gateway webhook route, SQS, worker Lambda.
- *MVP fallback:* operator runs Smartlead UI; backend records campaign/results.

### S5 — Reply queue + AI (LLM message flow) · **P2 (Milestone 2)**
- **Features:** ingest Smartlead `EMAIL_REPLY` webhooks → **OpenRouter (Claude) labels** the response
  (positive / objection / OOO / not-interested…) and **drafts a reply**; optionally push the label
  back as Smartlead `LEAD_CATEGORY_UPDATED`; operator approves/edits → **send via Smartlead
  reply-to-thread**; status dropdown disposition; campaign filter; count pips.
- **UI wired:** Workspace → *Reply queue*.
- **Tools/access:** Smartlead webhooks + reply API; **OpenRouter** (label + draft); SQS; S3.
- **AWS:** + webhook route, SQS, worker Lambda.

### S6 — Booking, meeting & feedback (Google Workspace/Meet) · **P0 (MVP, revenue gate)**
- **Features:** tokenized **booking links** + slot picker against client availability; on booking,
  **Google Calendar API creates the event with a Google Meet link and invites both the buyer
  (prospect) and the client (seller)** for the sales call; recording-consent capture. After the
  call, **Google Meet REST API** yields `conferenceRecords` → `participants` (**duration**),
  `transcripts` → record meeting **metadata (summary, duration, participants, start/end)** to the
  HoldSlot DB; **OpenRouter (Claude)** writes the summary from the transcript. Tokenized **feedback
  links** (rating + chips) — feedback completes qualification context.
- **UI wired:** external *booking* + *feedback* (valid/expired); Client Action Status → *Booking
  links* (embedded invite) + *Feedback forms*; Workspace → *Meeting summaries*.
- **Tools/access:** **Google Calendar API** (event + Meet link + invites), **Google Meet REST API
  v2** (conferenceRecords/participants/transcripts), **Workspace Events API → Pub/Sub** (conference-
  ended trigger) or scheduled poll, **OpenRouter** (summary), SES (invites/feedback/reminders).
- **AWS:** + Pub/Sub→ingest Lambda (or EventBridge poll), S3 (transcripts), EventBridge.

### S7 — Billing & metrics · **P1 (MVP)**

**Pricing model (locked, USD):**

| Plan | Activation (once) | Monthly | ICP scope | Enrichment cap | Overage | Outbound | Per qualified meeting |
|---|---|---|---|---|---|---|---|
| **Free** | — | $0 | 1 brief, 1 ICP draft | 10 prospects (one-time) | — | None | N/A |
| **Launch** | $400 | $800 | 1 ICP | 150 prospects / mo | $3 / prospect | Yes | $500 |
| **Growth** | $400 | $1,600 | up to 3 ICPs | 400 prospects / mo | $3 / prospect | Yes | $500 |

- **What each charge pays for** (client-facing copy, homepage): **Activation $400** = building +
  warming the isolated sending setup (domains + mailboxes), so outreach lands not spam (S4).
  **Monthly** = the always-on engine (enrichment, sending infra, AI, operator research/outreach),
  billed whether or not meetings book. **Per meeting $500** = the outcome only.
- **Qualification rule:** a meeting is billable iff **(a)** the prospect has a client `ProspectApproval`
  from S3, **(b)** the S6 Google Meet metadata shows **duration ≥ 10 minutes**, **and (c)** it has
  **cleared a 48-hour dispute window** with no upheld dispute. On meeting-end, set
  `Meeting.dispute_window_ends_at = end + 48h`; an **EventBridge Scheduler** timer flips `billable=true`
  when the window passes undisputed. A client dispute inside the window parks the meeting for operator
  review instead of billing.
- **Stripe shape:** per-plan **subscription** (Launch/Growth monthly) + one-time **activation** invoice
  item + **metered** usage for qualified meetings ($500) and **enrichment overage** ($3/prospect over
  cap). Free = no Stripe customer until upgrade.
- **Features:** `LedgerEntry` per chargeable event (kinds: activation, subscription, qualified-meeting,
  enrichment-overage; meetings tagged campaign+batch); monthly close → Stripe invoice; **Overview**
  aggregations (headline, needs-attention, weekly stats, leads funnel).
- **Enrichment overage & overrides (anti-burn, from S1/S2):** over-cap enrichment is metered at
  **$3/prospect** as `enrichment-overage` `LedgerEntry` rows (the paid path past 150/400). An
  **`admin_quota_override`** toggle adjusts/limits this per client.
- **UI wired:** Workspace → *Billing ledger*; *Overview* dashboard.
- **Tools/access:** **Stripe** (subscription + invoice items + metered + webhooks), OpenRouter (optional
  insights), EventBridge (dispute-window timer + monthly close).
- **AWS:** + Stripe-webhook route, EventBridge.

### Cross-cutting
- **Webhooks** (Clay callback, Smartlead, Google/Pub-Sub, Stripe, SES events) → API Gateway →
  idempotent Lambda handlers.
- **One SQS+Lambda worker pattern** reused everywhere.
- **AuditLog + status logs** feed Client Action Status logs and the Overview needs-attention strip.
- **Security**: per-tenant row scoping, signed expiring tokens on all external links, Secrets Manager,
  least-privilege IAM, rate limiting on public/external + webhook routes (verify signatures).

---

## 5. Estimated cost & cost-minimization (rough, USD/month)

Framed two ways so cost can be checked against both the **pricing model** (§7) and the **growth
model** (§11): a **shared platform floor** (fixed regardless of tenant count at launch) plus a
**per-tenant variable cost** (scales with active tenants + plan tier). The per-tenant figures are
what feed the §11 Tech COGS line, so the two sections reconcile.

**A. Shared platform floor** — billed whether 3 or 12 tenants are live:

| Item | Minimized launch cost | Note |
|---|--:|---|
| AWS (Lambda+API GW · Aurora SLv2+Data API · SQS/EventBridge/SSM · Secrets Manager · S3 · SES · CloudWatch · Route53) | ~$80–150 | Scale-to-zero; Aurora 0-ACU idle + Data API (no NAT) is the floor's main driver. SnapStart cache <$4; Secrets Manager ~$2–3 (5 platform secrets) |
| Smartlead — **one** platform account | ~$39–94 | Single account for all tenants; per-client isolation is the SmartSenders domains, not separate accounts |
| Google Workspace — **pooled** operator host seats (~2–3, not per-tenant) | ~$36–54 | Meetings hosted under HoldSlot seats so Meet REST yields duration/transcript; pooling keeps this fixed |
| **Shared floor** | **~$155–300** | Amortizes toward ~$0/tenant as the book grows |

**B. Per-tenant variable cost** (per active tenant / month, by plan):

| Driver | Launch (150 prospects) | Growth (400 prospects) | Note |
|---|--:|--:|---|
| **Clay enrichment** | ~$100 | ~$270 | ~40 credits/prospect at ~$0.017/cr (volume tier) — **70%+ of variable cost** |
| LLM via OpenRouter (cheap models, one adapter) | ~$8–15 | ~$12–20 | Brief structuring, fit scoring, reply drafts, summaries |
| Smartlead sending (marginal) | ~$5–10 | ~$10–20 | Within the single platform account |
| Stripe (2.9% + $0.30) | ~$23 (churn) → ~$96 (adopter) | scales with plan + meetings | On plan fee + $500 meetings |
| **Per-tenant tech, ex-Stripe** | **~$115–125** | **~$290–310** | **≈ 15% of $800 / ≈ 19% of $1,600** |

**Reconciliation to §11:** §5 is bottom-up (floor + per-tenant); §11 is a blended ~9–12% of
revenue. They agree **at scale (H3–H4)**, where the fixed floor amortizes to near-zero per tenant
(H4 Tech COGS ≈ $6.2k/mo incl. the +30% buffer). In **H1–H2** bottom-up per-tenant runs *higher*
than §11's blended rate because the fixed floor is spread over only a handful of tenants — the floor,
not Clay, dominates at low tenant counts; Clay dominates once the book grows.

**Why Clay is the cost story:** Clay credits are spent **per prospect sourced** (for *every* tenant,
including churn that never books) — not **per meeting billed** (winners only). That asymmetry is
exactly what the plan-derived enrichment cap guards (§6 #7: 150/400, $3 overage past it).

**Cost-minimization decisions (full feature, least spend):**
1. **Clay cap + wave sourcing** — the cap bounds worst-case burn; source in waves (partial first
   batch, top up only on approval traction) so a churn client that quits in month 2–3 never burns the
   full ~6,000 credits up front. Single biggest margin lever.
2. **Pooled Workspace host seats** (operator-hosted meetings), not one seat per client → a fixed cost
   stays fixed.
3. **One Smartlead account**; isolated deliverability via SmartSenders domains funded by the **$400
   activation** (§6 #10) → no per-domain passthrough line; Free tier provisions none.
4. **AWS scale-to-zero** already chosen — Lambda, Aurora SLv2 0-ACU, Data API (no NAT), SSM free
   tier; dev stays ~$0.
5. **Smallest-model-that-works** behind the single LLM adapter — cheap models for labeling/scoring/
   drafting, a larger one only for summaries.

> Dev stays near **$0** (free tier + scale-to-zero). Keep the $5 AWS Budget alarm on dev; set a real
> cap before production. Deliberate simplifications: no NAT Gateway (Data API), no Recall.ai/Transcribe
> (Google Meet metadata), one LLM vendor (**OpenRouter**, §6 #3) behind one swappable adapter — set an
> OpenRouter monthly spend cap.

---

## 6. Decisions — locked (1–11)

1. **Compute:** Lambda + **SnapStart (Python 3.12+)**. ✅
2. **Cold email:** **Smartlead**. ✅
3. **AI:** **OpenRouter (Claude + others) as the sole AI billing point**, behind one swappable
   adapter (no Gemini/Anthropic-direct). Chosen over Bedrock for reliable model access from Hong Kong. ✅
4. **Meeting capture:** **Google Meet metadata** via Calendar + Meet REST API (no Recall.ai/Transcribe). ✅
5. **Launch mode:** **operator-assisted MVP `S0 → S1 → S3 → S6 → S7`**. ✅
6. **IaC:** **Terraform** (provisions Lambda+SnapStart, API GW, Aurora SLv2, SQS, EventBridge, SES, Secrets Manager, SSM, S3, IAM). ✅
7. **Anti-burn quota:** **plan-derived** `enrichment_cap` (Free 10 once · Launch 150/mo · Growth 400/mo);
   over-cap metered at **$3/prospect**, not blocked; enforced at S2, admin-overridable. ✅
8. **Anti-theft masking:** client approval page serves a **masked, tiered-reveal** payload; clear-text
   contact data is backend-only (→Smartlead). ✅
9. **Lookalike domains:** **client-approved** before purchase; provisioned via Smartlead **SmartSenders**
   (3 domains × 2 mailboxes), kicked off at onboarding for warm-up; funded by the $400 activation fee (#11).
   ⚠️ *Verify SmartSenders API path/payload + Namecheap/DNS automation against current Smartlead docs before build.*
10. **Domain-setup cost:** ✅ *resolved* — covered by the one-time **$400 activation fee** (#11); no
    separate passthrough line.
11. **Pricing model (USD):** **Free $0 / Launch $800/mo / Growth $1,600/mo**, one-time **$400 activation**,
    **$500 per qualified meeting**, **$3/prospect overage**, billable only after a **48-hour dispute
    window**. Replaces the old flat HKD 6,000 + HKD 4,000 model. ✅ *(Site/backend currency now USD; the
    figures match the homepage pricing section.)*

## 7. Sequencing

- **Milestone 1 — MVP to revenue:** S0 → S1 → S3 → S6 → S7. Brief in (Claude-structured),
  approve a batch, book a Meet call (buyer+client), capture Meet metadata, bill ≥10-min approved
  meetings ($500 after the 48-h dispute window) on top of the plan subscription + $400 activation.
  Research/outreach/replies operator-run via Clay + Smartlead.
- **Milestone 2 — efficiency:** S2 (Clay automation) → S4 (Smartlead campaign engine) →
  S5 (reply labeling + drafting).
- **Milestone 3 — scale/polish:** full webhook automation, dashboards, deliverability tuning,
  multi-operator roles.

Each stage ships via the proven flow: push `dev` → review → fast-forward `main` → prod.

---

## 8. Screen → stage → API map (UI cutover guide)

Existing `apps/web` routes (client slug = `[client]`), the stage that powers each, and the
backend surface to build. Replace the page's co-located mock consts with these once the stage lands.

| Route (`apps/web`) | Mock source | Powered by | Backend surface (indicative) |
|---|---|---|---|
| `/login` | `login.html` | **S0** | `POST /auth/login`, `/auth/forgot`, `/auth/reset` |
| client switcher (all console) | `lib/client.ts` | **S0** | `GET/POST /clients`, slug uniqueness |
| `/[client]/workspace` · Business brief + ICP | `workspace/page.tsx` | **S1** | `GET/PUT /clients/{c}/brief`, `POST /brief/structure` (Claude), `CRUD /icps` |
| `/[client]/workspace` · Prospect list | `workspace/page.tsx` | **S2** | `POST /icps/{id}/research` (→Clay), `GET /prospects`, Clay callback webhook |
| `/[client]/workspace` · Sendout Batch | `workspace/page.tsx` | **S3** | `CRUD /batches`, `POST /batches/{id}/send`, batch status |
| `/[client]/approve/[token]` | `approve/[token]` | **S3** | `GET /approval/{token}` (**masked, tiered-reveal payload**), `POST /approval/{token}/decide` (per-prospect) |
| `/[client]/client-status` · List approval | `client-status/page.tsx` | **S3** | `GET /clients/{c}/approvals`, templates, status log |
| `/[client]/workspace` · Campaign | `workspace/page.tsx` | **S4** | `CRUD /campaigns` (→Smartlead), send controls, `OutreachEvent` sync |
| domain approval (lookalike) | new surface | **S4** (kicked off S1) | `GET/POST /clients/{c}/sending-domains` (propose → **client-approve** → SmartSenders purchase) |
| `/[client]/workspace` · Reply queue | `workspace/page.tsx` | **S5** | Smartlead reply webhook, `GET /replies`, `POST /replies/{id}/send` |
| `/[client]/book/[token]` | `book/[token]` | **S6** | `GET /booking/{token}` (slots), `POST /booking/{token}/book` (→Calendar+Meet) |
| `/[client]/client-status` · Booking links | `client-status/page.tsx` | **S6** | `GET /clients/{c}/bookings` + invite email |
| `/[client]/feedback/[token]` | `feedback/[token]` | **S6** | `GET /feedback/{token}`, `POST /feedback/{token}` |
| `/[client]/workspace` · Meeting summaries | `workspace/page.tsx` | **S6** | `GET /meetings` (Meet metadata + OpenRouter summary) |
| `/[client]/workspace` · Billing ledger | `workspace/page.tsx` | **S7** | `GET /clients/{c}/ledger`, monthly close → Stripe |
| `/[client]/overview` | `overview/page.tsx` | **S7** | `GET /clients/{c}/overview` (aggregations) |

External links (`approve`/`book`/`feedback`) are unauthenticated and reached by signed, expiring
tokens; each renders valid / success / expired (`?state=expired` in the mock).

---

## 9. Expected repo layout (to create at S0)

```
apps/api/                 FastAPI service (managed outside the pnpm JS workspace)
  app/
    main.py               FastAPI app + Mangum handler (Lambda + SnapStart)
    core/                 config (Secrets Manager + SSM), auth (JWT), db (Aurora Data API client), logging
    domains/              one package per domain: clients, briefs, icps, prospects,
                          batches, approvals, campaigns, replies, bookings, meetings,
                          feedback, billing
    integrations/         openrouter, clay, smartlead, google (calendar+meet), stripe, ses
    workers/              SQS-triggered handlers (research callback, smartlead sync, summaries)
    webhooks/             clay, smartlead, google/pubsub, stripe, ses (signature-verified)
  pyproject.toml
infra/
  alembic/                migrations (schema source of truth)
  terraform/              Terraform IaC for Lambda+SnapStart, API GW, Aurora SLv2, SQS,
                          EventBridge, SES, Secrets Manager, SSM, S3, IAM — with dev/prod workspaces
```

> **IaC = Terraform (locked, §6).** Use remote state (S3 backend + DynamoDB lock) and separate
> dev/prod workspaces so each maps to the corresponding Amplify branch environment.

---

## 10. Next action (start of next session)

1. Expand **S0** into a task list and scaffold `apps/api` + `infra/` per §9 (Terraform IaC,
   remote state, dev/prod workspaces).
2. Stand up auth + clients, then cut over `/login` and the client switcher to the live API (§8).
3. Proceed S1 → S3 → S6 → S7 (MVP), wiring each screen as its stage completes.

Architecture and product decisions are locked (§6 1–11), including the USD tiered pricing model (#11).
**One build-time check remains and does not block S0:** §6 #9 — *verify the Smartlead SmartSenders API
surface before building S4*. Keep this file updated as the single source of truth: tick stages and note
any decision changes with a short rationale.

---

## 11. 2-Year Growth Model (cohort, conservative)

Business-planning model only — not a build dependency. It sizes the venture under realistic
adoption, churn, and acquisition assumptions, and exists to set expectations on ARR, retention,
margin, and funding need. Horizon: **Year 0 starting Oct 2026 → Sep 2028**, by half-year (H1–H4):
H1 market-fit · H2 normal adoption · H3–H4 full growth with marketing spend.

### Cohort assumptions (all adjustable)
Every signup is one of two cohorts:

- **Adopter — 15% of signups** (real market adoption): meetings ramp → peak → **die out** after the
  client's business has grown ~250–500%. ~90 qualified meetings over **1.5 years**, then the account
  ends. Meetings/mo by tenure half-year: HY0 ≈ 4 → HY1 ≈ 7 (peak) → HY2 ≈ 4 (fading). Launch plan
  throughout → **LTV ≈ $60k**. Because life is capped at 1.5 yrs, a cohort acquired in H1 has died by H4.
- **Churn — 85% of signups** (slow adoption), split 50/50:
  - **Fast Fails** — quit ~Month 2 → **LTV ≈ $1.2k**
  - **Slow Fails** — quit ~Month 3 → **LTV ≈ $2.5k** (blended churn LTV ≈ $1.85k)
- **Signups** ramp organically (not reverse-engineered to a target): 6 / 12 / 24 / 40.
- **Operator labour** (the dominant real COGS) scales with active client load on a stepped ratio as
  automation comes online: H1 founder-run **$0** → H2 **1:6** → H3–H4 **1:10**, @ ~$4,000/mo loaded.
- **Tech COGS** (Clay/Smartlead/AWS/LLM + Stripe 2.9%) carries a **+30% buffer**.
- **Marketing Spend** is tuned so H4 lands at a **5.0× LTV/CAC** operating target.
- **ARR** = durable run-rate of the active adopter book (churn excluded — it's transient).
- **Indicative valuation** uses **~4× ARR** (tech-enabled B2B services / services-as-software comp;
  see note below). **LTV/CAC** is revenue-based and blended across both cohorts.

### Master table — Oct 2026 → Sep 2028 (USD)

| Line | H1 · Oct'26–Mar'27 (market-fit) | H2 · Apr–Sep'27 (adoption) | H3 · Oct'27–Mar'28 (growth) | H4 · Apr–Sep'28 (full growth) | 2-Yr Total |
|---|--:|--:|--:|--:|--:|
| **Signups (new clients)** | 6 | 12 | 24 | 40 | 82 |
| — adopter (15%) | 1 | 2 | 4 | 6 | 13 |
| — churn (85%) | 5 | 10 | 20 | 34 | 69 |
| Active Adopter (1.5 Years die-out) | 1 | 3 | 7 | 12 | 12 |
| *Revenue* | | | | | |
| Adopter revenue (~$60k LTV) | $17.2k | $60.2k | $137.2k | $240.0k | $454.6k |
| Fast Fails Churn 50% (~$1.2k LTV) | $3.6k | $6.0k | $12.0k | $20.4k | $42.0k |
| Slow Fails Churn 50% (~$2.5k LTV) | $5.0k | $12.5k | $25.0k | $42.5k | $85.0k |
| **Total revenue (period)** | **$25.8k** | **$78.7k** | **$174.2k** | **$302.9k** | **$581.6k** |
| *Costs* | | | | | |
| Tech COGS (Clay/Smartlead/AWS/Stripe, +30% buffer) | $3.7k | $9.8k | $21.5k | $37.0k | $72.1k |
| Operator ratio | founder | 1:6 | 1:10 | 1:10 | — |
| Operator labour | $0k | $22.0k | $28.8k | $49.2k | $100.0k |
| Marketing Spend | $5.0k | $15.0k | $50.0k | $84.6k | $154.6k |
| **Total costs (period)** | **$8.7k** | **$46.8k** | **$100.3k** | **$170.8k** | **$326.6k** |
| **Net contribution** | **$17.1k** | **$31.9k** | **$73.9k** | **$132.1k** | **$255.0k** |
| **Margin %** | **66.4%** | **40.5%** | **42.4%** | **43.6%** | **43.8%** |
| GRR | – | 100% | 85% | 74% | – |
| NRR | – | 154% | 115% | 101% | – |
| **ARR** | $34k | $119k | $271k | **$475k** | – |
| **Indicative valuation (~4× ARR)** | $0.1M | $0.5M | $1.1M | **$1.9M** | – |
| **LTV/CAC** | 13.9× | 9.2× | 5.5× | **5.0×** | 5.9× |

### Read-out
- **Reaches ~$475k ARR in 2 years**, not $1M — at this realistic trajectory, $1M ARR is a Year-3
  milestone requiring a wider funnel and/or better retention.
- **Acquisition is well-tuned** (H4 LTV/CAC 5.0×, blended 5.9× — comfortably above the 3× floor);
  the binding constraint is **retention, not acquisition**.
- **GRR 74% and falling** is the honest weakness: the 1.5-yr adopter die-out + contraction leaks ~¼
  of retained ARR each period. **NRR settles to ~101%** — treading water; growth must come from new
  logos, not the existing base. This is agency-tier retention, which is why the 4× multiple is the
  optimistic end (a sober investor at this GRR prices ~2–3× → ~$1.0–1.4M).
- **Profitable as a services operation (~44% contribution margin)** but **not yet a venture-scale
  compounding asset.** Cost magnitude order: Marketing > Operator labour > Tech.
- **Highest-value levers** (in order): (1) **extend adopter life past 1.5 yrs** — directly fixes GRR
  and lifts NRR back above 110%; (2) **raise the 15% adopter rate** — each point converts a ~$1.85k
  churn into a ~$60k adopter (~32× swing). Adding signups alone just scales a leaky bucket.

### Caveats & not-yet-modeled metrics
- **Contribution-level only.** Excludes **R&D/engineering** (building the agentic platform), **G&A**,
  and founder/sales salaries — load these and H1–H2 likely run at a net loss / burn. The next
  iteration should add **full OpEx → monthly burn, runway, cumulative cash low-point, total raise**.
- **Rule of 40** was intentionally dropped: at sub-$1M ARR it's a small-base artifact (growth % off a
  tiny denominator dominates) and reads as naïve to investors — revisit only past ~$1–10M ARR.
- **Other metrics to add for a B2B AI raise:** CAC payback (months), AI/inference gross margin & cost
  per meeting, Quick Ratio, Magic Number, expansion/upsell (Launch→Growth), activation rate &
  time-to-value, dispute/show-up rate, and TAM/SAM/SOM.
- **Valuation basis:** comps span outbound/SDR agencies (~1–2× revenue) to AI-SDR software (~8–15×
  ARR in 2024–25); HoldSlot is a hybrid and the 85% churn / sub-100% steady-state NRR caps it well
  below the software tier — base case **~4× ARR**, range ~2–6×.
