# HoldSlot — Initial Build Plan (dogfood MVP)

> Planning only — no backend code yet. This is the **first build**: make HoldSlot's own product real
> enough that the company runs its own outbound on it and lands its first signups. Scoped cut of the
> full spec in `backend-development-plan.md`.

## Scope & Definition of Done

- **Scope:** build the **single-tenant outbound → booked-meeting loop** and point it at HoldSlot's own
  market. **HoldSlot is tenant #0.** Defer all multi-client, billing, protection, and analytics work.
- **DoD:** the company uses the flow to land **6 signups in half a year** — i.e. §11's **H1 (Oct'26 →
  Mar'27)** target. The dogfood run *is* H1.
- **Timeline:** build **now → Sept'26** (~4 months); loop runs live **Oct'26 → Mar'27**.
- **Already live (not in scope to build):** the marketing site + all 8 mock UI pages on Amplify
  (account `138743894336`). This build replaces the mock data behind the loop's screens with a live API.

**The long pole is not code.** Cold-email **domain warm-up takes ~3 weeks** and gates every meeting.
Start domain warm-up and the Clay / Smartlead / Google / OpenRouter account setup **on day 0, in
parallel with the build** — prerequisites, not build steps.

## Build vs. skip

| Capability | This phase |
|---|---|
| Auth · single tenant · deploy | **BUILD** |
| Brief → ICP → ResearchSpec (LLM via OpenRouter) | **BUILD** |
| Prospect storage + filter/select | **BUILD** |
| **Clay connection** — push ResearchSpec → table (webhook-in) → callback → ingest enriched prospects | **BUILD** |
| Batch + internal approve/select | **BUILD** |
| **Smartlead connection** — batch → campaign, leads, A/B/C sequences, send controls, open/reply sync, reply-to-thread | **BUILD** |
| **Meeting connection** — booking link + Google Calendar event + Meet link + invites; capture held + duration via Meet REST | **BUILD** |
| Sending domains + warm-up | operate (manual setup — start now) |
| AI reply drafting · summaries/transcripts · feedback links · anti-theft masking · billing/Stripe · overview analytics · multi-tenant · automated SmartSenders | **SKIP** → return when onboarding paying signups |

## Phases (dependency- and priority-ordered)

| # | Phase | Must-build | Depends on | Priority | Phase DoD |
|---|---|---|---|---|---|
| **A** | Foundation (S0) | Founder login (JWT), single HoldSlot tenant, Aurora DB + deploy, console shell on live data | — | **P0** | Log in, see live console |
| **B** | Targeting (S1) | Brief intake → OpenRouter structures a ResearchSpec; ICP record | A | **P0** | ResearchSpec saved, Clay-ready |
| **C** | Prospects + Clay (S2) | ResearchSpec → Clay table → callback → ingest `Prospect` rows w/ fit context; filter/select | B · Clay | **P0** | Enriched prospects flow in automatically |
| **D** | Batch (S3 minimal) | Batch from selected prospects, mark approved internally. No external masked page | C | **P1** | Approved batch ready to send |
| **E** | Outreach + Smartlead (S4) | Batch → Smartlead campaign; leads + A/B/C sequences; send controls; webhook sync → `OutreachEvent`; reply-to-thread | D · warmed domains · Smartlead | **P0** | Live campaign sending; replies tracked in-app |
| **F** | Book + meeting (S6 minimal) | Booking link + slot picker → Google Calendar event + Meet link + invites; capture held + duration via Meet REST | E · Google Workspace | **P0** | Prospect self-books a Meet call; held/duration recorded |
| **G** | Run & close (human) | Meeting → founder pitches the live product → close → onboard signup = create their tenant (reuse A) | F | **P0** | **6 signups over H1** |

**Critical path:** A → B → C → D → E → F → G.
**Parallel from day 0 (long-lead):** domain warm-up · account setup · ICP + cold-email copy.

## Materials to prepare

**Accounts & keys**
- AWS `138743894336` — budget alarm before prod.
- **OpenRouter** — API key + monthly spend cap; confirm HK-accessible Claude models.
- **Clay** — credit plan + table + API key + inbound-webhook URL/secret.
- **Smartlead** — plan + API key + webhook signing secret + sending-account IDs.
- **Google Workspace** — domain + 1–2 host seats, Meet enabled, OAuth client + service-account JSON (domain-wide delegation) + scopes.
- Domain registrar / DNS access. *(Stripe — not this phase.)*

**Sending infrastructure (start now — ~3-week warm-up)**
- 2–3 alternate sending domains (e.g. `getholdslot.com`, `tryholdslot.com`), ~2 mailboxes each.
- SPF / DKIM / DMARC records; sender names + signatures; do-not-email suppression list.

**Content & assets (our own GTM)**
- HoldSlot's own **ICP** (industries, titles, company size, geos, triggers) — consumed by Brief→spec.
- **Cold-email copy** (A/B/C + sequence + personalization angle).
- **Sales pitch / demo** — the live product is the demo. Booking availability. Landing-site CTA → booking flow.

**Decisions needed before the relevant phase**
- **Fit-scoring rubric** (what makes a good HoldSlot prospect) — blocks C.
- **Cold-outreach compliance** (CAN-SPAM / GDPR / HK PDPO) + unsubscribe + suppression owner — gates E.
- Booking-link lifetime / expiry — F. · AWS region / data residency — A.
