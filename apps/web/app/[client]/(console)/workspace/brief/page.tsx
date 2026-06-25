"use client";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useClient } from "@/lib/nav";
import clsx from "clsx";
import { useToast } from "@/components/Toast";
import { type RowError, mergeExclusionText, parseExclusionCsv } from "@/lib/csv";
import {
  type IcpSuggestion,
  type ResearchJob,
  type ResearchSpecResult,
  createIcp as apiCreateIcp,
  deleteIcp as apiDeleteIcp,
  updateIcp as apiUpdateIcp,
  getBrief,
  getResearchSpec,
  getStructureStatus,
  listIcps,
  putBrief,
  structureBrief,
} from "@/lib/api";
import type { Brief, Icp, IcpFields } from "@/lib/workspace/types";
import {
  CHANNEL_OPTS,
  CYCLE_OPTS,
  EXCL_PLACEHOLDER,
  EXCL_TEXT_KEY,
  LANGUAGE_OPTS,
  MATURITY_OPTS,
  MAX_CSV_BYTES,
  MAX_CSV_ROWS,
  SENIORITY_OPTS,
  TONE_OPTS,
  apiToIcp,
  blankBrief,
  blankFields,
  blankIcp,
  icpToApi,
  sleep,
} from "@/lib/workspace/constants";
import {
  CsvErrors,
  ExclFormat,
  Lbl,
  PillGroup,
  Section,
  SpecReview,
  TagInput,
} from "@/components/workspace";

// Coerce a stored brief document into the form's Brief shape (defensive on multi-value fields + the
// meetingsLand→attendeeEmails read-migration). Shared by the cache lazy-init and the loader so a
// cached tab-return seeds the exact same form state a fresh load would.
function briefFromDoc(b: Awaited<ReturnType<typeof getBrief>> | null): Brief {
  const d = (b?.data ?? {}) as Partial<Brief>;
  return {
    ...blankBrief(),
    ...d,
    valueProps: Array.isArray(d.valueProps) ? d.valueProps : blankBrief().valueProps,
    languages: Array.isArray(d.languages) ? d.languages : [],
    attendeeEmails:
      d.attendeeEmails ||
      (typeof (d as Record<string, unknown>).meetingsLand === "string"
        ? ((d as Record<string, unknown>).meetingsLand as string)
        : ""),
    noExcludeCustomers: !!d.noExcludeCustomers,
    noExcludeDeals: !!d.noExcludeDeals,
    noDoNotContact: !!d.noDoNotContact,
  };
}

export default function BriefPage() {
  const client = useClient();
  // Cross-navigation cache for this page's API reads (brief/icps/spec). Keyed by client so a tab
  // switch returns instantly from cache (see app/providers.tsx); writes below sync the cache.
  const qc = useQueryClient();
  const toast = useToast();
  // Tracks the live client so an async poll that resolves *after* a client switch can bail before
  // writing the previous client's spec into the new client's view (used by pollStructuring).
  const clientRef = useRef(client);
  useEffect(() => {
    clientRef.current = client;
  }, [client]);

  // ICPs
  // Starts with one empty profile so `icps[icpSel]` is always defined; the live ICPs from
  // the API replace this on load (or it stays as the first, unsaved profile).
  const [icps, setIcps] = useState<Icp[]>(() => {
    const cached = qc.getQueryData<Awaited<ReturnType<typeof listIcps>>>(["icps", client]);
    return cached && cached.length ? cached.map(apiToIcp) : [blankIcp()];
  });
  const [icpSel, setIcpSel] = useState(0);
  function newIcp() {
    // Functional append so two rapid clicks can't collide on the same letter/length;
    // capture the new index from the same snapshot so the selection can't go stale either.
    let added = 0;
    setIcps((s) => {
      added = s.length;
      return [
        ...s,
        {
          short: "ICP " + String.fromCharCode(65 + s.length),
          tag: "",
          persona: "",
          fields: blankFields(),
        },
      ];
    });
    setIcpSel(added);
    toast("ICP profile created");
  }
  // Accept an LLM ICP suggestion (derived from the customer list) → a new, prefilled ICP the
  // founder reviews and saves. Jumps to the ICP section so it's edited in context.
  function acceptIcpSuggestion(sug: IcpSuggestion) {
    let added = 0;
    setIcps((s) => {
      added = s.length;
      return [
        ...s,
        {
          short: sug.name || "ICP " + String.fromCharCode(65 + s.length),
          tag: "from customers",
          persona: "",
          fields: {
            ...blankFields(),
            industries: sug.company_search_params?.q_organization_keyword_tags ?? [],
            // Personas are facets now (Management Level × Department), not free-text titles — the
            // operator fills the ICP's target titles; the facets drive Apollo directly.
            jobTitles: [],
          },
        },
      ];
    });
    setIcpSel(added);
    setOpenSec(2);
    toast("ICP added from suggestion · review & save");
  }
  function delIcp() {
    if (icps.length <= 1) return toast("Keep at least one ICP", "warn");
    const cur = icps[icpSel];
    if (cur.id) setDeletedIcpIds((s) => [...s, cur.id!]);
    const next = icps.filter((_, i) => i !== icpSel);
    setIcps(next);
    setIcpSel((s) => Math.min(s, next.length - 1));
    toast(cur.short + " deleted", "warn");
  }
  const updateIcp = (patch: Partial<Icp>) =>
    setIcps((s) => s.map((x, i) => (i === icpSel ? { ...x, ...patch } : x)));
  const setIcpField = <K extends keyof IcpFields>(key: K, val: IcpFields[K]) =>
    setIcps((s) =>
      s.map((x, i) => (i === icpSel ? { ...x, fields: { ...x.fields, [key]: val } } : x))
    );

  // Business brief (global sections)
  const [brief, setBrief] = useState<Brief>(() => {
    const cached = qc.getQueryData<Awaited<ReturnType<typeof getBrief>>>(["brief", client]);
    return cached ? briefFromDoc(cached) : blankBrief();
  });
  const [submitted, setSubmitted] = useState(false);
  // CSV attachment name per exclusion field (keyed: "customers", "deals")
  const [csvNames, setCsvNames] = useState<Record<string, string>>({});
  // Invalid/skipped rows from the last import, per field — shown back to the user.
  const [csvErrors, setCsvErrors] = useState<Record<string, RowError[]>>({});
  // CSV import: parse → validate against the three-column contract → merge valid rows
  // (dedupe by domain) into the field → persist immediately → report skipped rows.
  // Called from an inline arrow at each <input> (not curried in JSX) so it's recognised as an
  // event handler — letting persist() read its refs without a refs-during-render warning.
  const onCsv = async (
    key: "customers" | "deals" | "doNotContact",
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-uploading the same file
    if (!file) return;

    const textKey = EXCL_TEXT_KEY[key];
    if (!/\.csv$/i.test(file.name) && file.type !== "text/csv") {
      toast("Please upload a .csv file", "warn");
      return;
    }
    if (file.size > MAX_CSV_BYTES) {
      toast("CSV is too large (max 1 MB)", "warn");
      return;
    }
    let text: string;
    try {
      text = await file.text();
    } catch {
      toast("Could not read the file", "warn");
      return;
    }

    const { valid, errors, total } = parseExclusionCsv(text);
    if (total > MAX_CSV_ROWS) {
      toast(`CSV has too many rows (max ${MAX_CSV_ROWS.toLocaleString()})`, "warn");
      return;
    }
    if (valid.length === 0 && errors.length === 0) {
      toast("No rows found in the CSV", "warn");
      return;
    }

    setCsvNames((s) => ({ ...s, [key]: file.name }));
    setCsvErrors((s) => ({ ...s, [key]: errors }));

    if (valid.length === 0) {
      toast("No valid rows — see the issues below", "warn");
      return;
    }

    const { text: merged, added, duplicates } = mergeExclusionText(brief[textKey], valid);
    const next = { ...brief, [textKey]: merged };
    setBrief(next);

    const parts = [`Imported ${added}`];
    if (duplicates) parts.push(`${duplicates} duplicate${duplicates > 1 ? "s" : ""} skipped`);
    if (errors.length) parts.push(`${errors.length} invalid skipped`);
    toast(parts.join(" · "));
    void persist(next); // save to DB immediately (state updates are async — pass the snapshot)
  };
  const setB = <K extends keyof Brief>(key: K, val: Brief[K]) =>
    setBrief((s) => ({ ...s, [key]: val }));
  // "Nothing to exclude" attestation: ticking it clears (and locks) the matching
  // list + any attached CSV so we never carry contradictory data into sourcing.
  const setNoExclude =
    (
      flag: "noExcludeCustomers" | "noExcludeDeals" | "noDoNotContact",
      textKey: "excludeCustomers" | "excludeDeals" | "doNotContact",
      csvKey: string
    ) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const on = e.target.checked;
      setBrief((s) => ({ ...s, [flag]: on, ...(on ? { [textKey]: "" } : {}) }));
      if (on) {
        setCsvNames((s) => ({ ...s, [csvKey]: "" }));
        setCsvErrors((s) => ({ ...s, [csvKey]: [] }));
      }
    };
  const setValueProp = (i: number, val: string) =>
    setBrief((s) => {
      const next = [...s.valueProps];
      next[i] = val;
      return { ...s, valueProps: next };
    });
  const f = icps[icpSel].fields;

  // accordion: one section open at a time (0 = all collapsed). Starts collapsed; an effect
  // auto-opens the earliest still-incomplete section once the brief hydrates (see below).
  const [openSec, setOpenSec] = useState(0);
  // True once we've auto-opened a section for the current client load (so manual toggles stick).
  const autoOpenedRef = useRef(false);
  // after a section opens, bring its title bar to the top (below the sticky bars)
  const scrollToSec = (n: number) =>
    setTimeout(
      () =>
        document
          .getElementById("brief-sec-" + n)
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      60
    );
  const toggle = (n: number) => {
    const next = openSec === n ? 0 : n;
    setOpenSec(next);
    if (next) scrollToSec(next);
  };
  // --- Phase B: live brief + ICP + ResearchSpec ----------------------------
  const [saving, setSaving] = useState(false);
  const [structuring, setStructuring] = useState(false);
  // True while the brief/ICP/spec are hydrating for this client (initial load + client switch).
  const [loading, setLoading] = useState(() => !qc.getQueryData(["brief", client]));
  const [spec, setSpec] = useState<ResearchSpecResult | null>(() => {
    const cached = qc.getQueryData<Awaited<ReturnType<typeof getResearchSpec>>>([
      "research-spec",
      client,
    ]);
    return cached?.latest ?? null;
  });
  // IDs of saved ICPs the operator has deleted; flushed to the API on the next save.
  const [deletedIcpIds, setDeletedIcpIds] = useState<string[]>([]);
  // Guards against concurrent persist() runs (rapid section saves / save-during-structure).
  const savingRef = useRef(false);
  // Latest snapshot that arrived while a save was in flight — flushed when it finishes, so a
  // CSV import (or any edit) saved mid-save isn't silently dropped. Last-write-wins.
  const pendingBriefRef = useRef<Brief | null>(null);

  // Hydrate the brief + ICPs + latest spec for this client.
  useEffect(() => {
    if (!client) return;
    let alive = true;
    autoOpenedRef.current = false; // re-pick the earliest-incomplete section for this client
    (async () => {
      // Only show the full-page spinner when there's nothing cached to show; a tab-return with a warm
      // cache renders the form immediately (the fetchQuery calls below resolve from cache, no network).
      setLoading(!qc.getQueryData(["brief", client]));
      // Load independently so one failing endpoint doesn't blank the others. fetchQuery serves the
      // cached payload when fresh (instant, no request) and refetches in the background when stale.
      const b = await qc
        .fetchQuery({ queryKey: ["brief", client], queryFn: () => getBrief(client) })
        .catch(() => null);
      const ics = await qc
        .fetchQuery({ queryKey: ["icps", client], queryFn: () => listIcps(client) })
        .catch(() => null);
      const rs = await qc
        .fetchQuery({ queryKey: ["research-spec", client], queryFn: () => getResearchSpec(client) })
        .catch(() => null);
      if (!alive) return;
      // Coerce the multi-value fields to arrays so the controlled inputs never crash on a malformed
      // document (the form always writes arrays, but be defensive on read) — see briefFromDoc.
      if (b) setBrief(briefFromDoc(b));
      if (ics) {
        setIcps(ics.length ? ics.map(apiToIcp) : [blankIcp()]);
        setIcpSel(0);
        setDeletedIcpIds([]);
      }
      if (rs) {
        setSpec(rs.latest);
      }
      setLoading(false);
      // Resume polling if a structuring job is still running from before this load (e.g. a refresh
      // mid-generation) — the worker runs server-side, so reattach the spinner + pick up the result.
      const job = await getStructureStatus(client).catch(() => null);
      if (alive && job && (job.status === "queued" || job.status === "running")) {
        setStructuring(true);
        pollStructuring(job, client).finally(() => {
          if (alive) setStructuring(false);
        });
      }
    })();
    return () => {
      alive = false;
    };
    // Re-runs only on client change: pollStructuring captures its client via startClient/clientRef
    // and qc is a stable QueryClient, so neither is a real dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client]);

  // Persist the brief + sync every ICP (create new, update existing, delete removed).
  // Sequential so a new ICP's server id is recorded immediately — a mid-sync failure can
  // never cause the same ICP to be re-created (and duplicated) on the next save.
  async function persist(briefSnapshot: Brief = brief) {
    if (savingRef.current) {
      // Don't drop — queue the latest snapshot and flush it when the in-flight save finishes.
      pendingBriefRef.current = briefSnapshot;
      return;
    }
    savingRef.current = true;
    setSaving(true);
    try {
      const saved = await putBrief(client, briefSnapshot as unknown as Record<string, unknown>);
      // Keep the nav cache in sync so a tab-return after saving shows the saved brief, not a stale one.
      qc.setQueryData(["brief", client], saved);
      for (const icp of icps) {
        if (icp.id) {
          await apiUpdateIcp(client, icp.id, icpToApi(icp));
        } else {
          const created = await apiCreateIcp(client, icpToApi(icp));
          // Record the new id immediately (reference-matched) so it survives a later failure.
          setIcps((s) => s.map((x) => (x === icp ? { ...x, id: created.id } : x)));
        }
      }
      for (const id of deletedIcpIds) await apiDeleteIcp(client, id);
      setDeletedIcpIds([]);
      // ICPs changed — drop the cached list so the next read (here or on the List tab) refetches.
      qc.invalidateQueries({ queryKey: ["icps", client] });
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
    // Flush a save that arrived mid-flight (e.g. a CSV import). Latest snapshot only.
    const queued = pendingBriefRef.current;
    if (queued) {
      pendingBriefRef.current = null;
      await persist(queued);
    }
  }

  // Poll the async structuring worker (DeepSeek V4 Pro scoping runs ~1 min off the request path)
  // to a terminal state, then load the produced spec. Shared by the Generate button + on-load
  // resume (a job can still be running after a refresh). `startClient` pins the call to the client
  // that launched it, so a mid-run client switch never writes another client's spec.
  async function pollStructuring(job: ResearchJob, startClient: string) {
    const deadline = Date.now() + 4 * 60 * 1000; // generous cap; worker keeps running server-side
    const stillCurrent = () => clientRef.current === startClient;
    while ((job.status === "queued" || job.status === "running") && Date.now() < deadline) {
      await sleep(3000);
      if (!stillCurrent()) return; // client switched away — stop polling, don't write a stale spec/toast
      job = await getStructureStatus(startClient);
    }
    if (!stillCurrent()) return;
    if (job.status === "done") {
      const rs = await getResearchSpec(startClient);
      setSpec(rs.latest);
      qc.setQueryData(["research-spec", startClient], rs); // new spec → refresh the nav cache
      toast("Prospect scope v" + (job.spec_version ?? rs.latest?.version ?? "") + " generated");
    } else if (job.status === "error") {
      toast(job.error || "Structuring failed", "warn");
    } else {
      toast("Still generating — this can take ~1 min; it'll appear when ready.", "warn");
    }
  }

  // Save the brief + ICPs, then kick off async structuring and poll it to completion.
  async function runStructure() {
    setStructuring(true);
    try {
      await persist();
      const job = await structureBrief(client); // 202 — returns the job to poll
      await pollStructuring(job, client);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Structuring failed", "warn");
    } finally {
      setStructuring(false);
    }
  }

  async function saveAndContinue(cur: number) {
    // Surface missing required fields once the operator tries to save.
    setSubmitted(true);
    let ok = true;
    try {
      await persist(); // confirm the save before claiming progress
    } catch (e) {
      ok = false;
      toast(e instanceof Error ? e.message : "Save failed", "warn");
    }
    if (ok) toast("Saved");
    const order = [1, 2, 3, 4, 5, 6];
    const next = order.find((n) => n > cur && !secComplete[n]) ?? (cur < 6 ? cur + 1 : cur);
    setOpenSec(next);
    if (next !== cur) scrollToSec(next);
  }

  const filled = (v: string | string[]) => (Array.isArray(v) ? v.length > 0 : v.trim() !== "");
  const icpReady = icps.every(
    (p) =>
      p.fields.industries.length &&
      p.fields.companySize.trim() &&
      p.fields.geographies.length &&
      p.fields.jobTitles.length &&
      p.fields.seniority.length &&
      p.fields.departments.length
  );
  // Required fields per section, as booleans (filled = true). Drives both the
  // per-section "x/N" counter and the Complete/Pending status. Section 2's
  // counter tracks the ICP currently being edited (f); its Complete badge still
  // requires every ICP to be ready (icpReady).
  const secReq: Record<number, boolean[]> = {
    1: [
      filled(brief.companyName),
      filled(brief.website),
      filled(brief.sell),
      filled(brief.problem),
      filled(brief.dealSize),
      filled(brief.salesCycle),
    ],
    2: [
      filled(f.industries),
      filled(f.companySize),
      filled(f.geographies),
      filled(f.jobTitles),
      filled(f.seniority),
      filled(f.departments),
    ],
    3: [
      brief.valueProps.some((v) => v.trim()),
      filled(brief.proofPoints),
      filled(brief.signals),
      filled(brief.tone),
      brief.languages.length > 0,
    ],
    4: [
      filled(brief.excludeCustomers) || brief.noExcludeCustomers,
      filled(brief.excludeDeals) || brief.noExcludeDeals,
    ],
    5: [
      filled(brief.attendeeEmails),
      filled(brief.attendees),
      filled(brief.availability),
      filled(brief.channel),
      filled(brief.contact),
      filled(brief.approver),
    ],
    6: [filled(brief.meetingsPerMonth), filled(brief.qualifiedDef)],
  };
  const secCount = (n: number) => ({
    done: secReq[n].filter(Boolean).length,
    total: secReq[n].length,
  });
  // per-section completeness (drives the status label + the top bar)
  const secComplete: Record<number, boolean> = {
    1: secReq[1].every(Boolean),
    2: icpReady,
    3: secReq[3].every(Boolean),
    4: secReq[4].every(Boolean),
    5: secReq[5].every(Boolean),
    6: secReq[6].every(Boolean),
  };
  // Top-bar percentage tracks required fields filled across all sections (not sections done /6),
  // so each field moves the bar rather than only a whole completed section.
  const allReq = Object.values(secReq).flat();
  const completePct = Math.round((allReq.filter(Boolean).length / allReq.length) * 100);
  // Prospect-Scope gating stays section-based (every ICP ready, not just the current one), so the
  // field-based bar above can read 100% without unblocking before all sections are truly done.
  const allComplete = Object.values(secComplete).every(Boolean);
  // The earliest section still missing required fields (0 = none — every section is complete).
  const firstIncompleteSec = ([1, 2, 3, 4, 5, 6] as const).find((n) => !secComplete[n]) ?? 0;
  // On load / client switch, open that section (or collapse all when nothing is left). Runs once
  // per load — guarded by autoOpenedRef so a later edit completing a section won't yank it shut.
  useEffect(() => {
    if (loading || autoOpenedRef.current) return;
    autoOpenedRef.current = true;
    setOpenSec(firstIncompleteSec);
  }, [loading, firstIncompleteSec]);
  const errCls = (ok: boolean, base = "input") => clsx(base, submitted && !ok && "err");

  return (
    <section className="tabpane active">
      {loading ? (
        <div className="panel">
          <div className="panel-loading">
            <span className="hs-spinner" aria-hidden="true" />
            Loading your brief…
          </div>
        </div>
      ) : (
        <>
          <div className="brief-top">
            <div className="brief-legend">
              <span>
                <span className="brief-req">Required</span> Needed before we start
              </span>
              <span>
                <span className="brief-opt">Optional</span> Helpful, not essential
              </span>
            </div>
            <div className="brief-progress">
              <div className="bp-bar">
                <div className="bp-fill" style={{ width: completePct + "%" }} />
              </div>
              <span className="bp-label">{completePct}% complete</span>
            </div>
          </div>

          {/* 1 · Company & Product Basics */}
          <Section
            num={1}
            title="Company & Product Basics"
            sub="Who you are and what you sell"
            complete={secComplete[1]}
            count={secCount(1)}
            open={openSec === 1}
            onToggle={() => toggle(1)}
            onContinue={() => saveAndContinue(1)}
          >
            <div className="panel-pad">
              <div className="grid2">
                <div className="field">
                  <Lbl
                    req
                    done={filled(brief.companyName)}
                    help="The brand name as it should appear in email signatures."
                  >
                    Company name
                  </Lbl>
                  <input
                    className={errCls(filled(brief.companyName))}
                    value={brief.companyName}
                    placeholder="e.g. Acme Analytics"
                    onChange={(e) => setB("companyName", e.target.value)}
                  />
                </div>
                <div className="field">
                  <Lbl
                    req
                    done={filled(brief.website)}
                    help="Used for enrichment context and to verify what you sell."
                  >
                    Website
                  </Lbl>
                  <input
                    type="url"
                    className={errCls(filled(brief.website))}
                    value={brief.website}
                    placeholder="https://"
                    onChange={(e) => setB("website", e.target.value)}
                  />
                </div>
              </div>
              <div className="field">
                <Lbl
                  req
                  done={filled(brief.sell)}
                  help="If you can't say it cleanly in one line, the campaign suffers. Keep it simple."
                >
                  What do you sell, in one sentence?
                </Lbl>
                <input
                  className={errCls(filled(brief.sell))}
                  value={brief.sell}
                  placeholder="e.g. A workforce analytics platform that reduces attrition"
                  onChange={(e) => setB("sell", e.target.value)}
                />
              </div>
              <div className="field">
                <Lbl
                  req
                  done={filled(brief.problem)}
                  help="Not the features, the underlying problem. This becomes the spine of every message."
                >
                  What problem do you solve for your customers?
                </Lbl>
                <textarea
                  className={errCls(filled(brief.problem), "textarea")}
                  value={brief.problem}
                  onChange={(e) => setB("problem", e.target.value)}
                />
              </div>
              <div className="grid2">
                <div className="field" style={{ marginBottom: 0 }}>
                  <Lbl
                    req
                    done={filled(brief.dealSize)}
                    help="Annual contract value. Determines whether the unit economics work."
                  >
                    Average deal size (annual)
                  </Lbl>
                  <input
                    className={errCls(filled(brief.dealSize))}
                    value={brief.dealSize}
                    placeholder="e.g. $25,000 / year"
                    onChange={(e) => setB("dealSize", e.target.value)}
                  />
                </div>
                <div className="field" style={{ marginBottom: 0 }}>
                  <Lbl
                    req
                    done={filled(brief.salesCycle)}
                    help="Shapes follow-up cadence and time-to-revenue."
                  >
                    Typical sales cycle length
                  </Lbl>
                  <select
                    className={errCls(filled(brief.salesCycle), "select")}
                    value={brief.salesCycle}
                    onChange={(e) => setB("salesCycle", e.target.value)}
                  >
                    <option value="">Select…</option>
                    {CYCLE_OPTS.map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </Section>

          {/* 2 · Ideal Customer Profiles (ICP + Personas, per profile) */}
          <Section
            num={2}
            title="Ideal Customer Profiles"
            sub="The companies and people to reach · one block per profile"
            complete={secComplete[2]}
            count={secCount(2)}
            open={openSec === 2}
            onToggle={() => toggle(2)}
            onContinue={() => saveAndContinue(2)}
            hideFoot
          >
            <div className="panel-pad">
              <div className="brief-subdiv first">ICP List</div>
              <div className="icp-tabs">
                {icps.map((p, i) => (
                  <button
                    key={p.id ?? "new-" + i}
                    className={clsx("icp-pill", i === icpSel && "on")}
                    onClick={() => setIcpSel(i)}
                  >
                    <div className="ipn">{p.short}</div>
                    {p.tag && <div className="ipt">{p.tag}</div>}
                  </button>
                ))}
                <button className="icp-pill add" onClick={newIcp}>
                  ＋ New ICP
                </button>
              </div>

              <div className="grid2">
                <div className="field">
                  <label>ICP name</label>
                  <input
                    className="input"
                    value={icps[icpSel].short}
                    placeholder="e.g. ICP A"
                    onChange={(e) => updateIcp({ short: e.target.value })}
                  />
                </div>
                <div className="field">
                  <label>Segment label</label>
                  <input
                    className="input"
                    value={icps[icpSel].tag}
                    placeholder="e.g. Primary persona"
                    onChange={(e) => updateIcp({ tag: e.target.value })}
                  />
                </div>
              </div>
              <div className="field">
                <label>
                  Persona <span className="opt">· optional</span>
                </label>
                <textarea
                  className="textarea"
                  value={icps[icpSel].persona}
                  placeholder="Describe this buyer profile, their role, and why they buy."
                  onChange={(e) => updateIcp({ persona: e.target.value })}
                />
              </div>

              <div className="brief-subdiv">Ideal Customer Profile</div>
              <div className="field">
                <Lbl
                  req
                  done={filled(f.industries)}
                  help={
                    'List the specific sectors. "Everyone" usually means the targeting needs sharpening.'
                  }
                >
                  Target industries / verticals
                </Lbl>
                <TagInput
                  value={f.industries}
                  onChange={(v) => setIcpField("industries", v)}
                  placeholder="Type a sector, press Enter"
                  invalid={submitted && !f.industries.length}
                />
              </div>
              <div className="grid2">
                <div className="field">
                  <Lbl req done={filled(f.companySize)} help="By employee count and/or revenue.">
                    Target company size
                  </Lbl>
                  <input
                    className={errCls(filled(f.companySize))}
                    value={f.companySize}
                    placeholder="e.g. 50–500 employees"
                    onChange={(e) => setIcpField("companySize", e.target.value)}
                  />
                </div>
                <div className="field">
                  <Lbl done={filled(f.maturity)} help="Helps refine list and tone.">
                    Company maturity / stage
                  </Lbl>
                  <select
                    className="select"
                    value={f.maturity}
                    onChange={(e) => setIcpField("maturity", e.target.value)}
                  >
                    <option value="">Select…</option>
                    {MATURITY_OPTS.map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="field">
                <Lbl
                  req
                  done={filled(f.geographies)}
                  help="Countries, regions, or cities to focus on."
                >
                  Target geographies
                </Lbl>
                <TagInput
                  value={f.geographies}
                  onChange={(v) => setIcpField("geographies", v)}
                  placeholder="e.g. United States, UK, Singapore"
                  invalid={submitted && !f.geographies.length}
                />
              </div>
              <div className="field">
                <Lbl
                  done={filled(f.technologies)}
                  help="If you can answer this, it unlocks tech-stack-based targeting."
                >
                  Technologies your ideal customer uses
                </Lbl>
                <TagInput
                  value={f.technologies}
                  onChange={(v) => setIcpField("technologies", v)}
                  placeholder="e.g. Salesforce, Shopify, Workday"
                />
              </div>

              <div className="brief-subdiv">Target personas</div>
              <div className="field">
                <Lbl
                  req
                  done={filled(f.jobTitles)}
                  help={'The exact titles, not "decision makers". Be specific.'}
                >
                  Primary job titles to target
                </Lbl>
                <TagInput
                  value={f.jobTitles}
                  onChange={(v) => setIcpField("jobTitles", v)}
                  placeholder="e.g. Head of Sales, VP Sales, CRO"
                  invalid={submitted && !f.jobTitles.length}
                />
              </div>
              <div className="field">
                <Lbl req done={filled(f.seniority)} help="Select all that apply.">
                  Seniority level
                </Lbl>
                <PillGroup
                  options={SENIORITY_OPTS}
                  value={f.seniority}
                  onChange={(v) => setIcpField("seniority", v)}
                  invalid={submitted && !f.seniority.length}
                />
              </div>
              <div className="grid2">
                <div className="field">
                  <Lbl req done={filled(f.departments)} help="Which teams these people sit in.">
                    Departments / functions
                  </Lbl>
                  <TagInput
                    value={f.departments}
                    onChange={(v) => setIcpField("departments", v)}
                    placeholder="e.g. Sales, Marketing, Finance"
                    invalid={submitted && !f.departments.length}
                  />
                </div>
                <div className="field">
                  <Lbl
                    done={filled(f.buyerVsChampion)}
                    help="Often different people. Shapes who we target first."
                  >
                    Economic buyer vs. champion
                  </Lbl>
                  <input
                    className="input"
                    value={f.buyerVsChampion}
                    placeholder="e.g. CFO signs off, Head of Ops champions"
                    onChange={(e) => setIcpField("buyerVsChampion", e.target.value)}
                  />
                </div>
              </div>
              <div className="field">
                <Lbl
                  done={filled(f.avoidTitles)}
                  help="Personas that look right but never convert."
                >
                  Titles to explicitly avoid
                </Lbl>
                <TagInput
                  value={f.avoidTitles}
                  onChange={(v) => setIcpField("avoidTitles", v)}
                  placeholder="e.g. Procurement, junior analysts"
                />
              </div>

              <div className="icp-foot">
                <div className="row">
                  <button className="btn btn-danger btn-sm" onClick={delIcp}>
                    Delete
                  </button>
                  <button className="btn btn-accent btn-sm" onClick={() => saveAndContinue(2)}>
                    Save &amp; continue
                  </button>
                </div>
              </div>
            </div>
          </Section>

          {/* 3 · Message Inputs */}
          <Section
            num={3}
            title="Message Inputs"
            sub="The raw material for your email copy"
            complete={secComplete[3]}
            count={secCount(3)}
            open={openSec === 3}
            onToggle={() => toggle(3)}
            onContinue={() => saveAndContinue(3)}
          >
            <div className="panel-pad">
              <div className="field">
                <Lbl
                  req
                  done={brief.valueProps.some((v) => v.trim())}
                  help="Specific, concrete benefits. Push yourself to name three distinct ones."
                >
                  Top 3 value propositions
                </Lbl>
                {[0, 1, 2].map((i) => (
                  <input
                    key={i}
                    className={clsx(
                      "input",
                      submitted && i === 0 && !brief.valueProps.some((v) => v.trim()) && "err"
                    )}
                    style={{ marginBottom: i < 2 ? 10 : 0 }}
                    value={brief.valueProps[i] ?? ""}
                    placeholder={"Value prop " + (i + 1)}
                    onChange={(e) => setValueProp(i, e.target.value)}
                  />
                ))}
              </div>
              <div className="field">
                <Lbl
                  req
                  done={filled(brief.proofPoints)}
                  help="Notable clients, metrics, awards, funding. This is what makes cold email believable."
                >
                  Proof points / credibility markers
                </Lbl>
                <textarea
                  className={errCls(filled(brief.proofPoints), "textarea")}
                  value={brief.proofPoints}
                  onChange={(e) => setB("proofPoints", e.target.value)}
                />
              </div>
              <div className="field">
                <Lbl
                  req
                  done={filled(brief.signals)}
                  help="Trigger events that suggest someone is in-market. Drives targeting and hooks."
                >
                  What signals a prospect is ready?
                </Lbl>
                <textarea
                  className={errCls(filled(brief.signals), "textarea")}
                  value={brief.signals}
                  onChange={(e) => setB("signals", e.target.value)}
                />
              </div>
              <div className="grid2">
                <div className="field">
                  <Lbl done={filled(brief.objections)} help="Pre-arms our reply handling.">
                    Common objections you hear
                  </Lbl>
                  <textarea
                    className="textarea"
                    value={brief.objections}
                    onChange={(e) => setB("objections", e.target.value)}
                  />
                </div>
                <div className="field">
                  <Lbl done={filled(brief.competitors)} help="Helps with positioning.">
                    Competitors you&apos;re compared to
                  </Lbl>
                  <textarea
                    className="textarea"
                    value={brief.competitors}
                    onChange={(e) => setB("competitors", e.target.value)}
                  />
                </div>
              </div>
              <div className="grid2">
                <div className="field" style={{ marginBottom: 0 }}>
                  <Lbl req done={filled(brief.tone)} help="How the emails should feel.">
                    Tone preference
                  </Lbl>
                  <select
                    className={errCls(filled(brief.tone), "select")}
                    value={brief.tone}
                    onChange={(e) => setB("tone", e.target.value)}
                  >
                    <option value="">Select…</option>
                    {TONE_OPTS.map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                </div>
                <div className="field" style={{ marginBottom: 0 }}>
                  <Lbl req done={filled(brief.languages)} help="Select all that apply.">
                    Language(s) for outreach
                  </Lbl>
                  <PillGroup
                    options={LANGUAGE_OPTS}
                    value={brief.languages}
                    onChange={(v) => setB("languages", v)}
                    invalid={submitted && !brief.languages.length}
                  />
                  {brief.languages.includes("Other") && (
                    <input
                      className="input"
                      style={{ marginTop: 10 }}
                      value={brief.languageOther}
                      placeholder="If other, please specify"
                      onChange={(e) => setB("languageOther", e.target.value)}
                    />
                  )}
                </div>
              </div>
            </div>
          </Section>

          {/* 4 · Exclusions & Guardrails */}
          <Section
            num={4}
            title="Exclusions & Guardrails"
            sub="Who we must never contact"
            complete={secComplete[4]}
            count={secCount(4)}
            open={openSec === 4}
            onToggle={() => toggle(4)}
            onContinue={() => saveAndContinue(4)}
          >
            <div className="panel-pad">
              <div className="brief-callout">
                <span className="ci">!</span>
                <div>
                  <b>Please don&apos;t rush this section.</b> Exclusions are the single most
                  important safeguard. Contacting your existing customers or active deals is the
                  fastest way to cause a problem, so the more complete this is, the safer your
                  campaign.
                </div>
              </div>
              <div className={clsx("field", brief.noExcludeCustomers && "is-locked")}>
                <Lbl
                  req
                  done={filled(brief.excludeCustomers) || brief.noExcludeCustomers}
                  help="We will never contact these. Add one company per line using the three columns below, or upload a CSV. If you have none, tick the box."
                >
                  Existing customers to exclude
                </Lbl>
                <ExclFormat />
                <textarea
                  className={errCls(
                    filled(brief.excludeCustomers) || brief.noExcludeCustomers,
                    "textarea"
                  )}
                  value={brief.excludeCustomers}
                  placeholder={EXCL_PLACEHOLDER}
                  disabled={brief.noExcludeCustomers}
                  onChange={(e) => setB("excludeCustomers", e.target.value)}
                />
                <div className="brief-upload">
                  <label
                    className={clsx(
                      "btn btn-ghost btn-sm",
                      brief.noExcludeCustomers && "disabled"
                    )}
                  >
                    <span className="up-ico">↥</span> Upload CSV
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      hidden
                      disabled={brief.noExcludeCustomers}
                      onChange={(e) => onCsv("customers", e)}
                    />
                  </label>
                  <span className="brief-hint">
                    {csvNames.customers
                      ? "Attached: " + csvNames.customers
                      : "Or upload a CSV with columns: company domain, company name, website."}
                  </span>
                  <label className="brief-none">
                    <input
                      type="checkbox"
                      checked={brief.noExcludeCustomers}
                      onChange={setNoExclude(
                        "noExcludeCustomers",
                        "excludeCustomers",
                        "customers"
                      )}
                    />
                    We have no existing customers to exclude.
                  </label>
                </div>
                <CsvErrors
                  errors={csvErrors.customers}
                  onDismiss={() => setCsvErrors((s) => ({ ...s, customers: [] }))}
                />
              </div>
              <div className={clsx("field", brief.noExcludeDeals && "is-locked")}>
                <Lbl
                  req
                  done={filled(brief.excludeDeals) || brief.noExcludeDeals}
                  help="Prospects already in your sales process. Double-touching these creates friction. Same three columns as above, or upload a CSV. If you have none, tick the box."
                >
                  Active deals / pipeline to exclude
                </Lbl>
                <ExclFormat />
                <textarea
                  className={errCls(
                    filled(brief.excludeDeals) || brief.noExcludeDeals,
                    "textarea"
                  )}
                  value={brief.excludeDeals}
                  placeholder={EXCL_PLACEHOLDER}
                  disabled={brief.noExcludeDeals}
                  onChange={(e) => setB("excludeDeals", e.target.value)}
                />
                <div className="brief-upload">
                  <label
                    className={clsx("btn btn-ghost btn-sm", brief.noExcludeDeals && "disabled")}
                  >
                    <span className="up-ico">↥</span> Upload CSV
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      hidden
                      disabled={brief.noExcludeDeals}
                      onChange={(e) => onCsv("deals", e)}
                    />
                  </label>
                  <span className="brief-hint">
                    {csvNames.deals
                      ? "Attached: " + csvNames.deals
                      : "Or upload a CSV with columns: company domain, company name, website."}
                  </span>
                  <label className="brief-none">
                    <input
                      type="checkbox"
                      checked={brief.noExcludeDeals}
                      onChange={setNoExclude("noExcludeDeals", "excludeDeals", "deals")}
                    />
                    We have no active deals in pipeline to exclude.
                  </label>
                </div>
                <CsvErrors
                  errors={csvErrors.deals}
                  onDismiss={() => setCsvErrors((s) => ({ ...s, deals: [] }))}
                />
              </div>
              <div className={clsx("field", brief.noDoNotContact && "is-locked")}>
                <Lbl
                  done={filled(brief.doNotContact) || brief.noDoNotContact}
                  help="Competitors, partners, investors, or any sensitive relationships to keep off the list. Same three columns as above, or upload a CSV. If you have none, tick the box."
                >
                  Competitors & do-not-contact (any reason)
                </Lbl>
                <ExclFormat />
                <textarea
                  className="textarea"
                  value={brief.doNotContact}
                  placeholder={EXCL_PLACEHOLDER}
                  disabled={brief.noDoNotContact}
                  onChange={(e) => setB("doNotContact", e.target.value)}
                />
                <div className="brief-upload">
                  <label
                    className={clsx("btn btn-ghost btn-sm", brief.noDoNotContact && "disabled")}
                  >
                    <span className="up-ico">↥</span> Upload CSV
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      hidden
                      disabled={brief.noDoNotContact}
                      onChange={(e) => onCsv("doNotContact", e)}
                    />
                  </label>
                  <span className="brief-hint">
                    {csvNames.doNotContact
                      ? "Attached: " + csvNames.doNotContact
                      : "Or upload a CSV with columns: company domain, company name, website."}
                  </span>
                  <label className="brief-none">
                    <input
                      type="checkbox"
                      checked={brief.noDoNotContact}
                      onChange={setNoExclude("noDoNotContact", "doNotContact", "doNotContact")}
                    />
                    We have no competitors or do-not-contact companies.
                  </label>
                </div>
                <CsvErrors
                  errors={csvErrors.doNotContact}
                  onDismiss={() => setCsvErrors((s) => ({ ...s, doNotContact: [] }))}
                />
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <Lbl
                  done={filled(brief.compliance)}
                  help="Any rules specific to your industry we should know about."
                >
                  Compliance or legal constraints
                </Lbl>
                <input
                  className="input"
                  value={brief.compliance}
                  placeholder="e.g. Cannot contact public sector entities"
                  onChange={(e) => setB("compliance", e.target.value)}
                />
              </div>
            </div>
          </Section>

          {/* 5 · Logistics & Handoff */}
          <Section
            num={5}
            title="Logistics & Handoff"
            sub="How meetings and updates flow to you"
            complete={secComplete[5]}
            count={secCount(5)}
            open={openSec === 5}
            onToggle={() => toggle(5)}
            onContinue={() => saveAndContinue(5)}
          >
            <div className="panel-pad">
              <div className="field">
                <Lbl
                  req
                  done={filled(brief.attendeeEmails)}
                  help="The email addresses on your side to invite. We create the Google Meet and send the calendar invite to these people — one per line, or comma-separated."
                >
                  Meeting attendee emails
                </Lbl>
                <textarea
                  className={errCls(filled(brief.attendeeEmails), "textarea")}
                  value={brief.attendeeEmails}
                  placeholder={"jane@yourcompany.com\njohn@yourcompany.com"}
                  onChange={(e) => setB("attendeeEmails", e.target.value)}
                />
              </div>
              <div className="field">
                <Lbl
                  req
                  done={filled(brief.attendees)}
                  help="Names and titles of the people whose calendars we're booking into."
                >
                  Who attends the meetings?
                </Lbl>
                <input
                  className={errCls(filled(brief.attendees))}
                  value={brief.attendees}
                  placeholder="e.g. Jane Doe (AE), John Smith (Sales Lead)"
                  onChange={(e) => setB("attendees", e.target.value)}
                />
              </div>
              <div className="grid2">
                <div className="field">
                  <Lbl req done={filled(brief.availability)} help="Days, times, time zone.">
                    Availability constraints
                  </Lbl>
                  <input
                    className={errCls(filled(brief.availability))}
                    value={brief.availability}
                    placeholder="e.g. Tue–Thu, 10am–4pm GMT"
                    onChange={(e) => setB("availability", e.target.value)}
                  />
                </div>
                <div className="field">
                  <Lbl
                    req
                    done={filled(brief.channel)}
                    help="How we'll send updates and reply alerts."
                  >
                    Preferred channel with us
                  </Lbl>
                  <select
                    className={errCls(filled(brief.channel), "select")}
                    value={brief.channel}
                    onChange={(e) => setB("channel", e.target.value)}
                  >
                    <option value="">Select…</option>
                    {CHANNEL_OPTS.map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid2">
                <div className="field" style={{ marginBottom: 0 }}>
                  <Lbl
                    req
                    done={filled(brief.contact)}
                    help="The person we coordinate with day to day."
                  >
                    Main point of contact
                  </Lbl>
                  <input
                    className={errCls(filled(brief.contact))}
                    value={brief.contact}
                    placeholder="Name, role, email"
                    onChange={(e) => setB("contact", e.target.value)}
                  />
                </div>
                <div className="field" style={{ marginBottom: 0 }}>
                  <Lbl
                    req
                    done={filled(brief.approver)}
                    help="Sometimes different from the point of contact. Clarifying now avoids delays."
                  >
                    Who has approval authority?
                  </Lbl>
                  <input
                    className={errCls(filled(brief.approver))}
                    value={brief.approver}
                    placeholder="Name, role"
                    onChange={(e) => setB("approver", e.target.value)}
                  />
                </div>
              </div>
            </div>
          </Section>

          {/* 6 · Targets & Definitions */}
          <Section
            num={6}
            title="Targets & Definitions"
            sub="What success looks like, and how we measure it"
            complete={secComplete[6]}
            count={secCount(6)}
            open={openSec === 6}
            onToggle={() => toggle(6)}
            onContinue={() => saveAndContinue(6)}
            last
          >
            <div className="panel-pad">
              <div className="field">
                <Lbl
                  req
                  done={filled(brief.meetingsPerMonth)}
                  help="Sets expectations against your plan. Surfaces any mismatch early."
                >
                  Qualified meetings expected per month
                </Lbl>
                <input
                  type="number"
                  min={0}
                  className={errCls(filled(brief.meetingsPerMonth))}
                  value={brief.meetingsPerMonth}
                  placeholder="e.g. 15"
                  onChange={(e) => setB("meetingsPerMonth", e.target.value)}
                />
              </div>
              <div className="field">
                <Lbl
                  req
                  done={filled(brief.qualifiedDef)}
                  help="The most important definition in this form. We reconcile it with our standard before launch so billing is never ambiguous."
                >
                  What counts as a &quot;qualified meeting&quot; for you?
                </Lbl>
                <textarea
                  className={errCls(filled(brief.qualifiedDef), "textarea")}
                  value={brief.qualifiedDef}
                  onChange={(e) => setB("qualifiedDef", e.target.value)}
                />
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <Lbl
                  done={filled(brief.first90)}
                  help="Aligns expectations and frames our first review together."
                >
                  What does a successful first 90 days look like?
                </Lbl>
                <textarea
                  className="textarea"
                  value={brief.first90}
                  onChange={(e) => setB("first90", e.target.value)}
                />
              </div>
            </div>
          </Section>

          <SpecReview
            client={client}
            spec={spec}
            structuring={structuring}
            saving={saving}
            ready={allComplete}
            onStructure={runStructure}
            onAcceptIcp={acceptIcpSuggestion}
          />
        </>
      )}
    </section>
  );
}
