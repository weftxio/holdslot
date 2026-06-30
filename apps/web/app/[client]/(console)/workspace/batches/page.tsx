"use client";
import { Fragment, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { useQuery } from "@tanstack/react-query";
import {
  deleteBatch as apiDeleteBatch,
  getBatch,
  getBrief,
  sendApproval as apiSendApproval,
  type BatchDetailApi,
} from "@/lib/api";
import { useClient } from "@/lib/nav";
import { Modal } from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import type { Batch } from "@/lib/workspace/types";
import {
  attendeeEmailsFromBrief,
  BATCH_STATUS_CLS,
  daysAgoLabel,
  decisionView,
  exclusionsFromBrief,
  fmtShortDate,
} from "@/lib/workspace/constants";

export default function BatchesPage() {
  const client = useClient();
  const toast = useToast();
  const { batches, reloadBatches } = useWorkspace();
  const pendingBatches = batches.filter((b) => b.status === "Pending").length;

  // Do-not-contact list is read live from this client's Brief (§4 Exclusions & Guardrails), not
  // mock data. Shares the ["brief", client] cache with the Business Brief tab, so it's instant
  // after that tab has loaded and reflects whatever exclusions the client most recently saved.
  const { data: briefRes } = useQuery({ queryKey: ["brief", client], queryFn: () => getBrief(client) });
  const { groups: exclusionGroups, count: exclusionCount } = exclusionsFromBrief(briefRes?.data);
  // Recipients for the approval link: the Meeting attendee emails saved on this client's Brief (§5).
  // Shares the ["brief", client] cache above, so the dropdown is populated the moment the brief loads.
  const attendeeEmails = attendeeEmailsFromBrief(briefRes?.data);

  // expandable batch detail — fetched live per batch id on first open
  const [openBatch, setOpenBatch] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, BatchDetailApi>>({});
  const [exclOpen, setExclOpen] = useState(false);
  const [lastEmail, setLastEmail] = useState("");
  // batch the user is sending the approval link for (drives the recipient-picker modal); `sendEmail`
  // is the chosen attendee address and `sending` gates the modal's Send button.
  const [sendFor, setSendFor] = useState<Batch | null>(null);
  const [sendEmail, setSendEmail] = useState("");
  const [sending, setSending] = useState(false);
  // batch pending a confirmed delete (drives the confirm modal); `deleting` gates the modal button.
  const [pendingDelete, setPendingDelete] = useState<Batch | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Refetch on every open (no stale cache): a batch's decisions can change after the client responds
  // via the link, so the prior detail is shown only until the fresh fetch lands.
  const loadDetail = useCallback(
    async (id: string) => {
      try {
        const d = await getBatch(client, id);
        setDetails((s) => ({ ...s, [id]: d }));
      } catch {
        /* leave unloaded — the row just shows no detail */
      }
    },
    [client]
  );

  const toggleBatch = (b: Batch, domId: string, open: boolean) => {
    setOpenBatch(open ? null : b.id);
    if (!open) {
      void loadDetail(b.id);
      setTimeout(
        () => document.getElementById(domId)?.scrollIntoView({ behavior: "smooth", block: "start" }),
        60
      );
    }
  };

  // deep-link: ?batch=<id> opens this tab with that batch expanded (and its detail loaded). Keyed by
  // id, not name — batch names aren't unique, so a name match could open the wrong batch.
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("batch");
    if (!id) return;
    const idx = batches.findIndex((x) => x.id === id);
    if (idx < 0) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time ?batch= deep-link that also scrolls
    setOpenBatch(id);
    void loadDetail(id);
    setTimeout(
      () =>
        document
          .getElementById("sob-item-" + idx)
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      160
    );
    // run once after batches first load; loadDetail is stable enough for this one-shot deep-link
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batches.length]);

  // Open the recipient picker for this batch. Pre-select the last address used if it's still one of
  // the Brief's attendee emails, otherwise the first attendee (empty when the Brief has none).
  const openSend = (b: Batch) => {
    setSendEmail(attendeeEmails.includes(lastEmail) ? lastEmail : attendeeEmails[0] || "");
    setSendFor(b);
  };

  // batch approval action: send the approval link to the chosen attendee, or a follow-up nudge if it
  // was already sent. Recipient comes from the Brief dropdown (no free-text), so no prompt box.
  const onSend = async () => {
    const b = sendFor;
    const email = sendEmail.trim();
    if (!b || !email) return;
    setSending(true);
    try {
      await apiSendApproval(client, b.id, email);
      setLastEmail(email);
      await reloadBatches();
      toast(
        b.status === "Rejected"
          ? "Revised list re-sent to client"
          : b.sentAt
            ? "Follow-up nudge sent to client"
            : "Approval email sent to client"
      );
      setSendFor(null);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Send failed", "warn");
    } finally {
      setSending(false);
    }
  };

  // confirmed batch delete (server cascades its approval records + links). Close the row if it was
  // open, drop its cached detail, then refresh the list so the deleted batch disappears.
  const onDelete = async (b: Batch) => {
    setDeleting(true);
    try {
      await apiDeleteBatch(client, b.id);
      if (openBatch === b.id) setOpenBatch(null);
      setDetails(({ [b.id]: _drop, ...rest }) => rest);
      await reloadBatches();
      toast("Batch deleted");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Delete failed", "warn");
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  };

  return (
    <section className="tabpane active">
      <div className="between" style={{ marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
        <div className="section-label" style={{ marginBottom: 0 }}>
          Batches sent for client approval · status updates as the client responds
        </div>
        <div className="row" style={{ gap: 10, alignItems: "center" }}>
          <Link href={`/${client}/client-status/approval`} className="btn btn-ghost btn-2xs">
            Edit approval email
          </Link>
          <span className="badge badge-warn">
            <span className="bdot" />
            {pendingBatches} pending approval
          </span>
        </div>
      </div>
      <div className="sob">
        {/* Pinned do-not-contact batch — always on top, never contacted, excluded everywhere */}
        <div className={clsx("sob-item sob-exclude", exclOpen && "open")}>
          <div
            className="sob-card"
            role="button"
            tabIndex={0}
            aria-expanded={exclOpen}
            onClick={() => setExclOpen((o) => !o)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setExclOpen((o) => !o);
              }
            }}
          >
            <div className="sob-ico">⊘</div>
            <div className="sob-main">
              <div className="sob-name">Do-not-contact list</div>
              <div className="sob-meta">
                {exclusionCount > 0 ? (
                  <>
                    <b style={{ color: "var(--danger)" }}>{exclusionCount}</b> suppressed contacts ·
                    never contacted · excluded from every batch &amp; campaign
                  </>
                ) : (
                  <>No exclusions in your Brief yet · add them in Business Brief → Exclusions</>
                )}
              </div>
            </div>
            <span className="badge badge-danger">
              <span className="bdot" />
              Excluded
            </span>
            <span className="sob-chev" aria-hidden>
              ⌄
            </span>
          </div>
          {exclOpen && (
            <div className="sob-detail">
              <div className="sob-scroll">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Company domain</th>
                      <th>Company name</th>
                      <th>Website</th>
                      <th>Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {exclusionCount === 0 && (
                      <tr>
                        <td colSpan={4} className="muted">
                          No companies on your do-not-contact list yet · add them in your Business
                          Brief under Exclusions &amp; Guardrails.
                        </td>
                      </tr>
                    )}
                    {exclusionGroups.flatMap((g) =>
                      g.entries.map((e) => (
                        <tr key={g.tag + e.domain}>
                          <td>
                            <span className="nm">{e.domain}</span>
                          </td>
                          <td className="muted">{e.name}</td>
                          <td className="muted">{e.website}</td>
                          <td>
                            <span className={clsx("badge", g.cls)}>
                              <span className="bdot" />
                              {g.tag}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              <div className="sob-more">
                Sourced from your Brief exclusions · no prospect in any sendout batch overlaps
                this list.
              </div>
            </div>
          )}
        </div>
        {batches.length === 0 && (
          <div className="ph" style={{ padding: "26px 4px" }}>
            No batches yet · create one from the enriched prospects on the Prospect List tab.
          </div>
        )}
        {batches.map((b, i) => {
          const open = openBatch === b.id;
          const detail = details[b.id];
          return (
            <div className={clsx("sob-item", open && "open")} key={b.id} id={"sob-item-" + i}>
              <div
                className="sob-card"
                role="button"
                tabIndex={0}
                aria-expanded={open}
                onClick={() => toggleBatch(b, "sob-item-" + i, open)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggleBatch(b, "sob-item-" + i, open);
                  }
                }}
              >
                <div className="sob-ico">B{i + 1}</div>
                <div className="sob-main">
                  <div className="sob-name">{b.name}</div>
                  <div className="sob-meta">
                    <b style={{ color: "var(--ink)" }}>{b.approved}</b> approved ·{" "}
                    <b style={{ color: "var(--ink)" }}>{b.count}</b> total prospects · sourced
                    from {b.icp}
                  </div>
                  <div className="sob-dates">
                    {(
                      [
                        ["Created", b.createdAt],
                        ["Approved", b.approvedAt],
                        ["Sent", b.sentAt],
                      ] as [string, string | undefined][]
                    )
                      .filter((e): e is [string, string] => Boolean(e[1]))
                      .map(([label, d]) => (
                        <span className="sob-date" key={label}>
                          {label} {fmtShortDate(d)} · <b>{daysAgoLabel(d)}</b>
                        </span>
                      ))}
                    {b.status === "Pending" && (
                      <span className="sob-date warn">Not yet approved</span>
                    )}
                  </div>
                </div>
                {(b.status === "Pending" || b.status === "Rejected") && (
                  <button
                    className="btn btn-accent btn-sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      openSend(b);
                    }}
                  >
                    {b.status === "Rejected"
                      ? "Re-send for approval"
                      : b.sentAt
                        ? "Follow-Up Approval"
                        : "Send approval email"}
                  </button>
                )}
                <span className={clsx("badge", BATCH_STATUS_CLS[b.status] || "badge-neutral")}>
                  <span className="bdot" />
                  {b.status}
                </span>
                <span className="sob-chev" aria-hidden>
                  ⌄
                </span>
              </div>
              {open && (
                <div className="sob-detail">
                  <div className="sob-scroll">
                    <table className="tbl">
                      <thead>
                        <tr>
                          <th>Company</th>
                          <th>Industry</th>
                          <th>Prospect</th>
                          <th>Approval</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(detail?.companies ?? []).map((co, ci) => (
                          <Fragment key={co.domain + ci}>
                            {co.prospects.map((p, pj) => {
                              const dec = decisionView(p.decision, b.status);
                              return (
                                <tr key={p.approval_id}>
                                  {pj === 0 && (
                                    <>
                                      <td className="vtop" rowSpan={co.prospects.length}>
                                        <span className="nm">{co.company || co.domain || "—"}</span>
                                        {co.domain && <div className="sub">{co.domain}</div>}
                                      </td>
                                      <td className="vtop" rowSpan={co.prospects.length}>
                                        {co.industry ? (
                                          <span className="icp-chip">{co.industry}</span>
                                        ) : (
                                          <span className="muted">—</span>
                                        )}
                                      </td>
                                    </>
                                  )}
                                  <td>
                                    <span className="nm">{p.full_name || "—"}</span>
                                    <div className="sub">{p.title}</div>
                                  </td>
                                  <td>
                                    <span className={clsx("badge", dec.cls)}>
                                      <span className="bdot" />
                                      {dec.label}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </Fragment>
                        ))}
                        {detail && detail.companies.length === 0 && (
                          <tr>
                            <td colSpan={4} className="muted">
                              No prospects in this batch.
                            </td>
                          </tr>
                        )}
                        {!detail && (
                          <tr>
                            <td colSpan={4} className="muted">
                              Loading prospects…
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                  <div className="sob-more between" style={{ alignItems: "center", gap: 12 }}>
                    <span>
                      {b.count} prospects · {b.approved} approved
                    </span>
                    <button className="btn btn-danger btn-sm" onClick={() => setPendingDelete(b)}>
                      Delete batch
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <Modal
        open={sendFor !== null}
        onClose={() => !sending && setSendFor(null)}
        title={
          sendFor?.status === "Rejected"
            ? "Re-send the revised list"
            : sendFor?.sentAt
              ? "Send a follow-up nudge"
              : "Send approval email"
        }
        subtitle={sendFor ? `Batch "${sendFor.name}" · ${sendFor.count} prospects` : undefined}
        footer={
          <>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setSendFor(null)}
              disabled={sending}
            >
              Cancel
            </button>
            <button
              className="btn btn-accent btn-sm"
              onClick={() => void onSend()}
              disabled={sending || !sendEmail}
            >
              {sending
                ? "Sending…"
                : sendFor?.status === "Rejected"
                  ? "Re-send for approval"
                  : sendFor?.sentAt
                    ? "Send follow-up"
                    : "Send approval email"}
            </button>
          </>
        }
      >
        {sendFor?.status === "Rejected" && (
          <p style={{ margin: "0 0 14px", lineHeight: 1.5 }}>
            This batch was rejected. Re-sending <b>reopens</b> it and emails a fresh approval link so
            the client can review the revised list.
          </p>
        )}
        {sendFor &&
          (attendeeEmails.length > 0 ? (
            <div className="field" style={{ margin: 0 }}>
              <label>Send the approval link to</label>
              <select
                className="select"
                value={sendEmail}
                onChange={(e) => setSendEmail(e.target.value)}
              >
                {attendeeEmails.map((em) => (
                  <option key={em} value={em}>
                    {em}
                  </option>
                ))}
              </select>
              <div className="muted" style={{ marginTop: 8 }}>
                From your Brief · Meeting attendee emails.
              </div>
            </div>
          ) : (
            <p style={{ margin: 0, lineHeight: 1.5 }}>
              No meeting attendee emails on your Brief yet. Add them in{" "}
              <Link href={`/${client}/workspace/brief`}>Business Brief · Meeting attendee emails</Link>
              , then send.
            </p>
          ))}
      </Modal>

      <Modal
        open={pendingDelete !== null}
        onClose={() => !deleting && setPendingDelete(null)}
        title={pendingDelete ? `Delete batch "${pendingDelete.name}"?` : ""}
        footer={
          <>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setPendingDelete(null)}
              disabled={deleting}
            >
              Cancel
            </button>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => pendingDelete && void onDelete(pendingDelete)}
              disabled={deleting}
            >
              {deleting ? "Deleting…" : "Delete batch"}
            </button>
          </>
        }
      >
        {pendingDelete && (
          <p style={{ margin: 0, lineHeight: 1.5 }}>
            This permanently deletes <b>{pendingDelete.name}</b>, its{" "}
            <b>{pendingDelete.count}</b> approval record{pendingDelete.count === 1 ? "" : "s"}, and
            any approval links. This can&apos;t be undone.
            {pendingDelete.status !== "Pending" && (
              <>
                {" "}
                Because the batch is already {pendingDelete.status.toLowerCase()}, its recorded
                approve/remove decisions are erased too.
              </>
            )}
          </p>
        )}
      </Modal>
    </section>
  );
}
