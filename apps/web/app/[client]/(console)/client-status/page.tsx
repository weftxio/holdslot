"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import { STATUS_TABS, useStatusTab, type StatusTabKey } from "@/components/console/StatusTab";
import "./client-status.css";

const BACK: Record<StatusTabKey, [string, string]> = {
  approval: ["workspace#batches", "Back to Sendout Batch"],
  booking: ["workspace#campaign", "Back to Campaign"],
  feedback: ["workspace#summaries", "Back to Meeting summaries"],
};

const A_LOG: [string, string, string, string, string, string][] = [
  ["Batch 3", "2 days ago", "48", "Not yet", "Pending", "badge-warn"],
  ["Batch 2", "placeholder", "52", "placeholder date", "Approved", "badge-ok"],
  ["Batch 1", "placeholder", "40", "placeholder date", "Approved", "badge-ok"],
  ["Batch 1 (rev)", "placeholder", "6", "placeholder date", "Changes requested", "badge-danger"],
];
const B_LOG: [string, string, string, string, string][] = [
  ["Prospect 1", "placeholder", "Placeholder day, time", "Booked", "badge-ok"],
  ["Prospect 2", "placeholder", "Awaiting choice", "Pending", "badge-warn"],
  ["Prospect 3", "placeholder", "None", "Expired", "badge-danger"],
  ["Prospect 4", "placeholder", "Placeholder day, time", "Booked", "badge-ok"],
  ["Prospect 5", "placeholder", "Placeholder day, time", "Booked", "badge-ok"],
];
const F_LOG: [string, number, string, string, string, string][] = [
  ["Prospect 1", 4, "Placeholder comment about a useful, relevant call.", "placeholder date", "badge-ok", "Received"],
  ["Prospect 2", 5, "Placeholder comment, well prepared and on point.", "placeholder date", "badge-ok", "Received"],
  ["Prospect 4", 3, "Placeholder comment, interested but early.", "placeholder date", "badge-ok", "Received"],
  ["Prospect 5", 0, "No response yet", "Not yet", "badge-warn", "Awaiting"],
];

function Stars({ n }: { n: number }) {
  return (
    <span className="stars-sm">
      {[1, 2, 3, 4, 5].map((i) =>
        i <= n ? <span key={i}>★</span> : <span key={i} className="off">★</span>
      )}
    </span>
  );
}

export default function ClientStatus() {
  const { client } = useParams<{ client: string }>();
  const toast = useToast();
  const { tab, setTab } = useStatusTab();
  const [approvalBatch, setApprovalBatch] = useState("");

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
  const renderTmplText = (text: string) =>
    text
      .split(/(\{\{[^}]+\}\})/g)
      .map((p, i) => (/^\{\{.*\}\}$/.test(p) ? <span key={i} className="mph">{p}</span> : p));

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
          <span className="bk">←</span>
          {BACK[tab][1]}
        </Link>
      </div>

      <div className="tabs" role="tablist">
        {STATUS_TABS.map(([k, label]) => (
          <button key={k} className={clsx("tab", tab === k && "active")} onClick={() => activate(k)}>
            {label}
          </button>
        ))}
      </div>

      {/* LIST APPROVAL */}
      <section className={clsx("es-section", tab === "approval" && "active")}>
        <div className="es-summary">
          <div className="esc"><div className="ecap">Total prospects</div><div className="en"><Sample>n</Sample></div></div>
          <div className="esc"><div className="ecap">Approved</div><div className="en"><Sample>n</Sample></div></div>
          <div className="esc"><div className="ecap">Message sent</div><div className="en"><Sample>n</Sample></div></div>
          <div className="esc accent"><div className="ecap">Booked meeting</div><div className="en"><Sample>n</Sample></div></div>
        </div>

        <div className="es-grid">
          <div className="tmpl">
            <div className="panel">
              <div className="panel-head">
                <div><h3>Sendout template</h3><div className="ph-sub">The approval request the client receives</div></div>
                <span className="badge badge-ok"><span className="bdot" />Active</span>
              </div>
              <div className="panel-pad">
                <div className="tmpl-mail">
                  <div className="tmpl-mailhead">
                    <div className="trow"><span className="tk">From</span><span className="tv">HoldSlot on behalf of Northwind</span></div>
                    <div className="trow"><span className="tk">To</span><span className="tv">Client contact</span></div>
                    <div className="trow">
                      <span className="tk">Subject</span>
                      {editingTmpl ? (
                        <input className="input" style={{ flex: 1, padding: "6px 9px", fontSize: 12.5 }} value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
                      ) : (
                        <span className="tv subj">{tmpl.subject}</span>
                      )}
                    </div>
                  </div>
                  <div className="tmpl-body">
                    {editingTmpl ? (
                      <>
                        <textarea className="textarea" style={{ minHeight: 120, fontSize: 13 }} value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
                        <input className="input" style={{ marginTop: 10, padding: "8px 11px", fontSize: 13 }} value={draft.cta} onChange={(e) => setDraft({ ...draft, cta: e.target.value })} placeholder="Button label" />
                        <div className="tmpl-meta" style={{ marginTop: 8 }}>Use {"{{client_name}}"} and {"{{count}}"} as placeholders.</div>
                      </>
                    ) : (
                      <>
                        {tmpl.body.split("\n\n").map((para, i) => (
                          <p key={i}>{renderTmplText(para)}</p>
                        ))}
                        <a className="tmpl-cta">{tmpl.cta}</a>
                      </>
                    )}
                  </div>
                  <div className="tmpl-foot"><span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--cerulean)", display: "inline-block" }} />Secure link, expires after a set window</div>
                </div>
                <div className="tmpl-actions">
                  <button
                    className="btn btn-sm"
                    style={{ width: "100%", background: "var(--cerulean-deep)", color: "#fff" }}
                    onClick={() => toast("Approval request sent to client")}
                  >
                    Send to client <span className="arrow">→</span>
                  </button>
                </div>
                <div className="tmpl-actions" style={{ marginTop: 9 }}>
                  {editingTmpl ? (
                    <>
                      <button className="btn btn-accent btn-sm" style={{ flex: 1 }} onClick={saveTmpl}>Save template</button>
                      <button className="btn btn-ghost btn-sm" style={{ flex: 1 }} onClick={() => setEditingTmpl(false)}>Cancel</button>
                    </>
                  ) : (
                    <>
                      <button className="btn btn-ghost btn-sm" style={{ flex: 1 }} onClick={startEditTmpl}>Edit template</button>
                      <Link href={approveHref} target="_blank" className="btn btn-ghost btn-sm" style={{ flex: 1 }}>Preview live page ↗</Link>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div>
            <div className="panel">
              <div className="panel-head">
                <div><h3>Status log</h3><div className="ph-sub">Every approval request and how the client responded</div></div>
                <div className="row" style={{ gap: 8 }}>
                  <select className="log-filter" value={approvalBatch} onChange={(e) => setApprovalBatch(e.target.value)}>
                    <option value="">All batches</option>
                    {A_LOG.map((r) => <option key={r[0]}>{r[0]}</option>)}
                  </select>
                  <Link href={approveHref} target="_blank" className="btn btn-ghost btn-sm" style={{ height: 36 }}>Open client page ↗</Link>
                </div>
              </div>
              <div style={{ overflowX: "auto" }}>
                <table className="tbl">
                  <thead><tr><th>Batch</th><th>Sent</th><th>Prospects</th><th>Responded</th><th>Status</th></tr></thead>
                  <tbody>
                    {A_LOG.filter((r) => !approvalBatch || r[0] === approvalBatch).map((r) => (
                      <tr key={r[0]}>
                        <td><span className="nm">{r[0]}</span> <Sample>sample</Sample></td>
                        <td className="muted">{r[1]}</td>
                        <td className="num">{r[2]}</td>
                        <td className="muted">{r[3]}</td>
                        <td><span className={clsx("badge", r[5])}><span className="bdot" />{r[4]}</span></td>
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
          <div className="esc"><div className="ecap">Links sent</div><div className="en"><Sample>n</Sample></div></div>
          <div className="esc accent"><div className="ecap">Meetings accepted</div><div className="en"><Sample>n</Sample></div></div>
          <div className="esc"><div className="ecap">Expired unused</div><div className="en">1</div></div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <div><h3>Status log</h3><div className="ph-sub">Links sent, the meeting each prospect accepted, and the invitation email under each row</div></div>
          </div>
          <div className="panel-pad">
            <div>
              {B_LOG.map((r, i) => (
                <div className="bk-card" key={i}>
                  <div className="bk-top">
                    <div className="bk-ico">P{i + 1}</div>
                    <div className="bk-main">
                      <div className="bn">{r[0]} <Sample>sample</Sample></div>
                      <div className="bm">Sample Co {i + 1} · link sent {r[1]} · slot: {r[2]}</div>
                    </div>
                    <span className={clsx("badge", r[4])}><span className="bdot" />{r[3]}</span>
                  </div>
                  <div className="bk-invite">
                    <div className="bk-invite-label">Invitation email sent</div>
                    <div className="tmpl-mail">
                      <div className="tmpl-mailhead">
                        <div className="trow"><span className="tk">Subject</span><span className="tv subj">{r[0]}, grab a time with Northwind</span></div>
                      </div>
                      <div className="tmpl-body">
                        <p>Hi {r[0]}, thanks for your interest. Pick a time that suits you and it lands on both calendars. Calls may be recorded so we can share a short summary with the host.</p>
                        <a className="tmpl-cta">Pick a time</a>
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
          <div className="esc"><div className="ecap">Forms sent</div><div className="en"><Sample>n</Sample></div></div>
          <div className="esc accent"><div className="ecap">Responses</div><div className="en"><Sample>n</Sample></div></div>
          <div className="esc"><div className="ecap">Average rating</div><div className="en"><Sample>n</Sample></div></div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <div><h3>Feedback history</h3><div className="ph-sub">Ratings and comments returned by prospects</div></div>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead><tr><th>Prospect</th><th>Meeting</th><th>Rating</th><th>Comment</th><th>Received</th></tr></thead>
              <tbody>
                {F_LOG.map((r, i) => (
                  <tr key={i}>
                    <td><div className="who-cell"><div className="av-sm">P{i + 1}</div><div><div className="nm">{r[0]} <Sample>sample</Sample></div><div className="sub">Sample Co {i + 1}</div></div></div></td>
                    <td className="muted">Meeting {i + 1}</td>
                    <td>{r[1] ? <Stars n={r[1]} /> : <span className="muted">Pending</span>}</td>
                    <td><div className="log-comment">{r[2]}</div></td>
                    <td><span className={clsx("badge", r[4])}><span className="bdot" />{r[5]}</span></td>
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
