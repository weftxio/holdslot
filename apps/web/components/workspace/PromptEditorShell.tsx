import { type ReactNode } from "react";

// The two-pane prompt editor shared by the list-page rubric modal and the spec-panel prompt modal
// (S6). The layout is identical — an editable System-prompt column (badge + action row + textarea)
// beside a read-only Input-prompt column (meta + <pre>), with a hint line beneath — but every leaf
// differs between the two, so they're passed in as slots. The badge row ABOVE this (model / purpose
// / version) is NOT part of the shell; it differs and stays at each call site.
export function PromptEditorShell({
  systemBadge,
  systemActions,
  systemValue,
  onSystemChange,
  inputMeta,
  inputContent,
  hint,
}: {
  systemBadge: ReactNode;
  systemActions: ReactNode;
  systemValue: string;
  onSystemChange: (v: string) => void;
  inputMeta: ReactNode;
  inputContent: ReactNode;
  hint: ReactNode;
}) {
  return (
    <>
      <div className="prompt-cols">
        {/* LEFT — System prompt: editable, saved per client as the next version. */}
        <div className="prompt-col">
          <div className="prompt-col-head">
            <label>System prompt {systemBadge}</label>
            <div className="row" style={{ gap: 8, alignItems: "center" }}>
              {systemActions}
            </div>
          </div>
          <textarea
            className="prompt-edit"
            value={systemValue}
            spellCheck={false}
            onChange={(e) => onSystemChange(e.target.value)}
          />
        </div>
        {/* RIGHT — Input prompt: read-only, the real message the model receives. */}
        <div className="prompt-col">
          <div className="prompt-col-head">
            <label>Input prompt</label>
            {inputMeta}
          </div>
          <pre className="prompt-pre">{inputContent}</pre>
        </div>
      </div>
      <div className="ph-sub prompt-hint">{hint}</div>
    </>
  );
}
