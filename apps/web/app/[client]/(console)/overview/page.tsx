"use client";
import { useEffect } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { Sample } from "@/components/Sample";
import "./overview.css";

// Lazy-load the calendar (react-big-calendar ~70kB) so it streams in after the
// dashboard is interactive instead of blocking /overview hydration.
const MeetingCalendar = dynamic(() => import("./MeetingCalendar"), {
  ssr: false,
  loading: () => <div className="cal-wrap" style={{ height: 580 }} />,
});

// Bar width is derived from n (count ÷ top-of-funnel count), so the chart can't
// drift out of sync the way storing both a width and a count would.
const FUNNEL: { label: string; color: string; n: number }[] = [
  { label: "Sourced", color: "#C9D7E8", n: 1000 },
  { label: "Approved", color: "#AEC4DD", n: 820 },
  { label: "Contacted", color: "var(--cerulean)", n: 780 },
  { label: "Replied", color: "#7C9CC0", n: 440 },
  { label: "Positive", color: "var(--cerulean-deep)", n: 260 },
  { label: "Meeting booked", color: "var(--ink)", n: 150 },
];
const FUNNEL_TOP = FUNNEL[0].n;

export default function Overview() {
  const { client } = useParams<{ client: string }>();

  useEffect(() => {
    const t = setTimeout(() => {
      document.querySelectorAll<HTMLElement>("#funnel .fn2-bar").forEach((bar) => {
        bar.style.width = (bar.getAttribute("data-w") || "0") + "%";
      });
    }, 200);
    return () => clearTimeout(t);
  }, []);

  const status = (anchor: string) => `/${client}/client-status#${anchor}`;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Overview</h1>
        </div>
      </div>

      <div className="headline">
        <div className="hl-main">
          <div className="big">
            <span className="ph-inline ph">
              <span className="ph-tag">count</span>
            </span>
          </div>
          <div className="cap">Qualified meetings booked</div>
          <div className="delta">
            <span className="up">▲ sample</span> vs. prior 30 days
          </div>
        </div>
        <div className="hl-cell">
          <div className="n">
            <span className="ph-inline ph">
              <span className="ph-tag" style={{ fontSize: 8 }}>
                n
              </span>
            </span>
            %
          </div>
          <div className="l">Show-up rate on booked meetings</div>
        </div>
        <div className="hl-cell">
          <div className="n">
            <span className="ph-inline ph">
              <span className="ph-tag" style={{ fontSize: 8 }}>
                n
              </span>
            </span>
          </div>
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
                <b>Batch 3 · 48 prospects</b> sent to the client <b>2 days ago</b>, not yet
                approved. Nothing ships until they sign off.
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
                <b>4 interested prospects</b> sent a booking link. <b>1 expired unused</b>, 3 still
                open. One reminder is scheduled.
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
                <b>2 forms pending</b> from meetings held this week. Feedback gates billing &amp;
                the qualified-meeting count.
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
                <Sample>n</Sample>
              </span>
            </div>
            <hr className="hr" />
            <div className="between">
              <span className="muted" style={{ fontSize: 13.5 }}>
                New positive replies
              </span>
              <span className="tnum" style={{ fontWeight: 700 }}>
                <Sample>n</Sample>
              </span>
            </div>
            <hr className="hr" />
            <div className="between">
              <span className="muted" style={{ fontSize: 13.5 }}>
                Replies awaiting review
              </span>
              <Link
                href={`/${client}/workspace#replies`}
                style={{ color: "var(--danger)", fontWeight: 700, fontSize: 13.5 }}
              >
                3
              </Link>
            </div>
            <hr className="hr" />
            <div className="between">
              <span className="muted" style={{ fontSize: 13.5 }}>
                Billable this cycle
              </span>
              <span className="tnum" style={{ fontWeight: 700 }}>
                $<Sample>amt</Sample>
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
              {FUNNEL.map((f, i) => {
                const w = Math.round((f.n / FUNNEL_TOP) * 100);
                const prev = i === 0 ? f.n : FUNNEL[i - 1].n;
                const conv = Math.round((f.n / prev) * 100);
                return (
                  <div className="fn2-stage" key={f.label}>
                    <div className="fn2-head">
                      <span className="fn2-label">
                        <span className="fn2-dot" style={{ background: f.color }} />
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
                      <div className="fn2-bar" data-w={w} style={{ background: f.color }}>
                        <span className="fn2-pct">{w}%</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <div>
              <h3>Meeting Calendar</h3>
              <div className="ph-sub">
                Booked meetings this month · all dates <Sample>sample</Sample>
              </div>
            </div>
          </div>
          <div className="panel-pad">
            <MeetingCalendar />
          </div>
        </div>
      </div>
    </>
  );
}
