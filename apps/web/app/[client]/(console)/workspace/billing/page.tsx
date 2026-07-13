"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { useToast } from "@/components/Toast";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { PER_MEETING_USD } from "@/lib/workspace/constants";
import {
  getBillingStatus,
  listMeetings,
  refreshMeetings,
  type BillingSubscriptionApi,
  type MeetingApi,
} from "@/lib/api";

const PLAN_LABEL: Record<string, string> = { free: "Free", launch: "Launch", growth: "Growth" };
const SUB_STATUS_BADGE: Record<string, string> = {
  active: "badge-ok",
  past_due: "badge-warn",
  canceled: "badge-danger",
  incomplete: "badge-warn",
};

const OUTCOME: Record<string, { label: string; badge: string }> = {
  qualified: { label: "Qualified", badge: "badge-ok" },
  short_call: { label: "Short call", badge: "badge-warn" },
  noshow: { label: "No-show", badge: "badge-danger" },
};
const BILLING_BADGE: Record<string, string> = {
  Billed: "badge-ok",
  Held: "badge-warn",
  "Not billable": "badge-neutral",
};

function fmt(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function BillingPage() {
  const client = useParams<{ client: string }>().client;
  const toast = useToast();
  const { reloadMeetings } = useWorkspace();
  const [rows, setRows] = useState<MeetingApi[] | null>(null);
  const [busy, setBusy] = useState(false);
  // GS6 — the Stripe subscription line; null until this tenant is on billing (every tenant today),
  // so nothing extra renders. getBillingStatus never throws (a 404 → null), keeping the page dormant-safe.
  const [sub, setSub] = useState<BillingSubscriptionApi | null>(null);

  const load = useCallback(() => {
    listMeetings(client, "past").then(setRows).catch(() => setRows([]));
    getBillingStatus(client).then((s) => setSub(s.subscription));
  }, [client]);
  useEffect(() => load(), [load]);

  async function refresh() {
    setBusy(true);
    try {
      await refreshMeetings(client);
      load();
      // The sweep can flip a meeting to Billed/qualified — invalidate the shared past-meetings
      // query so Meeting Recaps doesn't show stale outcome/won until a manual reload (M9).
      await reloadMeetings();
      toast("Ledger refreshed");
    } catch (e) {
      // M24 — a sweep failure was an unhandled rejection with zero feedback; surface it.
      toast(e instanceof Error ? e.message : "Couldn't refresh the ledger — try again", "warn");
    } finally {
      setBusy(false);
    }
  }

  const list = rows ?? [];
  const billed = list.filter((r) => r.billing_chip === "Billed");
  const cycleDue = billed.reduce((s, r) => s + (r.amount || 0), 0);

  function exportLedgerCsv() {
    const headers = [
      "Date", "Meeting with", "Company", "Campaign", "Batch", "Outcome", "Feedback", "Status",
      "Amount (USD)",
    ];
    const csvRows = list.map((r) => [
      fmt(r.scheduled_at),
      r.prospect_name,
      r.company_name,
      r.campaign_name,
      r.batch_name,
      OUTCOME[r.outcome || ""]?.label || r.outcome || "",
      r.feedback_state,
      r.billing_chip,
      r.billing_chip === "Billed" && r.amount != null ? String(r.amount) : "",
    ]);
    const csv = [headers, ...csvRows]
      .map((row) => row.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
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
          <div className="ln">{billed.length}</div>
        </div>
        <div className="ls">
          <div className="lcap">Current cycle due</div>
          <div className="ln">${cycleDue.toLocaleString()}</div>
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
            {sub && (
              <div className="ph-sub" style={{ marginTop: 6, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span>{PLAN_LABEL[sub.plan] || sub.plan} plan</span>
                <span className={clsx("badge", SUB_STATUS_BADGE[sub.status] || "badge-neutral")}>
                  <span className="bdot" />
                  {sub.status === "past_due" ? "Payment due" : sub.status === "active" ? "Active" : sub.status}
                </span>
                <span>
                  · {sub.current_month_usage}/{sub.enrichment_cap} enrichments this month
                </span>
              </div>
            )}
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={refresh} disabled={busy}>
              {busy ? "Refreshing…" : "Refresh"}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={exportLedgerCsv}>
              Export CSV
            </button>
          </div>
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
                    No completed meetings yet.
                  </td>
                </tr>
              )}
              {list.map((r) => {
                const oc = OUTCOME[r.outcome || ""] || { label: r.outcome || "—", badge: "badge-neutral" };
                return (
                  <tr key={r.id}>
                    <td className="muted">{fmt(r.scheduled_at)}</td>
                    <td>
                      <div className="nm">{r.prospect_name || "Prospect"}</div>
                      <div className="sub">{r.company_name}</div>
                    </td>
                    <td>
                      <div className="sum-tags">
                        {r.campaign_name && <span className="stag">{r.campaign_name}</span>}
                        {r.batch_name && <span className="stag">{r.batch_name}</span>}
                      </div>
                    </td>
                    <td>
                      <span className={clsx("badge", oc.badge)}>
                        <span className="bdot" />
                        {oc.label}
                      </span>
                    </td>
                    <td className="muted">{r.feedback_state === "Received" ? "Received" : "—"}</td>
                    <td>
                      <span className={clsx("badge", BILLING_BADGE[r.billing_chip] || "badge-neutral")}>
                        <span className="bdot" />
                        {r.billing_chip}
                      </span>
                    </td>
                    <td className="amt-cell">
                      {r.billing_chip === "Billed" && r.amount != null ? (
                        `$${r.amount.toLocaleString()}`
                      ) : (
                        <span className="muted">·</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
