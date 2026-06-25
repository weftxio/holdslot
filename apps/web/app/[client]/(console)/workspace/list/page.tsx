"use client";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useClient } from "@/lib/nav";
import clsx from "clsx";
import { Modal } from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
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
  deletePeopleScopeOverride,
  enrichProspects,
  findCompaniesAsync,
  findLookalikesAsync,
  findPeople,
  getFitPrompt,
  getPeopleDepartments,
  getPeopleScopeOverride,
  getResearchSpec,
  getSourcingDocs,
  LIST_CEILING,
  listCompanies,
  listIcps,
  listProspects,
  peopleFacets,
  putPeopleScopeOverride,
  rescoreCompaniesAsync,
  rescoreProspectsAsync,
  saveSourcingDoc,
  SCORE_BATCH_MAX,
  selectCompanies,
  updateCompanyFieldsAsync,
} from "@/lib/api";
import type { ScoringJobApi } from "@/lib/api";
import type {
  Icp,
  PeopleScopeForm,
  PeopleScopeOverride,
  ScopeForm,
  ScopeOverride,
} from "@/lib/workspace/types";
import {
  ENRICHED_STATUS,
  NEEDS_ENRICH,
  SENIORITY_OPTIONS,
  SOURCE_CLS,
  SOURCE_LABEL,
  STATUS_LABEL,
  TODAY_ISO,
  apiToIcp,
  clearScoring,
  compareProspectRows,
  effectivePeopleScope,
  effectiveScope,
  formToOverride,
  formToPeopleOverride,
  humanizeFacet,
  loadScopeOverride,
  peopleScopeSummary,
  peopleScopeToForm,
  saveScopeOverride,
  scopeSummary,
  scopeToForm,
} from "@/lib/workspace/constants";
import {
  CompanyStudy,
  FitScore,
  LinkedInLink,
  SpecHead,
  WebLink,
} from "@/components/workspace";

export default function ListPage() {
  const client = useClient();
  const toast = useToast();
  // Batch creation from selection writes the shared cross-tab batches state (and reads the current
  // count for the default batch name).
  const { batches, setBatches } = useWorkspace();

  // ICPs + research spec — loaded locally on mount: icpNameById/the fIcp filter/ICP labels need
  // `icps`, and the scope-override `effectiveScope` needs `spec`. Additive to the list load below.
  const [icps, setIcps] = useState<Icp[]>([]);
  const [spec, setSpec] = useState<ResearchSpecResult | null>(null);

  // Prospect list (Phase C — live). Prospects, sourcing docs, and the round-history scoreboard
  // are loaded from the API; selection is by prospect id. Batch creation stays client-side until
  // Phase D builds the backend (the select → batch seam is real; the batch object is the mock).
  const [prospects, setProspects] = useState<ProspectApi[]>([]);
  const [prospectsLoading, setProspectsLoading] = useState(false);
  const [companiesLoading, setCompaniesLoading] = useState(false);
  // W5 — true when the feed has more rows than the LIST_CEILING we auto-load (drives the notice).
  const [prospectsTruncated, setProspectsTruncated] = useState(false);
  const [companiesTruncated, setCompaniesTruncated] = useState(false);
  // Tracks the live client so an async reload/handler that resolves *after* a client switch can
  // bail before writing the previous client's data into the new client's view.
  const clientRef = useRef(client);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [fFit, setFFit] = useState("");
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
  const [companies, setCompanies] = useState<CompanyApi[]>([]);
  const [companyChecked, setCompanyChecked] = useState<Set<string>>(new Set());
  // Companies whose prospect rows are EXPANDED in the Step-2 list (company id). Default: not in the
  // set → collapsed, so the list opens with every company collapsed to its one-line summary.
  const [expandedCos, setExpandedCos] = useState<Set<string>>(new Set());
  const [coSearch, setCoSearch] = useState("");
  const [coFit, setCoFit] = useState("");
  // Status filter: "" all · "accepted" = people_found (the Accepted tag) · "pending" = not yet.
  const [coStatus, setCoStatus] = useState("");
  const [enriching, setEnriching] = useState(false);
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
  // Manual override of the AI scope's Apollo company-search filters (Settings modal).
  const [scopeOverride, setScopeOverride] = useState<ScopeOverride | null>(null);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [scopeForm, setScopeForm] = useState<ScopeForm | null>(null);
  // Same, for the Step-2 Apollo people-search filters.
  const [peopleScopeOverride, setPeopleScopeOverride] = useState<PeopleScopeOverride | null>(null);
  // The saved override is hydrated from the server on mount; until it resolves we don't yet know the
  // real scope, so the Find-Settings gear stays disabled to avoid showing (or saving over) the wrong
  // scope. On a load failure it stays false and a warning is surfaced — never a silent AI-scope view.
  const [pplScopeLoaded, setPplScopeLoaded] = useState(false);
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

  const icpNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of icps) if (p.id) m.set(p.id, p.short);
    return m;
  }, [icps]);

  async function reloadProspects() {
    setProspectsLoading(true);
    try {
      // Let errors propagate — a failed reload must surface, never silently blank the list
      // (which reads as "no prospects" and tempts a re-import / re-spend).
      const { items: ps, truncated } = await listProspects(client);
      if (clientRef.current !== client) return; // client switched mid-flight — drop stale data
      setProspects(ps);
      setProspectsTruncated(truncated);
      setChecked(new Set());
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
      const { items: cs, truncated } = await listCompanies(client);
      if (clientRef.current !== client) return;
      setCompanies(cs);
      setCompaniesTruncated(truncated);
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
  // since the brief route no longer renders alongside it.
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
    setSearch("");
    setCoSearch("");
    setFIcp("");
    setFFit("");
    setCoFit("");
    setCoStatus("");
    setScopeOverride(loadScopeOverride(client)); // per-client manual scope; null → AI spec
    setPeopleScopeOverride(null); // hydrated from the server below (replaces the old localStorage)
    setPplScopeLoaded(false); // gate the Find-Settings gear until the saved scope is known
    setProspectsTruncated(false); // cleared until the new client's feed reports its own cap
    setCompaniesTruncated(false);
    let alive = true;
    setCompaniesLoading(true);
    setProspectsLoading(true);
    // The saved people-scope override is fetched on its own track: unlike the lists (a failure there
    // just warns), a failed/slow override fetch must NOT silently present the AI scope — find_people
    // still applies the saved DB row, so we keep the gear disabled and surface a warning instead.
    const ovP = getPeopleScopeOverride(client);
    (async () => {
      try {
        const [ps, cs, dl, depts, ics, rs] = await Promise.all([
          listProspects(client),
          listCompanies(client),
          getSourcingDocs(client),
          getPeopleDepartments(client).catch(() => [] as FacetOption[]), // non-fatal: subs-only view
          listIcps(client).catch(() => null),
          getResearchSpec(client).catch(() => null),
        ]);
        if (!alive) return;
        setProspects(ps.items);
        setProspectsTruncated(ps.truncated);
        setCompanies(cs.items);
        setCompaniesTruncated(cs.truncated);
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
    (async () => {
      try {
        const pplOv = await ovP;
        if (!alive) return;
        setPeopleScopeOverride(pplOv ? { people_search_params: pplOv } : null);
        setPplScopeLoaded(true);
      } catch {
        if (alive) toast("Couldn’t load saved person filters · reload to edit them", "warn");
      }
    })();
    return () => {
      alive = false;
    };
  }, [client]);

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
  // filters the companies; `fFit` filters the people shown within them. Ordered by enriched count,
  // then total people — both descending — so the most-progressed companies surface first.
  const pursued = useMemo(
    () =>
      companies
        .filter(
          (c) =>
            (c.status === "selected" || c.status === "people_found") &&
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
    [companies, search, prospectsByCompany]
  );
  // The pool a manually-added person can attach to: companies accepted into Step 2 (with a domain,
  // since the backend resolves the person's company by domain). Drives the Add-person dropdown.
  const step2Companies = useMemo(
    () =>
      companies.filter(
        (c) => (c.status === "selected" || c.status === "people_found") && c.domain
      ),
    [companies]
  );
  // Rows of a pursued company that pass the fit filter — the per-company nested list.
  const rowsForCompany = (id: string) =>
    (prospectsByCompany.get(id) ?? [])
      .filter((p) => !fFit || p.fit_tier === fFit)
      .filter((p) => !fStatus || p.status === fStatus)
      .sort(compareProspectRows);
  // People in view across all pursued companies = the unit of selection for score / enrich / batch.
  const visible = useMemo(
    () => pursued.flatMap((c) => rowsForCompany(c.id)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pursued, prospectsByCompany, fFit, fStatus]
  );
  const selCount = visible.filter((p) => checked.has(p.id)).length;
  // Step-2 companies that are ticked — the unit of selection for Find People.
  const pplCoSel = pursued.filter((c) => companyChecked.has(c.id));
  // Step-2 dock: enrich and batch are mutually exclusive — find before enrich, enrich before
  // batch. Computed over the WHOLE selection (not the filtered view) so a filter change can't
  // drop checked rows. `confirmEnrich`/`createBatch` re-derive from the same rule.
  const selectedProspects = useMemo(
    () => prospects.filter((p) => checked.has(p.id)),
    [prospects, checked]
  );
  const toEnrich = useMemo(
    () => selectedProspects.filter((p) => NEEDS_ENRICH.has(p.status)),
    [selectedProspects]
  );
  const enrichedSel = useMemo(
    () => selectedProspects.filter((p) => p.status === ENRICHED_STATUS),
    [selectedProspects]
  );
  const canEnrich = toEnrich.length > 0;
  // Batch only once EVERY selected person is enriched (a verified email) — closes the gap where an
  // enrich_failed (no-email) row slipped through the old "nothing still needs enrich" gate.
  const canBatch = useMemo(
    () =>
      selectedProspects.length > 0 && selectedProspects.every((p) => p.status === ENRICHED_STATUS),
    [selectedProspects]
  );

  function toggleRow(id: string) {
    setChecked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  // ---- Stage 1: companies ----
  const coVisible = useMemo(
    () =>
      companies
        .filter((c) => {
          const text = `${c.name} ${c.domain} ${c.industry}`.toLowerCase();
          const accepted = c.status === "people_found";
          const statusOk =
            !coStatus || (coStatus === "accepted" ? accepted : !accepted);
          return (
            (!coSearch || text.includes(coSearch.toLowerCase())) &&
            (!coFit || c.fit_tier === coFit) &&
            statusOk
          );
        })
        // Accepted (people_found) rows float to the top; within each group, highest fit_score first
        // (nulls last). Sorting explicitly here makes the order self-sufficient rather than relying
        // on the backend list endpoint's ORDER BY (defense-in-depth, matching compareProspectRows).
        .sort((a, b) => {
          const aa = a.status === "people_found" ? 0 : 1;
          const ba = b.status === "people_found" ? 0 : 1;
          if (aa !== ba) return aa - ba;
          return (b.fit_score ?? -1) - (a.fit_score ?? -1);
        }),
    [companies, coSearch, coFit, coStatus]
  );
  const coSelCount = coVisible.filter((c) => companyChecked.has(c.id)).length;
  // A background AI-scoring pass (Find / Find Lookalike / Update AI Score) is running for ≥1 row.
  const scoringActive = scoringCoIds.size > 0;
  const scoringPeopleActive = scoringPersonIds.size > 0;
  const coAllChecked = coVisible.length > 0 && coSelCount === coVisible.length;
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
    () => scopeSummary(effectiveScope(scopeOverride, spec)),
    [scopeOverride, spec]
  );
  const pplScopeSummary = useMemo(
    () => peopleScopeSummary(effectivePeopleScope(peopleScopeOverride, spec)),
    [peopleScopeOverride, spec]
  );
  function toggleCo(id: string) {
    setCompanyChecked((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }
  function toggleCoCollapse(id: string) {
    setExpandedCos((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }
  function toggleAllCo(on: boolean) {
    const ids = coVisible.map((c) => c.id);
    setCompanyChecked((s) => {
      const n = new Set(s);
      for (const id of ids) on ? n.add(id) : n.delete(id);
      return n;
    });
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
    const job = await awaitScoringJob(client, started.job_id, () => clientRef.current === client);
    if (clientRef.current !== client) return null;
    if (job.status === "error") {
      toast(typeof job.error === "string" && job.error ? job.error : `${failLabel} failed`, "warn");
      return null;
    }
    return job;
  }

  // Flow A — Apollo company search from the saved ResearchSpec (or the Settings override). Needs a
  // generated scope. The 0-result toast distinguishes "Apollo matched nothing" (loosen filters)
  // from "matched but all filtered out as dupes/exclusions" (`dropped`) so the cause is explainable.
  // Async (W4): kicks a background find job, polls it, then reloads. Rows land unscored.
  async function runFindCompanies() {
    setFindingCo(true);
    try {
      const job = await runScoringJob(
        () => findCompaniesAsync(client, { icp_id: fIcp || null, ...(scopeOverride ?? {}) }),
        "Find companies"
      );
      if (!job) return;
      await reloadCompanies();
      const found = Number(job.result?.found ?? 0);
      const dropped = Number(job.result?.dropped ?? 0);
      if (found) {
        const tail = dropped ? ` · ${dropped} filtered out` : "";
        // Rows land unscored and stay that way (AI Score shows "Pending"); the operator scores on
        // demand by selecting rows and clicking Update AI Score. No auto-trigger.
        toast(
          `Found ${found} ${found === 1 ? "company" : "companies"}${tail} · ` +
            "select rows and click Update AI Score to score them"
        );
      } else if (dropped) {
        toast(
          `Apollo returned ${dropped}, but all were filtered out as duplicates or exclusions. ` +
            "Adjust the scope in ⚙ Settings.",
          "warn"
        );
      } else {
        toast(
          "No companies matched the current scope. Loosen the filters in ⚙ Settings " +
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
    const ids = [...companyChecked];
    if (!ids.length) return toast("Select companies to re-score", "warn");
    if (ids.length > SCORE_BATCH_MAX) {
      return toast(`Score at most ${SCORE_BATCH_MAX} companies at a time — narrow your selection.`, "warn");
    }
    toast(`Scoring ${ids.length} ${ids.length === 1 ? "company" : "companies"} in the background…`);
    rescoringCoRef.current = true;
    void scoreCompaniesJob(ids).finally(() => {
      rescoringCoRef.current = false;
    });
  }

  // "Update Field" — re-enrich Apollo firmographics for the selected rows. Each call spends Apollo
  // credits, so it is deliberate/manual (Find Companies enriches only new rows). Async (W4),
  // capped at SCORE_BATCH_MAX rows per job.
  async function runUpdateFields() {
    const ids = [...companyChecked];
    if (!ids.length) return toast("Select companies to update", "warn");
    if (ids.length > SCORE_BATCH_MAX) {
      return toast(`Update at most ${SCORE_BATCH_MAX} companies at a time — narrow your selection.`, "warn");
    }
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
      if (clientRef.current === client) toast(e instanceof Error ? e.message : "Update failed", "warn");
    } finally {
      if (clientRef.current === client) setUpdatingFields(false);
    }
  }

  // Score a set of company rows on one async background job (W4). The rows show "Scoring…" until the
  // job settles; the worker owns the batch (survives a tab close), and we reload once on completion.
  async function scoreCompaniesJob(ids: string[]) {
    setScoringCoIds((prev) => new Set([...prev, ...ids]));
    try {
      const job = await runScoringJob(() => rescoreCompaniesAsync(client, ids), "Scoring");
      if (clientRef.current !== client) return;
      if (job) {
        await reloadCompanies();
        const scored = Number(job.result?.scored ?? 0);
        toast(`Scored ${scored} ${scored === 1 ? "company" : "companies"}`);
      }
    } catch (e) {
      if (clientRef.current === client) toast(e instanceof Error ? e.message : "Scoring failed", "warn");
    } finally {
      if (clientRef.current === client) clearScoring(setScoringCoIds, ids);
    }
  }

  // "Find Lookalike" — find the next batch of peers of the checked rows. The seeds are the search
  // input (no Settings modal); the server aggregates their firmographics and drops every company
  // already in the list (seeds included), so `found` is the genuinely-new peers. Rows land UNSCORED
  // and stay that way (AI Score shows "Pending") — the operator scores on demand via Update AI
  // Score. The toast tells the outcomes apart: new / all-listed / none.
  async function runLookalike() {
    const ids = [...companyChecked];
    if (!ids.length) return toast("Select companies to find lookalikes", "warn");
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
        const tail = dropped ? ` · ${dropped} already in your list` : "";
        toast(
          `Found ${found} new lookalike ${found === 1 ? "company" : "companies"}${tail} · ` +
            "select rows and click Update AI Score to score them"
        );
      } else if (dropped) {
        toast(
          `Apollo returned ${dropped} similar ${dropped === 1 ? "company" : "companies"}, ` +
            `but ${dropped === 1 ? "it is" : "all are"} already in your list — nothing new to add.`,
          "warn"
        );
      } else {
        toast(
          "No companies similar to the selection were found. The seeds may be too sparse — " +
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
  function openScopeSettings() {
    setScopeForm(scopeToForm(effectiveScope(scopeOverride, spec)));
    setScopeOpen(true);
  }
  function saveScopeSettings() {
    if (!scopeForm) return;
    const ov = formToOverride(scopeForm);
    setScopeOverride(ov);
    saveScopeOverride(client, ov);
    setScopeOpen(false);
    toast("Search filters saved · used on the next Find");
  }
  function resetScopeSettings() {
    setScopeOverride(null);
    saveScopeOverride(client, null);
    setScopeForm(scopeToForm(effectiveScope(null, spec)));
    toast("Reverted to the AI-generated scope");
  }

  // Step 1 → Step 2: stage the ticked companies (discovered → selected) so they appear in the Step-2
  // table as "Pending" rows, then switch to Step 2. No Apollo call yet — people are found there, per
  // company. The ticks carry over (companyChecked is shared) so Find People is one click away.
  async function stageForPeople() {
    const ids = [...companyChecked];
    if (!ids.length) return;
    setStaging(true);
    try {
      await selectCompanies(client, ids, true);
      await reloadCompanies();
      setListStage("people");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn’t move companies to Step 2", "warn");
    } finally {
      setStaging(false);
    }
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
      setCompanyChecked((s) => {
        const n = new Set(s);
        ids.forEach((id) => n.delete(id));
        return n;
      });
      toast(`Removed ${ids.length} ${ids.length === 1 ? "company" : "companies"} from Step 2`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn’t remove companies", "warn");
    } finally {
      setRemoving(false);
    }
  }

  // Flow B — find people at the ticked Step-2 companies (free; enrichment is the credit spend). The
  // search is driven by the explicit company ids, so a row can be re-searched after loosening the
  // filters. People land UNSCORED ("Pending") — the operator scores them via Get AI score.
  async function runFindPeople() {
    const ids = pplCoSel.map((c) => c.id);
    if (!ids.length) return toast("Select companies in the list to find people", "warn");
    setFindingPpl(true);
    setFindingPplIds(new Set(ids));
    try {
      // The saved override is NOT sent in the body: the server reads it from the DB (the single
      // source of truth), so a stale in-memory copy in one tab can't shadow a save/reset done in
      // another. find_people falls back to the DB override → AI spec when no body override is given.
      const res = await findPeople(client, {
        company_ids: ids,
        icp_id: fIcp || null,
      });
      await Promise.all([reloadProspects(), reloadCompanies()]);
      if (res.found) {
        const tail = res.dropped ? ` · ${res.dropped} filtered out` : "";
        toast(
          `Found ${res.found} ${res.found === 1 ? "person" : "people"}${tail} · ` +
            "select them and click Get AI score to score them"
        );
      } else if (res.dropped) {
        toast(
          `Apollo returned ${res.dropped}, but all were filtered out (already imported, no Apollo id, ` +
            "or an avoided title). Adjust the Management Level / Department in ⚙ Settings.",
          "warn"
        );
      } else {
        toast(
          "No people matched — even after widening. Pick different Management Level / Department " +
            "facets in ⚙ Settings (the live counts show where people actually are).",
          "warn"
        );
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "Find people failed", "warn");
    } finally {
      setFindingPpl(false);
      setFindingPplIds(new Set());
    }
  }

  // Step-2 'Get AI score' — re-score the checked people on one async background job (W4), per-row
  // "Scoring…". Each call is a paid LLM request; capped at SCORE_BATCH_MAX rows (a bigger selection
  // is refused with a message rather than silently split).
  function runScorePeople() {
    if (rescoringPplRef.current) return; // block a double-click before the button disables
    const picked = selectedProspects;
    if (!picked.length) return toast("Select people to score", "warn");
    if (picked.length > SCORE_BATCH_MAX) {
      return toast(`Score at most ${SCORE_BATCH_MAX} people at a time — narrow your selection.`, "warn");
    }
    toast(`Scoring ${picked.length} ${picked.length === 1 ? "person" : "people"} in the background…`);
    rescoringPplRef.current = true;
    void scorePeopleJob(picked.map((p) => ({ id: p.id, key: p.identity_key }))).finally(() => {
      rescoringPplRef.current = false;
    });
  }

  // Score a set of people on one async background job (W4). Rows show "Scoring…" until it settles;
  // the worker owns the batch (survives a tab close), and we reload once on completion.
  async function scorePeopleJob(rows: { id: string; key: string }[]) {
    const ids = rows.map((r) => r.id);
    setScoringPersonIds((prev) => new Set([...prev, ...ids]));
    try {
      const job = await runScoringJob(
        () => rescoreProspectsAsync(client, rows.map((r) => r.key)),
        "Scoring"
      );
      if (clientRef.current !== client) return;
      if (job) {
        await reloadProspects();
        const scored = Number(job.result?.scored ?? 0);
        toast(`Scored ${scored} ${scored === 1 ? "person" : "people"}`);
      }
    } catch (e) {
      if (clientRef.current === client) toast(e instanceof Error ? e.message : "Scoring failed", "warn");
    } finally {
      if (clientRef.current === client) clearScoring(setScoringPersonIds, ids);
    }
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
  function openPeopleScopeSettings() {
    setPeopleScopeForm(peopleScopeToForm(effectivePeopleScope(peopleScopeOverride, spec)));
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
      const saved = await putPeopleScopeOverride(client, ov.people_search_params);
      if (clientRef.current !== client) return; // client switched mid-save — drop the stale write
      setPeopleScopeOverride(saved ? { people_search_params: saved } : null);
      setPeopleScopeOpen(false);
      toast(
        saved
          ? "Person filters saved · used on the next Find People"
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
      await deletePeopleScopeOverride(client);
      if (clientRef.current !== client) return; // client switched mid-reset — drop the stale write
      setPeopleScopeOverride(null);
      setPeopleScopeForm(peopleScopeToForm(effectivePeopleScope(null, spec)));
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

  // The enrich gate — confirm the selected scored people for enrichment. (The paid Apollo
  // people/match enrichment is wired server-side in Phase C; this flips status for now.)
  async function confirmEnrich() {
    if (enriching) return;
    const keys = toEnrich.map((p) => p.identity_key);
    if (!keys.length) return toast("Select found people to confirm for enrichment", "warn");
    setEnriching(true);
    // Chunk under the server's MAX_ENRICH_PER_REQUEST (15): each request is the credit spend, so a
    // small chunk keeps every call well under the 30s gateway cap and bounds per-request spend. The
    // server returns spend counts per chunk (even on partial Apollo failure), so totals are exact.
    const CHUNK = 10;
    let confirmed = 0,
      enriched = 0,
      credits = 0,
      failed = 0;
    try {
      for (let i = 0; i < keys.length; i += CHUNK) {
        const res = await enrichProspects(client, keys.slice(i, i + CHUNK));
        confirmed += res.confirmed;
        enriched += res.enriched;
        credits += res.credits_spent;
        failed += res.failed;
        await reloadProspects(); // reflect each chunk as it lands
      }
      const spent = `${credits} credit${credits === 1 ? "" : "s"} spent`;
      const failTail = failed ? ` · ${failed} failed` : "";
      toast(
        enriched ? `Enriched ${enriched} · ${spent}${failTail}` : `Confirmed ${confirmed}${failTail}`,
        failed ? "warn" : undefined
      );
    } catch (e) {
      await reloadProspects(); // surface whatever earlier chunks already committed
      toast(e instanceof Error ? e.message : "Confirm failed", "warn");
    } finally {
      setEnriching(false);
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
      const v = stage === "prospect_fit" ? dl.prospect_fit?.version : dl.company_fit?.version;
      toast(`Saved ${stage === "prospect_fit" ? "prospect" : "company"} fit rubric v${v}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Save failed", "warn");
    } finally {
      setSavingDoc(null);
    }
  }

  function createBatch() {
    const name = newBatchName.trim() || "Batch " + (batches.length + 1);
    // Only enriched people can be batched — enforce enrich-before-batch (the dock already gates
    // the button; re-check here so a stale click can't slip unenriched rows through).
    const picked = enrichedSel;
    if (!picked.length) {
      return toast("Select enriched people — enrich the Found ones first", "warn");
    }
    const icpSet = new Set(picked.map((p) => (p.icp_id ? icpNameById.get(p.icp_id) : null) || "—"));
    setBatches((s) => [
      ...s,
      {
        name,
        count: picked.length,
        approved: 0,
        icp: icpSet.size === 1 ? [...icpSet][0] : "Multiple ICPs",
        status: "Pending",
        createdAt: TODAY_ISO,
      },
    ]);
    setNewBatchName("");
    setChecked(new Set());
    toast(name + " created with " + picked.length + " prospects, pending client approval");
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
              <span className="tab-ct">({prospects.length})</span>
            </button>
          </div>
          <div className="head-actions">
            <button className="btn btn-ghost btn-sm" onClick={openRubric}>
              Fit Rubric
            </button>
            {listStage === "companies" ? (
              <button
                className="btn btn-ghost btn-sm"
                onClick={runRescore}
                disabled={!coSelCount || scoringActive || findingPpl}
                title="Re-run fit scoring for the selected companies · one paid LLM call each"
              >
                {scoringActive
                  ? "Scoring…"
                  : coSelCount
                    ? `Get AI score ${coSelCount}`
                    : "Get AI score"}
              </button>
            ) : (
              <button
                className="btn btn-ghost btn-sm"
                onClick={runScorePeople}
                disabled={!selCount || scoringPeopleActive || findingPpl}
                title="Run fit scoring for the selected people · one paid LLM call each"
              >
                {scoringPeopleActive
                  ? "Scoring…"
                  : selCount
                    ? `Get AI score ${selCount}`
                    : "Get AI score"}
              </button>
            )}
          </div>
        </div>

        {listStage === "companies" ? (
          <>
            <div className="list-band">
              <h3>Find companies likely to buy</h3>
              <div className="band-actions">
                <button
                  className="btn btn-primary btn-sm"
                  onClick={openScopeSettings}
                  title="Edit the Apollo company-search filters used by Find Company"
                >
                  Find Settings
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={runFindCompanies}
                  disabled={findingCo}
                  title="Search Apollo from the current scope · enriches only new companies"
                >
                  {findingCo ? "Finding…" : "Find Company"}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={runLookalike}
                  disabled={!coSelCount || findingLookalike || findingCo}
                  title="Find the next batch of companies similar to the selected rows · spends Apollo credits"
                >
                  {findingLookalike
                    ? "Finding…"
                    : coSelCount
                      ? `Find Lookalike ${coSelCount}`
                      : "Find Lookalike"}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={runUpdateFields}
                  disabled={!coSelCount || updatingFields || findingCo}
                  title="Re-enrich Apollo firmographics for the selected companies · spends Apollo credits"
                >
                  {updatingFields
                    ? "Updating…"
                    : coSelCount
                      ? `Enrichment ${coSelCount}`
                      : "Enrichment"}
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
                  value={coSearch}
                  onChange={(e) => setCoSearch(e.target.value)}
                />
              </div>
              <select
                className="select"
                value={coStatus}
                onChange={(e) => setCoStatus(e.target.value)}
              >
                <option value="">All status</option>
                <option value="accepted">Accepted</option>
                <option value="pending">Pending</option>
              </select>
              <select className="select" value={coFit} onChange={(e) => setCoFit(e.target.value)}>
                <option value="">Any fit</option>
                <option value="Strong">Strong fit</option>
                <option value="Good">Good fit</option>
                <option value="Moderate">Moderate fit</option>
                <option value="Below">Below</option>
              </select>
              <button className="btn btn-ghost btn-sm" onClick={() => setAddCoOpen(true)}>
                Manual Upload
              </button>
            </div>
            <div className="countrow">
              <b>{coVisible.length}</b>&nbsp;shown&nbsp;·&nbsp;<b>{coSelCount}</b>&nbsp;selected
              {companiesTruncated && (
                <span className="muted">&nbsp;·&nbsp;showing first {LIST_CEILING}</span>
              )}
            </div>
            <div className="list-body">
              {coBusy && (
                <div className="list-overlay" role="status" aria-live="polite">
                  <span className="hs-spinner" aria-hidden="true" />
                  <span>Fetching…</span>
                </div>
              )}
              <div className="list-scroll">
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: 34 }}>
                      <input
                        type="checkbox"
                        className="tbl-check"
                        checked={coAllChecked}
                        onChange={(e) => toggleAllCo(e.target.checked)}
                      />
                    </th>
                    <th>Company</th>
                    <th>AI Score</th>
                    <th>Domain</th>
                    <th>Website</th>
                    <th>Industry</th>
                    <th>Size</th>
                    <th>Source</th>
                    <th>Enrichment</th>
                  </tr>
                </thead>
                {coVisible.length > 0 && (
                  <tbody>
                    {coVisible.map((c) => (
                      <tr key={c.id} className={clsx(companyChecked.has(c.id) && "row-sel")}>
                        <td>
                          <input
                            type="checkbox"
                            className="tbl-check"
                            checked={companyChecked.has(c.id)}
                            onChange={() => toggleCo(c.id)}
                          />
                        </td>
                        <td>
                          <div className="who-cell">
                            <div>
                              {c.status === "people_found" ? (
                                <span className="sel-tag">Accepted</span>
                              ) : null}
                              <div className="nm">{c.name || c.domain}</div>
                              {c.country ? <div className="sub">{c.country}</div> : null}
                            </div>
                          </div>
                        </td>
                        <td>
                          {scoringCoIds.has(c.id) ? (
                            <span className="fit-scoring" title="AI fit-scoring in progress">
                              <span className="hs-spinner" aria-hidden="true" />
                              Scoring…
                            </span>
                          ) : (
                            <FitScore
                              tier={c.fit_tier}
                              score={c.fit_score}
                              reason={c.fit_reason}
                            />
                          )}
                        </td>
                        <td>
                          <span className="domain">{c.domain}</span>
                        </td>
                        <td>
                          <WebLink website={c.website} domain={c.domain} />
                        </td>
                        <td className="muted">{c.industry || "—"}</td>
                        <td className="muted">{c.size || "—"}</td>
                        <td>
                          <span
                            className={clsx("badge", SOURCE_CLS[c.source] ?? "badge-neutral")}
                          >
                            <span className="bdot" />
                            {SOURCE_LABEL[c.source] ?? c.source}
                          </span>
                        </td>
                        <td>
                          <CompanyStudy e={c.enrichment} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                )}
              </table>
              {coVisible.length === 0 && (
                <div className="list-empty muted">
                  No companies match the current scope yet · click Find Companies to search Apollo.
                  <br />
                  {coScopeSummary ? (
                    <>
                      Active filters{scopeOverride ? " (custom)" : ""} · {coScopeSummary}.
                      <br />
                      Too few results? Widen them in ⚙ Settings, or + Add company manually.
                    </>
                  ) : (
                    <>Set your filters in ⚙ Settings, or + Add company manually. Finding is free.</>
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
              <div className="band-actions">
                <button
                  className="btn btn-primary btn-sm"
                  onClick={openPeopleScopeSettings}
                  disabled={!pplScopeLoaded}
                  title={
                    pplScopeLoaded
                      ? "Edit the Apollo people-search filters used by Find People"
                      : "Loading your saved person filters…"
                  }
                >
                  Find Settings
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={runFindPeople}
                  disabled={findingPpl || !pplCoSel.length}
                  title="Find people at the ticked companies (free; enrich spends credits)"
                >
                  {findingPpl
                    ? "Finding…"
                    : pplCoSel.length
                      ? `Find People ${pplCoSel.length}`
                      : "Find People"}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={confirmEnrich}
                  disabled={!canEnrich || enriching}
                  title={
                    canEnrich
                      ? "Enrich the selected Found people · spends Apollo credits"
                      : "Select people marked Found to enrich them."
                  }
                >
                  {enriching
                    ? "Confirming…"
                    : toEnrich.length
                      ? `Enrichment ${toEnrich.length}`
                      : "Enrichment"}
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
              <select
                className="select"
                value={fStatus}
                onChange={(e) => setFStatus(e.target.value)}
              >
                <option value="">All status</option>
                <option value="found">Found</option>
                <option value="scored">Enriched</option>
              </select>
              <select className="select" value={fFit} onChange={(e) => setFFit(e.target.value)}>
                <option value="">Any fit</option>
                <option value="Strong">Strong fit</option>
                <option value="Good">Good fit</option>
                <option value="Moderate">Moderate fit</option>
                <option value="Below">Below</option>
              </select>
              <button className="btn btn-ghost btn-sm" onClick={() => setAddPersonOpen(true)}>
                Manual Upload
              </button>
            </div>
            <div className="countrow">
              <b>{pursued.length}</b>&nbsp;companies&nbsp;·&nbsp;<b>{visible.length}</b>&nbsp;people&nbsp;·&nbsp;
              <b>{selCount}</b>&nbsp;selected
              {prospectsTruncated && (
                <span className="muted">&nbsp;·&nbsp;showing first {LIST_CEILING}</span>
              )}
            </div>
            <div className="list-body">
              {pplBusy && (
                <div className="list-overlay" role="status" aria-live="polite">
                  <span className="hs-spinner" aria-hidden="true" />
                  <span>Fetching…</span>
                </div>
              )}
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
                    <th>AI Score</th>
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
                                onChange={() => toggleCo(c.id)}
                                onClick={(e) => e.stopPropagation()}
                                title="Select this company to find people"
                              />
                              {countBadge}
                            </span>
                            <span className="nm">{c.name || c.domain}</span>
                            {c.domain ? <span className="domain">{c.domain}</span> : null}
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
                              {rows.length === 1 ? "person" : "people"} hidden · click company cell
                              to expand viewing
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
                                className={clsx(i === 0 && "co-start", checked.has(p.id) && "row-sel")}
                              >
                                {i === 0 ? companyCell(rows.length) : null}
                                <td>
                                  <input
                                    type="checkbox"
                                    className="tbl-check"
                                    checked={checked.has(p.id)}
                                    onChange={() => toggleRow(p.id)}
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
                                  {scoringPersonIds.has(p.id) ? (
                                    <span className="fit-scoring" title="AI fit-scoring in progress">
                                      <span className="hs-spinner" aria-hidden="true" />
                                      Scoring…
                                    </span>
                                  ) : (
                                    <FitScore
                                      tier={p.fit_tier}
                                      score={p.fit_score}
                                      reason={p.fit_reason}
                                    />
                                  )}
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
                      No companies in Step 2 yet · go to Step 1, tick companies, and click
                      “Find people for N →”.
                      {pplScopeSummary ? (
                        <>
                          <br />
                          Person filters{peopleScopeOverride ? " (custom)" : ""} · {pplScopeSummary}
                          . Adjust them in ⚙ Settings.
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
                    {toEnrich.length && enrichedSel.length ? (
                      <span className="sub"> · {toEnrich.length} need enrichment first</span>
                    ) : null}
                  </>
                ) : (
                  "Select people to create batch"
                )}
              </span>
              {selectedProspects.length ? (
                <button className="dock-clear" onClick={() => setChecked(new Set())}>
                  Clear
                </button>
              ) : null}
              <span className="dock-spacer" />
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
                        ? "Enrich the Found people first — only enriched people can be batched."
                        : "Select enriched people to batch them."
                  }
                >
                  Create batch →
                </button>
              </div>
            </div>
          </>
        )}
      </div>

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
          <span className="badge badge-neutral">
            rubric v{docs?.[rubricStage]?.version ?? "—"}
          </span>
        </div>
        <div className="prompt-cols">
          {/* LEFT — System prompt: the active stage's rubric, editable + saved as the next version. */}
          <div className="prompt-col">
            <div className="prompt-col-head">
              <label>
                System prompt{" "}
                <span className="badge badge-neutral">v{docs?.[rubricStage]?.version ?? "—"}</span>
              </label>
              <div className="row" style={{ gap: 8, alignItems: "center" }}>
                <button
                  type="button"
                  className="btn btn-accent btn-xs"
                  onClick={() => saveDoc(rubricStage)}
                  disabled={savingDoc === rubricStage}
                >
                  {savingDoc === rubricStage ? "Saving…" : "Save as new version"}
                </button>
              </div>
            </div>
            <textarea
              className="prompt-edit"
              value={rubricDraft}
              spellCheck={false}
              onChange={(e) => setRubricDraft(e.target.value)}
            />
          </div>
          {/* RIGHT — Input prompt: the REAL message the model receives, fetched from the API
              (targeting context = this client's brief + research spec + ICP docs + sample row). */}
          <div className="prompt-col">
            <div className="prompt-col-head">
              <label>Input prompt</label>
              <span className="ph-sub">
                {fitPromptLoading
                  ? "loading…"
                  : fitPrompt?.company
                    ? `read-only · sample: ${fitPrompt.company}`
                    : `read-only · no ${rubricStage === "prospect_fit" ? "prospect" : "company"} yet`}
              </span>
            </div>
            <pre className="prompt-pre">
              {fitPromptLoading
                ? "Loading the input prompt…"
                : fitPromptErr
                  ? fitPromptErr
                  : fitPrompt?.user ||
                    `${
                      rubricStage === "prospect_fit"
                        ? "Find people first to preview a prospect's"
                        : "Find a company first to preview its"
                    } input prompt.`}
            </pre>
          </div>
        </div>
        <div className="ph-sub prompt-hint">
          Edits are saved for this client and used on the next re-score. Each{" "}
          {rubricStage === "prospect_fit" ? "prospect" : "company"} is scored against this rubric
          with the input prompt shown on the right.
        </div>
      </Modal>

      {/* FIND-COMPANY SCOPE SETTINGS — edit the Apollo company-search filters Phase B produced.
          Empty fields are dropped server-side (they simply widen the search). */}
      <Modal
        open={scopeOpen}
        className="modal-lg"
        onClose={() => setScopeOpen(false)}
        title="Find Companies · search filters"
        subtitle="Apollo company-search filters, pre-filled from your AI scope · blank fields are dropped · saved per client for the next Find."
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
        {scopeForm && (
          <>
            <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
              <span className="badge badge-neutral">search · apollo</span>
              <span className="badge badge-info">pre-filled from AI scope</span>
            </div>
            <SpecHead>Company search · firmographics</SpecHead>
            <div className="sourcing-cols">
              <div className="field">
                <label>Keywords · industry / market tags (comma-separated)</label>
                <input
                  className="input"
                  type="text"
                  placeholder="Insurtech, Insurance"
                  value={scopeForm.keywords}
                  onChange={(e) => setScopeForm({ ...scopeForm, keywords: e.target.value })}
                />
              </div>
              <div className="field">
                <label>Locations · HQ country / region (comma-separated)</label>
                <input
                  className="input"
                  type="text"
                  placeholder="hong kong, singapore, thailand"
                  value={scopeForm.locations}
                  onChange={(e) => setScopeForm({ ...scopeForm, locations: e.target.value })}
                />
              </div>
            </div>
            <div className="sourcing-cols" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div className="field">
                <label>Employee size ranges · min,max (; for more)</label>
                <input
                  className="input"
                  type="text"
                  placeholder="10,100 ; 101,500"
                  value={scopeForm.sizes}
                  onChange={(e) => setScopeForm({ ...scopeForm, sizes: e.target.value })}
                />
              </div>
              <div className="field">
                <label>Revenue min (USD)</label>
                <input
                  className="input"
                  type="number"
                  placeholder="(any)"
                  value={scopeForm.revenueMin}
                  onChange={(e) => setScopeForm({ ...scopeForm, revenueMin: e.target.value })}
                />
              </div>
              <div className="field">
                <label>Revenue max (USD)</label>
                <input
                  className="input"
                  type="number"
                  placeholder="(any)"
                  value={scopeForm.revenueMax}
                  onChange={(e) => setScopeForm({ ...scopeForm, revenueMax: e.target.value })}
                />
              </div>
            </div>
            <SpecHead>Buying signals (intent) · optional, narrows hard</SpecHead>
            <div className="field">
              <label>Hiring for job titles (comma-separated)</label>
              <input
                className="input"
                type="text"
                placeholder="sales, growth, commercial"
                value={scopeForm.hiringTitles}
                onChange={(e) => setScopeForm({ ...scopeForm, hiringTitles: e.target.value })}
              />
            </div>
            <div className="sourcing-cols" style={{ gridTemplateColumns: "1fr 1fr 1fr 1fr" }}>
              <div className="field">
                <label>Funded since</label>
                <input
                  className="input"
                  type="date"
                  value={scopeForm.fundedMin}
                  onChange={(e) => setScopeForm({ ...scopeForm, fundedMin: e.target.value })}
                />
              </div>
              <div className="field">
                <label>Funded until</label>
                <input
                  className="input"
                  type="date"
                  value={scopeForm.fundedMax}
                  onChange={(e) => setScopeForm({ ...scopeForm, fundedMax: e.target.value })}
                />
              </div>
              <div className="field">
                <label>Jobs posted since</label>
                <input
                  className="input"
                  type="date"
                  value={scopeForm.jobsMin}
                  onChange={(e) => setScopeForm({ ...scopeForm, jobsMin: e.target.value })}
                />
              </div>
              <div className="field">
                <label>Jobs posted until</label>
                <input
                  className="input"
                  type="date"
                  value={scopeForm.jobsMax}
                  onChange={(e) => setScopeForm({ ...scopeForm, jobsMax: e.target.value })}
                />
              </div>
            </div>
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
                Tick one or more companies in the Step-2 list to load live counts and the
                department options.
              </p>
            )}

            <SpecHead>Management Level{pplFacetsLoading ? " · loading…" : ""}</SpecHead>
            <div className="facet-grid">
              {SENIORITY_OPTIONS.map((o) => {
                const count = pplFacets?.seniorities.find((s) => s.value === o.value)?.count;
                return (
                  <label key={o.value} className="facet-row">
                    <input
                      type="checkbox"
                      className="tbl-check"
                      checked={peopleScopeForm.seniorities.includes(o.value)}
                      onChange={() => toggleFacet("seniorities", o.value)}
                    />
                    <span className="facet-label">{o.label}</span>
                    {count != null && <span className="facet-count">{count}</span>}
                  </label>
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
                  <label key={d.value} className="facet-row">
                    <input
                      type="checkbox"
                      className="tbl-check"
                      checked={peopleScopeForm.departments.includes(d.value)}
                      onChange={() => toggleFacet("departments", d.value)}
                    />
                    <span className="facet-label">{d.label}</span>
                    {d.count != null && <span className="facet-count">{d.count}</span>}
                  </label>
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
                    <label key={o.value} className="facet-row">
                      <input
                        type="checkbox"
                        className="tbl-check"
                        checked={peopleScopeForm.departments.includes(o.value)}
                        onChange={() => toggleFacet("departments", o.value)}
                      />
                      <span className="facet-label">{o.label}</span>
                    </label>
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
          <>
            <button className="btn btn-ghost btn-sm" onClick={() => setAddCoOpen(false)}>
              Cancel
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={submitAddCompany}
              disabled={savingCo || !coForm.domain.trim()}
            >
              {savingCo ? "Scoring…" : "Add + score"}
            </button>
          </>
        }
      >
        <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
          <span className="badge badge-neutral">source · manual</span>
          <span className="badge badge-info">fit-scored on add</span>
        </div>
        <div className="field">
          <label>Company domain *</label>
          <input
            className="input"
            type="text"
            placeholder="acme.com"
            value={coForm.domain}
            onChange={(e) => setCoForm({ ...coForm, domain: e.target.value })}
          />
        </div>
        <div className="field">
          <label>Name</label>
          <input
            className="input"
            type="text"
            placeholder="Acme Robotics"
            value={coForm.name}
            onChange={(e) => setCoForm({ ...coForm, name: e.target.value })}
          />
        </div>
        <div className="field">
          <label>Website</label>
          <input
            className="input"
            type="text"
            placeholder="https://acme.com"
            value={coForm.website}
            onChange={(e) => setCoForm({ ...coForm, website: e.target.value })}
          />
        </div>
        <div className="sourcing-cols">
          <div className="field">
            <label>Industry</label>
            <input
              className="input"
              type="text"
              value={coForm.industry}
              onChange={(e) => setCoForm({ ...coForm, industry: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Size</label>
            <input
              className="input"
              type="text"
              placeholder="201-500"
              value={coForm.size}
              onChange={(e) => setCoForm({ ...coForm, size: e.target.value })}
            />
          </div>
        </div>
        <div className="sourcing-cols">
          <div className="field">
            <label>Country</label>
            <input
              className="input"
              type="text"
              value={coForm.country}
              onChange={(e) => setCoForm({ ...coForm, country: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Company LinkedIn</label>
            <input
              className="input"
              type="text"
              placeholder="linkedin.com/company/…"
              value={coForm.linkedin_url}
              onChange={(e) => setCoForm({ ...coForm, linkedin_url: e.target.value })}
            />
          </div>
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
          <>
            <button className="btn btn-ghost btn-sm" onClick={() => setAddPersonOpen(false)}>
              Cancel
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={submitAddPerson}
              disabled={savingPerson}
            >
              {savingPerson ? "Scoring…" : "Add + score"}
            </button>
          </>
        }
      >
        <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
          <span className="badge badge-neutral">source · manual</span>
          <span className="badge badge-info">fit-scored on add</span>
        </div>
        <div className="sourcing-cols">
          <div className="field">
            <label>Full name</label>
            <input
              className="input"
              type="text"
              value={personForm.full_name}
              onChange={(e) => setPersonForm({ ...personForm, full_name: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Title</label>
            <input
              className="input"
              type="text"
              placeholder="VP Engineering"
              value={personForm.title}
              onChange={(e) => setPersonForm({ ...personForm, title: e.target.value })}
            />
          </div>
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
        <div className="field">
          <label>LinkedIn URL</label>
          <input
            className="input"
            type="text"
            placeholder="linkedin.com/in/…"
            value={personForm.linkedin_url}
            onChange={(e) => setPersonForm({ ...personForm, linkedin_url: e.target.value })}
          />
        </div>
        <div className="field">
          <label>Email (optional — leave blank to enrich later)</label>
          <input
            className="input"
            type="text"
            value={personForm.email}
            onChange={(e) => setPersonForm({ ...personForm, email: e.target.value })}
          />
        </div>
        <div className="ph-sub" style={{ marginTop: 16 }}>
          LinkedIn URL, name + company domain, or email · rest optional · scored on save.
        </div>
      </Modal>
    </section>
  );
}
