// Step-1 (Companies) branch of the Prospect List (2.4 Stage 3). Pure presentational: the JSX body,
// the two per-row render helpers (renderCompanyRow / renderSubGroups), and the two co-located
// <style> strings are lifted verbatim from list/page.tsx; every value it reads arrives as an
// identically-named prop, so the parent still owns all state + handlers.
import { Fragment } from "react";
import clsx from "clsx";
import { type CompanyApi, type ScoreLabel, SCORE_BATCH_MAX } from "@/lib/api";
import type { ScopeOverride } from "@/lib/workspace/types";
import {
  BUCKET_HEAD,
  BUCKET_ORDER,
  COMPANY_AXES,
  SOURCE_CLS,
  SOURCE_LABEL,
  businessModelChip,
} from "@/lib/workspace/constants";
import { CompanyStudy, WebLink } from "@/components/workspace";
import {
  COLLAPSED_KEYS,
  FitCell,
  IcpFilterSelect,
  ListOverlay,
  activateOnKey,
  subGroupsOf,
} from "./helpers";

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

export function Step1Companies({
  setFindHistoryOpen,
  openScopeSettings,
  scopeOverride,
  runFindCompanies,
  coMutating,
  findingCo,
  coTargetIcpName,
  coSelCount,
  runRescore,
  scoringActive,
  findingPpl,
  runLookalike,
  findingLookalike,
  runUpdateFields,
  updatingFields,
  setCompanyChecked,
  scopeExhausted,
  runLookalikeOfStrong,
  setScopeExhausted,
  coSearch,
  setCoSearch,
  icpOptions,
  fIcp,
  setFIcp,
  icpNeedsPick,
  coStatus,
  setCoStatus,
  setAddCoOpen,
  coVisible,
  coBusy,
  coBuckets,
  expandedBuckets,
  toggleBucket,
  scoreUnscoredWave,
  coScopeSummary,
  stageForPeople,
  staging,
  icpNameById,
  companyChecked,
  toggleCo,
  scoringCoIds,
  expandedSubs,
  toggleSub,
}: {
  setFindHistoryOpen: (v: boolean) => void;
  openScopeSettings: () => void;
  scopeOverride: ScopeOverride | null;
  runFindCompanies: () => void;
  coMutating: boolean;
  findingCo: boolean;
  coTargetIcpName: string | null | undefined;
  coSelCount: number;
  runRescore: () => void;
  scoringActive: boolean;
  findingPpl: boolean;
  runLookalike: () => void;
  findingLookalike: boolean;
  runUpdateFields: () => void;
  updatingFields: boolean;
  setCompanyChecked: (v: Set<string>) => void;
  scopeExhausted: boolean;
  runLookalikeOfStrong: () => void;
  setScopeExhausted: (v: boolean) => void;
  coSearch: string;
  setCoSearch: (v: string) => void;
  icpOptions: { id: string; label: string }[];
  fIcp: string;
  setFIcp: (v: string) => void;
  icpNeedsPick: boolean;
  coStatus: string;
  setCoStatus: (v: string) => void;
  setAddCoOpen: (v: boolean) => void;
  coVisible: CompanyApi[];
  coBusy: boolean;
  coBuckets: Map<ScoreLabel | "unscored", CompanyApi[]>;
  expandedBuckets: Set<string>;
  toggleBucket: (key: string) => void;
  scoreUnscoredWave: () => void;
  coScopeSummary: string;
  stageForPeople: () => void;
  staging: boolean;
  icpNameById: Map<string, string>;
  companyChecked: Set<string>;
  toggleCo: (c: CompanyApi, allowExcluded?: boolean) => void;
  scoringCoIds: Set<string>;
  expandedSubs: Set<string>;
  toggleSub: (key: string) => void;
}) {
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
          <tr
            className="bucket-sub bucket-head--btn"
            role="button"
            tabIndex={0}
            onClick={() => toggleSub(subKey)}
            onKeyDown={activateOnKey(() => toggleSub(subKey))}
          >
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

  return (
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
            <button className="btn btn-ghost btn-sm" onClick={() => setCompanyChecked(new Set())}>
              Clear
            </button>
          </div>
        </div>
      )}
      {scopeExhausted ? (
        <div className="se-notice" role="status">
          <style>{SE_CSS}</style>
          <div className="se-body">
            <strong>You&apos;ve reviewed every company Apollo has for this scope.</strong> Find
            resumes at the next page each run, and this one reached the end — there are no new
            companies left under these exact filters. To open up more:
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
        <select className="select" value={coStatus} onChange={(e) => setCoStatus(e.target.value)}>
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
                        role="button"
                        tabIndex={0}
                        onKeyDown={activateOnKey(() => toggleBucket(key))}
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
              No companies match the current scope yet · click Find Companies to search Apollo.
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
  );
}
