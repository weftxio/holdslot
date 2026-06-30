"use client";
import { Fragment, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { useQuery } from "@tanstack/react-query";
import {
  getBatch,
  getBrief,
  sendApproval as apiSendApproval,
  type BatchDetailApi,
} from "@/lib/api";
import { useClient } from "@/lib/nav";
import { useToast } from "@/components/Toast";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import type { Batch } from "@/lib/workspace/types";
import {
  BATCH_STATUS_CLS,
  DECISION_VIEW,
  daysAgoLabel,
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

  // expandable batch detail — fetched live per batch id on first open
  const [openBatch, setOpenBatch] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, BatchDetailApi>>({});
  const [exclOpen, setExclOpen] = useState(false);
  const [lastEmail, setLastEmail] = useState("");

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

  // batch approval action: send the approval link, or a follow-up nudge if it was already sent
  const onSend = async (b: Batch) => {
    const email = window.prompt("Send the approval link to which client email?", lastEmail);
    if (!email || !email.trim()) return;
    try {
      await apiSendApproval(client, b.id, email.trim());
      setLastEmail(email.trim());
      await reloadBatches();
      toast(b.sentAt ? "Follow-up nudge sent to client" : "Approval email sent to client");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Send failed", "warn");
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
                {b.status === "Pending" && (
                  <button
                    className="btn btn-accent btn-sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      void onSend(b);
                    }}
                  >
                    {b.sentAt ? "Follow-Up Approval" : "Send approval email"}
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
                              const dec = DECISION_VIEW[p.decision] || {
                                label: p.decision,
                                cls: "badge-neutral",
                              };
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
                  <div className="sob-more">
                    {b.count} prospects · {b.approved} approved
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
