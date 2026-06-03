"use client";
import { useState } from "react";
import { Sample } from "@/components/Sample";
import { ExternalShell } from "@/components/external/ExternalShell";
import "./book.css";

const DAYS: [string, string][] = [
  ["Mon", "12"],
  ["Tue", "13"],
  ["Wed", "14"],
  ["Thu", "15"],
  ["Fri", "16"],
];
const SLOTS: string[][] = [
  ["9:00", "10:30", "13:00", "14:00", "15:30", "16:30"],
  ["9:30", "11:00", "11:30", "13:30", "15:00", "16:00"],
  ["10:00", "10:30", "12:00", "14:30", "15:30", "17:00"],
  ["9:00", "9:30", "13:00", "14:00", "16:00", "16:30"],
  ["10:30", "11:00", "12:30", "13:30", "14:30", "15:00"],
];
const TAKEN: number[][] = [[2], [4], [1], [3], [0]];

export default function Book() {
  const [day, setDay] = useState(1);
  const [time, setTime] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const dn = DAYS[day][0] + " " + DAYS[day][1];

  const success = (
    <div className="success-inner">
      <div className="tick">✓</div>
      <h1>You&apos;re booked.</h1>
      <div className="booked-chip">
        📅{" "}
        <span>
          {dn} · {time} (placeholder)
        </span>
      </div>
      <p>
        A calendar invite with the video link is on its way to your inbox. You&apos;ll get a
        reminder before the call.
      </p>
      <p className="muted" style={{ fontSize: 13, marginTop: 16 }}>
        Need to reschedule? Use the link in your confirmation email.
      </p>
    </div>
  );

  return (
    <ExternalShell
      secure="🔒 Secure link · expires after use"
      footBy="Scheduling by HoldSlot"
      footNote="No account needed."
      expiredTitle="This booking link has expired"
      expiredLines={[
        "For security, booking links are valid for a limited time or a single use. This one is no longer active.",
        "Reply to the email you received and we'll send a fresh link with new times right away.",
      ]}
      success={success}
      done={done}
    >
      <div className="ext-head">
        <span className="eyebrow">You&apos;re invited</span>
        <h1>Book your meeting</h1>
        <p>
          Thanks for your interest in <b>Northwind</b> <Sample>sample</Sample>. Pick a time that
          works and it drops straight onto both calendars with an invite.
        </p>
        <div className="meeting-meta" style={{ marginTop: 16 }}>
          <span className="mm">
            <span className="mi">◷</span>30 minutes
          </span>
          <span className="mm">
            <span className="mi">▦</span>Video call
          </span>
          <span className="mm">
            <span className="mi">◑</span>With placeholder host
          </span>
        </div>
      </div>
      <div className="ext-pad">
        <div className="section-label">Choose a day</div>
        <div className="day-tabs">
          {DAYS.map((d, i) => (
            <button
              key={i}
              className={"day-tab" + (i === day ? " on" : "")}
              onClick={() => {
                setDay(i);
                setTime(null);
              }}
            >
              <div className="dow">{d[0]}</div>
              <div className="dnum">{d[1]}</div>
            </button>
          ))}
        </div>

        <div className="section-label">
          Available times <Sample>sample</Sample>
        </div>
        <div className="slots">
          {SLOTS[day].map((t, si) => {
            const taken = TAKEN[day].includes(si);
            return (
              <button
                key={si}
                className={"slot" + (taken ? " taken" : "") + (!taken && time === t ? " on" : "")}
                disabled={taken}
                onClick={() => !taken && setTime(t)}
              >
                {t}
                {!taken && <span className="smark">✓</span>}
              </button>
            );
          })}
        </div>
        <div className="tzrow">🌐 Times shown in your local timezone · placeholder TZ</div>

        <div className="consent">
          <span className="ci">●</span>
          <span>
            <b style={{ color: "var(--ink)" }}>Recording notice.</b> This call may be recorded and
            transcribed so HoldSlot can prepare a meeting summary for the host. By booking, you
            consent to recording. You can ask the host to turn it off at any point during the call.
          </span>
        </div>

        <div className="confirm-bar">
          <span className="pick">
            {time ? (
              <>
                Selected ·{" "}
                <b>
                  {dn} at {time}
                </b>
              </>
            ) : (
              "Select a time to continue"
            )}
          </span>
          <button className="btn btn-primary" disabled={!time} onClick={() => setDone(true)}>
            Confirm booking
          </button>
        </div>
      </div>
    </ExternalShell>
  );
}
