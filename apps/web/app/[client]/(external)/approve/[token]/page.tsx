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

// One-line "why a fit" summary shown under each prospect (placeholder copy for the mock).
const SUMMARIES = [
  "Placeholder: matches your ICP, recently showed a buying signal.",
  "Placeholder: right seniority and team size, active in your category.",
  "Placeholder: fits your target industry and deal-size profile.",
  "Placeholder: decision-maker at a company in your sweet spot.",
  "Placeholder: strong fit on role, region, and tech stack.",
  "Placeholder: matches your ICP, growing team with a relevant need.",
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
          HoldSlot has prepared this list of prospects for <b>Northwind</b> <Sample>sample</Sample>{" "}
          for your review · please approve within 5 days so we can keep your campaign on schedule.
          Nothing is contacted until you approve. Remove anyone who isn&apos;t a fit, then approve
          in one click.
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
                <div className="why">{SUMMARIES[i]}</div>
              </div>
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
          <button className="btn btn-primary" onClick={() => setDone(true)} disabled={live === 0}>
            Approve {live} prospect{live === 1 ? "" : "s"} &amp; start outreach
          </button>
        </div>
      </div>
    </ExternalShell>
  );
}
