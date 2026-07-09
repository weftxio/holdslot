# HoldSlot — Prospect Scoring Spec (v2)

Replaces the 0–100 `AI Score` with a 4-label system.

**Changes from v1**, after verifying 4 of 66 companies against the web:
1. New `is_active` gate — CXA Group has been in liquidation since Sept 2025 and Apollo still reports it as healthy
2. `outbound_gap` redefined around **distribution model**, not headcount
3. Headcount demoted from gate to signal — Apollo's field is unreliable

---

## 1. Schema

**Remove:** `AI Score` (0–100 integer)

**Add:**
- `label` — one of four values
- `icp` — `A`, `B`, or `null`
- `reason` — short string, always populated
- `subscores` — `{deal_fit, outbound_gap, trigger, reachability}`, each 1–5
- `flags` — array, optional
- `verified` — bool. `false` until a human or search confirms

---

## 2. The four labels

| Label | Meaning | UI |
|---|---|---|
| `contact_now` | Strong fit, contact this cycle | Expanded |
| `contact_soon` | Fits, but a gap or unknown | Expanded |
| `low_fit` | Our judgment says no. Client may override | Collapsed |
| `excluded_by_rules` | A rule removed it | Collapsed, shows rule |

Two are actions. Two are footnotes. **Never delete a row** — every sourced company gets a label and a reason.

---

## 3. Processing order

Stop at first match.

```
1. Liveness check → excluded_by_rules   [NEW]
2. Rule check     → excluded_by_rules
3. Data check     → low_fit
4. ICP match      → low_fit if no match
5. Score          → contact_now / contact_soon / low_fit
```

---

## 4. Step 1 — Liveness (new, and the most important addition)

Enrichment data lags reality by months. Apollo showed CXA Group at 65 staff and $63M revenue while it was nine months into voluntary liquidation.

Before scoring, check for:

| Signal | Action |
|---|---|
| "liquidation", "wound up", "ceased operations", "shut down", "dissolved" | `excluded_by_rules`, reason `"company defunct"` |
| Acquired and absorbed into parent | `excluded_by_rules`, reason `"acquired — no longer independent"` |
| Website dead or parked | `excluded_by_rules`, reason `"no active web presence"` |
| Last news item > 24 months old | flag `stale_record`, do not exclude |

Implementation: a single web search on `"{company} liquidation OR acquired OR shut down"` per row before scoring.

Cost: one search per row, 150 rows/month at the Launch tier. Worth it — the alternative is emailing a company in liquidation under the client's brand, which is exactly the failure the client-approval step exists to prevent.

**This gate did not exist in v1 and nothing else catches it.**

---

## 5. Step 2 — Rules (client-defined)

From client intake. Not our inference.

```python
RULES = {
    "market": "B2B",
    "geographies": ["Hong Kong", "Singapore", "Thailand"],
    "excluded_companies": [],   # client's "who to avoid"
}
```

| Condition | reason |
|---|---|
| `market == "B2C"` and rule is B2B-only | `"rule: B2B only"` |
| `hq_country not in geographies` | `"rule: outside target geography"` |
| `name in excluded_companies` | `"rule: client exclusion"` |

**Market tag is unreliable.** Luma Health is tagged B2C but sells group health insurance to companies, NGOs, embassies, and international schools with a 3-employee minimum. Before excluding on B2C, check whether a B2B line exists. If it does, the company is `Both` — do not exclude.

Geography uses **HQ from the description**, not the HQ field. Known mismatches:
- Gateway Search — field says Singapore, description says Blue Bell, Pennsylvania
- Knoldus — field says Singapore, description says Ontario, Canada
- Psicología y Mente — field says Singapore, is a Spanish-language site

On disagreement, trust the description and set flag `hq_mismatch`.

Rows tagged `Complex` in source data are not B2C. Treat as B2B.

---

## 6. Step 3 — Data check

`low_fit`, reason `"data_unusable"`, if any of:

- `industry` null or `—`
- `hq_country` null
- `website` is a wire service or aggregator (`newswire.ca`)

**Headcount is no longer a gate.** Bytesforce reads 46 (ContactOut), 60 (Apollo), 200–500 (SignalHire). The field cannot carry a hard rule.

---

## 7. Step 4 — ICP match

```python
ICP_A = {
    "industries": ["insurtech", "insurance", "healthtech", "wellness"],
    "geographies": ["Hong Kong", "Singapore", "Thailand"],
}

ICP_B = {
    "industries": [
        "strategy consultancy", "IT services", "corporate services",
        "marketing agency", "creative agency", "digital agency",
        "executive search", "specialist recruiting", "fractional CFO",
    ],
    "geographies": ["Hong Kong", "Singapore", "Thailand"],
}
```

Match on industry **and** geography.

**Read the description, not the `industries` field.** Apollo tags Blackpanda "computer & network security"; they are a Lloyd's of London-accredited coverholder underwriting cyber insurance. That is ICP A.

No match → `low_fit`, reason `"wrong vertical"`.

**Blocking gap:** `company_size` and `stage` were left blank on both ICP intake forms. Until filled, headcount is a signal only, feeding `reachability` — no size gate runs.

This is not a safe default. Kerry (98), KOS (150), and Exasoft (110) currently sit on a boundary that was invented, not specified. Filling this field will move roughly a third of the list. Get it from the client before the first send.

---

## 8. Step 5 — Score

Four axes, 1–5. Sum 4–20.

```python
def label_from_score(total):
    if total >= 16: return "contact_now"
    if total >= 10: return "contact_soon"
    return "low_fit"
```

### deal_fit — does ACV support $500/meeting?

| | |
|---|---|
| 5 | Enterprise contracts, six figures |
| 3 | Mid-ticket. Blackpanda's IR-1 is USD 8,000/yr for 800 endpoints |
| 1 | Self-serve. Voiso starts at $49/mo |

### outbound_gap — do they need us? **[redefined]**

v1 inferred this from headcount. Wrong. The real signal is **how they currently acquire customers**:

| Score | Distribution model | Example |
|---|---|---|
| **5** | Word-of-mouth / referral only | Bytesforce: grown "purely through Word of Mouth" |
| **4** | Inbound / product-led, no demand gen | Pro5.ai: client must arrive with a job description |
| **3** | Conference and event-led BD | Bytesforce also does ITC Asia, ITC DIA Europe |
| **2** | Broker or reseller network | Luma: sells via Pacific Prime |
| **1** | Named channel partners, or investor-as-distributor | Blackpanda: IR-1 distributed by Singtel, Macroview, CTM — and Singtel Innov8 co-led their raise |

A partner-led company has already solved distribution. They are the hardest sell for outbound-as-a-service.

Also score down if hiring for sales roles — Luma is currently hiring a Business Development Manager, Sales Consultant, and Client Solutions Executive. They are building in-house.

### trigger — in-market now?

| | |
|---|---|
| 5 | Raise, exec change, new market, rebrand, >20% growth |
| 1 | Flat, no events |

Rebrand counts. Pro5.ai renamed from Mangtas in Feb 2024 — repositioning needs new pipeline.

### reachability — can we reach the buyer?

| | |
|---|---|
| 5 | Founder-led, small team |
| 1 | 1000+ staff, layered |

Headcount feeds here, and only here. Treat as approximate.

---

## 9. Reason strings

Always populated. Short.

```
"company defunct"
"acquired — no longer independent"
"rule: B2B only"
"rule: outside target geography"
"rule: client exclusion"
"data_unusable"
"wrong vertical"
"too large"
"partner-led distribution"
"building in-house sales"
"not a buyer (non-profit / gov)"
"fits ICP A — <one clause>"
"fits ICP B — <one clause>"
```

---

## 10. Flags

Non-blocking. Small warning marker in UI.

| Flag | Trigger |
|---|---|
| `hq_mismatch` | HQ field disagrees with description |
| `headcount_uncertain` | Sources disagree by >2x |
| `revenue_implausible` | Off by >10x from description |
| `founding_date_conflict` | `Est.` year disagrees with description |
| `competitor_adjacent` | Overlaps HoldSlot's offer |
| `partner_led` | Named distribution partners found |
| `stale_record` | No news in 24 months |

Known bad rows:
- **Amicorp** — `$59B`, description says ~$430M
- **Manus AI** — `Est. 2018`, description says founded 2025
- **Hytech** — `Est. 2022` with $106M revenue and 1,100 staff
- **Bytesforce** — headcount 46 / 60 / 200–500 depending on source; API count listed as 1,300, company now says 2,700+

---

## 11. UI

Sort: `contact_now` → `contact_soon` → `low_fit` → `excluded_by_rules`

**Expanded rows** show:
```
Company · Headcount · Geo · ICP badge · [verified ✓]
Subscore bar (4 segments)
One-sentence reason
Trigger line — the email hook
```

Not the Apollo blurb. That goes behind a click.

**Collapsed rows** — one summary line:
```
Low fit (32)                    ▸
Excluded by your rules (17)     ▸
```

Remove the standalone `ICP A/B` column. It currently disagrees with the score — CXA is ICP A at 55, EngageRocket is ICP B at 55. Fold into the badge.

---

## 12. Expected output — current 66 rows

Use as a test fixture, not as ground truth.

**Verified: 5** — Bytesforce, Blackpanda, CXA, Luma, Pro5.ai.
**Unverified: 61** — marked `verified: false`.

Verification moved 3 of the first 4 rows checked. The `low_fit` and `excluded_by_rules` buckets are almost certainly carrying more dead companies, more wrong HQs, and more B2C tags on firms that have a B2B line. Nobody reads collapsed rows, so that is where errors will sit. Verify before the first send, not after.

**5 contactable rows from 66 sourced** — down from 10 in v1, and the number will move again. Under the $800/mo Launch tier that is 150 prospects to surface perhaps a dozen. The sourcing query is the bottleneck, not the scoring. A better rubric makes the problem visible; it does not fix it. Fix the query first.

### contact_now (5)

| Company | ICP | Geo | Reason | ✓ |
|---|---|---|---|---|
| Bytesforce | A | SG | Insurtech, Celent Luminary, grown "purely through word of mouth" — no SDR function | ✓ |
| Pro5.ai | B | SG | Built AI platform to *avoid* hiring recruiters; inbound-only, 20–30% of salary ACV | ✓ |
| Talent Blue Search | B | HK | Executive search, HK | |
| Space Executive | B | SG | Executive search, Sequoia/Goldman clients | |
| RONIN Research | B | HK | Market research consulting, +84.6% growth | |

**Bytesforce hook:** the word-of-mouth admission. They have a Chief Growth Officer and do conference BD (ITC Asia, ITC DIA Europe). No outbound.

**Pro5.ai hook:** they explicitly rejected the recruitment-agency route because it "would require an army of manual recruiters." HoldSlot is that argument applied to sales. Flag `competitor_adjacent` and `partner_led` (SGTech, XA Network, Remote.com) — expect the partner objection.

### contact_soon (7)

| Company | ICP | Geo | Gap | ✓ |
|---|---|---|---|---|
| Blackpanda | A | SG | Lloyd's coverholder, real ICP A — but IR-1 distributed by Singtel, Macroview, CTM. Singtel Innov8 is also an investor | ✓ |
| Luma Health | A | TH | Group insurance for companies/NGOs/embassies. But hiring BDM + Sales Consultant, and sells via Pacific Prime | ✓ |
| The Edge Partnership | B | HK | Specialist recruiting, -12.3% growth — needs pipeline | |
| Aquis Search | B | HK | Executive search, HK | |
| Kerry Consulting | B | SG | Exec search, right geo | |
| Exasoft | B | SG | Staffing + IT services, both verticals | |
| Rapsys Technologies | B | SG | IT services + BPO, thin ACV signal | |

### low_fit (32) — collapsed

**wrong vertical (15):** Manus AI, Doozy Robotics, Gaussian Robotics, ZStack, Tinvio, Voiso, Lynx Analytics, Antalpha, Wonder, Giift, GlobalSignIn, BidMatrix, Better HR, Openspace Capital, LINE MAN Wongnai

**too large (13):** Singtel, NCS Group, Changi Airport Group, PERSOL APAC, VISTRA, Optimum Solutions, CrimsonLogic, LPS, Hytech, ADVANCE.AI, TO THE NEW, Amicorp Group, HKT Digital Ventures

**not a buyer (3):** Singapore College of Insurance, FinTech Association of HK, Financial Services Development Council

**has existing sales org (3):** Tech in Asia, Asian Private Banker, China Travel News

**near size ceiling (2):** KOS International, AlwaysHired

**wrong vertical, adjacent (2):** Omni HR *(HR tech, not a listed vertical)*, EngageRocket *(wellness-adjacent)*

**data_unusable (1):** AddSecure Smart Transport — no geo, no industry, no headcount

### excluded_by_rules (17) — collapsed

**company defunct (1):** CXA Group — voluntary liquidation, shareholder vote 25 Sept 2025 ✓

**rule: B2B only (11):** Bowtie, Blue Insurance HK, Avo Insurance, Tahoe Life, HL Assurance, OONA Insurance, SingSaver, Enjin, The Luxe Nomad, Centaline, Nomad Capitalist

*Luma Health removed from this list — has a B2B group line.*

**rule: outside target geography (4):** Gateway Search *(Pennsylvania)*, Knoldus *(Ontario)*, Psicología y Mente *(Spanish-language, HQ field wrong)*, AddSecure *(no country)*

**testing row (1):** HoldSlot
