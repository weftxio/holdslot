# HoldSlot — Business Plan & 0→1 Strategy (v1)

> **Stop buying sales tools. Start buying meetings.**
>
> This is the **business plan** — the market thesis, the evidence, and a higher-success-rate 0→1
> operating strategy. It is the strategic layer above the two build docs; it does **not** replace them:
> - [`backend-development-plan.md`](backend-development-plan.md) — the spec (architecture, pricing model §7, cost model §5, growth model §11).
> - [`initial-build-plan.md`](initial-build-plan.md) — the dogfood MVP build order (Phases A–G).
> - [`data-schema.md`](data-schema.md) — the system of record.
>
> **Author's stance:** written as a 0→1 operator + investor would — decisions, not a survey. Where the
> market evidence contradicts the current plan, this doc says so and proposes the change. Every market
> claim is tagged with a source; all evidence was gathered by multi-source web research (Jul 2026) and
> adversarially fact-checked (39/41 verifier votes upheld; the 2 refutations were a narrow nuance on
> Microsoft's enforcement *sequence*, not the rule). Full source list in the appendix.

> **Date:** 2026-07-02 · **Horizon:** launch Oct 2026 (H1 = Oct'26→Mar'27) · **Currency:** USD.

---

## 0. TL;DR — the one-paragraph thesis

The B2B outbound market in 2026 has a **trust problem, not a capacity problem.** Incumbent agencies
(Belkins, CIENCE, Martal, SalesRoads, Leadium) charge **$3,000–15,000/mo retainers** and lose most
clients fast — the dominant buyer complaint is **"calendar-stuffing"**: meetings booked to hit a billing
number that never convert. In parallel, the **autonomous AI-SDR** category (11x, Artisan, AiSDR) is in
open backlash — **50–80% churn inside 90 days**, hallucinated emails, collapsed deliverability — and the
*surviving* model that every post-mortem points to is a **hybrid human-in-the-loop managed service billed
on outcomes.** That is precisely HoldSlot. The pay-per-**qualified-held**-meeting model, the **48-hour
dispute window**, and the **masked client-approval** step are each independently validated by market
evidence as the exact mechanisms that neutralise the trust failure. **The gap is real and the model is
sound.** The two things that will actually decide success are **(1) retention** — the company's own growth
model already flags this as the binding constraint, yet nothing in the current build targets it — and
**(2) surviving a slowly degrading cold-email channel** by not being cold-email-*only*. This plan
re-sequences the venture from *software phases* to *learning milestones*, adds a **beachhead niche**, a
**client-quality gate**, a **retention engine**, and a **multi-channel + APAC-data hedge**, and rewrites
the H1 definition-of-done from "6 signups" into a falsifiable kill/scale decision.

---

## 1. The market in 2026 — what the evidence says

Seven research questions, one picture: **the incumbents are expensive and distrusted, the AI-native
challengers are imploding, and the channel is bifurcating (not dying).** A disciplined, transparent,
outcome-billed operator walks into the gap between them.

### 1.1 Incumbent agencies: expensive retainers, high churn, thin trust

| Fact (verified) | Source |
|---|---|
| Incumbent retainers: **Belkins $3–15k/mo (3–6mo min)**, CIENCE $2k/mo + $1.5–5.5k SDR staffing, SalesRoads $5.4–10k, Martal $3–11k, Leadium $3–7k. | leadgen.cience.com/belkins · isaless (2026-02-18) |
| **Neither Belkins nor CIENCE offers pay-per-qualified-meeting** — both are retainer/staffing. Pay-per-appointment players exist but are thin (Inside Sales Solutions, Callbox, Blue Zebra, BAO, Martal). Most large agencies remain retainer-first. | cience/belkins · isaless.com |
| The **#1 and #2 buyer complaints** about pay-per-meeting vendors: **"calendar-stuffing"** (meetings that bill but never close) and **burning sending domains** to hit volume, wrecking the client's deliverability. | prospeo (2026 buyer's guide) |
| A lead-gen agency owner: **~90% of clients churned after month 1**; a $2,500/mo retainer produced 2–4 meetings = **$625–1,250 effective per meeting**. Buyers anchor at ~$100–167/meeting → expectations gap drives churn. | linkeddit / r/LeadGeneration (2026-03-21) |
| Structural cost failure: on a $5k/mo retainer, **only ~10% ($500) funds the actual lead-gen work** (40% overhead, 30% commission, 20% account manager). | r/Entrepreneur (211 upvotes) via linkeddit |
| Disputes are mostly caused by **undefined terms + poor documentation, not genuinely bad leads** — so precise qualification definitions + evidence capture (recordings, timestamps) is the make-or-break of a pay-per-meeting model. | leadgen-economy (dispute guide) |
| Belkins still enjoys **4.9/5 on Clutch (230 reviews)** and delivers at scale (one client: 78 C-level appts in 6 mo) — the incumbent model *works* at five-figure engagement sizes; the weakness is **price, transparency, and SMB accessibility**, not competence. | clutch.co/profile/belkins |

**Read:** the incumbent moat is real capability at real prices for mid-market/enterprise. The **whitespace
is the underserved SMB / lower-mid buyer** who can't stomach a $5k retainer + 6-month lock-in and who has
been burned by opaque calendar-stuffing. HoldSlot's **$800–1,600/mo + pay-per-held-meeting + masked
approval + Meet-verified evidence** is a point-by-point answer to that buyer's exact grievances.

### 1.2 AI-SDR software: the substitute is in open backlash

| Fact (verified) | Source |
|---|---|
| **11x** (a16z/Benchmark-backed): employees reported **losing 70–80% of customers**; internal retention **20–30%**; ~$14M *claimed* ARR vs **~$3M** surviving 3-month break clauses; falsely listed ZoomInfo/Airtable as customers; hallucinations, emails to spam and to the *wrong* customers. CEO stepped down May 2025. | TechCrunch (2025-03-24) · Sifted |
| Category-level: **managed AI-SDR contracts see ~50–70% cancellation within 90 days** ("the 90-day kill curve"), clustered at days 60–90 once deliverability data develops. | leadgen-economy (failure forensics) |
| **AI reply rates collapse to 0.5–1.5% at scale** vs 4–6% for a human SDR on a warm domain; AI cost/meeting reaches **$150–300 once deliverability degrades** vs $35–50 human. AiSDR: **12–18% hallucination rate**. Artisan gross retention est. **<60%**. | leadgen-economy · digitalapplied |
| **Counter-evidence:** Artisan still raised **$25M (Apr 2025)** and **"is still hiring humans"** to make the AI work — capital is repricing the category, not abandoning it, and the raise tacitly concedes the human-in-the-loop point. | TechCrunch (2025-04-09) |
| Every serious post-mortem lands on the same surviving model: **hybrid human + AI managed service** — i.e. exactly HoldSlot's positioning. | leadgen-economy |

**Read:** this is HoldSlot's single strongest tailwind. The "just buy the AI SDR" alternative is actively
losing trust, and the market has independently concluded that the winning shape is *done-for-you with
humans in the loop, billed on outcomes.* HoldSlot should **explicitly position against autonomous AI**
("a human approves every meeting; you only pay when one actually happens") rather than *as* an AI tool —
being mistaken for an AI-SDR SaaS is a **reputational liability**, not a category benefit.

### 1.3 Cold-email channel: bifurcating, not dying — but the trend is down

| Fact (verified) | Source |
|---|---|
| Platform-wide avg reply rate **fell 8.5% (2019) → 5.1% (2024) → 3.43% (2025)**; but **top quartile 5.5%+, top decile 10.7%+.** The channel rewards skill, not volume. | Instantly Benchmark 2026 |
| **AI vs human, 100k matched emails (HoldSlot's exact Smartlead/Instantly/Apollo stack):** human copy **5.2% reply / 1.1%→meeting / 3% spam** vs AI **4.1% / 0.7% / 8% spam**. Human books **~57% more meetings per email** and is flagged spam far less. (Exception: in **SaaS**, AI narrowly beat human 6.1 vs 5.7% — degradation is vertical-dependent.) | digitalapplied (2026-04-26) |
| **Signal-based outbound** (3–5 scored buying signals) hits **4–10% reply, 30–40% lower cost/meeting**; Unify reports signal emails **5–18% vs 1–3% generic**. | growleads · unifygtm |
| Only **3–5% of any TAM is in an active buying cycle** at any moment (Forrester) — a hard ceiling on timing-agnostic list outbound. | growleads |
| **Bulk-sender rules** (Google/Yahoo/MS): 5,000-msg/day threshold, mandatory SPF/DKIM/DMARC, **<0.3% spam, <2% bounce**, one-click unsubscribe; Gmail moved to **permanent 550 rejection (Nov 2025)**; MS Outlook.com enforcing since May 2025. | redsift · Microsoft · dmarcian |
| **Structural relief for HoldSlot's model:** spreading volume across **many secondary domains, each well under 5,000/day** (the standard Smartlead playbook) is **not directly caught** by the volume threshold; and MS **365 business inboxes — HoldSlot's actual B2B targets — are not yet covered** by the consumer-domain thresholds. | digitalapplied · Microsoft |
| Belkins' 2025 client reviews show cold **still books qualified meetings at scale** (41% open / 12% reply on one campaign) — degraded ≠ dead for skilled operators. | clutch.co/profile/belkins |

**Read:** the channel is a **slowly deflating asset**, and HoldSlot's plan is levered directly to reply
rate (every point of reply-rate decline raises meeting COGS on a pay-per-meeting model). Two implications
the current plan under-weights: **(a) human-quality copy is a measurable moat** (57% more meetings/email,
1/3 the spam) — HoldSlot's operator-in-the-loop is an *advantage*, not a cost to automate away; **(b)
single-channel is a strategic risk** — the plan must add signal-based triggers and at least one non-email
channel before email decay compounds.

### 1.4 Pay-per-meeting economics: the model is validated — at the right price and volume

| Fact (verified) | Source |
|---|---|
| Pay-per-appointment ranges **$100–500 SMB / $300–600 enterprise / $600–1,500+ C-suite**; mid-market band **$350–700**; Clutch-cited **$550–1,700**. HoldSlot's **$500** sits mid-to-upper SMB / low mid-market. | prospeo · saleshive |
| **Pay-per-HELD** (attended) commands a premium over pay-per-scheduled; buyers of *scheduled* absorb **10–30% no-show**. **Pay-per-qualified-held typically prices $600–900** in 2026 → HoldSlot's $500 is **below** the premium-tier range. | prospeo · nerdyjoe |
| **48-hour dispute window** matches the recommended industry norm exactly (ack 4h / assess 24h / resolve 48h); dispute/return rates of **6–20%** are normal in performance lead-gen. | leadgen-economy · prospeo |
| Hybrid (base + per-meeting) is established at **$2–4k base + $150–400/meeting** — HoldSlot **undercuts the base** while charging **above-band per meeting**: a coherent, defensible structure. | salescaptain · prospeo |
| Buyer's alternative cost: **in-house SDR fully loaded $9.8–14.2k/mo = $700–1,150/meeting**; Belkins effective **~$550/meeting delivered**. HoldSlot at $500 + low base **wins the ROI comparison**. | isaless · clutch |
| Pay-per-meeting **pencils only below ~10 meetings/mo per client**; above ~15–20 buyers defect to retainers/in-house. Prices **<$150/meeting signal junk leads.** | prospeo |

**Read:** HoldSlot's pricing is **inside market norms and well-structured** — the held-meeting trigger and
48h window are best-practice, not invention. Two refinements the evidence supports: **(1) $500 flat is
mispriced in both directions** — below the $600–900 qualified-held band, yet at the top of what burned SMB
buyers anchor to (Reddit consensus **$100–250/meeting**; two sources put $500 at the very top of the SMB
range). Resolution: **don't reprice mid-pilot** — hold $500 flat through the pilot cohort and let the
**client-quality gate (ACV threshold, I1)** make $500 trivially payable; introduce **seniority-tiered
pricing** ($350 Director / $500 VP / $750 C-suite, mirroring the market curve) at GA once dispute/show
data exists. **(2) The model's natural ceiling is ~10 meetings/mo/client** — beyond that a client should be
*graduated* to a retainer or in-house motion; design the Growth tier and expansion path around that reality
rather than fighting it.

### 1.5 APAC: a real geographic wedge — but HoldSlot's own data stack is the weak link

| Fact (verified) | Source |
|---|---|
| **<15% of Apollo's 275M contacts** are Asian professionals outside major tech hubs; **SEA mid-market coverage is single-digit %.** Western tools against Asian accounts: **~40% bounce, 60% incomplete** profiles. | gruppointegritas |
| A **hybrid stack** (local registries — SG **ACRA**, MY **SSM**, TH **DBD**, PH **SEC** — + waterfall enrichment + human VA) reaches **80%+ coverage** — an emerging "GTM-engineering" model. | gruppointegritas |
| **Compliance is green for B2B cold email** in the launch markets: **SG PDPA** (opt-out; biz contact excluded; 5–10 biz-day unsub — *but lawful collection basis still required, so scraped lists can violate*), **HK PDPO/UEMO** (opt-out, sender ID, 10 biz-day), **TH PDPA** (legitimate interest, 5-day, early enforcement). | b2bdataindex · imisofts |
| **Vietnam is out for cold-first:** Cybersecurity Law 2018 + Decree 13/2023 require **express prior consent** — standard opt-out outbound is unlawful. | b2bdataindex |
| The regional agency field is **thin** (Scalelab SG+HK, iSmart on PDPA compliance); **some SG providers already run pay-per-meeting at $500–1,000.** | ultragrowthmedia |

**Read:** APAC is a genuine underserved wedge **and** a trap: the exact geography HoldSlot wants to win is
where **Apollo is weakest**, and lawful-source rules mean the *scraped-list* shortcut is a compliance
landmine in SG. This **hardens two existing plan items into must-haves**: the **AroundDeal/waterfall
fallback** ([`initial-build-plan.md`](initial-build-plan.md) → Asia depth) and a **local-registry
enrichment path** — not "post-MVP", but part of the APAC go-to-market from day one. **Drop Vietnam** from
the cold-email ICP; keep HK/SG/TH.

---

## 2. Market gaps a new entrant can exploit (ranked)

Concrete, evidence-backed openings — each mapped to a HoldSlot mechanism (existing or to build).

| # | Gap | Evidence | HoldSlot's answer |
|---|---|---|---|
| **G1** | **Trust/transparency void** — "calendar-stuffing", opaque held-vs-booked, quality-by-account-manager lottery. | prospeo · clutch · nerdyjoe | **Masked client-approval + Meet-verified held ≥10min + append-only approval record + 48h dispute.** The whole billing model is a trust instrument. **This is the core wedge.** |
| **G2** | **Autonomous AI-SDR backlash** — 50–80% churn, hallucinations; buyers burned, seeking a *trustworthy* alternative. | TechCrunch · Sifted · leadgen-economy | Position as **"a human approves every meeting; pay only when it happens"** — the anti-AI-SDR. |
| **G3** | **SMB/lower-mid affordability gap** — priced out of $3–15k retainers + 3–6mo locks. | cience/belkins · isaless | **$800–1,600/mo, no long lock, outcome-billed.** 2–4× under the retainer floor. |
| **G4** | **Alignment gap** — retainer buyers "pay regardless of whether meetings convert." | isaless (2025-09-22) | Base covers the engine; **the outcome fee only bills on a held, approved meeting.** |
| **G5** | **APAC coverage void** — Western data thin, few regional performance-based players, compliance green (ex-VN). | gruppointegritas · ultragrowthmedia | **APAC-native waterfall + local registries + PDPA/PDPO-clean sourcing** as a first-class GTM, not a fallback. |
| **G6** | **Dispute/definition chaos** — most disputes are undefined-terms, not bad leads. | leadgen-economy | **Pre-agreed "qualified" definition + captured evidence** (approval record, Meet metadata, timestamps) makes disputes rare and fast. |
| **G7** | **Copy-quality gap** — AI spray books 57% fewer meetings/email and 8% spam; skilled human copy wins. | digitalapplied | **Operator-in-the-loop, per-niche copy** as a deliberate quality moat, not a cost to remove. |

**The wedge, in one line:** *the transparent, outcome-billed, human-verified alternative to both the
$5k-retainer black box and the hallucinating AI-SDR — starting with underserved SMBs in APAC.*

---

## 3. Current plan: validated vs. contradicted

### ✅ Validated by the market (keep / lean in)
- **Pay-per-qualified-HELD meeting** — held-trigger commands a premium; no-show risk sits with the vendor. ✔
- **48-hour dispute window** — matches best-practice norms exactly. ✔
- **Masked client-approval + append-only `prospect_approval` evidence** — the antidote to the #1 buyer complaint and to dispute chaos. ✔
- **Human-in-the-loop, done-for-you** — the model every AI-SDR post-mortem converges on. ✔
- **Hybrid pricing that undercuts the retainer base** — coherent and defensible. ✔
- **Cost discipline** (~$195/mo run cost; enrich-only-selected) — COGS is small vs plan fee, as the plan claims. ✔
- **APAC B2B compliance thesis** — legally sound in HK/SG/TH. ✔

### ⚠️ Contradicted / under-weighted by the evidence (change)
- **C1 — Single channel (cold email only).** The channel is deflating (8.5→3.43% reply) and HoldSlot's economics are levered to it. **Add signal triggers + one non-email channel** (LinkedIn-manual at MVP) to the roadmap. *(§1.3)*
- **C2 — Apollo-only sourcing into APAC.** The target geography is where Apollo is weakest (<15% APAC, ~40% bounce). **Promote the waterfall + local-registry path from "post-MVP" to launch-critical for APAC ICPs.** *(§1.5)*
- **C3 — $500 flat is mispriced in both directions.** Below the $600–900 qualified-held band, yet at the top of the burned-SMB anchor ($100–250). Resolution: **flat $500 through pilots + the ACV client-gate**, then **seniority tiers at GA** — never a mid-pilot reprice. *(§1.4)*
- **C4 — "6 signups" is not a learning instrument.** Under the plan's own 85% churn assumption, 6 signups ≈ 1 adopter — statistically empty. **Re-cast H1 DoD as design-partner + evidence milestones.** *(§5, §7)*
- **C5 — No client-quality gate.** Anyone with $800 can sign; a weak-offer client churns regardless of meeting quality (that *is* the 85%). **Screen briefs before onboarding.** *(§4)*
- **C6 — Retention has no owner in A–G.** The growth model says retention is the binding constraint (32× LTV swing per adopter-rate point) yet no build phase targets it. **Add a retention engine.** *(§4)*
- **C7 — Free tier demos the tool, not the outcome.** 10 prospects, no outbound = shows plumbing, not a booked meeting. **Replace with a paid pilot / performance trial.** *(§4)*
- **C8 — Time-to-first-value is a churn bomb.** ~3-week warm-up + $1,200 upfront before any outcome; fast-fails quit ~M2. **Bridge the gap with a pre-warmed domain pool + early deliverables.** *(§4)*
- **C9 — Drop Vietnam** from the cold-first ICP (express-consent regime). *(§1.5)*

---

## 4. Ten building ideas that raise the success rate

Ordered by leverage on the two things that decide the outcome — **adopter-rate** and **retention** (the
growth model's own highest-value levers). Each is scoped so it can slot into the existing A–G build.

### I1 — Client-quality gate (the single highest-leverage change) 🎯
The growth model: raising the 15% adopter rate converts a ~$1.85k churn into a ~$60k adopter — **~32× per
point.** The cheapest way to raise it is to **stop onboarding clients who will churn no matter what.**
Score the intake **Brief** on: offer clarity, **ACV ≥ a threshold** (so one closed deal repays a year of
fees), presence of referenceable customers, and evidence of market pull. Weak offers get a **waitlist +
"fix these three things"** note, not an invoice. *Build:* a rubric over the existing `brief.data` JSONB +
a `qualification_score` — reuses the exact churn-proof rubric pattern already built in Phase B. **Protects
COGS, sender reputation, and case studies simultaneously.**

### I2 — Retention engine: meeting → opportunity → outcome 🎯
Nothing in A–G tracks what happens *after* the meeting, yet retention is the binding constraint. Extend
the feedback loop into a **lightweight pipeline tracker**: for each qualified meeting, capture
client-reported outcome (advanced / closed-won / dead) via the feedback-link primitive that already
exists. This yields (a) the **ROI story that renews clients** ("we sourced $X pipeline / $Y closed"), (b)
the **outcome data** that tunes targeting (the latent `outreach_outcome` column finally gets used), and
(c) the **expansion trigger** (a client winning deals buys a second ICP/region). *Build:* one table +
reuse feedback links; wire into Performance Summary as a "pipeline influenced" headline.

### I3 — Beachhead niche (pick ONE, saturate it)
"B2B SMBs" is not an ICP. Copy, data quality, case studies, and referrals **only compound inside a
niche.** Selection criteria: ACV high enough for $500/meeting to be trivial, a reachable population in
HK/SG/TH, a channel where cold still works (evidence: **SaaS is the one vertical where even AI copy beats
human** — the channel is healthiest there), and a domain the founder can speak credibly in. **Recommended
starting niche:** *B2B SaaS / dev-tools / fintech-infra companies ($1–10M ARR) selling into SEA.* Expand
to adjacent niches only after one is saturated.

### I4 — Multi-channel resilience (de-risk the deflating channel)
Add, in order: **(a) signal triggers** (job-change, hiring, funding — Apollo's `intent_filters` already
exist in the ResearchSpec) to lift reply rates 2–4× and cut meeting COGS; **(b) LinkedIn-manual at MVP**
— the operator sends ~20 connects/day against the *same approved list* (no new infra, just labor), giving
a second path to the meeting when email underperforms. This directly hedges the §1.3 risk and matches
where the market is moving. *Build:* signal triggers are a ResearchSpec/prompt change; LinkedIn is an
operator SOP + a `channel` field on outreach events.

### I5 — Kill the time-to-value gap (contract design, not new infra)
The ~3-week warm-up + $1,200 upfront before any outcome is a structural churn window (C8) — SG-market
evidence says 4–8 weeks to consistent results, and fast-fails quit ~M2. A shared *generic* pre-warmed
domain pool is the obvious fix but **collides with locked decision §6 #9** (domains are client-approved
lookalikes of the *client's* brand, funded by the activation fee — a lookalike warmed for client A can't
serve client B, and generic domains depress reply trust). The spec already contains the real fix — *"provisioning must start early... kicked off at onboarding, not at campaign-send"* — so operationalize it
as contract mechanics:
1. **Activation + domain provisioning fire at contract signature** (enforce the spec's own rule as an SLA);
2. **Week-1 deliverables** — ICP profiles, the approved prospect list, and campaign copy land before any
   send, so the client sees value inside days;
3. **Start the monthly fee at first-send** (or pro-rate month 1) so no client pays a full idle month;
4. **Contract states "first meetings in weeks 3–6"** explicitly — set the expectation the evidence supports
   instead of letting silence set a worse one.
For the pilot cohort specifically: sign in Jul–Aug'26 so every pilot's lookalike domains are long-warmed
before the Oct launch window.

### I6 — Seniority-tiered outcome pricing (capture the margin the market leaves you — at GA)
Move from **$500 flat** to **$350 Director / $500 VP / $750 C-suite** (mirrors the verified market curve
and the qualified-held $600–900 band). Same billing machinery (`meeting.amount` is already computed, not
hard-coded); the tier is a function of the approved prospect's seniority — which the system already knows,
and which the client sees on the masked approval page before approving (transparency preserved). Lifts
blended revenue/meeting without changing the model. **Timing: introduce at GA, not during pilots** — SMB
buyers anchor low ($100–250), and repricing mid-pilot burns trust for margin you can capture later with
dispute/show data behind you.

### I7 — Two-sided proof flywheel
Every delivered meeting generates proof on **both** sides that currently evaporates. Capture: **client
case studies** (auto-drafted from the I2 outcome data), a **live "meetings booked this month" counter**
(the homepage placeholder, wired to real `meeting` rows), and a light **prospect-side signal** ("this
intro was arranged by HoldSlot"). Proof is the cheapest acquisition channel and compounds only if
captured systematically. *Build:* Performance-Summary read + a public stat endpoint.

### I8 — Per-niche outcome-tuned targeting (the durable moat)
The `prompt` table is already versioned **per tenant × stage**, and `outreach_outcome` exists to close the
loop. Make it explicit: **feed won/lost outcomes back into per-niche fit rubrics**, so HoldSlot's targeting
in its beachhead niche becomes measurably better than any generalist tool's. This is the one asset that
compounds with volume and can't be bought — the answer to "why not just use Apollo yourself?"

### I9 — Sell-before-you-finish-building (H0 pre-sales)
Don't wait for Phase G to meet the market. During warm-up (Jul–Sep'26), **pre-sell 3–5 paid pilots**,
fulfilled with the already-live A–D console + operator-run sending. Converts the DoD from a passive funnel
test into **active design partnerships** with weekly feedback — the fastest path to product-market fit and
the first case studies. **This is not a deviation from the plan — it *is* the plan:** the backend spec's
own confirmed launch mode (§1) is *"operator-assisted MVP S0→S1→S3→S6→S7... operators run Apollo/Smartlead
manually and the backend stores the results."* The A–G build order quietly drifted into build-everything-
first; I9 is a return to the spec's locked decision.

### I10 — Referral/partner channel (pay-per-meeting is an easy referral promise)
"We book you qualified meetings and you only pay when they happen" is a frictionless referral. Cultivate
**accelerators, VC platform teams, and fractional-CRO/GTM networks in HK/SG** as a referral layer. Low
CAC, pre-qualified intros, and it compounds with the I7 proof flywheel.

---

## 5. The re-sequenced 0→1 plan — learning milestones, not software phases

The current build is sequenced by *software* (A→G). That's correct **engineering** order but the wrong
**venture** order: it puts acquisition last-implicitly (Phase G) and never explicitly builds toward
retention. Overlay a **learning sequence** on top of the (excellent) existing build:

```
        RETENTION-FIRST, ACQUISITION-LAST
  ┌─────────────────────────────────────────────────────────┐
  │ L0  PROVE DELIVERY   → can we book a qualified, held,    │  tenant #0 (dogfood) + 3 pilots
  │     (unit economics)   client-approved meeting at        │  Phases A–F live; I1,I9
  │                        target COGS?                      │
  │ L1  PROVE RETENTION  → do design partners renew &        │  3–5 paid pilots, weekly loop
  │     (the moat)         expand? does the outcome loop     │  I2,I3,I8; ≥1 case study
  │                        move pipeline?                    │
  │ L2  PROVE ACQUISITION→ can we acquire repeatably below   │  I7,I10; niche saturation
  │     (scale)            target CAC in the niche?          │
  └─────────────────────────────────────────────────────────┘
```

- **L0 — Prove delivery (now → ~Oct'26).** Finish E/F (outreach → Meet-verified meeting). Run the loop on
  tenant #0 **and** 3 pre-sold pilots (I9). Instrument every step. **Gate:** ≥1 qualified-held meeting
  delivered end-to-end at a COGS the model predicts. *This is the only thing the current H1 DoD actually
  measures — keep it, but make it milestone 1 of 3, not the finish line.*
- **L1 — Prove retention (Oct'26 → Mar'27 = H1).** Turn the 3–5 pilots into **design partners** with a
  weekly feedback ritual and the I2 outcome loop. **Gate:** design partners renew month-2→3, at least one
  expands (2nd ICP/region), and ≥1 public case study exists. *This is the real H1 test — retention, the
  binding constraint — not a raw signup count.*
- **L2 — Prove acquisition (H2+).** Only once L1 holds, turn on I7/I10 and niche marketing. Scaling
  acquisition before retention is proven just **scales a leaky bucket** (the growth model says so
  explicitly).

**Why invert the order:** the growth model's own read-out — *"the binding constraint is retention, not
acquisition"* and *"adding signups alone just scales a leaky bucket"* — is an instruction the current build
order ignores. Retention-first is the single biggest change this plan makes.

---

## 6. Positioning, pricing & GTM (recommended)

- **Category:** *Done-for-you qualified meetings* — **not** "AI SDR", **not** "lead-gen agency." Anchor
  against both: cheaper and unlocked vs the retainer black box; human-verified and trustworthy vs the
  AI-SDR. Lead every pitch with the trust mechanic: **"A human approves every prospect. You only pay when a
  qualified meeting actually happens. Verified, disputable, no lock-in."**
- **Pricing (evolve the locked model, don't break it):**
  - Keep **Launch $800 / Growth $1,600 + $400 activation + 48h dispute window** — all validated.
  - **Change (at GA, not mid-pilot):** flat $500 → **seniority-tiered $350/$500/$750** per qualified-held
    meeting (I6; §1.4). Pilots stay at flat $500; the ACV gate (I1) is what makes $500 trivially payable.
  - **Replace Free tier** (10 prospects, no outbound) with a **paid pilot / 14-day performance trial** that
    delivers a *real* first meeting — the outcome is the only convincing demo (C7).
  - **Add a graduation path:** past ~8–10 meetings/mo, move the client to a higher Growth tier or an
    explicit retainer — pay-per-meeting stops penciling above that volume (§1.4), so design for it.
- **Beachhead:** one niche (I3), HK/SG/TH, **ex-Vietnam.** Saturate before expanding.
- **Acquisition:** proof flywheel (I7) + referral/partner layer (I10); founder-led sales in H1.
- **Data:** Apollo + **APAC waterfall + local registries from day one** for APAC ICPs (C2); lawful-source
  discipline for SG PDPA (no scraped lists).

---

## 7. Success metrics — replace "6 signups" with a decision framework

A 0→1 venture should run on **falsifiable leading indicators with thresholds and dates**, not a lagging
count. Track weekly; each gate is a **kill / iterate / scale** decision.

| Milestone | Leading indicator | Green (scale) | Amber (iterate) | Red (kill/pivot) |
|---|---|---|---|---|
| **L0 delivery** | Positive-reply rate (per campaign) | ≥ 2% | 1–2% | < 1% after copy iteration |
| | Booked → held show rate | ≥ 70% | 60–70% | < 60% (targeting/data problem) |
| | Operator-loaded COGS per qualified meeting | ≤ 40% of blended revenue/meeting | 40–70% | > revenue |
| **L1 retention** | Design-partner renewal M2→M3 | ≥ 3 of 5 | 2 of 5 | ≤ 1 |
| | Expansion (2nd ICP/region) | ≥ 1 | 0 (but renewing) | churn |
| | Outcome loop shows influenced pipeline | ≥ 1 client with $-pipeline | qualitative only | none |
| | Public case studies | ≥ 1 | in progress | none by Mar'27 |
| **L2 acquisition** | Blended CAC vs target | ≤ target (LTV/CAC ≥ 3) | 3–5× cost | > target |
| | Adopter rate (of signups) | ≥ 20% | 10–20% | < 10% |

*Threshold basis (verified benchmarks): human-copy positive-reply averages 2.1% (total replies 5.2%), so
≥2% positive marks genuinely good performance; healthy show rates are 70–90% and <60% signals a
targeting/data problem — hence 70% green, 60% the amber floor.*

**H1 DoD (revised):** *not* "6 signups" but **"3+ paying design partners past the M2→M3 churn cliff, ≥1
expansion, ≥1 public case study, operator-loaded delivery COGS proven ≤40% of blended revenue/meeting."**
That is a real test of the binding constraint. Signups are an L2 metric; chasing them in H1 optimises the wrong stage.

---

## 8. Risks & mitigations (top 6)

| Risk | Evidence | Mitigation |
|---|---|---|
| **Cold-email decay** raises meeting COGS faster than expected. | 8.5→3.43% reply trend (§1.3) | Multi-channel (I4) + human-quality copy moat (I7) + signal triggers; monitor reply-rate as a P0 metric. |
| **APAC data thinness** starves the pipeline in the target geography. | <15% Apollo APAC (§1.5) | Waterfall + local registries from day one (C2); niche selection biased to reachable populations. |
| **Retention (adopter die-out)** caps the venture at agency-tier value. | Growth model GRR 74% | Retention engine (I2), client-quality gate (I1), expansion path (I6/§6). |
| **Deliverability blocklisting** from a bad client wrecks shared reputation. | bulk-sender rules (§1.3) | Per-client isolated lookalike domains (already planned); client-quality gate; spam <0.1% guardrail. |
| **Mistaken for a failing AI-SDR** category. | 11x/Artisan backlash (§1.2) | Position explicitly *against* autonomous AI; "human approves every meeting." |
| **Time-to-first-value churn** (fast-fails quit ~M2). | $1.2k churn LTV (growth model) | Provision-at-signature + fee-at-first-send + week-1 deliverables (I5), paid pilot with a real first meeting, weekly design-partner cadence. |

---

## 9. What to do in the next 90 days (Jul–Sep 2026)

Concrete, ordered, and mostly **non-code** — the leverage now is customer learning, not more software.

1. **Pick the beachhead niche** (I3) and write its ICP + offer thesis. *(founder, week 1)*
2. **Stand up the client-quality gate** (I1) — a Brief rubric + threshold; reuse Phase-B rubric pattern. *(small build)*
3. **Pre-sell 3–5 paid pilots** in the niche (I9), fulfilled on the live A–D console + operator sending. *(founder sales)*
4. **Sign pilots early and provision their lookalike domains at signature** (I5) so every pilot's domains
   are long-warmed before Oct; write fee-at-first-send + "meetings in weeks 3–6" into the pilot contract. *(ops + contract, parallel to the existing `getholdslot.com` warm-up)*
5. **Finish E/F** (outreach → Meet-verified meeting) — the delivery proof (L0). *(the existing build)*
6. **Wire the retention/outcome loop** (I2) — one table + feedback links; make it live before the first meeting lands. *(small build)*
7. **Instrument the L0/L1 metrics** (§7) into Performance Summary. *(small build)*
8. **Add APAC waterfall + local-registry sourcing** for the niche's geography (C2). *(build — was "post-MVP")*
9. **Draft the tiered pricing + paid-pilot offer** (I6, §6) and update the site copy/positioning against AI-SDR. *(founder + web)*
10. **Line up 2–3 referral partners** (I10) for when L1 holds. *(founder, low effort now)*

**Sequencing principle:** *prove delivery (L0) on real pilots → prove they renew (L1) → only then spend on
acquisition (L2).* Retention-first, acquisition-last.

---

## Appendix — sources

Research gathered Jul 2026 via multi-source web search; claims adversarially verified (39/41 verifier
votes upheld). Key sources by theme:

- **Agency pricing / incumbents:** leadgen.cience.com/belkins · isaless.com/pay-per-appointment · prospeo.io (2026 pricing guide) · salescaptain.io · saleshive.com · outboundsalespro.com · clutch.co/profile/belkins · trustpilot.com/review/belkins.io
- **AI-SDR backlash:** techcrunch.com (11x, 2025-03-24; Artisan, 2025-04-09) · sifted.eu (11x) · leadgen-economy.com (AI-SDR cancellation forensics) · coldreach.ai (Artisan review) · onlycfo.io
- **Cold-email channel health:** instantly.ai/cold-email-benchmark-report-2026 · digitalapplied.com (100k AI-vs-human) · redsift.com (bulk-sender) · Microsoft Tech Community (Outlook high-volume rules) · unifygtm.com · belkins.io/blog/cold-email-response-rates
- **Buyer complaints / disputes:** linkeddit.com (Reddit roundup) · leadgen-economy.com (dispute guide) · nerdyjoe.com · clutch.co
- **Emerging models:** growleads.io (signal-based) · unifygtm.com (intent-based)
- **APAC gaps / compliance:** gruppointegritas.com (Asian data gap) · b2bdataindex.com (44-nation matrix) · ultragrowthmedia.com (SG agencies) · imisofts.com (SG PDPA)

> **Caveats:** several pricing/benchmark sources are vendor blogs or comparison listicles (directional, not
> audited); Instantly's benchmark is large-sample but vendor-selected; the dispute-rate norms come partly
> from consumer lead-gen (analog, not direct B2B evidence). Numbers are triangulated across ≥2 sources
> where cited as ranges. Treat as decision-grade market intelligence, not audited fact.
