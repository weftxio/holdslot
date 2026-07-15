// Find-Company scope-settings modal — edit the Apollo company-search filters (per ICP). Extracted
// from list/page.tsx (2.4 Stage 1) as a pure presentational modal; the seed/switch/save/reset
// handlers stay in the parent and arrive as props. JSX body byte-identical to the inline original.
import { Modal } from "@/components/Modal";
import { SpecHead } from "@/components/workspace";
import type { ScopeForm } from "@/lib/workspace/types";
import { Field } from "./fields";

export function ScopeSettingsModal({
  scopeOpen,
  setScopeOpen,
  resetScopeSettings,
  saveScopeSettings,
  scopeForm,
  setScopeForm,
  icpOptions,
  scopeIcp,
  switchScopeIcp,
}: {
  scopeOpen: boolean;
  setScopeOpen: (v: boolean) => void;
  resetScopeSettings: () => void;
  saveScopeSettings: () => void;
  scopeForm: ScopeForm | null;
  setScopeForm: (f: ScopeForm) => void;
  icpOptions: { id: string; label: string }[];
  scopeIcp: string;
  switchScopeIcp: (icp: string) => void;
}) {
  return (
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
  );
}
