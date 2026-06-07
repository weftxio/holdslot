"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import { STATUS_TABS, useStatusTab, type StatusTabKey } from "@/components/console/StatusTab";
import { highlightTokens } from "@/lib/tmpl";
import "./client-status.css";

const BACK: Record<StatusTabKey, [string, string]> = {
  approval: ["workspace#batches", "Back to Approval Batches"],
  booking: ["workspace#campaign", "Back to Outreach Campaigns"],
  feedback: ["workspace#summaries", "Back to Meeting Recaps"],
};

type ApprovalRow = {
  name: string;
  sent: string;
  prospects: string;
  responded: string;
  status: string;
  badge: string;
};
const A_LOG: ApprovalRow[] = [
  {
    name: "Batch 3",
    sent: "2 days ago",
    prospects: "48",
    responded: "Not yet",
    status: "Pending",
    badge: "badge-warn",
  },
  {
    name: "Batch 2",
    sent: "placeholder",
    prospects: "52",
    responded: "placeholder date",
    status: "Approved",
    badge: "badge-ok",
  },
  {
    name: "Batch 1",
    sent: "placeholder",
    prospects: "40",
    responded: "placeholder date",
    status: "Approved",
    badge: "badge-ok",
  },
];

type BookingRow = { name: string; sent: string; meeting: string; status: string; badge: string };
const B_LOG: BookingRow[] = [
  {
    name: "Prospect 1",
    sent: "Jun 2",
    meeting: "Tue, Jun 10 · 2:30 PM",
    status: "Confirmed",
    badge: "badge-ok",
  },
  {
    name: "Prospect 2",
    sent: "Jun 3",
    meeting: "Wed, Jun 11 · 10:00 AM",
    status: "Awaiting confirm",
    badge: "badge-warn",
  },
  {
    name: "Prospect 3",
    sent: "May 28",
    meeting: "Mon, Jun 9 · 3:00 PM",
    status: "Expired",
    badge: "badge-danger",
  },
  {
    name: "Prospect 4",
    sent: "Jun 1",
    meeting: "Thu, Jun 12 · 11:00 AM",
    status: "Confirmed",
    badge: "badge-ok",
  },
  {
    name: "Prospect 5",
    sent: "May 30",
    meeting: "Wed, Jun 4 · 1:00 PM",
    status: "Confirmed",
    badge: "badge-ok",
  },
];

type FeedbackRow = {
  name: string;
  rating: number;
  comment: string;
  meeting: string;
  feedback: string;
  badge: string;
  status: string;
  // true when feedback has been pending >5 days (real impl computes from dates);
  // gates the "Send follow-up nudge" action.
  overdue?: boolean;
};
const F_LOG: FeedbackRow[] = [
  {
    name: "Prospect 1",
    rating: 4,
    comment: "Placeholder comment about a useful, relevant call.",
    meeting: "Jun 4",
    feedback: "Jun 5",
    badge: "badge-ok",
    status: "Received",
  },
  {
    name: "Prospect 2",
    rating: 5,
    comment: "Placeholder comment, well prepared and on point.",
    meeting: "Jun 2",
    feedback: "Jun 3",
    badge: "badge-ok",
    status: "Received",
  },
  {
    name: "Prospect 4",
    rating: 3,
    comment: "Placeholder comment, interested but early.",
    meeting: "May 28",
    feedback: "May 29",
    badge: "badge-ok",
    status: "Received",
  },
  {
    name: "Prospect 5",
    rating: 0,
    comment: "No response yet",
    meeting: "May 30",
    feedback: "—",
    badge: "badge-warn",
    status: "Awaiting",
    overdue: true,
  },
];

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

export default function ClientStatus() {
  const { client } = useParams<{ client: string }>();
  const toast = useToast();
  const { tab, setTab } = useStatusTab();
  const [approvalBatch, setApprovalBatch] = useState("");

  // "Propose new time" inline editor for expired bookings (one open at a time)
  const [propose, setPropose] = useState<{ name: string; time: string; msg: string } | null>(null);
  const openPropose = (r: BookingRow) =>
    setPropose({
      name: r.name,
      time: "",
      msg:
        `Hi ${r.name}, your earlier booking link expired before we could lock a time. ` +
        `Here's a fresh suggested slot for your call with Northwind — confirm and it lands on both calendars.`,
    });

  // deep-link support: pick up the #hash on first load
  useEffect(() => {
    const h = location.hash.slice(1) as StatusTabKey;
    if (STATUS_TABS.some(([k]) => k === h)) setTab(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function activate(name: StatusTabKey) {
    setTab(name);
    history.replaceState(null, "", "#" + name);
  }

  // editable sendout template
  const [tmpl, setTmpl] = useState({
    subject: "Northwind: your prospect list is ready to approve",
    body:
      "Hi {{client_name}}, we've prepared a new batch of {{count}} prospects matched to your brief.\n\n" +
      "Nothing is contacted until you approve. Review the list, then approve it or flag anyone who isn't a fit.",
    cta: "Review the list",
  });
  const [editingTmpl, setEditingTmpl] = useState(false);
  const [draft, setDraft] = useState(tmpl);
  function startEditTmpl() {
    setDraft(tmpl);
    setEditingTmpl(true);
  }
  function saveTmpl() {
    setTmpl(draft);
    setEditingTmpl(false);
    toast("Template saved");
  }

  const approveHref = `/${client}/approve/sample-link`;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Client Action</h1>
          <div className="sub">
            What gets sent to clients and prospects, and what&apos;s come back · all records{" "}
            <Sample>sample</Sample>
          </div>
        </div>
        <Link
          href={`/${client}/${BACK[tab][0]}`}
          className="back-btn"
          style={{ marginBottom: 0, alignSelf: "flex-start", marginLeft: "auto" }}
        >
          {BACK[tab][1]}
        </Link>
      </div>

      <div className="tabs" role="tablist">
        {STATUS_TABS.map(([k, label]) => (
          <button
            key={k}
            className={clsx("tab", tab === k && "active")}
            onClick={() => activate(k)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* LIST APPROVAL */}
      <section className={clsx("es-section", tab === "approval" && "active")}>
        <div className="es-summary">
          <div className="esc">
            <div className="ecap">Total prospects</div>
            <div className="en">
              <Sample>n</Sample>
            </div>
          </div>
          <div className="esc">
            <div className="ecap">Approved</div>
            <div className="en">
              <Sample>n</Sample>
            </div>
          </div>
          <div className="esc">
            <div className="ecap">Message sent</div>
            <div className="en">
              <Sample>n</Sample>
            </div>
          </div>
          <div className="esc accent">
            <div className="ecap">Booked meeting</div>
            <div className="en">
              <Sample>n</Sample>
            </div>
          </div>
        </div>

        <div className="es-grid">
          <div className="tmpl">
            <div className="panel">
              <div className="panel-head">
                <div>
                  <h3>Sendout template</h3>
                  <div className="ph-sub">The approval request the client receives</div>
                </div>
                <span className="badge badge-ok">
                  <span className="bdot" />
                  Active
                </span>
              </div>
              <div className="panel-pad">
                <div className="tmpl-mail">
                  <div className="tmpl-mailhead">
                    <div className="trow">
                      <span className="tk">From</span>
                      <span className="tv">HoldSlot on behalf of Northwind</span>
                    </div>
                    <div className="trow">
                      <span className="tk">To</span>
                      <span className="tv">Client contact</span>
                    </div>
                    <div className="trow">
                      <span className="tk">Subject</span>
                      {editingTmpl ? (
                        <input
                          className="input"
                          style={{ flex: 1, padding: "6px 9px", fontSize: 12.5 }}
                          value={draft.subject}
                          onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
                        />
                      ) : (
                        <span className="tv subj">{tmpl.subject}</span>
                      )}
                    </div>
                  </div>
                  <div className="tmpl-body">
                    {editingTmpl ? (
                      <>
                        <textarea
                          className="textarea"
                          style={{ minHeight: 120, fontSize: 13 }}
                          value={draft.body}
                          onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                        />
                        <input
                          className="input"
                          style={{ marginTop: 10, padding: "8px 11px", fontSize: 13 }}
                          value={draft.cta}
                          onChange={(e) => setDraft({ ...draft, cta: e.target.value })}
                          placeholder="Button label"
                        />
                        <div className="tmpl-meta" style={{ marginTop: 8 }}>
                          Use {"{{client_name}}"} and {"{{count}}"} as placeholders.
                        </div>
                      </>
                    ) : (
                      <>
                        {tmpl.body.split("\n\n").map((para, i) => (
                          <p key={i}>{highlightTokens(para)}</p>
                        ))}
                        <a className="tmpl-cta">{tmpl.cta}</a>
                      </>
                    )}
                  </div>
                  <div className="tmpl-foot">
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: "var(--cerulean)",
                        display: "inline-block",
                      }}
                    />
                    Secure link, expires after a set window
                  </div>
                </div>
                <div className="tmpl-actions">
                  <button
                    className="btn btn-sm"
                    style={{ width: "100%", background: "var(--cerulean-deep)", color: "#fff" }}
                    onClick={() => toast("Approval request sent to client")}
                  >
                    Send to client
                  </button>
                </div>
                <div className="tmpl-actions" style={{ marginTop: 9 }}>
                  {editingTmpl ? (
                    <>
                      <button
                        className="btn btn-accent btn-sm"
                        style={{ flex: 1 }}
                        onClick={saveTmpl}
                      >
                        Save template
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        style={{ flex: 1 }}
                        onClick={() => setEditingTmpl(false)}
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="btn btn-ghost btn-sm"
                        style={{ flex: 1 }}
                        onClick={startEditTmpl}
                      >
                        Edit template
                      </button>
                      <Link
                        href={approveHref}
                        target="_blank"
                        className="btn btn-ghost btn-sm"
                        style={{ flex: 1 }}
                      >
                        Preview live page
                      </Link>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div>
            <div className="panel">
              <div className="panel-head">
                <div>
                  <h3>Status log</h3>
                  <div className="ph-sub">Every approval request and how the client responded</div>
                </div>
                <div className="row" style={{ gap: 8 }}>
                  <select
                    className="log-filter"
                    value={approvalBatch}
                    onChange={(e) => setApprovalBatch(e.target.value)}
                  >
                    <option value="">All batches</option>
                    {A_LOG.map((r) => (
                      <option key={r.name}>{r.name}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div style={{ overflowX: "auto" }}>
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Batch</th>
                      <th>Sent</th>
                      <th>Prospects</th>
                      <th>Responded</th>
                      <th>Status</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {A_LOG.filter((r) => !approvalBatch || r.name === approvalBatch).map((r) => (
                      <tr key={r.name}>
                        <td>
                          <span className="nm">{r.name}</span> <Sample>sample</Sample>
                        </td>
                        <td className="muted">{r.sent}</td>
                        <td className="num">{r.prospects}</td>
                        <td className="muted">{r.responded}</td>
                        <td>
                          <span className={clsx("badge", r.badge)}>
                            <span className="bdot" />
                            {r.status}
                          </span>
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <Link
                            href={`/${client}/workspace?batch=${encodeURIComponent(r.name)}#batches`}
                            className="btn btn-ghost btn-2xs"
                          >
                            View batch
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* BOOKING LINKS */}
      <section className={clsx("es-section", tab === "booking" && "active")}>
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
                Each prospect&apos;s suggested meeting time, the status, and the invitation email
                under every row
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
                          <span className="tv subj">
                            {r.name}, your meeting time with Northwind
                          </span>
                        </div>
                      </div>
                      <div className="tmpl-body">
                        <p>
                          Hi {r.name}, thanks for your interest. We&apos;ve set aside a suggested
                          time for your call with Northwind: <strong>{r.meeting}</strong>. It lands
                          on both calendars once you confirm. Calls may be recorded so we can share
                          a short summary with the host.
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

      {/* FEEDBACK FORMS */}
      <section className={clsx("es-section", tab === "feedback" && "active")}>
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
    </>
  );
}
