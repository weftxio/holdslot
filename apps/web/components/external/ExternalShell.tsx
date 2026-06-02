"use client";
import Link from "next/link";
import { StateToggle, useLinkState } from "../StateToggle";
import "../external.css";

const footDot = {
  width: 9,
  height: 9,
  borderRadius: "50%",
  background: "var(--cerulean)",
  display: "inline-block",
} as const;

export function ExternalShell({
  secure,
  narrow,
  footBy,
  footNote,
  expiredTitle,
  expiredLines,
  success,
  done,
  children,
}: {
  secure: string;
  narrow?: boolean;
  footBy: string;
  footNote: string;
  expiredTitle: string;
  expiredLines: string[];
  success: React.ReactNode;
  done: boolean;
  children: React.ReactNode;
}) {
  const [state, setState] = useLinkState();
  const expired = state === "expired";

  return (
    <div className="ext-body">
      <StateToggle state={state} onChange={setState} />

      <div className="ext-top">
        <Link href="/" className="logo">
          <span className="dot" />
          HoldSlot
        </Link>
        <span className="secure">{secure}</span>
      </div>

      <div className="ext-main">
        <div className={"ext-card" + (narrow ? " ext-card-narrow" : "")}>
          {!expired && !done && children}

          {!expired && done && <div className="success-pane show">{success}</div>}

          {expired && (
            <div className="expired-pane show">
              <div className="expired-card">
                <div className="xmark">⏱</div>
                <h1>{expiredTitle}</h1>
                {expiredLines.map((l, i) => (
                  <p key={i}>{l}</p>
                ))}
                <div style={{ marginTop: 26 }}>
                  <Link href="/" className="btn btn-ghost">
                    Back to HoldSlot
                  </Link>
                </div>
              </div>
            </div>
          )}

          {!expired && !done && (
            <div className="ext-foot">
              <span className="by">
                <span style={footDot} />
                {footBy}
              </span>
              <span className="muted" style={{ fontSize: 12 }}>
                {footNote}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
