// Step-2 (People) branch of the Prospect List (2.4 Stage 3). Pure presentational: the JSX body is
// lifted verbatim from list/page.tsx; every value it reads arrives as an identically-named prop, so
// the parent still owns all state + handlers.
import { Fragment } from "react";
import clsx from "clsx";
import type { CompanyApi, ProspectApi } from "@/lib/api";
import type { PeopleScopeOverride } from "@/lib/workspace/types";
import { ENRICHED_STATUS, PROSPECT_AXES, STATUS_LABEL } from "@/lib/workspace/constants";
import { LinkedInLink } from "@/components/workspace";
import { FitCell, IcpFilterSelect, ListOverlay, activateOnKey } from "./helpers";

export function Step2People({
  peopleScopeOverride,
  openPeopleScopeSettings,
  coTargetIcpName,
  runFindPeople,
  findingPpl,
  pplCoSel,
  removeFromStep2,
  removing,
  search,
  setSearch,
  icpOptions,
  fIcp,
  setFIcp,
  fStatus,
  setFStatus,
  setAddPersonOpen,
  pursued,
  visible,
  selectedProspects,
  pplBusy,
  rowsForCompany,
  findingPplIds,
  expandedCos,
  companyChecked,
  toggleCo,
  toggleCoCollapse,
  icpNameById,
  checked,
  scoringPersonIds,
  toggleRow,
  prospectsLoading,
  companiesLoading,
  pplScopeSummary,
  setChecked,
  toEnrich,
  runRevealScore,
  scoringPeopleActive,
  canBatch,
  newBatchName,
  setNewBatchName,
  createBatch,
  creatingBatch,
}: {
  peopleScopeOverride: PeopleScopeOverride | null;
  openPeopleScopeSettings: () => void;
  coTargetIcpName: string | null | undefined;
  runFindPeople: () => void;
  findingPpl: boolean;
  pplCoSel: CompanyApi[];
  removeFromStep2: () => void;
  removing: boolean;
  search: string;
  setSearch: (v: string) => void;
  icpOptions: { id: string; label: string }[];
  fIcp: string;
  setFIcp: (v: string) => void;
  fStatus: string;
  setFStatus: (v: string) => void;
  setAddPersonOpen: (v: boolean) => void;
  pursued: CompanyApi[];
  visible: ProspectApi[];
  selectedProspects: ProspectApi[];
  pplBusy: boolean;
  rowsForCompany: (id: string) => ProspectApi[];
  findingPplIds: Set<string>;
  expandedCos: Set<string>;
  companyChecked: Set<string>;
  toggleCo: (c: CompanyApi, allowExcluded?: boolean) => void;
  toggleCoCollapse: (id: string) => void;
  icpNameById: Map<string, string>;
  checked: Set<string>;
  scoringPersonIds: Set<string>;
  toggleRow: (p: ProspectApi) => void;
  prospectsLoading: boolean;
  companiesLoading: boolean;
  pplScopeSummary: string;
  setChecked: (v: Set<string>) => void;
  toEnrich: ProspectApi[];
  runRevealScore: () => void;
  scoringPeopleActive: boolean;
  canBatch: boolean;
  newBatchName: string;
  setNewBatchName: (v: string) => void;
  createBatch: () => void;
  creatingBatch: boolean;
}) {
  return (
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
            {removing ? "Removing…" : pplCoSel.length ? `Remove ${pplCoSel.length}` : "Remove"}
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
        <select className="select" value={fStatus} onChange={(e) => setFStatus(e.target.value)}>
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
                  const enrichedCount = rows.filter((p) => p.status === ENRICHED_STATUS).length;
                  // Company cell — count badge atop the name; spans the company's people rows.
                  // When the company has people, clicking the cell collapses/expands that list
                  // (the select checkbox stops propagation so ticking doesn't toggle it).
                  const companyCell = (rowSpan: number) => (
                    <td
                      className={clsx("vtop", "grp-co-cell", expandable && "grp-co-click")}
                      rowSpan={rowSpan}
                      role={expandable ? "button" : undefined}
                      tabIndex={expandable ? 0 : undefined}
                      onClick={expandable ? () => toggleCoCollapse(c.id) : undefined}
                      onKeyDown={
                        expandable ? activateOnKey(() => toggleCoCollapse(c.id)) : undefined
                      }
                      title={
                        expandable ? (collapsed ? "Expand people" : "Collapse people") : undefined
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
                          <span className="badge badge-neutral">{icpNameById.get(c.icp_id)}</span>
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
                          {rows.length === 1 ? "person" : "people"} hidden · click company cell to
                          expand viewing
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
                  No companies in Step 2 yet · go to Step 1, tick companies, and click “Find people
                  for N →”.
                  {pplScopeSummary ? (
                    <>
                      <br />
                      Person filters{peopleScopeOverride ? " (custom)" : ""} · {pplScopeSummary}.
                      Adjust them in ⚙ Personas.
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
            disabled={!canBatch || creatingBatch}
            title={
              canBatch
                ? ""
                : toEnrich.length
                  ? "Reveal & score the Found people first — only revealed people can be batched."
                  : "Select people with a revealed email to batch them."
            }
          >
            {creatingBatch ? "Creating…" : "Create batch →"}
          </button>
        </div>
      </div>
    </>
  );
}
