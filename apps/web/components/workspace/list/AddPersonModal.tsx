// Add-person modal (manual, stage 2) — same schema as an imported row, source=manual. Extracted
// from list/page.tsx (2.4 Stage 1) as a pure presentational modal; `submitAddPerson` stays in the
// parent and arrives as a prop. The company dropdown reads the Step-2 companies passed in.
import { Modal } from "@/components/Modal";
import { ConfirmFooter } from "@/components/workspace";
import type { CompanyApi } from "@/lib/api";
import { Field, ManualBadges, type ManualPersonForm } from "./fields";

export function AddPersonModal({
  addPersonOpen,
  setAddPersonOpen,
  submitAddPerson,
  savingPerson,
  personForm,
  setPersonForm,
  step2Companies,
}: {
  addPersonOpen: boolean;
  setAddPersonOpen: (v: boolean) => void;
  submitAddPerson: () => void;
  savingPerson: boolean;
  personForm: ManualPersonForm;
  setPersonForm: (f: ManualPersonForm) => void;
  step2Companies: CompanyApi[];
}) {
  return (
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
  );
}
