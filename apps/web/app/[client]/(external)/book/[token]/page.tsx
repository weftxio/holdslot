"use client";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Sample } from "@/components/Sample";
import { ExternalShell } from "@/components/external/ExternalShell";
import { RetryNotice } from "@/components/external/RetryNotice";
import {
  getBookingView,
  isLinkGoneError,
  isSlotTakenError,
  submitBooking,
  type BookingViewApi,
} from "@/lib/api";
import "./book.css";

// Group UTC slot instants into the viewer's local days (the mock's "Times shown in your local
// timezone"). Each day carries its weekday label + day-of-month + the local time buttons.
type LocalDay = { key: string; dow: string; dnum: string; slots: { iso: string; label: string }[] };

function groupByLocalDay(slots: string[]): LocalDay[] {
  const days = new Map<string, LocalDay>();
  for (const iso of slots) {
    const d = new Date(iso);
    const key = d.toLocaleDateString(undefined, { year: "numeric", month: "2-digit", day: "2-digit" });
    if (!days.has(key)) {
      days.set(key, {
        key,
        dow: d.toLocaleDateString(undefined, { weekday: "short" }),
        dnum: d.toLocaleDateString(undefined, { day: "numeric" }),
        slots: [],
      });
    }
    days.get(key)!.slots.push({
      iso,
      label: d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }),
    });
  }
  return [...days.values()];
}

export default function Book() {
  const token = useParams<{ token: string }>().token;
  const [view, setView] = useState<BookingViewApi | null>(null);
  const [day, setDay] = useState(0);
  const [slot, setSlot] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    // The booking endpoint is never-404: a dead link returns a 200 `state`, so a THROWN error here
    // is always transient (cold-start / network). Surface a retry — never a fake "expired" (M1).
    getBookingView(token)
      .then((v) => alive && setView(v))
      .catch(() => alive && setLoadError(true));
    return () => {
      alive = false;
    };
  }, [token, reloadNonce]);

  const reload = () => {
    setView(null);
    setSlot(null);
    setSubmitError("");
    setLoadError(false);
    setReloadNonce((n) => n + 1);
  };

  const localDays = useMemo(() => groupByLocalDay(view?.slots ?? []), [view?.slots]);
  const chosenLabel = useMemo(() => {
    if (!slot) return null;
    const d = new Date(slot);
    return `${d.toLocaleDateString(undefined, { weekday: "short", day: "numeric" })} at ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
  }, [slot]);

  async function confirm() {
    if (!slot || busy) return;
    setBusy(true);
    setSubmitError("");
    try {
      await submitBooking(token, slot);
      setDone(true);
    } catch (e) {
      if (isLinkGoneError(e)) {
        // 410 — the link itself lapsed/was used between load and submit → the used/expired pane.
        setView((v) => (v ? { ...v, state: "used" } : v));
      } else if (isSlotTakenError(e)) {
        // 409 — that slot was just taken. The link is still good: keep the picker, refresh the
        // times, and tell them to pick another (never a dead-end — that would lose the meeting).
        setSlot(null);
        setSubmitError("That time was just taken — pick another below.");
        reload();
      } else {
        // 400 tampered · 503 cold-start · network — keep the picker, offer a retry inline.
        setSubmitError("We couldn't book that just now — please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  const success = (
    <div className="success-inner">
      <div className="tick">✓</div>
      <h1>You&apos;re booked.</h1>
      {chosenLabel && (
        <div className="booked-chip">
          📅 <span>{chosenLabel}</span>
        </div>
      )}
      <p>
        A calendar invite with the video link is on its way to your inbox. You&apos;ll get a reminder
        before the call.
      </p>
      <p className="muted" style={{ fontSize: 13, marginTop: 16 }}>
        Need to reschedule? Use the link in your confirmation email.
      </p>
    </div>
  );

  const forceExpired = !!view && view.state !== "valid";
  const active = localDays[day];

  return (
    <ExternalShell
      secure="🔒 Secure link · expires after use"
      footBy="Scheduling by HoldSlot"
      footNote="No account needed."
      expiredTitle={view?.state === "used" ? "This booking link has been used" : "This booking link has expired"}
      expiredLines={[
        "For security, booking links are valid for a limited time or a single use. This one is no longer active.",
        "Reply to the email you received and we'll send a fresh link with new times right away.",
      ]}
      success={success}
      done={done}
      forceExpired={forceExpired}
    >
      <div className="ext-head">
        <span className="eyebrow">You&apos;re invited</span>
        <h1>Book your meeting</h1>
        <p>
          Thanks for your interest in <b>{view?.client_name || "HoldSlot"}</b>. Pick a time that works
          and it drops straight onto both calendars with an invite.
        </p>
        <div className="meeting-meta" style={{ marginTop: 16 }}>
          <span className="mm">
            <span className="mi">◷</span>
            {view?.duration_min || 30} minutes
          </span>
          <span className="mm">
            <span className="mi">▦</span>Video call
          </span>
          <span className="mm">
            <span className="mi">◑</span>With {view?.client_name || "your host"}
          </span>
        </div>
      </div>
      <div className="ext-pad">
        {!view ? (
          loadError ? (
            <RetryNotice onRetry={reload} />
          ) : (
            <div className="ph" style={{ padding: "24px 4px" }}>
              Loading available times…
            </div>
          )
        ) : localDays.length === 0 ? (
          <div className="ph" style={{ padding: "24px 4px" }}>
            No times are open right now. Reply to your email and we&apos;ll send fresh options.
          </div>
        ) : (
          <>
            <div className="section-label">Choose a day</div>
            <div className="day-tabs">
              {localDays.map((d, i) => (
                <button
                  key={d.key}
                  className={"day-tab" + (i === day ? " on" : "")}
                  onClick={() => {
                    setDay(i);
                    setSlot(null);
                  }}
                >
                  <div className="dow">{d.dow}</div>
                  <div className="dnum">{d.dnum}</div>
                </button>
              ))}
            </div>

            <div className="section-label">Available times</div>
            <div className="slots">
              {active?.slots.map((sl) => (
                <button
                  key={sl.iso}
                  className={"slot" + (slot === sl.iso ? " on" : "")}
                  onClick={() => setSlot(sl.iso)}
                >
                  {sl.label}
                  <span className="smark">✓</span>
                </button>
              ))}
            </div>
            <div className="tzrow">🌐 Times shown in your local timezone</div>

            <div className="consent">
              <span className="ci">●</span>
              <span>
                <b style={{ color: "var(--ink)" }}>Recording notice.</b> This call may be recorded and
                transcribed so HoldSlot can prepare a meeting summary for the host. By booking, you
                consent to recording. You can ask the host to turn it off at any point during the call.
              </span>
            </div>

            {submitError && (
              <div style={{ color: "var(--danger)", fontSize: 13, margin: "4px 0 10px" }}>
                {submitError}
              </div>
            )}
            <div className="confirm-bar">
              <span className="pick">
                {chosenLabel ? (
                  <>
                    Selected · <b>{chosenLabel}</b>
                  </>
                ) : (
                  "Select a time to continue"
                )}
              </span>
              <button className="btn btn-primary" disabled={!slot || busy} onClick={confirm}>
                {busy ? "Booking…" : "Confirm booking"}
              </button>
            </div>
          </>
        )}
      </div>
    </ExternalShell>
  );
}
