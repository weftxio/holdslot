"use client";
import { useState } from "react";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { MOCK_TODAY, daysAgoLabel, fmtShortDate } from "@/lib/workspace/constants";
import { NUDGE_COPY, REPLY_COPY } from "@/lib/workspace/fixtures";

export default function RepliesPage() {
  const toast = useToast();
  const { replies, setReplies, campaigns } = useWorkspace();
  const [replyCamp, setReplyCamp] = useState("");
  const remaining = replies.filter((r) => !r.done).length; // global total, for the tab pip
  const inViewReplies = replies.filter((r) => !replyCamp || r.campaign === replyCamp);
  const remainingInView = inViewReplies.filter((r) => !r.done).length;
  function finishReply(i: number, label: string) {
    setReplies((s) => s.map((r, idx) => (idx === i && !r.done ? { ...r, done: label } : r)));
  }
  function toggleEdit(i: number) {
    const wasEditing = replies[i]?.editing;
    setReplies((s) => s.map((r, idx) => (idx === i ? { ...r, editing: !r.editing } : r)));
    if (wasEditing) toast("Draft updated");
  }

  return (
    <section className="tabpane active">
      <div
        className="row"
        style={{ marginBottom: 18, justifyContent: "flex-end", flexWrap: "wrap", gap: 12 }}
      >
        {remaining > 0 ? (
          <span className="badge badge-warn">
            <span className="bdot" />
            {remaining} awaiting review
          </span>
        ) : (
          <span className="badge badge-ok">
            <span className="bdot" />
            All handled
          </span>
        )}
        <select
          className="select select-sm"
          style={{ minWidth: 160 }}
          value={replyCamp}
          onChange={(e) => setReplyCamp(e.target.value)}
        >
          <option value="">All campaigns</option>
          {campaigns.map((c) => (
            <option key={c.name}>{c.name}</option>
          ))}
        </select>
      </div>
      <div>
        {replies.map((r, i) => {
          // One source of truth for the two reply modes (inbound reply vs follow-up nudge).
          const c = r.nudge ? NUDGE_COPY : { ...REPLY_COPY, body: r.quote };
          return (
            <div
              key={i}
              className={clsx("reply", r.done && "done")}
              style={{ display: !replyCamp || r.campaign === replyCamp ? undefined : "none" }}
            >
              <div className="reply-head">
                <div className="av-sm">R{i + 1}</div>
                <div className="meta">
                  <div className="nm">{r.n}</div>
                  <div className="ro">{r.role}</div>
                  <div className="tagline">
                    <span className="ttag">{r.campaign}</span>
                    <span className="ttag">{r.batch}</span>
                    {r.nudge && <span className="ttag nudge">Follow-up nudge</span>}
                  </div>
                </div>
                <span className={clsx("badge", r.badge)}>
                  <span className="bdot" />
                  {r.cls}
                </span>
              </div>
              <div className="reply-quote">
                <div className="reply-qhead">
                  <span className="ql">{c.qhead}</span>
                  <span className="reply-date">
                    {c.datePrefix}
                    {fmtShortDate(r.repliedAt)} · {daysAgoLabel(r.repliedAt, MOCK_TODAY)}
                  </span>
                </div>
                {c.body}
              </div>
              <div className="reply-draft">
                <div className="dl">
                  {c.draftLabel} <Sample>auto-draft</Sample>
                </div>
                <textarea
                  readOnly={!r.editing}
                  value={r.text}
                  onChange={(e) => {
                    const v = e.target.value;
                    setReplies((s) => s.map((x, idx) => (idx === i ? { ...x, text: v } : x)));
                  }}
                />
                <div className="reply-actions">
                  <button className="btn btn-ghost btn-sm" onClick={() => toggleEdit(i)}>
                    {r.editing ? "Done editing" : "Edit draft"}
                  </button>
                  <button
                    className="btn btn-accent btn-sm"
                    onClick={() => {
                      finishReply(i, c.done);
                      toast(c.done);
                    }}
                  >
                    {c.cta}
                  </button>
                </div>
              </div>
              <div className="reply-sent-banner">
                <span>✓</span>
                <span>{r.done}</span>
              </div>
            </div>
          );
        })}
        {replyCamp && inViewReplies.length === 0 && (
          <div className="sum-empty">No replies for {replyCamp} yet.</div>
        )}
      </div>
      <div
        className={clsx(
          "queue-empty",
          inViewReplies.length > 0 && remainingInView === 0 && "show"
        )}
      >
        <div className="ee">✓</div>
        <h3 style={{ fontSize: 20, color: "var(--ink)", marginBottom: 6 }}>Queue clear</h3>
        <p style={{ fontSize: 14 }}>
          Every classified reply has been handled. New replies will appear here as they&apos;re
          sorted.
        </p>
      </div>
    </section>
  );
}
