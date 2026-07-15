// Shared leaf atoms for the Prospect-List modals (2.4 Stage 1). `Field`/`ManualBadges`/`FacetRow`
// were module-level helpers in list/page.tsx; the five extracted modals are their only consumers, so
// they move here verbatim. The two manual-add form shapes live here too, shared by page.tsx's state
// and the Add-company / Add-person modal props.
import { useId } from "react";

// The manual-add company form (Add-company modal) — same field set as an imported row.
export type ManualCompanyForm = {
  domain: string;
  name: string;
  website: string;
  industry: string;
  size: string;
  country: string;
  linkedin_url: string;
};

// The manual-add person form (Add-person modal).
export type ManualPersonForm = {
  full_name: string;
  company: string;
  domain: string;
  linkedin_url: string;
  email: string;
  title: string;
  seniority: string;
};

// A labelled text/number input in the scope / add-company / add-person modals (S4) — the
// `div.field > label + input.input` block repeated 17× with only label/value/placeholder/type
// varying. `onChange` receives the raw string value.
export function Field({
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
  // L20 (a11y) — associate the caption with the input via htmlFor/id so all modal inputs have an
  // accessible name (the bare <label> gave none). useId keeps it unique across the ~17 reuses.
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
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
export function ManualBadges() {
  return (
    <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
      <span className="badge badge-neutral">source · manual</span>
      <span className="badge badge-info">fit-scored on add</span>
    </div>
  );
}

// One checkbox row in the Personas facet sidebar (seniority + departments, probed or not, S19) —
// label + optional live count. `key` stays on the call site, per the .map contract.
export function FacetRow({
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
