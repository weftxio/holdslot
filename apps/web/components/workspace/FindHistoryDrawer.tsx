"use client";
import { useEffect, useState } from "react";
import { Modal } from "@/components/Modal";
import { listResearchRuns, type ResearchRunApi } from "@/lib/api";

/**
 * Find-history drawer (D+ Stage 1b) — a read-only view over `/research-runs`, now lineage-rich.
 * Answers "what did each find actually ask, and how broad was it?": per run we show when · source ·
 * ICP · spec version · the ai/custom scope chip · rows landed · Apollo's `total_entries` match count ·
 * the relax trail · an over-broad flag, plus a per-row "View filters" popover of the EXACTLY-executed
 * Apollo body (override-proof) and Apollo's breadcrumb echo. All values render via JSX (never HTML).
 */

// research_run.source → a human label + a badge tone. Find + Lookalike are the sourcing doors;
// re-score / enrichment are the paid follow-ups booked as their own runs.
const SOURCE: Record<string, { label: string; cls: string }> = {
  apollo: { label: "Find", cls: "badge-info" },
  lookalike: { label: "Lookalike", cls: "badge-info" },
  rescore: { label: "Re-score", cls: "badge-neutral" },
  enrich: { label: "Enrichment", cls: "badge-neutral" },
};

// scope_source → the honest "who set this scope" chip. `custom` (operator-tuned in Find Settings)
// is warn-toned so a hand-edited search is never mistaken for the AI's.
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
  // D+ Stage 3/4 — the recycled negative signal + resolved tech vocabulary (server-added filters).
  organization_not_locations: "Excluded locations",
  currently_using_any_of_technology_uids: "Uses tech",
  currently_not_using_any_of_technology_uids: "Not using tech",
  person_titles: "Titles",
  include_similar_titles: "Fuzzy titles",
};

// A relax step id → a short human phrase (drop_keyword carries the dropped tag after the colon).
function relaxStepLabel(step: string): string {
  if (step === "drop_revenue_range") return "dropped revenue filter";
  if (step === "widen_size") return "widened size ranges";
  if (step.startsWith("drop_keyword:")) return `dropped keyword "${step.slice("drop_keyword:".length)}"`;
  return step;
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

// Mounted only while open (parent gates it) so each open starts with fresh state and the effect
// just fetches — no synchronous state reset in the effect body.
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

  useEffect(() => {
    let alive = true;
    listResearchRuns(client)
      .then((r) => alive && setRuns(r))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Could not load find history"));
    return () => {
      alive = false;
    };
  }, [client]);

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
        <ul className="fh-list">
          {runs.map((run) => {
            const src = SOURCE[run.source] ?? { label: run.source, cls: "badge-neutral" };
            const scope = run.scope_source ? SCOPE[run.scope_source] : null;
            const icpName = run.icp_id ? icpNameById.get(run.icp_id) : null;
            const meta = run.result_meta ?? {};
            const relaxLevel = meta.relax_level ?? 0;
            const showFilters = openFilters === run.run_id;
            const body = run.filter_body ?? {};
            const bodyKeys = Object.keys(body);
            return (
              <li key={run.run_id} className="fh-run">
                <div className="fh-row">
                  <span className={`badge ${src.cls}`}>{src.label}</span>
                  {scope ? <span className={`badge ${scope.cls}`}>{scope.label}</span> : null}
                  {icpName ? <span className="badge badge-info">{icpName}</span> : null}
                  {run.prompt_version ? (
                    <span className="badge badge-neutral">{run.prompt_version}</span>
                  ) : null}
                  <span className="fh-when">{whenLabel(run.created_at)}</span>
                </div>
                <div className="fh-row fh-stats">
                  <span className="fh-stat">
                    <strong>{run.rows_pushed}</strong> row{run.rows_pushed === 1 ? "" : "s"} landed
                  </span>
                  {meta.total_entries != null ? (
                    <span className="fh-stat">
                      <strong>{meta.total_entries.toLocaleString()}</strong> Apollo matches
                    </span>
                  ) : null}
                  {meta.page_cursor != null && meta.page_cursor >= 1 ? (
                    <span className="fh-stat" title="The page cursor this run reached — a re-find of the same scope resumes past it">
                      page{" "}
                      <strong>
                        {meta.resume_page && meta.resume_page !== meta.page_cursor
                          ? `${meta.resume_page}–${meta.page_cursor}`
                          : meta.page_cursor}
                      </strong>
                      {meta.total_pages ? ` / ${meta.total_pages}` : ""}
                    </span>
                  ) : null}
                  {meta.scope_exhausted ? (
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
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs fh-toggle"
                      onClick={() => setOpenFilters(showFilters ? null : run.run_id)}
                    >
                      {showFilters ? "Hide filters" : "View filters"}
                    </button>
                  ) : null}
                </div>
                {showFilters ? (
                  <div className="fh-filters">
                    {relaxLevel > 0 ? (
                      <p className="fh-relax">
                        Auto-widened to fill the batch: {(meta.relax_steps ?? []).map(relaxStepLabel).join(" → ")}.
                      </p>
                    ) : null}
                    <dl className="fh-dl">
                      {bodyKeys.map((k) => (
                        <div key={k} className="fh-dl-row">
                          <dt>{FIELD_LABEL[k] ?? k}</dt>
                          <dd>{fieldValue(body[k])}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </Modal>
  );
}

// Scoped to `.fh-*` classes only (rendered inside the modal body) so nothing leaks to other routes.
const FH_CSS = `
.fh-empty { color: var(--ink-soft); padding: 24px 4px; text-align: center; }
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
.fh-dl { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; }
.fh-dl-row { display: contents; }
.fh-dl dt { color: var(--ink-soft); font-size: 12px; }
.fh-dl dd { margin: 0; font-size: 13px; color: var(--ink); word-break: break-word; }
`;
