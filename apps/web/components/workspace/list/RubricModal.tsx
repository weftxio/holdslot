// The versioned fit-rubric editor (append-only). Extracted from list/page.tsx (2.4 Stage 1) as a
// pure presentational modal — every handler (openRubric/saveDoc) and the fetched sample prompt stay
// in the parent and arrive as props; the JSX body is byte-identical to the inline original.
import { Modal } from "@/components/Modal";
import { PromptEditorShell } from "@/components/workspace";
import type { FitPrompt, FitStage, SourcingDocList } from "@/lib/api";

export function RubricModal({
  showSourcing,
  setShowSourcing,
  rubricStage,
  saveDoc,
  savingDoc,
  rubricDraft,
  setRubricDraft,
  fitPrompt,
  docs,
  fitPromptLoading,
  fitPromptErr,
}: {
  showSourcing: boolean;
  setShowSourcing: (v: boolean) => void;
  rubricStage: FitStage;
  saveDoc: (stage: FitStage) => void;
  savingDoc: FitStage | null;
  rubricDraft: string;
  setRubricDraft: (v: string) => void;
  fitPrompt: FitPrompt | null;
  docs: SourcingDocList | null;
  fitPromptLoading: boolean;
  fitPromptErr: string | null;
}) {
  return (
    <Modal
      open={showSourcing}
      onClose={() => setShowSourcing(false)}
      title={`Fit rubric · ${rubricStage === "prospect_fit" ? "Step 2 · People" : "Step 1 · Companies"}`}
      subtitle={`The exact system + input prompt sent to the model to score each ${
        rubricStage === "prospect_fit" ? "prospect" : "company"
      }.`}
      className="modal-lg"
      footer={
        <button className="btn btn-primary btn-sm" onClick={() => setShowSourcing(false)}>
          Done
        </button>
      }
    >
      <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {fitPrompt && (
          <span className="badge badge-info">model · {fitPrompt.model.join(" → ")}</span>
        )}
        <span className="badge badge-neutral">purpose · {fitPrompt?.purpose ?? rubricStage}</span>
        <span className="badge badge-neutral">rubric v{docs?.[rubricStage]?.version ?? "—"}</span>
      </div>
      <PromptEditorShell
        systemBadge={
          <span className="badge badge-neutral">v{docs?.[rubricStage]?.version ?? "—"}</span>
        }
        systemActions={
          <button
            type="button"
            className="btn btn-accent btn-xs"
            onClick={() => saveDoc(rubricStage)}
            disabled={savingDoc === rubricStage}
          >
            {savingDoc === rubricStage ? "Saving…" : "Save as new version"}
          </button>
        }
        systemValue={rubricDraft}
        onSystemChange={setRubricDraft}
        inputMeta={
          <span className="ph-sub">
            {fitPromptLoading
              ? "loading…"
              : fitPrompt?.company
                ? `read-only · sample: ${fitPrompt.company}`
                : `read-only · no ${rubricStage === "prospect_fit" ? "prospect" : "company"} yet`}
          </span>
        }
        inputContent={
          fitPromptLoading
            ? "Loading the input prompt…"
            : fitPromptErr
              ? fitPromptErr
              : fitPrompt?.user ||
                `${
                  rubricStage === "prospect_fit"
                    ? "Find people first to preview a prospect's"
                    : "Find a company first to preview its"
                } input prompt.`
        }
        hint={
          <>
            Edits are saved for this client and used on the next re-score. Each{" "}
            {rubricStage === "prospect_fit" ? "prospect" : "company"} is scored against this rubric
            with the input prompt shown on the right.
          </>
        }
      />
    </Modal>
  );
}
