import { type ReactNode } from "react";

// The Cancel + confirm-action pair passed as a Modal `footer` (S5). The send / delete / decide /
// correct / add-company / add-person modals across the workspace share one shape: a ghost Cancel
// and a variant action button, both disabled while the action is in flight, the action swapping to
// a busy label. `confirmDisabled` adds a validation gate (e.g. an empty required field). Footers
// with a third button (e.g. "Reset to AI scope") or a lone "Done" button are intentionally not
// covered — they aren't this pattern.
export function ConfirmFooter({
  onCancel,
  onConfirm,
  busy,
  busyLabel,
  confirmLabel,
  variant = "primary",
  confirmDisabled = false,
}: {
  onCancel: () => void;
  onConfirm: () => void;
  busy: boolean;
  busyLabel: ReactNode;
  confirmLabel: ReactNode;
  variant?: "primary" | "accent" | "danger";
  confirmDisabled?: boolean;
}) {
  return (
    <>
      <button className="btn btn-ghost btn-sm" onClick={onCancel} disabled={busy}>
        Cancel
      </button>
      <button
        className={`btn btn-${variant} btn-sm`}
        onClick={onConfirm}
        disabled={busy || confirmDisabled}
      >
        {busy ? busyLabel : confirmLabel}
      </button>
    </>
  );
}
