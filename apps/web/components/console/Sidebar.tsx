"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { clearTokens } from "@/lib/api";
import { DEFAULT_CLIENT_PAGE } from "@/lib/client";
import { ClientSwitcher } from "./ClientSwitcher";
import { initialsOf, useMe } from "./MeContext";
import { NAV_ICONS } from "./NavIcons";
import { STATUS_TABS } from "./StatusTab";

export function Sidebar({
  slug,
  open,
  collapsed,
  onToggleCollapse,
}: {
  slug: string;
  open: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
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
        <div className="side-brand">
          <Link href={`${base}/${DEFAULT_CLIENT_PAGE}`} className="logo">
            <span className="dot" />
            <span className="txt">HoldSlot</span>
          </Link>
          <button
            type="button"
            className="side-collapse"
            onClick={onToggleCollapse}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? "»" : "«"}
          </button>
        </div>
        <ClientSwitcher currentSlug={slug} />
      </div>
      <nav className="side-nav">
        <span className="grp">Get Meeting</span>
        <Link
          href={`${base}/workspace`}
          className={clsx(onWorkspace && "active")}
          title="Workspace"
        >
          <span className="ico">{NAV_ICONS.workspace}</span>
          <span className="txt">Workspace</span>
        </Link>
        <Link
          href={`${base}/performance-summary`}
          className={clsx(onPerformance && "active")}
          title="Performance Summary"
        >
          <span className="ico">{NAV_ICONS.performance}</span>
          <span className="txt">Performance Summary</span>
        </Link>
        <span className="grp">Client Action</span>
        {STATUS_TABS.map(([key, label]) => (
          <Link
            key={key}
            href={`${base}/client-status/${key}`}
            className={clsx(pathname === `${base}/client-status/${key}` && "active")}
            title={label}
          >
            <span className="ico">{NAV_ICONS[key]}</span>
            <span className="txt">{label}</span>
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
