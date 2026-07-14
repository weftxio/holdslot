"use client";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useClient } from "@/lib/nav";
import { toggleInSet } from "@/lib/sets";
import clsx from "clsx";
import { Modal } from "@/components/Modal";
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
  type ResearchSpecResult,
  type SourcingDocList,
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
  getPeopleDepartments,
  getPeopleScopeOverride,
  getResearchSpec,
  getScopeOverride,
  getSourcingDocs,
  listCompanies,
  listIcps,
  listProspects,
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
import type { ScoreLabel, ScoringJobApi, Subscores } from "@/lib/api";
import type {
  Icp,
  PeopleScopeForm,
  PeopleScopeOverride,
  ScopeForm,
  ScopeOverride,
  ScoringSetter,
} from "@/lib/workspace/types";
import {
  BUCKET_HEAD,
  BUCKET_ORDER,
  COLLAPSED_LABELS,
  COMPANY_AXES,
  ENRICHED_STATUS,
  PROSPECT_AXES,
  SENIORITY_OPTIONS,
  SOURCE_CLS,
  SOURCE_LABEL,
  STATUS_LABEL,
  apiToIcp,
  businessModelChip,
  clearScoring,
  compareByLabel,
  effectivePeopleScope,
  effectiveScope,
  formToOverride,
  formToPeopleOverride,
  groupByLabel,
  humanizeFacet,
  peopleScopeSummary,
  peopleScopeToForm,
  scopeSummary,
  scopeToForm,
} from "@/lib/workspace/constants";
import {
  CompanyStudy,
  ConfirmFooter,
  LabelChip,
  LinkedInLink,
  PromptEditorShell,
  SpecHead,
  SubscoreList,
  WebLink,
} from "@/components/workspace";

// The two collapsed footnote buckets as a plain string set — COLLAPSED_LABELS is typed to
// ScoreLabel, but the bucket keys include the "unscored" (null-label) group, so membership is
// tested against strings.
const COLLAPSED_KEYS = new Set<string>(COLLAPSED_LABELS);
// Override gate (spec §11 / decision ④): an `excluded_by_rules` row is locked out of any selection;
// A selection verdict for a toggle: "ok" apply now · "blocked" locked out (an excluded row in Step 1)
// · "confirm" a low_fit ADD, challenged via the design-system Modal (M31 — was a `window.confirm`).
// Deselecting is always "ok"; only *adding* a gated row is challenged/blocked.
function maySelect(
  label: ScoreLabel | null,
  currentlyChecked: boolean,
  allowExcluded = false
): "ok" | "blocked" | "confirm" {
  if (currentlyChecked) return "ok"; // unticking is ALWAYS allowed (tick-to-remove in Step 2, R6)
  // Step 2 passes allowExcluded so a staged-then-excluded company can be TICKED for removal; the
  // funnel-advancing handlers (stageForPeople / runFindPeople / reveal) each filter excluded rows out
  // themselves, and the prune effect drops them from the selection after any reload/scoring wave.
  if (label === "excluded_by_rules") return allowExcluded ? "ok" : "blocked";
  if (label === "low_fit") return "confirm";
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
// The row carries a non-empty subscore vector (a scored row) → render the 4-segment bar.
const hasSubs = (s: Record<string, number> | undefined) => !!s && Object.keys(s).length > 0;
// The Step-1 company / Step-2 person score cell — one of three states: fit-scoring in progress, a
// resolved label (chip + subscores, plus an optional grey reason line the company table shows for
// non-contact buckets), or Pending. Extracted (S18) so both tables emit byte-identical markup.
function FitCell({
  scoring,
  label,
  score,
  subscores,
  axes,
  reason,
}: {
  scoring: boolean;
  label: ScoreLabel | null;
  score: number | null;
  subscores: Subscores;
  axes: readonly string[];
  reason?: string | null;
}) {
  if (scoring)
    return (
      <span className="fit-scoring" title="AI fit-scoring in progress">
        <span className="hs-spinner" aria-hidden="true" />
        Scoring…
      </span>
    );
  if (!label) return <span className="muted">Pending</span>;
  return (
    <div className="ai-score-cell">
      <span className="label-line">
        <LabelChip label={label} score={score} />
      </span>
      {hasSubs(subscores) ? <SubscoreList subscores={subscores} axes={axes} /> : null}
      {reason ? (
        <span className="score-reason" title={reason}>
          {reason}
        </span>
      ) : null}
    </div>
  );
}
// The "Fetching…" spinner overlaid on a list body while a fetch is in flight (Step-1 + Step-2,
// S18) — renders nothing when idle so the caller can drop it in unconditionally.
function ListOverlay({ busy }: { busy: boolean }) {
  if (!busy) return null;
  return (
    <div className="list-overlay" role="status" aria-live="polite">
      <span className="hs-spinner" aria-hidden="true" />
      <span>Fetching…</span>
    </div>
  );
}
// One checkbox row in the Personas facet sidebar (seniority + departments, probed or not, S19) —
// label + optional live count. `key` stays on the call site, per the .map contract.
function FacetRow({
  label,
  checked,
  count,
  onToggle,
}: {
  label: string;
  checked: boolean;
  count?: number;
  onToggle: () => void;
}) {
  return (
    <label className="facet-row">
      <input type="checkbox" className="tbl-check" checked={checked} onChange={onToggle} />
      <span className="facet-label">{label}</span>
      {count != null && <span className="facet-count">{count}</span>}
    </label>
  );
}
// The by-ICP list filter above Step-1 and Step-2 (S19) — identical bar the title and the Step-1
// "pick an ICP" warn-highlight. Renders nothing when there's ≤1 ICP (nothing to filter by).
function IcpFilterSelect({
  options,
  value,
  onChange,
  title,
  highlight,
}: {
  options: { id: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  title: string;
  highlight?: boolean;
}) {
  if (options.length <= 1) return null;
  return (
    <select
      className="select"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      title={title}
      style={
        highlight
          ? {
              borderColor: "var(--warn)",
              boxShadow: "0 0 0 3px var(--warn-wash)",
              transition: "box-shadow 0.2s",
            }
          : undefined
      }
    >
      <option value="">All ICPs</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
// A labelled text/number input in the scope / add-company / add-person modals (S4) — the
// `div.field > label + input.input` block repeated 17× with only label/value/placeholder/type
// varying. `onChange` receives the raw string value.
function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: "text" | "number";
  placeholder?: string;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      <input
        className="input"
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
// The badge pair atop the add-company / add-person modals (S21 — was duplicated inline in both).
function ManualBadges() {
  return (
    <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
      <span className="badge badge-neutral">source · manual</span>
      <span className="badge badge-info">fit-scored on add</span>
    </div>
  );
}
// Find People searches one Apollo call per org; the server caps a single request at MAX_ORGS_PER_FIND
// (8) orgs, so the FE chunks a larger selection into 8-org calls threaded by one group_id.
const FIND_ORGS_CHUNK = 8;

// A footnote bucket (low_fit / excluded_by_rules) is sub-grouped by WHY each row landed there, so
// the operator can scan the rejection reasons at a glance (spec §9). A gate-killed row carries a
// canonical reason string ("wrong vertical", "too large", "rule: B2B only", …); a low_fit row that
// was actually SCORED low (a real score_total, free-text reason) has no canonical tag, so all such
// rows fold into one "Low score" group instead of fragmenting into one-off reasons.
function prettyReason(reason: string): string {
  const s = (reason || "")
    .trim()
    .replace(/^rule:\s*/i, "")
    .replace(/_/g, " ");
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}
type SubGroup = { key: string; label: string; rows: CompanyApi[] };
function subGroupsOf(rows: CompanyApi[]): SubGroup[] {
  const groups = new Map<string, SubGroup>();
  for (const c of rows) {
    const scoredLow = c.label === "low_fit" && c.score_total != null;
    const key = scoredLow ? "__scored_low" : (c.reason || "").trim().toLowerCase() || "__other";
    const label = scoredLow ? "Low score" : prettyReason(c.reason) || "Other";
    const g = groups.get(key);
    if (g) g.rows.push(c);
    else groups.set(key, { key, label, rows: [c] });
  }
  // Biggest group first — the most common rejection reason is what the operator most wants to see.
  return [...groups.values()].sort((a, b) => b.rows.length - a.rows.length);
}

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

  // ICPs + research spec — loaded locally on mount: icpNameById/the fIcp filter/ICP labels need
  // `icps`, and the scope-override `effectiveScope` needs `spec`. Additive to the list load below.
  const [icps, setIcps] = useState<Icp[]>(() => {
    const cached = qc.getQueryData<Awaited<ReturnType<typeof listIcps>>>(["icps", client]);
    return cached ? cached.map(apiToIcp) : [];
  });
  const [spec, setSpec] = useState<ResearchSpecResult | null>(() => {
    const cached = qc.getQueryData<Awaited<ReturnType<typeof getResearchSpec>>>([
      "research-spec",
      client,
    ]);
    return cached?.latest ?? null;
  });
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
  // Prospect list (Phase C — live). Prospects, sourcing docs, and the round-history scoreboard
  // are loaded from the API; selection is by prospect id. Batch creation stays client-side until
  // Phase D builds the backend (the select → batch seam is real; the batch object is the mock).
  const [prospects, setProspects] = useState<ProspectApi[]>(
    () => qc.getQueryData<{ items: ProspectApi[] }>(["prospects", client])?.items ?? []
  );
  const [prospectsLoading, setProspectsLoading] = useState(
    () => !qc.getQueryData(["prospects", client])
  );
  const [companiesLoading, setCompaniesLoading] = useState(
    () => !qc.getQueryData(["companies", client])
  );
  // Tracks the live client so an async reload/handler that resolves *after* a client switch can
  // bail before writing the previous client's data into the new client's view.
  const clientRef = useRef(client);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [fStatus, setFStatus] = useState(""); // "" all · "found" · "scored" (Enriched)
  const [fIcp, setFIcp] = useState(""); // an ICP id (or "")
  const [newBatchName, setNewBatchName] = useState("");
  // Fit-rubric settings (the versioned scoring rubric), edited in a modal.
  const [showSourcing, setShowSourcing] = useState(false);
  const [docs, setDocs] = useState<SourcingDocList | null>(null);
  const [rubricDraft, setRubricDraft] = useState("");
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
  const [companies, setCompanies] = useState<CompanyApi[]>(
    () => qc.getQueryData<{ items: CompanyApi[] }>(["companies", client])?.items ?? []
  );
  const [companyChecked, setCompanyChecked] = useState<Set<string>>(new Set());
  // Companies whose prospect rows are EXPANDED in the Step-2 list (company id). Default: not in the
  // set → collapsed, so the list opens with every company collapsed to its one-line summary.
  const [expandedCos, setExpandedCos] = useState<Set<string>>(new Set());
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
  // M31 — a low_fit ADD is confirmed via a design-system Modal (not window.confirm); this holds the
  // toggle to apply if the operator confirms.
  const [lowFitPrompt, setLowFitPrompt] = useState<{ apply: () => void } | null>(null);
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
  const [coForm, setCoForm] = useState({ ...blankCo });
  const [savingCo, setSavingCo] = useState(false);
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
  const [masterDepts, setMasterDepts] = useState<FacetOption[]>([]); // 14 masters, from the backend
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
  const [personForm, setPersonForm] = useState({ ...blankPerson });
  const [savingPerson, setSavingPerson] = useState(false);

  async function reloadProspects() {
    setProspectsLoading(true);
    try {
      // Let errors propagate — a failed reload must surface, never silently blank the list
      // (which reads as "no prospects" and tempts a re-import / re-spend).
      const { items: ps } = await listProspects(client);
      if (clientRef.current !== client) return; // client switched mid-flight — drop stale data
      setProspects(ps);
      // N11 — do NOT wipe the people selection on every reload (a Reveal & score reload blew away
      // the operator's ticks). The prune effect drops only now-excluded ids; ghost ids for removed
      // rows are harmless (selectedProspects filters against the live list). Mirrors reloadCompanies.
      qc.setQueryData(["prospects", client], { items: ps }); // keep the nav cache fresh
    } catch (e) {
      if (clientRef.current === client) {
        toast(e instanceof Error ? e.message : "Couldn’t refresh prospects", "warn");
      }
    } finally {
      if (clientRef.current === client) setProspectsLoading(false);
    }
  }

  async function reloadCompanies() {
    setCompaniesLoading(true);
    try {
      const { items: cs } = await listCompanies(client);
      if (clientRef.current !== client) return;
      setCompanies(cs);
      qc.setQueryData(["companies", client], { items: cs }); // keep the nav cache fresh
    } catch (e) {
      if (clientRef.current === client) {
        toast(e instanceof Error ? e.message : "Couldn’t refresh companies", "warn");
      }
    } finally {
      if (clientRef.current === client) setCompaniesLoading(false);
    }
  }

  // Hydrate companies, the prospect list, and sourcing docs for this client. Selection and
  // filters are reset here — they reference the *previous* client's prospect/ICP ids and would
  // otherwise leak across a switch (a stale fIcp silently hides the new client's rows; stale
  // checked ids feed accept/createBatch). Load errors surface as a toast and never blank the
  // list silently (that reads as "no prospects" and tempts a re-import / re-spend).
  // ICPs + the latest research spec are also loaded here (additive): the list owns its own copy
  // since the brief route no longer renders alongside it. The synchronous setState calls below
  // intentionally reset per-client UI state on a client switch (the App Router can't remount this
  // page on the [client] param), then kick the cached load — hence the scoped disable.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!client) return;
    clientRef.current = client;
    setChecked(new Set());
    setCompanyChecked(new Set());
    // Clear any in-flight "Scoring…" flags from the previous client (the background loop bails on the
    // client switch, but its safety-net clear is gated on the old client — these would otherwise leak).
    setScoringCoIds(new Set());
    setScoringPersonIds(new Set());
    rescoringCoRef.current = false;
    rescoringPplRef.current = false;
    updateFieldsCoRef.current = false;
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
    let alive = true;
    // Show the list spinner only when there's nothing cached for this client; a warm tab-return
    // renders the cached rows immediately (the fetchQuery calls below resolve from cache, no request).
    setCompaniesLoading(!qc.getQueryData(["companies", client]));
    setProspectsLoading(!qc.getQueryData(["prospects", client]));
    // The saved people-scope override is loaded on its own (client, fIcp) track below (per-ICP), so
    // it's not fetched here.
    (async () => {
      try {
        // fetchQuery serves the cached payload when fresh (instant, no request) and refetches in the
        // background when stale; the cache lives above the routes, so this is what frees a tab-switch
        // from a full reload. The lists' free DB reads are safe to background-revalidate (no credits).
        const [ps, cs, dl, depts, ics, rs] = await Promise.all([
          qc.fetchQuery({ queryKey: ["prospects", client], queryFn: () => listProspects(client) }),
          qc.fetchQuery({ queryKey: ["companies", client], queryFn: () => listCompanies(client) }),
          qc.fetchQuery({
            queryKey: ["sourcing-docs", client],
            queryFn: () => getSourcingDocs(client),
          }),
          qc
            .fetchQuery({
              queryKey: ["people-departments", client],
              queryFn: () => getPeopleDepartments(client),
            })
            .catch(() => [] as FacetOption[]), // non-fatal: subs-only view
          qc
            .fetchQuery({ queryKey: ["icps", client], queryFn: () => listIcps(client) })
            .catch(() => null),
          qc
            .fetchQuery({
              queryKey: ["research-spec", client],
              queryFn: () => getResearchSpec(client),
            })
            .catch(() => null),
        ]);
        if (!alive) return;
        setProspects(ps.items);
        setCompanies(cs.items);
        setDocs(dl);
        setRubricDraft(dl?.company_fit?.body ?? "");
        setMasterDepts(depts);
        if (ics) setIcps(ics.map(apiToIcp));
        if (rs) setSpec(rs.latest);
      } catch (e) {
        if (alive) toast(e instanceof Error ? e.message : "Couldn’t load prospects", "warn");
      } finally {
        if (alive) {
          setCompaniesLoading(false);
          setProspectsLoading(false);
        }
      }
    })();
    return () => {
      alive = false;
    };
    // qc (QueryClient) and toast (useCallback) are stable, so the effect still only re-runs on a
    // client change.
  }, [client, qc, toast]);
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
    const apply = () =>
      setChecked((s) => {
        const n = new Set(s);
        if (n.has(p.id)) n.delete(p.id);
        else n.add(p.id);
        return n;
      });
    const verdict = maySelect(p.label, checked.has(p.id));
    if (verdict === "blocked") return; // excluded locked out
    if (verdict === "confirm") {
      setLowFitPrompt({ apply }); // low_fit add → design-system confirm (M31)
      return;
    }
    apply();
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
    // excluded locked out of Step-1 selection; low_fit confirms; unticking always allowed. Step 2
    // passes allowExcluded so a staged-then-excluded company can be ticked for removal (R6).
    const apply = () => setCompanyChecked((s) => toggleInSet(s, c.id));
    const verdict = maySelect(c.label, companyChecked.has(c.id), allowExcluded);
    if (verdict === "blocked") return;
    if (verdict === "confirm") {
      setLowFitPrompt({ apply }); // low_fit add → design-system confirm (M31)
      return;
    }
    apply();
  }
  function toggleCoCollapse(id: string) {
    setExpandedCos((s) => toggleInSet(s, id));
  }
  // Expand/collapse a Step-1 footnote bucket (low_fit / excluded_by_rules) — keyed by the label.
  function toggleBucket(key: string) {
    setExpandedBuckets((s) => toggleInSet(s, key));
  }
  // Expand/collapse one reason sub-group inside a footnote bucket — keyed `${bucket}::${reasonKey}`.
  function toggleSub(key: string) {
    setExpandedSubs((s) => toggleInSet(s, key));
  }

  // One Step-1 company row (the v2 call-sheet cell: label chip + score, the four subscores as a text
  // list, and — for non-contact rows — a one-line reason). An `excluded_by_rules` row can't be ticked
  // (decision ④); its rule shows as the reason.
  const renderCompanyRow = (c: CompanyApi) => {
    const excluded = c.label === "excluded_by_rules";
    const contact = c.label === "contact_now" || c.label === "contact_soon";
    const icpLabel = c.icp_id ? icpNameById.get(c.icp_id) : undefined;
    return (
      <tr key={c.id} className={clsx(companyChecked.has(c.id) && "row-sel")}>
        <td>
          <input
            type="checkbox"
            className="tbl-check"
            checked={companyChecked.has(c.id)}
            // R6 — a checked row re-scored to excluded must stay untickable-off (only a NEW excluded
            // selection is blocked); pruneExcluded also drops it from the selection on the next reload.
            disabled={excluded && !companyChecked.has(c.id)}
            title={excluded ? "Excluded by rules — can't be selected" : undefined}
            onChange={() => toggleCo(c)}
          />
        </td>
        <td>
          <div className="who-cell">
            <div>
              {c.status === "people_found" ? <span className="sel-tag">Accepted</span> : null}
              <div className="nm">{c.name || c.domain}</div>
              {icpLabel || c.country ? (
                <div className="sub who-meta">
                  {icpLabel ? (
                    <span className="badge badge-neutral icp-badge">{icpLabel}</span>
                  ) : null}
                  {c.country ? <span>{c.country}</span> : null}
                </div>
              ) : null}
            </div>
          </div>
        </td>
        <td>
          {/* reason line: hidden for the two contact buckets (kept for low_fit / excluded). */}
          <FitCell
            scoring={scoringCoIds.has(c.id)}
            label={c.label}
            score={c.score_total}
            subscores={c.subscores}
            axes={COMPANY_AXES}
            reason={contact ? null : c.reason}
          />
        </td>
        <td>
          <WebLink website={c.website} domain={c.domain} />
        </td>
        <td className="muted">
          <div>{c.industry || "—"}</div>
          {c.business_model ? (
            <div className="ind-model">
              <span className={clsx("badge", businessModelChip(c.business_model).cls)}>
                {businessModelChip(c.business_model).label}
              </span>
            </div>
          ) : null}
        </td>
        <td className="muted">{c.size || "—"}</td>
        <td>
          <span className={clsx("badge", SOURCE_CLS[c.source] ?? "badge-neutral")}>
            <span className="bdot" />
            {SOURCE_LABEL[c.source] ?? c.source}
          </span>
        </td>
        <td>
          <CompanyStudy e={c.enrichment} />
        </td>
      </tr>
    );
  };

  // The expanded body of a footnote bucket (low_fit / excluded_by_rules): one count row per rejection
  // reason (indented under the bucket head), each expanding to the companies under that reason. Only
  // called for the two collapsible buckets — the action buckets render flat via renderCompanyRow.
  const renderSubGroups = (bucketKey: string, rows: CompanyApi[]) =>
    subGroupsOf(rows).map((g) => {
      const subKey = `${bucketKey}::${g.key}`;
      const open = expandedSubs.has(subKey);
      return (
        <Fragment key={subKey}>
          <tr className="bucket-sub bucket-head--btn" onClick={() => toggleSub(subKey)}>
            <td colSpan={8}>
              <span className="bucket-head-in bucket-sub-in">
                <span className={clsx("bucket-caret", open && "open")} aria-hidden="true">
                  ▸
                </span>
                <span className="bucket-sub-name">{g.label}</span>
                <span className="bucket-ct">{g.rows.length}</span>
                <span className="bucket-hint">{open ? "hide" : "review"}</span>
              </span>
            </td>
          </tr>
          {open ? g.rows.map(renderCompanyRow) : null}
        </Fragment>
      );
    });

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
          <>
            <div className="list-band">
              <h3>Find companies likely to buy</h3>
              <div className="band-actions">
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setFindHistoryOpen(true)}
                  title="Every find run · the exact scope it searched, match count, and spend"
                >
                  History
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={openScopeSettings}
                  title={
                    scopeOverride
                      ? "Custom scope active — Find uses your edited filters, not the AI spec"
                      : "Edit the Apollo company-search filters Find uses (saved per ICP)"
                  }
                >
                  Scope{scopeOverride ? " · Custom" : ""}
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={runFindCompanies}
                  disabled={coMutating}
                  title="Search Apollo for the target ICP's scope · free · enriches only new companies"
                >
                  {findingCo
                    ? "Finding…"
                    : coTargetIcpName
                      ? `Find · ${coTargetIcpName}`
                      : "Find company"}
                </button>
              </div>
            </div>
            {/* Selection bar (v2 toolbar): actions that act on the ticked rows appear only when a
                selection exists — Get AI score / lookalikes / refresh — so the primary band stays a
                clean "find" zone. `coSelCount` is visible∩checked, and every action below runs on
                that same set, so the count on the button always matches what runs (no "Score 3 runs
                9" drift). */}
            {coSelCount > 0 && (
              <div className="list-band sel-band">
                <style>{SEL_CSS}</style>
                <span className="sel-count">
                  <b>{coSelCount}</b> selected
                </span>
                <div className="band-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={runRescore}
                    disabled={scoringActive || findingPpl}
                    title="Run the paid AI fit score for the selected companies (≤15 per run)"
                  >
                    {scoringActive ? "Scoring…" : `Get AI score ${coSelCount}`}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={runLookalike}
                    disabled={coMutating}
                    title="Find the next batch of companies similar to the selected rows"
                  >
                    {findingLookalike ? "Finding…" : `Find lookalikes ${coSelCount}`}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={runUpdateFields}
                    disabled={coMutating}
                    title="Re-enrich Apollo firmographics for the selected companies · spends credits"
                  >
                    {updatingFields ? "Updating…" : `Refresh company data ${coSelCount}`}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => setCompanyChecked(new Set())}
                  >
                    Clear
                  </button>
                </div>
              </div>
            )}
            {scopeExhausted ? (
              <div className="se-notice" role="status">
                <style>{SE_CSS}</style>
                <div className="se-body">
                  <strong>You&apos;ve reviewed every company Apollo has for this scope.</strong>{" "}
                  Find resumes at the next page each run, and this one reached the end — there are
                  no new companies left under these exact filters. To open up more:
                </div>
                <div className="se-actions">
                  <button
                    className="btn btn-accent btn-sm"
                    onClick={runLookalikeOfStrong}
                    disabled={coMutating}
                    title="Find the next batch of companies similar to your Strong/Good rows"
                  >
                    {findingLookalike ? "Finding…" : "Find lookalikes of your best rows"}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={openScopeSettings}
                    title="Widen the Apollo filters, or regenerate the scope from the Business brief"
                  >
                    Adjust scope
                  </button>
                  <button
                    className="btn btn-ghost btn-xs se-dismiss"
                    onClick={() => setScopeExhausted(false)}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            ) : null}
            <div className="filter-row list-toolbar">
              <div className="search">
                <span className="si">⌕</span>
                <input
                  className="input"
                  type="text"
                  placeholder="Search company or domain"
                  value={coSearch}
                  onChange={(e) => setCoSearch(e.target.value)}
                />
              </div>
              <IcpFilterSelect
                options={icpOptions}
                value={fIcp}
                onChange={setFIcp}
                title="Filter the list by ICP · Find Company searches the picked ICP's scope"
                highlight={icpNeedsPick}
              />
              <select
                className="select"
                value={coStatus}
                onChange={(e) => setCoStatus(e.target.value)}
              >
                <option value="">All status</option>
                <option value="accepted">Accepted</option>
                <option value="pending">Pending</option>
              </select>
              <button className="btn btn-ghost btn-sm" onClick={() => setAddCoOpen(true)}>
                Manual Upload
              </button>
            </div>
            <div className="countrow">
              <b>{coVisible.length}</b>&nbsp;shown&nbsp;·&nbsp;<b>{coSelCount}</b>&nbsp;selected
            </div>
            <div className="list-body">
              <ListOverlay busy={coBusy} />
              <div className="list-scroll">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th style={{ width: 34 }} />
                      <th>Company</th>
                      <th>Fit</th>
                      <th>Domain</th>
                      <th>Industry</th>
                      <th>Size</th>
                      <th>Source</th>
                      <th>Enrichment</th>
                    </tr>
                  </thead>
                  {coVisible.length > 0 && (
                    <tbody>
                      {/* Call sheet (spec §11): one group per label bucket. EVERY bucket header is a
                        collapse toggle, and ALL buckets default CLOSED to a one-line count — the
                        operator expands the bucket they want to work. `expandedBuckets` holds the
                        expanded keys. Footnotes (low_fit / excluded) expand to a per-reason
                        breakdown; the rest expand to a flat row list. */}
                      {BUCKET_ORDER.map((key) => {
                        const rows = coBuckets.get(key) ?? [];
                        if (!rows.length) return null;
                        const footnote = COLLAPSED_KEYS.has(key); // low_fit / excluded_by_rules
                        const open = expandedBuckets.has(key);
                        return (
                          <Fragment key={key}>
                            <tr
                              className="bucket-head bucket-head--btn"
                              onClick={() => toggleBucket(key)}
                            >
                              <td colSpan={8}>
                                <span className="bucket-head-in">
                                  <span
                                    className={clsx("bucket-caret", open && "open")}
                                    aria-hidden="true"
                                  >
                                    ▸
                                  </span>
                                  <span
                                    className={clsx("bucket-dot", `bucket-dot--${key}`)}
                                    aria-hidden="true"
                                  />
                                  <span className="bucket-name">{BUCKET_HEAD[key]}</span>
                                  <span className="bucket-ct">{rows.length}</span>
                                  <span className="bucket-hint">
                                    {open ? "hide" : footnote ? "review" : "show"}
                                  </span>
                                  {key === "unscored" && (
                                    <button
                                      className="btn btn-accent btn-xs"
                                      style={{ marginLeft: "auto" }}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        scoreUnscoredWave();
                                      }}
                                      disabled={scoringActive || findingPpl}
                                      title="Run the paid AI fit score for the next batch of unscored companies (≤15 per run)"
                                    >
                                      {scoringActive
                                        ? "Scoring…"
                                        : `Score next ${Math.min(rows.length, SCORE_BATCH_MAX)} →`}
                                    </button>
                                  )}
                                </span>
                              </td>
                            </tr>
                            {open
                              ? footnote
                                ? renderSubGroups(key, rows)
                                : rows.map(renderCompanyRow)
                              : null}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  )}
                </table>
                {coVisible.length === 0 && (
                  <div className="list-empty muted">
                    No companies match the current scope yet · click Find Companies to search
                    Apollo.
                    <br />
                    {coScopeSummary ? (
                      <>
                        Active filters{scopeOverride ? " (custom)" : ""}
                        {fIcp && icpNameById.get(fIcp) ? ` · ${icpNameById.get(fIcp)}` : ""} ·{" "}
                        {coScopeSummary}.
                        <br />
                        Too few results? Widen them in ⚙ Scope, or + Add company manually.
                      </>
                    ) : (
                      <>Set your filters in ⚙ Scope, or + Add company manually. Finding is free.</>
                    )}
                  </div>
                )}
              </div>
            </div>
            <div className="list-dock">
              <span className={clsx("dock-count", !coSelCount && "empty")}>
                {coSelCount ? (
                  <>
                    <b>{coSelCount}</b> companies selected
                  </>
                ) : (
                  "Select companies to move to Step 2"
                )}
              </span>
              {coSelCount ? (
                <button className="dock-clear" onClick={() => setCompanyChecked(new Set())}>
                  Clear
                </button>
              ) : null}
              <span className="dock-spacer" />
              <button
                className="btn btn-primary"
                onClick={() => void stageForPeople()}
                disabled={!coSelCount || staging}
              >
                {staging ? "Moving…" : `Find people for ${coSelCount} →`}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="list-band">
              <h3>Find the right person</h3>
              <span className="band-sub">Personas auto-matched per company ICP</span>
              <div className="band-actions">
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => void openPeopleScopeSettings()}
                  title="Edit the Apollo people-search personas Find People uses (saved per ICP)"
                >
                  {peopleScopeOverride ? "Personas · Custom" : "Personas"}
                  {coTargetIcpName ? ` · ${coTargetIcpName}` : ""}
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={runFindPeople}
                  disabled={findingPpl || !pplCoSel.length}
                  title="Re-find people at the ticked companies (free; reveal emails spends credits)"
                >
                  {findingPpl
                    ? "Finding…"
                    : pplCoSel.length
                      ? `Find People ${pplCoSel.length}`
                      : "Find People"}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => void removeFromStep2()}
                  disabled={!pplCoSel.length || removing}
                  title="Remove the ticked companies from Step 2 (back to the Step-1 list)"
                >
                  {removing
                    ? "Removing…"
                    : pplCoSel.length
                      ? `Remove ${pplCoSel.length}`
                      : "Remove"}
                </button>
              </div>
            </div>
            <div className="filter-row list-toolbar">
              <div className="search">
                <span className="si">⌕</span>
                <input
                  className="input"
                  type="text"
                  placeholder="Search company or domain"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <IcpFilterSelect
                options={icpOptions}
                value={fIcp}
                onChange={setFIcp}
                title="Filter the Step-2 companies (and their people) by ICP"
              />
              <select
                className="select"
                value={fStatus}
                onChange={(e) => setFStatus(e.target.value)}
              >
                <option value="">All status</option>
                <option value="found">Found</option>
                <option value="scored">Enriched</option>
              </select>
              <button className="btn btn-ghost btn-sm" onClick={() => setAddPersonOpen(true)}>
                Manual Upload
              </button>
            </div>
            <div className="countrow">
              <b>{pursued.length}</b>&nbsp;companies&nbsp;·&nbsp;<b>{visible.length}</b>
              &nbsp;people&nbsp;·&nbsp;
              {/* R13 — the "selected" count reads the WHOLE selection (what Reveal & score acts on),
                  mirroring Step 1's `coSelCount`, so the countrow and the dock never disagree. */}
              <b>{selectedProspects.length}</b>&nbsp;selected
            </div>
            <div className="list-body">
              <ListOverlay busy={pplBusy} />
              <div className="list-scroll">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Company</th>
                      <th style={{ width: 34 }} />
                      <th>Prospect</th>
                      <th>Title</th>
                      <th>Status</th>
                      <th>LinkedIn</th>
                      <th>Fit</th>
                    </tr>
                  </thead>
                  {pursued.length > 0 && (
                    <tbody>
                      {pursued.map((c) => {
                        const rows = rowsForCompany(c.id);
                        const finding = findingPplIds.has(c.id);
                        const searched = c.status === "people_found";
                        // The per-company count/status indicator — sits on top of the company name.
                        const countBadge = finding ? (
                          <span className="fit-scoring">
                            <span className="hs-spinner" aria-hidden="true" />
                            Finding…
                          </span>
                        ) : !searched ? (
                          <span className="badge badge-warn">
                            <span className="bdot" />
                            Pending
                          </span>
                        ) : rows.length === 0 ? (
                          <span className="badge badge-neutral">
                            <span className="bdot" />0 people
                          </span>
                        ) : (
                          <span className="badge badge-info">
                            <span className="bdot" />
                            {rows.length} {rows.length === 1 ? "person" : "people"}
                          </span>
                        );
                        const collapsed = !expandedCos.has(c.id);
                        const expandable = rows.length > 0;
                        const enrichedCount = rows.filter(
                          (p) => p.status === ENRICHED_STATUS
                        ).length;
                        // Company cell — count badge atop the name; spans the company's people rows.
                        // When the company has people, clicking the cell collapses/expands that list
                        // (the select checkbox stops propagation so ticking doesn't toggle it).
                        const companyCell = (rowSpan: number) => (
                          <td
                            className={clsx("vtop", "grp-co-cell", expandable && "grp-co-click")}
                            rowSpan={rowSpan}
                            onClick={expandable ? () => toggleCoCollapse(c.id) : undefined}
                            title={
                              expandable
                                ? collapsed
                                  ? "Expand people"
                                  : "Collapse people"
                                : undefined
                            }
                          >
                            <div className="grp-co">
                              <span className="grp-co-top">
                                <input
                                  type="checkbox"
                                  className="tbl-check"
                                  checked={companyChecked.has(c.id)}
                                  // R6 — allowExcluded: a staged company later re-scored excluded can
                                  // still be ticked here to Remove it (the funnel actions skip excluded).
                                  onChange={() => toggleCo(c, true)}
                                  onClick={(e) => e.stopPropagation()}
                                  title="Select this company to find people"
                                />
                                {countBadge}
                              </span>
                              <span className="nm">{c.name || c.domain}</span>
                              {c.domain ? <span className="domain">{c.domain}</span> : null}
                              {c.icp_id && icpNameById.get(c.icp_id) ? (
                                <span className="badge badge-neutral">
                                  {icpNameById.get(c.icp_id)}
                                </span>
                              ) : null}
                            </div>
                          </td>
                        );
                        // No people yet (pending · finding · searched-empty) — a single standalone row.
                        if (rows.length === 0) {
                          return (
                            <tr key={c.id} className="co-start">
                              {companyCell(1)}
                              <td />
                              <td className="muted grp-hint" colSpan={5}>
                                {finding
                                  ? "Finding people…"
                                  : !searched
                                    ? "Tick this company, then Find People"
                                    : "No people found · loosen Find Settings, then Find People again"}
                              </td>
                            </tr>
                          );
                        }
                        // Collapsed — hide the people rows, keep one company row with a count hint.
                        if (collapsed) {
                          return (
                            <tr key={c.id} className="co-start">
                              {companyCell(1)}
                              <td />
                              <td className="muted grp-hint" colSpan={5}>
                                {enrichedCount} enriched · {rows.length}{" "}
                                {rows.length === 1 ? "person" : "people"} hidden · click company
                                cell to expand viewing
                              </td>
                            </tr>
                          );
                        }
                        return (
                          <Fragment key={c.id}>
                            {rows.map((p, i) => {
                              const enriched = p.status === ENRICHED_STATUS;
                              const stClass = enriched
                                ? "st--enriched"
                                : p.status === "score_error" || p.status === "enrich_failed"
                                  ? "st--error"
                                  : "st--found";
                              const stMeta = enriched
                                ? p.email_valid
                                  ? "email verified"
                                  : "email · unverified"
                                : p.status === "confirmed"
                                  ? "awaiting enrichment"
                                  : p.status === "score_error"
                                    ? "scoring failed"
                                    : p.status === "enrich_failed"
                                      ? "no Apollo match"
                                      : "no email yet";
                              return (
                                <tr
                                  key={p.id}
                                  className={clsx(
                                    i === 0 && "co-start",
                                    checked.has(p.id) && "row-sel"
                                  )}
                                >
                                  {i === 0 ? companyCell(rows.length) : null}
                                  <td>
                                    <input
                                      type="checkbox"
                                      className="tbl-check"
                                      checked={checked.has(p.id)}
                                      disabled={p.label === "excluded_by_rules"}
                                      title={
                                        p.label === "excluded_by_rules"
                                          ? "Excluded by rules — can't be selected"
                                          : undefined
                                      }
                                      onChange={() => toggleRow(p)}
                                    />
                                  </td>
                                  <td>
                                    <div className="who-cell">
                                      <div>
                                        <div className="nm">{p.full_name || "—"}</div>
                                        <div className="sub">{p.email || "no email yet"}</div>
                                      </div>
                                    </div>
                                  </td>
                                  <td className="muted">{p.title || "—"}</td>
                                  <td>
                                    <div className="st2">
                                      <span className={clsx("st", stClass)}>
                                        <span className="st-dot" />
                                        {STATUS_LABEL[p.status] ?? p.status}
                                      </span>
                                      <span className="st-meta">{stMeta}</span>
                                    </div>
                                  </td>
                                  <td>
                                    <LinkedInLink url={p.linkedin_url} />
                                  </td>
                                  <td>
                                    <FitCell
                                      scoring={scoringPersonIds.has(p.id)}
                                      label={p.label}
                                      score={p.score_total}
                                      subscores={p.subscores}
                                      axes={PROSPECT_AXES}
                                    />
                                  </td>
                                </tr>
                              );
                            })}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  )}
                </table>
                {pursued.length === 0 && (
                  <div className="list-empty muted">
                    {prospectsLoading || companiesLoading ? (
                      "Loading…"
                    ) : (
                      <>
                        No companies in Step 2 yet · go to Step 1, tick companies, and click “Find
                        people for N →”.
                        {pplScopeSummary ? (
                          <>
                            <br />
                            Person filters{peopleScopeOverride ? " (custom)" : ""} ·{" "}
                            {pplScopeSummary}. Adjust them in ⚙ Personas.
                          </>
                        ) : null}
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
            <div className="list-dock">
              <span className={clsx("dock-count", !selectedProspects.length && "empty")}>
                {selectedProspects.length ? (
                  <>
                    <b>{selectedProspects.length}</b> selected
                    {toEnrich.length ? (
                      <span className="sub"> · {toEnrich.length} need email reveal</span>
                    ) : null}
                  </>
                ) : (
                  "Select people to score, reveal emails, and batch"
                )}
              </span>
              {selectedProspects.length ? (
                <button className="dock-clear" onClick={() => setChecked(new Set())}>
                  Clear
                </button>
              ) : null}
              <span className="dock-spacer" />
              {/* People-selection funnel (left→right): reveal & score → create batch. One merged
                  action — reveal verified emails (the ONLY Apollo credit spend, 1cr/email) THEN AI-score
                  on the revealed data, since scoring a pre-reveal row gates on missing contact. When the
                  selection is already revealed it's a pure re-score (0 credits), so the label drops the
                  "Reveal &" / credit count. */}
              <button
                className="btn btn-accent btn-sm"
                onClick={runRevealScore}
                disabled={!selectedProspects.length || scoringPeopleActive || findingPpl}
                title={
                  toEnrich.length
                    ? "Reveal verified emails for the selected people (1 Apollo credit each), then AI-score them on the revealed data · ≤15 per run"
                    : "AI-score the selected people (already revealed — no credits) · ≤15 per run"
                }
              >
                {scoringPeopleActive
                  ? "Working…"
                  : toEnrich.length
                    ? `Reveal & score ${selectedProspects.length} · ${toEnrich.length} credits`
                    : `Score ${selectedProspects.length}`}
              </button>
              <div className={clsx("dock-act", canBatch ? "on" : "off")}>
                <input
                  className="input dock-name"
                  type="text"
                  placeholder="Batch Name"
                  value={newBatchName}
                  onChange={(e) => setNewBatchName(e.target.value)}
                  disabled={!canBatch}
                />
                <button
                  className="btn btn-primary"
                  onClick={createBatch}
                  disabled={!canBatch}
                  title={
                    canBatch
                      ? ""
                      : toEnrich.length
                        ? "Reveal & score the Found people first — only revealed people can be batched."
                        : "Select people with a revealed email to batch them."
                  }
                >
                  Create batch →
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* M31 — low_fit ADD confirm (design-system Modal, replacing window.confirm) */}
      <Modal
        open={lowFitPrompt !== null}
        onClose={() => setLowFitPrompt(null)}
        title="Add a Low-fit row?"
        footer={
          <>
            <button className="btn btn-ghost btn-sm" onClick={() => setLowFitPrompt(null)}>
              Cancel
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => {
                lowFitPrompt?.apply();
                setLowFitPrompt(null);
              }}
            >
              Add anyway
            </button>
          </>
        }
      >
        <p style={{ margin: 0, lineHeight: 1.5 }}>
          This row scored <b>Low fit</b>. Add it to the selection anyway?
        </p>
      </Modal>

      {/* FIT RUBRIC MODAL — the versioned scoring rubric (append-only) */}
      <Modal
        open={showSourcing}
        onClose={() => setShowSourcing(false)}
        title={`Fit rubric · ${rubricStage === "prospect_fit" ? "Step 2 · People" : "Step 1 · Companies"}`}
        subtitle={`The exact system + input prompt sent to the model to score each ${
          rubricStage === "prospect_fit" ? "prospect" : "company"
        }.`}
        className="modal-lg"
        footer={
          <button className="btn btn-primary btn-sm" onClick={() => setShowSourcing(false)}>
            Done
          </button>
        }
      >
        <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
          {fitPrompt && (
            <span className="badge badge-info">model · {fitPrompt.model.join(" → ")}</span>
          )}
          <span className="badge badge-neutral">purpose · {fitPrompt?.purpose ?? rubricStage}</span>
          <span className="badge badge-neutral">rubric v{docs?.[rubricStage]?.version ?? "—"}</span>
        </div>
        <PromptEditorShell
          systemBadge={
            <span className="badge badge-neutral">v{docs?.[rubricStage]?.version ?? "—"}</span>
          }
          systemActions={
            <button
              type="button"
              className="btn btn-accent btn-xs"
              onClick={() => saveDoc(rubricStage)}
              disabled={savingDoc === rubricStage}
            >
              {savingDoc === rubricStage ? "Saving…" : "Save as new version"}
            </button>
          }
          systemValue={rubricDraft}
          onSystemChange={setRubricDraft}
          inputMeta={
            <span className="ph-sub">
              {fitPromptLoading
                ? "loading…"
                : fitPrompt?.company
                  ? `read-only · sample: ${fitPrompt.company}`
                  : `read-only · no ${rubricStage === "prospect_fit" ? "prospect" : "company"} yet`}
            </span>
          }
          inputContent={
            fitPromptLoading
              ? "Loading the input prompt…"
              : fitPromptErr
                ? fitPromptErr
                : fitPrompt?.user ||
                  `${
                    rubricStage === "prospect_fit"
                      ? "Find people first to preview a prospect's"
                      : "Find a company first to preview its"
                  } input prompt.`
          }
          hint={
            <>
              Edits are saved for this client and used on the next re-score. Each{" "}
              {rubricStage === "prospect_fit" ? "prospect" : "company"} is scored against this
              rubric with the input prompt shown on the right.
            </>
          }
        />
      </Modal>

      {/* FIND-COMPANY SCOPE SETTINGS — edit the Apollo company-search filters Phase B produced.
          Empty fields are dropped server-side (they simply widen the search). */}
      <Modal
        open={scopeOpen}
        className="modal-lg"
        onClose={() => setScopeOpen(false)}
        title="Find Companies · search filters"
        subtitle="Apollo company-search filters, pre-filled from the selected ICP's AI scope · blank fields are dropped · saved per ICP for the next Find."
        footer={
          <>
            <button
              className="btn btn-ghost btn-sm"
              onClick={resetScopeSettings}
              title="Discard manual edits and use the AI-generated scope"
            >
              Reset to AI scope
            </button>
            <span style={{ flex: 1 }} />
            <button className="btn btn-ghost btn-sm" onClick={() => setScopeOpen(false)}>
              Cancel
            </button>
            <button className="btn btn-primary btn-sm" onClick={saveScopeSettings}>
              Save filters
            </button>
          </>
        }
      >
        {!scopeForm && <p className="muted">Loading the ICP’s saved filters…</p>}
        {scopeForm && (
          <>
            <div
              className="row"
              style={{ gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}
            >
              {icpOptions.length > 0 && (
                <select
                  className="select"
                  value={scopeIcp}
                  onChange={(e) => switchScopeIcp(e.target.value)}
                  title="Switch which ICP's search filters you are viewing/editing · Save targets the next Find at this ICP"
                >
                  {icpOptions.map((o) => (
                    <option key={o.id} value={o.id}>
                      ICP · {o.label}
                    </option>
                  ))}
                </select>
              )}
              <span className="badge badge-neutral">search · apollo</span>
              <span className="badge badge-info">pre-filled from AI scope</span>
              {icpOptions.length > 1 && (
                <span className="ph-sub">
                  switching ICP reloads that profile&rsquo;s filters · Save first to keep edits
                </span>
              )}
            </div>
            <SpecHead>Company search · firmographics</SpecHead>
            <div className="sourcing-cols">
              <Field
                label="Keywords · industry / market tags (comma-separated)"
                placeholder="Insurtech, Insurance"
                value={scopeForm.keywords}
                onChange={(v) => setScopeForm({ ...scopeForm, keywords: v })}
              />
              <Field
                label="Locations · HQ country / region (comma-separated)"
                placeholder="hong kong, singapore, thailand"
                value={scopeForm.locations}
                onChange={(v) => setScopeForm({ ...scopeForm, locations: v })}
              />
            </div>
            <div className="sourcing-cols" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <Field
                label="Employee size ranges · min,max (; for more)"
                placeholder="10,100 ; 101,500"
                value={scopeForm.sizes}
                onChange={(v) => setScopeForm({ ...scopeForm, sizes: v })}
              />
              <Field
                label="Revenue min (USD)"
                type="number"
                placeholder="(any)"
                value={scopeForm.revenueMin}
                onChange={(v) => setScopeForm({ ...scopeForm, revenueMin: v })}
              />
              <Field
                label="Revenue max (USD)"
                type="number"
                placeholder="(any)"
                value={scopeForm.revenueMax}
                onChange={(v) => setScopeForm({ ...scopeForm, revenueMax: v })}
              />
            </div>
            <SpecHead>Buying signals (intent) · optional, narrows hard</SpecHead>
            <Field
              label="Hiring for job titles (comma-separated)"
              placeholder="sales, growth, commercial"
              value={scopeForm.hiringTitles}
              onChange={(v) => setScopeForm({ ...scopeForm, hiringTitles: v })}
            />
          </>
        )}
      </Modal>

      {/* FIND-PEOPLE SCOPE SETTINGS — edit the Apollo people-search filters Phase B produced.
          Empty fields are dropped server-side; the org scope comes from your Step-1 selection. */}
      <Modal
        open={peopleScopeOpen}
        className="modal-lg"
        onClose={() => setPeopleScopeOpen(false)}
        title="Find People · who to target"
        subtitle="Target people by Management Level × Department & Job Function — Apollo's own facets — with live counts for your ticked Step-2 companies · saved per client."
        footer={
          <>
            <button
              className="btn btn-ghost btn-sm"
              onClick={resetPeopleScopeSettings}
              disabled={savingPplScope}
              title="Discard manual edits and use the AI-generated person scope"
            >
              Reset to AI scope
            </button>
            <span style={{ flex: 1 }} />
            <button className="btn btn-ghost btn-sm" onClick={() => setPeopleScopeOpen(false)}>
              Cancel
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={savePeopleScopeSettings}
              disabled={savingPplScope}
            >
              {savingPplScope ? "Saving…" : "Save filters"}
            </button>
          </>
        }
      >
        {peopleScopeForm && (
          <>
            <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
              <span className="badge badge-neutral">facets · apollo</span>
              {peopleScopeOverride ? (
                <span className="badge badge-warn">custom</span>
              ) : (
                <span className="badge badge-info">from AI scope</span>
              )}
              {pplFacets && (
                <span className="badge badge-neutral">{pplFacets.total} people in scope</span>
              )}
            </div>
            <p className="ph-sub" style={{ marginTop: 0 }}>
              Management Level AND Department · OR within each. A strict combo can return few or
              none, so Find People auto-widens (department-only, then level-only); leave a facet
              empty to skip it.
            </p>
            {pplCoSel.length === 0 && (
              <p className="ph-sub" style={{ color: "var(--warn)" }}>
                Tick one or more companies in the Step-2 list to load live counts and the department
                options.
              </p>
            )}

            <SpecHead>Management Level{pplFacetsLoading ? " · loading…" : ""}</SpecHead>
            <div className="facet-grid">
              {SENIORITY_OPTIONS.map((o) => {
                const count = pplFacets?.seniorities.find((s) => s.value === o.value)?.count;
                return (
                  <FacetRow
                    key={o.value}
                    label={o.label}
                    checked={peopleScopeForm.seniorities.includes(o.value)}
                    count={count}
                    onToggle={() => toggleFacet("seniorities", o.value)}
                  />
                );
              })}
            </div>

            <SpecHead>Departments &amp; Job Function</SpecHead>
            {pplFacets ? (
              // Top-level departments only (no subdepartment drill-down) — the master facet plus
              // its live count is enough to target; any selected non-master value is appended so a
              // prior sub-selection stays visible and uncheckable.
              <div className="facet-grid">
                {[
                  ...pplFacets.departments.map((d) => ({
                    value: d.value,
                    label: d.label,
                    count: d.count as number | undefined,
                  })),
                  ...peopleScopeForm.departments
                    .filter((v) => !pplFacets.departments.some((d) => d.value === v))
                    .map((value) => ({ value, label: humanizeFacet(value), count: undefined })),
                ].map((d) => (
                  <FacetRow
                    key={d.value}
                    label={d.label}
                    checked={peopleScopeForm.departments.includes(d.value)}
                    count={d.count}
                    onToggle={() => toggleFacet("departments", d.value)}
                  />
                ))}
              </div>
            ) : (
              <>
                {/* No live probe yet (no companies ticked): still show the master departments so the
                    AI-scope selection is visible + editable. Any scope-selected subdepartment not in
                    the master list is appended so it isn't hidden until the probe loads. */}
                <div className="facet-grid">
                  {[
                    ...masterDepts,
                    ...peopleScopeForm.departments
                      .filter((v) => !masterDepts.some((o) => o.value === v))
                      .map((value) => ({ value, label: humanizeFacet(value) })),
                  ].map((o) => (
                    <FacetRow
                      key={o.value}
                      label={o.label}
                      checked={peopleScopeForm.departments.includes(o.value)}
                      onToggle={() => toggleFacet("departments", o.value)}
                    />
                  ))}
                </div>
                <p className="ph-sub" style={{ marginTop: 8 }}>
                  {pplFacetsLoading
                    ? "Loading live counts…"
                    : "Tick companies above for live counts and the full subdepartment list."}
                </p>
              </>
            )}
          </>
        )}
      </Modal>

      {/* ADD COMPANY (manual, stage 1) — same schema as an imported row, source=manual */}
      <Modal
        open={addCoOpen}
        onClose={() => setAddCoOpen(false)}
        title="Add company"
        subtitle="Add one company by hand · suppression-checked, then fit-scored against your rubric on save."
        footer={
          <ConfirmFooter
            onCancel={() => setAddCoOpen(false)}
            onConfirm={submitAddCompany}
            busy={savingCo}
            confirmDisabled={!coForm.domain.trim()}
            busyLabel="Scoring…"
            confirmLabel="Add + score"
          />
        }
      >
        <ManualBadges />
        <Field
          label="Company domain *"
          placeholder="acme.com"
          value={coForm.domain}
          onChange={(v) => setCoForm({ ...coForm, domain: v })}
        />
        <Field
          label="Name"
          placeholder="Acme Robotics"
          value={coForm.name}
          onChange={(v) => setCoForm({ ...coForm, name: v })}
        />
        <Field
          label="Website"
          placeholder="https://acme.com"
          value={coForm.website}
          onChange={(v) => setCoForm({ ...coForm, website: v })}
        />
        <div className="sourcing-cols">
          <Field
            label="Industry"
            value={coForm.industry}
            onChange={(v) => setCoForm({ ...coForm, industry: v })}
          />
          <Field
            label="Size"
            placeholder="201-500"
            value={coForm.size}
            onChange={(v) => setCoForm({ ...coForm, size: v })}
          />
        </div>
        <div className="sourcing-cols">
          <Field
            label="Country"
            value={coForm.country}
            onChange={(v) => setCoForm({ ...coForm, country: v })}
          />
          <Field
            label="Company LinkedIn"
            placeholder="linkedin.com/company/…"
            value={coForm.linkedin_url}
            onChange={(v) => setCoForm({ ...coForm, linkedin_url: v })}
          />
        </div>
        <div className="ph-sub" style={{ marginTop: 16 }}>
          Domain required · rest optional · scored on save.
        </div>
      </Modal>

      {/* ADD PERSON (manual, stage 2) — same schema as an imported row, source=manual */}
      <Modal
        open={addPersonOpen}
        onClose={() => setAddPersonOpen(false)}
        title="Add person"
        subtitle="Add one person by hand · suppression-checked, then fit-scored against your rubric on save."
        footer={
          <ConfirmFooter
            onCancel={() => setAddPersonOpen(false)}
            onConfirm={submitAddPerson}
            busy={savingPerson}
            busyLabel="Scoring…"
            confirmLabel="Add + score"
          />
        }
      >
        <ManualBadges />
        <div className="sourcing-cols">
          <Field
            label="Full name"
            value={personForm.full_name}
            onChange={(v) => setPersonForm({ ...personForm, full_name: v })}
          />
          <Field
            label="Title"
            placeholder="VP Engineering"
            value={personForm.title}
            onChange={(v) => setPersonForm({ ...personForm, title: v })}
          />
        </div>
        <div className="field">
          <label>Company</label>
          <select
            className="select"
            value={personForm.domain}
            onChange={(e) => {
              const co = step2Companies.find((c) => c.domain === e.target.value);
              setPersonForm({
                ...personForm,
                domain: co?.domain ?? "",
                company: co?.name ?? "",
              });
            }}
          >
            <option value="">
              {step2Companies.length ? "Select a company…" : "No accepted companies yet"}
            </option>
            {step2Companies.map((c) => (
              <option key={c.id} value={c.domain}>
                {c.name || c.domain}
                {c.domain ? ` · ${c.domain}` : ""}
              </option>
            ))}
          </select>
        </div>
        <Field
          label="LinkedIn URL"
          placeholder="linkedin.com/in/…"
          value={personForm.linkedin_url}
          onChange={(v) => setPersonForm({ ...personForm, linkedin_url: v })}
        />
        <Field
          label="Email (optional — leave blank to enrich later)"
          value={personForm.email}
          onChange={(v) => setPersonForm({ ...personForm, email: v })}
        />
        <div className="ph-sub" style={{ marginTop: 16 }}>
          LinkedIn URL, name + company domain, or email · rest optional · scored on save.
        </div>
      </Modal>

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

// D+ Stage 3 — scope-exhausted notice. Scoped to `.se-*` so nothing leaks to other routes (the list
// page has no co-located stylesheet; this mirrors the FindHistoryDrawer pattern). Warn-toned but
// calm — it's a "you're done here, try these" prompt, not an error.
// The v2 selection bar — a slim cerulean-wash strip that appears only when rows are ticked, holding
// the actions that act on the selection (kept out of the primary "find" band above).
const SEL_CSS = `
.sel-band { background: var(--cerulean-wash); }
.sel-band .sel-count { font-size: 13px; font-weight: 650; color: var(--ink); }
.sel-band .sel-count b { color: var(--cerulean-deep); }
`;

const SE_CSS = `
.se-notice { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px;
  margin: 12px 0 0; padding: 12px 14px; border: 1px solid var(--warn); border-radius: 10px;
  background: var(--warn-wash); }
.se-body { flex: 1 1 320px; font-size: 13px; color: var(--ink); line-height: 1.45; }
.se-body strong { color: var(--ink); }
.se-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.se-dismiss { margin-left: 2px; }
`;
