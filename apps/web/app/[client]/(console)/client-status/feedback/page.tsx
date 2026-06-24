"use client";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import { F_LOG } from "@/lib/fixtures/client-status";

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

export default function FeedbackPage() {
  const toast = useToast();

  return (
    <section className="es-section active">
      <div className="es-summary">
        <div className="esc">
          <div className="ecap">Forms sent</div>
          <div className="en">
            <Sample>n</Sample>
          </div>
        </div>
        <div className="esc accent">
          <div className="ecap">Responses</div>
          <div className="en">
            <Sample>n</Sample>
          </div>
        </div>
        <div className="esc">
          <div className="ecap">Average rating</div>
          <div className="en">
            <Sample>n</Sample>
          </div>
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
              {F_LOG.map((r, i) => (
                <tr key={r.name}>
                  <td>
                    <div className="who-cell">
                      <div className="av-sm">P{i + 1}</div>
                      <div>
                        <div className="nm">
                          {r.name} <Sample>sample</Sample>
                        </div>
                        <div className="sub">Sample Co {i + 1}</div>
                      </div>
                    </div>
                  </td>
                  <td className="muted tnum">{r.meeting}</td>
                  <td>
                    {r.rating ? <Stars n={r.rating} /> : <span className="muted">Pending</span>}
                  </td>
                  <td>
                    <div className="log-comment">{r.comment}</div>
                  </td>
                  <td className="muted tnum">{r.feedback}</td>
                  <td>
                    <span className={clsx("badge", r.badge)}>
                      <span className="bdot" />
                      {r.status}
                    </span>
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {r.status === "Awaiting" && r.overdue && (
                      <button
                        className="btn btn-ghost btn-2xs"
                        onClick={() => toast("Follow-up nudge sent to " + r.name)}
                      >
                        Send Follow-Up
                      </button>
                    )}
                    {r.rating > 0 && r.rating <= 3 && (
                      <button
                        className="btn btn-ghost btn-2xs"
                        onClick={() => toast("Flagged low rating to client for " + r.name)}
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
