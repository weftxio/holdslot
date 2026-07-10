"use client";
import { useEffect, useMemo, useState } from "react";
import { Modal } from "@/components/Modal";
import { listResearchRuns, type ResearchRunApi } from "@/lib/api";

/**
 * Find-history drawer v2 (U4) — a read-only, grouped view over `/research-runs`. Answers "what did we
 * search, when, and what did it cost?": a summary strip on top, type-filter chips, day group headers,
 * and THREADED entries — repeated company finds of the same scope collapse on `body_hash` (the
 * paginated same-search), a merged stage→find's chunked people calls collapse on `group_id` — so one
 * logical search is one row, not N. Per-run filters expand to the EXACTLY-executed Apollo body
 * (company) or the per-org bodies (people). All values render via JSX (never HTML).
 */

type RunType = "find" | "lookalike" | "scoring" | "enrichment";

// research_run.source → the logical action. A source=apollo run is a Find (company OR people — the
// per-org filter_body tells them apart); lookalike/rescore/enrich are their own doors.
function runType(run: ResearchRunApi): RunType {
  if (run.source === "lookalike") return "lookalike";
  if (run.source === "rescore") return "scoring";
  if (run.source === "enrich") return "enrichment";
  return "find";
}
const TYPE_BADGE: Record<RunType, { label: string; cls: string }> = {
  find: { label: "Find", cls: "badge-info" },
  lookalike: { label: "Lookalike", cls: "badge-info" },
  scoring: { label: "Scoring", cls: "badge-neutral" },
  enrichment: { label: "Enrichment", cls: "badge-neutral" },
};

const TYPE_CHIPS: { key: RunType | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "find", label: "Finds" },
  { key: "lookalike", label: "Lookalikes" },
  { key: "scoring", label: "Scoring" },
  { key: "enrichment", label: "Enrichment" },
];

// scope_source → the honest "who set this scope" chip. `custom` (operator-tuned in Find Settings) is
// warn-toned so a hand-edited search is never mistaken for the AI's.
const SCOPE: Record<string, { label: string; cls: string }> = {
  ai: { label: "AI scope", cls: "badge-neutral" },
  custom: { label: "Custom scope", cls: "badge-warn" },
  lookalike: { label: "Seed-derived", cls: "badge-neutral" },
};

// Apollo filter key → a friendly label for the "View filters" popover (company + people fields).
const FIELD_LABEL: Record<string, string> = {
  q_organization_keyword_tags: "Keywords",
  organization_num_employees_ranges: "Employee size",
  organization_locations: "Locations",
  revenue_range: "Revenue",
  q_organization_job_titles: "Hiring for",
  person_seniorities: "Seniority",
  person_department_or_subdepartments: "Departments",
  q_keywords: "Profile keywords",
  organization_ids: "Org",
  organization_not_locations: "Excluded locations",
  currently_using_any_of_technology_uids: "Uses tech",
  currently_not_using_any_of_technology_uids: "Not using tech",
  person_titles: "Titles",
  include_similar_titles: "Fuzzy titles",
};

// A people find records `filter_body = { per_org: { domain: { body, relax, raw, survivors } } }`.
function isPeopleFind(run: ResearchRunApi): boolean {
  return !!(run.filter_body && "per_org" in run.filter_body);
}

// Thread key: same-scope company finds collapse on body_hash (the paginated same-search); a merged
// stage→find's chunked people calls collapse on group_id; everything else stands alone (run_id).
function threadKey(run: ResearchRunApi): string {
  const m = run.result_meta ?? {};
  if (m.group_id) return `g:${m.group_id}`;
  if ((run.source === "apollo" || run.source === "lookalike") && m.body_hash) return `b:${m.body_hash}`;
  return `r:${run.run_id}`;
}

type Thread = {
  key: string;
  type: RunType;
  runs: ResearchRunApi[]; // newest → oldest
  latest: ResearchRunApi;
  latestAt: string | null;
  rowsTotal: number;
  spendTotal: number;
  people: boolean;
};

function buildThreads(runs: ResearchRunApi[]): Thread[] {
  const byKey = new Map<string, ResearchRunApi[]>();
  const order: string[] = [];
  for (const run of runs) {
    const k = threadKey(run);
    const g = byKey.get(k);
    if (g) g.push(run);
    else {
      byKey.set(k, [run]);
      order.push(k);
    }
  }
  const threads = order.map((k) => {
    const rs = byKey.get(k)!.slice().sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
    const latest = rs[0];
    return {
      key: k,
      type: runType(latest),
      runs: rs,
      latest,
      latestAt: latest.created_at,
      rowsTotal: rs.reduce((n, r) => n + (r.rows_pushed ?? 0), 0),
      spendTotal: rs.reduce((n, r) => n + (r.cost_usd ?? 0), 0),
      people: isPeopleFind(latest),
    } satisfies Thread;
  });
  // Newest thread first (by its most recent run).
  return threads.sort((a, b) => (b.latestAt ?? "").localeCompare(a.latestAt ?? ""));
}

function fieldValue(value: unknown): string {
  if (value == null) return "—";
  if (Array.isArray(value)) return value.length ? value.map(String).join(", ") : "—";
  if (typeof value === "object") {
    const o = value as Record<string, unknown>;
    if ("min" in o || "max" in o) {
      const fmt = (n: unknown) => (n == null || n === "" ? "…" : String(n));
      return `${fmt(o.min)} – ${fmt(o.max)}`;
    }
    return JSON.stringify(o);
  }
  return String(value);
}

function relaxStepLabel(step: string): string {
  if (step === "drop_revenue_range") return "dropped revenue filter";
  if (step === "widen_size") return "widened size ranges";
  if (step.startsWith("drop_keyword:")) return `dropped keyword "${step.slice("drop_keyword:".length)}"`;
  return step;
}

// Full date + time so every row is self-describing (the day header groups them; this labels each).
function whenLabel(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}
function dayKey(iso: string | null): string {
  if (!iso) return "undated";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "undated" : String(startOfDay(d));
}
function dayLabel(iso: string | null, nowMs: number): string {
  if (!iso) return "Undated";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Undated";
  const diff = Math.round((startOfDay(new Date(nowMs)) - startOfDay(d)) / 86_400_000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

const money = (n: number) => (n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(4)}`);

// Mounted only while open (parent gates it) so each open starts with fresh state and the effect just
// fetches — no synchronous state reset in the effect body.
export function FindHistoryDrawer({
  onClose,
  client,
  icpNameById,
}: {
  onClose: () => void;
  client: string;
  icpNameById: Map<string, string>;
}) {
  const [runs, setRuns] = useState<ResearchRunApi[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openFilters, setOpenFilters] = useState<string | null>(null);
  const [chip, setChip] = useState<RunType | "all">("all");
  // "Now" captured once when the runs load (impure calls belong in the effect, never render), so the
  // week window + day headers are stable across re-renders.
  const [nowMs, setNowMs] = useState(0);

  useEffect(() => {
    let alive = true;
    listResearchRuns(client)
      .then((r) => {
        if (!alive) return;
        setRuns(r);
        setNowMs(Date.now());
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Could not load find history"));
    return () => {
      alive = false;
    };
  }, [client]);

  const threads = useMemo(() => (runs ? buildThreads(runs) : []), [runs]);

  // Summary strip — finds this week (find + lookalike threads in the last 7 days), total rows landed,
  // and total scoring + enrichment spend (cost_usd across every run).
  const summary = useMemo(() => {
    const weekAgo = nowMs - 7 * 86_400_000;
    let findsThisWeek = 0;
    for (const t of threads) {
      if ((t.type === "find" || t.type === "lookalike") && t.latestAt) {
        const ms = new Date(t.latestAt).getTime();
        if (!Number.isNaN(ms) && ms >= weekAgo) findsThisWeek += 1;
      }
    }
    const rowsLanded = (runs ?? []).reduce((n, r) => n + (r.rows_pushed ?? 0), 0);
    const spend = (runs ?? []).reduce((n, r) => n + (r.cost_usd ?? 0), 0);
    return { findsThisWeek, rowsLanded, spend };
  }, [threads, runs, nowMs]);

  const shown = useMemo(
    () => (chip === "all" ? threads : threads.filter((t) => t.type === chip)),
    [threads, chip]
  );

  // Group the (already newest-first) threads by the day of their most recent run.
  const days = useMemo(() => {
    const out: { key: string; label: string; threads: Thread[] }[] = [];
    for (const t of shown) {
      const k = dayKey(t.latestAt);
      const last = out[out.length - 1];
      if (last && last.key === k) last.threads.push(t);
      else out.push({ key: k, label: dayLabel(t.latestAt, nowMs), threads: [t] });
    }
    return out;
  }, [shown, nowMs]);

  return (
    <Modal open onClose={onClose} title="Find history" className="fh-modal">
      <style>{FH_CSS}</style>
      {error ? (
        <p className="fh-empty">{error}</p>
      ) : runs === null ? (
        <p className="fh-empty">Loading…</p>
      ) : runs.length === 0 ? (
        <p className="fh-empty">No finds yet — run Find Company to start the history.</p>
      ) : (
        <>
          <div className="fh-summary">
            <span className="fh-sum">
              <strong>{summary.findsThisWeek}</strong> find{summary.findsThisWeek === 1 ? "" : "s"} this week
            </span>
            <span className="fh-sum">
              <strong>{summary.rowsLanded.toLocaleString()}</strong> rows landed
            </span>
            <span className="fh-sum">
              <strong>{money(summary.spend)}</strong> scoring + enrichment spend
            </span>
          </div>
          <div className="fh-chips">
            {TYPE_CHIPS.map((c) => (
              <button
                key={c.key}
                type="button"
                className={`fh-chip${chip === c.key ? " on" : ""}`}
                onClick={() => setChip(c.key)}
              >
                {c.label}
              </button>
            ))}
          </div>
          {shown.length === 0 ? (
            <p className="fh-empty">No {chip} runs yet.</p>
          ) : (
            days.map((day) => (
              <div key={day.key} className="fh-day">
                <div className="fh-day-head">{day.label}</div>
                <ul className="fh-list">
                  {day.threads.map((t) => (
                    <ThreadCard
                      key={t.key}
                      thread={t}
                      icpNameById={icpNameById}
                      open={openFilters === t.key}
                      onToggle={() => setOpenFilters(openFilters === t.key ? null : t.key)}
                    />
                  ))}
                </ul>
              </div>
            ))
          )}
        </>
      )}
    </Modal>
  );
}

function ThreadCard({
  thread,
  icpNameById,
  open,
  onToggle,
}: {
  thread: Thread;
  icpNameById: Map<string, string>;
  open: boolean;
  onToggle: () => void;
}) {
  const run = thread.latest;
  const meta = run.result_meta ?? {};
  const type = TYPE_BADGE[thread.type];
  const scope = run.scope_source ? SCOPE[run.scope_source] : null;
  const icpName = run.icp_id ? icpNameById.get(run.icp_id) : null;
  const relaxLevel = meta.relax_level ?? 0;
  const runCount = thread.runs.length;
  // People threads aggregate orgs searched / people found across their chunked runs.
  const orgs = thread.people
    ? thread.runs.reduce((n, r) => n + (r.result_meta?.orgs_searched ?? 0), 0)
    : 0;
  const body = (run.filter_body ?? {}) as Record<string, unknown>;
  const perOrg = thread.people ? ((body.per_org as Record<string, PerOrg>) ?? {}) : null;
  const bodyKeys = thread.people ? Object.keys(perOrg ?? {}) : Object.keys(body);

  return (
    <li className="fh-run">
      <div className="fh-row">
        <span className={`badge ${type.cls}`}>{type.label}</span>
        {thread.people ? <span className="badge badge-neutral">People</span> : null}
        {scope ? <span className={`badge ${scope.cls}`}>{scope.label}</span> : null}
        {icpName ? <span className="badge badge-info">{icpName}</span> : null}
        {runCount > 1 ? (
          <span className="badge badge-neutral" title="Threaded — the same search across several runs">
            ×{runCount} runs
          </span>
        ) : null}
        <span className="fh-when">{whenLabel(thread.latestAt)}</span>
      </div>
      <div className="fh-row fh-stats">
        <span className="fh-stat">
          <strong>{thread.rowsTotal}</strong> row{thread.rowsTotal === 1 ? "" : "s"} landed
        </span>
        {thread.people ? (
          orgs ? (
            <span className="fh-stat">
              <strong>{orgs}</strong> org{orgs === 1 ? "" : "s"} searched
            </span>
          ) : null
        ) : meta.total_entries != null ? (
          <span className="fh-stat">
            <strong>{meta.total_entries.toLocaleString()}</strong> Apollo matches
          </span>
        ) : null}
        {thread.spendTotal > 0 ? (
          <span className="fh-stat" title="LLM scoring spend booked to this run">
            <strong>{money(thread.spendTotal)}</strong> spend
          </span>
        ) : null}
        {!thread.people && meta.scope_exhausted ? (
          <span className="badge badge-warn" title="Reached the end of this scope's Apollo results — regenerate or find lookalikes for more">
            scope exhausted
          </span>
        ) : null}
        {relaxLevel > 0 ? (
          <span className="badge badge-warn" title={(meta.relax_steps ?? []).map(relaxStepLabel).join(" · ")}>
            auto-widened ×{relaxLevel}
          </span>
        ) : null}
        {meta.over_broad ? (
          <span className="badge badge-danger" title="Over 100k matches — the scope is likely too loose to be useful">
            over-broad
          </span>
        ) : null}
        {bodyKeys.length ? (
          <button type="button" className="btn btn-ghost btn-xs fh-toggle" onClick={onToggle}>
            {open ? "Hide filters" : "View filters"}
          </button>
        ) : null}
      </div>
      {open ? (
        <div className="fh-filters">
          {relaxLevel > 0 && !thread.people ? (
            <p className="fh-relax">
              Auto-widened to fill the batch: {(meta.relax_steps ?? []).map(relaxStepLabel).join(" → ")}.
            </p>
          ) : null}
          {thread.people && perOrg ? (
            <div className="fh-orgs">
              {bodyKeys.map((domain) => {
                const o = perOrg[domain] ?? {};
                const ob = (o.body ?? {}) as Record<string, unknown>;
                const obKeys = Object.keys(ob);
                return (
                  <div key={domain} className="fh-org">
                    <div className="fh-org-head">
                      <span className="fh-org-name">{domain}</span>
                      <span className="fh-org-ct">
                        {o.survivors ?? 0}/{o.raw ?? 0} people
                        {o.relax ? ` · relaxed ×${o.relax}` : ""}
                      </span>
                    </div>
                    {obKeys.length ? (
                      <dl className="fh-dl">
                        {obKeys.map((k) => (
                          <div key={k} className="fh-dl-row">
                            <dt>{FIELD_LABEL[k] ?? k}</dt>
                            <dd>{fieldValue(ob[k])}</dd>
                          </div>
                        ))}
                      </dl>
                    ) : (
                      <p className="fh-relax">No facet filters — everyone at this org.</p>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <dl className="fh-dl">
              {bodyKeys.map((k) => (
                <div key={k} className="fh-dl-row">
                  <dt>{FIELD_LABEL[k] ?? k}</dt>
                  <dd>{fieldValue(body[k])}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      ) : null}
    </li>
  );
}

type PerOrg = { body?: Record<string, unknown>; relax?: number; raw?: number; survivors?: number };

// Scoped to `.fh-*` classes only (rendered inside the modal body) so nothing leaks to other routes.
const FH_CSS = `
.fh-empty { color: var(--ink-soft); padding: 24px 4px; text-align: center; }
.fh-summary { display: flex; flex-wrap: wrap; gap: 6px 18px; padding: 10px 12px; margin-bottom: 12px;
  border: 1px solid var(--line); border-radius: 10px; background: var(--cerulean-wash); }
.fh-sum { font-size: 13px; color: var(--ink-soft); }
.fh-sum strong { color: var(--ink); font-variant-numeric: tabular-nums; }
.fh-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.fh-chip { font: inherit; font-size: 12px; padding: 4px 12px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--line); background: var(--paper); color: var(--ink-soft); }
.fh-chip.on { background: var(--cerulean-deep); border-color: var(--cerulean-deep); color: #fff; }
.fh-day { margin-bottom: 16px; }
.fh-day-head { font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--ink-faint); margin: 0 0 8px; }
.fh-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.fh-run { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; }
.fh-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.fh-stats { margin-top: 6px; }
.fh-when { margin-left: auto; color: var(--ink-soft); font-size: 12px; white-space: nowrap; }
.fh-stat { font-size: 13px; color: var(--ink); }
.fh-stat strong { font-variant-numeric: tabular-nums; }
.fh-toggle { margin-left: auto; }
.fh-filters { margin-top: 10px; border-top: 1px dashed var(--line); padding-top: 8px; }
.fh-relax { margin: 0 0 8px; font-size: 12px; color: var(--warn); }
.fh-orgs { display: flex; flex-direction: column; gap: 10px; }
.fh-org { border-left: 2px solid var(--line); padding-left: 10px; }
.fh-org-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; margin-bottom: 4px; }
.fh-org-name { font-size: 13px; font-weight: 650; color: var(--ink); }
.fh-org-ct { font-size: 12px; color: var(--ink-soft); font-variant-numeric: tabular-nums; }
.fh-dl { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; }
.fh-dl-row { display: contents; }
.fh-dl dt { color: var(--ink-soft); font-size: 12px; }
.fh-dl dd { margin: 0; font-size: 13px; color: var(--ink); word-break: break-word; }
`;
