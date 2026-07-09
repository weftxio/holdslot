# Company Score Rubric v1 (scoring v2, 2026-07-09)

Machine-consumable axis anchors for the **stage-1 company scorer** (`company_score_v2`), transcribed
from `docs/holdslot-scoring-spec-v2.md` §8. Consumed as **data** (founder-editable without code) —
seeded as `prompt` stage `company_score`, version 1. The scorer reads the latest version as its
scoring framework; a re-weighting is a doc edit, never a code change.

> **Shape (spec §3):** the free deterministic gates (liveness · client rules · data check · size
> rule · ICP match) run *around* this rubric — the server owns them. This rubric only supplies the
> **four 1–5 axis anchors** the model scores a gate-survivor on. The total (sum 4–20) and the label
> (≥16 `contact_now` · ≥10 `contact_soon` · else `low_fit`) are computed server-side; the model
> never sets the label. The client never sees the number — only the label + the one-line reason.

## deal_fit — does the deal size support $500 / booked meeting?

| Score | Anchor |
|---|---|
| 5 | Enterprise contracts, six figures. |
| 3 | Mid-ticket (e.g. Blackpanda's IR-1 is ~USD 8,000/yr for 800 endpoints). |
| 1 | Self-serve / low ticket (e.g. Voiso starts at $49/mo). |

## outbound_gap — do they NEED outbound-as-a-service?

The signal is **how they currently acquire customers**, not headcount. A company that has already
solved distribution is the hardest sell for outbound-as-a-service.

| Score | Distribution model | Example |
|---|---|---|
| 5 | Word-of-mouth / referral only | Bytesforce — grown "purely through word of mouth" |
| 4 | Inbound / product-led, no demand gen | Pro5.ai — the client must arrive with a job description |
| 3 | Conference- and event-led BD | Bytesforce also does ITC Asia, ITC DIA Europe |
| 2 | Broker or reseller network | Luma — sells via Pacific Prime |
| 1 | Named channel partners, or investor-as-distributor | Blackpanda — IR-1 via Singtel / Macroview / CTM; Singtel Innov8 co-led the raise |

**Score DOWN** if they are hiring in-house sales (e.g. Luma hiring a BDM + Sales Consultant + Client
Solutions Executive — they are building the function in-house).

## trigger — are they in-market now?

| Score | Anchor |
|---|---|
| 5 | A raise, exec change, new market, rebrand, or >20% growth. |
| 1 | Flat, no events. |

A **rebrand counts** — Pro5.ai renamed from Mangtas in Feb 2024; repositioning needs new pipeline.

## reachability — can we reach the buyer?

| Score | Anchor |
|---|---|
| 5 | Founder-led, small team. |
| 1 | 1000+ staff, layered org. |

Headcount feeds **here, and only here** — treat as approximate (the field is unreliable).

## ICP match — read the DESCRIPTION, not the `industries` field

Apollo's `industries` tag is often wrong (it tags Blackpanda "computer & network security"; they are
a Lloyd's-accredited coverholder underwriting cyber insurance → ICP A). Judge the description against
the ICP definitions supplied in the targeting context. Set `icp_match.icp` = `A` / `B` / `none`; no
match → the server labels the row `wrong vertical`. `reason` for a match reads `fits ICP A — <clause>`.
