"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { ClientSwitcher } from "./ClientSwitcher";
import { STATUS_TABS, useStatusTab } from "./StatusTab";

export function Sidebar({ slug, open }: { slug: string; open: boolean }) {
  const pathname = usePathname();
  const base = `/${slug}`;
  const onOverview = pathname === `${base}/overview`;
  const onWorkspace = pathname === `${base}/workspace`;
  const onStatus = pathname === `${base}/client-status`;
  const { tab, setTab } = useStatusTab();

  return (
    <aside className={clsx("side", open && "open")}>
      <div className="side-top">
        <Link href={`${base}/overview`} className="logo">
          <span className="dot" />
          HoldSlot
        </Link>
        <ClientSwitcher currentSlug={slug} />
      </div>
      <nav className="side-nav">
        <span className="grp">Get Meeting</span>
        <Link href={`${base}/overview`} className={clsx(onOverview && "active")}>
          Overview
        </Link>
        <Link href={`${base}/workspace`} className={clsx(onWorkspace && "active")}>
          Workspace
        </Link>
        <span className="grp">Client Action</span>
        {STATUS_TABS.map(([key, label]) => (
          <Link
            key={key}
            href={`${base}/client-status#${key}`}
            scroll={false}
            className={clsx(onStatus && tab === key && "active")}
            onClick={() => {
              setTab(key);
              if (typeof window !== "undefined") window.scrollTo({ top: 0 });
            }}
          >
            {label}
          </Link>
        ))}
      </nav>
      <div className="side-foot">
        <div className="av">OP</div>
        <div className="who">
          Operator <span>Outbound desk</span>
        </div>
        <Link href="/login" className="out" title="Sign out">
          ⏻
        </Link>
      </div>
    </aside>
  );
}
