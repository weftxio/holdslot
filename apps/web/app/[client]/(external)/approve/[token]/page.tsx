"use client";
import { useState } from "react";
import { Sample } from "@/components/Sample";
import { ExternalShell } from "@/components/external/ExternalShell";
import "./approve.css";

const ROLES = [
  "Placeholder title",
  "Placeholder title",
  "Placeholder title",
  "Placeholder title",
  "Placeholder title",
  "Placeholder title",
];

export default function Approve() {
  const [removed, setRemoved] = useState<Record<number, boolean>>({});
  const [done, setDone] = useState(false);
  const live = ROLES.length - Object.values(removed).filter(Boolean).length;

  const success = (
    <div className="success-inner">
      <div className="tick">✓</div>
      <h1>List approved.</h1>
      <p>
        Thank you. HoldSlot will begin reaching out to your approved prospects from warmed inboxes.
        Interested replies will be handled and qualified meetings booked straight onto your
        calendar.
      </p>
      <p className="muted" style={{ fontSize: 13, marginTop: 18 }}>
        You can close this page. No account needed.
      </p>
    </div>
  );

  return (
    <ExternalShell
      secure="🔒 Secure link · for the client"
      footBy="Sent securely by HoldSlot"
      footNote="Questions? Reply to the email this came from."
      expiredTitle="This link has expired"
      expiredLines={[
        "For security, approval links are valid for a limited time. This one is no longer active.",
        "We've let your HoldSlot operator know. A fresh link is on its way to your inbox shortly.",
      ]}
      success={success}
      done={done}
    >
      <div className="ext-head">
        <span className="eyebrow">Your approval needed</span>
        <h1>Approve your prospect list</h1>
        <p>
          HoldSlot prepared this batch for <b>Northwind</b> <Sample>sample</Sample>. Nothing is
          contacted until you approve. Remove anyone who isn&apos;t a fit, then approve in one
          click.
        </p>
      </div>
      <div className="ext-pad">
        <div className="summary-strip">
          <span>
            <b>Batch 3</b> · {live} prospects · matched to your brief
          </span>
          <span className="badge badge-warn">
            <span className="bdot" />
            Awaiting approval
          </span>
        </div>

        <div className="approve-list">
          {ROLES.map((r, i) => (
            <div className={"approve-row" + (removed[i] ? " removed" : "")} key={i}>
              <div className="av-sm">P{i + 1}</div>
              <div className="ai">
                <div className="nm">
                  Prospect {i + 1} <Sample>sample</Sample>
                </div>
                <div className="rl">
                  {r} · Sample Co {i + 1}
                </div>
              </div>
              <span className="badge badge-info" style={{ marginRight: 4 }}>
                <span className="bdot" />
                Good fit
              </span>
              <button className="ex" onClick={() => setRemoved((s) => ({ ...s, [i]: !s[i] }))}>
                {removed[i] ? "Undo" : "Remove"}
              </button>
            </div>
          ))}
        </div>

        <div className="consent" style={{ marginBottom: 20 }}>
          <span className="ci">✓</span>
          <span>
            Every prospect was verified against your exclusion rules. By approving, you authorise
            HoldSlot to begin outreach to this list on your behalf. You can pause anytime.
          </span>
        </div>

        <div className="cta-row">
          <button
            className="btn btn-ghost"
            onClick={() => alert("Mock: opens a change-request note")}
          >
            Request changes
          </button>
          <button className="btn btn-primary" onClick={() => setDone(true)}>
            Approve list &amp; start outreach <span className="arrow">→</span>
          </button>
        </div>
      </div>
    </ExternalShell>
  );
}
