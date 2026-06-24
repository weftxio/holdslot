"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { clearTokens } from "@/lib/api";
import { DEFAULT_CLIENT_PAGE } from "@/lib/client";
import { ClientSwitcher } from "./ClientSwitcher";
import { initialsOf, useMe } from "./MeContext";
import { STATUS_TABS } from "./StatusTab";

export function Sidebar({ slug, open }: { slug: string; open: boolean }) {
  const pathname = usePathname();
  const base = `/${slug}`;
  const onPerformance = pathname === `${base}/performance-summary`;
  const onWorkspace = pathname.startsWith(`${base}/workspace`);

  const { me } = useMe();
  const name = me?.full_name || me?.email || "Loading…";
  const role = me?.clients.find((c) => c.slug === slug)?.role;
  const subtitle = role ? role[0].toUpperCase() + role.slice(1) : me?.email ? "Account" : "";

  return (
    <aside className={clsx("side", open && "open")}>
      <div className="side-top">
        <Link href={`${base}/${DEFAULT_CLIENT_PAGE}`} className="logo">
          <span className="dot" />
          HoldSlot
        </Link>
        <ClientSwitcher currentSlug={slug} />
      </div>
      <nav className="side-nav">
        <span className="grp">Get Meeting</span>
        <Link href={`${base}/workspace`} className={clsx(onWorkspace && "active")}>
          Workspace
        </Link>
        <Link href={`${base}/performance-summary`} className={clsx(onPerformance && "active")}>
          Performance Summary
        </Link>
        <span className="grp">Client Action</span>
        {STATUS_TABS.map(([key, label]) => (
          <Link
            key={key}
            href={`${base}/client-status/${key}`}
            className={clsx(pathname === `${base}/client-status/${key}` && "active")}
          >
            {label}
          </Link>
        ))}
      </nav>
      <div className="side-foot">
        <div className="av">{initialsOf(me)}</div>
        <div className="who">
          {name} <span>{subtitle}</span>
        </div>
        <Link href="/login" className="out" title="Sign out" onClick={() => clearTokens()}>
          ⏻
        </Link>
      </div>
    </aside>
  );
}
