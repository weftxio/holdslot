"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { decideApproval, getApproval, type ApprovalViewApi } from "@/lib/api";
import { ExternalShell } from "@/components/external/ExternalShell";
import "./approve.css";

export default function Approve() {
  const token = useParams<{ token: string }>().token;
  const [view, setView] = useState<ApprovalViewApi | null>(null);
  const [removed, setRemoved] = useState<Record<string, boolean>>({});
  const [done, setDone] = useState(false);
  const [mode, setMode] = useState<"approved" | "changes">("approved");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getApproval(token)
      .then(setView)
      .catch(() =>
        setView({ state: "expired", batch_name: "", client_name: "", count: 0, expires_at: null, prospects: [] })
      );
  }, [token]);

  const prospects = view?.prospects ?? [];
  const live = prospects.length - prospects.filter((p) => removed[p.id]).length;

  async function approve() {
    if (busy) return;
    setBusy(true);
    try {
      const removed_ids = prospects.filter((p) => removed[p.id]).map((p) => p.id);
      await decideApproval(token, { removed_ids });
      setMode("approved");
      setDone(true);
    } catch {
      // The link lapsed/was used between load and submit — flip to the expired pane.
      setView((v) => (v ? { ...v, state: "used" } : v));
    } finally {
      setBusy(false);
    }
  }

  async function requestChanges() {
    if (busy) return;
    setBusy(true);
    try {
      await decideApproval(token, { request_changes: true });
      setMode("changes");
      setDone(true);
    } catch {
      setView((v) => (v ? { ...v, state: "used" } : v));
    } finally {
      setBusy(false);
    }
  }

  const success =
    mode === "changes" ? (
      <div className="success-inner">
        <div className="tick">✓</div>
        <h1>Thanks — we&apos;ll revise the list.</h1>
        <p className="confirm-copy">
          Your HoldSlot operator has been notified and will send an updated list shortly.
          <br />
          Nothing is contacted until you approve.
        </p>
        <p className="muted" style={{ fontSize: 13, marginTop: 18 }}>
          You can close this page. No account needed.
        </p>
      </div>
    ) : (
      <div className="success-inner">
        <div className="tick">✓</div>
        <h1>List approved.</h1>
        <p className="confirm-copy">
          Thank you.
          <br />
          We&apos;ll reach out to your approved prospects from warmed inboxes.
          <br />
          Replies are handled and qualified meetings land on your calendar.
        </p>
        <p className="muted" style={{ fontSize: 13, marginTop: 18 }}>
          You can close this page. No account needed.
        </p>
      </div>
    );

  const forceExpired = !!view && view.state !== "valid";

  return (
    <ExternalShell
      secure="🔒 Secure link · for the client"
      footBy="Sent securely by HoldSlot"
      expiredTitle={view?.state === "used" ? "This link has already been used" : "This link has expired"}
      expiredLines={[
        "For security, approval links are valid for a limited time and can be used once.",
        "We've let your HoldSlot operator know. A fresh link is on its way to your inbox shortly.",
      ]}
      success={success}
      done={done}
      forceExpired={forceExpired}
    >
      <div className="ext-head">
        <span className="eyebrow">Your approval needed</span>
        <h1>Approve your prospect list</h1>
        <p>
          HoldSlot has prepared this list of prospects for <b>{view?.client_name || "your team"}</b>{" "}
          for your review. Nothing is contacted until you approve. Remove anyone who isn&apos;t a fit,
          then approve in one click.
        </p>
      </div>
      <div className="ext-pad">
        <div className="summary-strip">
          <span>
            <b>{view?.batch_name || "Your batch"}</b> · {live} prospect{live === 1 ? "" : "s"} ·
            matched to your brief
          </span>
          <span className="badge badge-warn">
            <span className="bdot" />
            Awaiting approval
          </span>
        </div>

        {!view ? (
          <div className="ph" style={{ padding: "24px 4px" }}>
            Loading your prospect list…
          </div>
        ) : (
          <div className="approve-list">
            {prospects.map((p, i) => (
              <div className={"approve-row" + (removed[p.id] ? " removed" : "")} key={p.id}>
                <div className="av-sm">P{i + 1}</div>
                <div className="ai">
                  <div className="nm">{p.name || "Prospect"}</div>
                  <div className="rl">
                    {[p.title, p.company_descriptor].filter(Boolean).join(" · ")}
                  </div>
                  {p.fit_reason && <div className="why">{p.fit_reason}</div>}
                </div>
                <button
                  className="ex"
                  onClick={() => setRemoved((s) => ({ ...s, [p.id]: !s[p.id] }))}
                >
                  {removed[p.id] ? "Undo" : "Reject"}
                </button>
              </div>
            ))}
            {prospects.length === 0 && (
              <div className="ph" style={{ padding: "18px 4px" }}>
                This batch has no prospects to review.
              </div>
            )}
          </div>
        )}

        <div className="consent" style={{ marginBottom: 20 }}>
          <span className="ci">✓</span>
          <span>
            Every prospect was verified against your exclusion rules. By approving, you authorise
            HoldSlot to begin outreach to this list on your behalf. You can pause anytime.
          </span>
        </div>

        <div className="cta-row">
          {live > 0 ? (
            <button className="btn btn-primary" onClick={approve} disabled={busy || !view}>
              {`Approve ${live} prospect${live === 1 ? "" : "s"} & start outreach`}
            </button>
          ) : (
            // Every prospect removed → the one action left is to bounce the whole list back. Submits
            // request_changes, so the batch goes Rejected (reopenable via the operator's Re-send).
            <button className="btn btn-danger" onClick={requestChanges} disabled={busy || !view}>
              Reject the list
            </button>
          )}
        </div>
      </div>
    </ExternalShell>
  );
}
