"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useClient } from "@/lib/nav";
import { getPerformanceSummary, type PerformanceSummaryApi } from "@/lib/api";
import "./performance-summary.css";

// Lazy-load the calendar (react-big-calendar ~70kB) so it streams in after the
// dashboard is interactive instead of blocking /performance-summary hydration.
const MeetingCalendar = dynamic(() => import("./MeetingCalendar"), {
  ssr: false,
  loading: () => <div className="cal-wrap" style={{ height: 580 }} />,
});

// Bar width is derived from n (count ÷ top-of-funnel count) so the chart can't drift out of sync.
// Colors are keyed by the stage label the API returns (Sourced → Meeting booked), so the live
// funnel keeps the design's cost-gradient palette. Meeting booked reads 0 until Phase F.
const FUNNEL_COLOR: Record<string, string> = {
  Sourced: "#C9D7E8",
  Approved: "#AEC4DD",
  Contacted: "var(--cerulean)",
  Replied: "#7C9CC0",
  Positive: "var(--cerulean-deep)",
  "Meeting booked": "var(--ink)",
};

export default function PerformanceSummary() {
  const client = useClient();
  const [summary, setSummary] = useState<PerformanceSummaryApi | null>(null);

  useEffect(() => {
    let alive = true;
    getPerformanceSummary(client)
      .then((s) => alive && setSummary(s))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [client]);

  const funnel = summary?.funnel ?? [];
  const funnelTop = funnel[0]?.n || 0;

  // Animate the bars in once the funnel data is present (mirrors the design's reveal). Keyed on
  // `summary` (set once) rather than the per-render `funnel` array.
  useEffect(() => {
    if (!summary?.funnel.length) return;
    const t = setTimeout(() => {
      document.querySelectorAll<HTMLElement>("#funnel .fn2-bar").forEach((bar) => {
        bar.style.width = (bar.getAttribute("data-w") || "0") + "%";
      });
    }, 200);
    return () => clearTimeout(t);
  }, [summary]);

  const status = (anchor: string) => `/${client}/client-status/${anchor}`;
  const approvalsPending = summary?.approvals_pending ?? 0;
  const awaitingReview = summary?.replies_awaiting_review ?? 0;
  const positiveReplies = summary?.new_positive_replies ?? 0;
  const qualified = summary?.qualified_last_30d ?? 0;
  const delta = summary?.qualified_delta ?? 0;
  const showUp = summary?.show_up_rate;
  const awaitingWeek = summary?.awaiting_this_week ?? 0;
  const openLinks = summary?.open_booking_links ?? 0;
  const heldNoFeedback = summary?.held_without_feedback ?? 0;

  return (
    <>
      <div className="headline">
        <div className="hl-main">
          <div className="big">{qualified}</div>
          <div className="cap">Qualified meetings booked</div>
          <div className="delta">
            <span className={delta >= 0 ? "up" : "down"}>
              {delta >= 0 ? "▲" : "▼"} {Math.abs(delta)}
            </span>{" "}
            vs. prior 30 days
          </div>
        </div>
        <div className="hl-cell">
          <div className="n">{showUp == null ? "—" : Math.round(showUp * 100)}%</div>
          <div className="l">Show-up rate on booked meetings</div>
        </div>
        <div className="hl-cell">
          <div className="n">{awaitingWeek}</div>
          <div className="l">Awaiting on the calendar this week</div>
        </div>
      </div>

      <div className="ov-top">
        <div className="panel">
          <div className="panel-head">
            <div>
              <h3>Needs attention</h3>
              <div className="ph-sub">
                Client action status that&apos;s waiting on a client or prospect
              </div>
            </div>
            <span className="na-head-count">3 open</span>
          </div>
          <div className="na-item">
            <div className="na-ico warn">①</div>
            <div className="na-body">
              <div className="t">Client list approval pending</div>
              <div className="d">
                <b>
                  {approvalsPending} {approvalsPending === 1 ? "batch" : "batches"}
                </b>{" "}
                sent to the client, {approvalsPending > 0 ? "not yet approved" : "all decided"}.
                Nothing ships until they sign off.
              </div>
            </div>
            <div className="na-act">
              <Link href={status("approval")} className="btn btn-ghost btn-sm">
                View status
              </Link>
            </div>
          </div>
          <div className="na-item">
            <div className="na-ico info">②</div>
            <div className="na-body">
              <div className="t">Outstanding booking links</div>
              <div className="d">
                <b>
                  {openLinks} booking {openLinks === 1 ? "link" : "links"}
                </b>{" "}
                sent and not yet booked. Re-send a fresh link from the reply thread when one lapses.
              </div>
            </div>
            <div className="na-act">
              <Link href={status("booking")} className="btn btn-ghost btn-sm">
                View status
              </Link>
            </div>
          </div>
          <div className="na-item">
            <div className="na-ico ok">③</div>
            <div className="na-body">
              <div className="t">Post-meeting feedback forms</div>
              <div className="d">
                <b>
                  {heldNoFeedback} held {heldNoFeedback === 1 ? "meeting" : "meetings"}
                </b>{" "}
                without feedback yet. Send the feedback form from the Feedback tab.
              </div>
            </div>
            <div className="na-act">
              <Link href={status("feedback")} className="btn btn-ghost btn-sm">
                View status
              </Link>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h3>Weekly Stats</h3>
          </div>
          <div className="panel-pad" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="between">
              <span className="muted" style={{ fontSize: 13.5 }}>
                Meetings held
              </span>
              <span className="tnum" style={{ fontWeight: 700 }}>
                {summary?.meetings_held_week ?? 0}
              </span>
            </div>
            <hr className="hr" />
            <div className="between">
              <span className="muted" style={{ fontSize: 13.5 }}>
                New positive replies
              </span>
              <span className="tnum" style={{ fontWeight: 700 }}>
                {positiveReplies}
              </span>
            </div>
            <hr className="hr" />
            <div className="between">
              <span className="muted" style={{ fontSize: 13.5 }}>
                Replies awaiting review
              </span>
              <Link
                href={`/${client}/workspace/replies`}
                style={{ color: "var(--danger)", fontWeight: 700, fontSize: 13.5 }}
              >
                {awaitingReview}
              </Link>
            </div>
            <hr className="hr" />
            <div className="between">
              <span className="muted" style={{ fontSize: 13.5 }}>
                Billable this cycle
              </span>
              <span className="tnum" style={{ fontWeight: 700 }}>
                ${(summary?.billable_this_cycle ?? 0).toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="ov-top ov-cal-row">
        <div className="panel">
          <div className="panel-head">
            <div>
              <h3>Leads Funnel</h3>
              <div className="ph-sub">Where every prospect in the campaign sits right now</div>
            </div>
          </div>
          <div className="panel-pad">
            <div className="funnel2" id="funnel">
              {funnel.map((f, i) => {
                const w = funnelTop ? Math.round((f.n / funnelTop) * 100) : 0;
                const prev = i === 0 ? f.n : funnel[i - 1].n;
                const conv = prev ? Math.round((f.n / prev) * 100) : 0;
                const color = FUNNEL_COLOR[f.label] || "var(--cerulean)";
                return (
                  <div className="fn2-stage" key={f.label}>
                    <div className="fn2-head">
                      <span className="fn2-label">
                        <span className="fn2-dot" style={{ background: color }} />
                        {f.label}
                      </span>
                      <span className="fn2-meta">
                        <span className="fn2-count">
                          {f.n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")}
                        </span>
                        {i > 0 && <span className="fn2-drop">{conv}% of prev</span>}
                      </span>
                    </div>
                    <div className="fn2-track">
                      <div className="fn2-bar" data-w={w} style={{ background: color }}>
                        <span className="fn2-pct">{w}%</span>
                      </div>
                    </div>
                  </div>
                );
              })}
              {!funnel.length && <div className="muted">Loading funnel…</div>}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <div>
              <h3>Meeting Calendar</h3>
              <div className="ph-sub">Booked meetings · shown in your local timezone</div>
            </div>
          </div>
          <div className="panel-pad">
            <MeetingCalendar items={summary?.calendar ?? []} />
          </div>
        </div>
      </div>
    </>
  );
}
