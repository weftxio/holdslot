"use client";
import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import { highlightTokens } from "@/lib/tmpl";
import { A_LOG } from "@/lib/fixtures/client-status";

export default function ApprovalPage() {
  const { client } = useParams<{ client: string }>();
  const toast = useToast();
  const [approvalBatch, setApprovalBatch] = useState("");

  // editable sendout template
  const [tmpl, setTmpl] = useState({
    subject: "HoldSlot: your prospect list is ready to approve",
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
    <section className="es-section active">
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
                    <span className="tv">HoldSlot</span>
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
  );
}
