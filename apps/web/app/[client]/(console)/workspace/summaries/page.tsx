"use client";
import { useState } from "react";
import clsx from "clsx";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";

const OUTCOME: Record<string, { label: string; badge: string }> = {
  qualified: { label: "Qualified", badge: "badge-ok" },
  short_call: { label: "Short call", badge: "badge-warn" },
  noshow: { label: "No-show", badge: "badge-danger" },
};

function fmt(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function SummariesPage() {
  // N47 — recaps come from the shared provider (not a static import) so a campaign rename remaps
  // their tag and they stay in this filter instead of orphaning under the old name.
  const { campaigns, recaps } = useWorkspace();
  const [sumCamp, setSumCamp] = useState("");
  const recapsInView = recaps.filter((rc) => !sumCamp || rc.campaign === sumCamp);

  return (
    <section className="tabpane active">
      <div className="between" style={{ marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
        <div className="section-label" style={{ marginBottom: 0 }}>
          Meeting summaries, newest first
        </div>
        <select
          className="select select-sm"
          style={{ minWidth: 160 }}
          value={sumCamp}
          onChange={(e) => setSumCamp(e.target.value)}
        >
          <option value="">All campaigns</option>
          {campaigns.map((c) => (
            <option key={c.name}>{c.name}</option>
          ))}
        </select>
      </div>
      <div>
        {recapsInView.map((rc, sx) => {
          const oc = OUTCOME[rc.outcome || ""] || {
            label: rc.outcome || "—",
            badge: "badge-neutral",
          };
          return (
            <div className="sum-card" key={rc.id}>
              <div className="sum-tags">
                {rc.campaign && <span className="stag">{rc.campaign}</span>}
                {rc.batch && <span className="stag">{rc.batch}</span>}
              </div>
              <div className="sh">
                <div>
                  <div className="sm">
                    Meeting {sx + 1} · {rc.prospectName || "Prospect"}
                  </div>
                  <div className="smeta">
                    {fmt(rc.scheduledAt)} · {rc.companyName || "—"}
                  </div>
                </div>
                <span className={clsx("badge", oc.badge)}>
                  <span className="bdot" />
                  {oc.label}
                </span>
              </div>
              <div className="srow">
                <span className="sk">Recording</span>
                <span className="sv">
                  <span className="mph">Pending</span> · captured after the call
                </span>
              </div>
              <div className="srow">
                <span className="sk">Attendees</span>
                <span className="sv">
                  <span className="mph">Pending</span>
                </span>
              </div>
              <div className="srow">
                <span className="sk">Discussed</span>
                <span className="sv">
                  <span className="mph">Pending</span> · a summary is prepared after the meeting.
                </span>
              </div>
              <div className="srow">
                <span className="sk">Next step</span>
                <span className="sv">
                  <span className="mph">Pending</span>
                </span>
              </div>
              <div className="srow">
                <span className="sk">Feedback</span>
                <span className="sv">
                  {rc.rating ? `${rc.rating}/5` : <span className="mph">Awaiting</span>}
                </span>
              </div>
              <div className="srow">
                <span className="sk">Final conversion</span>
                <span className="sv">
                  <span className={clsx("badge", rc.won ? "badge-ok" : "badge-neutral")}>
                    <span className="bdot" />
                    {rc.won ? "Deal won" : "No deal"}
                  </span>
                </span>
              </div>
            </div>
          );
        })}
        {recapsInView.length === 0 && (
          <div className="sum-empty">No meeting recaps {sumCamp ? `for ${sumCamp}` : "yet"}.</div>
        )}
      </div>
    </section>
  );
}
