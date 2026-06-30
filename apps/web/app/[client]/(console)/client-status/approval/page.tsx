"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import {
  getApprovalTemplate,
  listBatches,
  saveApprovalTemplate,
  type ApprovalTemplateApi,
  type BatchApi,
} from "@/lib/api";
import { useClient } from "@/lib/nav";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import { highlightTokens } from "@/lib/tmpl";
import { BATCH_STATUS_CLS, fmtShortDate, uiBatchStatus } from "@/lib/workspace/constants";

const DEFAULT_TMPL: ApprovalTemplateApi = {
  subject: "HoldSlot: your prospect list is ready to approve",
  body:
    "Hi there,\n\n" +
    "HoldSlot has prepared a new batch of {{prospects}} matched to your brief. " +
    "Take a look, then approve the list or remove anyone who isn't a fit.",
  cta: "Review the list",
};

const day = (iso: string | null) => (iso ? fmtShortDate(iso.slice(0, 10)) : null);

export default function ApprovalPage() {
  const client = useClient();
  const toast = useToast();
  const [approvalBatch, setApprovalBatch] = useState("");
  const [batches, setBatches] = useState<BatchApi[]>([]);

  // editable sendout template (seeded from the API; the default renders until it loads). Editing is
  // gated on `tmplReady` so a click before the fetch resolves can't seed the draft from the default
  // and save it over a custom template (also re-gated while a new client's template loads).
  const [tmpl, setTmpl] = useState<ApprovalTemplateApi>(DEFAULT_TMPL);
  const [tmplReady, setTmplReady] = useState(false);
  const [editingTmpl, setEditingTmpl] = useState(false);
  const [draft, setDraft] = useState(tmpl);

  useEffect(() => {
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- re-gate edit while the client's template loads
    setTmplReady(false);
    getApprovalTemplate(client)
      .then((t) => alive && setTmpl(t))
      .catch(() => undefined)
      .finally(() => alive && setTmplReady(true));
    listBatches(client)
      .then((b) => alive && setBatches(b))
      .catch(() => alive && setBatches([]));
    return () => {
      alive = false;
    };
  }, [client]);

  function startEditTmpl() {
    setDraft(tmpl);
    setEditingTmpl(true);
  }
  async function saveTmpl() {
    try {
      const saved = await saveApprovalTemplate(client, draft);
      setTmpl(saved);
      setEditingTmpl(false);
      toast("Template saved");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Save failed", "warn");
    }
  }

  // Derived summary chips — Total prospects + Approved are live (Phase D); Message sent (E) and
  // Booked meeting (F) stay placeholder until those phases land.
  const totalProspects = batches.reduce((n, b) => n + b.total, 0);
  const totalApproved = batches.reduce((n, b) => n + b.approved, 0);

  const log = batches.map((b) => {
    const status = uiBatchStatus(b.status);
    return {
      id: b.id,
      name: b.name,
      sent: b.sent_at ? day(b.sent_at)! : "Not sent",
      prospects: String(b.total),
      responded: b.decided_at ? day(b.decided_at)! : "Not yet",
      status,
      badge: BATCH_STATUS_CLS[status] || "badge-neutral",
    };
  });

  return (
    <section className="es-section active">
      <div className="es-summary">
        <div className="esc">
          <div className="ecap">Total prospects</div>
          <div className="en">{totalProspects}</div>
        </div>
        <div className="esc">
          <div className="ecap">Approved</div>
          <div className="en">{totalApproved}</div>
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
                        Use {"{{prospects}}"}, {"{{count}}"}, and {"{{client_name}}"} as
                        placeholders.
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
                <Link
                  href={`/${client}/workspace/batches`}
                  className="btn btn-sm"
                  style={{
                    width: "100%",
                    background: "var(--cerulean-deep)",
                    color: "#fff",
                    textAlign: "center",
                  }}
                >
                  Send a batch to client
                </Link>
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
                      disabled={!tmplReady}
                    >
                      Edit template
                    </button>
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
                  {log.map((r) => (
                    <option key={r.id}>{r.name}</option>
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
                  {log.length === 0 && (
                    <tr>
                      <td colSpan={6} className="muted">
                        No approval requests yet.
                      </td>
                    </tr>
                  )}
                  {log
                    .filter((r) => !approvalBatch || r.name === approvalBatch)
                    .map((r) => (
                      <tr key={r.id}>
                        <td>
                          <span className="nm">{r.name}</span>
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
                            href={`/${client}/workspace/batches?batch=${encodeURIComponent(r.id)}`}
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
