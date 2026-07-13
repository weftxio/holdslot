"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { useToast } from "@/components/Toast";
import { informClient, listFeedback, sendFeedbackForm, type FeedbackRowApi } from "@/lib/api";

const BADGE: Record<string, string> = {
  Received: "badge-ok",
  Pending: "badge-warn",
  None: "badge-neutral",
};

function Stars({ n }: { n: number }) {
  return (
    <span className="stars-sm">
      {[1, 2, 3, 4, 5].map((i) =>
        i <= n ? (
          <span key={i}>★</span>
        ) : (
          <span key={i} className="off">
            ★
          </span>
        )
      )}
    </span>
  );
}

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function FeedbackPage() {
  const client = useParams<{ client: string }>().client;
  const toast = useToast();
  const [rows, setRows] = useState<FeedbackRowApi[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    listFeedback(client).then(setRows).catch(() => setRows([]));
  }, [client]);
  useEffect(() => load(), [load]);

  async function follow(r: FeedbackRowApi) {
    setBusy(r.id);
    try {
      await sendFeedbackForm(client, r.id);
      toast("Feedback form sent to " + (r.prospect_name || "prospect"));
      load();
    } catch {
      toast("Could not send the feedback form", "warn"); // M31 — failures render as warnings
    } finally {
      setBusy(null);
    }
  }

  async function inform(r: FeedbackRowApi) {
    setBusy(r.id);
    try {
      await informClient(client, r.id);
      toast("Flagged low rating to the client");
    } catch {
      toast("No client attendee email on file", "warn"); // M31 — failures render as warnings
    } finally {
      setBusy(null);
    }
  }

  const list = rows ?? [];
  const responses = list.filter((r) => r.state === "Received").length;
  const rated = list.filter((r) => r.rating);
  const avg = rated.length
    ? (rated.reduce((s, r) => s + (r.rating || 0), 0) / rated.length).toFixed(1)
    : "—";

  return (
    <section className="es-section active">
      <div className="es-summary">
        <div className="esc">
          <div className="ecap">Forms sent</div>
          <div className="en">{list.length}</div>
        </div>
        <div className="esc accent">
          <div className="ecap">Responses</div>
          <div className="en">{responses}</div>
        </div>
        <div className="esc">
          <div className="ecap">Average rating</div>
          <div className="en">{avg}</div>
        </div>
      </div>
      <div className="panel">
        <div className="panel-head">
          <div>
            <h3>Feedback history</h3>
            <div className="ph-sub">Ratings and comments returned by prospects</div>
          </div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Prospect</th>
                <th>Meeting date</th>
                <th>Rating</th>
                <th>Comment</th>
                <th>Feedback date</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows === null && (
                <tr>
                  <td colSpan={7} className="muted">
                    Loading…
                  </td>
                </tr>
              )}
              {rows !== null && list.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted">
                    No held meetings yet — feedback opens after a meeting is held.
                  </td>
                </tr>
              )}
              {list.map((r, i) => (
                <tr key={r.id}>
                  <td>
                    <div className="who-cell">
                      <div className="av-sm">P{i + 1}</div>
                      <div>
                        <div className="nm">{r.prospect_name || "Prospect"}</div>
                        <div className="sub">{r.company_name}</div>
                      </div>
                    </div>
                  </td>
                  <td className="muted tnum">{fmt(r.scheduled_at)}</td>
                  <td>
                    {r.rating ? <Stars n={r.rating} /> : <span className="muted">Pending</span>}
                  </td>
                  <td>
                    <div className="log-comment">{r.comment || (r.overdue ? "Overdue" : "—")}</div>
                  </td>
                  <td className="muted tnum">{fmt(r.feedback_at)}</td>
                  <td>
                    <span className={clsx("badge", BADGE[r.state] || "badge-neutral")}>
                      <span className="bdot" />
                      {r.state}
                    </span>
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {r.state !== "Received" && r.overdue && (
                      <button
                        className="btn btn-ghost btn-2xs"
                        disabled={busy === r.id}
                        onClick={() => follow(r)}
                      >
                        Send Follow-Up
                      </button>
                    )}
                    {r.rating != null && r.rating > 0 && r.rating <= 3 && (
                      <button
                        className="btn btn-ghost btn-2xs"
                        disabled={busy === r.id}
                        onClick={() => inform(r)}
                      >
                        Inform client
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
