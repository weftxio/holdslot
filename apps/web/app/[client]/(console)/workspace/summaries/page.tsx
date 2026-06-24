"use client";
import { useState } from "react";
import clsx from "clsx";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { RECAPS } from "@/lib/workspace/fixtures";

export default function SummariesPage() {
  const { campaigns } = useWorkspace();
  const [sumCamp, setSumCamp] = useState("");
  const recapsInView = RECAPS.filter((rc) => !sumCamp || rc.campaign === sumCamp);

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
          const recUrl = `https://meet.google.com/rec/${rc.recId}`;
          return (
            <div className="sum-card" key={rc.recId}>
              <div className="sum-tags">
                <span className="stag">{rc.campaign}</span>
                <span className="stag">{rc.batch}</span>
              </div>
              <div className="sh">
                <div>
                  <div className="sm">
                    Meeting {sx + 1} · Prospect {sx + 1}
                  </div>
                  <div className="smeta">
                    Placeholder date · Sample Co {sx + 1} · recording on file
                  </div>
                </div>
                <span className="badge badge-ok">
                  <span className="bdot" />
                  Qualified
                </span>
              </div>
              <div className="srow">
                <span className="sk">Recording</span>
                <span className="sv">
                  <a className="rec-link" href={recUrl} target="_blank" rel="noopener noreferrer">
                    {recUrl}
                  </a>
                </span>
              </div>
              <div className="srow">
                <span className="sk">Attendees</span>
                <span className="sv">Placeholder names and titles</span>
              </div>
              <div className="srow">
                <span className="sk">Discussed</span>
                <span className="sv">
                  Placeholder summary of the conversation, pain points, and current stack.
                </span>
              </div>
              <div className="srow">
                <span className="sk">Next step</span>
                <span className="sv">
                  <span className="mph">Placeholder</span>: follow-up action and owner.
                </span>
              </div>
              <div className="srow">
                <span className="sk">Sentiment</span>
                <span className="sv">Placeholder: qualified, warm, evaluating.</span>
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
          <div className="sum-empty">No meeting recaps for {sumCamp} yet.</div>
        )}
      </div>
    </section>
  );
}
