# People Score Rubric v1 (scoring v2, 2026-07-09)

Machine-consumable axis anchors for the **stage-2 people scorer** (`prospect_score_v2`). Consumed as
**data** (founder-editable without code) — seeded as `prompt` stage `prospect_score`, version 1.

> **People tier — HoldSlot extrapolation.** `docs/initial-build-plan.md §D+.2` defines the company
> tier only; this mirrors its shape onto a person-shaped axis set (four axes, 1–5, sum 4–20, same
> ≥16 / ≥10 thresholds). **No web search per person** (the token win — the company already carries a
> web-verified label). **The company label CAPS the person** server-side: a person can never be more
> contactable than their account (excluded company → `excluded_by_rules "parent company excluded"`;
> `low_fit` company → `low_fit` person; `contact_soon` company → no `contact_now` person). Do NOT
> re-judge the company here — score only the individual.

## persona_fit — does the title/role match the decision-maker we target?

| Score | Anchor |
|---|---|
| 5 | Squarely the persona we search for (the exact function + level in the ICP's people scope). |
| 3 | Adjacent function or one level off. |
| 1 | Wrong function / wrong department for this deal. |

## authority — power to convert a deal

| Score | Anchor |
|---|---|
| 5 | Economic buyer — owns the budget and the decision. |
| 3 | Influencer / recommender — shapes it, doesn't sign. |
| 1 | No authority (IC, or too junior to move a deal). |

## trigger — a person-level in-market signal

| Score | Anchor |
|---|---|
| 5 | Recent role change, a team they are visibly building, a fresh mandate. |
| 1 | No personal signal. |

## reachability — can we actually reach them?

| Score | Anchor |
|---|---|
| 5 | A real, deliverable email present; not buried in a layered org. |
| 1 | No usable contact path, or many gatekeeper layers deep. |

A field still unknown after enrichment scores **low, not high**. `reason` is one short client-facing
sentence on why this person is (or is not) the right contact; no number. Emit `flags` only when
something is genuinely off, otherwise `[]`.
