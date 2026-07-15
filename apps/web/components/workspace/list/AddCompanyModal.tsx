// Add-company modal (manual, stage 1) — same schema as an imported row, source=manual. Extracted
// from list/page.tsx (2.4 Stage 1) as a pure presentational modal; `submitAddCompany` (which calls
// the API + kicks the background score) stays in the parent and arrives as a prop.
import { Modal } from "@/components/Modal";
import { ConfirmFooter } from "@/components/workspace";
import { Field, ManualBadges, type ManualCompanyForm } from "./fields";

export function AddCompanyModal({
  addCoOpen,
  setAddCoOpen,
  submitAddCompany,
  savingCo,
  coForm,
  setCoForm,
}: {
  addCoOpen: boolean;
  setAddCoOpen: (v: boolean) => void;
  submitAddCompany: () => void;
  savingCo: boolean;
  coForm: ManualCompanyForm;
  setCoForm: (f: ManualCompanyForm) => void;
}) {
  return (
    <Modal
      open={addCoOpen}
      onClose={() => setAddCoOpen(false)}
      title="Add company"
      subtitle="Add one company by hand · suppression-checked, then fit-scored against your rubric on save."
      footer={
        <ConfirmFooter
          onCancel={() => setAddCoOpen(false)}
          onConfirm={submitAddCompany}
          busy={savingCo}
          confirmDisabled={!coForm.domain.trim()}
          busyLabel="Scoring…"
          confirmLabel="Add + score"
        />
      }
    >
      <ManualBadges />
      <Field
        label="Company domain *"
        placeholder="acme.com"
        value={coForm.domain}
        onChange={(v) => setCoForm({ ...coForm, domain: v })}
      />
      <Field
        label="Name"
        placeholder="Acme Robotics"
        value={coForm.name}
        onChange={(v) => setCoForm({ ...coForm, name: v })}
      />
      <Field
        label="Website"
        placeholder="https://acme.com"
        value={coForm.website}
        onChange={(v) => setCoForm({ ...coForm, website: v })}
      />
      <div className="sourcing-cols">
        <Field
          label="Industry"
          value={coForm.industry}
          onChange={(v) => setCoForm({ ...coForm, industry: v })}
        />
        <Field
          label="Size"
          placeholder="201-500"
          value={coForm.size}
          onChange={(v) => setCoForm({ ...coForm, size: v })}
        />
      </div>
      <div className="sourcing-cols">
        <Field
          label="Country"
          value={coForm.country}
          onChange={(v) => setCoForm({ ...coForm, country: v })}
        />
        <Field
          label="Company LinkedIn"
          placeholder="linkedin.com/company/…"
          value={coForm.linkedin_url}
          onChange={(v) => setCoForm({ ...coForm, linkedin_url: v })}
        />
      </div>
      <div className="ph-sub" style={{ marginTop: 16 }}>
        Domain required · rest optional · scored on save.
      </div>
    </Modal>
  );
}
