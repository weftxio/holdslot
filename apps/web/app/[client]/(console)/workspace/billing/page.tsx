"use client";
import { useState } from "react";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import { PER_MEETING_USD } from "@/lib/workspace/constants";
import { LEDGER } from "@/lib/workspace/fixtures";

export default function BillingPage() {
  const toast = useToast();

  function exportLedgerCsv() {
    const headers = [
      "Date",
      "Meeting with",
      "Company",
      "Campaign",
      "Batch",
      "Outcome",
      "Feedback",
      "Status",
      "Amount (USD)",
    ];
    const rows = LEDGER.map((row, i) => [
      "Placeholder date",
      "Prospect " + (i + 1),
      "Sample Co " + (i + 1),
      "Campaign 1",
      "Batch 3",
      row.outcome,
      row.feedback,
      row.billing,
      row.billing === "Billed" ? String(PER_MEETING_USD) : "",
    ]);
    const csv = [headers, ...rows]
      .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "billing-ledger.csv";
    a.click();
    URL.revokeObjectURL(url);
    toast("CSV exported");
  }

  return (
    <section className="tabpane active">
      <div className="ledger-sum">
        <div className="ls">
          <div className="lcap">Meetings billed</div>
          <div className="ln">
            <Sample>n</Sample>
          </div>
        </div>
        <div className="ls">
          <div className="lcap">Current cycle due</div>
          <div className="ln">
            $<Sample>amt</Sample>
          </div>
        </div>
        <div className="ls accent">
          <div className="lcap">Per qualified meeting</div>
          <div className="ln">${PER_MEETING_USD}</div>
        </div>
      </div>
      <div className="panel">
        <div className="panel-head">
          <div>
            <h3>Billing Ledger</h3>
            <div className="ph-sub">Only completed, qualified meetings are billable</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={exportLedgerCsv}>
            Export CSV
          </button>
        </div>
        <div className="tbl-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Date</th>
                <th>Meeting with</th>
                <th>Campaign / Batch</th>
                <th>Outcome</th>
                <th>Feedback</th>
                <th>Status</th>
                <th className="amt-cell">Amount</th>
              </tr>
            </thead>
            <tbody>
              {LEDGER.map((row, i) => (
                <tr key={i}>
                  <td className="muted">Placeholder date</td>
                  <td>
                    <div className="nm">Prospect {i + 1}</div>
                    <div className="sub">Sample Co {i + 1}</div>
                  </td>
                  <td>
                    <div className="sum-tags">
                      <span className="stag">Campaign 1</span>
                      <span className="stag">Batch 3</span>
                    </div>
                  </td>
                  <td>
                    <span className={clsx("badge", row.outcomeBadge)}>
                      <span className="bdot" />
                      {row.outcome}
                    </span>
                  </td>
                  <td className="muted">{row.feedback}</td>
                  <td>
                    <span className={clsx("badge", row.billingBadge)}>
                      <span className="bdot" />
                      {row.billing}
                    </span>
                  </td>
                  <td className="amt-cell">
                    {row.billing === "Billed" ? (
                      `$${PER_MEETING_USD}`
                    ) : (
                      <span className="muted">·</span>
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
