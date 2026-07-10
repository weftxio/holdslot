# Final fix plan — pre-production review (Phase A → D+)

> **Purpose:** the single execution spec for the LAST fix wave before the production commit/push and
> Phase E. Produced by the final review of 2026-07-11 (six parallel full-file reviewers over backend ·
> frontend · infra/migrations/scripts · docs, plus a read-only live dev-Aurora check and an executed
> e2e run). It **consolidates and supersedes `docs/dplus-fix-plan.md`** (now deleted): §0 carries that
> wave's results and carve-outs; §G1–§G7 are the new work. Decisions are pre-made — work top-to-bottom,
> don't re-litigate.
> **Baseline:** working tree = commit `2838d85` + the uncommitted D+.5 fix wave (29 modified + 3 new
> files). Line numbers are as of this working tree — if a file drifts, re-locate by symbol name.

## How to work this plan

1. **One phase at a time, in order** (G1 → G7). After each phase: `cd apps/api && .venv/bin/python -m
   pytest -q` and `ruff check app/ tests/ scripts/`; for FE phases `pnpm build` + `npx tsc --noEmit` +
   `npx eslint app lib components e2e`. Each phase lands independently green.
2. **Smallest diff that fixes the item.** Match surrounding style; `line-length = 100` (ruff E501).
3. Each fix lands **with its test** where one is listed. Lesson from the D+.5 wave (N1): a money-path
   branch must have a **non-Aurora unit test** even when an Aurora-gated integration test exists —
   the gated test skipped locally and let a crash through.
4. Tick the `☐` boxes here as items complete (this doc is the progress tracker).
5. **Commit cadence (decided — §F Q1/Q2):** a checkpoint commit of the D+.5 wave + review docs was
   made 2026-07-11; make **one local commit per G-phase** (prefix `fix(final): G<n> …`). **Pushes**
   (need the `weftxio` gh account, founder go): push #1 after G4 (enables the deploy+smoke), push #2
   after G6 — see the §F Q1×Q2 reconciliation. Never push mid-phase (a push auto-deploys the FE).
6. **Hard constraints (unchanged):** OpenRouter → non-US providers only (HK 403) · zero new AWS
   resources until prod cutover (§G7 notes the two exceptions to schedule AT cutover) · Apollo
   searches free, `people/match` = only spend (1 cr/email), never before Gate 2 · no `innerHTML`/
   `dangerouslySetInnerHTML` for user values · design class names stay intact · `AWS_PROFILE=holdslot`
   (acct 138743894336) · test against deployed dev-cloud Lambda, never local uvicorn.
7. Items marked **(Q#)** reference a §F founder decision — **all eight are answered (2026-07-11)**;
   follow the recorded decision, not the archived defaults.

## Context pack (fresh session — read this before G1)

- **Commands.** Backend: `cd apps/api && .venv/bin/python -m pytest -q` (bare `python` is NOT on
  PATH) · `.venv/bin/ruff check app/ tests/ scripts/` (ruff: `line-length = 100`, select E,F,I,UP,B —
  E501 is the most common failure on new comments). Frontend (from `apps/web`): `pnpm build` ·
  `npx tsc --noEmit` · `npx eslint app lib components e2e`. **e2e:** `cd apps/web && pnpm exec
  playwright test` — self-contained: the config auto-starts `next dev` on :3100 with
  `NEXT_PUBLIC_API_BASE_URL` pointed at a DEAD port (127.0.0.1:9876) and every request is
  `page.route()`-mocked in `e2e/_mock.ts`; it can never reach the real (paid) API.
- **Layout.** Migrations live in `infra/alembic/versions/` (NOT under `apps/api`); ORM =
  `apps/api/app/models.py`; the model↔migration parity test = `apps/api/tests/test_migrations.py`.
  Async job workers are Lambda self-invocations routed in `app/main.py`; job ledger =
  `scoring_job` (prospects) / `research_job` (briefs). The 18 skipped tests are Aurora-gated
  (skip without `HOLDSLOT_DB_CLUSTER_ARN`) — they run only against dev cloud.
- **State at hand-off (2026-07-11).** Working tree = `2838d85` + the uncommitted D+.5 wave + this
  review's docs; **nothing committed**. Dev Aurora head = `0026`; migration `0027` is defined,
  **unapplied and uncommitted → still editable in place** (N8/N48/N49 rely on this). Verified: backend
  228 passed / 18 skipped · ruff clean · FE build+tsc+eslint clean · **e2e has exactly one failing
  test (N17)** — after G3, e2e green becomes part of the DoD.
- **Deploy chain.** `apps/api/scripts/build-and-deploy.sh` = alembic upgrade → Lambda publish →
  SnapStart wait → shift `live` alias; frontend deploys via Amplify autoBuild **on push to `dev`**
  (so a local commit is inert; a PUSH deploys the FE). Backend before frontend, always.

---

## §F · Founder decisions — ✅ ANSWERED (founder, 2026-07-11)

All eight answered. **These decisions are binding — the "Recommendation/Default" columns in the
archived options table below no longer apply.**

| # | Decision |
|---|---|
| **Q1** | ✅ **Checkpoint commit NOW** (made 2026-07-11, this session) · one local commit per G-phase · pushes per the Q1×Q2 reconciliation below. |
| **Q2** | ✅ **G1–G4 (all P1+P2) → push #1 + deploy + dev smoke → G5–G6 follow-up wave → push #2.** |
| **Q1×Q2 reconciliation** | The founder chose "single push after G6" (Q1) AND "deploy+smoke after G4" (Q2). The G4 smoke needs the FE deployed, and Amplify only deploys on push — so the recorded cadence is **two pushes: #1 after G4 (enables the deploy+smoke), #2 after G6**. Within each push, backend deploys FIRST (`build-and-deploy.sh` applies `0027` + shifts the Lambda), then the push rides Amplify. If the founder prefers literally one push, say so — the G4 smoke then covers backend only and the FE smoke waits for the post-G6 push. |
| **Q3** | ✅ Deterministic redaction in `_masked` now + a "never name the person/company" line at the NEXT rubric version (N10). |
| **Q4** | ✅ Skip the paid call — free-gate `low_fit "parent company low fit"` in pass 1; override→rescore recovers the text (N27). |
| **Q5** | ✅ **Wire "create client" to `POST /clients` — the complete real-onboarding flow in the database, NOT local create** (N45 rescoped accordingly; still also seed the switcher from `me.clients`). |
| **Q6** | ✅ N3 deletion-protection: land in G1, `terraform apply` with the next deploy · N20 DLQ+alarm / N52 IAM narrowing / N54 throttling: at prod cutover. |
| **Q7** | ✅ Modified: after G7's first deploy, **produce the re-score candidate list** (companies wrongly geo-excluded pre-N4 + N6 mis-tag suspects) and hand it to the founder — **the founder re-scores in the UI** ("Update AI Score"). No automated wave. |
| **Q8** | ✅ e2e = mandatory manual step in the G7 checklist now; wire into the deploy script at prod cutover. |

### Archived options table (context only — superseded by the decisions above)

| # | Decision | Options & trade-off | Recommendation | Default if unanswered |
|---|---|---|---|---|
| **Q1** | **Commit cadence.** 2,100+ changed lines are uncommitted (D+.5 wave + docs). | (a) hold everything for ONE atomic commit after G6 · (b) local checkpoint commit NOW, then one local commit per G-phase, single push after G6. Note: commit ≠ push — only a **push** triggers Amplify; local commits are inert and protect against a lost working tree. Splitting `0027` from its coalesce code across pushes is the hazard either way. | **(b)** — checkpoint now; push once, after G6, on your go. | (a) — strictly "commit only when asked". |
| **Q2** | **Scope before first deploy.** | (a) full G1–G6 before commit/deploy · (b) G1–G4 (all P1+P2) → commit/deploy/dev-smoke, then G5–G6 (P3s + cleanup) as a follow-up wave on a green baseline. | **(b)** — gets the P1-fixed build under your smoke sooner; no P3 blocks production. | (a) — work the doc in order. |
| **Q3** | **N10 masking strictness.** `fit_reason` free text on the masked approval page can name the person/company. | (a) deterministic code-side redaction in `_masked` now + a "never name them" line at the NEXT rubric version · (b) prompt-only (weaker; takes effect only on re-score) · (c) accept until tenant #2 (today the only client is HoldSlot itself — the "leak" is to yourself). | **(a)** — cheap, deterministic, testable. | (a). |
| **Q4** | **N27 paid people-score under `low_fit` parents.** The label is predetermined by the company cap; the paid call only buys reason/subscore text. | (a) free-gate in pass 1 (label `low_fit "parent company low fit"`, $0) — loses person-level reasons unless the company is later overridden + re-scored · (b) keep paying for the text. | **(a)** — matches the cost posture; override→rescore recovers the text when actually wanted. | (a). |
| **Q5** | **N45 client switcher.** Local-only "create client" navigates to a tenant that doesn't exist server-side. | (a) seed the switcher from `me.clients`, hide local create · (b) wire create to the existing `POST /clients` API (real onboarding — bigger, belongs to a later phase) · (c) leave as-is. | **(a)** — smallest honest fix. | (a). |
| **Q6** | **Infra apply timing** (all `terraform apply` = founder-run). | N3 deletion-protection: land the .tf change in G1 — apply NOW or with the next deploy? · N20 DLQ+alarm and N54 API-GW throttling: at prod cutover (zero-new-resources posture) or on dev now? · N52 IAM secret narrowing: cutover or now? | **N3 apply with the next deploy** (same `terraform apply`); **N20/N52/N54 at cutover** (already in the G7 register). | Code lands per plan; every apply waits for you. |
| **Q7** | **Post-deploy paid re-score wave.** N4 (geo gate) + N6 (ICP enum) mean some EXISTING labels are wrong — geo-over-excluded rows sit in `excluded_by_rules "rule: outside target geography"`. | Re-scoring them is the correction path: the free gates re-run at $0, and rows that now PASS proceed to the paid web-grounded call (~≤15/batch waves via "Update AI Score"). Scope: all rows, or only the geo-excluded ones? | **Yes, scoped** — re-score the geo-reason `excluded_by_rules` rows once N4 is deployed; leave the rest to the existing on-demand posture. | On-demand only (existing posture). |
| **Q8** | **e2e as a deploy gate.** N17 proved e2e was silently red while builds were green. | (a) documented manual step in the G7 checklist (it's already listed) · (b) also wire `pnpm exec playwright test` into `build-and-deploy.sh`/Amplify so a red e2e blocks deploys mechanically. | **(a) now, (b) at cutover** with the rest of the CI hardening. | (a). |

---

## §0 · D+.5 fix-wave result (carried from `dplus-fix-plan.md`, executed 2026-07-10)

All 31 code-review findings (R1–R31) were executed across phases F1–F7 on top of `2838d85`:

- **F1** migration `0027_dplus_indexes_race` — score-sorted feed indexes (R5), `scoring_job` partial
  unique + `enqueue_scoring` IntegrityError coalesce (R9), `research_run` scan index (R22a), dropped
  prefix-covered indexes + purged `sourcing` prompt rows (R29a/b). **Not yet applied to Aurora** (dev
  is at `0026`; verified live 2026-07-11 — 0 active `scoring_job` rows, 1 `sourcing` prompt row, tiny
  tables → the non-CONCURRENT index builds are safe).
- **F2** backend P1s — constant-width `_paginate` + cursor `per_page` guard (R1) · post-enrich DNC
  gate (R2) · `MAX_JOB_AGE_SECONDS=480` + atomic claim + guarded `_finalize` in both workers (R3) ·
  stable `_body_hash` (R4) · zero-prospect fit-prompt guard (R7).
- **F3** backend P2s — pre-enrich excluded-parent skip (R8, **but see N1**) · per-row enrich commits
  + sync `/prospects/enrich` deleted (R10) · `headcount_uncertain` removed via delete-fallback (R11) ·
  dynamic ICP enum (R19, **but see N6**) · cursor scan scoped to find sources (R22b, **but see N25**) ·
  truthful `rubric_version`/`scope_source` (R28).
- **F4** frontend list flow — e2e mock shape + seeded-render test (R17, **but see N17**) ·
  `pruneExcluded` + tick-to-remove (R6+R13, **but see N2/N11/N12**) · poll lifecycle (R12) · spend
  estimate by `!email` (R14) · GET-before-PUT override migration (R15) · shared UTC `lib/dates.ts`
  (R16, **but see N18**) · `trigger_line` rendered (R26) · reload-in-`finally` (R29c).
- **F5** Data-API round-trip wins (R20a–d) · **F6** dead-code/dup sweep (R23–R25, R27, R29d) ·
  **F7** docs true-up (R18, R29e, R31) + close-out.

**Verification at hand-off:** backend 228 passed / 18 skipped, ruff clean, single alembic head
`0027`; frontend `pnpm build` + `tsc` + `eslint` clean (e2e was NOT run then — see N17).

**Standing carve-outs (carry forward, still accepted):**
- **R21 deferred** — post-wave full-list reload instead of merging `job.result` rows; revisit only
  when a tenant list exceeds one `FEED_PAGE=250` page.
- **R27 residual** — `_latest_spec` ×2 and `_feedback_rows`↔`_scored_company_rows` cross-module query
  dups left in place (no clean shared home without polluting pure `feedback.py` or risking a
  `briefs↔prospects` import cycle).
- **R30 accepted gaps** — research-runs endpoint test · per-ICP people-precedence HTTP test.
  **Amended by this review:** gaps stay accepted, but rule 3 above (non-Aurora unit tests on
  money-path branches) is now mandatory — N1 is exactly the failure R30's acceptance permitted.

---

## §1 · New findings — this review (2026-07-11)

56 findings (N1–N56): **3 P1 · 19 P2 · 34 P3**, plus dead-code (§5) and perf (§6) inventories.
Six of them are regressions/incomplete spots **introduced by or missed in the D+.5 wave itself**:
N1 (R8), N5 (R1 guard ordering), N6 (R19 letter derivation), N17 (R17 test), N18 (R16 missed line),
N29 (R9's IntegrityError catch needs live verification). The rest are Phase A–D+ latents surfaced by
the full-repo sweep.

---

## G1 · P1 blockers — fix before any deploy

| ✔ | # | Where | Problem | Fix |
|---|---|---|---|---|
| ☐ | **N1** | `prospects/router.py:1990-2003` (`run_enrich_score_prospects`) | The R8 skip-set does `{c.id for c in db.execute(select(Company.id)…).scalars()}` — `.scalars()` yields raw UUIDs, so `c.id` raises `AttributeError`. Any Reveal & score batch containing ≥1 person under an `excluded_by_rules` company (the exact case R8 exists for) crashes the whole job to `error`; nothing reveals or scores. The covering test is Aurora-gated → never ran locally. | `excluded_parents = set(db.execute(…).scalars())`. **Add a non-Aurora unit test** (fake session, one excluded parent) that executes this branch — reuse the fake-session pattern from `tests/test_scoring.py`'s R9 race tests: stub `db.execute().scalars()` to yield UUIDs, assert the excluded person is skipped and the rest reach `_enrich_prospects`. |
| ☐ | **N2** | `list/page.tsx:1294` (`stageForPeople`) | `const ids = coSel.map((c) => c.id)` — no label filter, unlike `runFindPeople` (`:1399`). A checked row re-scored to `excluded_by_rules` (tick survives a stage-tab switch) gets staged + people-found → LOCKED invariant violated. The comment at `:108-109` claiming all funnel-advancing actions drop excluded rows is false for this path (also feeds `runRescore`/`runLookalike`/`runUpdateFields` via `coSel`). | Filter `c.label !== "excluded_by_rules"` from `ids` in `stageForPeople` (mirror `runFindPeople:1399`). The other `coSel` consumers (`runRescore` · `runLookalikeJob` · `runUpdateFields`) stay UNFILTERED — deliberate: they're free server-side (rescore re-runs the free gates first; update-fields spends nothing) and re-scoring an excluded row is the documented un-exclude path (§D+.2 decision ④). Only `stageForPeople` advances the funnel. Also fix the now-false comment at `:108-109` to name the one filtered path. |
| ☐ | **N3** | `infra/terraform/aurora.tf:54` | `skip_final_snapshot = true` and no `deletion_protection` on the ONE cluster that is also the production database (no separate prod backend). A `terraform destroy`/replacement plan deletes all client + billing data irrecoverably. | Add `deletion_protection = true`; replace `skip_final_snapshot` with `final_snapshot_identifier`. **`terraform apply` is founder-gated — Q6 ✅: rides the push-#1 deploy.** |

**Verify:** pytest + pnpm build; the new N1 unit test fails-before/passes-after.

---

## G2 · Backend P2 — correctness on the money/label path

| ✔ | # | Where | Problem | Fix |
|---|---|---|---|---|
| ☐ | **N4** | `labeling.py:239-243` + `_geographies_from_spec` (`:423-445`) | The free geo gate compares full `organization_locations` strings against country names: a city-level scope entry (`"Sydney"`, `"Kowloon, Hong Kong"` — expected input; R29d exists for them) means NO row's `hq_country`/`field_country` ever matches → every enriched row lands `excluded_by_rules "outside target geography"` before any paid score. | Fix in `_geographies_from_spec` only (`rules_gate` untouched): for each entry, add the normalized FULL string AND each comma-split segment to the allowed set (mirror `_is_apac`'s tokenization in `router.py:1408-1466`) — so `"Kowloon, Hong Kong"` admits `hong kong` and `"Sydney, Australia"` admits `australia`, while bare country entries keep working. Unit tests: `["Sydney, Australia"]` admits hq `Australia`; `["Singapore"]` admits `Singapore`; a truly-foreign row still excludes; a city-only entry with no country segment (`["Sydney"]`) must not exclude a null-country row (fail-open rule stays). |
| ☐ | **N5** | `router.py:1537-1538` (exhausted short-circuit) + `:1310-1329` (`_cursor_decision`) | The short-circuit records `search_meta={"scope_exhausted": True}` with no `per_page`, and `_cursor_decision` checks `per_page != PER_PAGE_MAX` BEFORE `scope_exhausted` → one short-circuited run permanently discards the exhaustion flag; subsequent finds restart at page 1 and re-walk the bought scope (0 new rows each) while reporting not-exhausted. The `:1321` "legacy cursor, only once" comment is wrong. | Two halves, do both: (a) short-circuit meta becomes `{"scope_exhausted": True, "per_page": apollo.PER_PAGE_MAX, "page_cursor": <prior page_cursor>, "total_pages": <prior>}` so the exhausted run re-records a valid cursor; (b) in `_cursor_decision`, check `scope_exhausted` BEFORE the `per_page` guard (an exhausted verdict is page-size-independent). Unit tests: exhausted-run meta → next decision `(1, True)`; legacy no-`per_page` non-exhausted meta still resets to `(1, False)`. |
| ☐ | **N6** | `fit.py:357` (`company_score_v2`) vs `router.py:646-651,674-678` | The R19 enum is positional (`A, B, …` from ICP count) but the prompt tells the model to return "the letter in its `name`" and the re-tag map keys on `_icp_letter(d["name"])` — renamed/non-conventional ICP names (or B+C after deleting A) put the model's letter outside the enum → strict decode forces a wrong letter → paid verdict re-tagged to the wrong ICP. Two names ending in the same letter silently collide (last wins). | One derivation, one home, used by BOTH sides so enum and map can never diverge: add `icp_letter_map(icps) -> dict[letter, icp_id]` in `fit.py` (beside the schema builder) — letter = `_icp_letter(name)`-style derivation, falling back to positional letters for ALL entries whenever any name is letterless or two names collide (consistent fallback, never mixed). `company_score_v2` builds the schema enum from its keys; `router.py`'s re-tag map (`:674-678`) imports the same function instead of rebuilding by name. Extend the 3-ICP unit test with renamed ICPs + a same-letter collision. |
| ☐ | **N7** | `router.py:2706-2707` (sync `find_people`) | `for p in prospects: db.refresh(p)` — up to 250 sequential Data-API round trips (~1 HTTP call each) on the 30s-gateway sync path, on top of ≤8×4-rung Apollo searches; pushes normal requests toward the gateway kill. `expire_on_commit=False`, so only NEW rows' server-defaulted `created_at` is missing. | Drop the loop; re-select the affected batch in one `IN()` query (or tolerate `created_at=None` in the response shape). |
| ☐ | **N8** | `briefs/structuring.py:128-144` (`enqueue_structuring`) + migration | Non-atomic check-then-insert with no DB backstop — the exact race R9 fixed for `scoring_job`, unfixed for `research_job`: double-click on Generate Scope → two workers, two billed DeepSeek Pro + web-search calls (~55–76s each), two spec versions; the poll tracks only one. | Mirror 0027 in the same (unapplied) migration: `research_job` has NO `kind` column (single job type), so the partial unique is `uq_research_job_active_tenant` on `(tenant_id) WHERE status IN ('queued','running')` — add to 0027 upgrade+downgrade, to `ResearchJob.__table_args__` in `models.py`, and to the parity test. In `enqueue_structuring`, mirror `scoring.enqueue_scoring`'s shape: catch the violation → re-run the existing in-flight lookup → return that job (same response shape as the current "already running" path). Note N29 applies here too — catch `DBAPIError` + match `23505`/"duplicate key", not bare `IntegrityError`. Reuse the R9 race-test pattern from `test_scoring.py`. **Fold into `0027`** (uncommitted + unapplied — no new migration; N48 + N49 land in the same edit). |
| ☐ | **N9** | `auth/service.py:53-54` (`rotate_refresh`) | Checks `user is None` but never `user.status` — a disabled user rotates refresh tokens (30-day chains) indefinitely; "disable the user" never terminates the session chain. | `if user is None or user.status != UserStatus.active: return None`. Unit test with a disabled user. |
| ☐ | **N10** | `approvals/router.py:67` (`_masked`) + `fit.py:333-336` prompt | The masked external view exposes `fit_reason` LLM free text whose prompt input contains the full name + exact company and never forbids echoing them — one "As VP Sales at Acme Robotics, Jane …" sentence defeats the masking (client gets unpaid-for clear-text identity). | **(Q3 ✅ decided.)** Code-side (deterministic): in `_masked`, redact case-insensitive occurrences of `enrichment.full_name` parts / company name / domain from `fit_reason` (replace with the masked descriptors). Also add a "never name the person or their company" line to both score rubrics at the next prompt version (founder-editable; don't retro-edit seeded prompt files — N51). Unit test on `_masked`. |

**Verify:** pytest + ruff. N8 changes migration 0027 → re-run the model↔migration parity test.

---

## G3 · Frontend P2 — selection/state integrity + the failing e2e

| ✔ | # | Where | Problem | Fix |
|---|---|---|---|---|
| ☐ | **N11** | `list/page.tsx:351` (`reloadProspects`) | `setChecked(new Set())` on EVERY reload wipes the whole people selection — contradicts the R6 whole-selection design (ticks placed while a background job finishes are silently cleared) and makes the prospects prune effect (`:477-482`) unreachable. | Remove the wipe; let the R6 prune effect drop only `excluded_by_rules` ids (mirroring `reloadCompanies`, which keeps `companyChecked`). |
| ☐ | **N12** | `list/page.tsx:1325-1343` (`removeFromStep2`) | Un-staging cleans `companyChecked` but not `checked` — the removed company's people stay selected but render nowhere: dock reads "8 selected", "Reveal & score 8" spends on 5 invisible rows with no way to untick except Clear. | In `removeFromStep2`, also drop `checked` ids whose prospect's `company_id` is in the removed set. |
| ☐ | **N13** | `list/page.tsx:1027,1089,1218` + reset effect `:391-405` | `findingCo`/`updatingFields`/`findingLookalike` reset inside a client-guarded `finally` but are NOT in the client-switch reset effect — an in-place `[client]` param change (browser back/forward) mid-run strands them true → permanent "Fetching…" overlay + disabled toolbar. | Add the four busy-flag resets (`setFindingCo(false)` etc. + `setStaging(false)`) to the client-switch reset effect. |
| ☐ | **N14** | `components/workspace/WorkspaceProvider.tsx:38-47` (`reloadBatches`) | No stale-client guard — a slow `listBatches(A)` resolving after the switch to B overwrites B's batches with A's (cross-client display leak). | Capture `client` at call time; bail before `setBatches` when it no longer matches (the list page's `clientRef` pattern). |
| ☐ | **N15** | `brief/page.tsx:386` (`persist`) | A created ICP's server id is recorded by object reference (`x === icp`); any edit while the create is in flight replaces the object → id orphaned → next save creates a duplicate ICP server-side. | Match by index/stable local key instead of reference. |
| ☐ | **N16** | `brief/page.tsx:247` | `void persist(next)` after CSV import — a failed PUT is an unhandled rejection; operator sees "Imported 40", navigates away, the do-not-contact list was never saved (compliance-adjacent). | `.catch((e) => toast(…, "warn"))`. |
| ☐ | **N17** | `e2e/routes.spec.ts:210-230` + `e2e/_mock.ts` seed | The R17 seeded-render test **fails as written** (confirmed by running it): Step-1 buckets default collapsed (`expandedBuckets` empty; rows render only when open, `page.tsx:1954`) so the row is never in the DOM; and the seed's `enrichment: {}` would crash `CompanyStudy` (`e.industries.length`, `spec.tsx:151`) if expanded. | In the test, click the "Contact now" bucket head row to expand it before asserting the row is visible; seed a FULL `CompanyEnrichment` object (copy the shape from `lib/api.ts` — every array field present, not `{}`), since `CompanyStudy` derefs `e.industries.length` unguarded. Re-run `pnpm exec playwright test` to green — from here e2e green is part of every phase's verify. |
| ☐ | **N18** | `components/workspace/FindHistoryDrawer.tsx:206` | `new Date(t.latestAt).getTime()` — one naive-UTC parse missed by R16; in HK every thread reads 8h old and the 7-day "finds this week" window mis-counts. | `parseUtc(t.latestAt)?.getTime() ?? NaN`. |
| ☐ | **N19** | `app/home.css:175` (`.sub`) | Unscoped generic class collides with the console's `.tbl .sub`/`.dock-count .sub` — global CSS persists across client-side nav, so after visiting `/` every console `<div className="sub">` gains `margin-bottom:32px; max-width:500px` (visibly broken tables). | Scope as `.home .sub` (only consumer is `app/page.tsx:163`, already under the `.home` wrapper). |

**Verify:** `pnpm build` + `tsc` + `eslint` + **run e2e** (`pnpm exec playwright test`) — e2e green is now
part of this phase's DoD (it was silently red).

---

## G4 · Ops/infra P2 — deploy-chain safety

| ✔ | # | Where | Problem | Fix |
|---|---|---|---|---|
| ☐ | **N20** | `infra/terraform/lambda.tf:79-83` | Async self-invoke path: `maximum_retry_attempts=0`, no failure destination, zero CloudWatch alarms — a throttle/bad-deploy drops every scoring/structuring dispatch silently; jobs sit `queued` until the 480s reaper mislabels them "worker timed out". | **(Q6 ✅: prod cutover**, zero-new-resources rule): add an `on_failure` destination + one alarm on Lambda `Errors`/`AsyncEventsDropped`. Record here so cutover picks it up; no change now. |
| ☐ | **N21** | `apps/api/scripts/c_smoke_live.py:18` | `PW = "tryholdslot1!"` — a repo-committed password that creates a real owner user on the live shared backend; a hard kill before teardown leaves an account with a publicly-known password. | `PW = secrets.token_urlsafe(16)` per run. |
| ☐ | **N22** | `apps/api/scripts/build-and-deploy.sh:16-18` | Runtime deps hardcoded, duplicating `pyproject.toml` — a dep added only to pyproject imports fine locally, then ImportError at cold start AFTER the alias shift (smoke runs post-shift, no rollback). | `uv pip install --target build/pkg .` (install the project) instead of the literal list; also `exit 1` when SnapStart never reaches `Active` (N55, same file — do both here). |

---

## G5 · P3 sweep — backend, frontend, infra (grouped; do per-row, each is small)

**Backend (prospects + other domains):**

| ✔ | # | Where | Problem → fix |
|---|---|---|---|
| ☐ | **N23** | `router.py:624-643` | Re-gated rows keep stale paid-score residue (`subscores`/`trigger_line`/`liveness`) in `fit_components` → an `excluded_by_rules` row renders last quarter's axes. Pop the paid block when the verdict carries no `signals`. |
| ☐ | **N24** | `router.py:1193,1728` | `uuid.UUID(params["icp_id"])` unwrapped in workers → malformed id = generic "internal error". Validate `icp_id` at the async enqueue endpoints. |
| ☐ | **N25** | `router.py:1302-1307` + `:2689` | People-find runs also record `source="apollo"` → they still consume the 50-run `_resume_page` window R22b was meant to protect. Give people-find its own source tag (e.g. `apollo_people`; keep `_CURSOR_FIND_SOURCES` as-is) — check FE FindHistoryDrawer grouping tolerates the new tag. |
| ☐ | **N26** | `router.py:2296` | `cost_per_accepted` is permanently null (`rows_accepted` never written anywhere). Drop the field from `ResearchRunOut` (and doc). |
| ☐ | **N27** | `router.py:862-876` + `labeling.py:379-385` | Paid `prospect_score_v2` still runs for people under a `low_fit` company though `_cap_by_company` predetermines the label — the call only buys reason text. **(Q4 ✅ decided: free-gate in pass 1** like the excluded case, label `low_fit` "parent company low fit", no paid call; override→rescore recovers the text when the company is rescued.) |
| ☐ | **N28** | `openrouter/client.py:295-310` | Parse-error retry discards the first billed attempt's cost/tokens → `llm_call.cost_usd` under-counts. Accumulate usage across attempts into the final `CallOutcome`. |
| ☐ | **N29** | `scoring.py:137` · `structuring.py:233` | The `aurora_data_api` driver maps errors to `IntegrityError` only when the AWS message matches its `Position/SQLState` regex — a live duplicate-key may surface as generic `DatabaseError`, skipping the R9/N8 coalesce (unique index still blocks the double job; the surface is a 500). Broaden to `except DBAPIError` + match `23505`/"duplicate key" in `str(e)`; **verify live during the deploy smoke** (double-POST an enqueue). |
| ☐ | **N30** | `structuring.py:139-143` | Job committed `queued` before `_dispatch`; a failed `lambda.invoke` 500s the route but strands the queued row → surface wedged ~8 min (every regenerate coalesces onto it). Wrap `_dispatch` in try/except → `_fail(db, job, "could not start worker")`. Check `scoring.enqueue_scoring` for the same pattern and fix both. |
| ☐ | **N31** | `batches/router.py:383-389` | `send_email`'s return ignored — SES failure still flips the batch to `sent`; the revenue-gating approval silently stalls. Surface `email_sent: bool` in the response (operator can re-send/copy the link). |
| ☐ | **N32** | `core/deps.py:88-95` + `models.py:43-45` | `TenantStatus.suspended` enforced nowhere. Add `Tenant.status == TenantStatus.active` to the membership query (non-members already 404). |
| ☐ | **N33** | `auth/service.py:46-57` | Refresh rotation is read-then-write — two concurrent uses of a stolen token both mint chains; single-use unenforced. Guarded `UPDATE … SET revoked_at=now() WHERE token_hash=… AND revoked_at IS NULL` + rowcount check (pattern already in `approvals/router.py:127-133`). |
| ☐ | **N34** | `auth/router.py:57-63` | User-absent login skips the argon2 verify → timing oracle for account existence. Verify against a static dummy hash when `user is None`. |
| ☐ | **N35** | `briefs/router.py:160-166` | `save_system_prompt` next-version is read-then-insert → concurrent saves hit `uq_prompt_tenant_stage_version` as a raw 500. Retry-on-conflict like `_insert_spec`. |
| ☐ | **N36** | `auth/service.py:27-34` | `refresh_token`/`password_reset` rows grow unbounded. Opportunistic `DELETE … WHERE expires_at < now()` on login. |
| ☐ | **N37** | `main.py:119-128` | CORS `allow_credentials=True` with env-driven origins — `"*"` would echo any Origin with credentials. Auth is pure bearer: drop `allow_credentials` (or hard-fail on `"*"`). |

**Frontend:**

| ✔ | # | Where | Problem → fix |
|---|---|---|---|
| ☐ | **N38** | `lib/workspace/constants.ts:86-91,190-193` | `batchFromApi` slices naive-UTC to `YYYY-MM-DD`; `daysAgoLabel` compares vs local now → HK day-level drift ("1 day ago" on creation day). Derive via `parseUtc` + viewer-local calendar date. |
| ☐ | **N39** | `list/page.tsx:490-502` | People-scope hydration error path keeps the PREVIOUS ICP's override in state (company counterpart resets to null at `:672-674`). Also `setPeopleScopeOverride(null)` in the catch. |
| ☐ | **N40** | `brief/page.tsx:352` | On-load `pollStructuring(...).finally(...)` lacks `.catch` → mid-poll network error = unhandled rejection, no message. Append a warn-toast catch. |
| ☐ | **N41** | `brief/page.tsx:124-137,143-163` | `newIcp`/`acceptIcpSuggestion` rely on eager updater evaluation to read `added` synchronously. Compute the new array/index outside the updater. |
| ☐ | **N42** | `list/page.tsx:1739,1774,1782` | Busy-flag asymmetry lets Find launch while Lookalike/Update runs (interleaved reloads/toasts). One `coMutating` disjunction on all three buttons. |
| ☐ | **N43** | `login/page.tsx:344-360` | Manual reset-token input is unreachable AND self-unmounting (gated on `!resetToken` while its own onChange sets it). Delete the block. |
| ☐ | **N44** | `lib/client.ts:31-32` + `ClientSwitcher.tsx:70` | `loadClients` accepts any JSON array; an entry without `name` throws in render → blank console on every route. Keep only entries with string `name`+`slug`; fall back to `DEFAULT_CLIENTS`. |
| ☐ | **N45** | `ClientSwitcher.tsx:49-58` + `lib/api.ts` + `components/console/MeContext` | "Create new client" is localStorage-only but console data is live per-tenant → navigates to a tenant that doesn't exist; all API 404s are swallowed into a plausible empty console. **(Q5 ✅ — founder chose the COMPLETE flow, not local create.)** Wire end-to-end: (a) the switcher list reads from `me.clients` (live); localStorage keeps only the last-selected slug; (b) "Create" calls a new `createClient(name)` in `lib/api.ts` → the existing JWT-gated `POST /clients` (the server generates + dedupes the slug — use the RETURNED slug, never derive it locally); (c) on success refetch `/me` (or add a refresh to MeContext) and navigate to `/<new-slug>/workspace`; (d) on failure warn-toast, no navigation. Rescoped by the founder from cleanup to a small feature — stays in G5 (not deploy-blocking). |
| ☐ | **N46** | `client-status/approval/page.tsx:261-264,288` | Status-log filter keys/matches on batch NAME (explicitly non-unique per `batches/page.tsx:81-82`) → duplicate options, merged logs. Use `value={r.id}` + filter by id. |
| ☐ | **N47** | `campaign/page.tsx:41-43` + `fixtures.ts:68-140` | Renaming a campaign orphans the mock Reply/Recap rows pinned to the literal "Campaign 1". On rename, remap matching campaign tags in replies state. (Mock-only; smallest diff.) |

**Infra / migrations / scripts:**

| ✔ | # | Where | Problem → fix |
|---|---|---|---|
| ☐ | **N48** | `infra/alembic/versions/20260710_0027_…py:52-55` | The partial-unique CREATE aborts the transactional upgrade if a duplicate active (tenant,kind) pair exists (pre-0027 code can still mint one). Verified clean on dev today; still: terminal-ize duplicate active rows (keep newest) before the CREATE. **0027 is unapplied — edit it in place** (with N8's `research_job` index + N49). |
| ☐ | **N49** | `0027` + `models.py:534-537` | `ix_research_run_tenant_id` is prefix-covered by the new `ix_research_run_tenant_created`. Drop it in 0027 (+ models). Parity test updates. |
| ☐ | **N50** | `infra/README.md` | Fresh `alembic upgrade head` stalls at `0002` without `HOLDSLOT_SEED_PASSWORD` (deliberate). One line in the README's migrate step. |
| ☐ | **N51** | `docs/prompts/*.md` | Migrations read these mutable files at run time (0005 was already retro-edited) → fresh-replay divergence. Add a "frozen once shipped" note at the top of `docs/prompts/` files or the README; new prompt text = new file + new migration. |
| ☐ | **N52** | `infra/terraform/iam.tf:63-66` | Lambda role can read ALL `holdslot/prod/*` secrets incl. Google SA + Smartlead it won't use until E/F. Enumerate `app`/`openrouter`/`apollo` only (founder-gated apply; **Q6 ✅ cutover**). |
| ☐ | **N53** | `amplify.yml` + `lib/api.ts:4-5` | `NEXT_PUBLIC_API_BASE_URL` lives only in Amplify console; unset → silent localhost fallback in a prod build. Fail the build in `preBuild` when unset. |
| ☐ | **N54** | `infra/terraform/apigw.tf:22-40` | No stage throttling (account defaults only) — runaway client = unbounded Lambda+ACU spend; only guard is the budget email. Set `throttling_burst_limit`/`throttling_rate_limit` on the stage (founder-gated apply; **Q6 ✅ cutover**). |
| ☐ | **N55** | `build-and-deploy.sh:35-39` | SnapStart wait falls through after 400s and still shifts `live`. Folded into **N22** (same file). |
| ☐ | **N56** | `0024_scoring_v2_labels.py:29` | Docstring says "five columns", four exist. Wording only. |

---

## §5 · Dead-code inventory (delete unless marked keep; grep-verify zero refs before each)

**Backend:** `router.py:944` `classify_companies(brief)` param never read (+ `add_company:1055` does an
extra `_latest_brief` round trip solely to pass it) · `scoring.py:87` `latest_job` zero callers ·
`apollo/client.py:168` `search_companies` no production caller (live path = `search_companies_meta`;
re-point its tests, delete, and fix the module docstring at `:7-8` that still claims company search
"consumes plan credits") · `fit.py:233` `COMPANY_SCORE_V2_SCHEMA` static (test-only — inline into the
test) · `apollo_map.py:266` `parse_person` `has_email` key never read · `suppression.py:43-45`
`Candidate.target_titles/target_seniority/icp_id/company_industry` write-only · stale docstrings
naming retired sync routes at `router.py:9,1700,2248,2497` · `openrouter/client.py:52` `DEFAULT_MODEL`
unreferenced · `core/security.py:69-80` refresh `jti` generated but never read · `core/config.py:22-26,
51-53` `Settings.secrets_prefix/db_*` fields never read (side effect: `get_settings()` crashes without
DB env even for JWT-only callers — remove the fields).

**Frontend:** `api.ts:1004-1016` `decideBatch` — **KEEP** (backlog: step-3 decide UI; annotate) ·
`e2e/_mock.ts:100-101` `"/people/scope-override"` case never matches (real path is
`/{client}/scope-override?kind=people`) — delete or fix the path · export-only-internal symbols (drop
`export`): `api.ts` `Feed`/`FindResult`/`RefreshResult`/`SavedSystemPrompt`/`ApprovalDecisionApi`/
`LoginResult`/`BriefResult`/`SourcingDocApi`/`CompanyManual`/`ProspectManual`/`ScopeKind`;
`constants.ts` `UNSCORED_RANK`/`labelRank`/`ExclusionGroup` · `ConsoleShell.tsx:66-71` the
`{onStatus && …}` crumb fragment is unreachable (`onStatus` forces `showTabSlot`) + `LABELS` entries it
renders · `types.ts:78` `Reply.draft` read only by fixture self-init · `login/page.tsx:344-360` (= N43).

---

## §6 · Unoptimized inventory (fix only what G-phases touch; rest = post-cutover backlog)

**Data-API round trips (backend):** `_run_company_find` (`router.py:1685-86`) per-row refresh + the
whole discarded `FindResult` build on worker paths · `_update_fields_core:2275-76` and
`select_companies:1785-86` refresh loops (results discarded / nothing re-read) · `list_research_runs:
2288-92` unbounded — returns ALL runs with full JSONB `filter_body`/`result_meta` per drawer open (add
LIMIT 50) · find-path redundant context loads (brief loaded ≤3×, spec ≤2× per request across
`_exclusions`/`classify_companies`/`_label_companies_deterministic` — thread the loaded rows through) ·
`batches/router.py:169-177` `create_batch` per-row INSERT+RETURNING (one multi-row `insert().values()`)
· `briefs/router.py:225-236` `get_research_spec` fetches every version's full JSONB for a version list ·
`auth/router.py:126-131` reset revokes tokens per-row (one UPDATE) · `structuring.py:240-276` full-scan
aggregations per preview (fine at dogfood volume; SQL-aggregate before multi-tenant).

**Frontend:** `brief/page.tsx:325-333` serial `getBrief→listIcps→getResearchSpec` (Promise.all) ·
`brief/page.tsx:381-389` `persist` PUTs every ICP serially even unchanged (diff or parallelize) ·
`list/page.tsx:1355-63` `findPeopleFor` strictly-serial chunks (bounded Promise.all — verify Apollo
rate limits first).

---

## §7 (= G7) · Production commit + deploy checklist

**Reviewed clean (no action):** no `innerHTML`/`dangerouslySetInnerHTML` anywhere in `apps/web`; all
console routes auth-gated (MeProvider redirect + SessionGuard; external pages token-based by design);
no CSS element-selector leaks (N19 is a class collision); no open redirect in login; OpenRouter pinned
to `deepseek/*` models — geo-blocked providers unreachable by construction; Gate-2 invariant holds
server-side (`people/match` reachable only via the reveal/rescore doors); `.gitignore` covers
`.env*`/`*.tfvars`/keys; no secrets in tf state or scripts (except N21); migration chain 0001→0027
replays linearly (0002 needs `HOLDSLOT_SEED_PASSWORD` — N50).

| ✔ | Step |
|---|---|
| ☑ | **Checkpoint commit** — ✅ made 2026-07-11 (this session): one atomic local commit = D+.5 wave + this review's docs (`0027` glued to the `enqueue_scoring`/`enqueue_structuring` coalesce code it pairs with). One local commit per G-phase from here (rule 5). No pushes until push #1. |
| ☐ | **Push #1 + deploy dev (after G4, founder go — Q2):** G1–G4 complete + green (backend pytest+ruff · FE build+tsc+eslint · **e2e green — mandatory, Q8**). Order: `build-and-deploy.sh` FIRST (alembic `0027` incl. N8/N48/N49 → Lambda publish → SnapStart wait → shift `live`; the N3 `terraform apply` rides this deploy — Q6) → THEN push via `weftxio` (Amplify auto-deploys the FE). Backend before frontend, always. |
| ☐ | **Dev smoke** (founder, deployed Lambda only): async find → score → reveal on the dev tenant · the 18 Aurora-gated tests · double-POST enqueue (scoring AND structuring) to verify the coalesce fires live (N29) · selection-edge manual pass (excluded untick/remove, filter+select, leave mid-poll). |
| ☐ | **Re-score candidate list (Q7 ✅):** after the smoke, query dev Aurora **read-only** for companies with `label = 'excluded_by_rules'` and the geo reason (`rule: outside target geography`) — wrongly excluded pre-N4 — plus any N6 mis-tag suspects (multi-ICP tenants with renamed ICPs; today = tenant #0 only). Deliver the list (name · domain · reason · ICP) to the founder; **the founder re-scores in the UI** ("Update AI Score", ≤15/batch — free gates re-run at $0, only now-passing rows reach the paid call). |
| ☐ | **G5–G6 follow-up wave** on the smoked baseline (per-phase commits; e2e stays green) → **push #2** (founder go; same backend-first order if any backend change shipped). |
| ☐ | **Prod cutover items** (existing plan + this review): terraform workspace `prod` · N20 DLQ+alarm · N52 IAM narrowing · N53 build guard · N54 throttling · e2e wired into the deploy script (Q8) · Aurora min-ACU ≥ 0.5 · S3 PAB · fresh JWT keys. (N3 already applied at push #1.) |

---

## Findings → phase map

| Phase | Items |
|---|---|
| G1 | N1 · N2 · N3 |
| G2 | N4 · N5 · N6 · N7 · N8 · N9 · N10 |
| G3 | N11–N19 |
| G4 | N20 · N21 · N22 (+N55) |
| G5 | N23–N54 · N56 |
| G6 | §5 dead code + §6 quick perf wins |
| G7 | push #1 + deploy (after G4) · smoke · re-score list (Q7) · G5–G6 → push #2 · cutover register |

## File → findings index (plan multi-edit files once; edits to the same file should land together)

| File | Findings |
|---|---|
| `apps/api/app/domains/prospects/router.py` | **N1** · N5 · N7 · N23 · N24 · N25 · N26 · N27 (+§5 docstrings, §6 refresh loops/`list_research_runs`/context loads) |
| `apps/api/app/domains/prospects/labeling.py` | N4 · N27 |
| `apps/api/app/domains/prospects/fit.py` | N6 (+§5 static schema const) |
| `apps/api/app/domains/prospects/scoring.py` | N29 · N30 (+§5 `latest_job`) |
| `apps/api/app/domains/briefs/structuring.py` | N8 · N29 · N30 (+§6 full-scan aggregations) |
| `apps/api/app/domains/auth/` | N9 · N33 · N34 · N36 (service+router; +§6 per-row revoke) |
| `apps/api/app/domains/approvals/router.py` | N10 |
| `apps/api/app/domains/batches/router.py` | N31 (+§6 per-row INSERT) |
| `apps/api/app/core/` + `main.py` | N32 (deps) · N37 (CORS) (+§5 `Settings` fields, `jti`) |
| `apps/api/app/integrations/openrouter/client.py` | N28 (+§5 `DEFAULT_MODEL`) |
| `infra/alembic/versions/…0027…py` + `models.py` | N8 · N48 · N49 (one edit; parity test rides along) |
| `infra/terraform/` | N3 (aurora) · N20 (lambda) · N52 (iam) · N54 (apigw) |
| `apps/api/scripts/` | N21 (smoke pw) · N22+N55 (deploy script) |
| `amplify.yml` · `infra/README.md` · `docs/prompts/` | N53 · N50 · N51 |
| `apps/web/…/workspace/list/page.tsx` | **N2** · N11 · N12 · N13 · N39 · N42 |
| `apps/web/…/workspace/brief/page.tsx` | N15 · N16 · N40 · N41 (+§6 serial loads/PUTs) |
| `apps/web/components/workspace/` | N14 (Provider) · N18 (FindHistoryDrawer) |
| `apps/web/e2e/` | N17 (+§5 dead mock case) |
| `apps/web/lib/` | N38 (constants) · N44 (client.ts) (+§5 export trims) |
| `apps/web/app/` (mock surface) | N19 (home.css) · N43 (login) · N45+N44 (ClientSwitcher) · N46 (approval log) · N47 (campaign) |

**Docs status:** `data-schema.md` + `initial-build-plan.md` were trued up to this review on
2026-07-11 (31 drift items fixed — spec-version labels, retired v1 vocabulary, route/kind counts,
identity-key form, scope-override as-built, S1/S2 gate rows, constants). Keep both docs in sync as
G-phases land (N8/N49 touch `0027` → update `data-schema.md`'s index/migration sections in G2).
