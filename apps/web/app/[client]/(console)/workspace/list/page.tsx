"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useClient } from "@/lib/nav";
import { toggleInSet } from "@/lib/sets";
import clsx from "clsx";
import { useToast } from "@/components/Toast";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { FindHistoryDrawer } from "@/components/workspace/FindHistoryDrawer";
import {
  type CompanyApi,
  type FacetOption,
  type FitPrompt,
  type FitStage,
  type PeopleFacets,
  type ProspectApi,
  addCompany,
  addProspect,
  awaitScoringJob,
  createBatch as apiCreateBatch,
  deletePeopleScopeOverride,
  deleteScopeOverride,
  enrichScoreProspectsAsync,
  findCompaniesAsync,
  findLookalikesAsync,
  findPeople,
  getFitPrompt,
  getPeopleScopeOverride,
  getScopeOverride,
  getSourcingDocs,
  peopleFacets,
  putPeopleScopeOverride,
  putScopeOverride,
  rescoreCompaniesAsync,
  rescoreProspectsAsync,
  saveSourcingDoc,
  SCORE_BATCH_MAX,
  selectCompanies,
  updateCompanyFieldsAsync,
} from "@/lib/api";
import type { ScoreLabel, ScoringJobApi } from "@/lib/api";
import type {
  PeopleScopeForm,
  PeopleScopeOverride,
  ScopeForm,
  ScopeOverride,
  ScoringSetter,
} from "@/lib/workspace/types";
import {
  ENRICHED_STATUS,
  clearScoring,
  compareByLabel,
  effectivePeopleScope,
  effectiveScope,
  formToOverride,
  formToPeopleOverride,
  groupByLabel,
  peopleScopeSummary,
  peopleScopeToForm,
  scopeSummary,
  scopeToForm,
} from "@/lib/workspace/constants";
import {
  AddCompanyModal,
  AddPersonModal,
  PeopleScopeModal,
  RubricModal,
  ScopeSettingsModal,
  Step1Companies,
  Step2People,
  useListData,
  type ManualCompanyForm,
  type ManualPersonForm,
} from "@/components/workspace/list";

// Override gate (spec §11 / decision ④): an `excluded_by_rules` row is locked out of any selection.
// A selection verdict for a toggle: "ok" apply now · "blocked" locked out (an excluded row in Step 1).
// Deselecting is always "ok"; only *adding* an excluded row is blocked. low_fit rows add freely.
function maySelect(
  label: ScoreLabel | null,
  currentlyChecked: boolean,
  allowExcluded = false
): "ok" | "blocked" {
  if (currentlyChecked) return "ok"; // unticking is ALWAYS allowed (tick-to-remove in Step 2, R6)
  // Step 2 passes allowExcluded so a staged-then-excluded company can be TICKED for removal; the
  // funnel-advancing handlers (stageForPeople / runFindPeople / reveal) each filter excluded rows out
  // themselves, and the prune effect drops them from the selection after any reload/scoring wave.
  if (label === "excluded_by_rules") return allowExcluded ? "ok" : "blocked";
  return "ok";
}

// Return `set` minus every id in `remove` — same reference when nothing changed (stable for React).
function dropIds(set: Set<string>, remove: Set<string>): Set<string> {
  let changed = false;
  const next = new Set<string>();
  for (const id of set) {
    if (remove.has(id)) changed = true;
    else next.add(id);
  }
  return changed ? next : set;
}
// Find People searches one Apollo call per org; the server caps a single request at MAX_ORGS_PER_FIND
// (8) orgs, so the FE chunks a larger selection into 8-org calls threaded by one group_id.
const FIND_ORGS_CHUNK = 8;

// Step-1 row order: Accepted companies (already staged to Step 2 → status "people_found") sort to
// the top, then by total 4-axis score (score_total, out of 20) desc, then newest. Label bucketing
// (groupByLabel) is applied AFTER this sort, so in the rendered call sheet this governs order WITHIN
// each bucket — Accepted rows head each section, then descend by score.
function compareCompanyRows(a: CompanyApi, b: CompanyApi): number {
  const accepted = (c: CompanyApi) => (c.status === "people_found" ? 0 : 1);
  if (accepted(a) !== accepted(b)) return accepted(a) - accepted(b);
  const sa = a.score_total ?? -1;
  const sb = b.score_total ?? -1;
  if (sa !== sb) return sb - sa;
  return (b.created_at ?? "").localeCompare(a.created_at ?? "");
}

export default function ListPage() {
  const client = useClient();
  // Cross-navigation cache for this page's API reads (companies/prospects/docs/depts/icps/spec/
  // people-scope). Keyed by client so a tab switch returns instantly from cache (app/providers.tsx);
  // the reloads + scope/doc writes below sync the cache so a return after a paid find shows fresh rows.
  const qc = useQueryClient();
  const toast = useToast();
  // Batch creation from the enriched selection calls the live API, then refreshes the shared
  // cross-tab batches state so the Sendout Batch + Campaign surfaces pick it up.
  const { reloadBatches } = useWorkspace();
  // Tracks the live client so an async reload/handler that resolves *after* a client switch can
  // bail before writing the previous client's data into the new client's view.
  const clientRef = useRef(client);
  // The list feed (companies · prospects · docs · icps · spec · master depts) + its two reloads and
  // the client-keyed hydrate live in useListData (2.4 Stage 2); it also owns the rubric draft (seeded
  // from the loaded rubric doc) and sets clientRef. Per-client UI resets stay in the effect below.
  const {
    icps,
    spec,
    prospects,
    companies,
    prospectsLoading,
    companiesLoading,
    docs,
    setDocs,
    rubricDraft,
    setRubricDraft,
    masterDepts,
    reloadProspects,
    reloadCompanies,
  } = useListData(client, clientRef);

  // The multi-ICP axis: dropdown options + id→name lookup for the ICP filter (both stages), the
  // ICP column chips, and the Find Company target. API-loaded ICPs always carry a real id.
  const icpOptions = useMemo(
    () =>
      icps
        .filter((i) => i.id)
        .map((i) => ({ id: i.id as string, label: i.short || i.tag || "ICP" })),
    [icps]
  );
  const icpNameById = useMemo(() => new Map(icpOptions.map((o) => [o.id, o.label])), [icpOptions]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [fStatus, setFStatus] = useState(""); // "" all · "found" · "scored" (Enriched)
  const [fIcp, setFIcp] = useState(""); // an ICP id (or "")
  const [newBatchName, setNewBatchName] = useState("");
  // Fit-rubric settings (the versioned scoring rubric), edited in a modal.
  const [showSourcing, setShowSourcing] = useState(false);
  const [savingDoc, setSavingDoc] = useState<FitStage | null>(null);
  // Which rubric the Fit-rubric modal is editing — `company_fit` on the Step-1 tab, `prospect_fit`
  // on Step-2 — set when the modal opens so its body/preview/badges all target the same stage.
  const [rubricStage, setRubricStage] = useState<FitStage>("company_fit");
  // The real fit-score prompt for one sample company (system rubric + the live targeting context
  // built from this client's brief + research spec + ICP docs), fetched when the modal opens.
  const [fitPrompt, setFitPrompt] = useState<FitPrompt | null>(null);
  const [fitPromptLoading, setFitPromptLoading] = useState(false);
  const [fitPromptErr, setFitPromptErr] = useState<string | null>(null);

  // Two-stage prospecting (company-first): step 1 finds companies, step 2 finds people at the
  // selected ones. `listStage` is the sub-view; companies + their selection live here.
  const [listStage, setListStage] = useState<"companies" | "people">("companies");
  const [companyChecked, setCompanyChecked] = useState<Set<string>>(new Set());
  const [coSearch, setCoSearch] = useState("");
  // Which collapsed footnote buckets (low_fit / excluded_by_rules) are expanded in the Step-1 table.
  // Default empty → both start collapsed to a one-line count (spec §11); reset on a client switch.
  const [expandedBuckets, setExpandedBuckets] = useState<Set<string>>(new Set());
  // Which reason sub-groups inside those buckets are expanded — keyed `${bucket}::${reasonKey}`.
  // Default empty → each reason opens collapsed to its count, so expanding a bucket shows the
  // per-reason breakdown rather than dumping every row (the point of the sub-layer).
  const [expandedSubs, setExpandedSubs] = useState<Set<string>>(new Set());
  // Status filter: "" all · "accepted" = people_found (the Accepted tag) · "pending" = not yet.
  const [coStatus, setCoStatus] = useState("");
  const [findingCo, setFindingCo] = useState(false);
  const [updatingFields, setUpdatingFields] = useState(false);
  const [findingLookalike, setFindingLookalike] = useState(false);
  // Company rows whose AI fit-score is being computed in the background (post-Lookalike). The AI
  // Score cell shows a "Scoring…" status for these until each chunk lands.
  const [scoringCoIds, setScoringCoIds] = useState<Set<string>>(new Set());
  const [findingPpl, setFindingPpl] = useState(false);
  const [staging, setStaging] = useState(false); // Step-1 → Step-2 move in flight
  const [removing, setRemoving] = useState(false); // Step-2 → Step-1 un-stage in flight
  // Step-2 company rows whose people are being searched right now (per-row "Finding people…").
  const [findingPplIds, setFindingPplIds] = useState<Set<string>>(new Set());
  // Prospect rows whose AI fit-score is being computed in the background (Step-2 'Get AI score').
  const [scoringPersonIds, setScoringPersonIds] = useState<Set<string>>(new Set());
  // Synchronous re-score guards: the button `disabled` only flips after a re-render, so a fast
  // double-click could dispatch two paid scoring passes before the flag lands. These ref guards
  // block the second click in the same tick (a paid-spend race).
  const rescoringCoRef = useRef(false);
  const rescoringPplRef = useRef(false);
  // M23 — same synchronous double-click guard for the paid company-field update (an Apollo credit
  // spend): the button's `disabled` only flips after a re-render, so a fast second click would fire
  // a second spend in the same tick without this ref.
  const updateFieldsCoRef = useRef(false);
  // L13 — same synchronous double-click guard for Create Batch: two fast clicks during the POST
  // round-trip otherwise mint two identical batches, both sendable for approval and mintable into
  // campaigns. `disabled` only flips after a re-render, so the ref blocks the second click in-tick.
  const creatingBatchRef = useRef(false);
  // R12 — false once this page unmounts, so a job poll loop stops (no orphan polling + toasts after
  // navigating away). Combined with the client check in the `alive` callbacks below.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
  // The liveness gate every job poll checks: still mounted AND still on this client.
  const pollAlive = () => mountedRef.current && clientRef.current === client;
  // Manual-add modals (same schema as imported rows; source=manual).
  const blankCo = {
    domain: "",
    name: "",
    website: "",
    industry: "",
    size: "",
    country: "",
    linkedin_url: "",
  };
  const [addCoOpen, setAddCoOpen] = useState(false);
  const [coForm, setCoForm] = useState<ManualCompanyForm>({ ...blankCo });
  const [savingCo, setSavingCo] = useState(false);
  const [creatingBatch, setCreatingBatch] = useState(false); // L13 — disables Create Batch in-flight
  // Manual override of the AI scope's Apollo company-search filters (Settings modal). Stored per
  // (client, ICP); this state mirrors the CURRENT ICP filter's entry (see the sync effect below).
  const [scopeOverride, setScopeOverride] = useState<ScopeOverride | null>(null);
  const [scopeOpen, setScopeOpen] = useState(false);
  // Find-history drawer (D+ Stage 1b) — read-only view of the scope lineage on `/research-runs`.
  const [findHistoryOpen, setFindHistoryOpen] = useState(false);
  // Scope-exhausted notice (D+ Stage 3): the last find walked to the end of this scope's Apollo
  // result set (the page cursor reached total_pages), so there is nothing new left to find here.
  const [scopeExhausted, setScopeExhausted] = useState(false);
  const [scopeForm, setScopeForm] = useState<ScopeForm | null>(null);
  // Which ICP the Find-Settings modal is editing (its own pick, so the operator can switch ICP
  // scopes inside the modal without touching the page filter until Save).
  const [scopeIcp, setScopeIcp] = useState("");
  // Brief attention flash on the Step-1 ICP dropdown when Find Company needs a pick — the toast
  // says WHAT, this shows WHERE.
  const [icpNeedsPick, setIcpNeedsPick] = useState(false);
  // Same, for the Step-2 Apollo people-search filters.
  const [peopleScopeOverride, setPeopleScopeOverride] = useState<PeopleScopeOverride | null>(null);
  const [peopleScopeOpen, setPeopleScopeOpen] = useState(false);
  const [peopleScopeForm, setPeopleScopeForm] = useState<PeopleScopeForm | null>(null);
  // Live facet sidebar for the Find-Settings modal (per Management-Level / Department people counts
  // across the selected Step-2 companies). Null until a probe runs; departments come from here too.
  const [pplFacets, setPplFacets] = useState<PeopleFacets | null>(null);
  const [pplFacetsLoading, setPplFacetsLoading] = useState(false);
  const blankPerson = {
    full_name: "",
    company: "",
    domain: "",
    linkedin_url: "",
    email: "",
    title: "",
    seniority: "",
  };
  const [addPersonOpen, setAddPersonOpen] = useState(false);
  const [personForm, setPersonForm] = useState<ManualPersonForm>({ ...blankPerson });
  const [savingPerson, setSavingPerson] = useState(false);

  // Reset per-client UI state on a client switch — selection, filters and in-flight flags reference
  // the PREVIOUS client's ids/state and would leak across a switch (a stale fIcp silently hides the
  // new client's rows; stale checked ids feed accept/createBatch; a busy flag wedges a button whose
  // finally is gated on the old client). The App Router can't remount this page on the [client] param,
  // so we reset here; the feed itself is hydrated by useListData (which also sets clientRef). (2.4)
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!client) return;
    setChecked(new Set());
    setCompanyChecked(new Set());
    // Clear any in-flight "Scoring…" flags from the previous client (the background loop bails on the
    // client switch, but its safety-net clear is gated on the old client — these would otherwise leak).
    setScoringCoIds(new Set());
    setScoringPersonIds(new Set());
    rescoringCoRef.current = false;
    rescoringPplRef.current = false;
    updateFieldsCoRef.current = false;
    creatingBatchRef.current = false;
    setCreatingBatch(false);
    // N13 — clear every mutation busy-flag too: each is set by a handler whose `finally` is gated on
    // the OLD client, so a switch mid-Find/Update/Lookalike/stage/remove would otherwise wedge the
    // button ("Fetching…") forever on the new client.
    setFindingCo(false);
    setUpdatingFields(false);
    setFindingLookalike(false);
    setFindingPpl(false);
    setFindingPplIds(new Set());
    setStaging(false);
    setRemoving(false);
    setSearch("");
    setCoSearch("");
    setFIcp("");
    setExpandedBuckets(new Set());
    setExpandedSubs(new Set());
    setCoStatus("");
    setPeopleScopeOverride(null); // hydrated from the server by the (client, fIcp) effect below
  }, [client]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // R6 — after ANY companies/prospects reload or scoring wave, drop selected ids whose row is now
  // `excluded_by_rules`, so an excluded company can never be staged into Step 2 (LOCKED invariant)
  // and an excluded person is never revealed/batched. Non-excluded ticks are kept even when filtered
  // out of view (the selection is deliberately over the WHOLE list; see coSel / selectedProspects).
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const excluded = new Set(
      companies.filter((c) => c.label === "excluded_by_rules").map((c) => c.id)
    );
    if (excluded.size) setCompanyChecked((s) => dropIds(s, excluded));
  }, [companies]);
  useEffect(() => {
    const excluded = new Set(
      prospects.filter((p) => p.label === "excluded_by_rules").map((p) => p.id)
    );
    if (excluded.size) setChecked((s) => dropIds(s, excluded));
  }, [prospects]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // The Step-2 people-scope override is persisted server-side per (tenant, ICP) — re-fetch it on
  // (client, fIcp) change so the "Custom" badge + summary reflect the selected ICP's own tuning and
  // follow the operator across browsers. Re-running here also RETRIES a failed load automatically
  // (switch ICP or client, or click the gear which re-seeds) — a single fetch failure no longer
  // disables the gear for the whole session. find_people reads the same DB row, so this is display.
  useEffect(() => {
    let alive = true;
    getPeopleScopeOverride(client, fIcp || undefined)
      .then((b) => {
        if (alive) setPeopleScopeOverride(b ? { people_search_params: b } : null);
      })
      .catch(() => {
        if (alive) {
          // N39 — drop the previous ICP's override on a failed load, so the "Custom" badge + scope
          // summary never keep reflecting a DIFFERENT ICP's tuning after switching ICPs.
          setPeopleScopeOverride(null);
          toast("Couldn’t load saved person filters · try again", "warn");
        }
      });
    return () => {
      alive = false;
    };
  }, [client, fIcp, toast]);

  // Prospects grouped by their company id (robust — the company label can drift; the id can't).
  const prospectsByCompany = useMemo(() => {
    const m = new Map<string, ProspectApi[]>();
    for (const p of prospects) {
      if (!p.company_id) continue;
      const g = m.get(p.company_id);
      if (g) g.push(p);
      else m.set(p.company_id, [p]);
    }
    return m;
  }, [prospects]);
  // Step 2 is company-centric: the pursued companies (staged into Step 2 as `selected`, or already
  // searched → `people_found`) are the rows; each company's found people nest beneath it. `search`
  // filters the companies; `fLabel` filters the people shown within them. Ordered by enriched count,
  // then total people — both descending — so the most-progressed companies surface first.
  const pursued = useMemo(
    () =>
      companies
        .filter(
          (c) =>
            (c.status === "selected" || c.status === "people_found") &&
            (!fIcp || c.icp_id === fIcp) &&
            (!search || `${c.name} ${c.domain}`.toLowerCase().includes(search.toLowerCase()))
        )
        .sort((a, b) => {
          const pa = prospectsByCompany.get(a.id) ?? [];
          const pb = prospectsByCompany.get(b.id) ?? [];
          const ea = pa.filter((p) => p.status === ENRICHED_STATUS).length;
          const eb = pb.filter((p) => p.status === ENRICHED_STATUS).length;
          if (eb !== ea) return eb - ea;
          return pb.length - pa.length;
        }),
    [companies, search, fIcp, prospectsByCompany]
  );
  // The pool a manually-added person can attach to: companies accepted into Step 2 (with a domain,
  // since the backend resolves the person's company by domain). Drives the Add-person dropdown.
  const step2Companies = useMemo(
    () =>
      companies.filter((c) => (c.status === "selected" || c.status === "people_found") && c.domain),
    [companies]
  );
  // Header count for the Step-2 tab — people whose company is CURRENTLY in Step 2 (selected |
  // people_found). Unlike `prospects.length`, this drops the people of a company that was removed
  // back to Step 1: their prospect rows persist in the DB but no longer show under any Step-2 row,
  // so the tab count would otherwise over-report. Independent of the search/fit/status filters (a
  // "total", mirroring how Step 1's tab shows all companies).
  const step2PeopleCount = useMemo(() => {
    const inStep2 = new Set(
      companies
        .filter((c) => c.status === "selected" || c.status === "people_found")
        .map((c) => c.id)
    );
    return prospects.reduce((n, p) => (p.company_id && inStep2.has(p.company_id) ? n + 1 : n), 0);
  }, [companies, prospects]);
  // Rows of a pursued company that pass the status filter — the per-company nested list, ordered as
  // a call sheet (contact_now first, then score desc, newest) via compareByLabel (spec §11). Label
  // filtering is done by the in-table bucket expand/collapse, not a dropdown (v2 toolbar).
  const rowsForCompany = (id: string) =>
    (prospectsByCompany.get(id) ?? [])
      .filter((p) => !fStatus || p.status === fStatus)
      .sort(compareByLabel);
  // People in view across all pursued companies = the unit of selection for score / enrich / batch.
  const visible = useMemo(
    () => pursued.flatMap((c) => rowsForCompany(c.id)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pursued, prospectsByCompany, fStatus]
  );
  // Step-2 companies that are ticked — the unit of selection for Find People.
  const pplCoSel = pursued.filter((c) => companyChecked.has(c.id));
  // Step-2 dock: reveal-&-score before batch — find people → reveal & score → batch. Computed over
  // the WHOLE selection (not the filtered view) so a filter change can't drop checked rows.
  // `runRevealScore`/`createBatch` re-derive from the same rule.
  const selectedProspects = useMemo(
    () => prospects.filter((p) => checked.has(p.id)),
    [prospects, checked]
  );
  const toEnrich = useMemo(
    // R14 — spend estimate: a person needs a PAID reveal iff they have no email yet. Email present =
    // already bought (no re-spend even if a later score failed); `enrich_failed` (no email) DOES
    // count — a re-match can spend — which the old status set (found/confirmed/score_error) missed.
    () => selectedProspects.filter((p) => !p.email),
    [selectedProspects]
  );
  const enrichedSel = useMemo(
    () => selectedProspects.filter((p) => p.status === ENRICHED_STATUS),
    [selectedProspects]
  );
  // Batch only once EVERY selected person is enriched (a verified email) — closes the gap where an
  // enrich_failed (no-email) row slipped through the old "nothing still needs enrich" gate.
  const canBatch = useMemo(
    () =>
      selectedProspects.length > 0 && selectedProspects.every((p) => p.status === ENRICHED_STATUS),
    [selectedProspects]
  );

  function toggleRow(p: ProspectApi) {
    if (maySelect(p.label, checked.has(p.id)) === "blocked") return; // excluded locked out
    setChecked((s) => {
      const n = new Set(s);
      if (n.has(p.id)) n.delete(p.id);
      else n.add(p.id);
      return n;
    });
  }

  // The Step-1 manual scope override is persisted server-side per (tenant, ICP) — re-fetch it
  // whenever the client or the selected ICP changes (covers mount + client switch too) so the
  // active-filters summary + "Custom" badge reflect that ICP's own tuning, following the operator
  // across browsers. The next Find reads the same DB row server-side, so this is display-only.
  useEffect(() => {
    let alive = true;
    getScopeOverride(client, "company", fIcp || undefined)
      .then((b) => {
        if (alive) setScopeOverride(b ? (b as ScopeOverride) : null);
      })
      .catch(() => {
        if (alive) setScopeOverride(null);
      });
    return () => {
      alive = false;
    };
  }, [client, fIcp]);

  // ---- Stage 1: companies ----
  // Filter, then order as a call sheet by label (spec §11): contact_now → contact_soon → unscored →
  // low_fit → excluded_by_rules (the bucket order, applied by groupByLabel). Within each bucket,
  // Accepted rows (people_found) sort first, then by total score (/20) desc, then newest
  // (compareCompanyRows). The old client-side market-exclusion pinning is gone — a market-mismatched
  // company now carries the `excluded_by_rules` label from the server, so it lands in that footnote.
  const coVisible = useMemo(
    () =>
      companies
        .filter((c) => {
          const text = `${c.name} ${c.domain} ${c.industry}`.toLowerCase();
          const accepted = c.status === "people_found";
          const statusOk = !coStatus || (coStatus === "accepted" ? accepted : !accepted);
          const icpOk = !fIcp || c.icp_id === fIcp;
          return (!coSearch || text.includes(coSearch.toLowerCase())) && statusOk && icpOk;
        })
        .sort(compareCompanyRows),
    [companies, coSearch, coStatus, fIcp]
  );
  // The filtered rows grouped into label buckets (spec §11) for the call-sheet render — action
  // buckets shown expanded, the two footnote buckets collapsed to a count row.
  const coBuckets = useMemo(() => groupByLabel(coVisible), [coVisible]);
  // The ticked companies that still exist — the unit every Step-1 selection action runs on. Computed
  // over the WHOLE selection (not the filtered view), mirroring Step-2's `selectedProspects`, so a
  // filter change never silently drops a tick AND the displayed count always equals what runs (fixes
  // the "Get AI score 3 · actually runs 9" gap where the count was visible∩checked but the handler
  // used every checked id).
  const coSel = useMemo(
    () => companies.filter((c) => companyChecked.has(c.id)),
    [companies, companyChecked]
  );
  const coSelCount = coSel.length;
  // N42 — ANY company-mutating action in flight (Find / Find Lookalike / Update fields). One shared
  // disjunction gates all three buttons, so a second mutation can't launch over a running one (Find
  // previously only checked `findingCo`, so it could fire while Lookalike/Update were mid-flight).
  const coMutating = findingCo || findingLookalike || updatingFields;
  // A background AI-scoring pass (Find / Find Lookalike / Update AI Score) is running for ≥1 row.
  const scoringActive = scoringCoIds.size > 0;
  const scoringPeopleActive = scoringPersonIds.size > 0;
  // Sample company for the Fit-rubric preview: the first ticked row, else the first one in view. Its
  // id is sent to GET /fit-prompt?stage=company_fit so the modal shows that row's real input prompt.
  const rubricSample = useMemo(
    () => coVisible.find((c) => companyChecked.has(c.id)) ?? coVisible[0] ?? companies[0] ?? null,
    [coVisible, companyChecked, companies]
  );
  // Sample prospect for the Step-2 (prospect_fit) preview: first ticked person, else first in view.
  // Its id is sent to GET /fit-prompt so the modal shows that person's real input prompt.
  const prospectSample = useMemo(
    () => visible.find((p) => checked.has(p.id)) ?? visible[0] ?? prospects[0] ?? null,
    [visible, checked, prospects]
  );
  // List is "fetching" during initial hydrate, an Apollo find, or a re-score — show the overlay
  // spinner over the table for the whole period, whether or not rows already exist.
  // Note: `scoringActive` is deliberately NOT here — background scoring keeps the table visible with
  // per-row "Scoring…" status instead of the full-list overlay.
  const coBusy = companiesLoading || findingCo || updatingFields || findingLookalike;
  const pplBusy = prospectsLoading || findingPpl;
  // One-line read of the scope Find Companies will use right now (override or AI spec) — shown in
  // the empty state so a 0-result is explainable, not mysterious.
  const coScopeSummary = useMemo(
    () => scopeSummary(effectiveScope(scopeOverride, spec, fIcp || undefined)),
    [scopeOverride, spec, fIcp]
  );
  const pplScopeSummary = useMemo(
    () => peopleScopeSummary(effectivePeopleScope(peopleScopeOverride, spec, fIcp || undefined)),
    [peopleScopeOverride, spec, fIcp]
  );
  // The ICP the next Find Company will target, shown on the Find button face (v2 toolbar): the
  // picked filter ICP, or the sole ICP when there's only one. Null on a multi-ICP scope with no
  // pick yet → the button reads "Find companies" and clicking flags the ICP filter to choose.
  const coTargetIcpName = fIcp
    ? icpNameById.get(fIcp)
    : icpOptions.length === 1
      ? icpOptions[0].label
      : null;
  function toggleCo(c: CompanyApi, allowExcluded = false) {
    // excluded locked out of Step-1 selection; unticking always allowed. Step 2 passes allowExcluded
    // so a staged-then-excluded company can be ticked for removal (R6). low_fit rows add freely.
    if (maySelect(c.label, companyChecked.has(c.id), allowExcluded) === "blocked") return;
    setCompanyChecked((s) => toggleInSet(s, c.id));
  }
  // Expand/collapse a Step-1 footnote bucket (low_fit / excluded_by_rules) — keyed by the label.
  function toggleBucket(key: string) {
    setExpandedBuckets((s) => toggleInSet(s, key));
  }
  // Expand/collapse one reason sub-group inside a footnote bucket — keyed `${bucket}::${reasonKey}`.
  function toggleSub(key: string) {
    setExpandedSubs((s) => toggleInSet(s, key));
  }

  async function submitAddCompany() {
    if (!coForm.domain.trim()) return toast("A company domain is required", "warn");
    setSavingCo(true);
    try {
      const co = await addCompany(client, { ...coForm, icp_id: fIcp || null });
      toast(`Added ${coForm.name || coForm.domain} · scoring…`);
      setAddCoOpen(false);
      setCoForm({ ...blankCo });
      await reloadCompanies();
      // The row lands UNSCORED (scoring is off the request path) — score it on a background job,
      // exactly like an Apollo-found row, so a slow reasoning call never blocks the add.
      void scoreCompaniesJob([co.id]);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Add failed", "warn");
    } finally {
      setSavingCo(false);
    }
  }

  // Kick off an async scoring job (W4) and poll it to completion. Returns the terminal job, or null
  // if the client switched away mid-flight or the job errored (the error is toasted here). Replaces
  // the old client-driven chunk loops — the worker owns the whole batch, surviving a tab close.
  async function runScoringJob(
    kick: () => Promise<ScoringJobApi>,
    failLabel: string
  ): Promise<ScoringJobApi | null> {
    const started = await kick();
    if (!started.job_id) {
      if (clientRef.current === client) toast(`${failLabel} failed`, "warn");
      return null;
    }
    const job = await awaitScoringJob(client, started.job_id, pollAlive);
    if (!pollAlive()) return null;
    if (job.status === "error") {
      toast(typeof job.error === "string" && job.error ? job.error : `${failLabel} failed`, "warn");
      return null;
    }
    // R12 — a non-terminal return (ceiling hit while still running) must NOT read as success: don't
    // reload as "done 0", just tell the operator it's still going. The finished rows land on the next
    // reload/refresh (the worker survives the tab).
    if (job.status !== "done") {
      toast(`${failLabel} is still running — refresh in a moment`, "ok");
      return null;
    }
    return job;
  }

  // Flow A — Apollo company search from the saved ResearchSpec (or the Settings override). Needs a
  // generated scope. The 0-result toast distinguishes "Apollo matched nothing" (loosen filters)
  // from "matched but all filtered out as dupes/exclusions" (`dropped`) so the cause is explainable.
  // Async (W4): kicks a background find job, polls it, then reloads. Rows land unscored.
  // Multi-ICP: the find is ICP-scoped — the ICP filter picks whose targeting block runs (a single
  // ICP is auto-picked). Mirrors the server 400 so the operator never hits an opaque error.
  async function runFindCompanies() {
    const icpForFind = fIcp || (icpOptions.length === 1 ? icpOptions[0].id : "");
    if (!icpForFind && icpOptions.length > 1) {
      setIcpNeedsPick(true);
      setTimeout(() => setIcpNeedsPick(false), 2200);
      return toast(
        "Pick an ICP in the filter first · Find Company searches one ICP's scope at a time",
        "warn"
      );
    }
    setFindingCo(true);
    setScopeExhausted(false); // clear last run's notice — this find gets a fresh verdict
    try {
      const job = await runScoringJob(
        // The saved override is read server-side from the DB (single source of truth), so a stale
        // in-memory copy in one tab can't shadow a save/reset done in another. find-company falls
        // back to the DB override → AI spec when no body override is given.
        () => findCompaniesAsync(client, { icp_id: icpForFind || null }),
        "Find companies"
      );
      if (!job) return;
      await reloadCompanies();
      const found = Number(job.result?.found ?? 0);
      const dropped = Number(job.result?.dropped ?? 0);
      // D+ Stage 3 — the page cursor resumes each find at the next page; when it reaches the end of
      // this scope's Apollo results the find comes back exhausted → show the recovery notice.
      const exhausted = Boolean(job.result?.scope_exhausted);
      const knownSkipped = Number(job.result?.known_skipped ?? 0);
      setScopeExhausted(exhausted);
      if (found) {
        // `dropped` already counts the known-skip; call it out so a low `found` on a re-find reads
        // as "these were already yours", not "the search is failing".
        const bits = [
          knownSkipped ? `${knownSkipped} already in your list` : "",
          dropped - knownSkipped > 0 ? `${dropped - knownSkipped} filtered out` : "",
        ].filter(Boolean);
        const tail = bits.length ? ` · ${bits.join(" · ")}` : "";
        // Rows land unscored and stay that way (AI Score shows "Pending"); the operator scores on
        // demand by selecting rows and clicking Update AI Score. No auto-trigger.
        toast(
          `Found ${found} new ${found === 1 ? "company" : "companies"}${tail} · ` +
            "select rows and click Update AI Score to score them"
        );
      } else if (exhausted) {
        // The notice below carries the recovery paths; keep the toast short.
        toast("You've reviewed every company Apollo has for this scope — see the notice below.");
      } else if (dropped) {
        toast(
          `Apollo returned ${dropped}, but all were filtered out as duplicates or exclusions. ` +
            "Adjust the scope in ⚙ Scope.",
          "warn"
        );
      } else {
        toast(
          "No companies matched the current scope. Loosen the filters in ⚙ Scope " +
            "(geo, size, keywords, or the funding/hiring windows).",
          "warn"
        );
      }
    } catch (e) {
      if (clientRef.current === client) {
        toast(e instanceof Error ? e.message : "Find companies failed", "warn");
      }
    } finally {
      if (clientRef.current === client) setFindingCo(false);
    }
  }

  // Re-run fit scoring for the checked companies (e.g. after the rubric / scoring prompt changed).
  // Unlike Find, this re-scores rows that already have a score — each call is a paid LLM request.
  // Async (W4): the whole batch runs on one background job (≤ SCORE_BATCH_MAX rows); a bigger
  // selection is refused with a message rather than silently split.
  function runRescore() {
    if (rescoringCoRef.current) return; // block a double-click before the button disables
    const ids = coSel.map((c) => c.id);
    if (!ids.length) return toast("Select companies to re-score", "warn");
    if (ids.length > SCORE_BATCH_MAX) {
      return toast(
        `Score at most ${SCORE_BATCH_MAX} companies at a time — narrow your selection.`,
        "warn"
      );
    }
    toast(`Scoring ${ids.length} ${ids.length === 1 ? "company" : "companies"} in the background…`);
    rescoringCoRef.current = true;
    // Clear the selection once the batch is dispatched — the rows now track progress via
    // `scoringCoIds` ("Scoring…"), and the tick-list is freed for the next batch. `ids` is already
    // captured, so the in-flight job is unaffected.
    setCompanyChecked(new Set());
    void scoreCompaniesJob(ids).finally(() => {
      rescoringCoRef.current = false;
    });
  }

  // Bucket CTA (decision ②): score the next wave of the "Needs score" bucket without ticking rows —
  // takes the first SCORE_BATCH_MAX unscored companies and scores them on one background job. The
  // operator clicks again to drain the rest (each wave is a paid LLM call, capped so no click ever
  // over-spends). Rows show "Scoring…"; scoreCompaniesJob reloads + reports on completion.
  function scoreUnscoredWave() {
    if (rescoringCoRef.current) return; // block a double-click before the button disables
    const wave = (coBuckets.get("unscored") ?? []).slice(0, SCORE_BATCH_MAX).map((c) => c.id);
    if (!wave.length) return;
    toast(
      `Scoring ${wave.length} ${wave.length === 1 ? "company" : "companies"} in the background…`
    );
    rescoringCoRef.current = true;
    void scoreCompaniesJob(wave).finally(() => {
      rescoringCoRef.current = false;
    });
  }

  // "Update Field" — re-enrich Apollo firmographics for the selected rows. Each call spends Apollo
  // credits, so it is deliberate/manual (Find Companies enriches only new rows). Async (W4),
  // capped at SCORE_BATCH_MAX rows per job.
  async function runUpdateFields() {
    if (updateFieldsCoRef.current) return; // block a double-click before the button disables (M23)
    const ids = coSel.map((c) => c.id);
    if (!ids.length) return toast("Select companies to update", "warn");
    if (ids.length > SCORE_BATCH_MAX) {
      return toast(
        `Update at most ${SCORE_BATCH_MAX} companies at a time — narrow your selection.`,
        "warn"
      );
    }
    updateFieldsCoRef.current = true;
    setUpdatingFields(true);
    try {
      const job = await runScoringJob(() => updateCompanyFieldsAsync(client, ids), "Update");
      if (clientRef.current !== client) return;
      if (job) {
        await reloadCompanies();
        const updated = Number(job.result?.updated ?? 0);
        toast(`Updated ${updated} ${updated === 1 ? "company" : "companies"}`);
      }
    } catch (e) {
      if (clientRef.current === client)
        toast(e instanceof Error ? e.message : "Update failed", "warn");
    } finally {
      updateFieldsCoRef.current = false;
      if (clientRef.current === client) setUpdatingFields(false);
    }
  }

  // Score a set of company rows on one async background job (W4). The rows show "Scoring…" until the
  // job settles; the worker owns the batch (survives a tab close), and we reload once on completion.
  // R27 — the shared background-job runner for the three scoring surfaces (score companies / reveal
  // & score people / score people). Each differs only in the "Scoring…" id set, the kick, the reload,
  // and the success toast (`onDone`) — everything else (mark scoring → poll → reload → toast → clear)
  // is identical, so it lives here once.
  async function runJob(opts: {
    ids: string[];
    setScoring: ScoringSetter;
    kick: () => Promise<ScoringJobApi>;
    label: string;
    reload: () => Promise<void>;
    onDone: (result: Record<string, unknown>) => void;
  }) {
    const { ids, setScoring, kick, label, reload, onDone } = opts;
    setScoring((prev) => new Set([...prev, ...ids]));
    try {
      const job = await runScoringJob(kick, label);
      if (clientRef.current !== client) return;
      if (job) {
        await reload();
        onDone(job.result || {});
      }
    } catch (e) {
      if (clientRef.current === client)
        toast(e instanceof Error ? e.message : `${label} failed`, "warn");
    } finally {
      if (clientRef.current === client) clearScoring(setScoring, ids);
    }
  }

  function scoreCompaniesJob(ids: string[]) {
    return runJob({
      ids,
      setScoring: setScoringCoIds,
      kick: () => rescoreCompaniesAsync(client, ids),
      label: "Scoring",
      reload: reloadCompanies,
      onDone: (r) => {
        const scored = Number(r.scored ?? 0);
        toast(`Scored ${scored} ${scored === 1 ? "company" : "companies"}`);
      },
    });
  }

  // "Find Lookalike" — find the next batch of peers of the checked rows. The seeds are the search
  // input (no Settings modal); the server aggregates their firmographics and drops every company
  // already in the list (seeds included), so `found` is the genuinely-new peers. Rows land UNSCORED
  // and stay that way (AI Score shows "Pending") — the operator scores on demand via Update AI
  // Score. The toast tells the outcomes apart: new / all-listed / none.
  async function runLookalike() {
    return runLookalikeJob("selection");
  }

  // D+ Stage 3 recovery — when the scope is exhausted, reuse the WINNERS: find lookalikes of every
  // Strong/Good row (positive-signal reuse), no manual selection needed. One click from the
  // scope-exhausted notice; hints if there are no strong rows to seed from yet.
  async function runLookalikeOfStrong() {
    return runLookalikeJob("strong");
  }

  // R27 — the shared Lookalike runner. `"selection"` seeds from the checked rows; `"strong"` (the
  // scope-exhausted recovery) seeds from every Contact-now/soon row and resets the exhausted flag.
  // The kick/reload/catch/finally boilerplate is identical; only the seeds + the exact toast copy
  // differ per mode (copy preserved verbatim).
  async function runLookalikeJob(mode: "selection" | "strong") {
    const ids = (
      mode === "strong"
        ? companies.filter((c) => c.label === "contact_now" || c.label === "contact_soon")
        : coSel
    ).map((c) => c.id);
    if (!ids.length) {
      return toast(
        mode === "strong"
          ? "No Contact-now or Contact-soon companies yet to seed lookalikes — score some rows " +
              "first, or regenerate the scope from the Business brief."
          : "Select companies to find lookalikes",
        "warn"
      );
    }
    setFindingLookalike(true);
    try {
      const job = await runScoringJob(
        () => findLookalikesAsync(client, { company_ids: ids, icp_id: fIcp || null }),
        "Lookalike search"
      );
      if (!job) return;
      await reloadCompanies();
      const found = Number(job.result?.found ?? 0);
      const dropped = Number(job.result?.dropped ?? 0);
      if (found) {
        if (mode === "strong") {
          setScopeExhausted(false); // fresh peers to review — the scope is no longer a dead end
          toast(
            `Found ${found} new lookalike ${found === 1 ? "company" : "companies"} of your ` +
              "best rows · select them and click Update AI Score to score them"
          );
        } else {
          const tail = dropped ? ` · ${dropped} already in your list` : "";
          toast(
            `Found ${found} new lookalike ${found === 1 ? "company" : "companies"}${tail} · ` +
              "select rows and click Update AI Score to score them"
          );
        }
      } else if (mode === "selection" && dropped) {
        toast(
          `Apollo returned ${dropped} similar ${dropped === 1 ? "company" : "companies"}, ` +
            `but ${dropped === 1 ? "it is" : "all are"} already in your list — nothing new to add.`,
          "warn"
        );
      } else {
        toast(
          mode === "strong"
            ? "No new lookalikes of your Strong/Good rows — regenerate the scope from the " +
                "Business brief to open up a fresh search."
            : "No companies similar to the selection were found. The seeds may be too sparse — " +
                "enrich them first (industry, size and revenue drive the match) or select more rows.",
          "warn"
        );
      }
    } catch (e) {
      if (clientRef.current === client) {
        toast(e instanceof Error ? e.message : "Lookalike search failed", "warn");
      }
    } finally {
      if (clientRef.current === client) setFindingLookalike(false);
    }
  }

  // ---- Settings (find-company scope) handlers ----
  // The modal edits ONE ICP's filters at a time (its own dropdown switches between them); each ICP's
  // tuning is persisted server-side under (tenant, "company", ICP) and shadows only that ICP's AI
  // block — so tuning one ICP never clobbers another, and the tuning follows the operator across
  // browsers. Reads/writes go through the generic scope-override endpoint.
  async function seedScopeForm(icp: string) {
    const block = await getScopeOverride(client, "company", icp || undefined).catch(() => null);
    if (clientRef.current !== client) return;
    setScopeForm(
      scopeToForm(effectiveScope(block ? (block as ScopeOverride) : null, spec, icp || undefined))
    );
  }
  function openScopeSettings() {
    // Default to the page's ICP pick (or the only/first ICP) so the form shows the scope the next
    // ICP-scoped Find would actually run.
    const icp = fIcp || icpOptions[0]?.id || "";
    setScopeIcp(icp);
    setScopeForm(null); // cleared until the server round-trip resolves (modal shows a loading state)
    void seedScopeForm(icp);
    setScopeOpen(true);
  }
  function switchScopeIcp(icp: string) {
    // Switching ICP re-seeds the form from THAT ICP's saved override / AI block (unsaved edits to
    // the previous ICP are discarded — Save first to keep them).
    setScopeIcp(icp);
    setScopeForm(null);
    void seedScopeForm(icp);
  }
  async function saveScopeSettings() {
    if (!scopeForm) return;
    const ov = formToOverride(scopeForm);
    try {
      // The server reflects what it stored: null when an all-empty form was treated as a revert to
      // the AI scope, else the saved block. Mirror it so the UI never disagrees.
      const saved = await putScopeOverride(client, "company", ov, scopeIcp || undefined);
      if (clientRef.current !== client) return;
      // The next Find should target the ICP whose filters were just saved — sync the page filter.
      // If the target ICP is unchanged, the fIcp effect won't refire, so set the page copy directly.
      if (scopeIcp && scopeIcp !== fIcp) setFIcp(scopeIcp);
      else setScopeOverride(saved ? (saved as ScopeOverride) : null);
      setScopeOpen(false);
      const label = scopeIcp ? icpNameById.get(scopeIcp) : null;
      toast(
        saved
          ? label
            ? `Search filters saved for ${label} · used on the next Find`
            : "Search filters saved · used on the next Find"
          : "No filters selected · reverted to the AI-generated scope"
      );
    } catch (e) {
      if (clientRef.current === client)
        toast(e instanceof Error ? e.message : "Couldn’t save search filters", "warn");
    }
  }
  async function resetScopeSettings() {
    try {
      await deleteScopeOverride(client, "company", scopeIcp || undefined);
      if (clientRef.current !== client) return;
      if (!scopeIcp || scopeIcp === fIcp) setScopeOverride(null);
      void seedScopeForm(scopeIcp);
      toast("Reverted to the AI-generated scope");
    } catch (e) {
      if (clientRef.current === client)
        toast(e instanceof Error ? e.message : "Couldn’t reset search filters", "warn");
    }
  }

  // Step 1 → Step 2: MERGED stage→find (decision ③). Stage the ticked companies (discovered →
  // selected) so they appear in the Step-2 table, switch to Step 2, THEN immediately find people at
  // them — chunked 8-orgs-per-call under one group_id — so sourcing people is one click, not two.
  // People land UNSCORED ("Pending"); the operator reveals + scores them via Reveal & score.
  // S20 — the shared "find people at these company ids" phase; stageForPeople and runFindPeople
  // differ only in the failure-toast copy.
  async function runPeopleFind(ids: string[], failMsg: string) {
    setFindingPpl(true);
    setFindingPplIds(new Set(ids));
    try {
      const { found, dropped } = await findPeopleFor(ids, crypto.randomUUID());
      reportFindPeople(found, dropped);
    } catch (e) {
      toast(e instanceof Error ? e.message : failMsg, "warn");
    } finally {
      setFindingPpl(false);
      setFindingPplIds(new Set());
    }
  }

  async function stageForPeople() {
    // Drop any `excluded_by_rules` row before staging — the LOCKED invariant (an excluded company is
    // never staged into Step 2 / never has people found at it). Mirrors `runFindPeople`; belt-and-
    // braces with the prune effect, which is async and can lag a just-landed exclusion label.
    const ids = coSel.filter((c) => c.label !== "excluded_by_rules").map((c) => c.id);
    if (!ids.length) return;
    setStaging(true);
    try {
      await selectCompanies(client, ids, true);
      await reloadCompanies();
      setListStage("people");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn’t move companies to Step 2", "warn");
      setStaging(false);
      return;
    }
    setStaging(false);
    // The find is a second phase: if staging succeeded but the find fails, the rows are already in
    // Step 2 (re-runnable via the Find People button) — so surface the find error without undoing.
    await runPeopleFind(ids, "Find people failed — retry with Find People");
  }

  // Step 2 → Step 1: remove the ticked companies from Step 2 (selected | people_found → discovered),
  // so an Accepted company can be taken back out of the pursuit. The rows leave the Step-2 table and
  // reappear in the Step-1 list; their checks are cleared.
  async function removeFromStep2() {
    const ids = pplCoSel.map((c) => c.id);
    if (!ids.length) return;
    setRemoving(true);
    try {
      await selectCompanies(client, ids, false);
      await reloadCompanies();
      const removed = new Set(ids);
      setCompanyChecked((s) => {
        const n = new Set(s);
        ids.forEach((id) => n.delete(id));
        return n;
      });
      // N12 — also drop any ticked PEOPLE under the removed companies. They leave Step 2 with their
      // parent, so leaving them in `checked` keeps invisible selected rows that a later reveal spends.
      setChecked((s) => {
        const n = new Set(s);
        prospects.forEach((p) => {
          if (p.company_id && removed.has(p.company_id)) n.delete(p.id);
        });
        return n;
      });
      toast(`Removed ${ids.length} ${ids.length === 1 ? "company" : "companies"} from Step 2`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn’t remove companies", "warn");
    } finally {
      setRemoving(false);
    }
  }

  // Flow B core — find people across `ids` (free; enrichment is the credit spend). Chunks the ids
  // into MAX_ORGS_PER_FIND-sized calls (server cap) under ONE `groupId` so the history drawer threads
  // them as a single find. The saved override is NOT sent in the body: the server reads it from the
  // DB (the single source of truth), so a stale in-memory copy in one tab can't shadow a save/reset
  // in another. People land UNSCORED ("Pending") — the operator reveals + scores via Reveal & score.
  // Returns totals; the CALLER owns the toast + the finding flags.
  async function findPeopleFor(ids: string[], groupId: string) {
    let found = 0;
    let dropped = 0;
    try {
      for (let i = 0; i < ids.length; i += FIND_ORGS_CHUNK) {
        const res = await findPeople(client, {
          company_ids: ids.slice(i, i + FIND_ORGS_CHUNK),
          icp_id: fIcp || null,
          group_id: groupId,
        });
        found += res.found;
        dropped += res.dropped;
      }
    } finally {
      // R29c — reload even if a chunk failed: earlier chunks may have landed people, so a partial
      // run must still refresh the list instead of leaving it stale. The error (if any) re-propagates
      // to the caller AFTER this runs.
      await Promise.all([reloadProspects(), reloadCompanies()]);
    }
    return { found, dropped };
  }
  // Report the outcome of a people-find (shared by the merged stage→find and the manual re-run).
  function reportFindPeople(found: number, dropped: number) {
    if (found) {
      const tail = dropped ? ` · ${dropped} filtered out` : "";
      toast(
        `Found ${found} ${found === 1 ? "person" : "people"}${tail} · ` +
          "select them and click Reveal & score to reveal their emails and score them"
      );
    } else if (dropped) {
      toast(
        `Apollo returned ${dropped}, but all were filtered out (already imported, no Apollo id, ` +
          "or an avoided title). Adjust the personas in ⚙ Personas.",
        "warn"
      );
    } else {
      toast(
        "No people matched — even after widening. Pick different Management Level / Department " +
          "facets in ⚙ Personas (the live counts show where people actually are).",
        "warn"
      );
    }
  }
  // Manual re-run: find people at the ticked Step-2 companies. `runFindPeople` re-searches by
  // explicit id, so a row can be re-searched after loosening the personas.
  async function runFindPeople() {
    // R6 — a staged-then-excluded company may be ticked (to Remove it), but must never be sent to
    // find-people: drop excluded from the funnel-advancing target.
    const ids = pplCoSel.filter((c) => c.label !== "excluded_by_rules").map((c) => c.id);
    if (!ids.length) return toast("Select companies in the list to find people", "warn");
    await runPeopleFind(ids, "Find people failed");
  }

  // Step-2 'Reveal & score' — the merged people action (W4, per-row "Scoring…"). Reveals verified
  // emails for the selected people (Apollo people/match, the credit spend) THEN scores them on the
  // revealed data, in ONE background job. Reveal-first is the point: scoring a pre-reveal row gates on
  // missing contact/seniority/dept → a degraded label. Enrich is idempotent, so a selection that's
  // already revealed just re-scores (0 credits). Capped at SCORE_BATCH_MAX (a bigger selection is
  // refused, not split). `toEnrich.length` = the rows that will actually spend a credit.
  function runRevealScore() {
    if (rescoringPplRef.current) return; // block a double-click before the button disables
    const picked = selectedProspects;
    if (!picked.length) return toast("Select people to reveal & score", "warn");
    if (picked.length > SCORE_BATCH_MAX) {
      return toast(
        `Reveal & score at most ${SCORE_BATCH_MAX} people at a time — narrow your selection.`,
        "warn"
      );
    }
    const spend = toEnrich.length;
    const noun = picked.length === 1 ? "person" : "people";
    toast(
      spend
        ? `Revealing emails + scoring ${picked.length} ${noun} in the background · ${spend} credit${
            spend === 1 ? "" : "s"
          }…`
        : `Scoring ${picked.length} ${noun} in the background…`
    );
    rescoringPplRef.current = true;
    // Clear the selection once dispatched — rows track progress via `scoringPersonIds`; `picked` is
    // already captured so the in-flight job is unaffected. Frees the tick-list for the next batch.
    setChecked(new Set());
    void revealScoreJob(picked.map((p) => ({ id: p.id, key: p.identity_key }))).finally(() => {
      rescoringPplRef.current = false;
    });
  }

  // Reveal + score a set of people on one async background job (W4). Rows show "Scoring…" until it
  // settles; the worker owns the batch (survives a tab close), and we reload once on completion.
  function revealScoreJob(rows: { id: string; key: string }[]) {
    return runJob({
      ids: rows.map((r) => r.id),
      setScoring: setScoringPersonIds,
      kick: () =>
        enrichScoreProspectsAsync(
          client,
          rows.map((r) => r.key)
        ),
      label: "Reveal & score",
      reload: reloadProspects,
      onDone: (result) => {
        const enriched = Number(result.enriched ?? 0);
        const credits = Number(result.credits_spent ?? 0);
        const scored = Number(result.scored ?? 0);
        const failed = Number(result.failed ?? 0) + Number(result.enrich_failed ?? 0);
        const failTail = failed ? ` · ${failed} failed` : "";
        toast(
          enriched
            ? `Revealed ${enriched} · scored ${scored} · ${credits} credit${
                credits === 1 ? "" : "s"
              }${failTail}`
            : `Scored ${scored}${failTail}`,
          failed ? "warn" : undefined
        );
      },
    });
  }

  // Score a set of people on one async background job (W4). Rows show "Scoring…" until it settles;
  // the worker owns the batch (survives a tab close), and we reload once on completion.
  function scorePeopleJob(rows: { id: string; key: string }[]) {
    return runJob({
      ids: rows.map((r) => r.id),
      setScoring: setScoringPersonIds,
      kick: () =>
        rescoreProspectsAsync(
          client,
          rows.map((r) => r.key)
        ),
      label: "Scoring",
      reload: reloadProspects,
      onDone: (r) => {
        const scored = Number(r.scored ?? 0);
        toast(`Scored ${scored} ${scored === 1 ? "person" : "people"}`);
      },
    });
  }

  // ---- Step-2 Settings (find-people scope) handlers ----
  // Load the live facet counts for the currently-ticked Step-2 companies (free, 0 credits). Skipped
  // when nothing is ticked — management level still renders from the static list, departments need
  // the probe. Guarded against a client switch landing the result on the wrong workspace.
  async function loadPeopleFacets() {
    const ids = pplCoSel.map((c) => c.id);
    if (!ids.length) {
      setPplFacets(null);
      return;
    }
    setPplFacetsLoading(true);
    try {
      const f = await peopleFacets(client, ids);
      if (clientRef.current === client) setPplFacets(f);
    } catch {
      if (clientRef.current === client) setPplFacets(null);
    } finally {
      if (clientRef.current === client) setPplFacetsLoading(false);
    }
  }
  async function openPeopleScopeSettings() {
    // Re-fetch the saved override fresh so the modal always seeds from the true server state for the
    // selected ICP — this is also the retry path if the background load failed. Fall back to the
    // in-memory copy on error rather than blocking the operator.
    let ov = peopleScopeOverride;
    try {
      const b = await getPeopleScopeOverride(client, fIcp || undefined);
      if (clientRef.current !== client) return;
      ov = b ? { people_search_params: b } : null;
      setPeopleScopeOverride(ov);
    } catch {
      /* keep the in-memory copy; still open the modal so a load blip never locks the operator out */
    }
    setPeopleScopeForm(peopleScopeToForm(effectivePeopleScope(ov, spec, fIcp || undefined)));
    setPplFacets(null);
    setPeopleScopeOpen(true);
    void loadPeopleFacets();
  }
  // Toggle one facet value in/out of a form facet array (immutable).
  function toggleFacet(key: "seniorities" | "departments", value: string) {
    setPeopleScopeForm((f) => {
      if (!f) return f;
      const has = f[key].includes(value);
      return { ...f, [key]: has ? f[key].filter((v) => v !== value) : [...f[key], value] };
    });
  }
  const [savingPplScope, setSavingPplScope] = useState(false);
  async function savePeopleScopeSettings() {
    if (!peopleScopeForm || savingPplScope) return;
    const ov = formToPeopleOverride(peopleScopeForm);
    setSavingPplScope(true);
    try {
      // The server reflects what it stored: null when an all-empty selection was treated as a revert
      // to the AI scope, else the saved params. Mirror that exactly so the UI never disagrees.
      const saved = await putPeopleScopeOverride(
        client,
        ov.people_search_params,
        fIcp || undefined
      );
      if (clientRef.current !== client) return; // client switched mid-save — drop the stale write
      setPeopleScopeOverride(saved ? { people_search_params: saved } : null);
      setPeopleScopeOpen(false);
      const label = fIcp ? icpNameById.get(fIcp) : null;
      toast(
        saved
          ? label
            ? `Person filters saved for ${label} · used on the next Find People`
            : "Person filters saved · used on the next Find People"
          : "No filters selected · reverted to the AI-generated person scope"
      );
    } catch (e) {
      if (clientRef.current === client)
        toast(e instanceof Error ? e.message : "Couldn’t save person filters", "warn");
    } finally {
      setSavingPplScope(false);
    }
  }
  async function resetPeopleScopeSettings() {
    if (savingPplScope) return;
    setSavingPplScope(true);
    try {
      await deletePeopleScopeOverride(client, fIcp || undefined);
      if (clientRef.current !== client) return; // client switched mid-reset — drop the stale write
      setPeopleScopeOverride(null);
      setPeopleScopeForm(peopleScopeToForm(effectivePeopleScope(null, spec, fIcp || undefined)));
      toast("Reverted to the AI-generated person scope");
    } catch (e) {
      if (clientRef.current === client)
        toast(e instanceof Error ? e.message : "Couldn’t reset person filters", "warn");
    } finally {
      setSavingPplScope(false);
    }
  }

  // ---- Stage 2: people ----
  async function submitAddPerson() {
    if (
      !personForm.full_name.trim() &&
      !personForm.email.trim() &&
      !personForm.linkedin_url.trim()
    ) {
      return toast("Add a name + company domain, a LinkedIn URL, or an email", "warn");
    }
    setSavingPerson(true);
    try {
      const p = await addProspect(client, { ...personForm, icp_id: fIcp || null });
      toast(`Added ${personForm.full_name || personForm.email} · scoring…`);
      setAddPersonOpen(false);
      setPersonForm({ ...blankPerson });
      await Promise.all([reloadProspects(), reloadCompanies()]);
      // Lands UNSCORED (scoring off the request path) — background-score it like a found row.
      void scorePeopleJob([{ id: p.id, key: p.identity_key }]);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Add failed", "warn");
    } finally {
      setSavingPerson(false);
    }
  }

  // Open the Fit-rubric modal and fetch the real fit-score prompt for one sample company (the first
  // ticked row, else the first in view) — the backend builds it from this client's brief + research
  // spec + ICP docs, so the Input-prompt pane shows exactly what reaches the model.
  async function openRubric() {
    // Step-2 tab → the people rubric; Step-1 tab → the company rubric. The modal's body, preview,
    // and badges all key off this stage.
    const stage: FitStage = listStage === "people" ? "prospect_fit" : "company_fit";
    setRubricStage(stage);
    setRubricDraft(
      (stage === "prospect_fit" ? docs?.prospect_fit?.body : docs?.company_fit?.body) ?? ""
    );
    setShowSourcing(true);
    setFitPrompt(null);
    setFitPromptErr(null);
    setFitPromptLoading(true);
    try {
      const sampleId = stage === "prospect_fit" ? prospectSample?.id : rubricSample?.id;
      const fp = await getFitPrompt(client, stage, sampleId);
      setFitPrompt(fp);
    } catch (e) {
      setFitPromptErr(e instanceof Error ? e.message : "Could not load the input prompt");
    } finally {
      setFitPromptLoading(false);
    }
  }

  // Save the founder's edit as the next version of the fit rubric (append-only vN+1).
  async function saveDoc(stage: FitStage) {
    const body = rubricDraft.trim();
    if (!body) return toast("Nothing to save", "warn");
    setSavingDoc(stage);
    try {
      await saveSourcingDoc(client, stage, body);
      const dl = await getSourcingDocs(client);
      setDocs(dl);
      qc.setQueryData(["sourcing-docs", client], dl); // sync the nav cache
      const v = stage === "prospect_fit" ? dl.prospect_fit?.version : dl.company_fit?.version;
      toast(`Saved ${stage === "prospect_fit" ? "prospect" : "company"} fit rubric v${v}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Save failed", "warn");
    } finally {
      setSavingDoc(null);
    }
  }

  async function createBatch() {
    if (creatingBatchRef.current) return; // L13 — block a double-click before the button disables
    // Only enriched people can be batched — enforce enrich-before-batch (the dock already gates
    // the button; re-check here so a stale click can't slip unenriched rows through).
    const picked = enrichedSel;
    if (!picked.length) {
      return toast("Select enriched people — enrich the Found ones first", "warn");
    }
    const name = newBatchName.trim();
    // Pass the shared ICP when the whole selection agrees; else the server leaves it unset.
    const icpIds = new Set(picked.map((p) => p.icp_id).filter(Boolean));
    const icp_id = icpIds.size === 1 ? ([...icpIds][0] as string) : undefined;
    creatingBatchRef.current = true;
    setCreatingBatch(true);
    try {
      const b = await apiCreateBatch(client, {
        prospect_ids: picked.map((p) => p.id),
        ...(name ? { name } : {}),
        ...(icp_id ? { icp_id } : {}),
      });
      await reloadBatches();
      setNewBatchName("");
      setChecked(new Set());
      toast(`${b.name} created with ${b.total} prospects, pending client approval`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Create batch failed", "warn");
    } finally {
      creatingBatchRef.current = false;
      setCreatingBatch(false);
    }
  }

  return (
    <section className="tabpane list-pane active">
      <div className="panel">
        <div className="panel-head">
          <div className="tabs">
            <button
              className={clsx("tab", listStage === "companies" && "active")}
              onClick={() => setListStage("companies")}
            >
              <span className="tab-num">Step 1</span> Companies{" "}
              <span className="tab-ct">({companies.length})</span>
            </button>
            <span className="tab-chev" aria-hidden="true">
              →
            </span>
            <button
              className={clsx("tab", listStage === "people" && "active")}
              onClick={() => setListStage("people")}
            >
              <span className="tab-num">Step 2</span> People{" "}
              <span className="tab-ct">({step2PeopleCount})</span>
            </button>
          </div>
          <div className="head-actions">
            <button
              className="btn btn-ghost btn-sm"
              onClick={openRubric}
              title="Edit the versioned AI scoring rubric that Get AI score runs against"
            >
              Edit scoring rubric
            </button>
          </div>
        </div>

        {listStage === "companies" ? (
          <Step1Companies
            setFindHistoryOpen={setFindHistoryOpen}
            openScopeSettings={openScopeSettings}
            scopeOverride={scopeOverride}
            runFindCompanies={runFindCompanies}
            coMutating={coMutating}
            findingCo={findingCo}
            coTargetIcpName={coTargetIcpName}
            coSelCount={coSelCount}
            runRescore={runRescore}
            scoringActive={scoringActive}
            findingPpl={findingPpl}
            runLookalike={runLookalike}
            findingLookalike={findingLookalike}
            runUpdateFields={runUpdateFields}
            updatingFields={updatingFields}
            setCompanyChecked={setCompanyChecked}
            scopeExhausted={scopeExhausted}
            runLookalikeOfStrong={runLookalikeOfStrong}
            setScopeExhausted={setScopeExhausted}
            coSearch={coSearch}
            setCoSearch={setCoSearch}
            icpOptions={icpOptions}
            fIcp={fIcp}
            setFIcp={setFIcp}
            icpNeedsPick={icpNeedsPick}
            coStatus={coStatus}
            setCoStatus={setCoStatus}
            setAddCoOpen={setAddCoOpen}
            coVisible={coVisible}
            coBusy={coBusy}
            coBuckets={coBuckets}
            expandedBuckets={expandedBuckets}
            toggleBucket={toggleBucket}
            scoreUnscoredWave={scoreUnscoredWave}
            coScopeSummary={coScopeSummary}
            stageForPeople={stageForPeople}
            staging={staging}
            icpNameById={icpNameById}
            companyChecked={companyChecked}
            toggleCo={toggleCo}
            scoringCoIds={scoringCoIds}
            expandedSubs={expandedSubs}
            toggleSub={toggleSub}
          />
        ) : (
          <Step2People
            peopleScopeOverride={peopleScopeOverride}
            openPeopleScopeSettings={openPeopleScopeSettings}
            coTargetIcpName={coTargetIcpName}
            runFindPeople={runFindPeople}
            findingPpl={findingPpl}
            pplCoSel={pplCoSel}
            removeFromStep2={removeFromStep2}
            removing={removing}
            search={search}
            setSearch={setSearch}
            icpOptions={icpOptions}
            fIcp={fIcp}
            setFIcp={setFIcp}
            fStatus={fStatus}
            setFStatus={setFStatus}
            setAddPersonOpen={setAddPersonOpen}
            pursued={pursued}
            visible={visible}
            selectedProspects={selectedProspects}
            pplBusy={pplBusy}
            rowsForCompany={rowsForCompany}
            findingPplIds={findingPplIds}
            companyChecked={companyChecked}
            toggleCo={toggleCo}
            icpNameById={icpNameById}
            checked={checked}
            scoringPersonIds={scoringPersonIds}
            toggleRow={toggleRow}
            prospectsLoading={prospectsLoading}
            companiesLoading={companiesLoading}
            pplScopeSummary={pplScopeSummary}
            setChecked={setChecked}
            toEnrich={toEnrich}
            runRevealScore={runRevealScore}
            scoringPeopleActive={scoringPeopleActive}
            canBatch={canBatch}
            newBatchName={newBatchName}
            setNewBatchName={setNewBatchName}
            createBatch={createBatch}
            creatingBatch={creatingBatch}
          />
        )}
      </div>

      <RubricModal
        showSourcing={showSourcing}
        setShowSourcing={setShowSourcing}
        rubricStage={rubricStage}
        saveDoc={saveDoc}
        savingDoc={savingDoc}
        rubricDraft={rubricDraft}
        setRubricDraft={setRubricDraft}
        fitPrompt={fitPrompt}
        docs={docs}
        fitPromptLoading={fitPromptLoading}
        fitPromptErr={fitPromptErr}
      />

      <ScopeSettingsModal
        scopeOpen={scopeOpen}
        setScopeOpen={setScopeOpen}
        resetScopeSettings={resetScopeSettings}
        saveScopeSettings={saveScopeSettings}
        scopeForm={scopeForm}
        setScopeForm={setScopeForm}
        icpOptions={icpOptions}
        scopeIcp={scopeIcp}
        switchScopeIcp={switchScopeIcp}
      />

      <PeopleScopeModal
        peopleScopeOpen={peopleScopeOpen}
        setPeopleScopeOpen={setPeopleScopeOpen}
        resetPeopleScopeSettings={resetPeopleScopeSettings}
        savingPplScope={savingPplScope}
        savePeopleScopeSettings={savePeopleScopeSettings}
        peopleScopeForm={peopleScopeForm}
        peopleScopeOverride={peopleScopeOverride}
        pplFacets={pplFacets}
        pplFacetsLoading={pplFacetsLoading}
        pplCoSel={pplCoSel}
        toggleFacet={toggleFacet}
        masterDepts={masterDepts}
      />

      <AddCompanyModal
        addCoOpen={addCoOpen}
        setAddCoOpen={setAddCoOpen}
        submitAddCompany={submitAddCompany}
        savingCo={savingCo}
        coForm={coForm}
        setCoForm={setCoForm}
      />

      <AddPersonModal
        addPersonOpen={addPersonOpen}
        setAddPersonOpen={setAddPersonOpen}
        submitAddPerson={submitAddPerson}
        savingPerson={savingPerson}
        personForm={personForm}
        setPersonForm={setPersonForm}
        step2Companies={step2Companies}
      />

      {findHistoryOpen ? (
        <FindHistoryDrawer
          onClose={() => setFindHistoryOpen(false)}
          client={client}
          icpNameById={icpNameById}
        />
      ) : null}
    </section>
  );
}
