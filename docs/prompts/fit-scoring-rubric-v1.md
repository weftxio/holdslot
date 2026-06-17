# Fit-Scoring Rubric v1 (locked 2026-06-14)

Machine-consumable transcription of `fit-scoring-framework.html` (the design artifact is the
source of truth for *intent*; this file is what the C3 scorer consumes as **data**, editable
without code). Stored as `sourcing_doc` type `fit_rubric`, version 1.

> **Shape: gates → score → tier.** Hard gates run first (binary, never scored). Survivors are
> scored across 4 weighted dimensions = 100 points. The score collapses to a tier. **The client
> never sees the number — only the tier + the reason tags.**

## 1. Gates (binary disqualifiers — applied before scoring, each logged for audit)

A candidate failing ANY gate is removed and never enters the score pool, a batch, or an approval page.

| Gate | Source |
|---|---|
| On any exclusion list (customer · active deal · competitor · do-not-contact) | Brief §5 + `doNotContact` |
| Geography out of scope (outside target regions) | Brief §2 / spec `locations` |
| Negative ICP (B2C-only when client is B2B, deal too small, etc.) | ICP doc |
| No verifiable contact path (email hard-bounces / cannot validate at all) | enrichment |

**Gate vs. score boundary (locked):** *no email at all / hard bounce* = **gate** (removed). A
*risky / accept-all* email is **not** gated — it is scored low in the Data dimension (3/6). This keeps
"thin data" a graded penalty, not a silent drop, while a guaranteed bounce never reaches a warmed domain.

## 2. Scoring — 4 dimensions, 100 points

Default weights `40 / 30 / 20 / 10`; **per-client config** (a tech-dependent client can raise tech/
company). Each sub-criterion scores full / partial / zero on its own rule, summed, then the dimension
is **capped at its max** (no single attribute inflates the rest).

### Company fit — 40
| Sub-criterion | Max | Full | Partial | Zero | Source |
|---|--:|---|---|--:|---|
| Industry / vertical | 16 | exact listed vertical (16) | adjacent vertical (8) | 0 | §2 |
| Company size band | 12 | inside band (12) | one band off (6) | 0 | §2 |
| Maturity / stage | 8 | matches (8) | adjacent (4) | 0 | §2 |
| Tech stack match | 4 | confirmed (4) | unknown (2) | 0 | §2 (optional) |

### Persona fit — 30
| Sub-criterion | Max | Full | Partial | Zero | Source |
|---|--:|---|---|--:|---|
| Job title | 14 | exact listed title (14) | equivalent / adjacent (7) | 0 | §3 |
| Seniority | 8 | target level (8) | one level off (4) | 0 | §3 |
| Department | 5 | right function (5) | — | 0 | §3 |
| Economic-buyer bonus | 3 | is the buyer at this company size (3) | — | 0 | §3 |

### Timing signals — 20
| Sub-criterion | Max | Full | Partial | Zero | Source |
|---|--:|---|---|--:|---|
| Primary buy trigger | 12 | fired <3 months ago (12) | fired 3–6 months ago (6) | 0 | §4 |
| Secondary signal | 6 | active hiring / news (6) | soft (3) | 0 | §4 |
| Engagement signal | 2 | site visit / prior open (2) | — | 0 | enrich |

### Data quality — 10 (deliverability self-defense, not fit)
| Sub-criterion | Max | Full | Partial | Zero |
|---|--:|---|---|--:|
| Email deliverability | 6 | verified (6) | accept-all / risky (3) | 0 |
| Profile completeness | 4 | complete & fresh (4) | partial (2) | 0 |

## 3. "Unknown" policy per field (locked — the HTML flags this as a required decision)

After enrichment, a field that is still unknown scores:
- **Firmographic match fields** (industry, size, maturity, title, seniority, department): **0** — we do
  not award a match we cannot see. (Cheap, enrich-then-score where the data exists; otherwise 0.)
- **Tech stack**: **partial (2)** — optional signal, absence is not the prospect's fault.
- **Engagement**: **0** — it is a bonus, not a baseline.
- **Email**: risky/accept-all → **3**; cannot validate at all → **gate-out** (§1).

## 4. Tiers & actions (thresholds are policy — tuned as outcome data accumulates)

| Tier | Score | Action |
|---|---|---|
| **Strong** | ≥ 75 | Batched first · deepest personalisation · lead with the matched trigger |
| **Good** | 55–74 | Standard sequence & cadence |
| **Moderate** | 40–54 | Volume-fill only · consider not showing at all |
| **Below** | < 40 | Discarded silently · never shown to the client |

## 5. Storage contract (the moat — store components, not just totals)

Each `prospect` record holds the **12 line-item points + reason tags** in `fit_components` (JSONB),
plus `fit_score` (int) and `fit_tier`. Three consumers, one structure: the approval page renders the
tags ("why they matched", Phase D); a billing dispute pulls the same record (Phase F); the learning
loop regresses components against reply/meeting outcomes (Phase E) → re-weight per vertical.

## 6. How the scorer runs it (C3)

`prospect_fit` purpose through the B3 adapter: Claude classifies each sub-criterion **against this fixed
rubric** (full/partial/zero) returning the points + a one-line justification per dimension — strict
`json_schema`. Deterministic where possible (size band, geography); LLM for the judgment calls
(adjacent vertical, equivalent title). The **partial-match maps** (what counts as "adjacent vertical" /
"equivalent title") are seeded per client at onboarding so they are not re-litigated per prospect.
