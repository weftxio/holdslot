# HoldSlot — Backend Development Plan (v2)

> Planning only. No backend code is written yet. Requirements are derived from the product
> (done-for-you, billed-per-qualified-meeting) and the eight mock pages in `apps/web`.
> v2 incorporates confirmed architecture decisions and per-stage direction.

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
  metadata). That gate drives the whole build priority.

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
| Secrets/config | **SSM Parameter Store (SecureString)** | Free tier; fetched post-SnapStart-restore |
| Transactional email | **Amazon SES** | Approval/booking/feedback emails, reminders |
| AI / LLM | **Amazon Bedrock (Claude) — sole AI billing point** | All HoldSlot-invoked LLM goes through Bedrock: brief structuring, reply labeling/drafting, meeting summaries. We do **not** use Google smartNotes/Gemini for summaries (Meet transcript → Bedrock instead). Clay's internal AI is part of Clay's product cost, separate category |
| Auth | **FastAPI + JWT** (argon2, refresh tokens) | Matches the email+pw login mock |
| Frontend | **Amplify** (already live, dev+prod, $0) | CI/CD proven |
| Observability | **CloudWatch** (+ optional Sentry) | |

**Third-party integrations (confirmed):**

| Capability | Vendor | Integration pattern |
|---|---|---|
| Prospect research/enrichment | **Clay** | Push structured ICP/search spec → Clay table **webhook-in**; Clay waterfall + Claygent enrich; Clay **HTTP API action** POSTs enriched prospects back to a HoldSlot callback. Operator-run table in MVP |
| Cold-email outreach | **Smartlead** | REST: create campaign, add leads, sequences, reply-to-thread; webhooks `EMAIL_*`, `LEAD_CATEGORY_UPDATED` |
| Calendar + meeting | **Google Workspace: Calendar API + Google Meet REST API v2** | Calendar creates the event + Meet link and invites buyer + client; Meet API returns `conferenceRecords`, `participants` (duration), `transcripts` |
| Payments | **Stripe** (metered billing) | base + per-qualified-meeting |

---

## 3. Core domain model

`Client` (slug) · `User` · `Brief` · `ResearchSpec` (LLM-structured) · `ICP` · `Prospect` (+enrichment) ·
`Batch` · `ApprovalLink` · `ProspectApproval` (per-prospect decision — billing precondition) ·
`Campaign` · `MessageVariant` · `OutreachEvent` · `Reply` (+label, draft) · `BookingLink` ·
`Meeting` (+Meet metadata: duration, participants, transcript ref, summary) · `FeedbackLink`/`Feedback` ·
`LedgerEntry`/`Invoice` · `EmailTemplate` · `AuditLog`. Every row scoped by `client_id`.

---

## 4. Build stages

### S0 — Core spine & deploy foundation · **P0 (MVP)**
- **Features:** FastAPI skeleton on Lambda+SnapStart; multi-tenant DB + Alembic baseline; JWT auth
  (login, forgot/reset); client CRUD + slug; SSM config; structured logging; CI/CD + IaC; health.
- **UI wired:** `login` (real auth), client switcher (real clients), app shell loads live session.
- **Tools/access:** SSM, SES (reset email), Aurora Data API, IAM.
- **AWS:** Lambda, API Gateway, Aurora Serverless v2, SSM, SES, S3 (artifacts), CloudWatch.

### S1 — Business Brief & ICP → research-ready spec · **P1 (MVP)**
- **Role of LLM (per direction):** Bedrock Claude **structures the client's raw brief input into a
  research-ready spec** — normalized ICP attributes + the concrete search/enrichment parameters S2
  needs (industries, sizes, geos, titles, triggers, exclusions, signals). This is the bridge into
  Clay. Plus completeness scoring and gap prompts.
- **Features:** Brief CRUD; Claude → `ResearchSpec`; ICP CRUD (multi-profile create/review/delete).
- **UI wired:** Workspace → *Business brief* (form + completeness ring), *ICP* profiles.
- **Tools/access:** **Bedrock (Claude)**.

### S2 — Prospect research via Clay · **P1 (Milestone 2)**
- **Features:** `Research prospects from ICP` → send `ResearchSpec` to a **Clay** table (webhook-in)
  → Clay enrichment waterfall + Claygent → Clay HTTP API **POSTs enriched prospects back** to a
  HoldSlot callback → store `Prospect` rows with fit score + **enrichment detail rich enough for the
  client to decide in S3**; filter/search/select.
- **UI wired:** Workspace → *Prospect list* (filters, Source ICP column, select).
- **Tools/access:** **Clay** (webhook-in + HTTP API out), SQS worker (callback ingest), Bedrock
  (fit scoring/dedupe). *MVP:* operator runs the Clay table; results flow back via webhook.
- **AWS:** + SQS, worker Lambda, API Gateway callback route, S3 (raw payloads).

### S3 — Sendout batch & client approval · **P0 (MVP, revenue precondition)**
- **Features:** Create `Batch` from selected prospects (pending/approved/rejected + approved/total).
  **Client-facing approval built for a smooth decision:** the approval page shows each prospect with
  enough context (name, title, company, fit reason, enrichment highlights) to approve/remove
  one-click. **Persist a per-prospect `ProspectApproval` record** — this is the agreement that S7
  bills against. Tokenized expiring links; editable sendout template; "Send to client".
- **UI wired:** Workspace → *Sendout Batch*; external *client-approval* (valid/expired); Client
  Action Status → *List approval* (batch selector, status log, template, send).
- **Tools/access:** SES (approval request), signed-token service, EventBridge (expiry/reminders).
- **AWS:** + EventBridge Scheduler.

### S4 — Campaign / outreach (Smartlead integration) · **P2 (Milestone 2)**
- **Features (per direction = fast DB↔Smartlead integration):** map approved batch → **Smartlead**
  campaign; push leads + A/B/C sequence variants; send controls (sending/pause, daily cap, split);
  sync send/open status back via webhooks into `OutreachEvent`.
- **UI wired:** Workspace → *Campaign* (variants, send controls, send button).
- **Tools/access:** **Smartlead** REST + webhooks; Bedrock (variant copy assist); SQS; EventBridge.
- **AWS:** + API Gateway webhook route, SQS, worker Lambda.
- *MVP fallback:* operator runs Smartlead UI; backend records campaign/results.

### S5 — Reply queue + AI (LLM message flow) · **P2 (Milestone 2)**
- **Features:** ingest Smartlead `EMAIL_REPLY` webhooks → **Bedrock Claude labels** the response
  (positive / objection / OOO / not-interested…) and **drafts a reply**; optionally push the label
  back as Smartlead `LEAD_CATEGORY_UPDATED`; operator approves/edits → **send via Smartlead
  reply-to-thread**; status dropdown disposition; campaign filter; count pips.
- **UI wired:** Workspace → *Reply queue*.
- **Tools/access:** Smartlead webhooks + reply API; **Bedrock** (label + draft); SQS; S3.
- **AWS:** + webhook route, SQS, worker Lambda.

### S6 — Booking, meeting & feedback (Google Workspace/Meet) · **P0 (MVP, revenue gate)**
- **Features:** tokenized **booking links** + slot picker against client availability; on booking,
  **Google Calendar API creates the event with a Google Meet link and invites both the buyer
  (prospect) and the client (seller)** for the sales call; recording-consent capture. After the
  call, **Google Meet REST API** yields `conferenceRecords` → `participants` (**duration**),
  `transcripts` → record meeting **metadata (summary, duration, participants, start/end)** to the
  HoldSlot DB; **Bedrock Claude** writes the summary from the transcript. Tokenized **feedback
  links** (rating + chips) — feedback completes qualification context.
- **UI wired:** external *booking* + *feedback* (valid/expired); Client Action Status → *Booking
  links* (embedded invite) + *Feedback forms*; Workspace → *Meeting summaries*.
- **Tools/access:** **Google Calendar API** (event + Meet link + invites), **Google Meet REST API
  v2** (conferenceRecords/participants/transcripts), **Workspace Events API → Pub/Sub** (conference-
  ended trigger) or scheduled poll, **Bedrock** (summary), SES (invites/feedback/reminders).
- **AWS:** + Pub/Sub→ingest Lambda (or EventBridge poll), S3 (transcripts), EventBridge.

### S7 — Billing & metrics · **P1 (MVP)**
- **Qualification rule (per direction):** a meeting is billable iff **(a)** the prospect has a
  client `ProspectApproval` from S3 **and (b)** the S6 Google Meet metadata shows the meeting was
  held with **duration ≥ 10 minutes**. Bill **HKD 6,000 base + HKD 4,000 × qualified meetings**.
- **Features:** `LedgerEntry` per qualified meeting (tagged campaign+batch); monthly close → Stripe
  metered invoice; **Overview** aggregations (headline, needs-attention, weekly stats, leads funnel).
- **UI wired:** Workspace → *Billing ledger*; *Overview* dashboard.
- **Tools/access:** **Stripe** (metered + webhooks), Bedrock (optional insights), EventBridge (close).
- **AWS:** + Stripe-webhook route, EventBridge.

### Cross-cutting
- **Webhooks** (Clay callback, Smartlead, Google/Pub-Sub, Stripe, SES events) → API Gateway →
  idempotent Lambda handlers.
- **One SQS+Lambda worker pattern** reused everywhere.
- **AuditLog + status logs** feed Client Action Status logs and the Overview needs-attention strip.
- **Security**: per-tenant row scoping, signed expiring tokens on all external links, SSM secrets,
  least-privilege IAM, rate limiting on public/external + webhook routes (verify signatures).

---

## 5. Estimated cost (rough, USD/month)

Assumptions — **Prod (modest):** ~10 client tenants, ~20k outreach+transactional emails/mo,
~50 meetings/mo, light–moderate Bedrock usage.

| AWS resource | Dev / idle | Prod (modest) |
|---|---|---|
| Lambda + API Gateway (HTTP) | ~$0 | $5–20 |
| Lambda SnapStart snapshot cache | ~$0–1 | $1–4 (min 3 hr/published version) |
| Aurora Serverless v2 + Data API | ~$0–5 | $45–90 (0 ACU idle) |
| SQS / EventBridge / SSM | ~$0 | $1–5 |
| S3 + transfer | <$1 | $3–8 |
| SES | <$1 | $2–5 |
| Amazon Bedrock (Claude) | $0–5 | $20–80 |
| CloudWatch | ~$0 | $3–8 |
| **AWS subtotal** | **~$0–12** | **~$80–220** |

**Third-party SaaS (not AWS), prod:** Clay (credit tiers, ~$149–349) · Smartlead (~$39–94) ·
Google Workspace (per sending/host seat, ~$12–18/seat) · Stripe (% of revenue). Budget
**~$250–550/mo** depending on volume and how much is automated vs operator-run.

> Dev stays near **$0** (free tier + scale-to-zero). Keep the $5 AWS Budget alarm on dev; set a
> real cap before production. No NAT Gateway (Data API), no Recall.ai/Transcribe (Google Meet
> metadata), single AI vendor (Bedrock) — three deliberate cost simplifications.

---

## 6. Confirmed decisions (locked)

1. **Compute:** Lambda + **SnapStart (Python 3.12+)**. ✅
2. **Cold email:** **Smartlead**. ✅
3. **AI:** **Amazon Bedrock as the sole AI billing point** (no Gemini/Anthropic-direct). ✅
4. **Meeting capture:** **Google Meet metadata** via Calendar + Meet REST API (no Recall.ai/Transcribe). ✅
5. **Launch mode:** **operator-assisted MVP `S0 → S1 → S3 → S6 → S7`**. ✅
6. **IaC:** **Terraform** (provisions Lambda+SnapStart, API GW, Aurora SLv2, SQS, EventBridge, SES, SSM, S3, IAM). ✅

## 7. Sequencing

- **Milestone 1 — MVP to revenue:** S0 → S1 → S3 → S6 → S7. Brief in (Claude-structured),
  approve a batch, book a Meet call (buyer+client), capture Meet metadata, bill ≥10-min approved
  meetings. Research/outreach/replies operator-run via Clay + Smartlead.
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
| `/[client]/approve/[token]` | `approve/[token]` | **S3** | `GET /approval/{token}`, `POST /approval/{token}/decide` (per-prospect) |
| `/[client]/client-status` · List approval | `client-status/page.tsx` | **S3** | `GET /clients/{c}/approvals`, templates, status log |
| `/[client]/workspace` · Campaign | `workspace/page.tsx` | **S4** | `CRUD /campaigns` (→Smartlead), send controls, `OutreachEvent` sync |
| `/[client]/workspace` · Reply queue | `workspace/page.tsx` | **S5** | Smartlead reply webhook, `GET /replies`, `POST /replies/{id}/send` |
| `/[client]/book/[token]` | `book/[token]` | **S6** | `GET /booking/{token}` (slots), `POST /booking/{token}/book` (→Calendar+Meet) |
| `/[client]/client-status` · Booking links | `client-status/page.tsx` | **S6** | `GET /clients/{c}/bookings` + invite email |
| `/[client]/feedback/[token]` | `feedback/[token]` | **S6** | `GET /feedback/{token}`, `POST /feedback/{token}` |
| `/[client]/workspace` · Meeting summaries | `workspace/page.tsx` | **S6** | `GET /meetings` (Meet metadata + Bedrock summary) |
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
    core/                 config (SSM), auth (JWT), db (Aurora Data API client), logging
    domains/              one package per domain: clients, briefs, icps, prospects,
                          batches, approvals, campaigns, replies, bookings, meetings,
                          feedback, billing
    integrations/         bedrock, clay, smartlead, google (calendar+meet), stripe, ses
    workers/              SQS-triggered handlers (research callback, smartlead sync, summaries)
    webhooks/             clay, smartlead, google/pubsub, stripe, ses (signature-verified)
  pyproject.toml
infra/
  alembic/                migrations (schema source of truth)
  terraform/              Terraform IaC for Lambda+SnapStart, API GW, Aurora SLv2, SQS,
                          EventBridge, SES, SSM, S3, IAM — with dev/prod workspaces
```

> **IaC = Terraform (locked, §6).** Use remote state (S3 backend + DynamoDB lock) and separate
> dev/prod workspaces so each maps to the corresponding Amplify branch environment.

---

## 10. Next action (start of next session)

1. Expand **S0** into a task list and scaffold `apps/api` + `infra/` per §9 (Terraform IaC,
   remote state, dev/prod workspaces).
2. Stand up auth + clients, then cut over `/login` and the client switcher to the live API (§8).
3. Proceed S1 → S3 → S6 → S7 (MVP), wiring each screen as its stage completes.

All architecture decisions are locked (§6) — no open sub-decisions remain. Keep this file updated
as the single source of truth: tick stages and note any decision changes with a short rationale.
