// Find-People scope-settings modal — target people by Management Level × Department, with live
// facet counts for the ticked Step-2 companies. Extracted from list/page.tsx (2.4 Stage 1) as a pure
// presentational modal; the facet-load/save/reset handlers stay in the parent and arrive as props.
import { Modal } from "@/components/Modal";
import { SpecHead } from "@/components/workspace";
import type { CompanyApi, FacetOption, PeopleFacets } from "@/lib/api";
import type { PeopleScopeForm, PeopleScopeOverride } from "@/lib/workspace/types";
import { SENIORITY_OPTIONS, humanizeFacet } from "@/lib/workspace/constants";
import { FacetRow } from "./fields";

export function PeopleScopeModal({
  peopleScopeOpen,
  setPeopleScopeOpen,
  resetPeopleScopeSettings,
  savingPplScope,
  savePeopleScopeSettings,
  peopleScopeForm,
  peopleScopeOverride,
  pplFacets,
  pplFacetsLoading,
  pplCoSel,
  toggleFacet,
  masterDepts,
}: {
  peopleScopeOpen: boolean;
  setPeopleScopeOpen: (v: boolean) => void;
  resetPeopleScopeSettings: () => void;
  savingPplScope: boolean;
  savePeopleScopeSettings: () => void;
  peopleScopeForm: PeopleScopeForm | null;
  peopleScopeOverride: PeopleScopeOverride | null;
  pplFacets: PeopleFacets | null;
  pplFacetsLoading: boolean;
  pplCoSel: CompanyApi[];
  toggleFacet: (key: "seniorities" | "departments", value: string) => void;
  masterDepts: FacetOption[];
}) {
  return (
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
            Management Level AND Department · OR within each. A strict combo can return few or none,
            so Find People auto-widens (department-only, then level-only); leave a facet empty to
            skip it.
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
  );
}
