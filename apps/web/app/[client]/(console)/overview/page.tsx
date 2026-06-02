"use client";
import { useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Sample } from "@/components/Sample";
import "./overview.css";

const FUNNEL: { label: string; color: string; w: number }[] = [
  { label: "Sourced", color: "#C9D7E8", w: 100 },
  { label: "Approved", color: "#AEC4DD", w: 82 },
  { label: "Contacted", color: "var(--cerulean)", w: 78 },
  { label: "Replied", color: "#7C9CC0", w: 44 },
  { label: "Positive", color: "var(--cerulean-deep)", w: 26 },
  { label: "Meeting booked", color: "var(--ink)", w: 15 },
];

export default function Overview() {
  const { client } = useParams<{ client: string }>();

  useEffect(() => {
    const t = setTimeout(() => {
      document.querySelectorAll<HTMLElement>("#funnel .fn-row").forEach((r) => {
        const fill = r.querySelector<HTMLElement>(".fn-fill");
        if (fill) fill.style.width = (r.getAttribute("data-w") || "0") + "%";
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
          <div className="cap">Qualified meetings booked</div>
          <div className="big">
            <span className="ph-inline ph">
              <span className="ph-tag">count</span>
            </span>
          </div>
          <div className="delta">
            <span className="up">▲ sample</span> vs. prior 30 days · billed on completion only
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
                View status <span className="arrow">→</span>
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
                View status <span className="arrow">→</span>
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
                View status <span className="arrow">→</span>
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
                3 →
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

      <div className="panel">
        <div className="panel-head">
          <div>
            <h3>Leads Funnel</h3>
            <div className="ph-sub">Where every prospect in the campaign sits right now</div>
          </div>
        </div>
        <div className="panel-pad">
          <div className="funnel" id="funnel">
            {FUNNEL.map((f) => (
              <div className="fn-row" data-w={f.w} key={f.label}>
                <span className="fl">
                  <span className="sd" style={{ background: f.color }} />
                  {f.label}
                </span>
                <div className="fn-track">
                  <div className="fn-fill" style={{ background: f.color }}>
                    <span className="fn-pct">{f.w}%</span>
                  </div>
                </div>
                <span className="fv">
                  <Sample>n</Sample>
                </span>
              </div>
            ))}
          </div>
          <div className="funnel-note">
            <span style={{ color: "var(--cerulean-deep)", fontWeight: 700 }}>↳</span>
            <span>
              Counts are <Sample>sample</Sample> placeholders. Bars show the relative shape of a
              healthy funnel: sourced narrows to booked meetings as quality gates apply.
            </span>
          </div>
        </div>
      </div>
    </>
  );
}
