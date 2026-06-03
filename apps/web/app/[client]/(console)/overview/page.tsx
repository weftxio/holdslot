"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Calendar, dateFnsLocalizer } from "react-big-calendar";
import { format, parse, startOfWeek, getDay } from "date-fns";
import { enUS } from "date-fns/locale";
import { Sample } from "@/components/Sample";
import "react-big-calendar/lib/css/react-big-calendar.css";
import "./overview.css";

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek,
  getDay,
  locales: { "en-US": enUS },
});

// Fixed reference month for the mock (deterministic — avoids SSR hydration drift)
const CAL_NOW = new Date(2026, 5, 3);
const CAL_MONTH = new Date(2026, 5, 1);

const MEETINGS = [
  {
    title: "Acme Robotics · Qualified",
    start: new Date(2026, 5, 4, 10, 0),
    end: new Date(2026, 5, 4, 10, 45),
  },
  {
    title: "Globex · Intro call",
    start: new Date(2026, 5, 9, 14, 30),
    end: new Date(2026, 5, 9, 15, 0),
  },
  {
    title: "Northwind · Demo",
    start: new Date(2026, 5, 12, 11, 0),
    end: new Date(2026, 5, 12, 11, 45),
  },
  {
    title: "Initech · Discovery",
    start: new Date(2026, 5, 17, 9, 30),
    end: new Date(2026, 5, 17, 10, 15),
  },
  {
    title: "Soylent · Follow-up",
    start: new Date(2026, 5, 23, 16, 0),
    end: new Date(2026, 5, 23, 16, 30),
  },
  {
    title: "Umbrella · Qualified",
    start: new Date(2026, 5, 26, 13, 0),
    end: new Date(2026, 5, 26, 13, 45),
  },
];

const FUNNEL: { label: string; color: string; w: number; n: number }[] = [
  { label: "Sourced", color: "#C9D7E8", w: 100, n: 1000 },
  { label: "Approved", color: "#AEC4DD", w: 82, n: 820 },
  { label: "Contacted", color: "var(--cerulean)", w: 78, n: 780 },
  { label: "Replied", color: "#7C9CC0", w: 44, n: 440 },
  { label: "Positive", color: "var(--cerulean-deep)", w: 26, n: 260 },
  { label: "Meeting booked", color: "var(--ink)", w: 15, n: 150 },
];

export default function Overview() {
  const { client } = useParams<{ client: string }>();
  const [calDate, setCalDate] = useState<Date>(CAL_MONTH);

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
                      <div className="fn2-bar" data-w={f.w} style={{ background: f.color }}>
                        <span className="fn2-pct">{f.w}%</span>
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
            <div className="cal-wrap">
              <Calendar
                localizer={localizer}
                events={MEETINGS}
                date={calDate}
                onNavigate={(d) => setCalDate(d)}
                getNow={() => CAL_NOW}
                defaultView="month"
                views={["month"]}
                popup
                style={{ height: 580 }}
              />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
