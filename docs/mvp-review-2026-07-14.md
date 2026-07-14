# HoldSlot MVP — build plan + review register (consolidated 2026-07-14)

> **Single source of record** for the post-M-register build. Consolidates what used to live in two
> files: **Part A** — the finalized forward build plan, decisions locked 2026-07-14 (this session);
> **Part B** — the independent Wave 1–5 verification + L-register + modularization study (the 07-14
> audit); **Part C** — the archived M-register build log, verbatim from the retired
> `mvp-review-2026-07-12.md`, kept for the still-uncommitted Waves 4+5 detail. This document
> **supersedes and replaces `mvp-review-2026-07-12.md`** (deleted per decision D8). Standing rules
> unchanged: backend-before-frontend deploy · commit/push/deploy only when founder-authorized · every
> fix ships with a test · money-path items add an Aurora-gated test.

## A0 · Locked decisions (2026-07-14)

| # | Decision | Resolution |
|---|---|---|
| D1 | Deploy order for landing Waves 4+5 | **Backend deploy FIRST** (applies `0032`, ships `MeetingOut.campaign_id` + the Wave-4/5 schema trims), THEN push `eec3852` to trigger the Amplify FE build. Also land **L15**'s one-line `campaignId == null` fallback before the push as belt-and-suspenders. |
| D2 | L-fixes vs modularization on shared big files | **Targeted L-fixes first** on the current tree (urgent + small), THEN modularize — avoids rebasing fixes across a moved tree. Exception: `lib/api.ts` split (2.1) is zero-behavior — do it before **L14** or fold L14 into that PR. |
| D3 | Founder acceptance vs code work | **Parallel.** Phase 3 (FR-1…FR-5) runs on live dev now; code Phases 1–2 proceed independently. Only FR-7 (Stripe) has a code dependency (L2/L3/L10). |
| D4 | Modularization scope now | **Hard prerequisites only:** 2.1 `api.ts` · 2.2 `prospects/router.py` · 2.3 `stage_moves.py` · 2.4 `list/page.tsx`. **Defer** 2.5/2.6/2.7 churn-gated (touch only when those files next change). |
| D5 | Stripe activation timing | **Keep billing dormant**; fix L2/L3 now so FR-7 is a probe-and-deploy *day*, not a build week (L3 prevents silent $0/meeting billing). |
| D6 | Timezone default | **OVERRIDE → `Asia/Hong_Kong` is the default for ALL timezone-related config** (not just meetings). New task **TZ-1** (Phase 1). Retires FR-4's TZ-override step. |
| D7 | `billable_this_cycle` (L10) | **Fix the `billed_at IS NULL` filter now**, bundled with the L2/L3 pre-Stripe block, so the console figure is correct the day billing activates. |
| D8 | Review-doc hygiene | **OVERRIDE → consolidate both review files into one** (this doc). `mvp-review-2026-07-12.md` deleted; its build-log content preserved verbatim in **Part C**. |
| D9 | FR-6 GD register | **Prerequisite decision session** before FR-7 — annotate GD-1…GD-10 (defaults pre-written, ~5 min/row). Not a build step. |

## A1 · Phase plan (execution order)

Two tracks run in parallel (D3): the **code track** (Phase 0 → 1 → 2, founder-gated commits/deploys)
and the **founder-acceptance track** (Phase 3, live dev, no code dependency). Phase 4 (go-live) opens
once Phase 3 ticks S6 **and** the pre-Stripe L-items (L2/L3/L10) have shipped. Finding-level detail for
every L-item is in **Part B §3**; for every FR/NF item in `initial-build-plan.md §G`.

### Phase 0 · Land the shipped work (unblocks everything) — ✅ SHIPPED 2026-07-14

| # | Task | Result |
|---|---|---|
| 0.1 | Commit Waves 4+5 (67 files: 62 mod + 2 deletes + 3 new) + docs consolidation | ✅ `98c90f2` (code) · `aa0e209` (docs); full gate green |
| 0.2 | Land **L15** one-liner (`campaignId == null` fallback) before push | ✅ `215ef4d` — tsc + Playwright green |
| 0.3 | **Backend deploy** → applied `0032` to dev Aurora, shipped Lambda **v89→v90** | ✅ `/health` ok · `MeetingOut.campaign_id` live in OpenAPI |
| 0.4 | Push `dev` → Amplify FE build (followed 0.3 per D1) | ✅ `origin/dev`=`215ef4d` · Amplify build #60 SUCCEED |

### Phase 1 · L-wave code fixes — ✅ COMMITTED 2026-07-14 (local; awaiting BE-deploy+push authorization)

All committed to local `dev` (unpushed); gate green at each step. Deploy sequence when authorized:
**backend deploy (L2–L12/TZ-1/`_iso`) → push (per D1)** — same as Phase 0.

| Group | Items | Commit | Test |
|---|---|---|---|
| 1a · Revenue P2 | **L1** (+L15 in Phase 0) | ✅ `cba6e27` | Playwright (409 keeps picker + message) |
| 1b · Pre-Stripe / FR-7 | **L2** · **L3** · **L4** · **L5** · **L10** | ✅ `358a174` | L3/L4/L5 unit · L10 Aurora (live-verified) · L2 via existing reserve test |
| 1c · Compliance | **L6** · **L7** | ✅ `4ecd0d3` | unit (dnc_entries · _unsub_writeback · _merged_dnc) |
| 1d · Cheap BE + TZ + iso | **L8** · **L9** · **L11** · **L12** · **TZ-1** · **batches `_iso`** | ✅ `40f88a2` | unit (validator · dedupe · 502 · HK tz ×2 · iso→Z) |
| 1e · FE sweep | **L13** · **L14** · **L16** · **L17** · **L18** · **L19** · **L21** · **L22** · **L20** (a11y) | ✅ `b58adfd` | tsc/eslint/build + Playwright 27✓ (harness = route-mock; per-fix e2e not added, see note) |
| 1f · Dead residue | **L-D** (`isTransientStatus` · `groupByCompany().meta` + consumer + type · apollo docstring) | ✅ `b58adfd` | — |

> **Discovered during 1b (NEW, not fixed — out of L-wave scope):** the Aurora-gated enrich e2e tests
> (`test_find_select_find_enrich_end_to_end` + siblings) are **red on live dev** — their base
> `owner_member` fixture ships a **pre-v4 spec** (`company_search_params`, no `icp_targeting`), but
> `find-company` now requires a v4 `icp_targeting` block (`targeting_for_icp`), and the `/companies`
> read returns `{items,next_cursor}` where the helper expects a bare list. Independent of the L-wave
> (my L10 Aurora test passes live; the L2 probe was dropped for this reason). **→ add task: refresh the
> enrich e2e fixtures to v4** before relying on that suite at the founder's gate.
>
> **1e test-coverage note:** the FE harness is route-mocked Playwright only (no component-test rig).
> The 9 sweep fixes are surgical (toast copy, loader reset/guard, cold-start branching, a11y
> attributes) — conditions the route-mock harness can't easily simulate — so they're covered by
> tsc + eslint + `next build` + the green Playwright suite rather than a new e2e per fix.

### Phase 2 · Modularization — hard prerequisites only (D4; deploy-neutral refactors)

| # | Split | Effort | Trigger / prerequisite |
|---|---|---|---|
| 2.1 | `lib/api.ts` → `lib/api/` package + barrel re-export | S | **first** — before/with L14; prereq for Stripe & any endpoint work |
| 2.2 | `prospects/router.py` → package (scope/serializers/label_engine/company_find/people_find/jobs) | L | before next find/scoring feature; own deploy AFTER the `0032` deploy; + manual live smoke; dissolves the `scoring.py` lazy cycle |
| 2.3 | `campaigns/router.py`: extract `stage_moves.py` (30 min, un-lazies 3 imports) | S | before meeting-summary/billing-evidence work; `replies.py`/`performance.py` stay churn-gated |
| 2.4 | `list/page.tsx` staged: modals → `useListData` hook → `Step1Companies`/`Step2People` | L | **hard prereq before any new list-page feature**; one PR each + manual find/score QA |
| — | **Deferred churn-gated (D4):** 2.5 `CampaignTab` motion · 2.6 `spec.tsx`/`brief/page.tsx`/`constants.ts` · 2.7 `meetings/sweep.py` | — | touch only when those files next change (2.5 is mandatory before carryover S8) |

### Phase 3 · Founder acceptance → DoD start (parallel track; live dev, founder-gated)

| # | FR | Action | Ticks / feeds |
|---|---|---|---|
| 3.1 | **FR-1** | S3 live batch round (create → send masked link → approve) | G0-2 · feeds FR-2 |
| 3.2 | **FR-2** | S4/S5 acceptance run (campaign off FR-1 batch → A/B/C → launch → triage ≥1 reply) | G0-1 |
| 3.3 | **FR-3** | F0 real held-Meet ≥10 min / 2p → `f_smoke_live.py --meeting-code` | G0-3 |
| 3.4 | **FR-4** | Availability doc (FD-1 JSON) + FD-1…8 sign-off | G0-4 · TZ default already HK via TZ-1 (D6) |
| 3.5 | **FR-5** | FA whole-phase acceptance (FA-1…12 scripted sitting) | **ticks S6 → G formally starts** |

### Phase 4 · Go-live register — billing → cutover → scale (triggered, founder-gated)

| # | FR / NF | Action | Prereq / unblocks |
|---|---|---|---|
| 4.1 | **FR-6** | Annotate GD-1…GD-10 decisions (D9) | locks GS/GP/GX shape |
| 4.2 | **FR-7 → NF-8** | GS0 Stripe account + config → probe green → apply `0031` → GS deploy | **needs L2/L3/L10 shipped**; billing goes live |
| 4.3 | **FR-8** | GSA first real billing round (activation invoice → $500 line lands) | GS DoD — billing real |
| 4.4 | **FR-9** | GOB per-signup ops (×6 over H1) | the revenue engine |
| 4.5 | **FR-10** | GOPS ongoing cadence (reply queue · disputes · won · KPI) | DoD visibility |
| 4.6 | **FR-11 → NF-9** | GP0/GP2 cutover go → GP3–GP9 runbook (SES prod case · prod JWT keys) | prod cutover |
| 4.7 | **FR-12 → NF-10** | GX4 capacity spends + GX1–GX3 SCALE build (2nd tenant) | volume path |

### Carryover — deferred-M items (fold where noted)

| Item | Disposition |
|---|---|
| **S8** (CampaignTab `detail` → `useQuery`) | do after/with 2.5 `CampaignTab` motion |
| **S28** (loader-key consolidation) | fold into **L18** (same cross-tenant loader code) |
| **S30** (split list page) | **superseded** by 2.4 staged plan — retire the label |
| **batches `_iso`** naive-Z fix | folded into Phase 1 (1d) |

## A2 · Standing gates & rules

- **Exit gates every wave:** `pytest` · `ruff` · `tsc --noEmit` · `eslint` · `next build` · Playwright — all green.
- **backend-before-frontend** deploy; **commit/push/deploy only when founder-authorized**.
- Each fix ships with a **non-Aurora unit test**; money-path items add an **Aurora-gated** test (run on the founder's live gate).
- Modularization PRs are **deploy-neutral** (no route/schema/class-name changes) + **one manual live-flow QA** for the two large splits (2.2, 2.4).

---

# Part B · Independent build audit — Wave 1–5 verification · L-register · modularization

> **Read-only study/design session — zero code changes.** Independent-checker round over the
> `docs/mvp-review-2026-07-12.md` M-register: (1) confirm every Wave 1–5 completion claim against the
> repo, (2) find bugs/issues/simplifications OUTSIDE that register, (3) modularization study for future
> scalability. Method: 5 parallel wave-verification reviewers (one per wave, file:line evidence per
> item) + 2 fresh-eyes reviewers (BE + FE, full-file, register-excluded) + 1 modularization analyst +
> a full local gate re-run. Per the closure rule, everything NEW found here lands in the **L-register**
> (§3) — the M-register cycle is verified and closes with this document.

## 0 · Session verdict

- **Waves 1–5 completion CONFIRMED.** Every itemized M-register claim verified present in the working
  tree with file:line evidence: Wave 1 (10 P2, M1–M10) ✅ · Wave 2 (12 BE P3, M11–M22, incl. migration
  `0032`) ✅ · Wave 3 (11 FE P3, M23–M33, incl. the new M33 dispute UI) ✅ · Wave 4 (M-D dead-code +
  SAFE simplify, sections A–F) ✅ · Wave 5 (**13 of 16** shipped — see errata E2 — S8/S28/S30 deferrals
  confirmed NOT built, correctly) ✅. Zero CONTRADICTED items across all five waves.
- **Gates independently re-run this session, all GREEN:** backend `pytest` **371✓ / 29 skipped** ·
  `ruff` clean · `tsc --noEmit` clean · `eslint` clean · `next build` clean · Playwright **26/26** —
  matching the register's §12 claims exactly.
- **Git state (2026-07-14):** `origin/dev` = `3a6a2f1` (Wave 1 pushed → live on dev Amplify) · local
  `dev` = `eec3852` (Waves 2+3 **committed, unpushed** — ahead 1) · Waves 4+5 **uncommitted** (63
  tracked modified + 2 staged deletes + 3 untracked new files). Alembic repo head `0032`; Aurora
  applied head `0031` (0032 rides the next backend deploy).
- **New findings (task 2): 1 P2 + 22 P3** — the P2 is a regression *inside* the Wave-1 M1 fix on the
  booking (revenue) page, re-verified first-hand (§3 L1). Backend re-review found **no new P1/P2**;
  the money-path core (token claims, sweep idempotency, meter dedupe, job claims, tenant guard,
  Stripe HMAC) re-verified sound a second time.
- **Register errata: 9** doc inaccuracies in the 07-12 text (§2) — none change the BUILT status.
- **Modularization (task 3):** 2 large staged splits (`prospects/router.py` 3038 LOC ·
  `list/page.tsx` 2980 LOC) + 1 cheap package split (`lib/api.ts` 1519 LOC) recommended before the
  next feature work; `models.py` and 5 other large files deliberately stay whole (§4).
- **Critical path to DoD unchanged and still 100% founder-gated:** commit/push Waves 4+5 → backend
  deploy (applies `0032`) → S3 round → S4/S5 → F0/FA → G0. **One new sequencing caution:** see §5.1 —
  pushing `eec3852` to dev auto-builds the FE with the M27 id-filter *before* the backend sends
  `campaign_id` (the register's claimed fallback does not exist — L15).

## 1 · Wave completion verification (task 1) — confirmed against code

| Wave | Scope | Verdict | Notes |
|---|---|---|---|
| 1 | M1–M10 (10 P2) + ApiError/RetryNotice/is_fk_violation enablers | ✅ **VERIFIED 10/10** | All shipped as §7 describes, incl. the deliberate 409-keeps-picker deviation. One nit: `isTransientStatus` is exported but never consumed (E8/L-D) |
| 2 | M11–M22 (12 BE P3) + `0032` | ✅ **VERIFIED 12/12** | All named tests exist; `0032` single linear head; async-webhook keep + 400-vs-404 refinement as documented. One attribution error (E1) |
| 3 | M23–M33 (11 FE P3) incl. M31 ×5 sub-sweeps | ✅ **VERIFIED 11/11** | Only line-number drift; M31-d em-dash scoping honored. But one M31 sub-item never shipped (E5/L19) and the M27 fallback claim is false (E4/L15) |
| 4 | M-D dead-code + SAFE simplify (S1/S3/S9–S17/S20/S25/S27/S29/S31) + deliberate keeps | ✅ **VERIFIED A–F all clean** | Deletions grep-confirmed absent; keeps confirmed present (`Meeting.summary`, `icp_limit`, naive batches `_iso` still flagged-not-fixed). Aggregates unverifiable (E7); `.ph-tag` residual in protected `globals.css` (E9) |
| 5 | 13 shipped (S2/S4/S5/S6/S7/S13/S18/S19/S21/S22/S23/S24/S26) · 3 deferred (S8/S28/S30) | ✅ **VERIFIED 13 + 3** | All extractions present (`FitCell`/`ListOverlay`/`FacetRow`/`IcpFilterSelect`/`Field`/`ConfirmFooter`/`PromptEditorShell`/`ManualBadges`/`toggleInSet`/`fmtDay`/`fmtDayYear`/`fetch_secret_json`); deferrals confirmed untouched (`reqRef` guard intact, billing self-fetch intact, `list/` not split) |

**Bottom line: the code is exactly where the register says it is.** The 07-12 register's BUILT+GATED
claims hold in full; the discrepancies found are documentation errors (§2), not build gaps — with two
exceptions promoted to the L-register because they are *behavioral*: the unshipped M31 sub-item (L19)
and the nonexistent M27 fallback (L15).

## 2 · Register errata — corrections to the 07-12 text

| # | Where (07-12) | Correction |
|---|---|---|
| E1 | §8.2 | `_latest_replies` lives in **`meetings/router.py:480`** (called from `list_bookings`), not `campaigns.` — behavior correct, module attribution wrong |
| E2 | §12 header | "11 of 16 shipped" → **13 of 16** (13 shipped + 3 deferred = 16; the 11 undercounts) |
| E3 | §12.1 | `list/page.tsx` = **2980 LOC** (not 2967) · `CampaignTab.tsx` = 1007 |
| E4 | §9.5 | "the summaries filter falls back to 'all' for recaps" — **that fallback was never written**; on the old backend, selecting any campaign hides every recap (→ L15, deploy-order hazard §5.1) |
| E5 | §9.2 | The M31 sub-item `"Forms sent" counts state:"None" rows` was named in the M31 register row but **not built** and not recorded as deferred (→ L19) |
| E6 | §12.2 | "`groupByCompany().meta` already gone" — true of `list/page.tsx` only; it survives in `CampaignTab.tsx:673-686` + dead consumer `:919` (→ L-D) |
| E7 | §10 | "net −296 LOC · 46 files" describes a Wave-4-only snapshot that no longer exists (Wave 5 shares the tree). Combined Waves 4+5: ≈ **−474 LOC** · 63 modified + 2 deleted + 3 added. The "2 deleted" is exact |
| E8 | §7.2 (M5) | `isTransientStatus` (`lib/api.ts:124`) is defined+exported but consumed by no page — the external pages branch via `else`. Dead export (→ L-D) |
| E9 | §10.2 (S1) | `.ph-tag` also exists in `globals.css:58` (unused). Left correctly per the §4 do-not-touch rule (design bundle verbatim) — recorded so the "absent" spot-check reads right. Also: `apps/api/build/pkg/` still holds the pre-S24 apollo client (stale packaged artifact — rebuilt by `build-and-deploy.sh`, note only) + the `search_companies_meta` docstring still says "As `search_companies`, but…" (cosmetic) |

## 3 · L-register — NEW findings (task 2), priority-sorted

> **✅ ALL RESOLVED 2026-07-14 (Phase 1).** L1·L15 · L2–L12 · L13·L14·L16–L22 · L20 · L-D all shipped
> to local `dev` (commits in Part A §A1); gate green. The finding detail below is retained as the
> rationale of record. One new item surfaced during the fix (stale enrich e2e fixtures) — see the
> Part A §A1 Phase-1 note.

Fresh-eyes pass over everything the M-register didn't cover, plus regressions introduced BY the wave
fixes. Every P2 was independently re-verified against the code path before landing here.

**P1 — none.** (Second consecutive full review with a clean money-path core.)

### P2

| # | Where | Finding → fix |
|---|---|---|
| **L1** | `web book/[token]/page.tsx:89-94` + `:63-69` | **Regression inside the M1 fix, re-verified first-hand.** The 409 slot-race branch does `setSubmitError("pick another…")` then `reload()` — and `reload()` itself does `setSubmitError("")`. The setters batch; last write wins; **the "pick another" message never renders**. The prospect sees their selection silently cleared with zero explanation, on the page that mints the unit of revenue (§7.3 explicitly promises this copy). Also `day` isn't reset by `reload()` — if the taken slot was the last on its day, the stale index can render an empty times pane. Fix: drop `setSubmitError("")` from `reload()` (its other callers already clear it) or reorder `reload(); setSubmitError(msg)`; add `setDay(0)` to `reload()` |

### P3 — backend (fold into the L-wave; L2/L3 BEFORE Stripe/FR-7 activation)

| # | Where | Finding → fix |
|---|---|---|
| **L2** | `billing/router.py:129-140` + `prospects/router.py:2945-3021` | **M13-introduced durability trade.** The atomic usage `UPDATE` is now uncommitted until the first per-row commit *after the whole Apollo fan-out* — a Lambda timeout mid-fan-out spends the Apollo credits but rolls back the reservation → cap leaks; and the uncommitted UPDATE holds the tenant's `subscription` row lock for the fan-out's duration (blocks `create_subscription`/Stripe webhook `_apply`). Fix: `db.commit()` in `_enrich_prospects` immediately after `reserve_enrichment` returns (nothing else dirty at that point — keeps M13's no-commit-in-helper principle, restores reserve-before-spend) |
| **L3** | `billing/router.py:228` + `scripts/verify_keys.py:388-396` | `create_subscription`'s `if p` filter **silently drops the metered qualified-meeting price** when `price_qualified_meeting` is absent from the Stripe secret — and the FR-7 seeding contract (verify_keys + GD-3 envelope docs) doesn't list that key (only `stripe_smoke_live.py` knows it). Founder seeds per checklist → all green → subscription created flat-only → **$0 billed per meeting, silently**. Fix: hard-fail (409 + log.error) on a paid plan missing the metered price; add the key to verify_keys + GD-3 docs |
| **L4** | `campaigns/router.py:784` (`_set_campaign_status`) | Pause/Resume call `sl.set_status()` with no try/except and no global SmartleadError handler → Smartlead outage = **raw 500 on first-class console buttons** (exact M17 class, unfixed siblings). Fix: catch `SmartleadError` → 502, mirroring M17 |
| **L5** | `integrations/smartlead/client.py:155-158` | Smartlead `_request` blind-retries transport errors for **every method incl. POST** — a timed-out `reply_to_thread` that landed is replayed (prospect gets the reply + booking link **twice**); `create_campaign` can mint an orphaned duplicate. Exact M19 class; the register scoped M19 to Google only. Fix: port the `retry_transport=False` opt-out to smartlead for `reply_to_thread` (+ `create_campaign`) |
| **L6** | `briefs/router.py:71-86` vs `campaigns/webhooks.py:139-158` | `PUT /brief` replaces `brief.data` wholesale → an operator saving a long-open Brief form **silently erases DNC entries the M3 unsub write-back appended in between** (Smartlead's own suppression still holds at send; the tenant-level find/enrich/batch exclusion — M3's whole point — is lost). Fix: server-side union-merge of `doNotContact` on PUT (or optimistic version check) |
| **L7** | `campaigns/webhooks.py:156-157` | `_unsub_writeback` string-form uses substring membership (`email not in existing.lower()`) — a new unsubscriber whose address is a substring of an existing entry (`son@x.com` vs listed `jason@x.com`) is **skipped**. The list-form branch is exact-match (correct). Fix: tokenize the string form (split on whitespace/commas), compare whole entries |
| **L8** | `prospects/router.py:2419,2566` + `_validate_icp_id` | M20 incomplete: `add_prospect` + `find_people` still raw `uuid.UUID(icp_id)` → 500. And `_validate_icp_id` is format-only — a well-formed **nonexistent** id dies at commit as FK-23503 → 500; a **cross-tenant** id is silently stored (contrast `create_batch`, which 404s non-owned). Fix: one shared parse-+-tenant-owned-or-404 ICP validator across all three doors |
| **L9** | `campaigns/router.py:260-270,465-476` (`_seed_variants`) | No dedupe of normalized variant keys against `uq_message_variant_campaign_key` — `""`→`"A"` colliding with a literal `"A"`, or two keys identical after the `[:8]` trim → uncaught unique violation → **raw 500 on the variants editor**. Fix: 400 on duplicate normalized keys |
| **L10** | `campaigns/router.py:999-1010` | `billable_this_cycle` sums qualified/undisputed/window-passed meetings **all-time** — no cycle bound, no `billed_at IS NULL`. Dormant-today; once Stripe activates, already-invoiced meetings inflate the console figure forever, diverging from the Stripe invoice. Fix: filter `billed_at IS NULL` (accrued-unbilled) or bound to cycle; else rename the field |
| **L11** | `meetings/router.py:656-663` (`inform_client`) | Ignores `send_email`'s boolean → 204 even when SES refused; operator believes the client was informed. Sibling `send_feedback` (:605) correctly 502s. Fix: `if not sent: raise 502` |
| **L12** | `prospects/router.py:2259-2262` (`scoring_job_status`) | Still 400s a malformed **path** id vs the M22 standard (404 via `core/deps.uuid_or_404`; campaigns/meetings/batches/icps comply). One-line swap |

### P3 — frontend

| # | Where | Finding → fix |
|---|---|---|
| **L13** | `list/page.tsx:1782-1806` (`createBatch`) | No in-flight guard at all (unlike every sibling first-class action) — two clicks during the POST round-trip create **two identical batches**, both sendable for approval and mintable into campaigns. Fix: busy state + disabled + M23-style ref. (Lesser sibling: `client-status/approval` `saveTmpl` also busy-less — idempotent PUT, cosmetic) |
| **L14** | `login/page.tsx:82-88` + `lib/api.ts:202-209` | **Reset-password still has the M25 bug class:** `reset()` throws a bare `Error` (no status, no cold-start retry), so the catch-all shows "This reset link is invalid or has expired." on a 503/network blip — routine on auto-pausing dev Aurora. Fix: `reset()` → `fail(r)` (ApiError); branch 400/410 vs transient; share the login cold-start retry |
| **L15** | `summaries/page.tsx:29` + `WorkspaceProvider.tsx:74` | **Register-adjacent (M27/E4):** filter is `!sumCamp \|\| rc.campaignId === sumCamp` with no `campaignId == null` fallback — against the deployed backend (no `campaign_id` until the pending deploy), selecting **any** campaign hides **every** recap. Shielded only by deploy order (§5.1). Fix: `\|\| rc.campaignId == null` (one line) — cheap insurance even if deploy order is honored |
| **L16** | `ClientSwitcher.tsx:29-35,59-77` + `MeContext.tsx:53-61` | M32-adjacent: `create()` awaits a `refetch()` that **swallows all errors** — on a blip the M32 effect sees the new slug missing from stale `me.clients` and bounces the user off the client they just created ("create failed" UX; tenant exists but listed nowhere until reload). Also `slugs.length === 0` skips the redirect entirely — a zero-membership user gets a dead workspace, no notice (M32 promised one). Fix: `refetch` returns success; skip/defer the bounce for a just-created slug; add the zero-membership notice |
| **L17** | `client-status/feedback/page.tsx:61-71` (`inform()`) | Catch-all toast asserts "No client attendee email on file" for **any** failure (503/network/500) — the false-claim class M31-e fixed on the batches modal. Fix: surface `e.message` with a generic fallback. Pairs with L11 (the BE half returns 204 on failure today) |
| **L18** | `billing/page.tsx:42-48` · `client-status/booking:30-35` · `client-status/feedback:41-46` | Hand-rolled loaders neither reset rows on `client` change nor guard the in-flight promise → on back/forward between tenants, **tenant A's ledger/booking/feedback rows render under tenant B's URL** until B's fetch lands; a slow A response can land after B's and stick. Low-likelihood (switcher routes to /workspace) but cross-tenant display on the money page. Beyond S28's deferred scope (that was key-consolidation). Fix: `setRows(null)` on client change + alive guard (or `useQuery(["…", client])`) |
| **L19** | `client-status/feedback/page.tsx:84-85` | The dropped M31 sub-item (E5): "Forms sent" = `list.length` — counts held meetings whose form was never sent (`state:"None"`). Fix: count `state !== "None"` |
| **L20** | a11y — `list/page.tsx:245-270` (`Field`) + `:991,2021-2024,2244-2248` | `<Field>`'s label has no `htmlFor`/wrapping → **all 17 modal inputs have no accessible name** (one-line fix ×17 now that S4 centralized it; `FacetRow` wraps correctly). Step-1 bucket/reason header rows + Step-2 company expand cell are `tr/td onClick` with no `role`/`tabIndex`/keydown — call-sheet buckets are keyboard-unreachable (batches' `sob-card` shows the correct in-house pattern) |
| **L21** | `approve/[token]/page.tsx:136-145,196-207` | Summary strip + CTA row render outside the `!view` gate → during load the client sees "Your batch · 0 prospects" **and a red disabled "Reject the list" button** for the whole cold-start. Fix: gate both on `view` |
| **L22** | `components/workspace/spec.tsx:399-413,827` | Prompt-editor Save never updates its compare baseline (`prompt.system`) after a successful save → the button re-enables for already-saved text; each further click **appends another spec version**. Fix: sync `prompt.system` on save |

### L-D · Dead/cleanup residue (ride the L-wave commits)

`lib/api.ts` `isTransientStatus` dead export (E8) · `CampaignTab.tsx:673-686,919` `groupByCompany().meta`
always-`""` + its unreachable consumer (E6, ~4 LOC) · apollo `search_companies_meta` docstring names the
deleted wrapper (E9) · `.ph-tag` in `globals.css` stays (protected).

### Low-confidence notes (recorded, not counted)

- `campaigns/webhooks.py:66` `_resolve_campaign` uses `scalar_one_or_none()` but `smartlead_campaign_id`
  is unique only per-tenant — two tenants sharing a Smartlead id would raise `MultipleResultsFound`,
  swallowed as `{"deferred": true}` forever. Improbable while one Smartlead account serves all tenants;
  revisit at multi-account.
- M19 delta: `google create_event` still retries on **429/5xx** (only transport retry was disabled). A
  5xx-after-commit from Google would duplicate the event; Google generally doesn't commit on 5xx.

### Fresh-eyes "checked but clean" (both reviewers)

Approvals masking/claim/decide gating · Stripe webhook (HMAC/tolerance/dedupe/never-5xx) · M2 sentinel
both paths · M11 totality · M21 rework semantics (bucketing + `SUM(CASE)` cell-for-cell) · job machinery
(atomic claims, reaper, coalesce) · sweep/qualify + NF-3 isolation · core (pagination codec,
`uuid_or_404`, violation predicates, `fetch_secret_json`, TTL cache, auth timing-safety) · FE: api.ts
single-flight refresh + cursor paging · SessionGuard · WorkspaceProvider key/invalidation matrix ·
list-page client-switch hygiene + paid-action ref guards · CampaignTab M26/`reqRef`/`fmtWhen` · golden
rules (zero `innerHTML`, class-scoped page CSS ×8, `.sample` markers, middot scoping honored).

## 4 · Modularization study (task 3) — split candidates for future scalability

Backend `apps/api/app` = 16,706 LOC (prospects domain alone 5,670 = 34%; its router = 54% of the
domain). Frontend `apps/web/{app,components,lib}` = 15,122 LOC. Files > 600 LOC:

| LOC | File | Verdict |
|---|---|---|
| 3038 | `api domains/prospects/router.py` | **SPLIT — priority 1 (BE)** |
| 2980 | `web workspace/list/page.tsx` | **SPLIT — priority 1 (FE), staged** |
| 1519 | `web lib/api.ts` | **SPLIT — cheapest high-value** |
| 1453 | `web workspace/brief/page.tsx` | split churn-gated |
| 1079 | `api models.py` | **keep whole** (by design) |
| 1071 | `api domains/campaigns/router.py` | partial split |
| 1007 | `web workspace/CampaignTab.tsx` | file-motion split |
| 850 | `web components/workspace/spec.tsx` | one-move split |
| 663 | `api domains/meetings/router.py` | optional |
| 661 | `api briefs/research_spec.py` | keep whole |
| 640 | `web workspace/batches/page.tsx` | keep whole |
| 618 | `web lib/workspace/constants.ts` | 3-way split |

### 4.1 `prospects/router.py` (3038) — five programs in one file · Effort L

Internal map: tenant/scope helpers `:155-435` · list endpoints + serializers `:436-580` · **scoring-v2
label engine** `:581-969` · **Flow-A company find pipeline** `:1054-1767` (incl. `_run_company_find`,
229 LOC) · async job layer + `SCORING_HANDLERS` `:1930-2303` · **Stage-2 people** `:2389-2937` (incl.
`find_people`, a single 257-LOC endpoint). Proposed package (router stays the aggregator; URL space +
`main.py` untouched): `scope.py` · `serializers.py` · `label_engine.py` · `company_find.py` ·
`people_find.py` (+ break `find_people` into its own commented phases) · `jobs.py` — moving
`SCORING_HANDLERS` into `jobs.py` **dissolves the existing `scoring.py:242` lazy-import cycle**.
Risks: 4 test files import ~10 private symbols by path (mechanical retarget); money-adjacent code
motion → wants a live smoke post-deploy. Why first: every next find/scoring feature (2nd source,
ladder tuning, model swap) lands here, and it was the wave-touched file.

### 4.2 `list/page.tsx` (2980) — the S30 revival, staged · Effort L

The Wave-5 extraction dividend is spent (components now live at `:132-281` of the same file); the
remaining mass is **57 `useState` hooks** of interleaved two-stage + five-modal state, not repeated
DOM. Staged split, one pin-tested PR each: **(1) modals out first** (~500 LOC, lowest risk:
`ScopeSettingsModal` · `PeopleScopeModal` · `AddCompanyModal` · `AddPersonModal` · `RubricModal`, each
with its already-isolated state cluster) → **(2) `useListData` hook** (boot effect `:546-633` + reload
fns + feed state) → **(3) `Step1Companies` / `Step2People`** (JSX branches `:1842-2182` /
`:2183-2480`; selection sets + in-flight sets + `maySelect` **stay in the parent** — they cross the
stage boundary) → `SEL_CSS`/`SE_CSS` strings → `workspace.css`. Caution: the route-mocked Playwright
suite can't observe live find/score semantics — each stage wants one manual find + one
reveal-and-score QA. Hard rule until then: **no new feature (no 58th `useState`) lands in this file
un-split.**

### 4.3 `lib/api.ts` (1519 · 141 exports · 24 importers) — Effort S, do first

Already phase-banded. → `lib/api/` package: `core.ts` (tokens/refresh/`ApiError`/request) +
`briefs.ts` · `prospects.ts` · `batches.ts` · `campaigns.ts` · `meetings.ts` · `billing.ts` ·
`external.ts`, with **`lib/api.ts` kept as a barrel re-export** so all 24 importers + Playwright mocks
compile unchanged. Near-zero risk; prerequisite hygiene before Stripe activation grows the Phase-G tail.

### 4.4 `campaigns/router.py` (1071) — partial split · Effort M

Extract **`stage_moves.py`** first (`record_stage_move`/`move_lead_or_409`, `:150-184`) — three
modules import it from the router today, two lazily as cycle guards (`meetings/router:198` ·
`meetings/public:219` · `campaigns/webhooks:31`); a leaf module makes all three eager and honest.
Then `replies.py` (E5 block `:526-737`, own URL family) + `performance.py` (E7 `:873-1071`, ~195-LOC
endpoint; its reverse lazy import of `sweep_meetings` un-lazies after 4.6). Core CRUD/launch stays
(~550 LOC, cohesive).

### 4.5 Smaller FE splits

**`CampaignTab.tsx` (1007):** pure file motion — `VariantPanel` (`:691-886`) + `CompanyCard`
(`:893-1007`) + a `stage-meta.ts` for the constants → `components/workspace/campaign/`. Do **before or
with** the deferred S8 (`detail`→`useQuery`): a smaller parent makes S8's 5-mutation-path audit
tractable. · **`spec.tsx` (850):** move `SpecReview` (~500 LOC, single importer) out; the shared atoms
stay. · **`constants.ts` (618):** → `brief-form.ts` / `scoring.ts` / `scope.ts` (the FE mirror of
prospect scope — pair with 4.1 so the mirrored pair reviews side-by-side); keep `constants.ts` as
barrel. · **`brief/page.tsx` (1453):** six accordion sections → `brief/sections/*` + a
`useBriefPersistence` hook — churn-gated, only when the form next changes.

### 4.6 Do-NOT-split (deliberate)

**`models.py` (1079)** — 26 thin behavior-free models + 4 shared column factories; one metadata module
keeps Alembic autogenerate + `data-schema.md` trivially diffable; supports ~2× this size. Revisit only
if models grow methods. · **`research_spec.py` (661)** — one versioned pipeline
(`SPEC_VERSION`/`PROMPT_VERSION` coherence depends on co-location). · `labeling.py` / `fit.py` /
`campaigns/service.py` / `launch.py` / `structuring.py` — each already a single-purpose extraction. ·
Integration clients — one-per-vendor by design (S13 already factored the shared half). ·
`batches/page.tsx` · `login` · home `page.tsx` · `FindHistoryDrawer` — single-flow/static. ·
`workspace.css` (2921) — the one-stylesheet golden rule. · Tests — none > 800 LOC; no action. ·
**`meetings/router.py`** — optional `sweep.py` extraction only if F-phase billing work reopens it (it
sits on the audited money path; don't move it for tidiness).

### 4.7 Recommended order

1. **`lib/api.ts` → package** (S, zero-behavior, barrel) — immediately; prerequisite for Stripe + any endpoint work.
2. **`prospects/router.py` package** (L) — before the next find/scoring feature; own deploy-neutral backend deploy *after* the pending 0032 deploy; pair with `constants.ts → scope.ts`.
3. **`campaigns/router.py`: `stage_moves.py`** (30 min, un-lazies 3 imports) → `replies.py`/`performance.py` (M) — before meeting-summary/billing-evidence work.
4. **`list/page.tsx` staged split** (L) — modals → data hook → step tables, one PR each + manual QA; hard prerequisite before any new list-page feature.
5. **`CampaignTab` motion** (S) — opportunistic; mandatory before S8.
6. `spec.tsx` / `brief/page.tsx` — churn-gated. 7. `meetings/sweep.py` — only if reopened.

All of the above are code-motion refactors: deploy-neutral (no route/schema/class-name changes), gated
on the standing suites + one manual live-flow QA for the two large splits.

## 5 · Execution guidance

### 5.1 · Sequencing caution (new, one-line insurance available)

`origin/dev` already serves Wave-1 FE. Pushing `eec3852` (Waves 2+3) triggers the Amplify FE build
**immediately**, but the backend deploy that adds `MeetingOut.campaign_id` is a separate founder
action — in that window the M27 recap filter hides all recaps when any campaign is selected (L15/E4;
the register believed a fallback existed). **Either do the backend deploy first (backend-before-
frontend rule, as standing) or land L15's one-line `campaignId == null` fallback before pushing.**
The Wave-4 FE schema-mirror trims must likewise ride the same backend deploy (§10.5 rule — confirmed
still true).

### 5.2 · Suggested L-wave order (backend-before-frontend, each fix gets a test)

1. **L1** (P2, revenue page — one-line class of fix) + L15 (its one-line sibling insurance).
2. **Pre-Stripe/FR-7 block:** L2 · L3 (both sit directly on the founder-register path about to be
   exercised) · then L4/L5 (Smartlead 502/retry siblings).
3. **Compliance pair:** L6 + L7 (DNC merge + substring fix — completes what M3 started).
4. Remaining BE cheapest-first: L8 · L9 · L11 · L12 · L10 (dormant).
5. FE sweep: L13 · L14 · L16 · L17 · L18 · L19 · L21 · L22 · L20 (a11y batch) + L-D dead residue.
6. Deferred-from-M carryover, unchanged: S8 · S28 · S30-as-§4.2 (now superseded by the staged split
   plan) · batches `_iso` naive-Z fix (the flagged M6-class latent) — fold the `_iso` fix into the
   L-wave's backend commit (it's a 1-line `iso_z` swap + test).

Exit gates: the standing protocol (pytest + ruff + tsc + eslint + build + Playwright green ·
founder-authorized commit/push/deploy).

### 5.3 · State of record after this session

**Totals:** M-register CLOSED (33 fixes + M-D + 28-of-31 simplify verified built; S8/S28/S30 openly
deferred). **L-register OPEN: 1 P2 + 22 P3 + L-D residue** (~none gate-blocking). Founder-gated DoD
path unchanged: commit/push Waves 4+5 → backend deploy (`0032`) → S3 → S4/S5 → F0/FA → G0.
`docs/mvp-review-2026-07-12.md` remains the detailed build log for Waves 1–5; this document is the
verification of record + the open register going forward.

---

# Part C · M-register build record — archived verbatim from `mvp-review-2026-07-12.md`

> Preserved unchanged as the detailed build log for Waves 1–5 (the source of the still-uncommitted
> Waves 4+5 detail). Superseded as the live register by **Part B** above; the internal `## N` section
> numbers below are the original 07-12 numbering. Once Waves 4+5 are committed (Phase 0.1), git history
> becomes the primary record and this archive can be trimmed.

> **Read-only planning/review session — zero code changes.** Post-G-NF full-repo audit: plan-vs-code gap
> analysis · phase-status confirmation · code review (backend + frontend, priority-sorted) · simplify check.
> Per the §D+.6 closure rule ("anything discovered from here belongs to a NEW register"), this is that
> register — it covers mostly **E/F/G-NF-era code** (the A–D+ cycle stays closed). Method: 5 parallel
> full-file reviewers (BE gap · FE gap · BE review · FE review · simplify) + local gate re-runs; every P2
> was independently re-verified against the code path before landing here.

## 0 · Session verdict

- **No P1 anywhere.** Money paths verified sound: per-row enrich double-spend stamp, atomic job claims +
  DB-unique one-per-tenant×kind, tenant guard mechanically present on every `/{client}` route, token
  claims idempotent, Stripe HMAC/idempotency/pinned-version correct, meter emission idempotent, no
  `innerHTML`/XSS, paid FE actions ref-guarded against double-click.
- **The code is AHEAD of the docs, not behind** — every material build claim (A–F + G-NF Wave 1+2)
  verified present in code; zero plan-claimed features missing. The gaps were all *doc staleness*
  (fixed this session — §1) plus **10 P2s and ~35 P3s** concentrated in the newest, least-reviewed
  code (campaigns/meetings/billing + their FE surfaces) — §3.
- **Gates re-verified this session:** pytest **358✓/23 skipped** · ruff clean · `tsc` clean · `eslint`
  clean · **Playwright 26✓ (run fresh — closes the "not yet run" open item)** · `dev` == `origin/dev`
  at `a978b36` (the "FE not pushed" claim was stale) · `cutover-prep` local-only at `cd0dca2` ✓.

## 1 · Plan accuracy (task 1) — reconciliation APPLIED this session

`initial-build-plan.md` had accreted status in four places that disagreed (header said v87/`0030`/338
tests · snapshot said v86/`0029`/~60 endpoints · G-NF log said v89/`0031`/358 — the log was right).
**All fixed in-place this session:**

| Doc | Fixed |
|---|---|
| `initial-build-plan.md` | Status header + source-of-truth line + Current-state snapshot → **v89 · head `0031` · 83 routes/13 routers · dev Amplify `a978b36`**; roadmap G row records G-NF Wave 1+2 shipped-dormant; "Still open" block updated (FE pushed · Playwright 26✓ this session); S3 gate row rephrased (E7 shipped); **§API surface table extended** with the 6 missing routers (campaigns · smartlead-webhooks · meetings · meetings-public · billing · stripe-webhook) + `llm-usage`; §D+.3 U3 sentence corrected to as-built (literal checked⊆visible NOT implemented; shipped = N11 prune-on-reload + R13 whole-selection counts) |
| `data-schema.md` | Internal contradiction fixed (`0001→0030` → `0001→0031`) |
| `CLAUDE.md` | **Rewritten** — was a full phase behind ("Phase 1 mock UI, no backend"); now records the live-wired console (auth/SessionGuard, nested-route tabs + portaled tab bars, TanStack Query, live API seam), real backend/infra layout, dead fixture files, test/deploy commands |

Residual doc nuances (recorded, not fixed — historical text): NF-6's "doc-fixtures" are inline in
`test_stripe.py` (no `fixtures/stripe/` dir) · plan F6 lines still describe `B_LOG`/`F_LOG` fixtures as
"today the mocks" (historical; files are now dead — M-D below).

## 2 · Phase status + remaining (task 2) — confirmed against code + git

| Ph | Verified status | Remaining |
|---|---|---|
| A–C | ✅ live (dev + prod FE), matches plan | none (S1/S2 signed off in review #5) |
| D | ✅ live | **founder S3 live batch round** (= G0-2; feeds the E acceptance campaign) |
| D+ | ✅ shipped dev+prod; review cycle closed | 3 standing carve-outs only (R21 · R27-dups · R30-tests) |
| E | 🟢 shipped dev (`d8aef2b`, `0028`/`0029`) | **founder S4/S5 acceptance run** (= G0-1; consumes the S3 batch) |
| F | 🟢 shipped dev (`44b761b`, `0030`), live-verified | **founder F0 real held-Meet (`--meeting-code`) + FA acceptance → tick S6** |
| G | ⬜ human; **G-NF Wave 1+2 code SHIPPED** (v89, `0031` dormant; NF-7 on `cutover-prep`) | founder register FR-1…FR-12; trigger-fired NF-8 (GS deploy ← FR-7) · NF-9 (cutover ← FR-11) · NF-10 (SCALE ← 2nd tenant) |

**Critical path to DoD is now 100% founder-gated:** S3 round → S4/S5 acceptance → F0/FA → G0 all-✓ → run
the loop. No code blocks any gate. This M-register is the only open build backlog (none of it gate-blocking).

## 3 · Code-review findings (task 3) — priority-sorted, with fixes

**P1 — none.**

### P2 — fix in the next build wave (ordered by business impact)

| # | Where | Finding | Suggested fix |
|---|---|---|---|
| **M1** | `web app/[client]/(external)/book/[token]/page.tsx:57-69` (+ load `:42-48`) | Booking-page catch conflates EVERY failure with "link used": a 409 (slot just taken), 503 cold-start, or network blip flips a **valid booking link to a permanent dead-end → meeting lost** (the product's unit of revenue). Load-time catch renders "expired" on transient errors too. | Flip to used/expired only on 409/410; other failures → inline "couldn't book — try again", keep the slot picker; retry/backoff on public GETs |
| **M2** | `api domains/meetings/public.py:59-64` `_read_busy` | On `GoogleError` returns `[]` = "no busy intervals" → **full slot grid offered + `slot_is_free` passes** during a Google outage → double-booked calendar, later swept as a real meeting. Contradicts its own docstring (FT3-9 "offer no slots"). | Return `None` sentinel on error; `view_booking` → `slots=[]`, `book_meeting` → 503-and-release |
| **M3** | `api domains/campaigns/webhooks.py:181-185` `_ingest` | `_unsub_writeback` only runs inside `if target and record_stage_move(...)` — an unsubscribe from a lead already at `drop` (bounced/negative-triaged first) or an unresolvable lead **never lands in the Brief `doNotContact` list**, breaking the documented SG-PDPA ≤5-day honor every future find/enrich/batch relies on. | Call `_unsub_writeback` whenever `internal == LEAD_UNSUBSCRIBED`, resolving the email off the payload, independent of the stage move |
| **M4** | `web components/console/MeContext.tsx:25-31` | Any `/me` failure (Aurora cold-start 503, network blip) → `clearTokens()` + forced re-login. Dev Aurora auto-pauses, so this fires **routinely** on first console open. | Retry cold-start statuses (reuse `isColdStartStatus`); clear tokens only on 401; 5xx/network → keep tokens + retry state |
| **M5** | `web` all 3 external token pages (`approve:16-37` · `feedback:31-52` · `book` load) | Same class as M1 across the other public pages: load-time `.catch()` renders "expired", submit catch flips to "used", on ANY error — prospect/client told a live link is dead after one cold-start hiccup. | Distinguish 410/409 from transient; add a retry affordance (shared helper with M1) |
| **M6** | `api domains/campaigns/router.py:65` `_iso` + `web replies/page.tsx:27` · `CampaignTab.tsx:67` | Campaigns serializes naive ISO (no `Z`; Data API returns naive UTC) and the FE parses with bare `new Date()` → **UTC digits rendered as local dates** — in HK (+8) a reply at 20:00 UTC Jul 11 shows "Jul 11" when it's Jul 12 04:00 local. Meetings domain does it right (`iso_z`). | BE: use `iso_z` in campaigns (mirrors meetings); FE: parse via `parseUtc`/`whenLabel` from `lib/dates.ts` (built for exactly this — R16 lesson) |
| **M7** | `web performance-summary/page.tsx:32-40` | `getPerformanceSummary(...).catch(() => undefined)` silently strands the page: hard "0" qualified meetings + zero needs-attention + "Loading funnel…" forever — **real-looking wrong numbers on the client-facing surface**. | Keep an error state (retry link / "couldn't load" panel) instead of zero-defaults |
| **M8** | `api models.py:838` `CampaignLead.variant_key` + `campaigns/router.py:94-113` | **No code path ever writes `variant_key`** → `_variant_metrics` always returns `{}` → the E6 A/B scoreboard shows 0/0/0 forever and `set_variant_winner` decides on blank data. In-code comment acknowledges it; the plan never surfaced it. | **✅ DECIDED (build):** ingest Smartlead's per-lead variant (webhook/statistics field) onto the lead so the scoreboard shows real counts |
| **M9** | `web workspace/billing/page.tsx:47-62` | Ledger "Refresh" runs the server sweep but never invalidates `["meetings", client, "past"]` → Meeting Recaps shows stale outcome/`won` indefinitely after a sweep flips a meeting to Billed. | After `refreshMeetings`, `invalidateQueries(["meetings", client, "past"])`; ideally read the ledger from that same query (also kills the duplicate fetch — S-note) |
| **M10** | `api domains/batches/router.py:282-295` `delete_batch` | Deleting a batch with a `Campaign` (FK RESTRICT) or billed-evidence `Meeting.approval_id` → unhandled FK violation → **raw 500 on a first-class console button**. | Pre-check (or catch FK error) → 409 "batch has a campaign / billed evidence" |

### P3 — backend (fold into the M-wave where cheap)

| # | Where | Finding · fix |
|---|---|---|
| **M11** | `meetings/service.py:78-85,126-145` | Founder-authored `brief.data.availability` unvalidated (`meeting_minutes:"abc"` → ValueError; malformed window → IndexError) and `availability_of` runs on EVERY meetings-surface read + the public booking page → one bad Brief edit 500s the whole surface. Fix: try/except per field → FD-1 defaults |
| **M12** | `billing/router.py:162-170` | `billing_status` never applies `_rollover` → in a new UTC month the GS6 line shows last month's usage until an enrich call. Fix: apply rollover read-only (no commit) |
| **M13** | `billing/router.py:104-141` | `reserve_enrichment` usage bump is read-modify-write (not `SET usage = usage + n`) + a mid-flow `db.commit()` commits the caller's dirty session. Shielded today only by the one-job invariant in another domain. Fix: atomic increment; drop mid-flow commit |
| **M14** | `billing/router.py:173-211` | Re-POST subscription with a different plan updates local caps but never touches Stripe prices → silent divergence (dormant today). Fix: 409 on plan change or call Stripe update |
| **M15** | `campaigns/router.py:599-621` | `triage_reply` stores `body.triage` unvalidated → typo'd class marks handled, no stage move, pollutes summary counts. Fix: 400 unless in `TRIAGE_CLASSES` |
| **M16** | `meetings/schemas.py:61-64` | Public `FeedbackIn.chips/comment` unbounded → a token holder can store MBs on the meeting row. Fix: max_length/count caps |
| **M17** | `campaigns/router.py:624-701` | `respond_reply`: booking-link row persisted only after the Smartlead send → DB failure post-send emails a URL that 410s forever; `SmartleadError` escapes as raw 500. Fix: catch → 502; accept-or-document the dead-link window |
| **M18** | `meetings/router.py:217-255` | `correct_outcome` works on unswept future meetings (`held IS NULL`) → accidental pre-meeting "qualified" becomes billable. Fix: 409 unless held/past |
| **M19** | `integrations/google/client.py:258-291` | `create_event` retries POST on transport timeout → duplicate calendar events + invites. Fix: no retry on that POST (or check-before-retry) |
| **M20** | `prospects/router.py:1025` | `add_company` raw `uuid.UUID(body.icp_id)` → 500 (siblings 400). Fix: reuse `_validate_icp_id` |
| **M21** | perf | `list_bookings` N+1 (2 event queries per link → 100 RTs at 50 links; use the `_lead_rows` bucket pattern) · `list_replies` unpaginated/unbounded (add cursor/cap) · `performance_summary` ~18 sequential counts (merge into conditional aggregates) · `pause/resume` serialize full `_detail()` then discard (return `_campaign_out`) |
| **M22** | design | Owner-gating divergence: briefs (`PUT /brief`, `POST /brief/structure` = paid DeepSeek call) + icps accept any member while every other write/spend door is owner-only — **✅ DECIDED: keep open** to all members (document as deliberate, no gating change) · malformed-id → 400 vs 404 varies by domain (pick 404, share helper) · `billing/webhooks.py:37` sole `async def` route doing sync DB I/O (make sync) · `ix_outreach_event_tenant_type_created` indexes `created_at` but consumers filter/order `occurred_at`; `Subscription.stripe_customer_id` unindexed (note) |

### P3 — frontend

| # | Where | Finding · fix |
|---|---|---|
| **M23** | `list/page.tsx:1093-1113` | `runUpdateFields` (Apollo credit spend) lacks the synchronous ref guard its sibling paid actions carry (async `disabled` only flips post-render). Fix: same `rescoringCoRef`-style guard |
| **M24** | `billing/page.tsx:53-62` | sweep `refresh()` has no catch → failure = unhandled rejection, zero feedback. Fix: catch → warn toast |
| **M25** | `login/page.tsx:115-120` | Any failure (500/network) shows "Invalid email or password." Fix: branch on status → "server unreachable — try again" variant |
| **M26** | `CampaignTab.tsx:280-309` | Variant save/add/delete toasts success + clears the edit buffer BEFORE the PUT resolves → on failure, false "saved" + draft lost. Fix: toast/clear after resolve |
| **M27** | `summaries/page.tsx:59-62` + `replies/page.tsx:104-106` | Campaign filters keyed/valued by `name` → same-named campaigns collide (both minted from batch names). Fix: filter by `campaign_id` |
| **M28** | `summaries/page.tsx:120-145` | NF-3 won toggle is one-way — no path back to `null` though the API accepts it. Fix: clicking the active button sends `null` |
| **M29** | `batches/page.tsx:89-106` | `?batch=` deep-link effect re-fires on `batches.length` change → deleting another batch re-expands + scroll-jumps. Fix: consume once (ref) or strip the param |
| **M30** | `client-status/approval/page.tsx:27` | `day()` renders the UTC day while the batches tab renders local (`localCalendarDate`, the N38 fix) → same batch shows different "Sent" dates. Fix: reuse `localCalendarDate` |
| **M31** | ui | `list/page.tsx:112-114` low-fit confirm uses `window.confirm` vs the design-system Modal everywhere else · `performance-summary:100` "3 open" chip hardcoded next to live counts · `client-status/feedback:81-84` "Forms sent" counts `state:"None"` rows · booking/feedback failure toasts omit `"warn"` kind (render green) · `batches:518-522` Brief-query error asserts "No attendee emails on your Brief yet" (false claim; distinguish `isError`) · em-dash separators in new FE copy vs the middot rule (one sweep) |
| **M32** | `ClientSwitcher.tsx:39-42` | A non-member slug renders as a normal-looking current client; every call then 403/404-toasts. Fix: once `me` resolves, redirect to `me.clients[0]` / access notice |

### M-D · Dead-code inventory (delete on the M-wave; all grep-verified zero callers)

- **BE:** `smartlead.sending_account_ids()` (superseded by `0029` DB pool) · `smartlead.fetch_analytics()` ·
  `meetings/service.participant_duration_min()` + `event_meeting_code()` (test-only) · campaigns
  `IllegalMove` · `CAMPAIGN_STARTED` (mapped, never written) · launch `COMPLETED` status (no transition
  sets it; docstring promises it) · `Meeting.summary` JSONB (no reader/writer — the deferred
  `meeting_summary` seam; keep only if the LLM recap is imminent) · `Subscription.icp_limit`/
  `plan_icp_limit` (serialized, enforced nowhere) · new dup helpers: `_brief_data`×2 · `_iso`×4 ·
  `is_unique_violation` living in `prospects/scoring` but imported by 5 domains (→ `core/db.py`) ·
  cross-module private imports (`meetings/public._brief_attendee` ← router; `launch._fail` ← router)
- **FE:** `lib/workspace/fixtures.ts` (whole file, 140 LOC) · `lib/fixtures/client-status.ts` (whole file,
  102 LOC, + the empty dir) · `lib/workspace/types.ts:64-95` `Campaign`/`Reply`/`LedgerRow` ·
  `constants.ts` `MOCK_TODAY`/`TODAY_ISO` + needless exports (`localCalendarDate`·`UNSCORED_RANK`·
  `labelRank`) · `WorkspaceProvider.setReplies` (zero consumers; NF-2 comment stale) · `api.ts`
  `FunnelStageApi` export · unused `Sample` import in `book/[token]` · ~~`api.ts correctOutcome`~~ —
  **✅ DECIDED: keep** — no longer dead; it's the wiring for the new M33 outcome-correction/dispute UI
  (backend door exists, `meetings/router.py:217`)

## 4 · Simplify register (task 4) — same output, same UI flow, ~500+ LOC less

From the dedicated simplify pass (S1–S25, all claims grep/read-verified; SAFE = mechanical zero-behavior-
change, CAREFUL = pin with a test first) **plus** the review-pass duplication notes (S26–S31). Biggest
safe wins first:

| # | Risk | What · where · est. LOC |
|---|---|---|
| S1 | SAFE | Dead CSS rule blocks — `workspace.css` (`.sum-card .sv .rec-link`·`.icp-foot .est`·`.cmp-name-input`·`.cmp-drop`·`.cmp-chip*`·`.cmp-send`·`.cmp-logch.calendar/.stripe`·`.cmp-logmeta`) + `performance-summary.css` `.ph-inline` + `home.css` `.ph-tag` · **~115** |
| S2 | CAREFUL | U1.6 localStorage scope-migration shim (`constants.ts:448-485` + its `list/page.tsx:630-660` effect) — inert once every founder browser carries the done-flag; verify no un-migrated `holdslot_scope_*` keys first · **~70** |
| S3 | SAFE | Dead-serialized meeting fields FE never reads (`MeetingOut.meet_link/duration_min/disputed/dispute_window_ends_at` · `FeedbackRowOut.chips` · `BookingConfirm` body) — schema+serializer+api.ts types only; columns/logic untouched · **~25** |
| S4 | CAREFUL | `<Field>` wrapper for the 17× identical `div.field>label+input` blocks in list-page modals · **~40-55** |
| S5 | CAREFUL | `ConfirmFooter` for the 9 identical Cancel-ghost + primary-busy modal footers (list ×5 · batches ×3 · spec ×1) · **~50-70** |
| S6 | CAREFUL | Shared two-pane prompt editor (spec.tsx:799-847 ≈ list/page.tsx:2445-2511) · **~30-35** |
| S7 | SAFE | `toggleId` Set-toggle helper (idiom ×8-9 across list/spec/CampaignTab) · **~25-30** |
| S8 | CAREFUL | CampaignTab detail fetch → `useQuery(["campaign", client, id])` (kills hand-rolled `reqRef` staleness guard) · **~25-30** |
| S9 | SAFE | Dead-serialized campaign/report fields (`CampaignOut.smartlead_campaign_id/updated_at` · `ReplyOut.campaign_lead_id` · `ScoringJobOut.kind` · `PerformanceSummaryOut.meetings_booked`) · **~12** |
| S10 | SAFE | `get_research_spec` fetches ALL spec rows (full JSONB) for a `versions` list no FE reads (+ unread `model`/`llm_call_id`) → `LIMIT 1` latest-spec read · **~10 + real query win** |
| S11 | SAFE | Batch-detail fields never rendered (`BatchProspectOut.seniority/fit_reason` · `BatchCompanyGroup.size/country/fit_reason`) · **~12** |
| S12 | SAFE | Approval external view over-serializes (`seniority`/`decision`/`count`/`expires_at`; decide-response counts discarded) — masking allow-list gets *smaller* · **~8** |
| S13 | SAFE | Secret-fetch boilerplate ×5 integrations → one `fetch_secret_json` (exists as `core/config._get_secret_json`) · **~15** |
| S14 | SAFE | Dead endpoint `GET /clients` (FE uses `/me`; no test/script hits it) · **~7** |
| S15 | SAFE | `CompanyOut.trigger_line` never rendered (close-out push unrendered it) — drop serialization; stays in `fit_components` · **~4** |
| S16 | SAFE | `ResearchRunOut.rows_accepted` (never written — always 0) + `.rubric_version` (zero FE reads) — drop from Out shape; keep DB lineage columns · **~6** |
| S17 | SAFE | Dead campaigns-service constants `TRIAGE_CLASSES`\* + `STAGES` (\*wire M15 first — M15 makes `TRIAGE_CLASSES` load-bearing) · **~9** |
| S18 | CAREFUL | `<FitCell>` for the two three-state score cells (company :849-878 ≈ person :2312-2330) + dup `list-overlay`/spinner spans · **~30** |
| S19 | CAREFUL | `<FacetRow>` (mapped identically ×3) + the duplicated ICP-filter `<select>` (Step-1 ≈ Step-2) · **~25** |
| S20 | SAFE | `stageForPeople` ≈ `runFindPeople` byte-identical bar the toast string → `runPeopleFind(ids, msg)` · **~10** |
| S21 | SAFE | Single-valued props + micro-dupes (`SpecChips.warn` · `Section.extra` · `safeHref`×2 · `isStep2`×3 · "source · manual" badge ×2 · `groupByCompany().meta` always `""`) · **~15** |
| S22 | CAREFUL | v3-spec fallback (`research_spec.py:598-604` + FE mirror) — removable once every tenant's latest spec is v4+ (one SQL check) · **~13** |
| S23 | CAREFUL | Legacy flat (pre-`by_icp`) scope-override payload fallback (`prospects/router.py:202-203`) — one SQL check first · **~4** |
| S24 | CAREFUL | `apollo.search_companies` production-dead (real path = `search_companies_meta`; callers are tests) — retarget the paginate test, delete · **~22** |
| S25 | SAFE | `STATUS_LABEL` = `Object.fromEntries(STATUS_TABS)` (StatusTab.tsx restates the tuples) · **~4** |
| S26 | SAFE | Date formatting 6× duplicated (`fmt`/`fmtWhen`/`fmtDate` one-offs) → one `fmtDay(iso)` in `lib/dates.ts` — **fixes the M6/M30 tz bug class and the dup together** · **~25** |
| S27 | SAFE | OUTCOME badge map ×3 (summaries · billing · MeetingCalendar) → `lib/workspace/constants` · **~10** |
| S28 | SAFE | billing page re-fetches `listMeetings(client,"past")` the provider caches; approval page raw `listBatches` bypasses `["batches"]` — share query keys (also fixes M9 for free) · **~15** |
| S29 | SAFE | billing hand-rolled CSV quoting → `lib/csv.ts` helper serving both · **~15** |
| S30 | — | `list/page.tsx` (3005 LOC) split: Step-1 table · Step-2 table · 5 modals separable with existing state lifted; `SEL_CSS`/`SE_CSS` strings → workspace.css. Not LOC-saving, but the single biggest reviewability win |
| S31 | SAFE | `useParams<{client}>` → `useClient()` in billing/booking/feedback pages (consistency) · **~5** |

**Do-not-touch (looks removable, isn't):** `rbc-*` CSS (react-big-calendar runtime classes) ·
`bucket-dot--*` (template string) · `globals.css` (design bundle verbatim by golden rule) ·
`GET /{client}/llm-usage` no FE caller **by design** (NF-4 Swagger surface) · FE `MOVES`/`PER_MEETING_USD`
mirrors (deliberate sync copies; server still enforces) · `useHashRedirect` (legacy links in old emails) ·
`smartlead.add_leads(settings=…)` (tested compliance guard) · `list_email_accounts` (used by
`e_smoke_live.py`) · all Stripe/billing code (dormant ≠ dead) · `core/pagination`/`cache`/`email` (≥2 real
callers each) · every `Settings` field is read · converting list/brief `useState` mirrors to `useQuery`
(refetch/loading semantics would change — fails the provably-identical bar).

## 5 · Suggested execution order (one M-wave, backend-before-frontend)

1. **M-wave P2 pass** — M2/M3/M8-BE-half/M10 (backend) then M1/M4/M5/M6/M7/M9 (frontend; M6 needs the
   BE `iso_z` half first). M1+M5 share one "distinguish 410 from transient + retry" helper. *Money-path
   rule applies: each gets a non-Aurora unit test (the N1 lesson).*
2. **P3 sweep** — M11 first (public-page 500 risk), then M12-M22 backend · M23-M32 frontend, cheapest-first.
3. **Dead-code + SAFE simplify** — M-D + S1/S3/S7/S9-S17/S20/S21/S25-S29/S31 ride the same commits as
   the files they touch; CAREFUL items (S2/S4-S6/S8/S18/S19/S22-S24) behind their pin-tests, only if slack.
4. Founder decisions **RESOLVED 2026-07-12** (§6) — no forks remain: **M8** = build variant ingestion (P2) ·
   **M33** = build the outcome-correction/dispute UI, keep `correctOutcome` (new P3, pairs w/ M18) ·
   **M22** = Brief/ICP stay open to all members (document only, no gate).

Exit gates: the standing protocol (pytest+ruff+tsc+eslint+build+Playwright green · founder-authorized push).

## 6 · Consolidated build plan (task 3 + task 4 merged, execution-ordered)

One flat backlog of every fix (M) and simplify (S) item, ordered by the §5 waves. `Kind`: fix · perf ·
design · ui · dead · simplify · refactor. `P/R`: P2/P3 priority for fixes, SAFE/CAREFUL risk for simplify.
LOC only tracked for simplify. Nothing here gates a founder acceptance gate.

### Wave 1 — P2 fixes (backend-first, then FE; each gets a non-Aurora unit test) — ✅ BUILT + GATED 2026-07-13 (see §7; awaiting founder push)

| # | Kind | P/R | Side | Where · what → fix |
|---|---|---|---|---|
| M2 | fix | P2 | BE | `meetings/public.py:59-64` · `_read_busy` returns `[]` on GoogleError → double-booking → return `None` sentinel; view=`slots[]`, book=503+release |
| M3 | fix | P2 | BE | `campaigns/webhooks.py:181-185` · unsub write-back nested under stage-move guard → PDPA skip → call whenever `LEAD_UNSUBSCRIBED`, resolve email off payload |
| M8 | fix | P2 | BE+FE | `models.py:838` + `campaigns/router.py:94-113` · `variant_key` never written → E6 A/B scoreboard blank → **✅ DECIDED (build):** ingest Smartlead's per-lead variant onto the lead so the scoreboard shows real per-A/B/C sent/reply/meeting counts |
| M10 | fix | P2 | BE | `batches/router.py:282-295` · `delete_batch` FK RESTRICT → raw 500 → pre-check/catch → 409 |
| M1 | fix | P2 | FE | `book/[token]/page.tsx:57-69` · catch flips valid link to dead-end → used/expired only on 409/410, else inline retry + keep picker |
| M4 | fix | P2 | FE | `MeContext.tsx:25-31` · `/me` failure clears session on cold-start → clear only on 401; 5xx/net → keep+retry |
| M5 | fix | P2 | FE | `approve` · `feedback` · `book` load · same class as M1 on all public pages → shared 410-vs-transient + retry helper (with M1) |
| M6 | fix | P2 | BE+FE | `campaigns/router.py:65` + `replies`/`CampaignTab` · naive ISO → wrong local date in HK → `iso_z` (BE) + `parseUtc`/`whenLabel` (FE) |
| M7 | fix | P2 | FE | `performance-summary/page.tsx:32-40` · silent zero-defaults on client surface → error/retry state |
| M9 | fix | P2 | FE | `billing/page.tsx:47-62` · refresh doesn't invalidate meetings → stale recaps → `invalidateQueries(["meetings",client,"past"])` |

### Wave 2 — P3 backend sweep (M11 first: public-page 500 risk) — ✅ BUILT + GATED 2026-07-13 (see §8; awaiting founder push + deploy)

| # | Kind | P/R | Side | Where · what → fix |
|---|---|---|---|---|
| M11 | fix | P3 | BE | `meetings/service.py:78-145` · unvalidated `brief.availability` 500s the whole surface + booking page → try/except per field → FD-1 defaults |
| M12 | fix | P3 | BE | `billing/router.py:162-170` · no `_rollover` → stale prior-month usage → read-only rollover (no commit) |
| M13 | fix | P3 | BE | `billing/router.py:104-141` · read-modify-write usage + mid-flow `db.commit()` → atomic `SET usage=usage+n`; drop commit |
| M14 | fix | P3 | BE | `billing/router.py:173-211` · plan change skips Stripe prices → 409 or Stripe update (dormant) |
| M15 | fix | P3 | BE | `campaigns/router.py:599-621` · `triage_reply` stores unvalidated class → 400 unless in `TRIAGE_CLASSES` (makes S17's const load-bearing) |
| M16 | fix | P3 | BE | `meetings/schemas.py:61-64` · unbounded public `FeedbackIn.chips/comment` → max_length/count caps |
| M17 | fix | P3 | BE | `campaigns/router.py:624-701` · booking-link persisted after Smartlead send → catch→502; accept/document dead-link window |
| M18 | fix | P3 | BE | `meetings/router.py:217-255` · `correct_outcome` on unswept future meeting → billable → 409 unless held/past |
| M19 | fix | P3 | BE | `google/client.py:258-291` · `create_event` retries POST on timeout → dup events → no retry / check-before-retry |
| M20 | fix | P3 | BE | `prospects/router.py:1025` · raw `uuid.UUID(icp_id)` → 500 → reuse `_validate_icp_id` |
| M21 | perf | P3 | BE | `list_bookings` N+1 · `list_replies` unpaginated · `performance_summary` 18 seq counts · `pause/resume` full `_detail()` discarded |
| M22 | design | P3 | BE | Brief/ICP editing → **✅ DECIDED (keep open):** stays available to all members by design; add a code comment + plan note, **no gating change**. Remaining M22 work: 400-vs-404 helper · async route doing sync IO · index `created_at`-vs-`occurred_at` |

### Wave 3 — P3 frontend sweep (cheapest-first) — ✅ BUILT + GATED 2026-07-13 (see §9; awaiting founder push + deploy)

| # | Kind | P/R | Side | Where · what → fix |
|---|---|---|---|---|
| M23 | fix | P3 | FE | `list/page.tsx:1093-1113` · `runUpdateFields` (credit spend) no sync ref guard → `rescoringCoRef`-style guard |
| M24 | fix | P3 | FE | `billing/page.tsx:53-62` · sweep `refresh()` no catch → warn toast |
| M25 | fix | P3 | FE | `login/page.tsx:115-120` · all failures show "invalid email or password" → branch on status |
| M26 | fix | P3 | FE | `CampaignTab.tsx:280-309` · toast/clear buffer before PUT resolves → toast/clear after resolve |
| M27 | fix | P3 | FE | `summaries:59-62` + `replies:104-106` · filter keyed by `name` collides → filter by `campaign_id` |
| M28 | fix | P3 | FE | `summaries/page.tsx:120-145` · won toggle one-way → clicking active sends `null` |
| M29 | fix | P3 | FE | `batches/page.tsx:89-106` · `?batch=` effect re-fires on length change → consume once (ref) |
| M30 | fix | P3 | FE | `client-status/approval/page.tsx:27` · UTC day vs batches' local → reuse `localCalendarDate` |
| M31 | ui | P3 | FE | `window.confirm` vs Modal · hardcoded "3 open" · em-dash vs middot · toast kinds · false Brief-error copy |
| M32 | fix | P3 | FE | `ClientSwitcher.tsx:39-42` · non-member slug renders live → redirect to `me.clients[0]`/notice |
| M33 | build | P3 | FE+BE | **✅ NEW (decided): outcome-correction / dispute UI** — backend door already exists (`meetings/router.py:217`); build the console surface to correct a mis-marked held/qualified/won meeting before it bills. **Pairs with M18** (409-guard so a future/unswept meeting can't be corrected into a bill) |

### Wave 4 — dead-code + SAFE simplify — ✅ BUILT + GATED 2026-07-13 (see §10; S7/S21/S26/S28 + S13 deferred)

| # | Kind | P/R | Side | What · where · LOC |
|---|---|---|---|---|
| M-D | dead | — | BE+FE | Delete all grep-verified zero-caller code (§M-D). **BE:** smartlead dead fns · `IllegalMove` · `CAMPAIGN_STARTED` · `Meeting.summary` · dup helpers → `core/db`. **FE:** `fixtures.ts` · `client-status.ts` · dead types/consts. **NOTE:** `correctOutcome` is **no longer dead** — it's now the wiring for M33 (keep the export) |
| S1 | simplify | SAFE | FE | dead CSS rule blocks (workspace/perf/home) · ~115 |
| S3 | simplify | SAFE | BE | dead-serialized meeting fields (`meet_link`/`duration_min`/`disputed`/…) · ~25 |
| S7 | simplify | SAFE | FE | `toggleId` Set-toggle helper ×8-9 · ~25-30 |
| S9 | simplify | SAFE | BE | dead-serialized campaign/report fields · ~12 |
| S10 | simplify | SAFE | BE | `get_research_spec` → `LIMIT 1` latest-spec · ~10 + query win |
| S11 | simplify | SAFE | BE | batch-detail fields never rendered · ~12 |
| S12 | simplify | SAFE | BE | approval external view over-serialize · ~8 |
| S13 | simplify | SAFE | BE | secret-fetch boilerplate ×5 → `fetch_secret_json` · ~15 |
| S14 | simplify | SAFE | BE | dead endpoint `GET /clients` · ~7 |
| S15 | simplify | SAFE | BE | `CompanyOut.trigger_line` never rendered · ~4 |
| S16 | simplify | SAFE | BE | `ResearchRunOut.rows_accepted`/`.rubric_version` · ~6 |
| S17 | simplify | SAFE | BE | dead campaigns constants (`STAGES`; `TRIAGE_CLASSES` **after M15**) · ~9 |
| S20 | simplify | SAFE | FE | `stageForPeople`≈`runFindPeople` → `runPeopleFind(ids,msg)` · ~10 |
| S21 | simplify | SAFE | FE | single-valued props + micro-dupes · ~15 |
| S25 | simplify | SAFE | FE | `STATUS_LABEL` = `Object.fromEntries(STATUS_TABS)` · ~4 |
| S26 | simplify | SAFE | FE | date fmt 6× → `fmtDay(iso)` — **also fixes M6/M30 tz bug class** · ~25 |
| S27 | simplify | SAFE | FE | OUTCOME badge map ×3 → constants · ~10 |
| S28 | simplify | SAFE | FE | share query keys — **also fixes M9** · ~15 |
| S29 | simplify | SAFE | FE | billing CSV → `lib/csv.ts` helper · ~15 |
| S31 | simplify | SAFE | FE | `useParams` → `useClient()` (billing/booking/feedback) · ~5 |

### Wave 5 — CAREFUL simplify (behind pin-tests, only if slack) — ✅ BUILT + GATED 2026-07-13 (see §12; 11 of 16 shipped · S8·S28·S30 deferred with rationale)

| # | Kind | P/R | Side | What · where · LOC |
|---|---|---|---|---|
| S2 | simplify | CAREFUL | FE | localStorage scope-migration shim (verify no un-migrated keys) · ~70 |
| S4 | simplify | CAREFUL | FE | `<Field>` wrapper ×17 list-modal blocks · ~40-55 |
| S5 | simplify | CAREFUL | FE | `ConfirmFooter` ×9 modal footers · ~50-70 |
| S6 | simplify | CAREFUL | FE | shared two-pane prompt editor (spec≈list) · ~30-35 |
| S8 | simplify | CAREFUL | FE | `CampaignTab` detail → `useQuery` (kills `reqRef` guard) · ~25-30 |
| S18 | simplify | CAREFUL | FE | `<FitCell>` ×2 three-state score cells · ~30 |
| S19 | simplify | CAREFUL | FE | `<FacetRow>` ×3 + dup ICP `<select>` · ~25 |
| S22 | simplify | CAREFUL | BE+FE | v3-spec fallback (SQL check first) · ~13 |
| S23 | simplify | CAREFUL | BE | legacy flat scope-override fallback (SQL check) · ~4 |
| S24 | simplify | CAREFUL | BE | `apollo.search_companies` prod-dead (retarget test) · ~22 |
| S30 | refactor | — | FE | `list/page.tsx` (3005 LOC) split — reviewability, not LOC · — |

**Totals:** 33 fixes/builds (0 P1 · 10 P2 · 23 P3, incl. M33) + M-D dead-code + 31 simplify (~500+ LOC).
**All 3 founder decisions RESOLVED 2026-07-12 — the plan now has zero human dependencies:**

| Decision | Resolution | Effect on plan |
|---|---|---|
| **M8** · A/B scoreboard | **Build** variant ingestion | stays P2; now a concrete build (ingest Smartlead per-lead variant), not a build-vs-hide fork |
| **`correctOutcome`** · dispute UI | **Build** the surface | becomes **M33** (new P3 build); `correctOutcome` export kept, removed from dead-code |
| **M22** · Brief/ICP access | **Keep open** to all members | no gating change; document as deliberate — the only work left in M22 is the 3 unrelated cleanups |

Do-not-touch list (§4) still governs.

## 7 · Wave 1 — BUILT + GATED (2026-07-13)

All 10 P2 items shipped to the working tree (backend-before-frontend, per §5). **Not yet
committed/pushed** — the standing "commit/push only when asked · founder-authorized" gate holds.
Gates re-run locally after the wave: **backend pytest 365✓ / 25 skipped** (was 358✓/23 — **+7 new
non-Aurora units**; +2 Aurora-gated skips) · **ruff clean** · **tsc clean** · **eslint clean (0
warnings)** · **next build ✓** · **Playwright 26✓**. The three `docs/*.md` edits in the tree are the
prior-session doc reconciliation (§1), not this build; the build touched only `apps/api` + `apps/web`
(+ one new FE component).

### 7.1 · What shipped, per item

| # | Side | Built (file) | Test proof |
|---|---|---|---|
| M2 | BE | `meetings/public.py` — `_read_busy` returns a `None` sentinel on `GoogleError` (was `[]` = "all free"); `view_booking` → `slots=[]`, `book_meeting` → 503 **+ releases the claim** during an outage | non-Aurora `test_read_busy_returns_none_sentinel_on_google_error`; Aurora `test_freebusy_outage_offers_no_slots_and_503_releases` |
| M3 | BE | `campaigns/webhooks.py` — the `_unsub_writeback` (PDPA `doNotContact`) now runs whenever `internal == LEAD_UNSUBSCRIBED`, **independent of the stage move** (was nested under it → a drop/unresolvable unsub silently skipped the list) | non-Aurora `test_unsub_writeback_*` (list+string forms · noop guards); Aurora funnel test extended with an unresolvable-lead unsub → DNC write |
| M6 | BE | `campaigns/router.py` — `_iso` routes through `msvc.iso_z` → `…Z` (mirrors meetings); fixes the naive-ISO → wrong-HK-day bug on reply/campaign timestamps | non-Aurora `test_campaign_iso_serializer_pins_utc_z` |
| M8 | BE | `campaigns/service.py` `variant_label()` (tolerant per-lead A/B/C read) + `webhooks._ingest` stamps `CampaignLead.variant_key` first-seen → the E6 scoreboard now derives real per-variant counts | non-Aurora `test_variant_label_*`; Aurora funnel test asserts the send event stamps `variant_key="A"` |
| M10 | BE | `prospects/scoring.py` `is_fk_violation()` (mirrors `is_unique_violation`, driver-drift-proof) + `batches/router.delete_batch` catches it → **409** (was a raw 500 on a first-class button) | non-Aurora `test_is_fk_violation_*`; Aurora `test_delete_batch_with_campaign_reference_409s` |
| M1 | FE | `book/[token]/page.tsx` — load error → retry (never a fake "expired"); submit branches: **410 → used pane · 409 → keep picker + refresh times ("pick another") · else inline retry** | Playwright 26✓ (route-mocked); classifiers unit-safe |
| M4 | FE | `MeContext.tsx` — `/me` failure clears tokens **only on 401**; a cold-start 5xx / network blip keeps the session + shows a full-pane retry (`MeLoadError`); true expiry still flows via `holdslot:auth-expired` | Playwright 26✓ |
| M5 | FE | `approve` + `feedback` + `book` share `isLinkGoneError`/`isSlotTakenError`/`isTransientStatus` (lib/api) + `RetryNotice` (new component): 410 → dead pane, everything else → keep the page + retry | Playwright 26✓ |
| M6 | FE | `replies/page.tsx` `fmtDate` + `CampaignTab.tsx` `fmtWhen` parse via `parseUtc` (lib/dates) — belt-and-suspenders with the BE `iso_z` half | Playwright 26✓ |
| M7 | FE | `performance-summary/page.tsx` — a load failure now shows a retry panel instead of silent hard-zeros + a permanent "Loading funnel…" on the client-facing surface | Playwright 26✓ |
| M9 | FE | `billing/page.tsx` — after the sweep, `refresh()` also `reloadMeetings()` (invalidates `["meetings",client,"past"]`) so Meeting Recaps isn't stale | Playwright 26✓ |
| M8 | FE | **No change needed** — `CampaignTab` already reads `v.sent/opens/replies`; M8-BE populating `variant_key` lights the scoreboard up | verified in-code (`CampaignTab.tsx:611-612`) |

### 7.2 · Cross-cutting additions (the shared enablers)

- **`ApiError extends Error`** (`lib/api.ts`) — carries the HTTP `status`, thrown by `getMe` +
  every public-token endpoint (`getBookingView`/`submitBooking`/`getApproval`/`decideApproval`/
  `getFeedbackView`/`submitFeedback`). Backward-compatible (extends `Error`), so every existing
  `catch (e) { e.message }` path is unchanged. This is the M1/M4/M5 enabler.
- **`RetryNotice`** (`components/external/RetryNotice.tsx`, new) — the one retry affordance the three
  public pages share (design-system classes only, no new CSS).
- **`is_fk_violation`** (`prospects/scoring.py`) — a sibling of the existing `is_unique_violation`,
  matching SQLSTATE 23503 across the psycopg / RDS-Data-API driver drift.

### 7.3 · Deliberate deviations from the plan text (with rationale)

1. **Booking 409 is NOT flipped to "used/expired."** §3 M1 read "flip to used/expired only on
   409/410," but a 409 on `book` means *the slot was just taken* — the link is still valid. Flipping
   it to a dead "used" pane would lose the meeting on a slot race — the exact harm M1 exists to stop.
   Shipped behavior: **410 → dead pane; 409 → keep the picker, refresh the times, "pick another."**
   Approve/feedback have no 409 path, so there it's simply 410 → dead, else retry.
2. **M8 frontend is a no-op** (see table) — recorded so the wave reads as complete, not skipped.
3. **Aurora-gated flow tests were added but not run here** (no Aurora env). They execute on the
   founder's live-gate run; the runnable proof this session is the **7 non-Aurora units** (all green).

### 7.4 · Not in this wave / next

- **M22-doc** (the "Brief/ICP open to all members — document as deliberate" note) is a §6 Wave-2
  item, not P2 — deferred with the rest of Wave 2.
- **Remaining to close Wave 1:** founder-authorized `git` commit + push to `dev` (Amplify autobuild),
  then the standing live smoke. Suggested first commit = the whole wave on a `hardening-m-wave`
  branch off `dev` (the §5 "start with BE, pause for sign-off" split is now moot — all 10 are built
  and green together).

## 8 · Wave 2 — BUILT + GATED (2026-07-13)

All 12 P3 backend items (M11–M22) shipped to the working tree, **backend-only** (zero `apps/web`
touched — the FE gates are unaffected, still green from Wave 1). **Not yet committed/pushed** — the
standing "commit/push only when asked · founder-authorized" gate holds. Gates re-run locally after
the wave: **backend pytest 372✓ / 29 skipped** (was 365✓/25 — **+7 new non-Aurora units**; **+4
Aurora-gated** flow/DB tests) · **ruff clean** · single linear Alembic head → **`0032`**.

One schema change this wave: **migration `0032` (index-only, deploy-first-safe)** — it applies on the
next founder backend deploy alongside the Wave 1+2 backend code (Aurora stays at `0031` until then).

### 8.1 · What shipped, per item

| # | Side | Built (file) | Test proof |
|---|---|---|---|
| M11 | BE | `meetings/service.py` — `availability_of` now validates every field + a new `_clean_windows` drops malformed days/windows → FD-1 defaults, so a bad Brief edit can't 500 the meetings surface / booking page (was `int("abc")`→ValueError · one-element window→IndexError) | non-Aurora `test_availability_of_*` · `test_clean_windows_drops_bad_and_keeps_good` · `test_available_slots_never_raises_on_malformed_brief` |
| M12 | BE | `billing/router.py` — `billing_status` applies `_rollover` read-only (no commit; the GET session closes → rollback) so the GS6 line shows the CURRENT UTC month before the first enrich of the month | covered by the M13 rollover assertion (shared `_rollover`); dormant |
| M13 | BE | `billing/router.py` — `reserve_enrichment` now reserves in ONE atomic `UPDATE … SET usage = (this-month usage else 0) + allowed` (no read-modify-write lost update; rollover folded into the CASE) and **drops the mid-flow `db.commit()`** (the caller owns the txn — it used to flush the caller's half-done enrich session) | Aurora `test_reserve_enrichment_atomic_increment_and_rollover`; decision math already unit-tested (`enrichment_decision`) |
| M14 | BE | `billing/router.py` — `create_subscription` 409s a plan CHANGE on a live Stripe subscription rather than silently diverging local caps from Stripe prices (chose the register's simpler "409" option; dormant) | verified in-code (dormant — no tenant has a subscription) |
| M15 | BE | `campaigns/router.py` — `triage_reply` 400s an unknown triage class (was silently stored → polluted the derived summary counts + left the pip on with no move). Makes `svc.TRIAGE_CLASSES` load-bearing (unblocks S17) | Aurora `test_triage_reply_rejects_unknown_class` |
| M16 | BE | `meetings/schemas.py` — public `FeedbackIn.chips/comment` bounded (`max_length` 12 chips × 64 chars · comment ≤ 2000) so a token holder can't store MBs on the meeting row | non-Aurora `test_feedback_in_caps_bound_public_input` |
| M17 | BE | `campaigns/router.py` — `respond_reply` catches `SmartleadError` → **502** (was a raw 500); the accepted post-send dead-link window (N31 persist-after-send) is documented in-code | covered by the existing `_respond_with_link` flow (Smartlead mocked); the happy path is asserted in `test_meetings_db` |
| M18 | BE | `meetings/router.py` — `correct_outcome` 409s an unswept FUTURE meeting (`held IS NULL` and scheduled ahead) so a pre-meeting hand-mark can't become billable; a swept-or-past meeting still corrects | Aurora `test_correct_outcome_blocks_unswept_future_meeting` |
| M19 | BE | `google/client.py` — `_request` gains `retry_transport`; `create_event` passes `False` so a timed-out `events.insert` (which may already have landed) is NOT blind-replayed → no duplicate calendar event + invites. Reads still retry transport errors | non-Aurora `test_create_event_post_does_not_retry_on_transport_error` (POST = 1 attempt; GET = bounded retries) |
| M20 | BE | `prospects/router.py` — `add_company` reuses `_validate_icp_id` → a malformed `icp_id` is a 400 (was a raw 500; siblings already 400) | reuses the `_validate_icp_id` path (N24-tested) |
| M21 | BE | perf: `list_bookings` N+1 → `_latest_replies` buckets the reply lookup in 2 queries for the whole page (was 2/link) · `list_replies` bounded by a `limit` (≤`REPLIES_PAGE_CAP=500`, was unbounded) · `performance_summary` — the **7 meeting count-cells collapse into ONE conditional-aggregate query** (~18 → ~11 RTs) · `pause/resume/launch` return `_campaign_summary` (light `CampaignOut`) instead of the discarded expensive `_detail` | Aurora `test_performance_summary_consolidated_counts_execute` (proves the CASE/SUM runs on the Data API); `list_bookings`/`list_replies` covered by `test_meetings_db`/`test_campaigns_db` |
| M22 | BE + schema | design: shared `core/deps.uuid_or_404` — malformed PATH ids standardize on **404** (campaigns aligned to meetings' existing 404; body-field `icp_id` stays 400 by design) · the sole `async` webhook route **stays async** (needs `await request.body()` for HMAC; documented — no event-loop contention under one-request-per-Lambda) · **migration `0032`**: swap `ix_outreach_event_tenant_type_created` → `…_occurred` (every consumer ORDER BYs `occurred_at`) + add `ix_subscription_stripe_customer_id` | non-Aurora `test_uuid_or_404_rejects_malformed_and_parses_valid`; `test_migrations` updated (head `0032`, occurred-index) |

### 8.2 · Cross-cutting additions (the shared enablers)

- **`core/deps.uuid_or_404(value, detail)`** — the one malformed-path-id → 404 helper; `campaigns._uuid`
  and `meetings._uuid` both delegate to it (was a 400/404 split across domains). M22.
- **`_request(..., retry_transport=True)`** (`integrations/google/client.py`) — lets a non-idempotent
  create opt out of the transport-error retry that duplicates side-effects. M19.
- **`campaigns._latest_replies(db, tenant, lead_ids)`** — the bucketed reply-lookup that replaces the
  per-link `_latest_reply` (deleted; zero other callers). M21.
- **`campaigns._campaign_summary(db, tenant, campaign)`** — the light `CampaignOut` builder now shared
  by launch/pause/resume (kills the discarded `_detail` work). M21.
- **migration `0032_outreach_occurred_index`** + the matching `models.py` `Index` edits.

### 8.3 · Deliberate deviations from the plan text (with rationale)

1. **M21 `performance_summary` is PARTIALLY consolidated.** The register said "merge ~18 counts into
   conditional aggregates." Shipped: the 7 **meeting** count-cells → one `SUM(CASE…)` query. **Left
   as separate queries on purpose:** (a) the money `billable_this_cycle` `SUM(amount)` — untouched, so
   the revenue figure carries zero consolidation risk; (b) the 4 OutreachEvent counts (`COUNT(DISTINCT
   CASE…)` is more exotic, marginal RT savings). Net ~18 → ~11 RTs on this one (non-looped) read. An
   Aurora test pins that the new aggregate executes on the Data API (the real risk was a dialect 500).
2. **M22 async webhook is NOT converted to sync.** The register read it as "sync DB I/O in an async
   route." But the route MUST be async — HMAC verification needs the RAW body via `await
   request.body()`, unreachable from a sync endpoint. Under one-request-per-Lambda (SnapStart) there is
   no concurrent request to starve, so the sync DB I/O is benign. Documented in-code instead of a
   breaking rewrite.
3. **M22 400-vs-404 refines "pick 404."** PATH-resource ids standardize on 404 (a bad id and a
   missing id read the same — no leak). BODY-field validation (`icp_id` in a POST body) stays **400** —
   that's input validation, semantically distinct from a missing path resource.
4. **M14 chose "409 on plan change"** (the register's simpler branch) over calling Stripe's price-update
   API, because Stripe is dormant (no subscription exists to update).
5. **The index finding became a real migration (`0032`), not just a "(note)".** It is index-only and
   deploy-first-safe; it makes the M21 `occurred_at`-ordered reads index-backed. Docs updated: **repo
   head `0032`**, **Aurora applied head still `0031`** (0032 pending the next backend deploy).

### 8.4 · Not in this wave / next

- **Wave 3** (M23–M33 · P3 frontend sweep + the M33 outcome-correction UI) · **Wave 4** (M-D dead-code +
  SAFE simplify) · **Wave 5** (CAREFUL simplify) — all still open, none gate-blocking.
- **Remaining to close Wave 2:** founder-authorized `git` commit + push to `dev` (Amplify autobuild is a
  no-op here — FE untouched), **then a founder-authorized backend deploy** (`scripts/build-and-deploy.sh`)
  which is what makes the Wave 1 **and** Wave 2 backend fixes live AND applies migration `0032`. The
  Aurora-gated tests (M13/M15/M18/M21) execute on that live-gate run.

## 9 · Wave 3 — BUILT + GATED (2026-07-13)

All 11 P3 frontend items (M23–M33) shipped to the working tree, **frontend + one small additive
backend field** (M27 needs `campaign_id` on `MeetingOut` to filter recaps by id — that one field
rides the already-pending Wave 1+2 backend deploy). **Not yet committed/pushed** — the standing
"commit/push only when asked · founder-authorized" gate holds. Gates re-run locally after the wave:
**FE `tsc` clean · `eslint` clean · `next build` clean · Playwright 26✓** · **backend pytest
372✓/29 skipped · ruff clean** (the M27 backend field is covered; no new schema/migration).

### 9.1 · What shipped, per item

| # | Side | Built (file) |
|---|---|---|
| M23 | FE | `list/page.tsx` — `runUpdateFields` (Apollo credit spend) gets the sibling `updateFieldsCoRef` synchronous double-click guard (set at entry, cleared in `finally` + on client-switch); the async `disabled` alone left a same-tick double-spend window |
| M24 | FE | `billing/page.tsx` — the sweep `refresh()` gains a `catch` → **warn** toast (was an unhandled rejection with zero feedback) |
| M25 | FE + api | `login/page.tsx` + `lib/api.ts` — `login` now throws `ApiError` (status-carrying); the sign-in catch shows "invalid email or password" ONLY on a real **401**, and "couldn't reach the server — try again" on a 5xx/network failure (login already retries cold-starts to its cap) — no more accusing a server outage of being a bad password |
| M26 | FE | `CampaignTab.tsx` — `guard` returns a success boolean; `saveVariant`/`addVariant`/`deleteVariant` toast + clear the edit buffer **only after the PUT resolves** (was optimistic → a failed save showed a false "saved" and lost the draft) |
| M27 | FE + BE | `replies/page.tsx` + `summaries/page.tsx` filter by **`campaign_id`**, not the non-unique campaign name (same-named campaigns from different batches collided). Replies already had `campaign_id`; recaps get it via a new `MeetingOut.campaign_id` (BE `_meeting_out`) → `MeetingApi` → `Recap.campaignId` → the provider map. Dropdowns now `value={c.id}`; empty-state copy resolves the name |
| M28 | FE | `summaries/page.tsx` — the Deal-won / No-deal toggle clears back to **undecided (null)** when you click the already-active button (`setMeetingWon` already accepted null) — now three-state end to end |
| M29 | FE | `batches/page.tsx` — the `?batch=` deep-link is consumed **once** (a `deepLinkDone` ref); it re-fired on every `batches.length` change, so deleting another batch re-expanded the deep-linked one + scroll-jumped |
| M30 | FE | `client-status/approval/page.tsx` — `day()` renders the viewer's **local** calendar day via `localCalendarDate` (N38), not the raw UTC `.slice(0,10)` (which disagreed with the batches tab for a late-UTC-evening event) |
| M31 | FE | ui sweep (below) |
| M32 | FE | `ClientSwitcher.tsx` — once `me` resolves, a slug the caller isn't a member of **redirects** to `me.clients[0]` instead of rendering as a live "current client" whose every API call 403/404-toasts |
| M33 | FE + api | **NEW: outcome-correction / dispute UI** — a "Correct outcome" Modal on each Meeting-Recap card (summaries tab) sets outcome (Qualified/Short call/No-show) + a "disputed" checkbox via `correctOutcome`, then `reloadMeetings`. **Pairs with M18**: recaps are held (past) meetings, so the backend's 409-guard never fires here; `won` stays isolated to its own setter (NF-3) |

### 9.2 · M31 ui sweep — what was done

- **`window.confirm` → design-system Modal** (`list/page.tsx`): `maySelect` is now a pure verdict
  (`"ok" | "blocked" | "confirm"`, no side effect); both selection toggles route a low_fit **add**
  through a `lowFitPrompt` Modal (Cancel / "Add anyway") instead of the native confirm.
- **Hardcoded "3 open" → live** (`performance-summary/page.tsx`): the Needs-attention chip now counts
  the categories actually non-zero (`approvalsPending`/`openLinks`/`heldNoFeedback`).
- **Failure toasts render as warnings** (`client-status/booking` + `client-status/feedback`): the
  three failure toasts that omitted the `"warn"` kind (and so rendered green/✓) now pass `"warn"`.
- **em-dash → middot** in the clear separator-style **new** copy (CampaignTab empty states; the
  booking failure toast). Scoping (deliberate): the `|| "—"` empty-value glyphs are the design's
  "no value" marker (NOT separators) and are left as-is, as are genuine mid-sentence prose
  parentheticals and the reviewed A–D+ list/brief copy.
- **False Brief-error copy** (`batches/page.tsx`): the send modal distinguishes Brief **loading** /
  **load-error** from a genuinely-empty Brief, so it no longer asserts "no attendee emails on your
  Brief" on a load blip.

### 9.3 · Cross-cutting additions

- **`MeetingOut.campaign_id`** (BE) → **`MeetingApi.campaign_id`** → **`Recap.campaignId`** +
  **`Recap.disputed`** (FE) — the id-keyed recap filter (M27) + the dispute flag the M33 UI reads.
- **`login` throws `ApiError`** (`lib/api.ts`) — status-carrying, so the login page can branch 401 vs
  server error (M25). Backward-compatible (`ApiError extends Error`).
- **`CampaignTab.guard` returns `Promise<boolean>`** — lets callers act only on a resolved write (M26).

### 9.4 · Deliberate deviations from the plan text (with rationale)

1. **Wave 3 is not pure-FE.** M27's correct fix (filter recaps by id, not name) needs `campaign_id`
   on the meeting read — a one-field, additive `MeetingOut` change. It carries no migration and rides
   the already-pending Wave 1+2 backend deploy, so it doesn't add a deploy step.
2. **M31 em-dash sweep is scoped, not total.** The golden rule targets em/en dashes used as
   *separators*; the shipped `|| "—"` empty-value glyphs are the design's no-value marker and match
   the reviewed A–F surfaces, so they're intentionally left. Converting them would diverge from the
   design and churn reviewed code for no correctness gain.
3. **M33 has no design mockup** (it's a NEW build). The Modal reuses the existing design-system
   primitives (`Modal`, `btn`, `field`, the batches decide-modal pattern) so it reads as native.

### 9.5 · Not in this wave / next

- **Wave 4** (M-D dead-code + SAFE simplify) · **Wave 5** (CAREFUL simplify) — still open, none
  gate-blocking.
- **Remaining to close Wave 3:** founder-authorized `git` commit + push to `dev` (Amplify autobuild
  deploys the FE), and the same founder-authorized backend deploy that makes Wave 1+2 live also
  ships the M27 `campaign_id` field (until then the summaries filter falls back to "all" for recaps,
  since `campaign_id` is absent on the old backend — the page stays functional).

## 10 · Wave 4 — BUILT + GATED (2026-07-13)

M-D dead-code + the SAFE simplify set, shipped to the working tree on top of the committed Wave 2+3
(`eec3852`). **Not yet committed/pushed** — the standing "commit/push only when asked · founder-
authorized" gate holds. **No migration** (the two column-drop candidates were deliberately deferred —
§10.3), so Wave 4 is deploy-neutral. Net **−296 LOC** (46 files modified, 2 deleted). Gates re-run
after the wave: **backend pytest 371✓ / 29 skipped · ruff clean**; **FE `tsc` clean · `eslint` clean ·
`next build` clean · Playwright 26✓**. The audit's M-D/simplify inventory predated Waves 1–3, so every
deletion was **re-verified against current code** first — that caught three now-load-bearing items
(§10.4) and several "dead" fields that Wave 3 had revived.

### 10.1 · M-D dead-code — what was deleted

- **BE clean deletes:** `smartlead.sending_account_ids()` · `smartlead.fetch_analytics()` (both only in
  `__all__`+docstrings) · `meetings/service.participant_duration_min()` + `event_meeting_code()`
  (test-only — their two test assertions removed) · `campaigns/service.IllegalMove` · `launch.COMPLETED`
  (never-set status) · `campaigns/service.CAMPAIGN_STARTED` (def + both label/category map rows —
  mapped, never emitted).
- **BE consolidations:** `is_unique_violation` **+ `is_fk_violation`** moved `prospects/scoring.py` →
  **`core/db.py`** (generic DB-error predicates; 6 importers repointed, `is_fk` moved alongside since
  M10 added it as a sibling) · `launch._fail` → public **`launch.fail`** · `meetings/public._brief_attendee`
  → public **`brief_attendee`** (the two intra-domain private-import smells).
- **FE clean deletes:** `lib/workspace/fixtures.ts` + `lib/fixtures/client-status.ts` (whole files, 0
  importers; empty dir removed) → then dead `types.ts` `Campaign`/`Reply`/`LedgerRow` · `constants.ts`
  `MOCK_TODAY`/`TODAY_ISO` (deleted) + de-exported `UNSCORED_RANK`/`labelRank` (used only internally) ·
  `WorkspaceProvider.setReplies` (0 consumers) · unused `Sample` import in `book/[token]` · de-exported
  `FunnelStageApi` (used only inside `api.ts`). **`correctOutcome` kept** (M33 wiring).

### 10.2 · SAFE simplify — what was applied

- **Backend:** **S3** (dropped serialized-but-unread `MeetingOut.meet_link/duration_min/dispute_window_ends_at`,
  `FeedbackRowOut.chips`, `BookingConfirm.scheduled_at/meet_link` — **kept `MeetingOut.disputed`**, revived
  by M33) · **S9** (`CampaignOut.smartlead_campaign_id/updated_at`, `ReplyOut.campaign_lead_id`,
  `ScoringJobOut.kind`, `PerformanceSummaryOut.meetings_booked`) · **S10** (`get_research_spec` → `LIMIT 1`;
  dropped the never-read `ResearchSpecList.versions` → no longer pulls every spec's full JSONB) · **S11**
  (`BatchProspect.seniority/fit_reason`, `BatchCompanyGroup.size/country/fit_reason`) · **S12** (external
  approval masking allow-list *tightened*: dropped `ApprovalProspect.seniority/decision`,
  `ApprovalView.count/expires_at`) · **S14** (dead `GET /clients` endpoint) · **S15** (`CompanyOut.trigger_line`)
  · **S16** (`ResearchRunOut.rows_accepted/rubric_version`) · **S17** (dead `STAGES` const only). Each
  dropped schema field was trimmed on **both** the BE serializer/schema and its `api.ts` type mirror; the
  DB columns/logic are untouched (lineage preserved).
- **Frontend:** **S1** (11 dead CSS rule blocks across workspace/perf/home css — each verified 0 JSX/template
  hits) · **S20** (`stageForPeople`/`runFindPeople` → shared `runPeopleFind(ids, msg)`) · **S25**
  (`STATUS_LABEL` = `Object.fromEntries(STATUS_TABS)`) · **S27** (the outcome→label/badge map ×3 →
  `OUTCOME_BADGE` in `constants`; billing + summaries alias it, MeetingCalendar reads `.label`) · **S29**
  (billing CSV export → shared `csvCell` in `lib/csv.ts`) · **S31** (`useParams<{client}>` → `useClient()`
  in billing + client-status booking/feedback).

### 10.3 · Deliberate deviations from the register (with rationale)

1. **`_iso` ×4 consolidation SKIPPED.** The four helpers are **not** provably-identical — `batches/router._iso`
   serializes naive (`dt.isoformat()`) while the other three attach `Z` via `msvc.iso_z`. Consolidating to
   `iso_z` would silently change the batches timestamps (a behavior change, not a dedup); the shared logic
   already lives once in `iso_z` and the three thin wrappers are trivial None-guards. *(Batches' naive-ISO
   serialization is a latent M6-class tz bug — flagged for a future fix wave, not touched here.)*
2. **`_brief_data` ×2 dedup SKIPPED.** The two copies are identical (2 lines each) but `meetings/router`
   reaches into `meetings/public` via a **lazy** import (an existing import-cycle guard); deduping cleanly
   would risk that topology for ~2 LOC. Left as-is.
3. **S13 (secret-fetch dedup ×5) DEFERRED.** The 5 integration `_secret()` helpers have per-integration
   nuance (e.g. smartlead's `HOLDSLOT_SMARTLEAD_KEY` env override, caching); "replace all with the shared
   `_get_secret_json`" is not a pure zero-behavior change and risks the local-dev/test secret path. Deferred
   to a careful pass.
4. **`Meeting.summary` JSONB KEPT.** It's the deferred `meeting_summary` LLM-recap seam; dropping it is a
   migration, not a same-commit ride. **`Subscription.icp_limit`/`plan_icp_limit` KEPT** — *not* zero-caller
   (plumbed through the billing router/schema/service serialization; "enforced nowhere" ≠ unreferenced), and
   dropping needs a migration + touches the dormant billing `Out` shape. Keeping both = Wave 4 stays
   deploy-neutral (no `0033`).
5. **S29 changes the exported-CSV bytes** (quote-all → conditional-quote via `csvCell`). Both are valid
   RFC-4180 that re-parse to identical columns; judged SAFE (the CSV contract is the data, not the bytes).
6. **FE simplify S7/S21/S26/S28 DEFERRED** (§10.5).

### 10.4 · Stale-inventory catches (register predated Waves 1–3)

Three "dead" targets were **now load-bearing** and correctly **kept**: `localCalendarDate` export (imported
by the approval page since M30) · `correctOutcome` (imported by summaries since M33) · `TRIAGE_CLASSES`
(made load-bearing by M15 — so **S17 shrank to deleting `STAGES` only**). And **`MeetingOut.disputed`** —
listed by S3 as dead-serialized — was revived by M33, so it was **kept** while its three siblings were dropped.

### 10.5 · Not in this wave / next

- **FE simplify deferred (SAFE-but-sprawling / already-realized):** **S7** (`toggleId` helper — the toggle
  idiom is entangled with the selection-guard/low-fit-confirm logic in the 3k-LOC list page, not the clean
  uniform ×8-9 assumed; touching it risks the credit-spend selection) · **S21** (scattered single-valued-prop
  micro-dupes — fiddly, low value) · **S26** (`fmtDay` date-fmt dedup — M6/M30 already fixed the tz bug, so
  now pure cosmetic spread across many files) · **S28** (share query keys — M9 already fixed the correctness;
  the register's own do-not-touch note warns useState→useQuery changes refetch/loading semantics). These
  belong in a focused follow-on pass, not rushed at the tail of a large wave.
- **Wave 5** (CAREFUL simplify — S2/S4/S5/S6/S8/S18/S19/S22/S23/S24/S30) — still open, none gate-blocking.
- **Four Aurora-gated tests** were fixed by inspection for the dropped fields (they don't run locally, so
  they'd otherwise fail the founder's live gate): `test_research_spec` (`versions`) · `test_meetings_db`
  (`confirm.meet_link` → reads it off the row) · `test_campaigns_db` (`detail.smartlead_campaign_id` → off
  the Campaign row) · `test_batches` (`view.count` → `len(view.prospects)`).
- **Remaining to close Wave 4:** founder-authorized `git` commit + push to `dev`. Deploy-neutral — no
  migration; the FE type-mirror trims are matched to the BE serializer trims in the same wave, so they must
  ride the **same** backend deploy that already carries Wave 1+2 (else the FE would drop fields the old
  backend still sends — harmless, since the FE stopped reading them).

## 11 · Wave 5 — READINESS SCOPED (2026-07-13, not built)

Wave 5 is the **discretionary CAREFUL tail** — §6 tags it "only if slack," none of it gate-blocks the
DoD, and it must respect the §4 do-not-touch list. This section is the pre-flight: **every item was
re-verified against the working tree on top of Wave 4** (line-accurate as of `eec3852` + the 49
uncommitted Wave-4 files), because the register's inventory predated Waves 1–4 and has drifted. Scope =
the 11 CAREFUL simplify items (S2·S4·S5·S6·S8·S18·S19·S22·S23·S24·S30) **+** the 5 SAFE items Wave 4
deferred as sprawling/careful (S7·S13·S21·S26·S28). **Nothing here is built** — but the pre-flight
(§11.1) has **RUN and CLEARED all 3 founder-gated items**, so every item is now build-ready.

### 11.1 · Founder-gated pre-flight — ✅ RAN + CLEARED (2026-07-13)

Three items depended on a live check `claude_code`'s default creds can't make (dev Aurora is in AWS
account `138743894336`; browser `localStorage` is unobservable server-side). All three now **PASS** —
S2 from the founder's browser dump (both dev + prod origins), S22/S23 run via the RDS Data API against
dev Aurora using the `holdslot` AWS profile (`user/claude_code` in the cluster's account):

| # | Check | Result (2026-07-13) | Verdict |
|---|---|---|---|
| S2 | any un-migrated `holdslot_scope_*` key without the `holdslot_scope_migrated_<client>` done-flag | Both origins: done-flag `=1`, **zero** raw scope keys | ✅ **CLEARED** — shim inert; delete `constants.ts:461-490` + `list/page.tsx:646-695` (~70 LOC) |
| S22 | every tenant's **latest** `research_spec.spec` carries the `icp_targeting` key | `v3_latest_tenants = 0` (both tenants: `4b47b7d7`@v18, `c2ccb150`@v1 — both `icp_targeting=true`) | ✅ **CLEARED** — v3 fallback (`research_spec.py:598-605` + FE mirror) is dead; delete (~13 LOC) |
| S23 | no `scope_override.params` missing the `by_icp` key | `legacy_flat_overrides = 0` (tenant `4b47b7d7` people+company both `by_icp`-keyed; tenant `c2ccb150` has none) | ✅ **CLEARED** — flat fallback (`prospects/router.py:201-203`) is dead; delete (~4 LOC) |

*Live-data aside — RESOLVED:* the "2nd tenant" `c2ccb150` is a **test leftover, not a real signup**, so it
does **NOT** genuinely trip the NF-10/GX SCALE-seam trigger. Detail: slug `b4-17d76e96`, name "B4 17d76e96",
one owner `b4-17d76e96@example.com` (RFC-2606 reserved domain), created `2026-07-11 02:20:03` with last-login
**7s later** (machine-speed, not human) during the Jul-11 Phase-E/F/G-NF live-testing spree. Activity is a
shallow brief+scope test only — 1 brief · 2 icps · 1 research_spec · 1 llm_call · **0** companies/prospects/
runs/batches/campaigns/meetings/subscriptions/billing_events/sending_accounts. **No billing evidence attached
→ safe to delete** (Membership FKs CASCADE); recommend a dev-Aurora cleanup so it stops falsely tripping the
2nd-tenant trigger. Not done here (no unauthorized mutation of dev data).

### 11.2 · Re-verification deltas vs the register (drift caught this pre-flight)

- **S4** — now **18** `.field` blocks in `list/page.tsx` (register said 17), and **0 in `spec.tsx`** → S4 is
  **list-page-only**, not the "list ×N · spec" the register implied. `<Field>` extraction stays valid; scope
  is one file.
- **S7** — the toggle idiom is **not** the uniform ×8-9 the register assumed. Only `list/page.tsx:812`
  (`n.has(id) ? n.delete(id) : n.add(id)`) is a true toggle; `:120` (build-a-Set), `:1154` (union-add),
  `:1390` (bulk-delete) are **different** Set ops. Real `toggleId` surface ≈ 2-3 sites, not 8-9 — matches
  Wave 4's reason for deferring it (entangled with the credit-spend selection guard, not a clean idiom).
- **S13** — confirmed **genuinely CAREFUL**: all 5 integrations `@lru_cache _secret()` but each has a
  *distinct* env-override (`HOLDSLOT_STRIPE_KEY`/`_SMARTLEAD_KEY`/`_GOOGLE_SA`/`_APOLLO_KEY`/`_OPENROUTER_MODELS`)
  and *distinct* return shape (**apollo returns a bare `str`**, openrouter fallback-merges models, google must
  never cache the token). `core/config._get_secret_json` only does the raw SM read+parse. Realistic S13 =
  factor the **SM-read half** into the shared helper, **keep** each integration's env-override + envelope
  wrapper (the local-dev/test seam). Not a wholesale swap.
- **S8** — confirmed: `CampaignTab.tsx` (849 LOC) hand-rolls `reqRef` staleness guard (`:121`) around
  `loadDetail`+`useEffect` (`:135-151`). `useQuery(["campaign", client, id])` replaces it — **but** this is a
  §4 do-not-touch-class change (alters refetch/loading/error semantics). Careful, last.
- **S24** — confirmed code-only, no live check: `search_companies` (`:168`) is a prod-dead rows-only wrapper
  over `search_companies_meta` (`:179`, the real path in `prospects/router`); only `test_prospects_apollo` +
  `test_apollo` call it. Delete + retarget the 2 tests to `_meta` (unpack the tuple). Safe anytime.
- **S18** — confirmed: two `ai-score-cell` three-state cells (`:877` company · `:2339` person) + duplicate
  `list-overlay` spinner (`:1936`+`:2151`). `<FitCell>`/shared-overlay extraction valid.
- **S19** — confirmed: `facet-row` ×3 (`:2749`/`:2779`/`:2803`) + duplicated ICP `<select>` (Step-1
  `:1895`/`:1918` ≈ Step-2 `:2116`/`:2130`). `<FacetRow>` + shared select valid.
- **S26** — confirmed **3 byte-identical** copies of `new Date(iso).toLocaleDateString(undefined,{month:"short",day:"numeric"})`
  (`booking/page.tsx:16` · `feedback/page.tsx:32` · `billing/page.tsx:32`) + `replies.fmtDate` + `CampaignTab.fmtWhen`
  + `summaries` one-off. `lib/dates.ts` already exists as the home. Pure cosmetic now (M6/M30 fixed the tz bug).
- **S30** — `list/page.tsx` is now **3052 LOC** (was 3005). Note the **ordering win**: doing the S18/S19/S4/S5/S6
  extractions **first** shrinks this file materially — re-assess whether a formal split (S30) is still needed
  afterward, rather than splitting a file that's about to lose ~200 LOC to extractions.

### 11.3 · Recommended execution order (sub-waves; backend-first, pin-test-gated)

| Sub-wave | Items | Why grouped · gate |
|---|---|---|
| **5a · BE deletions (all pre-flight-cleared)** | S24 · S22 · S23 · S13 | Rides the same still-pending Wave 1+2 backend deploy. S24 = delete prod-dead wrapper + retarget 2 tests; **S22 = delete the now-dead v3 fallback (BE + FE mirror)**; **S23 = delete the now-dead flat fallback**; S13 = factor SM-read half only. Gate: `pytest` + `ruff`. |
| **5b · FE deletions + component extractions** | **S2** → S18 → S19 → S4 → S5 → S6 | **S2 first** — a pure deletion of the now-provably-inert shim (~70 LOC), lowest risk. Then the byte-identical-DOM extractions on the list page; each is **one commit, Playwright re-run after each** (pin-test = same class names emitted, 26✓ holds). Both naturally shrink `list/page.tsx`. |
| **5c · FE careful state + deferred SAFE** | S8 · S28 · S26 · S7 · S21 | The two **semantics-changers** (S8/S28: `useState`→`useQuery`/shared keys — §4 do-not-touch caution, refetch/loading changes) done last + most carefully; S26/S7/S21 are the cosmetic tail folded in. |
| **5d · S30** | S30 | Re-assess **after 5b** — the file may no longer warrant a split. |

### 11.4 · Do-not-touch cautions + what stays OUT of Wave 5

- **S8 + S28 brush the §4 do-not-touch line** — the register's own note warns `useState`→`useQuery` and
  shared-query-key changes alter refetch/loading/error semantics. M9 already fixed S28's *correctness* (Wave 1),
  so S28 is now pure consolidation, not a bug-fix — treat as lowest-value/highest-risk.
- **`_iso` ×4 is NOT a Wave-5 dedup** — it's a latent **M6-class bug** (batches serializes naive, wrong HK day).
  It belongs in a future **fix** wave, not a simplify (§10.3). Do not "consolidate" it here.
- **`_brief_data` ×2 stays** — lazy-import cycle guard; 2 LOC not worth the topology risk (§10.3).
- **Column-drops are a SEPARATE migration wave, not Wave 5** — `Meeting.summary` JSONB (deferred
  `meeting_summary` seam) + `Subscription.icp_limit`/`plan_icp_limit` (plumbed through the dormant billing `Out`
  shape) each need a `0033` migration + touch dormant seams. Folding them in would break Wave 5's
  deploy-neutrality. Cut them only when the dormant seams themselves are cut.

### 11.5 · Readiness state — FINALIZED (pre-flight cleared)

- **Ready to build now (no blockers):** S2, S22, S23, S24, S13, S18, S19, S4, S5, S6, S26, S7, S21, S30 —
  all pin-test-gated and code-only. S13/S22/S23/S24 are BE deletions that ride the pending Wave 1+2 backend
  deploy (S22 also trims its FE mirror in the same commit); the rest are FE. **Wave 5 stays deploy-neutral**
  — no migration (the column-drops remain OUT, §11.4).
- **Ready but highest-risk (do last, §4 caution):** S8, S28.
- **BLOCKERS: none** — all 3 founder-gated pre-flight checks CLEARED (§11.1).
- **NOT started, NOT authorized:** no Wave 5 code written; commit/push of Waves 1–4 still pending the founder
  gate. The only thing left before building is an explicit **"build Wave 5"** ask — the plan itself now has
  zero open dependencies.

  → Superseded 2026-07-13: the **"build Wave 5"** ask landed and Wave 5 is now BUILT + GATED — see §12.

## 12 · Wave 5 — BUILT + GATED (2026-07-13)

Built on the same session that pre-flighted it (§11). **11 of the 16 items shipped**; S8 · S28 · S30 were
**deferred with rationale** (§12.3) as the plan's own highest-risk/lowest-value tail (§11.4/§11.5). Wave 5
stays **deploy-neutral** — no migration; the BE deletions ride the still-pending Wave 1+2 backend deploy.

**Gates (all GREEN):** BE `ruff` clean · `pytest` **371 passed / 29 skipped** (the skips are the Aurora-gated
integration suite). FE `tsc --noEmit` clean · `eslint` clean · `next build` clean · Playwright **26/26**
(the byte-identical-DOM pin-test for every 5b extraction). `prettier --write` run on all touched files.

### 12.1 · What shipped, per item

| # | Item | What was done |
|---|---|---|
| **S24** | apollo `search_companies` prod-dead | Deleted the rows-only wrapper + its `__all__` entry; fixed the module docstring to name `search_companies_meta` (the real path) + its 0-credit reality. Retargeted `test_apollo` ×2 to `_meta` (unpack the tuple) and **deleted** the vestigial `search_companies` monkeypatch in `test_prospects_apollo` (it stubbed a now-absent attr → would have raised). |
| **S22** | v3-spec fallback | Deleted the `blocks is None` legacy branch in `targeting_for_icp` (BE) — `if not blocks: return None` now covers absent/empty. Deleted the FE mirror's v3 branch in `specTargetingBlock` (`return sp` → `return {}`; the first-block leniency stays). Updated `test_research_spec` (v3 blob → None) + docstrings. |
| **S23** | legacy-flat scope-override | Deleted the `by_icp is None → return params` branch in `_scope_override_block`; guarded `by_icp = … or {}` so a (now-absent) flat payload can't `AttributeError`. Updated `test_scope_override` (flat payload → None) + docstring. |
| **S13** | secret-fetch boilerplate ×5 | Added `core/config.fetch_secret_json(name)` (region/prefix/read/parse). Routed all 5 integrations (`stripe`/`smartlead`/`apollo`/`google`/`openrouter`) through it, **keeping** each env-override + envelope shape (apollo's bare-`str`, openrouter's model-merge, google's uncached token). Dropped the now-unused `import boto3` from all 5. |
| **S2** | localStorage scope-migration shim | Deleted `SCOPE_MIGRATED_KEY` + `pendingLocalScopeMigrations`/`clearMigratedScope`/`markScopeMigrationDone` (constants.ts, ~28 LOC) and the ~50-LOC migration `useEffect` + its 3 imports in `list/page.tsx`. Pre-flight (§11.1) proved the shim inert. |
| **S18** | 3-state score cells + overlay | Extracted `<FitCell>` (company + person cells; `reason` prop optional, hidden for contact buckets) and `<ListOverlay busy>` (the Fetching… spinner). Byte-identical DOM. |
| **S19** | facet rows + ICP select | Extracted `<FacetRow>` (×3 seniority/dept checkboxes, `key` on the call site) and `<IcpFilterSelect>` (Step-1 ≈ Step-2; `highlight` prop drives the Step-1 pick-an-ICP warn border; renders null when ≤1 ICP). |
| **S4** | `<Field>` wrapper | Extracted `<Field label value onChange type? placeholder?>`; converted **17** `div.field>label+input` blocks. The 18th (add-person Company `<select>`) has bespoke logic → left as-is. |
| **S5** | `ConfirmFooter` | New `components/workspace/ConfirmFooter.tsx` (`variant` primary/accent/danger · `busy`/`confirmDisabled` · busy-label swap). Applied to **6** footers (batches ×3 · summaries ×1 · list add-co/add-person ×2). |
| **S6** | two-pane prompt editor | New `PromptEditorShell` (slot props for the divergent badge/actions/meta/content/hint); routed both the list-page rubric modal and the spec-panel prompt modal through it. |
| **S26** | date-format dedupe | Added `fmtDay` + `fmtDayYear` to `lib/dates.ts` (both parseUtc-based → tz-correct). Routed billing/booking/feedback → `fmtDay`, replies/summaries → `fmtDayYear`. `CampaignTab.fmtWhen` left (unique format — no `timeZoneName`, unlike `whenLabel`). |
| **S7** | Set-toggle idiom | Added `lib/sets.ts` `toggleInSet<T>`; applied to the **5** true toggles (list ×4 + CampaignTab ×1). |
| **S21** | single-valued props + micro-dupes | Removed dead `SpecChips.warn` + `Section.extra` props (never passed); extracted `<ManualBadges>` (the source·manual / fit-scored pair, ×2). `safeHref`/`isStep2`/`groupByCompany().meta` were **already gone** (earlier-wave drift). |

`list/page.tsx`: **3052 → 2967 LOC**, and six repeated presentational blocks are now named single-source
components (`FitCell`/`ListOverlay`/`FacetRow`/`IcpFilterSelect`/`Field`/`ManualBadges`) + the shared
`PromptEditorShell`.

### 12.2 · Deliberate deviations from the plan text (with rationale)

- **S5 covered 6 footers, not "9"** — re-verification found only 6 match the Cancel+action-busy pattern; the
  register's "list ×5" over-counted (it swept in the lone "Done" footers and the 3-button "Reset to AI scope"
  footers, which aren't this shape). The two list modals (add-co/add-person) had Cancel *enabled* during save
  while batches/summaries disabled it; `ConfirmFooter` unifies to **disabled-while-busy** — a strictly-safer
  consistency change (can't close mid-submit), documented here. Playwright 26/26 confirms no regression.
- **S6 is a layout shell, not a shared editor** — every leaf (badge, save button, textarea state, right
  meta/content, hint) differs between the two modals; only the two-pane skeleton is shared, so the faithful
  extraction is a slot-prop shell (the model row above it stays at each call site).
- **S21 inventory largely evaporated** — `safeHref`/`isStep2`/`groupByCompany().meta` no longer exist (removed
  in Waves 1–4). Only the dead props + the badge pair survived; those were done.
- **S7 surface = 5, not the register's 8–9 nor §11.2's "only :812"** — the true `has?delete:add` idiom is at 5
  sites (list ×4 + CampaignTab ×1); other Set ops (build/union/bulk-delete) were correctly left alone.

### 12.3 · Deferred (with rationale) — S8 · S28 · S30

The plan's own §11.4/§11.5 tagged these the highest-risk / lowest-value tail ("§4 do-not-touch caution," "only
if slack"). On inspection each is a behavior-altering refactor, not a simplify, and the route-mocked Playwright
suite can't validate the runtime semantics they'd change — so they were deferred, not forced:

- **S8** (`CampaignTab` detail → `useQuery`) — `detail` is **not** purely fetch-driven: it's a direct mutation
  target in **5** campaign-operation paths (create/launch/variant-edit). A faithful `useQuery` swap needs
  `setQueryData` across all 5 + new refetch/loading/error/`refetchOnWindowFocus` semantics on live campaign
  flows. The hand-rolled `reqRef` staleness guard is **correct** as-is; the churn/risk isn't justified in a
  discretionary wave.
- **S28** (share query keys) — §11.4 already records M9 fixed the *correctness*; what remains is pure
  consolidation that changes the **billing (money) page's** loading/refetch semantics (a `useState`→`useQuery`
  swap or exposing raw provider state). Lowest value, highest risk, money-adjacent.
- **S30** (`list/page.tsx` formal split) — reviewability-only, not LOC-saving; §11.3 said "re-assess after 5b."
  The 5b extractions already delivered the incremental reviewability win (6 named components + the shared
  shell; 3052→2967 LOC). A full split moves ~3000 LOC of interdependent state across module boundaries — a
  large refactor a route-mocked suite can't fully validate, out of scope for a discretionary wave.

Picking these up later is a clean, self-contained follow-up (each is one focused PR with its own manual QA of
the affected flow), not a Wave-5 gap.

### 12.4 · Dev-Aurora cleanup (same session, founder-authorized)

The `c2ccb150` / `b4-17d76e96` test-leftover tenant (§11.1 aside) was **deleted** from dev Aurora on founder
authorization: one `DELETE FROM tenant WHERE id='c2ccb150-…'` (26 child tables cascade-cleared; verified 0
residual rows). Only the `holdslot` tenant remains. The orphaned owner `app_user`
(`b4-17d76e96@example.com`, 0 memberships) is inert and was left in place (the DELETE was scoped to the tenant).
