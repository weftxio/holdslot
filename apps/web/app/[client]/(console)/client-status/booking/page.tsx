"use client";
import { useState } from "react";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import { B_LOG, type BookingRow } from "@/lib/fixtures/client-status";

export default function BookingPage() {
  const toast = useToast();

  // "Propose new time" inline editor for expired bookings (one open at a time)
  const [propose, setPropose] = useState<{ name: string; time: string; msg: string } | null>(null);
  const openPropose = (r: BookingRow) =>
    setPropose({
      name: r.name,
      time: "",
      msg:
        `Hi ${r.name}, your earlier booking link expired before we could lock a time. ` +
        `Here's a fresh suggested slot for your call with HoldSlot — confirm and it lands on both calendars.`,
    });

  return (
    <section className="es-section active">
      <div className="es-summary">
        <div className="esc">
          <div className="ecap">Invites sent</div>
          <div className="en">
            <Sample>n</Sample>
          </div>
        </div>
        <div className="esc accent">
          <div className="ecap">Meetings accepted</div>
          <div className="en">
            <Sample>n</Sample>
          </div>
        </div>
        <div className="esc">
          <div className="ecap">Expired unused</div>
          <div className="en">1</div>
        </div>
      </div>
      <div className="panel">
        <div className="panel-head">
          <div>
            <h3>Status log</h3>
            <div className="ph-sub">
              Each prospect&apos;s suggested meeting time, the status, and the invitation email under
              every row
            </div>
          </div>
        </div>
        <div className="panel-pad">
          <div>
            {B_LOG.map((r, i) => (
              <div className="bk-card" key={r.name}>
                <div className="bk-top">
                  <div className="bk-ico">P{i + 1}</div>
                  <div className="bk-main">
                    <div className="bn">
                      {r.name} <Sample>sample</Sample>
                    </div>
                    <div className="bm">
                      Sample Co {i + 1} · invite sent {r.sent}
                    </div>
                  </div>
                  <div className="bk-date">
                    <span className="bk-date-k">Meeting date</span>
                    <span className="bk-date-v">{r.meeting}</span>
                  </div>
                  <span className={clsx("badge", r.badge)}>
                    <span className="bdot" />
                    {r.status}
                  </span>
                  {r.status === "Expired" && propose?.name !== r.name && (
                    <button className="btn btn-accent btn-sm" onClick={() => openPropose(r)}>
                      Propose new time
                    </button>
                  )}
                </div>
                {r.status === "Expired" && propose?.name === r.name && (
                  <div className="bk-propose">
                    <div className="bk-invite-label">Propose a new time</div>
                    <input
                      className="input"
                      placeholder="New suggested time (e.g. Tue, Jun 17 · 2:30 PM)"
                      value={propose.time}
                      onChange={(e) => setPropose({ ...propose, time: e.target.value })}
                    />
                    <textarea
                      className="textarea"
                      style={{ marginTop: 10 }}
                      value={propose.msg}
                      onChange={(e) => setPropose({ ...propose, msg: e.target.value })}
                    />
                    <div className="row" style={{ marginTop: 10, justifyContent: "flex-end" }}>
                      <button className="btn btn-ghost btn-sm" onClick={() => setPropose(null)}>
                        Cancel
                      </button>
                      <button
                        className="btn btn-accent btn-sm"
                        onClick={() => {
                          setPropose(null);
                          toast("New invite sent to " + r.name);
                        }}
                      >
                        Send new invite
                      </button>
                    </div>
                  </div>
                )}
                <div className="bk-invite">
                  <div className="bk-invite-label">Invitation email sent</div>
                  <div className="tmpl-mail">
                    <div className="tmpl-mailhead">
                      <div className="trow">
                        <span className="tk">Subject</span>
                        <span className="tv subj">{r.name}, your meeting time with HoldSlot</span>
                      </div>
                    </div>
                    <div className="tmpl-body">
                      <p>
                        Hi {r.name}, thanks for your interest. We&apos;ve set aside a suggested time
                        for your call with HoldSlot: <strong>{r.meeting}</strong>. It lands on both
                        calendars once you confirm. Calls may be recorded so we can share a short
                        summary with the host.
                      </p>
                      <a className="tmpl-cta">Confirm this time</a>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
