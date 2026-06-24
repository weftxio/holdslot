"use client";
import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { useClient } from "@/lib/nav";
import clsx from "clsx";
import { useToast } from "@/components/Toast";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import type { Batch } from "@/lib/workspace/types";
import {
  BATCH_STATUS_CLS,
  TODAY_ISO,
  daysAgoLabel,
  fmtShortDate,
} from "@/lib/workspace/constants";
import {
  EXCLUSION_COUNT,
  EXCLUSIONS,
  SAMPLE_CONNECTIONS,
  SAMPLE_INDUSTRIES,
  SCORE_TIERS,
  STAFF_ROLES,
} from "@/lib/workspace/fixtures";

export default function BatchesPage() {
  const client = useClient();
  const toast = useToast();
  const { batches, setBatches } = useWorkspace();
  const pendingBatches = batches.filter((b) => b.status === "Pending").length;

  // expandable batch detail (sample prospect rows)
  const [openBatch, setOpenBatch] = useState<string | null>(null);
  const [exclOpen, setExclOpen] = useState(false);
  const toggleBatch = (name: string, id: string, open: boolean) => {
    setOpenBatch(open ? null : name);
    if (!open) {
      setTimeout(
        () => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }),
        60
      );
    }
  };

  // deep-link: ?batch=<name> opens the Approval Batches tab with that batch expanded
  useEffect(() => {
    const b = new URLSearchParams(location.search).get("batch");
    if (!b) return;
    // Only expand/scroll when the requested batch actually exists — a stale or
    // unknown ?batch= value just lands on the tab instead of expanding nothing.
    const idx = batches.findIndex((x) => x.name === b);
    if (idx < 0) return;
    setOpenBatch(b);
    setTimeout(
      () =>
        document
          .getElementById("sob-item-" + idx)
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      160
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // batch approval action: send the approval email, or nudge if it was already sent
  const sendApproval = (name: string) => {
    const alreadySent = !!batches.find((x) => x.name === name)?.sentAt;
    setBatches((s) =>
      s.map((b) => (b.name === name ? { ...b, sentAt: b.sentAt || TODAY_ISO } : b))
    );
    toast(alreadySent ? "Follow-up nudge sent to client" : "Approval email sent to client");
  };

  // Group a batch's prospects under their company — company is the primary row, its related
  // staff listed beneath. Distributes b.count people across companies of 2–3, sorted by company.
  const batchCompanies = (b: Batch) => {
    const groups: {
      company: string;
      domain: string;
      score: (typeof SCORE_TIERS)[number];
      industry: string;
      connectedTo: string;
      people: { name: string; role: string; status: string }[];
    }[] = [];
    let placed = 0;
    let ci = 0;
    while (placed < b.count) {
      const size = Math.min((ci % 2) + 2, b.count - placed); // 2, 3, 2, 3 …
      const people = Array.from({ length: size }, (_, k) => {
        const idx = placed + k;
        return {
          name: "Prospect " + (idx + 1),
          role: STAFF_ROLES[idx % STAFF_ROLES.length],
          status: idx < b.approved ? "Approved" : b.status === "Rejected" ? "Rejected" : "Pending",
        };
      });
      groups.push({
        company: "Sample Co " + (ci + 1),
        domain: "sampleco" + (ci + 1) + ".com",
        score: SCORE_TIERS[ci % SCORE_TIERS.length],
        industry: SAMPLE_INDUSTRIES[ci % SAMPLE_INDUSTRIES.length],
        connectedTo: SAMPLE_CONNECTIONS[ci % SAMPLE_CONNECTIONS.length],
        people,
      });
      placed += size;
      ci++;
    }
    return groups;
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
                <b style={{ color: "var(--danger)" }}>{EXCLUSION_COUNT}</b> suppressed contacts ·
                never contacted · excluded from every batch &amp; campaign
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
                    {EXCLUSIONS.flatMap((g) =>
                      g.entries.map((e) => (
                        <tr key={g.label + e.domain}>
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
        {batches.map((b, i) => {
          const open = openBatch === b.name;
          return (
            <div className={clsx("sob-item", open && "open")} key={b.name} id={"sob-item-" + i}>
              <div
                className="sob-card"
                role="button"
                tabIndex={0}
                aria-expanded={open}
                onClick={() => toggleBatch(b.name, "sob-item-" + i, open)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggleBatch(b.name, "sob-item-" + i, open);
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
                    {!b.approvedAt && <span className="sob-date warn">Not yet approved</span>}
                  </div>
                </div>
                {b.status === "Pending" && (
                  <button
                    className="btn btn-accent btn-sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      sendApproval(b.name);
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
                          <th>Score</th>
                          <th>Industries</th>
                          <th>Connected to</th>
                          <th>Prospect</th>
                          <th>Approval</th>
                        </tr>
                      </thead>
                      <tbody>
                        {batchCompanies(b).map((co) => (
                          <Fragment key={co.company}>
                            {co.people.map((p, pj) => (
                              <tr key={co.company + p.name}>
                                {/* Company-level cells span the company's staff rows (first row only) */}
                                {pj === 0 && (
                                  <>
                                    <td className="vtop" rowSpan={co.people.length}>
                                      <span className="nm">{co.company}</span>
                                      <div className="sub">{co.domain}</div>
                                    </td>
                                    <td className="vtop" rowSpan={co.people.length}>
                                      <span className={clsx("badge", co.score.cls)}>
                                        <span className="bdot" />
                                        {co.score.grade} · {co.score.heat}
                                      </span>
                                    </td>
                                    <td className="vtop" rowSpan={co.people.length}>
                                      <span className="icp-chip">{co.industry}</span>
                                    </td>
                                    <td className="vtop muted" rowSpan={co.people.length}>
                                      {co.connectedTo}
                                    </td>
                                  </>
                                )}
                                <td>
                                  <span className="nm">{p.name}</span>
                                  <div className="sub">{p.role}</div>
                                </td>
                                <td>
                                  <span
                                    className={clsx(
                                      "badge",
                                      BATCH_STATUS_CLS[p.status] || "badge-neutral"
                                    )}
                                  >
                                    <span className="bdot" />
                                    {p.status}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </Fragment>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="sob-more">
                    {b.count} prospects · {b.approved} approved · {b.count - b.approved} pending
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
